package stats

const schema = `
CREATE TABLE IF NOT EXISTS practice_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    user_id TEXT DEFAULT 'default',
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    total_words INTEGER NOT NULL,
    correct_words INTEGER NOT NULL,
    incorrect_words INTEGER NOT NULL,
    accuracy REAL NOT NULL,
    duration_seconds INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS word_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    word TEXT NOT NULL,
    chinese_meaning TEXT,
    category TEXT,
    user_input TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL,
    time_spent REAL,
    error_type TEXT,
    attempt_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES practice_sessions(session_id)
);

CREATE TABLE IF NOT EXISTS word_mastery (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL,
    total_attempts INTEGER DEFAULT 0,
    correct_attempts INTEGER DEFAULT 0,
    incorrect_attempts INTEGER DEFAULT 0,
    mastery_level TEXT DEFAULT 'new',
    last_attempt_time DATETIME,
    average_time REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_type TEXT NOT NULL,
    milestone_name TEXT NOT NULL,
    description TEXT,
    achieved_at DATETIME NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS anki_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at DATETIME NOT NULL,
    before_words INTEGER NOT NULL,
    after_words INTEGER NOT NULL,
    added_words INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    message TEXT,
    source_path TEXT,
    target_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anki_sync_added_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id INTEGER NOT NULL,
    word_id INTEGER,
    word TEXT NOT NULL,
    chinese_meaning TEXT,
    category TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sync_id) REFERENCES anki_sync_history(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_start_time ON practice_sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_session_id ON word_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_word ON word_attempts(word);
CREATE INDEX IF NOT EXISTS idx_attempt_time ON word_attempts(attempt_time);
CREATE INDEX IF NOT EXISTS idx_word_category ON word_attempts(category);
CREATE INDEX IF NOT EXISTS idx_mastery_level ON word_mastery(mastery_level);
CREATE INDEX IF NOT EXISTS idx_mastery_word ON word_mastery(word);
CREATE UNIQUE INDEX IF NOT EXISTS idx_milestone_type_unique ON milestones(milestone_type);
CREATE INDEX IF NOT EXISTS idx_anki_sync_history_synced_at ON anki_sync_history(synced_at);
CREATE INDEX IF NOT EXISTS idx_anki_sync_added_words_sync_id ON anki_sync_added_words(sync_id);
`
