package stats

import (
	"path/filepath"
	"testing"
	"time"
)

func TestStoreSaveSessionAndOverview(t *testing.T) {
	store, err := Open(filepath.Join(t.TempDir(), "stats.db"))
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()

	duration := 3.2
	endTime := time.Date(2026, 5, 21, 10, 5, 0, 0, time.UTC)
	session := SessionRequest{
		SessionID:       "test-session",
		StartTime:       time.Date(2026, 5, 21, 10, 0, 0, 0, time.UTC),
		EndTime:         &endTime,
		TotalWords:      2,
		CorrectWords:    1,
		IncorrectWords:  1,
		Accuracy:        50,
		DurationSeconds: 300,
		WordAttempts: []AttemptRequest{
			{
				Word:           "atmosphere",
				ChineseMeaning: "大气层；氛围",
				Category:       "自然地理",
				UserInput:      "atmosphere",
				IsCorrect:      true,
				TimeSpent:      &duration,
			},
			{
				Word:           "catastrophic",
				ChineseMeaning: "灾难性的",
				Category:       "自然地理",
				UserInput:      "catastrofic",
				IsCorrect:      false,
				TimeSpent:      &duration,
			},
		},
	}

	if err := store.SaveSession(session); err != nil {
		t.Fatalf("SaveSession() error = %v", err)
	}
	if err := store.SaveSession(session); err != nil {
		t.Fatalf("duplicate SaveSession() error = %v", err)
	}

	overview, err := store.Overview()
	if err != nil {
		t.Fatalf("Overview() error = %v", err)
	}
	if overview.TotalSessions != 1 || overview.TotalWordsPracticed != 2 || overview.OverallAccuracy != 50 {
		t.Fatalf("unexpected overview: %#v", overview)
	}

	distribution, err := store.MasteryDistribution()
	if err != nil {
		t.Fatalf("MasteryDistribution() error = %v", err)
	}
	if distribution["learning"] != 1 || distribution["weak"] != 1 {
		t.Fatalf("unexpected distribution: %#v", distribution)
	}

	milestones, err := store.Milestones()
	if err != nil {
		t.Fatalf("Milestones() error = %v", err)
	}
	if len(milestones) != 1 || milestones[0].MilestoneType != "first_practice" {
		t.Fatalf("unexpected milestones: %#v", milestones)
	}
}

func TestStoreWordDetailQueries(t *testing.T) {
	store, err := Open(filepath.Join(t.TempDir(), "stats.db"))
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()

	firstEndTime := time.Date(2026, 5, 21, 10, 5, 0, 0, time.UTC)
	firstSession := SessionRequest{
		SessionID:       "detail-session-1",
		StartTime:       time.Date(2026, 5, 21, 10, 0, 0, 0, time.UTC),
		EndTime:         &firstEndTime,
		TotalWords:      2,
		CorrectWords:    1,
		IncorrectWords:  1,
		Accuracy:        50,
		DurationSeconds: 300,
		WordAttempts: []AttemptRequest{
			{Word: "atmosphere", ChineseMeaning: "大气层；氛围", UserInput: "atmosphere", IsCorrect: true},
			{Word: "catastrophic", ChineseMeaning: "灾难性的", UserInput: "catastrofic", IsCorrect: false},
		},
	}

	secondEndTime := time.Date(2026, 5, 22, 10, 5, 0, 0, time.UTC)
	secondSession := SessionRequest{
		SessionID:       "detail-session-2",
		StartTime:       time.Date(2026, 5, 22, 10, 0, 0, 0, time.UTC),
		EndTime:         &secondEndTime,
		TotalWords:      2,
		CorrectWords:    1,
		IncorrectWords:  1,
		Accuracy:        50,
		DurationSeconds: 300,
		WordAttempts: []AttemptRequest{
			{Word: "atmosphere", ChineseMeaning: "大气层；氛围", UserInput: "atmosphire", IsCorrect: false},
			{Word: "evidence", ChineseMeaning: "证据", UserInput: "evidence", IsCorrect: true},
		},
	}

	if err := store.SaveSession(firstSession); err != nil {
		t.Fatalf("SaveSession(first) error = %v", err)
	}
	if err := store.SaveSession(secondSession); err != nil {
		t.Fatalf("SaveSession(second) error = %v", err)
	}

	masteryWords, err := store.MasteryWords("weak", 10)
	if err != nil {
		t.Fatalf("MasteryWords() error = %v", err)
	}
	if len(masteryWords) == 0 {
		t.Fatal("expected weak mastery words")
	}
	if masteryWords[0].ChineseMeaning == "" {
		t.Fatalf("expected mastery word Chinese meaning, got %#v", masteryWords[0])
	}

	errorWords, err := store.ErrorTypeWords("spelling", 10)
	if err != nil {
		t.Fatalf("ErrorTypeWords() error = %v", err)
	}
	if len(errorWords) == 0 {
		t.Fatal("expected spelling error words")
	}
	if errorWords[0].Word != "atmosphere" || errorWords[0].UserInput != "atmosphire" || errorWords[0].ErrorCount != 1 {
		t.Fatalf("unexpected latest error detail: %#v", errorWords[0])
	}

	selectionStats, err := store.SelectionStatsByWord()
	if err != nil {
		t.Fatalf("SelectionStatsByWord() error = %v", err)
	}
	atmosphere := selectionStats["atmosphere"]
	if atmosphere.Word != "atmosphere" || atmosphere.TotalAttempts != 2 || atmosphere.LastAttemptCorrect {
		t.Fatalf("unexpected selection stats: %#v", atmosphere)
	}
}
