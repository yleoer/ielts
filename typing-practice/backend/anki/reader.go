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

	// deck_id 在不同导入环境可能会变化，所以优先用 deck_name 解析真实 ID。
	if deckID, err := reader.resolveDeckID(); err == nil && deckID != 0 {
		reader.deckID = deckID
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
	// immutable=1 告诉 SQLite 这个文件由外部管理且本连接绝不写入，
	// 因此读取时不会再向 Anki 的 collection.anki2 申请锁。
	// 如果某个运行环境不支持 immutable，再回退到普通 mode=ro 只读连接。
	return []string{
		fmt.Sprintf("file:%s?mode=ro&immutable=1&cache=shared&_busy_timeout=5000&_pragma=busy_timeout(5000)", escapedPath),
		fmt.Sprintf("file:%s?mode=ro&cache=shared&_busy_timeout=5000&_pragma=busy_timeout(5000)", escapedPath),
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
	// 新版 Anki 有独立 decks 表；旧版/导入包可能仍把 decks JSON 放在 col 表里。
	// 两种都尝试，最后才回退到配置里的固定 deck_id。
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

	// 不在 SQL 里用 WHERE name = ?，因为 Anki 新库的 name 使用 unicase collation，
	// 纯 Go SQLite 驱动未必认识这个 collation；读出来在 Go 里比较最稳。
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
