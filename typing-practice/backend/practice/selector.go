package practice

import (
	"math"
	"math/rand"
	"strings"
	"time"

	"typing-practice/models"
	"typing-practice/stats"
)

type weightedWord struct {
	word   models.Word
	score  float64
	bucket string
}

func SelectWords(candidates []models.Word, statsByWord map[string]stats.SelectionStats, limit int, now time.Time, rng *rand.Rand) []models.Word {
	if limit <= 0 || len(candidates) == 0 {
		return nil
	}
	if limit > len(candidates) {
		limit = len(candidates)
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	if rng == nil {
		rng = rand.New(rand.NewSource(time.Now().UnixNano()))
	}

	lookup := normalizeStats(statsByWord)
	weighted := make([]weightedWord, 0, len(candidates))
	for _, word := range candidates {
		itemStats, ok := lookup[normalizeWord(word.Word)]
		score := scoreWord(itemStats, ok, now)
		weighted = append(weighted, weightedWord{
			word:   word,
			score:  score,
			bucket: bucketFor(itemStats, ok, now),
		})
	}

	quotas := bucketQuotas(limit)
	selected := make([]models.Word, 0, limit)
	selectedIDs := make(map[int64]bool)

	for _, bucket := range []string{"weak", "learning", "review", "random"} {
		selected = append(selected, takeFromBucket(weighted, bucket, quotas[bucket], selectedIDs, rng)...)
	}
	if len(selected) < limit {
		selected = append(selected, takeFromBucket(weighted, "", limit-len(selected), selectedIDs, rng)...)
	}

	return selected
}

func normalizeStats(input map[string]stats.SelectionStats) map[string]stats.SelectionStats {
	output := make(map[string]stats.SelectionStats, len(input))
	for word, item := range input {
		key := normalizeWord(word)
		if key == "" {
			key = normalizeWord(item.Word)
		}
		if key != "" {
			output[key] = item
		}
	}
	return output
}

func bucketQuotas(limit int) map[string]int {
	weak := roundedPercent(limit, 40)
	learning := roundedPercent(limit, 25)
	review := roundedPercent(limit, 20)
	randomQuota := limit - weak - learning - review
	if randomQuota < 0 {
		randomQuota = 0
	}
	return map[string]int{
		"weak":     weak,
		"learning": learning,
		"review":   review,
		"random":   randomQuota,
	}
}

func roundedPercent(total, percent int) int {
	return (total*percent + 50) / 100
}

func takeFromBucket(words []weightedWord, bucket string, count int, selectedIDs map[int64]bool, rng *rand.Rand) []models.Word {
	if count <= 0 {
		return nil
	}

	pool := make([]weightedWord, 0, len(words))
	for _, item := range words {
		if selectedIDs[item.word.ID] {
			continue
		}
		if bucket != "" && item.bucket != bucket {
			continue
		}
		pool = append(pool, item)
	}

	selected := make([]models.Word, 0, count)
	for len(selected) < count && len(pool) > 0 {
		index := weightedIndex(pool, rng)
		item := pool[index]
		selected = append(selected, item.word)
		selectedIDs[item.word.ID] = true
		pool = append(pool[:index], pool[index+1:]...)
	}
	return selected
}

func weightedIndex(pool []weightedWord, rng *rand.Rand) int {
	total := 0.0
	for _, item := range pool {
		if item.score > 0 {
			total += item.score
		}
	}
	if total <= 0 {
		return rng.Intn(len(pool))
	}

	needle := rng.Float64() * total
	for i, item := range pool {
		if item.score <= 0 {
			continue
		}
		needle -= item.score
		if needle <= 0 {
			return i
		}
	}
	return len(pool) - 1
}

func bucketFor(item stats.SelectionStats, ok bool, now time.Time) string {
	if !ok || item.TotalAttempts == 0 {
		return "random"
	}

	level := strings.ToLower(strings.TrimSpace(item.MasteryLevel))
	due := daysSince(item.LastAttemptTime, now) >= 7
	if !item.LastAttemptCorrect || level == "weak" || item.IncorrectAttempts > item.CorrectAttempts {
		return "weak"
	}
	if due && (level == "mastered" || level == "familiar") {
		return "review"
	}
	if level == "learning" || level == "familiar" {
		return "learning"
	}
	return "random"
}

func scoreWord(item stats.SelectionStats, ok bool, now time.Time) float64 {
	if !ok || item.TotalAttempts == 0 {
		return baseScore("new")
	}

	score := baseScore(item.MasteryLevel)
	score += float64(item.IncorrectAttempts * 8)
	score -= float64(item.CorrectAttempts * 2)

	if !item.LastAttemptCorrect {
		score += 25
	}

	switch days := daysSince(item.LastAttemptTime, now); {
	case days >= 14:
		score += 35
	case days >= 7:
		score += 25
	case days >= 3:
		score += 10
	}

	switch {
	case item.AverageTime > 8:
		score += 15
	case item.AverageTime > 5:
		score += 10
	case item.AverageTime > 3:
		score += 5
	}

	return math.Max(score, 1)
}

func baseScore(level string) float64 {
	switch strings.ToLower(strings.TrimSpace(level)) {
	case "weak":
		return 80
	case "learning":
		return 45
	case "familiar":
		return 20
	case "mastered":
		return 5
	case "new", "":
		return 30
	default:
		return 30
	}
}

func daysSince(lastAttempt time.Time, now time.Time) int {
	if lastAttempt.IsZero() {
		return 0
	}
	if now.Before(lastAttempt) {
		return 0
	}
	return int(now.Sub(lastAttempt).Hours() / 24)
}

func normalizeWord(word string) string {
	return strings.ToLower(strings.TrimSpace(word))
}
