package handlers

import (
	"net/http"
	"strconv"
	"strings"

	"typing-practice/models"
	"typing-practice/stats"

	"github.com/gin-gonic/gin"
)

func (api *API) RegisterStatsRoutes(router *gin.Engine) {
	// 统计接口单独挂在 /api/stats 下，对应统计文档中的端点。
	group := router.Group("/api/stats")
	group.POST("/sessions", api.SaveStatsSession)
	group.GET("/heatmap", api.GetHeatmap)
	group.GET("/accuracy-trend", api.GetAccuracyTrend)
	group.GET("/mastery-distribution", api.GetMasteryDistribution)
	// 点击“单词掌握度分布”饼图时，前端会按 mastery_level 拉取对应单词明细。
	group.GET("/mastery-words", api.GetMasteryWords)
	group.GET("/speed-trend", api.GetSpeedTrend)
	group.GET("/daily-duration", api.GetDailyDuration)
	group.GET("/streak", api.GetStreak)
	group.GET("/error-types", api.GetErrorTypes)
	// 点击“错误类型分布”饼图时，前端会按 error_type 拉取具体错误单词。
	group.GET("/error-type-words", api.GetErrorTypeWords)
	group.GET("/milestones", api.GetMilestones)
	group.GET("/overview", api.GetOverview)
}

func (api *API) SaveStatsSession(c *gin.Context) {
	// 前端练习结束后提交完整 session 和每个单词的尝试记录。
	// 保存逻辑在 stats.Store 中保证幂等：同一个 session_id 重复提交会覆盖旧明细。
	if api.Stats == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "error": "stats database is not available"})
		return
	}

	var request stats.SessionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error()})
		return
	}

	if err := api.Stats.SaveSession(request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"success": false, "error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":    true,
		"message":    "Session saved successfully",
		"session_id": request.SessionID,
	})
}

func (api *API) GetHeatmap(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.Heatmap(c.Query("start_date"), c.Query("end_date"))
	})
}

func (api *API) GetAccuracyTrend(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.AccuracyTrend(queryInt(c, "days", 30))
	})
}

func (api *API) GetMasteryDistribution(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		distribution, err := api.Stats.MasteryDistribution()
		if err != nil {
			return nil, err
		}
		selectionStats, err := api.Stats.SelectionStatsByWord()
		if err != nil {
			return nil, err
		}
		words, err := api.currentAnkiWordPool()
		if err != nil || len(words) == 0 {
			return distribution, nil
		}
		return mergeUnpracticedWords(distribution, words, selectionStats), nil
	})
}

func (api *API) GetMasteryWords(c *gin.Context) {
	// level 与 word_mastery.mastery_level 对齐：mastered/familiar/learning/weak/new。
	api.respondStats(c, func() (any, error) {
		level := c.Query("level")
		limit := queryInt(c, "limit", 200)
		if level != "new" {
			return api.Stats.MasteryWords(level, limit)
		}

		selectionStats, err := api.Stats.SelectionStatsByWord()
		if err != nil {
			return nil, err
		}
		words, err := api.currentAnkiWordPool()
		if err != nil {
			return nil, err
		}
		return unpracticedWordDetails(words, selectionStats, limit), nil
	})
}

func (api *API) GetSpeedTrend(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.SpeedTrend(queryInt(c, "days", 30))
	})
}

func (api *API) GetDailyDuration(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.DailyDuration(queryInt(c, "days", 30))
	})
}

func (api *API) GetStreak(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.Streak()
	})
}

func (api *API) GetErrorTypes(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.ErrorTypes()
	})
}

func (api *API) GetErrorTypeWords(c *gin.Context) {
	// type 与 word_attempts.error_type 对齐：spelling/missing_letter/extra_letter/completely_wrong/skipped。
	api.respondStats(c, func() (any, error) {
		return api.Stats.ErrorTypeWords(c.Query("type"), queryInt(c, "limit", 200))
	})
}

func (api *API) GetMilestones(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.Milestones()
	})
}

func (api *API) GetOverview(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.Overview()
	})
}

func (api *API) respondStats(c *gin.Context, fetch func() (any, error)) {
	// 统计查询端点的响应格式完全一致：{ success, data } 或 { success, error }。
	// 这里集中处理，避免每个 handler 重复样板代码。
	if api.Stats == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "error": "stats database is not available"})
		return
	}

	data, err := fetch()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "data": data})
}

func queryInt(c *gin.Context, name string, defaultValue int) int {
	value, err := strconv.Atoi(c.Query(name))
	if err != nil || value <= 0 {
		return defaultValue
	}
	return value
}

func (api *API) currentAnkiWordPool() ([]models.Word, error) {
	api.ReaderMu.RLock()
	defer api.ReaderMu.RUnlock()

	if api.Reader == nil {
		return nil, nil
	}
	return api.Reader.GetLearnedWordPool("all")
}

func mergeUnpracticedWords(distribution map[string]int, words []models.Word, selectionStats map[string]stats.SelectionStats) map[string]int {
	data := make(map[string]int, len(distribution))
	for level, count := range distribution {
		data[level] = count
	}
	data["new"] = len(unpracticedWordDetails(words, selectionStats, 0))
	return data
}

func unpracticedWordDetails(words []models.Word, selectionStats map[string]stats.SelectionStats, limit int) []stats.MasteryWordDetail {
	if limit <= 0 {
		limit = len(words)
	}
	if limit > 1000 {
		limit = 1000
	}

	practiced := make(map[string]struct{}, len(selectionStats))
	for word := range selectionStats {
		practiced[normalizeWordKey(word)] = struct{}{}
	}

	details := make([]stats.MasteryWordDetail, 0)
	seen := make(map[string]struct{}, len(words))
	for _, word := range words {
		key := normalizeWordKey(word.Word)
		if key == "" {
			continue
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		if _, ok := practiced[key]; ok {
			continue
		}

		details = append(details, stats.MasteryWordDetail{
			Word:           word.Word,
			ChineseMeaning: word.ChineseMeaning,
		})
		if len(details) >= limit {
			break
		}
	}
	return details
}

func normalizeWordKey(word string) string {
	return strings.ToLower(strings.TrimSpace(word))
}
