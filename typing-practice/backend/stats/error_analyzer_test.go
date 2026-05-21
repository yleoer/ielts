package stats

import "testing"

func TestAnalyzeErrorType(t *testing.T) {
	tests := []struct {
		name     string
		expected string
		input    string
		want     string
	}{
		{name: "correct", expected: "atmosphere", input: "atmosphere", want: ""},
		{name: "skipped", expected: "atmosphere", input: "", want: "skipped"},
		{name: "missing letter", expected: "atmosphere", input: "atmospher", want: "missing_letter"},
		{name: "extra letter", expected: "atmosphere", input: "atmospheree", want: "extra_letter"},
		{name: "spelling", expected: "catastrophic", input: "catastrofic", want: "spelling"},
		{name: "wrong", expected: "phenomenon", input: "banana", want: "completely_wrong"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := AnalyzeErrorType(tt.expected, tt.input); got != tt.want {
				t.Fatalf("got %q, want %q", got, tt.want)
			}
		})
	}
}

func TestCalculateMasteryLevel(t *testing.T) {
	tests := []struct {
		name    string
		mastery WordMastery
		want    string
	}{
		{name: "new", mastery: WordMastery{}, want: "new"},
		{name: "weak", mastery: WordMastery{TotalAttempts: 5, CorrectAttempts: 2, IncorrectAttempts: 3}, want: "weak"},
		{name: "learning", mastery: WordMastery{TotalAttempts: 1, CorrectAttempts: 1}, want: "learning"},
		{name: "familiar", mastery: WordMastery{TotalAttempts: 4, CorrectAttempts: 3, IncorrectAttempts: 1}, want: "familiar"},
		{name: "mastered", mastery: WordMastery{TotalAttempts: 7, CorrectAttempts: 6, IncorrectAttempts: 1}, want: "mastered"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := CalculateMasteryLevel(tt.mastery); got != tt.want {
				t.Fatalf("got %q, want %q", got, tt.want)
			}
		})
	}
}
