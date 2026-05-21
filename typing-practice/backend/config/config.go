package config

import (
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"
)

type Config struct {
	// Server 控制 Gin 监听地址。
	Server ServerConfig `yaml:"server"`
	// Anki 控制外部 Anki collection.anki2 的读取位置和目标牌组。
	Anki AnkiConfig `yaml:"anki"`
	// Practice 控制练习单词拉取数量等业务默认值。
	Practice PracticeConfig `yaml:"practice"`
	// Stats 控制本应用自己的统计数据库位置。
	Stats StatsConfig `yaml:"stats"`
}

type ServerConfig struct {
	Host string `yaml:"host"`
	Port int    `yaml:"port"`
}

type AnkiConfig struct {
	DBPath   string `yaml:"db_path"`
	DeckName string `yaml:"deck_name"`
	DeckID   int64  `yaml:"deck_id"`
}

type PracticeConfig struct {
	DefaultLimit int  `yaml:"default_limit"`
	MaxLimit     int  `yaml:"max_limit"`
	EnableAudio  bool `yaml:"enable_audio"`
}

type StatsConfig struct {
	DBPath string `yaml:"db_path"`
}

func Load() (*Config, error) {
	cfg := defaultConfig()

	// config.yaml 是可选的：缺省时用默认配置，存在时覆盖默认值。
	if path := findConfigFile(); path != "" {
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		if err := yaml.Unmarshal(data, &cfg); err != nil {
			return nil, err
		}
	}

	// 环境变量优先级最高，方便 Docker 运行时通过 -e 覆盖路径和端口。
	applyEnvOverrides(&cfg)
	normalize(&cfg)

	return &cfg, nil
}

func (c Config) Addr() string {
	host := strings.TrimSpace(c.Server.Host)
	if host == "" {
		host = "localhost"
	}
	return host + ":" + strconv.Itoa(c.Server.Port)
}

func defaultConfig() Config {
	return Config{
		Server: ServerConfig{
			Host: "localhost",
			Port: 8080,
		},
		Anki: AnkiConfig{
			DBPath:   defaultAnkiDBPath(),
			DeckName: "IELTS Vocabulary",
			DeckID:   2055274336,
		},
		Practice: PracticeConfig{
			DefaultLimit: 20,
			MaxLimit:     100,
			EnableAudio:  false,
		},
		Stats: StatsConfig{
			DBPath: filepath.Join("data", "stats.db"),
		},
	}
}

func findConfigFile() string {
	// 支持两种启动目录：
	// 1. 在 backend 目录运行 go run .
	// 2. 在仓库根目录运行 go run ./typing-practice/backend
	candidates := []string{
		filepath.Join("config", "config.yaml"),
		filepath.Join("typing-practice", "backend", "config", "config.yaml"),
	}

	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}

	return ""
}

func applyEnvOverrides(cfg *Config) {
	if value := strings.TrimSpace(os.Getenv("SERVER_HOST")); value != "" {
		cfg.Server.Host = value
	}
	if value := strings.TrimSpace(os.Getenv("SERVER_PORT")); value != "" {
		if port, err := strconv.Atoi(value); err == nil {
			cfg.Server.Port = port
		}
	}
	if value := strings.TrimSpace(os.Getenv("ANKI_DB_PATH")); value != "" {
		cfg.Anki.DBPath = value
	}
	if value := strings.TrimSpace(os.Getenv("ANKI_DECK_NAME")); value != "" {
		cfg.Anki.DeckName = value
	}
	if value := strings.TrimSpace(os.Getenv("ANKI_DECK_ID")); value != "" {
		if deckID, err := strconv.ParseInt(value, 10, 64); err == nil {
			cfg.Anki.DeckID = deckID
		}
	}
	if value := strings.TrimSpace(os.Getenv("PRACTICE_DEFAULT_LIMIT")); value != "" {
		if limit, err := strconv.Atoi(value); err == nil {
			cfg.Practice.DefaultLimit = limit
		}
	}
	if value := strings.TrimSpace(os.Getenv("PRACTICE_MAX_LIMIT")); value != "" {
		if limit, err := strconv.Atoi(value); err == nil {
			cfg.Practice.MaxLimit = limit
		}
	}
	if value := strings.TrimSpace(os.Getenv("STATS_DB_PATH")); value != "" {
		cfg.Stats.DBPath = value
	}
}

func normalize(cfg *Config) {
	// normalize 负责兜底非法或空配置，避免后续代码到处判断零值。
	if cfg.Server.Port <= 0 {
		cfg.Server.Port = 8080
	}
	if strings.TrimSpace(cfg.Server.Host) == "" {
		cfg.Server.Host = "localhost"
	}
	if strings.TrimSpace(cfg.Anki.DBPath) == "" {
		cfg.Anki.DBPath = defaultAnkiDBPath()
	}
	if strings.TrimSpace(cfg.Anki.DeckName) == "" {
		cfg.Anki.DeckName = "IELTS Vocabulary"
	}
	if cfg.Practice.DefaultLimit <= 0 {
		cfg.Practice.DefaultLimit = 20
	}
	if cfg.Practice.MaxLimit <= 0 {
		cfg.Practice.MaxLimit = 100
	}
	if cfg.Practice.DefaultLimit > cfg.Practice.MaxLimit {
		cfg.Practice.DefaultLimit = cfg.Practice.MaxLimit
	}
	if strings.TrimSpace(cfg.Stats.DBPath) == "" {
		cfg.Stats.DBPath = filepath.Join("data", "stats.db")
	}
}

func defaultAnkiDBPath() string {
	// Windows 下优先检查文档中的 User 1；如果不存在，就扫描 Anki2 下的真实 profile。
	// 这对中文 profile 名（例如“账户1”）尤其有用。
	if appData := os.Getenv("APPDATA"); appData != "" {
		userOne := filepath.Join(appData, "Anki2", "User 1", "collection.anki2")
		if _, err := os.Stat(userOne); err == nil {
			return userOne
		}
		if discovered := DiscoverAnkiDB(filepath.Join(appData, "Anki2")); discovered != "" {
			return discovered
		}
		return userOne
	}

	if home, err := os.UserHomeDir(); err == nil {
		candidates := []string{
			filepath.Join(home, "Library", "Application Support", "Anki2"),
			filepath.Join(home, ".local", "share", "Anki2"),
		}
		for _, candidate := range candidates {
			if discovered := DiscoverAnkiDB(candidate); discovered != "" {
				return discovered
			}
		}
	}

	return ""
}

func DiscoverAnkiDB(ankiRoot string) string {
	// 只做一层 profile 扫描，避免误入 addons/logs 等非用户数据目录。
	if strings.TrimSpace(ankiRoot) == "" {
		return ""
	}

	entries, err := os.ReadDir(ankiRoot)
	if err != nil {
		return ""
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		name := entry.Name()
		if strings.HasPrefix(name, ".") || name == "addons21" || name == "logs" {
			continue
		}
		dbPath := filepath.Join(ankiRoot, name, "collection.anki2")
		if _, err := os.Stat(dbPath); err == nil {
			return dbPath
		}
	}

	return ""
}

func (c Config) Validate() error {
	if strings.TrimSpace(c.Anki.DBPath) == "" {
		return errors.New("anki database path is empty")
	}
	return nil
}
