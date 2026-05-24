package anki

import (
	"database/sql"
	"path/filepath"
	"strings"
	"testing"

	"typing-practice/config"

	_ "github.com/mattn/go-sqlite3"
)

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

func TestReaderIncludesChildDecks(t *testing.T) {
	dbPath := filepath.Join(t.TempDir(), "collection.anki2")
	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	statements := []string{
		`CREATE TABLE decks (id INTEGER PRIMARY KEY, name TEXT)`,
		`CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT)`,
		`CREATE TABLE cards (nid INTEGER, did INTEGER, type INTEGER, queue INTEGER)`,
		`INSERT INTO decks (id, name) VALUES (1, 'IELTS Vocabulary')`,
		`INSERT INTO decks (id, name) VALUES (2, 'IELTS Vocabulary::Review')`,
		`INSERT INTO decks (id, name) VALUES (3, 'Other')`,
		`INSERT INTO cards (nid, did, type, queue) VALUES (101, 1, 1, 2)`,
		`INSERT INTO cards (nid, did, type, queue) VALUES (102, 2, 1, 2)`,
		`INSERT INTO cards (nid, did, type, queue) VALUES (103, 3, 1, 2)`,
	}
	for _, statement := range statements {
		if _, err := db.Exec(statement); err != nil {
			if strings.Contains(err.Error(), "CGO_ENABLED=0") {
				t.Skip("sqlite integration test requires CGO")
			}
			t.Fatalf("exec %q: %v", statement, err)
		}
	}
	for id, fields := range map[int]string{
		101: "alpha\x1f/a/\x1fn.\x1fmeaning alpha",
		102: "bravo\x1f/b/\x1fn.\x1fmeaning bravo",
		103: "charlie\x1f/c/\x1fn.\x1fmeaning charlie",
	} {
		if _, err := db.Exec(`INSERT INTO notes (id, flds) VALUES (?, ?)`, id, fields); err != nil {
			t.Fatal(err)
		}
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	reader, err := NewReader(config.AnkiConfig{
		DBPath:   dbPath,
		DeckName: "IELTS Vocabulary",
	})
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()

	total, err := reader.CountLearned()
	if err != nil {
		t.Fatal(err)
	}
	if total != 2 {
		t.Fatalf("expected parent and child deck words, got %d", total)
	}

	words, err := reader.GetLearnedWordPool("all")
	if err != nil {
		t.Fatal(err)
	}
	if len(words) != 2 || words[0].Word != "alpha" || words[1].Word != "bravo" {
		t.Fatalf("unexpected words: %#v", words)
	}
}
