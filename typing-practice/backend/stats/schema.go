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

CREATE INDEX IF NOT EXISTS idx_session_start_time ON practice_sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_session_id ON word_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_word ON word_attempts(word);
CREATE INDEX IF NOT EXISTS idx_attempt_time ON word_attempts(attempt_time);
CREATE INDEX IF NOT EXISTS idx_word_category ON word_attempts(category);
CREATE INDEX IF NOT EXISTS idx_mastery_level ON word_mastery(mastery_level);
CREATE INDEX IF NOT EXISTS idx_mastery_word ON word_mastery(word);
CREATE UNIQUE INDEX IF NOT EXISTS idx_milestone_type_unique ON milestones(milestone_type);
`
