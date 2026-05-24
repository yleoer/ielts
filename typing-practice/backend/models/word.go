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
