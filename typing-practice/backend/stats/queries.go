package stats

import (
	"fmt"
	"time"
)

func (s *Store) Heatmap(startDate, endDate string) ([]HeatmapPoint, error) {
	// 热力图按天聚合 session 数量和平均正确率。
	if startDate == "" {
		startDate = time.Now().UTC().AddDate(0, 0, -365).Format("2006-01-02")
	}
	if endDate == "" {
		endDate = time.Now().UTC().Format("2006-01-02")
	}

	rows, err := s.db.Query(`
SELECT date(start_time) AS practice_date,
       COUNT(*) AS session_count,
       COALESCE(AVG(accuracy), 0) AS accuracy
FROM practice_sessions
WHERE date(start_time) BETWEEN ? AND ?
GROUP BY date(start_time)
ORDER BY practice_date`, startDate, endDate)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []HeatmapPoint
	for rows.Next() {
		var item HeatmapPoint
		if err := rows.Scan(&item.Date, &item.Count, &item.Accuracy); err != nil {
			return nil, err
		}
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) AccuracyTrend(days int) ([]AccuracyTrendPoint, error) {
	// 正确率趋势用“总正确数 / 总单词数”计算，避免简单平均 session accuracy 造成偏差。
	rows, err := s.db.Query(`
SELECT date(start_time) AS practice_date,
       COALESCE(SUM(correct_words) * 100.0 / NULLIF(SUM(total_words), 0), 0) AS accuracy,
       COALESCE(SUM(total_words), 0) AS total_words
FROM practice_sessions
WHERE date(start_time) >= date(?)
GROUP BY date(start_time)
ORDER BY practice_date`, sinceDate(days))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []AccuracyTrendPoint
	for rows.Next() {
		var item AccuracyTrendPoint
		if err := rows.Scan(&item.Date, &item.Accuracy, &item.TotalWords); err != nil {
			return nil, err
		}
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) MasteryDistribution() (map[string]int, error) {
	// 预置所有等级为 0，保证前端饼图即使没有某类数据也能稳定渲染。
	data := map[string]int{
		"mastered": 0,
		"familiar": 0,
		"learning": 0,
		"weak":     0,
		"new":      0,
	}

	rows, err := s.db.Query(`
SELECT mastery_level, COUNT(*)
FROM word_mastery
GROUP BY mastery_level`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var level string
		var count int
		if err := rows.Scan(&level, &count); err != nil {
			return nil, err
		}
		data[level] = count
	}
	return data, rows.Err()
}

func (s *Store) MasteryWords(level string, limit int) ([]MasteryWordDetail, error) {
	// 明细弹窗可能一次展示较多单词，但仍限制上限，避免一次查询拖慢页面。
	if limit <= 0 {
		limit = 200
	}
	if limit > 1000 {
		limit = 1000
	}

	rows, err := s.db.Query(`
WITH latest_meaning AS (
    SELECT word,
           chinese_meaning,
           ROW_NUMBER() OVER (PARTITION BY word ORDER BY attempt_time DESC, id DESC) AS row_number
    FROM word_attempts
    WHERE COALESCE(chinese_meaning, '') <> ''
)
SELECT wm.word,
       COALESCE(lm.chinese_meaning, '') AS chinese_meaning,
       wm.total_attempts,
       wm.correct_attempts,
       wm.incorrect_attempts,
       COALESCE(wm.correct_attempts * 100.0 / NULLIF(wm.total_attempts, 0), 0) AS accuracy,
       COALESCE(wm.average_time, 0) AS average_time
FROM word_mastery wm
LEFT JOIN latest_meaning lm
  ON lm.word = wm.word
 AND lm.row_number = 1
WHERE wm.mastery_level = ?
-- 优先展示最需要复习的词：错误多、练习多的排在前面。
ORDER BY wm.incorrect_attempts DESC, wm.total_attempts DESC, wm.word ASC
LIMIT ?`, level, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []MasteryWordDetail
	for rows.Next() {
		var item MasteryWordDetail
		if err := rows.Scan(
			&item.Word,
			&item.ChineseMeaning,
			&item.TotalAttempts,
			&item.CorrectAttempts,
			&item.IncorrectAttempts,
			&item.Accuracy,
			&item.AverageTime,
		); err != nil {
			return nil, err
		}
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) SelectionStatsByWord() (map[string]SelectionStats, error) {
	// 练习选词算法需要一个轻量索引：每个词的掌握度、错误次数、平均耗时和最近一次结果。
	rows, err := s.db.Query(`
WITH latest_attempt AS (
    SELECT word,
           is_correct,
           attempt_time,
           ROW_NUMBER() OVER (PARTITION BY word ORDER BY attempt_time DESC, id DESC) AS row_number
    FROM word_attempts
)
SELECT wm.word,
       wm.total_attempts,
       wm.correct_attempts,
       wm.incorrect_attempts,
       wm.mastery_level,
       COALESCE(wm.average_time, 0),
       COALESCE(wm.last_attempt_time, ''),
       COALESCE(la.is_correct, 1)
FROM word_mastery wm
LEFT JOIN latest_attempt la
  ON la.word = wm.word
 AND la.row_number = 1`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	data := make(map[string]SelectionStats)
	for rows.Next() {
		var item SelectionStats
		var lastAttempt string
		var lastCorrect int
		if err := rows.Scan(
			&item.Word,
			&item.TotalAttempts,
			&item.CorrectAttempts,
			&item.IncorrectAttempts,
			&item.MasteryLevel,
			&item.AverageTime,
			&lastAttempt,
			&lastCorrect,
		); err != nil {
			return nil, err
		}
		item.LastAttemptTime = parseDBTime(lastAttempt)
		item.LastAttemptCorrect = lastCorrect != 0
		data[item.Word] = item
	}
	return data, rows.Err()
}

func (s *Store) SpeedTrend(days int) ([]SpeedTrendPoint, error) {
	// 打字速度趋势使用 word_attempts.time_spent 的每日平均值。
	// 前端图表可以反转 Y 轴，让“时间越短越好”更直观。
	rows, err := s.db.Query(`
SELECT date(attempt_time) AS practice_date,
       COALESCE(AVG(time_spent), 0) AS average_time,
       COUNT(*) AS word_count
FROM word_attempts
WHERE time_spent IS NOT NULL
  AND date(attempt_time) >= date(?)
GROUP BY date(attempt_time)
ORDER BY practice_date`, sinceDate(days))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []SpeedTrendPoint
	for rows.Next() {
		var item SpeedTrendPoint
		if err := rows.Scan(&item.Date, &item.AverageTime, &item.WordCount); err != nil {
			return nil, err
		}
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) DailyDuration(days int) ([]DailyDurationPoint, error) {
	// 每日练习时长来自 session.duration_seconds，单位在 API 层转为分钟。
	rows, err := s.db.Query(`
SELECT date(start_time) AS practice_date,
       COALESCE(SUM(duration_seconds), 0) / 60.0 AS duration_minutes,
       COUNT(*) AS session_count
FROM practice_sessions
WHERE date(start_time) >= date(?)
GROUP BY date(start_time)
ORDER BY practice_date`, sinceDate(days))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []DailyDurationPoint
	for rows.Next() {
		var item DailyDurationPoint
		if err := rows.Scan(&item.Date, &item.DurationMinutes, &item.SessionCount); err != nil {
			return nil, err
		}
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) Streak() (StreakData, error) {
	// 连续学习不看练习次数，只看某一天是否至少有一次 session。
	dates, err := s.practiceDates()
	if err != nil {
		return StreakData{}, err
	}
	current, longest := calculateStreaks(dates, time.Now().UTC())
	return StreakData{
		CurrentStreak: current,
		LongestStreak: longest,
		TotalDays:     len(dates),
		PracticeDates: dates,
	}, nil
}

func (s *Store) ErrorTypes() (map[string]int, error) {
	// 同样预置所有错误类型，避免前端遇到缺失 key。
	data := map[string]int{
		"spelling":         0,
		"missing_letter":   0,
		"extra_letter":     0,
		"completely_wrong": 0,
		"skipped":          0,
	}

	rows, err := s.db.Query(`
SELECT COALESCE(NULLIF(error_type, ''), 'spelling') AS type_name, COUNT(*)
FROM word_attempts
WHERE is_correct = 0
GROUP BY type_name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var errorType string
		var count int
		if err := rows.Scan(&errorType, &count); err != nil {
			return nil, err
		}
		data[errorType] = count
	}
	return data, rows.Err()
}

func (s *Store) ErrorTypeWords(errorType string, limit int) ([]ErrorTypeWordDetail, error) {
	// 错误类型明细用于图表点击后的弹窗，limit 上限保护页面和 SQLite 查询。
	if limit <= 0 {
		limit = 200
	}
	if limit > 1000 {
		limit = 1000
	}

	rows, err := s.db.Query(`
WITH filtered AS (
    SELECT id, word, chinese_meaning, category, user_input, attempt_time
    FROM word_attempts
    WHERE is_correct = 0
      AND COALESCE(NULLIF(error_type, ''), 'spelling') = ?
),
ranked AS (
    SELECT word,
           chinese_meaning,
           category,
           user_input,
           attempt_time,
           -- 每个单词的错误次数用于列表排序和前端展示。
           COUNT(*) OVER (PARTITION BY word) AS error_count,
           -- 每个单词只取最近一次错误输入，避免 MAX(user_input) 这类字符串聚合带来误导。
           ROW_NUMBER() OVER (PARTITION BY word ORDER BY attempt_time DESC, id DESC) AS row_number
    FROM filtered
)
SELECT word,
       COALESCE(chinese_meaning, '') AS chinese_meaning,
       COALESCE(category, '') AS category,
       COALESCE(user_input, '') AS user_input,
       error_count,
       COALESCE(attempt_time, '') AS last_attempt_at
FROM ranked
WHERE row_number = 1
ORDER BY error_count DESC, last_attempt_at DESC, word ASC
LIMIT ?`, errorType, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []ErrorTypeWordDetail
	for rows.Next() {
		var item ErrorTypeWordDetail
		if err := rows.Scan(
			&item.Word,
			&item.ChineseMeaning,
			&item.Category,
			&item.UserInput,
			&item.ErrorCount,
			&item.LastAttemptAt,
		); err != nil {
			return nil, err
		}
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) Milestones() ([]Milestone, error) {
	rows, err := s.db.Query(`
SELECT milestone_type, milestone_name, COALESCE(description, ''), achieved_at, COALESCE(metadata, '')
FROM milestones
ORDER BY achieved_at ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var data []Milestone
	for rows.Next() {
		var item Milestone
		var achievedAt string
		if err := rows.Scan(&item.MilestoneType, &item.MilestoneName, &item.Description, &achievedAt, &item.Metadata); err != nil {
			return nil, err
		}
		item.AchievedAt = parseDBTime(achievedAt)
		data = append(data, item)
	}
	return data, rows.Err()
}

func (s *Store) Overview() (Overview, error) {
	// 概览卡片需要的数据来自多个表：session 聚合、连续天数、mastery 计数。
	var overview Overview
	err := s.db.QueryRow(`
SELECT COUNT(*),
       COALESCE(SUM(total_words), 0),
       COALESCE(SUM(correct_words) * 100.0 / NULLIF(SUM(total_words), 0), 0),
       COALESCE(SUM(duration_seconds), 0) / 60.0
FROM practice_sessions`).Scan(
		&overview.TotalSessions,
		&overview.TotalWordsPracticed,
		&overview.OverallAccuracy,
		&overview.TotalTimeMinutes,
	)
	if err != nil {
		return Overview{}, err
	}

	streak, err := s.Streak()
	if err != nil {
		return Overview{}, err
	}
	overview.CurrentStreak = streak.CurrentStreak

	if err := s.db.QueryRow(`SELECT COUNT(*) FROM word_mastery WHERE mastery_level = 'mastered'`).Scan(&overview.MasteredWords); err != nil {
		return Overview{}, err
	}
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM word_mastery WHERE mastery_level = 'weak'`).Scan(&overview.WeakWords); err != nil {
		return Overview{}, err
	}

	return overview, nil
}

func (s *Store) CheckAndCreateMilestones(session SessionRequest) error {
	// 里程碑使用 INSERT OR IGNORE，因此同一类型只会记录第一次达成。
	var sessionCount int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM practice_sessions`).Scan(&sessionCount); err != nil {
		return err
	}
	if sessionCount == 1 {
		if err := s.createMilestone("first_practice", "首次练习", "开始你的学习之旅", ""); err != nil {
			return err
		}
	}

	var distinctWords int
	if err := s.db.QueryRow(`SELECT COUNT(DISTINCT word) FROM word_attempts`).Scan(&distinctWords); err != nil {
		return err
	}
	if distinctWords >= 100 {
		if err := s.createMilestone("word_count_100", "百词斩", "累计练习 100 个单词", fmt.Sprintf(`{"word_count":%d}`, distinctWords)); err != nil {
			return err
		}
	}

	if session.Accuracy >= 90 {
		if err := s.createMilestone("accuracy_90", "正确率达人", "首次正确率达到 90%", fmt.Sprintf(`{"accuracy":%.2f}`, session.Accuracy)); err != nil {
			return err
		}
	}

	streak, err := s.Streak()
	if err != nil {
		return err
	}
	if streak.CurrentStreak >= 7 {
		if err := s.createMilestone("streak_7", "坚持不懈", "连续学习 7 天", fmt.Sprintf(`{"streak":%d}`, streak.CurrentStreak)); err != nil {
			return err
		}
	}

	var totalAttempts int
	if err := s.db.QueryRow(`SELECT COUNT(*) FROM word_attempts`).Scan(&totalAttempts); err != nil {
		return err
	}
	if totalAttempts >= 1000 {
		if err := s.createMilestone("total_1000", "千次练习", "累计完成 1000 次单词练习", fmt.Sprintf(`{"attempts":%d}`, totalAttempts)); err != nil {
			return err
		}
	}

	return nil
}

func (s *Store) createMilestone(milestoneType, name, description, metadata string) error {
	_, err := s.db.Exec(`
INSERT OR IGNORE INTO milestones (
    milestone_type, milestone_name, description, achieved_at, metadata
) VALUES (?, ?, ?, ?, ?)`,
		milestoneType,
		name,
		description,
		formatTime(time.Now()),
		metadata,
	)
	return err
}

func (s *Store) practiceDates() ([]string, error) {
	rows, err := s.db.Query(`
SELECT DISTINCT date(start_time)
FROM practice_sessions
ORDER BY date(start_time) ASC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var dates []string
	for rows.Next() {
		var date string
		if err := rows.Scan(&date); err != nil {
			return nil, err
		}
		dates = append(dates, date)
	}
	return dates, rows.Err()
}

func sinceDate(days int) string {
	if days <= 0 {
		days = 30
	}
	return time.Now().UTC().AddDate(0, 0, -days+1).Format("2006-01-02")
}

func calculateStreaks(dateStrings []string, now time.Time) (int, int) {
	// dateStrings 已按日期升序排列。longest 从头扫描，current 从最后一天反向扫描。
	if len(dateStrings) == 0 {
		return 0, 0
	}

	dates := make([]time.Time, 0, len(dateStrings))
	for _, value := range dateStrings {
		parsed, err := time.Parse("2006-01-02", value)
		if err == nil {
			dates = append(dates, parsed)
		}
	}
	if len(dates) == 0 {
		return 0, 0
	}

	longest := 1
	run := 1
	for i := 1; i < len(dates); i++ {
		diff := int(dates[i].Sub(dates[i-1]).Hours() / 24)
		if diff == 1 {
			run++
		} else if diff > 1 {
			run = 1
		}
		if run > longest {
			longest = run
		}
	}

	current := 0
	today, _ := time.Parse("2006-01-02", now.Format("2006-01-02"))
	last := dates[len(dates)-1]
	lag := int(today.Sub(last).Hours() / 24)
	if lag == 0 || lag == 1 {
		current = 1
		for i := len(dates) - 2; i >= 0; i-- {
			diff := int(last.Sub(dates[i]).Hours() / 24)
			if diff == 1 {
				current++
				last = dates[i]
				continue
			}
			if diff > 1 {
				break
			}
		}
	}

	return current, longest
}

func parseDBTime(value string) time.Time {
	for _, layout := range []string{time.RFC3339, "2006-01-02 15:04:05"} {
		parsed, err := time.Parse(layout, value)
		if err == nil {
			return parsed
		}
	}
	return time.Time{}
}
