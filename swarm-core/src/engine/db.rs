use std::path::PathBuf;
use rusqlite::{Connection, Result};

pub fn default_swarm_db_path() -> PathBuf {
    if let Ok(val) = std::env::var("OPENCODE_SWARM_DB") {
        return PathBuf::from(val);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".opencode").join("swarm").join("swarm.db")
}

pub fn open_swarm_db(path_opt: Option<&PathBuf>) -> Result<Connection> {
    let path = match path_opt {
        Some(p) => p.clone(),
        None => default_swarm_db_path(),
    };

    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    let conn = Connection::open(&path)?;
    let _ = conn.busy_timeout(std::time::Duration::from_secs(30));
    let _: String = conn.query_row("PRAGMA journal_mode = WAL", [], |r| r.get(0)).unwrap_or_default();
    conn.execute_batch(
        r#"
        PRAGMA synchronous = NORMAL;
        PRAGMA foreign_keys = ON;
        "#,
    )?;

    init_swarm_schema(&conn)?;
    Ok(conn)
}

pub fn init_swarm_schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS sentinel_rules (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            target_agent TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL,
            checklist TEXT NOT NULL,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sentinel_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_code TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            task_title TEXT DEFAULT '',
            details TEXT NOT NULL,
            severity TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'global',
            resolved INTEGER DEFAULT 0,
            resolution_notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS swarm_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            assigned_to TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'todo',
            priority TEXT NOT NULL DEFAULT 'normal',
            project TEXT NOT NULL DEFAULT 'global',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS swarm_artifacts (
            key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            artifact_type TEXT NOT NULL DEFAULT 'contract',
            creator TEXT NOT NULL DEFAULT 'agent',
            project TEXT NOT NULL DEFAULT 'global',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tester_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_path TEXT NOT NULL,
            runner TEXT NOT NULL,
            status TEXT NOT NULL,
            total_tests INTEGER DEFAULT 0,
            passed INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            coverage_pct REAL DEFAULT 0.0,
            duration_ms INTEGER DEFAULT 0,
            output TEXT DEFAULT '',
            project TEXT NOT NULL DEFAULT 'global',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS component_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            check_type TEXT NOT NULL,
            passed INTEGER NOT NULL,
            diagnostics TEXT DEFAULT '',
            project TEXT NOT NULL DEFAULT 'global',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_violations_rule ON sentinel_violations(rule_code);
        CREATE INDEX IF NOT EXISTS idx_violations_project ON sentinel_violations(project);
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON swarm_tasks(project);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON swarm_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_artifacts_project ON swarm_artifacts(project);
        CREATE INDEX IF NOT EXISTS idx_runs_project ON tester_runs(project);
        "#,
    )?;
    Ok(())
}
