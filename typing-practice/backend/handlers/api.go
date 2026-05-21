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
	"typing-practice/stats"
	"typing-practice/utils"

	"github.com/gin-gonic/gin"
)

type API struct {
	// Config 保存运行时配置，handler 中主要用于读取默认 limit 和 Anki/统计路径。
	Config *config.Config
	// Reader 负责读取 Anki 数据库；可能为 nil，此时词库相关接口返回 503。
	Reader *anki.Reader
	// Stats 负责统计数据库；启动时必须初始化成功。
	Stats *stats.Store
}

func RegisterRoutes(router *gin.Engine, api *API) {
	// 这里注册练习主流程相关接口；统计图表接口在 RegisterStatsRoutes 中注册。
	router.GET("/api/health", api.Health)
	router.GET("/api/words", api.GetWords)
	router.POST("/api/check", api.CheckSpelling)
	router.POST("/api/stats", api.SubmitStats)
	router.GET("/api/config", api.GetConfig)
	api.RegisterStatsRoutes(router)
}

func (api *API) Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"status":  "ok",
	})
}

func (api *API) GetWords(c *gin.Context) {
	// 从 Anki 中随机读取“已学习”的单词。limit 会被配置中的 max_limit 限制。
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
	// 根据 word_id 重新从 Anki 取 expected，而不是信任前端传来的答案。
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
	// 兼容旧前端的统计提交格式：继续写 JSONL，同时同步写入新的 SQLite 统计库。
	var request models.StatsRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error()})
		return
	}

	if err := appendStats(request); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "error": err.Error()})
		return
	}
	if api.Stats != nil && request.Total > 0 {
		if err := api.Stats.SaveSession(legacyStatsToSession(request)); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error()})
			return
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"message": "Statistics saved",
	})
}

func (api *API) GetConfig(c *gin.Context) {
	// 返回前端展示/诊断需要的运行配置，不暴露敏感信息。
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
	// 旧版轻量统计文件，保留它是为了不破坏已有调试数据和前端调用。
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
