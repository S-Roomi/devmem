CREATE TABLE events (
  id          TEXT PRIMARY KEY,
  device_id   TEXT NOT NULL,
  type        TEXT NOT NULL,
  start_ms    INTEGER NOT NULL,
  duration_ms INTEGER,
  exit_code   INTEGER,
  cwd         TEXT,
  command     TEXT NOT NULL
);