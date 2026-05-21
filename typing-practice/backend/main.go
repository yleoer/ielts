package main

import (
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"typing-practice/anki"
	"typing-practice/config"
	"typing-practice/handlers"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	var reader *anki.Reader
	reader, err = anki.NewReader(cfg.Anki)
	if err != nil {
		log.Printf("Anki reader disabled: %v", err)
	} else {
		defer reader.Close()
		log.Printf("Using Anki database: %s", reader.DBPath())
		log.Printf("Using deck: %s (%d)", reader.DeckName(), reader.DeckID())
	}

	router := gin.Default()
	router.Use(cors.New(cors.Config{
		AllowOrigins: []string{
			"http://localhost:3000",
			"http://127.0.0.1:3000",
			"http://localhost:8080",
			"http://127.0.0.1:8080",
		},
		AllowOriginFunc:  func(origin string) bool { return origin == "" || origin == "null" },
		AllowMethods:     []string{"GET", "POST", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	api := &handlers.API{Config: cfg, Reader: reader}
	handlers.RegisterRoutes(router, api)
	registerFrontend(router)

	log.Printf("Listening on http://%s", cfg.Addr())
	if err := router.Run(cfg.Addr()); err != nil {
		log.Fatal(err)
	}
}

func registerFrontend(router *gin.Engine) {
	frontendPath := filepath.Clean(filepath.Join("..", "frontend"))
	if _, err := os.Stat(filepath.Join(frontendPath, "index.html")); err != nil {
		return
	}

	router.Static("/assets", filepath.Join(frontendPath, "assets"))
	router.Static("/src", filepath.Join(frontendPath, "src"))
	router.GET("/", func(c *gin.Context) {
		c.File(filepath.Join(frontendPath, "index.html"))
	})
	router.NoRoute(func(c *gin.Context) {
		if c.Request.Method == http.MethodGet {
			c.File(filepath.Join(frontendPath, "index.html"))
			return
		}
		c.JSON(http.StatusNotFound, gin.H{"success": false, "error": "not found"})
	})
}
