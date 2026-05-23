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
)

const fieldSeparator = "\x1f"

var htmlTagPattern = regexp.MustCompile(`<[^>]*>`)

// Reader 封装对 Anki collection.anki2 的只读访问。
// 后端不会修改 Anki 数据库，避免破坏 Anki 自己的同步和学习状态。
type Reader struct {
	db       *sql.DB
	dbPath   string
	deckName string
	deckID   int64
	deckIDs  []int64
}

func NewReader(cfg config.AnkiConfig) (*Reader, error) {
	dbPath := strings.TrimSpace(cfg.DBPath)
	if dbPath == "" {
		return nil, errors.New("anki database path is empty")
	}

	if _, err := os.Stat(dbPath); err != nil {
		return nil, fmt.Errorf("anki database not found at %s: %w", dbPath, err)
	}

	db, err := openSQLite(dbPath)
	if err != nil {
		return nil, err
	}

	reader := &Reader{
		db:       db,
		dbPath:   dbPath,
		deckName: strings.TrimSpace(cfg.DeckName),
		deckID:   cfg.DeckID,
	}

	if deckIDs, err := reader.resolveDeckIDs(); err == nil && len(deckIDs) > 0 {
		reader.deckIDs = deckIDs
		reader.deckID = deckIDs[0]
	} else if reader.deckID != 0 {
		reader.deckIDs = []int64{reader.deckID}
	}

	return reader, nil
}

func openSQLite(dbPath string) (*sql.DB, error) {
	var lastErr error
	// The app now runs on local Linux/Docker, so use the CGO sqlite3 driver only.
	for _, dsn := range ankiDSNs(dbPath) {
		for _, driver := range []string{"sqlite3"} {
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
	}

	return nil, lastErr
}

func ankiDSNs(dbPath string) []string {
	escapedPath := filepath.ToSlash(dbPath)
	// 优先用普通只读连接，让 SQLite 能读取 collection.anki2-wal 中尚未 checkpoint 的数据。
	// 如果没有 WAL 或某些环境只支持不可变只读，再回退到 immutable=1。
	return []string{
		fmt.Sprintf("file:%s?mode=ro&cache=shared&_busy_timeout=5000&_pragma=busy_timeout(5000)", escapedPath),
		fmt.Sprintf("file:%s?mode=ro&immutable=1&cache=shared&_busy_timeout=5000&_pragma=busy_timeout(5000)", escapedPath),
	}
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
		// 分类筛选发生在解析字段之后，所以先多取一些随机单词，再在 Go 里过滤。
		queryLimit = limit * 20
		if queryLimit < 100 {
			queryLimit = 100
		}
		if queryLimit > 1000 {
			queryLimit = 1000
		}
	}

	deckIDs := r.learnedDeckIDs()
	args := append(int64Args(deckIDs), queryLimit)
	rows, err := r.db.Query(fmt.Sprintf(`
SELECT n.id, n.flds
FROM notes n
WHERE n.id IN (
    SELECT DISTINCT c.nid
    FROM cards c
    WHERE c.did IN (%s)
      AND (c.type >= 1 OR c.queue >= 2)
)
ORDER BY RANDOM()
LIMIT ?`, placeholders(len(deckIDs))), args...)
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

func (r *Reader) GetLearnedWordPool(category string) ([]models.Word, error) {
	if r == nil || r.db == nil {
		return nil, errors.New("anki reader is not available")
	}

	category = strings.TrimSpace(category)
	if category == "" {
		category = "all"
	}

	deckIDs := r.learnedDeckIDs()
	rows, err := r.db.Query(fmt.Sprintf(`
SELECT n.id, n.flds
FROM notes n
WHERE n.id IN (
    SELECT DISTINCT c.nid
    FROM cards c
    WHERE c.did IN (%s)
      AND (c.type >= 1 OR c.queue >= 2)
)
ORDER BY n.id`, placeholders(len(deckIDs))), int64Args(deckIDs)...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var words []models.Word
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
	deckIDs := r.learnedDeckIDs()
	err := r.db.QueryRow(fmt.Sprintf(`
SELECT COUNT(DISTINCT c.nid)
FROM cards c
WHERE c.did IN (%s)
  AND (c.type >= 1 OR c.queue >= 2)`, placeholders(len(deckIDs))), int64Args(deckIDs)...).Scan(&total)
	return total, err
}

func ParseWord(id int64, rawFields string) (models.Word, bool) {
	// Anki notes.flds 使用 ASCII 31(Unit Separator) 分隔字段。
	// 本项目生成牌组的字段顺序是 Word, Phonetic, PartOfSpeech, ChineseMeaning, ...
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
	// Anki 字段中可能有 HTML 高亮、<br> 和实体编码；API 返回给前端前先转成纯文本。
	value = html.UnescapeString(value)
	value = strings.ReplaceAll(value, "<br>", "\n")
	value = strings.ReplaceAll(value, "<br/>", "\n")
	value = strings.ReplaceAll(value, "<br />", "\n")
	value = htmlTagPattern.ReplaceAllString(value, "")
	return strings.TrimSpace(value)
}

func (r *Reader) resolveDeckID() (int64, error) {
	deckIDs, err := r.resolveDeckIDs()
	if err != nil || len(deckIDs) == 0 {
		return 0, err
	}
	return deckIDs[0], nil
}

func (r *Reader) resolveDeckIDs() ([]int64, error) {
	if r.deckName != "" {
		if ids, err := r.resolveDeckIDsFromDecksTable(); err == nil && len(ids) > 0 {
			return ids, nil
		}
		if ids, err := r.resolveDeckIDsFromLegacyCol(); err == nil && len(ids) > 0 {
			return ids, nil
		}
	}

	if r.deckID != 0 {
		return []int64{r.deckID}, nil
	}
	return nil, errors.New("deck not found")
}

func (r *Reader) resolveDeckIDFromDecksTable() (int64, error) {
	ids, err := r.resolveDeckIDsFromDecksTable()
	if err != nil || len(ids) == 0 {
		return 0, err
	}
	return ids[0], nil
}

func (r *Reader) resolveDeckIDsFromDecksTable() ([]int64, error) {
	if ok, err := r.tableExists("decks"); err != nil || !ok {
		return nil, err
	}

	// 不在 SQL 里用 WHERE name = ?，因为 Anki 新库的 name 使用 unicase collation，
	// 纯 Go SQLite 驱动未必认识这个 collation；读出来在 Go 里比较最稳。
	rows, err := r.db.Query(`SELECT id, name FROM decks`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var exact []int64
	var children []int64
	for rows.Next() {
		var id int64
		var name string
		if err := rows.Scan(&id, &name); err != nil {
			return nil, err
		}
		if name == r.deckName {
			exact = append(exact, id)
			continue
		}
		if isChildDeck(name, r.deckName) {
			children = append(children, id)
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	return append(exact, children...), nil
}

func (r *Reader) resolveDeckIDFromLegacyCol() (int64, error) {
	ids, err := r.resolveDeckIDsFromLegacyCol()
	if err != nil || len(ids) == 0 {
		return 0, err
	}
	return ids[0], nil
}

func (r *Reader) resolveDeckIDsFromLegacyCol() ([]int64, error) {
	var raw sql.NullString
	if err := r.db.QueryRow(`SELECT decks FROM col LIMIT 1`).Scan(&raw); err != nil {
		return nil, err
	}
	if !raw.Valid || strings.TrimSpace(raw.String) == "" {
		return nil, nil
	}

	var decks map[string]struct {
		Name string `json:"name"`
	}
	if err := json.Unmarshal([]byte(raw.String), &decks); err != nil {
		return nil, err
	}

	var exact []int64
	var children []int64
	for idText, deck := range decks {
		if deck.Name != r.deckName && !isChildDeck(deck.Name, r.deckName) {
			continue
		}
		var id int64
		if _, err := fmt.Sscanf(idText, "%d", &id); err != nil {
			return nil, err
		}
		if deck.Name == r.deckName {
			exact = append(exact, id)
		} else {
			children = append(children, id)
		}
	}

	return append(exact, children...), nil
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

func (r *Reader) learnedDeckIDs() []int64 {
	if len(r.deckIDs) > 0 {
		return r.deckIDs
	}
	if r.deckID != 0 {
		return []int64{r.deckID}
	}
	return []int64{0}
}

func isChildDeck(name, parent string) bool {
	parent = strings.TrimSpace(parent)
	return parent != "" && strings.HasPrefix(name, parent+"::")
}

func placeholders(count int) string {
	if count <= 1 {
		return "?"
	}
	return strings.TrimRight(strings.Repeat("?,", count), ",")
}

func int64Args(values []int64) []any {
	args := make([]any, len(values))
	for index, value := range values {
		args[index] = value
	}
	return args
}
