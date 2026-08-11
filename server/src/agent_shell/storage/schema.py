from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA secure_delete = ON;

-- Removed legacy single-agent/API history. There is no user data contract to migrate yet.
DROP TABLE IF EXISTS agent_session_run_outputs;
DROP TABLE IF EXISTS agent_session_runs;
DROP TABLE IF EXISTS api_message_history_outputs;
DROP TABLE IF EXISTS api_message_history;

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

CREATE TABLE IF NOT EXISTS workflow_runs (
    thread_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    request_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    messages_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'failed', 'cancelled')
    ),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT NOT NULL,
    langsmith_project TEXT NOT NULL,
    tracing_enabled INTEGER NOT NULL CHECK (tracing_enabled IN (0, 1)),
    run_tree_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_started
ON workflow_runs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_request
ON workflow_runs(request_id);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow
ON workflow_runs(workflow_id, started_at DESC);

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
