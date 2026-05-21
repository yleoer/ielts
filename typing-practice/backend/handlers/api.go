package handlers

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"typing-practice/anki"
	"typing-practice/config"
	"typing-practice/models"
	"typing-practice/utils"

	"github.com/gin-gonic/gin"
)

type API struct {
	Config *config.Config
	Reader *anki.Reader
}

func RegisterRoutes(router *gin.Engine, api *API) {
	router.GET("/api/health", api.Health)
	router.GET("/api/words", api.GetWords)
	router.POST("/api/check", api.CheckSpelling)
	router.POST("/api/stats", api.SubmitStats)
	router.GET("/api/config", api.GetConfig)
}

func (api *API) Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"status":  "ok",
	})
}

func (api *API) GetWords(c *gin.Context) {
	if api.Reader == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"success": false,
			"error":   "Anki database is not available",
		})
		return
	}

	limit := api.Config.Practice.DefaultLimit
	if raw := c.Query("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": "limit must be a number"})
			return
		}
		limit = parsed
	}
	limit = utils.ClampLimit(limit, api.Config.Practice.DefaultLimit, api.Config.Practice.MaxLimit)

	category := c.DefaultQuery("category", "all")
	words, err := api.Reader.GetLearnedWords(limit, category)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"data":    words,
		"total":   len(words),
	})
}

func (api *API) CheckSpelling(c *gin.Context) {
	if api.Reader == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"success": false,
			"error":   "Anki database is not available",
		})
		return
	}

	var request models.CheckRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error()})
		return
	}

	word, err := api.Reader.GetWordByID(request.WordID)
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, sql.ErrNoRows) || errors.Is(err, os.ErrNotExist) {
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"success": false, "error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, models.CheckResponse{
		Success:   true,
		Correct:   utils.CheckSpelling(word.Word, request.UserInput),
		Expected:  word.Word,
		UserInput: request.UserInput,
	})
}

func (api *API) SubmitStats(c *gin.Context) {
	var request models.StatsRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error()})
		return
	}

	if err := appendStats(request); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "Statistics saved",
	})
}

func (api *API) GetConfig(c *gin.Context) {
	totalLearned := 0
	ankiAvailable := api.Reader != nil
	deckID := api.Config.Anki.DeckID
	if api.Reader != nil {
		deckID = api.Reader.DeckID()
		if total, err := api.Reader.CountLearned(); err == nil {
			totalLearned = total
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"success":        true,
		"anki_available": ankiAvailable,
		"anki_path":      api.Config.Anki.DBPath,
		"deck_name":      api.Config.Anki.DeckName,
		"deck_id":        deckID,
		"total_learned":  totalLearned,
		"default_limit":  api.Config.Practice.DefaultLimit,
		"max_limit":      api.Config.Practice.MaxLimit,
	})
}

func appendStats(stats models.StatsRequest) error {
	record := struct {
		SubmittedAt time.Time `json:"submitted_at"`
		models.StatsRequest
	}{
		SubmittedAt:  time.Now(),
		StatsRequest: stats,
	}

	if err := os.MkdirAll("data", 0o755); err != nil {
		return err
	}

	file, err := os.OpenFile(filepath.Join("data", "stats.jsonl"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	return encoder.Encode(record)
}
