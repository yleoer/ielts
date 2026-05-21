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
	Server   ServerConfig   `yaml:"server"`
	Anki     AnkiConfig     `yaml:"anki"`
	Practice PracticeConfig `yaml:"practice"`
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

func Load() (*Config, error) {
	cfg := defaultConfig()

	if path := findConfigFile(); path != "" {
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		if err := yaml.Unmarshal(data, &cfg); err != nil {
			return nil, err
		}
	}

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
	}
}

func findConfigFile() string {
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
}

func normalize(cfg *Config) {
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
}

func defaultAnkiDBPath() string {
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
