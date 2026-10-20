-- ═══════════════════════════════════════════════════════════════
-- SWARM ENGINE: Operational Engine (Sentinel + Tester + Tasks)
-- OpenCode Swarm v2
-- ═══════════════════════════════════════════════════════════════

PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 30000;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SENTINEL RULES: Engineering & Quality Standards            │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS sentinel_rules (
    rule_code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    target_agent TEXT NOT NULL DEFAULT 'all',
    severity TEXT NOT NULL DEFAULT 'high',
    description TEXT NOT NULL,
    checklist TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SENTINEL AUDITS: Deliverable Reviews & Scorecards          │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS sentinel_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    agent_name TEXT NOT NULL,
    task_title TEXT NOT NULL,
    verdict TEXT NOT NULL,
    score INTEGER NOT NULL,
    violations_json TEXT DEFAULT '[]',
    feedback TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SENTINEL VIOLATIONS: Active & Resolved Quality Violations  │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS sentinel_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    agent_name TEXT NOT NULL,
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'high',
    details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    resolution_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    resolved_at TEXT DEFAULT ''
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  TESTER RUNS: Automated Test Suite Executions & Coverage    │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS tester_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    runner TEXT NOT NULL,
    target_path TEXT DEFAULT '',
    status TEXT NOT NULL,
    total_tests INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    coverage_percent REAL DEFAULT 0.0,
    duration_ms REAL DEFAULT 0.0,
    output TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  COMPONENT CHECKS: Syntax, Type & Lint Health               │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS component_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    file_path TEXT NOT NULL,
    check_type TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT DEFAULT '',
    duration_ms REAL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  ENDPOINT PROBES: Live HTTP Health & Latency Probes         │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS endpoint_probes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    url TEXT NOT NULL,
    method TEXT DEFAULT 'GET',
    expected_status INTEGER DEFAULT 200,
    actual_status INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0.0,
    status TEXT NOT NULL,
    response_snippet TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SWARM TASKS: Task Board & Milestone Lifecycle              │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS swarm_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'normal',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SWARM ARTIFACTS: Shared Contracts (API, Schemas, etc.)     │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS swarm_artifacts (
    artifact_key TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT 'default',
    title TEXT NOT NULL,
    creator TEXT NOT NULL,
    artifact_type TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (artifact_key, project)
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SWARM FEED: Broadcast Telemetry & Inter-Agent Signals       │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS swarm_feed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'default',
    sender TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'status',
    priority TEXT NOT NULL DEFAULT 'normal',
    created_at TEXT NOT NULL
);

-- Índices de aceleración
CREATE INDEX IF NOT EXISTS idx_sentinel_audits_proj ON sentinel_audits(project, created_at);
CREATE INDEX IF NOT EXISTS idx_sentinel_viol_proj ON sentinel_violations(project, status);
CREATE INDEX IF NOT EXISTS idx_tester_runs_proj ON tester_runs(project, created_at);
CREATE INDEX IF NOT EXISTS idx_comp_checks_proj ON component_checks(project, created_at);
CREATE INDEX IF NOT EXISTS idx_endpoint_probes_proj ON endpoint_probes(project, created_at);
CREATE INDEX IF NOT EXISTS idx_swarm_tasks_proj ON swarm_tasks(project, status);
CREATE INDEX IF NOT EXISTS idx_swarm_feed_proj ON swarm_feed(project, created_at);
