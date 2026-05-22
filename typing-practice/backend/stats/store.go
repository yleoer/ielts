package stats

import (
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type Store struct {
	db *sql.DB
}

func Open(path string) (*Store, error) {
	// 统计数据库默认放在 backend/data/stats.db；Docker 中可用 STATS_DB_PATH 覆盖。
	if strings.TrimSpace(path) == "" {
		path = filepath.Join("data", "stats.db")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}

	dsn := fmt.Sprintf("file:%s?cache=shared&_busy_timeout=5000", filepath.ToSlash(path))
	db, err := openSQLite(dsn)
	if err != nil {
		return nil, err
	}

	// SQLite 写入并发能力有限，限制为单连接可以减少锁冲突。
	db.SetMaxOpenConns(1)
	if _, err := db.Exec(`PRAGMA foreign_keys = ON`); err != nil {
		_ = db.Close()
		return nil, err
	}
	if _, err := db.Exec(schema); err != nil {
		_ = db.Close()
		return nil, err
	}

	return &Store{db: db}, nil
}

func (s *Store) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func openSQLite(dsn string) (*sql.DB, error) {
	var lastErr error
	// 现在只面向本地服务器和 Docker 运行，统一使用 CGO sqlite3 驱动。
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
	return nil, lastErr
}

func (s *Store) SaveSession(session SessionRequest) error {
	// 保存 session 的过程必须是事务：
	// 1. upsert practice_sessions
	// 2. 替换这个 session 的 word_attempts
	// 3. 根据所有 attempts 重建 word_mastery
	// 这样同一个 session_id 重复提交时不会把掌握度重复累计。
	if err := validateSession(session); err != nil {
		return err
	}
	if session.UserID == "" {
		session.UserID = "default"
	}
	if session.Accuracy == 0 && session.TotalWords > 0 {
		// 允许调用方不传 accuracy，由后端按 correct/total 补算。
		session.Accuracy = float64(session.CorrectWords) * 100 / float64(session.TotalWords)
	}

	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	endTime := nullableTime(session.EndTime)
	_, err = tx.Exec(`
INSERT INTO practice_sessions (
    session_id, user_id, start_time, end_time, total_words, correct_words,
    incorrect_words, accuracy, duration_seconds
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(session_id) DO UPDATE SET
    user_id = excluded.user_id,
    start_time = excluded.start_time,
    end_time = excluded.end_time,
    total_words = excluded.total_words,
    correct_words = excluded.correct_words,
    incorrect_words = excluded.incorrect_words,
    accuracy = excluded.accuracy,
    duration_seconds = excluded.duration_seconds`,
		session.SessionID,
		session.UserID,
		formatTime(session.StartTime),
		endTime,
		session.TotalWords,
		session.CorrectWords,
		session.IncorrectWords,
		session.Accuracy,
		session.DurationSeconds,
	)
	if err != nil {
		return err
	}

	if _, err := tx.Exec(`DELETE FROM word_attempts WHERE session_id = ?`, session.SessionID); err != nil {
		return err
	}

	for _, attempt := range session.WordAttempts {
		if strings.TrimSpace(attempt.Word) == "" {
			continue
		}
		errorType := ""
		if attempt.ErrorType != nil {
			errorType = strings.TrimSpace(*attempt.ErrorType)
		}
		if !attempt.IsCorrect && errorType == "" {
			// 前端未传错误类型时，由后端根据 expected/user_input 自动判断。
			errorType = AnalyzeErrorType(attempt.Word, attempt.UserInput)
		}

		_, err := tx.Exec(`
INSERT INTO word_attempts (
    session_id, word, chinese_meaning, category, user_input,
    is_correct, time_spent, error_type, attempt_time
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			session.SessionID,
			strings.TrimSpace(attempt.Word),
			strings.TrimSpace(attempt.ChineseMeaning),
			strings.TrimSpace(attempt.Category),
			attempt.UserInput,
			attempt.IsCorrect,
			nullableFloat(attempt.TimeSpent),
			errorType,
			formatTime(session.StartTime),
		)
		if err != nil {
			return err
		}

	}

	if err := rebuildWordMastery(tx); err != nil {
		return err
	}

	if err := tx.Commit(); err != nil {
		return err
	}

	return s.CheckAndCreateMilestones(session)
}

func validateSession(session SessionRequest) error {
	// 这里做业务一致性校验，不只依赖 Gin binding。
	// 例如 correct + incorrect 必须等于 total，否则图表统计会失真。
	if strings.TrimSpace(session.SessionID) == "" {
		return errors.New("session_id is required")
	}
	if session.TotalWords <= 0 {
		return errors.New("total_words must be positive")
	}
	if session.CorrectWords < 0 || session.IncorrectWords < 0 {
		return errors.New("correct_words and incorrect_words must be non-negative")
	}
	if session.CorrectWords+session.IncorrectWords != session.TotalWords {
		return errors.New("correct_words + incorrect_words must equal total_words")
	}
	if session.StartTime.IsZero() {
		return errors.New("start_time is required")
	}
	if session.EndTime != nil && session.EndTime.Before(session.StartTime) {
		return errors.New("end_time must be after start_time")
	}
	if session.Accuracy < 0 || session.Accuracy > 100 {
		return errors.New("accuracy must be between 0 and 100")
	}
	if session.DurationSeconds < 0 {
		return errors.New("duration_seconds must be non-negative")
	}
	return nil
}

func rebuildWordMastery(tx *sql.Tx) error {
	// 选择“从 word_attempts 全量重建 mastery”，而不是每次增量 +1。
	// 好处是 SaveSession 幂等：重复提交同一个 session 不会让 mastery 变大。
	if _, err := tx.Exec(`DELETE FROM word_mastery`); err != nil {
		return err
	}

	rows, err := tx.Query(`
SELECT word,
       COUNT(*) AS total_attempts,
       SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct_attempts,
       SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) AS incorrect_attempts,
       COALESCE(AVG(time_spent), 0) AS average_time,
       MAX(attempt_time) AS last_attempt_time
FROM word_attempts
GROUP BY word`)
	if err != nil {
		return err
	}
	defer rows.Close()

	type aggregate struct {
		word              string
		totalAttempts     int
		correctAttempts   int
		incorrectAttempts int
		averageTime       float64
		lastAttemptTime   string
	}

	var aggregates []aggregate
	for rows.Next() {
		var item aggregate
		if err := rows.Scan(
			&item.word,
			&item.totalAttempts,
			&item.correctAttempts,
			&item.incorrectAttempts,
			&item.averageTime,
			&item.lastAttemptTime,
		); err != nil {
			return err
		}
		aggregates = append(aggregates, item)
	}
	if err := rows.Err(); err != nil {
		return err
	}

	for _, item := range aggregates {
		level := CalculateMasteryLevel(WordMastery{
			Word:              item.word,
			TotalAttempts:     item.totalAttempts,
			CorrectAttempts:   item.correctAttempts,
			IncorrectAttempts: item.incorrectAttempts,
			AverageTime:       item.averageTime,
		})
		if _, err := tx.Exec(`
INSERT INTO word_mastery (
    word, total_attempts, correct_attempts, incorrect_attempts,
    mastery_level, last_attempt_time, average_time, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`,
			item.word,
			item.totalAttempts,
			item.correctAttempts,
			item.incorrectAttempts,
			level,
			item.lastAttemptTime,
			item.averageTime,
		); err != nil {
			return err
		}
	}

	return nil
}

func updateWordMastery(tx *sql.Tx, attempt AttemptRequest) error {
	// 早期的增量更新实现，目前保留作参考。
	// 当前 SaveSession 使用 rebuildWordMastery 来保证重复提交时统计不会翻倍。
	word := strings.TrimSpace(attempt.Word)
	var current WordMastery
	err := tx.QueryRow(`
SELECT word, total_attempts, correct_attempts, incorrect_attempts, mastery_level, COALESCE(average_time, 0)
FROM word_mastery
WHERE word = ?`, word).Scan(
		&current.Word,
		&current.TotalAttempts,
		&current.CorrectAttempts,
		&current.IncorrectAttempts,
		&current.MasteryLevel,
		&current.AverageTime,
	)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return err
	}

	current.Word = word
	current.TotalAttempts++
	if attempt.IsCorrect {
		current.CorrectAttempts++
	} else {
		current.IncorrectAttempts++
	}
	if attempt.TimeSpent != nil && *attempt.TimeSpent > 0 {
		if current.AverageTime <= 0 {
			current.AverageTime = *attempt.TimeSpent
		} else {
			current.AverageTime = ((current.AverageTime * float64(current.TotalAttempts-1)) + *attempt.TimeSpent) / float64(current.TotalAttempts)
		}
	}
	current.MasteryLevel = CalculateMasteryLevel(current)

	_, err = tx.Exec(`
INSERT INTO word_mastery (
    word, total_attempts, correct_attempts, incorrect_attempts,
    mastery_level, last_attempt_time, average_time, updated_at
) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP)
ON CONFLICT(word) DO UPDATE SET
    total_attempts = excluded.total_attempts,
    correct_attempts = excluded.correct_attempts,
    incorrect_attempts = excluded.incorrect_attempts,
    mastery_level = excluded.mastery_level,
    last_attempt_time = excluded.last_attempt_time,
    average_time = excluded.average_time,
    updated_at = excluded.updated_at`,
		current.Word,
		current.TotalAttempts,
		current.CorrectAttempts,
		current.IncorrectAttempts,
		current.MasteryLevel,
		current.AverageTime,
	)
	return err
}

func CalculateMasteryLevel(m WordMastery) string {
	// 掌握等级规则来自 STATISTICS-SPEC.md：
	// 错误多于正确为 weak；正确次数逐步进入 learning/familiar/mastered。
	if m.TotalAttempts == 0 {
		return "new"
	}
	if m.IncorrectAttempts > m.CorrectAttempts {
		return "weak"
	}
	if m.CorrectAttempts >= 6 {
		return "mastered"
	}
	if m.CorrectAttempts >= 3 {
		return "familiar"
	}
	if m.CorrectAttempts >= 1 {
		return "learning"
	}
	return "weak"
}

func nullableTime(value *time.Time) any {
	if value == nil || value.IsZero() {
		return nil
	}
	return formatTime(*value)
}

func nullableFloat(value *float64) any {
	if value == nil {
		return nil
	}
	return *value
}

func formatTime(value time.Time) string {
	return value.UTC().Format(time.RFC3339)
}
