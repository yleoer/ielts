package handlers

import (
	"net/http"
	"strconv"
	"sync"
	"time"

	"typing-practice/anki"
	"typing-practice/config"
	"typing-practice/models"
	"typing-practice/practice"
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
	// ReaderMu 保护 Reader 在手动同步时被关闭和重新打开。
	ReaderMu sync.RWMutex
	// Sync 记录最近一次 Anki 数据同步结果。
	Sync SyncStatus
}

func RegisterRoutes(router *gin.Engine, api *API) {
	// 这里注册练习主流程相关接口；统计图表接口在 RegisterStatsRoutes 中注册。
	router.GET("/api/health", api.Health)
	router.GET("/api/words", api.GetWords)
	router.GET("/api/config", api.GetConfig)
	router.GET("/api/sync/status", api.GetSyncStatus)
	router.POST("/api/sync/now", api.SyncNow)
	api.RegisterStatsRoutes(router)
}

func (api *API) Health(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"status":  "ok",
	})
}

func (api *API) GetWords(c *gin.Context) {
	// 从 Anki 中读取“已学习”的单词，再结合统计库做分桶加权抽样。
	api.ReaderMu.RLock()
	defer api.ReaderMu.RUnlock()

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
	words, err := api.smartPracticeWords(limit, category)
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

func (api *API) smartPracticeWords(limit int, category string) ([]models.Word, error) {
	if api.Stats == nil {
		return api.Reader.GetLearnedWords(limit, category)
	}

	pool, err := api.Reader.GetLearnedWordPool(category)
	if err != nil {
		return nil, err
	}
	selectionStats, err := api.Stats.SelectionStatsByWord()
	if err != nil {
		return api.Reader.GetLearnedWords(limit, category)
	}

	return practice.SelectWords(pool, selectionStats, limit, time.Now().UTC(), nil), nil
}

func (api *API) GetConfig(c *gin.Context) {
	// 返回前端展示/诊断需要的运行配置，不暴露敏感信息。
	api.ReaderMu.RLock()
	defer api.ReaderMu.RUnlock()

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
