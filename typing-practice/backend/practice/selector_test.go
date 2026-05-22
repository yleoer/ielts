package practice

import (
	"math/rand"
	"testing"
	"time"

	"typing-practice/models"
	"typing-practice/stats"
)

func TestSelectWordsUsesBucketsAndFillsLimit(t *testing.T) {
	now := time.Date(2026, 5, 22, 12, 0, 0, 0, time.UTC)
	candidates := []models.Word{
		{ID: 1, Word: "weak"},
		{ID: 2, Word: "learning"},
		{ID: 3, Word: "review"},
		{ID: 4, Word: "fresh"},
		{ID: 5, Word: "extra"},
	}
	statsByWord := map[string]stats.SelectionStats{
		"weak": {
			Word:               "weak",
			TotalAttempts:      4,
			CorrectAttempts:    1,
			IncorrectAttempts:  3,
			MasteryLevel:       "weak",
			LastAttemptTime:    now.AddDate(0, 0, -1),
			LastAttemptCorrect: false,
		},
		"learning": {
			Word:               "learning",
			TotalAttempts:      2,
			CorrectAttempts:    2,
			MasteryLevel:       "learning",
			LastAttemptTime:    now.AddDate(0, 0, -1),
			LastAttemptCorrect: true,
		},
		"review": {
			Word:               "review",
			TotalAttempts:      8,
			CorrectAttempts:    8,
			MasteryLevel:       "mastered",
			LastAttemptTime:    now.AddDate(0, 0, -10),
			LastAttemptCorrect: true,
		},
	}

	selected := SelectWords(candidates, statsByWord, 5, now, rand.New(rand.NewSource(1)))
	if len(selected) != 5 {
		t.Fatalf("expected 5 words, got %d: %#v", len(selected), selected)
	}

	seen := map[string]bool{}
	for _, word := range selected {
		if seen[word.Word] {
			t.Fatalf("duplicate word selected: %#v", selected)
		}
		seen[word.Word] = true
	}
	for _, word := range []string{"weak", "learning", "review"} {
		if !seen[word] {
			t.Fatalf("expected %q to be selected, got %#v", word, selected)
		}
	}
}

func TestSelectWordsClampsLimitToCandidateCount(t *testing.T) {
	candidates := []models.Word{
		{ID: 1, Word: "one"},
		{ID: 2, Word: "two"},
	}

	selected := SelectWords(candidates, nil, 10, time.Time{}, rand.New(rand.NewSource(1)))
	if len(selected) != len(candidates) {
		t.Fatalf("expected %d words, got %d", len(candidates), len(selected))
	}
}
