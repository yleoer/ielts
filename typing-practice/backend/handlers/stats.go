package handlers

import (
	"net/http"
	"strconv"
	"time"

	"typing-practice/models"
	"typing-practice/stats"

	"github.com/gin-gonic/gin"
)

func (api *API) RegisterStatsRoutes(router *gin.Engine) {
	// 统计接口单独挂在 /api/stats 下，对应 STATISTICS-SPEC.md 中的 12 个端点。
	group := router.Group("/api/stats")
	group.POST("/sessions", api.SaveStatsSession)
	group.GET("/heatmap", api.GetHeatmap)
	group.GET("/accuracy-trend", api.GetAccuracyTrend)
	group.GET("/mastery-distribution", api.GetMasteryDistribution)
	// 点击“单词掌握度分布”饼图时，前端会按 mastery_level 拉取对应单词明细。
	group.GET("/mastery-words", api.GetMasteryWords)
	group.GET("/top-errors", api.GetTopErrors)
	group.GET("/speed-trend", api.GetSpeedTrend)
	group.GET("/daily-duration", api.GetDailyDuration)
	group.GET("/category-mastery", api.GetCategoryMastery)
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
		return api.Stats.MasteryDistribution()
	})
}

func (api *API) GetMasteryWords(c *gin.Context) {
	// level 与 word_mastery.mastery_level 对齐：mastered/familiar/learning/weak/new。
	api.respondStats(c, func() (any, error) {
		return api.Stats.MasteryWords(c.Query("level"), queryInt(c, "limit", 200))
	})
}

func (api *API) GetTopErrors(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.TopErrors(queryInt(c, "limit", 10))
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

func (api *API) GetCategoryMastery(c *gin.Context) {
	api.respondStats(c, func() (any, error) {
		return api.Stats.CategoryMastery()
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

func legacyStatsToSession(request models.StatsRequest) stats.SessionRequest {
	// 兼容旧版 POST /api/stats：旧接口只知道错题列表，
	// 因此只能把错误单词写入 word_attempts，正确单词无法逐个还原。
	now := time.Now().UTC()
	attempts := make([]stats.AttemptRequest, 0, len(request.Errors))
	for _, item := range request.Errors {
		errorType := stats.AnalyzeErrorType(item.Word, item.UserInput)
		attempts = append(attempts, stats.AttemptRequest{
			Word:           item.Word,
			ChineseMeaning: item.Meaning,
			UserInput:      item.UserInput,
			IsCorrect:      false,
			ErrorType:      &errorType,
		})
	}

	return stats.SessionRequest{
		SessionID:       request.SessionID,
		StartTime:       now.Add(-time.Duration(request.DurationSeconds) * time.Second),
		EndTime:         &now,
		TotalWords:      request.Total,
		CorrectWords:    request.Correct,
		IncorrectWords:  request.Total - request.Correct,
		Accuracy:        float64(request.Correct) * 100 / float64(maxInt(request.Total, 1)),
		DurationSeconds: request.DurationSeconds,
		WordAttempts:    attempts,
	}
}

func maxInt(left, right int) int {
	if left > right {
		return left
	}
	return right
}
