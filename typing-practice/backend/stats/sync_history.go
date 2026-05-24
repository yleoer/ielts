package stats

import (
	"strings"
	"time"
)

type AnkiSyncWord struct {
	ID             int64
	Word           string
	ChineseMeaning string
	Category       string
}

type AnkiSyncHistoryEntry struct {
	SyncedAt      time.Time
	BeforeWords   int
	AfterWords    int
	AddedWords    int
	AddedWordList []AnkiSyncWord
	Success       bool
	Message       string
	SourcePath    string
	TargetPath    string
}

func (s *Store) SaveAnkiSyncHistory(entry AnkiSyncHistoryEntry) error {
	if s == nil || s.db == nil || entry.AddedWords <= 0 || len(entry.AddedWordList) == 0 {
		return nil
	}
	if entry.SyncedAt.IsZero() {
		entry.SyncedAt = time.Now()
	}

	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	result, err := tx.Exec(`
INSERT INTO anki_sync_history (
    synced_at, before_words, after_words, added_words,
    success, message, source_path, target_path
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		formatTime(entry.SyncedAt),
		entry.BeforeWords,
		entry.AfterWords,
		entry.AddedWords,
		entry.Success,
		entry.Message,
		entry.SourcePath,
		entry.TargetPath,
	)
	if err != nil {
		return err
	}

	syncID, err := result.LastInsertId()
	if err != nil {
		return err
	}

	for _, word := range entry.AddedWordList {
		if strings.TrimSpace(word.Word) == "" {
			continue
		}
		if _, err := tx.Exec(`
INSERT INTO anki_sync_added_words (
    sync_id, word_id, word, chinese_meaning, category
) VALUES (?, ?, ?, ?, ?)`,
			syncID,
			word.ID,
			strings.TrimSpace(word.Word),
			strings.TrimSpace(word.ChineseMeaning),
			strings.TrimSpace(word.Category),
		); err != nil {
			return err
		}
	}

	return tx.Commit()
}

func (s *Store) ListAnkiSyncHistory(limit int) ([]AnkiSyncHistoryEntry, error) {
	if s == nil || s.db == nil {
		return nil, nil
	}
	if limit <= 0 || limit > 50 {
		limit = 50
	}

	rows, err := s.db.Query(`
SELECT id, synced_at, before_words, after_words, added_words,
       success, COALESCE(message, ''), COALESCE(source_path, ''), COALESCE(target_path, '')
FROM anki_sync_history
ORDER BY synced_at DESC, id DESC
LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}

	type historyRow struct {
		id     int64
		entry  AnkiSyncHistoryEntry
		synced string
	}
	items := make([]historyRow, 0)
	for rows.Next() {
		var item historyRow
		if err := rows.Scan(
			&item.id,
			&item.synced,
			&item.entry.BeforeWords,
			&item.entry.AfterWords,
			&item.entry.AddedWords,
			&item.entry.Success,
			&item.entry.Message,
			&item.entry.SourcePath,
			&item.entry.TargetPath,
		); err != nil {
			_ = rows.Close()
			return nil, err
		}
		item.entry.SyncedAt = parseDBTime(item.synced)
		items = append(items, item)
	}
	if err := rows.Close(); err != nil {
		return nil, err
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	history := make([]AnkiSyncHistoryEntry, 0, len(items))
	for _, item := range items {
		words, err := s.listAnkiSyncWords(item.id)
		if err != nil {
			return nil, err
		}
		item.entry.AddedWordList = words
		history = append(history, item.entry)
	}
	return history, nil
}

func (s *Store) listAnkiSyncWords(syncID int64) ([]AnkiSyncWord, error) {
	rows, err := s.db.Query(`
SELECT COALESCE(word_id, 0), word, COALESCE(chinese_meaning, ''), COALESCE(category, '')
FROM anki_sync_added_words
WHERE sync_id = ?
ORDER BY id ASC`, syncID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	words := make([]AnkiSyncWord, 0)
	for rows.Next() {
		var word AnkiSyncWord
		if err := rows.Scan(&word.ID, &word.Word, &word.ChineseMeaning, &word.Category); err != nil {
			return nil, err
		}
		words = append(words, word)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return words, nil
}
