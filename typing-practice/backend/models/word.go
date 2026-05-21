package models

type Word struct {
	ID             int64  `json:"id"`
	Word           string `json:"word"`
	Phonetic       string `json:"phonetic"`
	PartOfSpeech   string `json:"part_of_speech"`
	ChineseMeaning string `json:"chinese_meaning"`
	ExampleEN      string `json:"example_en,omitempty"`
	ExampleCN      string `json:"example_cn,omitempty"`
	Category       string `json:"category,omitempty"`
}

type CheckRequest struct {
	WordID    int64  `json:"word_id" binding:"required"`
	UserInput string `json:"user_input" binding:"required"`
}

type CheckResponse struct {
	Success   bool   `json:"success"`
	Correct   bool   `json:"correct"`
	Expected  string `json:"expected"`
	UserInput string `json:"user_input"`
}

type ErrorRecord struct {
	Word      string `json:"word"`
	Meaning   string `json:"meaning,omitempty"`
	UserInput string `json:"user_input"`
}

type StatsRequest struct {
	SessionID       string        `json:"session_id" binding:"required"`
	Total           int           `json:"total"`
	Correct         int           `json:"correct"`
	DurationSeconds int           `json:"duration_seconds"`
	Errors          []ErrorRecord `json:"errors"`
}
