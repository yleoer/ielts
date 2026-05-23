package handlers

import (
	"testing"

	"typing-practice/models"
	"typing-practice/stats"
)

func TestMergeUnpracticedWordsCountsNewWords(t *testing.T) {
	distribution := map[string]int{
		"mastered": 1,
		"familiar": 0,
		"learning": 1,
		"weak":     0,
		"new":      0,
	}
	words := []models.Word{
		{Word: "Alpha", ChineseMeaning: "alpha meaning"},
		{Word: "bravo", ChineseMeaning: "bravo meaning"},
		{Word: "charlie", ChineseMeaning: "charlie meaning"},
	}
	selectionStats := map[string]stats.SelectionStats{
		"alpha": {Word: "alpha"},
	}

	got := mergeUnpracticedWords(distribution, words, selectionStats)
	if got["new"] != 2 {
		t.Fatalf("expected 2 new words, got %#v", got)
	}
	if got["mastered"] != 1 || got["learning"] != 1 {
		t.Fatalf("expected existing distribution to be preserved, got %#v", got)
	}
}

func TestUnpracticedWordDetails(t *testing.T) {
	words := []models.Word{
		{Word: "alpha", ChineseMeaning: "alpha meaning"},
		{Word: "bravo", ChineseMeaning: "bravo meaning"},
		{Word: "bravo", ChineseMeaning: "duplicate"},
		{Word: "charlie", ChineseMeaning: "charlie meaning"},
	}
	selectionStats := map[string]stats.SelectionStats{
		"alpha": {Word: "alpha"},
	}

	got := unpracticedWordDetails(words, selectionStats, 1)
	if len(got) != 1 || got[0].Word != "bravo" || got[0].ChineseMeaning != "bravo meaning" {
		t.Fatalf("unexpected unpracticed details: %#v", got)
	}
}
