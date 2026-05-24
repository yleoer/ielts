package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"typing-practice/anki"
	"typing-practice/config"
	"typing-practice/handlers"
	"typing-practice/stats"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func main() {
	// 启动时先加载配置。配置来源顺序是：默认值 -> config.yaml -> 环境变量。
	// 这样本地开发和 Docker 部署可以共用同一套代码。
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	// Anki 数据库只作为词库来源读取。读取失败时不终止服务，
	// 前端仍然可以打开，统计接口也仍然可用。
	var reader *anki.Reader
	reader, err = anki.NewReader(cfg.Anki)
	if err != nil {
		log.Printf("Anki reader disabled: %v", err)
	} else {
		defer reader.Close()
		log.Printf("Using Anki database: %s", reader.DBPath())
		log.Printf("Using deck: %s (%d)", reader.DeckName(), reader.DeckID())
	}

	// 统计数据库是应用自己的数据源，用来保存练习会话、单词尝试、
	// 掌握度和里程碑。它必须可用，否则统计功能无法正常工作。
	statsStore, err := stats.Open(cfg.Stats.DBPath)
	if err != nil {
		log.Fatalf("open stats database: %v", err)
	}
	defer statsStore.Close()
	log.Printf("Using stats database: %s", cfg.Stats.DBPath)

	router := gin.Default()
	router.Use(cors.New(cors.Config{
		AllowOrigins: []string{
			"http://localhost:3000",
			"http://127.0.0.1:3000",
			"http://localhost:8080",
			"http://127.0.0.1:8080",
		},
		// 允许直接打开本地 HTML 文件时产生的 null origin，方便无前端服务器调试。
		AllowOriginFunc:  func(origin string) bool { return origin == "" || origin == "null" },
		AllowMethods:     []string{"GET", "POST", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	api := &handlers.API{Config: cfg, Reader: reader, Stats: statsStore}
	handlers.RegisterRoutes(router, api)
	registerFrontend(router)
	api.StartAnkiSyncScheduler()

	log.Printf("Listening on http://%s", cfg.Addr())
	if err := router.Run(cfg.Addr()); err != nil {
		log.Fatal(err)
	}
}

func registerFrontend(router *gin.Engine) {
	// 后端顺便托管前端静态文件，部署时只需要暴露 8080 一个端口。
	// 如果 frontend 不存在，就只注册 API，不影响后端启动。
	frontendPath := filepath.Clean(filepath.Join("..", "frontend"))
	if _, err := os.Stat(filepath.Join(frontendPath, "index.html")); err != nil {
		return
	}

	router.Static("/assets", filepath.Join(frontendPath, "assets"))
	router.Static("/src", filepath.Join(frontendPath, "src"))
	router.GET("/", func(c *gin.Context) {
		c.File(filepath.Join(frontendPath, "index.html"))
	})
	router.GET("/index.html", func(c *gin.Context) {
		c.File(filepath.Join(frontendPath, "index.html"))
	})
	router.GET("/stats.html", func(c *gin.Context) {
		c.File(filepath.Join(frontendPath, "stats.html"))
	})
	// 对未知 GET 路径返回前端入口，给未来前端路由预留空间。
	router.NoRoute(func(c *gin.Context) {
		if strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.JSON(http.StatusNotFound, gin.H{"success": false, "error": "not found"})
			return
		}
		if c.Request.Method == http.MethodGet {
			c.File(filepath.Join(frontendPath, "index.html"))
			return
		}
		c.JSON(http.StatusNotFound, gin.H{"success": false, "error": "not found"})
	})
}
