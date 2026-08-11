from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA secure_delete = ON;

CREATE TABLE IF NOT EXISTS interception_test_records (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    intercepted_at TEXT NOT NULL,
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    request_raw_json TEXT NOT NULL,
    model_request_raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interception_test_records_time
ON interception_test_records(intercepted_at DESC);

CREATE INDEX IF NOT EXISTS idx_interception_test_records_model
ON interception_test_records(model);

CREATE TABLE IF NOT EXISTS api_message_history (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'completed', 'failed', 'client_disconnected'
        )
    ),
    request_body TEXT NOT NULL,
    response_body TEXT,
    response_content_type TEXT,
    http_status INTEGER,
    error_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_message_history_started
ON api_message_history(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_api_message_history_model
ON api_message_history(model);

CREATE INDEX IF NOT EXISTS idx_api_message_history_status
ON api_message_history(status);

CREATE TABLE IF NOT EXISTS api_message_history_outputs (
    history_id TEXT PRIMARY KEY REFERENCES api_message_history(id) ON DELETE CASCADE,
    response_blocks_json TEXT NOT NULL,
    media_assets_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_diagnostics (
    sequence INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL CHECK (
        level IN ('debug', 'info', 'warning', 'error')
    ),
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    code TEXT NOT NULL,
    exception_type TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_diagnostics_timestamp
ON runtime_diagnostics(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_runtime_diagnostics_request
ON runtime_diagnostics(request_id);

CREATE TABLE IF NOT EXISTS agent_session_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('completed', 'failed', 'client_disconnected')
    ),
    error_code TEXT,
    input_messages_json TEXT NOT NULL,
    timeline_json TEXT NOT NULL,
    response_text TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_session_runs_session
ON agent_session_runs(session_id, started_at);

CREATE INDEX IF NOT EXISTS idx_agent_session_runs_started
ON agent_session_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS agent_session_run_outputs (
    run_id TEXT PRIMARY KEY REFERENCES agent_session_runs(id) ON DELETE CASCADE,
    response_blocks_json TEXT NOT NULL,
    media_assets_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_output_assets (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    block_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'audio', 'video', 'file')),
    mime_type TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    original_filename TEXT NOT NULL,
    finalized INTEGER NOT NULL CHECK (finalized IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_media_output_assets_request
ON media_output_assets(request_id);

"""
