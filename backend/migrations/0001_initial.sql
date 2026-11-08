PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS user_timezones (
  guild_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  timezone TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
  message_id TEXT PRIMARY KEY,
  guild_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  username TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  edited_at TEXT,
  deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_guild_created
  ON messages (guild_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_channel_created
  ON messages (channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user_created
  ON messages (guild_id, user_id, created_at DESC);
