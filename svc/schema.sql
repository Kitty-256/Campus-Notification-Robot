-- notice-svc 数据库（SQLite，WAL 模式）
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS sources (
  id          TEXT PRIMARY KEY,        -- jwc / gs / informatics / ...
  list_url    TEXT NOT NULL,
  item_selector TEXT,
  encoding    TEXT DEFAULT 'utf-8',
  kind        TEXT DEFAULT 'html',     -- html | rss
  enabled     INTEGER DEFAULT 1
);

-- 采集原始快照：所有渠道的统一入口
CREATE TABLE IF NOT EXISTS raw_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source       TEXT NOT NULL,
  url          TEXT NOT NULL,
  url_hash     TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  content      TEXT,
  published_at TEXT,
  fetched_at   TEXT NOT NULL,
  processed    INTEGER DEFAULT 0,      -- 0 待处理 / 1 已处理 / 2 丢弃
  note         TEXT
);
CREATE INDEX IF NOT EXISTS ix_raw_pending ON raw_items(processed, id);

-- AI 处理后的成品
CREATE TABLE IF NOT EXISTS notices (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_id     INTEGER,
  cluster_id INTEGER,                  -- 同一件事的簇号；重复条目共享
  title      TEXT NOT NULL,
  one_line   TEXT,
  who        TEXT,
  deadline   TEXT,
  place      TEXT,
  tags       TEXT DEFAULT '[]',        -- JSON 数组
  source     TEXT,
  url        TEXT,
  score      REAL DEFAULT 0,
  confidence REAL DEFAULT 0,
  status     TEXT DEFAULT 'published', -- published | review
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notices_created ON notices(created_at);

-- 推送台账（验收指标全靠它）
CREATE TABLE IF NOT EXISTS deliveries (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  day        TEXT NOT NULL,
  chat_id    TEXT NOT NULL,
  count      INTEGER,
  status     TEXT DEFAULT 'ok',
  error      TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(day, chat_id)
);

-- 订阅（QQ 号 + 标签）
CREATE TABLE IF NOT EXISTS subscriptions (
  qq   TEXT NOT NULL,
  tag  TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (qq, tag)
);

-- 抓取日志（/api/stats 与告警用）
CREATE TABLE IF NOT EXISTS fetch_log (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  ok     INTEGER NOT NULL,
  n      INTEGER DEFAULT 0,
  err    TEXT,
  ts     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fetch_ts ON fetch_log(ts);

-- LLM 结果缓存（同一正文不重复花钱）
CREATE TABLE IF NOT EXISTS llm_cache (
  k       TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  ts      TEXT NOT NULL
);
