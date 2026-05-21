package utils

import "testing"

func TestCheckSpelling(t *testing.T) {
	tests := []struct {
		name     string
		expected string
		input    string
		want     bool
	}{
		{name: "exact", expected: "atmosphere", input: "atmosphere", want: true},
		{name: "case and spaces", expected: "Atmosphere", input: " atmosphere ", want: true},
		{name: "wrong", expected: "catastrophic", input: "catastrofic", want: false},
		{name: "variant", expected: "analyse / analyze", input: "analyze", want: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := CheckSpelling(tt.expected, tt.input); got != tt.want {
				t.Fatalf("CheckSpelling() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestClampLimit(t *testing.T) {
	if got := ClampLimit(0, 20, 100); got != 20 {
		t.Fatalf("got %d, want 20", got)
	}
	if got := ClampLimit(120, 20, 100); got != 100 {
		t.Fatalf("got %d, want 100", got)
	}
	if got := ClampLimit(30, 20, 100); got != 30 {
		t.Fatalf("got %d, want 30", got)
	}
}
