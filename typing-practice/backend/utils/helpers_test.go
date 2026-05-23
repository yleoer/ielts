package utils

import "testing"

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
