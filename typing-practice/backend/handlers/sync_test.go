package handlers

import (
	"os"
	"path/filepath"
	"testing"

	"typing-practice/models"
)

func TestCopyCollectionGroupCopiesSidecars(t *testing.T) {
	t.Setenv("ANKI_SYNC_STABLE_SECONDS", "0")
	dir := t.TempDir()
	source := filepath.Join(dir, "source", "collection.anki2")
	target := filepath.Join(dir, "target", "collection.anki2")
	if err := os.MkdirAll(filepath.Dir(source), 0o755); err != nil {
		t.Fatal(err)
	}

	files := map[string]string{
		source:          "main",
		source + "-wal": "wal",
		source + "-shm": "shm",
	}
	for path, content := range files {
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	copied, err := copyCollectionGroup(source, target)
	if err != nil {
		t.Fatalf("copyCollectionGroup() error = %v", err)
	}
	if len(copied) != 3 {
		t.Fatalf("expected 3 copied files, got %v", copied)
	}
	for path, content := range map[string]string{
		target:          "main",
		target + "-wal": "wal",
		target + "-shm": "shm",
	} {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if string(data) != content {
			t.Fatalf("unexpected content for %s: %q", path, string(data))
		}
	}
}

func TestCopyCollectionGroupRemovesStaleSidecars(t *testing.T) {
	t.Setenv("ANKI_SYNC_STABLE_SECONDS", "0")
	dir := t.TempDir()
	source := filepath.Join(dir, "source", "collection.anki2")
	target := filepath.Join(dir, "target", "collection.anki2")
	if err := os.MkdirAll(filepath.Dir(source), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(source, []byte("main"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target+"-wal", []byte("old wal"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target+"-shm", []byte("old shm"), 0o644); err != nil {
		t.Fatal(err)
	}

	copied, err := copyCollectionGroup(source, target)
	if err != nil {
		t.Fatalf("copyCollectionGroup() error = %v", err)
	}
	if len(copied) != 1 || copied[0] != "collection.anki2" {
		t.Fatalf("expected only main file copied, got %v", copied)
	}
	for _, path := range []string{target + "-wal", target + "-shm"} {
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("expected stale sidecar removed: %s", path)
		}
	}
}

func TestFindAddedWords(t *testing.T) {
	before := []models.Word{
		{ID: 1, Word: "alpha"},
	}
	after := []models.Word{
		{ID: 1, Word: "alpha"},
		{ID: 2, Word: "bravo"},
	}

	added := findAddedWords(before, after)
	if len(added) != 1 || added[0].Word != "bravo" {
		t.Fatalf("unexpected added words: %#v", added)
	}
}
