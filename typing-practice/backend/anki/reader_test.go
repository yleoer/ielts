package anki

import "testing"

func TestParseWord(t *testing.T) {
	raw := "atmosphere\x1f/phonetic/\x1fn.\x1f大气层；氛围\x1fThe <b>atmosphere</b> changed\x1f气氛变了\x1f[sound:a.mp3]\x1f自然地理"
	word, ok := ParseWord(123, raw)
	if !ok {
		t.Fatal("expected word to parse")
	}
	if word.ID != 123 || word.Word != "atmosphere" || word.ChineseMeaning != "大气层；氛围" || word.Category != "自然地理" {
		t.Fatalf("unexpected word: %#v", word)
	}
	if word.ExampleEN != "The atmosphere changed" {
		t.Fatalf("unexpected example: %q", word.ExampleEN)
	}
}

func TestParseWordRejectsMissingFields(t *testing.T) {
	if _, ok := ParseWord(1, "only\x1ftwo"); ok {
		t.Fatal("expected parse failure")
	}
}
