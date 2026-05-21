package stats

import "time"

type SessionRequest struct {
	// SessionID 由前端生成，同一个 ID 重复提交会被视为同一次练习的覆盖更新。
	SessionID string     `json:"session_id" binding:"required"`
	UserID    string     `json:"user_id,omitempty"`
	StartTime time.Time  `json:"start_time" binding:"required"`
	EndTime   *time.Time `json:"end_time,omitempty"`
	// TotalWords/CorrectWords/IncorrectWords 是会话级汇总，图表概览直接依赖它们。
	TotalWords      int     `json:"total_words" binding:"required"`
	CorrectWords    int     `json:"correct_words"`
	IncorrectWords  int     `json:"incorrect_words"`
	Accuracy        float64 `json:"accuracy"`
	DurationSeconds int     `json:"duration_seconds"`
	// WordAttempts 是单词级明细，用于错误排行、分类雷达、打字速度和 mastery。
	WordAttempts []AttemptRequest `json:"word_attempts"`
}

type AttemptRequest struct {
	// Word 必须是期望答案；错误类型分析会拿它和 UserInput 比较。
	Word           string `json:"word" binding:"required"`
	ChineseMeaning string `json:"chinese_meaning,omitempty"`
	Category       string `json:"category,omitempty"`
	UserInput      string `json:"user_input"`
	IsCorrect      bool   `json:"is_correct"`
	// TimeSpent 为单词输入耗时，前端暂时没有也可以为空。
	TimeSpent *float64 `json:"time_spent,omitempty"`
	// ErrorType 可由前端传入；为空时后端会自动分析。
	ErrorType *string `json:"error_type,omitempty"`
}

// WordMastery 是 word_mastery 表的内存表示，主要用于计算掌握等级。
type WordMastery struct {
	Word              string
	TotalAttempts     int
	CorrectAttempts   int
	IncorrectAttempts int
	MasteryLevel      string
	AverageTime       float64
}

type HeatmapPoint struct {
	Date     string  `json:"date"`
	Count    int     `json:"count"`
	Accuracy float64 `json:"accuracy"`
}

type AccuracyTrendPoint struct {
	Date       string  `json:"date"`
	Accuracy   float64 `json:"accuracy"`
	TotalWords int     `json:"total_words"`
}

type TopErrorWord struct {
	Word           string `json:"word"`
	ErrorCount     int    `json:"error_count"`
	TotalAttempts  int    `json:"total_attempts"`
	ChineseMeaning string `json:"chinese_meaning"`
}

type MasteryWordDetail struct {
	Word              string  `json:"word"`
	TotalAttempts     int     `json:"total_attempts"`
	CorrectAttempts   int     `json:"correct_attempts"`
	IncorrectAttempts int     `json:"incorrect_attempts"`
	Accuracy          float64 `json:"accuracy"`
	AverageTime       float64 `json:"average_time"`
}

type ErrorTypeWordDetail struct {
	Word           string `json:"word"`
	ChineseMeaning string `json:"chinese_meaning"`
	Category       string `json:"category"`
	UserInput      string `json:"user_input"`
	ErrorCount     int    `json:"error_count"`
	LastAttemptAt  string `json:"last_attempt_at"`
}

type SpeedTrendPoint struct {
	Date        string  `json:"date"`
	AverageTime float64 `json:"average_time"`
	WordCount   int     `json:"word_count"`
}

type DailyDurationPoint struct {
	Date            string  `json:"date"`
	DurationMinutes float64 `json:"duration_minutes"`
	SessionCount    int     `json:"session_count"`
}

type CategoryMasteryPoint struct {
	Category  string  `json:"category"`
	Accuracy  float64 `json:"accuracy"`
	WordCount int     `json:"word_count"`
}

type StreakData struct {
	CurrentStreak int      `json:"current_streak"`
	LongestStreak int      `json:"longest_streak"`
	TotalDays     int      `json:"total_days"`
	PracticeDates []string `json:"practice_dates"`
}

type Milestone struct {
	MilestoneType string    `json:"milestone_type"`
	MilestoneName string    `json:"milestone_name"`
	Description   string    `json:"description"`
	AchievedAt    time.Time `json:"achieved_at"`
	Metadata      string    `json:"metadata,omitempty"`
}

type Overview struct {
	TotalSessions       int     `json:"total_sessions"`
	TotalWordsPracticed int     `json:"total_words_practiced"`
	OverallAccuracy     float64 `json:"overall_accuracy"`
	TotalTimeMinutes    float64 `json:"total_time_minutes"`
	CurrentStreak       int     `json:"current_streak"`
	MasteredWords       int     `json:"mastered_words"`
	WeakWords           int     `json:"weak_words"`
}
