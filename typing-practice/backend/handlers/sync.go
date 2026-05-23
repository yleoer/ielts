package handlers

import (
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"typing-practice/anki"
	"typing-practice/models"
	"typing-practice/stats"

	"github.com/gin-gonic/gin"
)

type SyncStatus struct {
	LastSyncAt     *time.Time         `json:"last_sync_at,omitempty"`
	SourcePath     string             `json:"source_path,omitempty"`
	TargetPath     string             `json:"target_path,omitempty"`
	BeforeWords    int                `json:"before_words"`
	AfterWords     int                `json:"after_words"`
	AddedWords     int                `json:"added_words"`
	AddedWordList  []models.Word      `json:"added_word_list"`
	History        []SyncHistoryEntry `json:"history"`
	CopiedFiles    []string           `json:"-"`
	Success        bool               `json:"success"`
	Message        string             `json:"message,omitempty"`
	SyncConfigured bool               `json:"sync_configured"`
}

type SyncHistoryEntry struct {
	SyncedAt      time.Time     `json:"synced_at"`
	BeforeWords   int           `json:"before_words"`
	AfterWords    int           `json:"after_words"`
	AddedWords    int           `json:"added_words"`
	AddedWordList []models.Word `json:"added_word_list"`
	Success       bool          `json:"success"`
	Message       string        `json:"message,omitempty"`
}

type syncFileStat struct {
	Path    string
	Size    int64
	ModTime time.Time
}

func (api *API) GetSyncStatus(c *gin.Context) {
	api.ReaderMu.RLock()
	status := api.Sync
	status.SyncConfigured = syncConfigured()
	status.TargetPath = syncTargetPath(api)
	if api.Reader != nil && status.AfterWords == 0 {
		if total, err := api.Reader.CountLearned(); err == nil {
			status.AfterWords = total
		}
	}
	api.ReaderMu.RUnlock()

	status.History = api.loadSyncHistory()
	c.JSON(http.StatusOK, gin.H{"success": true, "data": status})
}

func (api *API) SyncNow(c *gin.Context) {
	status, err := api.syncAnkiCollection()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error(), "data": status})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "data": status})
}

func (api *API) syncAnkiCollection() (SyncStatus, error) {
	api.ReaderMu.Lock()
	defer api.ReaderMu.Unlock()

	status := SyncStatus{
		TargetPath:     syncTargetPath(api),
		SyncConfigured: syncConfigured(),
	}
	now := time.Now()
	status.LastSyncAt = &now
	if !status.SyncConfigured {
		status.Message = "Anki sync source is not configured"
		api.Sync = status
		return status, errors.New(status.Message)
	}

	source, err := latestCollection(os.Getenv("ANKI_SYNC_SOURCE_DIR"))
	if err != nil {
		status.Message = err.Error()
		api.Sync = status
		return status, err
	}
	status.SourcePath = source

	var beforeList []models.Word
	if api.Reader != nil {
		if words, err := api.Reader.GetLearnedWordPool("all"); err == nil {
			beforeList = words
			status.BeforeWords = len(words)
		} else if total, err := api.Reader.CountLearned(); err == nil {
			status.BeforeWords = total
		}
		_ = api.Reader.Close()
		api.Reader = nil
	}

	copied, err := copyCollectionGroup(source, status.TargetPath)
	if err != nil {
		status.Message = err.Error()
		api.Sync = status
		return status, err
	}
	status.CopiedFiles = copied

	reader, err := anki.NewReader(api.Config.Anki)
	if err != nil {
		status.Message = fmt.Sprintf("copied files but failed to reopen Anki database: %v", err)
		api.Sync = status
		return status, err
	}
	api.Reader = reader

	var afterList []models.Word
	if words, err := api.Reader.GetLearnedWordPool("all"); err == nil {
		afterList = words
		status.AfterWords = len(words)
	} else if total, err := api.Reader.CountLearned(); err == nil {
		status.AfterWords = total
	}
	status.AddedWordList = findAddedWords(beforeList, afterList)
	status.AddedWords = len(status.AddedWordList)
	status.Success = true
	status.Message = "Anki collection synced"
	api.saveSyncHistory(status)
	status.History = api.loadSyncHistory()
	api.Sync = status

	log.Printf(
		"Anki sync completed at %s: added_words=%d added_word_meanings=%s before_words=%d after_words=%d source=%s target=%s files=%s",
		status.LastSyncAt.Format(time.RFC3339),
		status.AddedWords,
		strings.Join(wordMeanings(status.AddedWordList), ","),
		status.BeforeWords,
		status.AfterWords,
		status.SourcePath,
		status.TargetPath,
		strings.Join(status.CopiedFiles, ","),
	)

	return status, nil
}

func findAddedWords(before, after []models.Word) []models.Word {
	known := make(map[int64]struct{}, len(before))
	for _, word := range before {
		known[word.ID] = struct{}{}
	}

	added := make([]models.Word, 0)
	for _, word := range after {
		if _, ok := known[word.ID]; ok {
			continue
		}
		added = append(added, word)
	}
	return added
}

func wordMeanings(words []models.Word) []string {
	if len(words) == 0 {
		return []string{"-"}
	}
	names := make([]string, 0, len(words))
	for _, word := range words {
		if word.ChineseMeaning != "" {
			names = append(names, word.ChineseMeaning)
			continue
		}
		names = append(names, word.Word)
	}
	return names
}

func (api *API) saveSyncHistory(status SyncStatus) {
	if api.Stats == nil || status.AddedWords <= 0 || len(status.AddedWordList) == 0 {
		return
	}
	entry := stats.AnkiSyncHistoryEntry{
		SyncedAt:      time.Now(),
		BeforeWords:   status.BeforeWords,
		AfterWords:    status.AfterWords,
		AddedWords:    status.AddedWords,
		AddedWordList: syncWordsToStats(status.AddedWordList),
		Success:       status.Success,
		Message:       status.Message,
		SourcePath:    status.SourcePath,
		TargetPath:    status.TargetPath,
	}
	if status.LastSyncAt != nil {
		entry.SyncedAt = *status.LastSyncAt
	}
	if err := api.Stats.SaveAnkiSyncHistory(entry); err != nil {
		log.Printf("save Anki sync history: %v", err)
	}
}

func (api *API) loadSyncHistory() []SyncHistoryEntry {
	if api.Stats == nil {
		return nil
	}
	history, err := api.Stats.ListAnkiSyncHistory(50)
	if err != nil {
		log.Printf("load Anki sync history: %v", err)
		return nil
	}
	return syncHistoryFromStats(history)
}

func syncWordsToStats(words []models.Word) []stats.AnkiSyncWord {
	result := make([]stats.AnkiSyncWord, 0, len(words))
	for _, word := range words {
		result = append(result, stats.AnkiSyncWord{
			ID:             word.ID,
			Word:           word.Word,
			ChineseMeaning: word.ChineseMeaning,
			Category:       word.Category,
		})
	}
	return result
}

func syncHistoryFromStats(history []stats.AnkiSyncHistoryEntry) []SyncHistoryEntry {
	result := make([]SyncHistoryEntry, 0, len(history))
	for _, item := range history {
		result = append(result, SyncHistoryEntry{
			SyncedAt:      item.SyncedAt,
			BeforeWords:   item.BeforeWords,
			AfterWords:    item.AfterWords,
			AddedWords:    item.AddedWords,
			AddedWordList: syncWordsFromStats(item.AddedWordList),
			Success:       item.Success,
			Message:       item.Message,
		})
	}
	return result
}

func syncWordsFromStats(words []stats.AnkiSyncWord) []models.Word {
	result := make([]models.Word, 0, len(words))
	for _, word := range words {
		result = append(result, models.Word{
			ID:             word.ID,
			Word:           word.Word,
			ChineseMeaning: word.ChineseMeaning,
			Category:       word.Category,
		})
	}
	return result
}

func (api *API) StartAnkiSyncScheduler() {
	if !syncConfigured() {
		return
	}
	go func() {
		initialWait := syncInitialWaitDuration()
		if initialWait > 0 {
			time.Sleep(initialWait)
		}
		api.runScheduledSync()

		ticker := time.NewTicker(syncIntervalDuration())
		defer ticker.Stop()
		for range ticker.C {
			api.runScheduledSync()
		}
	}()
}

func (api *API) runScheduledSync() {
	status, err := api.syncAnkiCollection()
	if err != nil {
		log.Printf("Anki scheduled sync skipped: %v", err)
		return
	}
	if status.AddedWords == 0 {
		log.Printf("Anki scheduled sync completed with no new words")
	}
}

func syncConfigured() bool {
	source := strings.TrimSpace(os.Getenv("ANKI_SYNC_SOURCE_DIR"))
	target := strings.TrimSpace(os.Getenv("ANKI_SYNC_TARGET"))
	return source != "" && target != ""
}

func syncTargetPath(api *API) string {
	if target := strings.TrimSpace(os.Getenv("ANKI_SYNC_TARGET")); target != "" {
		return target
	}
	if api != nil && api.Config != nil {
		return api.Config.Anki.DBPath
	}
	return ""
}

func latestCollection(sourceDir string) (string, error) {
	sourceDir = strings.TrimSpace(sourceDir)
	if sourceDir == "" {
		return "", errors.New("ANKI_SYNC_SOURCE_DIR is not configured")
	}

	var candidates []syncFileStat
	if err := filepath.WalkDir(sourceDir, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if entry.IsDir() || entry.Name() != "collection.anki2" {
			return nil
		}
		info, err := entry.Info()
		if err != nil || info.Size() == 0 {
			return nil
		}
		candidates = append(candidates, syncFileStat{Path: path, Size: info.Size(), ModTime: info.ModTime()})
		return nil
	}); err != nil {
		return "", err
	}

	if len(candidates) == 0 {
		return "", fmt.Errorf("no collection.anki2 found under %s", sourceDir)
	}
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].ModTime.After(candidates[j].ModTime)
	})
	return candidates[0].Path, nil
}

func copyCollectionGroup(source, target string) ([]string, error) {
	if strings.TrimSpace(target) == "" {
		return nil, errors.New("ANKI_SYNC_TARGET is not configured")
	}
	if err := ensureStableCollectionGroup(source); err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return nil, err
	}

	copied := make([]string, 0, 3)
	for _, suffix := range []string{"", "-wal", "-shm"} {
		src := source + suffix
		dst := target + suffix
		if _, err := os.Stat(src); err != nil {
			if os.IsNotExist(err) && suffix != "" {
				_ = os.Remove(dst)
				continue
			}
			return copied, err
		}
		if err := copyFileAtomic(src, dst); err != nil {
			return copied, err
		}
		copied = append(copied, filepath.Base(dst))
	}
	return copied, nil
}

func ensureStableCollectionGroup(source string) error {
	first, err := collectionGroupStats(source)
	if err != nil {
		return err
	}
	time.Sleep(syncStableDuration())
	second, err := collectionGroupStats(source)
	if err != nil {
		return err
	}
	if len(first) != len(second) {
		return errors.New("Anki collection files are changing; try again later")
	}
	for index := range first {
		if first[index].Path != second[index].Path ||
			first[index].Size != second[index].Size ||
			!first[index].ModTime.Equal(second[index].ModTime) {
			return errors.New("Anki collection files are changing; try again later")
		}
	}
	return nil
}

func collectionGroupStats(source string) ([]syncFileStat, error) {
	stats := make([]syncFileStat, 0, 3)
	for _, suffix := range []string{"", "-wal", "-shm"} {
		path := source + suffix
		info, err := os.Stat(path)
		if err != nil {
			if os.IsNotExist(err) && suffix != "" {
				continue
			}
			return nil, err
		}
		stats = append(stats, syncFileStat{Path: path, Size: info.Size(), ModTime: info.ModTime()})
	}
	return stats, nil
}

func syncStableDuration() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ANKI_SYNC_STABLE_SECONDS"))
	if raw == "" {
		return 2 * time.Second
	}
	parsed, err := time.ParseDuration(raw + "s")
	if err != nil || parsed < 0 {
		return 2 * time.Second
	}
	return parsed
}

func syncIntervalDuration() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ANKI_SYNC_INTERVAL_SECONDS"))
	if raw == "" {
		return 300 * time.Second
	}
	seconds, err := time.ParseDuration(raw + "s")
	if err != nil || seconds <= 0 {
		return 300 * time.Second
	}
	return seconds
}

func syncInitialWaitDuration() time.Duration {
	raw := strings.TrimSpace(os.Getenv("ANKI_SYNC_INITIAL_WAIT_SECONDS"))
	if raw == "" {
		return 60 * time.Second
	}
	seconds, err := time.ParseDuration(raw + "s")
	if err != nil || seconds < 0 {
		return 60 * time.Second
	}
	return seconds
}

func copyFileAtomic(source, target string) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()

	tmp := target + ".tmp"
	output, err := os.Create(tmp)
	if err != nil {
		return err
	}
	if _, err := io.Copy(output, input); err != nil {
		_ = output.Close()
		_ = os.Remove(tmp)
		return err
	}
	if err := output.Close(); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return os.Rename(tmp, target)
}
