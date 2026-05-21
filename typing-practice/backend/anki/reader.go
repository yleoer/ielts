package anki

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"typing-practice/config"
	"typing-practice/models"

	_ "github.com/mattn/go-sqlite3"
	_ "modernc.org/sqlite"
)

const fieldSeparator = "\x1f"

var htmlTagPattern = regexp.MustCompile(`<[^>]*>`)

type Reader struct {
	db       *sql.DB
	dbPath   string
	deckName string
	deckID   int64
}

func NewReader(cfg config.AnkiConfig) (*Reader, error) {
	dbPath := strings.TrimSpace(cfg.DBPath)
	if dbPath == "" {
		return nil, errors.New("anki database path is empty")
	}

	if _, err := os.Stat(dbPath); err != nil {
		return nil, fmt.Errorf("anki database not found at %s: %w", dbPath, err)
	}

	dsn := fmt.Sprintf("file:%s?mode=ro&cache=shared&_busy_timeout=5000", filepath.ToSlash(dbPath))
	db, err := openSQLite(dsn)
	if err != nil {
		return nil, err
	}

	reader := &Reader{
		db:       db,
		dbPath:   dbPath,
		deckName: strings.TrimSpace(cfg.DeckName),
		deckID:   cfg.DeckID,
	}

	if deckID, err := reader.resolveDeckID(); err == nil && deckID != 0 {
		reader.deckID = deckID
	}

	return reader, nil
}

func openSQLite(dsn string) (*sql.DB, error) {
	var lastErr error
	for _, driver := range []string{"sqlite3", "sqlite"} {
		db, err := sql.Open(driver, dsn)
		if err != nil {
			lastErr = err
			continue
		}

		if err := db.Ping(); err != nil {
			_ = db.Close()
			lastErr = err
			continue
		}

		return db, nil
	}

	return nil, lastErr
}

func (r *Reader) Close() error {
	if r == nil || r.db == nil {
		return nil
	}
	return r.db.Close()
}

func (r *Reader) DBPath() string {
	if r == nil {
		return ""
	}
	return r.dbPath
}

func (r *Reader) DeckName() string {
	if r == nil {
		return ""
	}
	return r.deckName
}

func (r *Reader) DeckID() int64 {
	if r == nil {
		return 0
	}
	return r.deckID
}

func (r *Reader) GetLearnedWords(limit int, category string) ([]models.Word, error) {
	if r == nil || r.db == nil {
		return nil, errors.New("anki reader is not available")
	}

	category = strings.TrimSpace(category)
	if category == "" {
		category = "all"
	}

	queryLimit := limit
	if !strings.EqualFold(category, "all") {
		queryLimit = limit * 20
		if queryLimit < 100 {
			queryLimit = 100
		}
		if queryLimit > 1000 {
			queryLimit = 1000
		}
	}

	rows, err := r.db.Query(`
SELECT n.id, n.flds
FROM notes n
WHERE n.id IN (
    SELECT DISTINCT c.nid
    FROM cards c
    WHERE c.did = ?
      AND (c.type >= 1 OR c.queue >= 2)
)
ORDER BY RANDOM()
LIMIT ?`, r.deckID, queryLimit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	words := make([]models.Word, 0, limit)
	for rows.Next() {
		var id int64
		var fields string
		if err := rows.Scan(&id, &fields); err != nil {
			return nil, err
		}

		word, ok := ParseWord(id, fields)
		if !ok {
			continue
		}
		if !strings.EqualFold(category, "all") && !strings.EqualFold(word.Category, category) {
			continue
		}

		words = append(words, word)
		if len(words) >= limit {
			break
		}
	}

	return words, rows.Err()
}

func (r *Reader) GetWordByID(id int64) (models.Word, error) {
	if r == nil || r.db == nil {
		return models.Word{}, errors.New("anki reader is not available")
	}

	var fields string
	err := r.db.QueryRow(`SELECT flds FROM notes WHERE id = ?`, id).Scan(&fields)
	if err != nil {
		return models.Word{}, err
	}

	word, ok := ParseWord(id, fields)
	if !ok {
		return models.Word{}, fmt.Errorf("note %d does not contain the expected word fields", id)
	}
	return word, nil
}

func (r *Reader) CountLearned() (int, error) {
	if r == nil || r.db == nil {
		return 0, errors.New("anki reader is not available")
	}

	var total int
	err := r.db.QueryRow(`
SELECT COUNT(DISTINCT c.nid)
FROM cards c
WHERE c.did = ?
  AND (c.type >= 1 OR c.queue >= 2)`, r.deckID).Scan(&total)
	return total, err
}

func ParseWord(id int64, rawFields string) (models.Word, bool) {
	fields := strings.Split(rawFields, fieldSeparator)
	if len(fields) < 4 {
		return models.Word{}, false
	}

	word := models.Word{
		ID:             id,
		Word:           cleanField(fields[0]),
		Phonetic:       cleanField(fields[1]),
		PartOfSpeech:   cleanField(fields[2]),
		ChineseMeaning: cleanField(fields[3]),
	}

	if len(fields) > 4 {
		word.ExampleEN = cleanField(fields[4])
	}
	if len(fields) > 5 {
		word.ExampleCN = cleanField(fields[5])
	}
	if len(fields) > 7 {
		word.Category = cleanField(fields[7])
	}

	if word.Word == "" || word.ChineseMeaning == "" {
		return models.Word{}, false
	}

	return word, true
}

func cleanField(value string) string {
	value = html.UnescapeString(value)
	value = strings.ReplaceAll(value, "<br>", "\n")
	value = strings.ReplaceAll(value, "<br/>", "\n")
	value = strings.ReplaceAll(value, "<br />", "\n")
	value = htmlTagPattern.ReplaceAllString(value, "")
	return strings.TrimSpace(value)
}

func (r *Reader) resolveDeckID() (int64, error) {
	if r.deckName != "" {
		if id, err := r.resolveDeckIDFromDecksTable(); err == nil && id != 0 {
			return id, nil
		}
		if id, err := r.resolveDeckIDFromLegacyCol(); err == nil && id != 0 {
			return id, nil
		}
	}

	if r.deckID != 0 {
		return r.deckID, nil
	}
	return 0, errors.New("deck not found")
}

func (r *Reader) resolveDeckIDFromDecksTable() (int64, error) {
	if ok, err := r.tableExists("decks"); err != nil || !ok {
		return 0, err
	}

	rows, err := r.db.Query(`SELECT id, name FROM decks`)
	if err != nil {
		return 0, err
	}
	defer rows.Close()

	for rows.Next() {
		var id int64
		var name string
		if err := rows.Scan(&id, &name); err != nil {
			return 0, err
		}
		if name == r.deckName {
			return id, nil
		}
	}
	if err := rows.Err(); err != nil {
		return 0, err
	}

	return 0, nil
}

func (r *Reader) resolveDeckIDFromLegacyCol() (int64, error) {
	var raw sql.NullString
	if err := r.db.QueryRow(`SELECT decks FROM col LIMIT 1`).Scan(&raw); err != nil {
		return 0, err
	}
	if !raw.Valid || strings.TrimSpace(raw.String) == "" {
		return 0, nil
	}

	var decks map[string]struct {
		Name string `json:"name"`
	}
	if err := json.Unmarshal([]byte(raw.String), &decks); err != nil {
		return 0, err
	}

	for idText, deck := range decks {
		if deck.Name != r.deckName {
			continue
		}
		var id int64
		if _, err := fmt.Sscanf(idText, "%d", &id); err != nil {
			return 0, err
		}
		return id, nil
	}

	return 0, nil
}

func (r *Reader) tableExists(tableName string) (bool, error) {
	var count int
	err := r.db.QueryRow(`
SELECT COUNT(*)
FROM sqlite_master
WHERE type = 'table'
  AND name = ?`, tableName).Scan(&count)
	return count > 0, err
}
