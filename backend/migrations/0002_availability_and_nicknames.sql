PRAGMA foreign_keys = ON;

-- One row represents one whole-hour interval and its availability state.
-- weekday: Monday=0 through Sunday=6. end_hour is exclusive.
CREATE TABLE IF NOT EXISTS weekly_availability (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  start_hour INTEGER NOT NULL CHECK (start_hour BETWEEN 0 AND 23),
  end_hour INTEGER NOT NULL CHECK (end_hour BETWEEN 1 AND 24),
  status TEXT NOT NULL CHECK (status IN ('free', 'chat')),
  CHECK (start_hour < end_hour)
);

CREATE INDEX IF NOT EXISTS idx_availability_lookup
  ON weekly_availability (guild_id, weekday, start_hour, end_hour, status);

CREATE INDEX IF NOT EXISTS idx_availability_user
  ON weekly_availability (guild_id, user_id, weekday);

-- Durable queue state. A new hourly cycle can reset a previous terminal failure.
CREATE TABLE IF NOT EXISTS nickname_updates (
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  target_nickname TEXT,
  cycle_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'success', 'failed')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 4),
  last_error TEXT,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (guild_id, user_id, cycle_key)
);

CREATE INDEX IF NOT EXISTS idx_nickname_updates_queue
  ON nickname_updates (cycle_key, status, attempts);
