PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS student_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supervisors (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  school TEXT NOT NULL DEFAULT '',
  college TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_supervisors_school ON supervisors(school);
CREATE INDEX IF NOT EXISTS idx_supervisors_email ON supervisors(email);

CREATE TABLE IF NOT EXISTS knowledge_items (
  position INTEGER PRIMARY KEY,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_history (
  position INTEGER PRIMARY KEY,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question_history (
  position INTEGER PRIMARY KEY,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_history (
  id TEXT PRIMARY KEY,
  task TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assistant_history_created_at
  ON assistant_history(created_at DESC);

CREATE TABLE IF NOT EXISTS app_cache (
  key TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
