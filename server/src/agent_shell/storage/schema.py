from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA secure_delete = ON;

CREATE TABLE IF NOT EXISTS provider_secrets (
    id TEXT PRIMARY KEY,
    secret_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    block_type TEXT NOT NULL,
    name TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_blocks_type_name ON blocks(block_type, name);
CREATE INDEX IF NOT EXISTS idx_blocks_type ON blocks(block_type);

CREATE TABLE IF NOT EXISTS primary_agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subagents (
    id TEXT PRIMARY KEY,
    component_name TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hook_workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lifecycle_workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_server_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    api_key TEXT
);

INSERT OR IGNORE INTO api_server_settings (
    singleton, enabled, api_key
) VALUES (1, 1, NULL);

CREATE TABLE IF NOT EXISTS api_server_request_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    max_initial_messages INTEGER NOT NULL CHECK (
        max_initial_messages >= 1 AND max_initial_messages <= 10000
    )
);

INSERT OR IGNORE INTO api_server_request_settings (
    singleton, max_initial_messages
) VALUES (1, 1000);

CREATE TABLE IF NOT EXISTS history_retention_settings (
    history_type TEXT PRIMARY KEY CHECK (
        history_type IN (
            'api_history', 'interception_history',
            'agent_session_runs', 'runtime_log'
        )
    ),
    retention_limit INTEGER NOT NULL CHECK (
        retention_limit >= 1 AND retention_limit <= 10000
    )
);

INSERT OR IGNORE INTO history_retention_settings (history_type, retention_limit)
VALUES
    ('api_history', 20),
    ('interception_history', 20),
    ('agent_session_runs', 20),
    ('runtime_log', 20);

CREATE TABLE IF NOT EXISTS runtime_control_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    interception_enabled INTEGER NOT NULL CHECK (
        interception_enabled IN (0, 1)
    ),
    verbose_diagnostics INTEGER NOT NULL CHECK (
        verbose_diagnostics IN (0, 1)
    )
);

INSERT OR IGNORE INTO runtime_control_settings (
    singleton, interception_enabled, verbose_diagnostics
) VALUES (1, 0, 0);

CREATE TABLE IF NOT EXISTS system_log_settings (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    max_size_mib INTEGER NOT NULL CHECK (
        max_size_mib >= 1 AND max_size_mib <= 1024
    )
);

INSERT OR IGNORE INTO system_log_settings (singleton, max_size_mib)
VALUES (1, 5);

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

"""
