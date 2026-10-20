use std::path::PathBuf;
use rusqlite::{Connection, Result};

pub fn default_db_path() -> PathBuf {
    if let Ok(val) = std::env::var("OPENCODE_BRAIN_DB") {
        return PathBuf::from(val);
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".opencode").join("brain").join("brain.db")
}

pub fn open_brain_db(path_opt: Option<&PathBuf>) -> Result<Connection> {
    let path = match path_opt {
        Some(p) => p.clone(),
        None => default_db_path(),
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

    init_schema(&conn)?;
    Ok(conn)
}

pub fn init_schema(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        r#"
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            node_type TEXT NOT NULL DEFAULT 'concept',
            content TEXT NOT NULL DEFAULT '',
            project TEXT NOT NULL DEFAULT 'global',
            agent_origin TEXT DEFAULT '',
            confidence REAL DEFAULT 1.0,
            access_count INTEGER DEFAULT 0,
            last_accessed TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            reason TEXT DEFAULT '',
            weight REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            UNIQUE(source_id, target_id, relation)
        );

        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            observation TEXT NOT NULL,
            observer TEXT DEFAULT '',
            observed_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            id, title, content, tags, project,
            content=nodes, content_rowid=rowid
        );

        CREATE TRIGGER IF NOT EXISTS nodes_fts_ai AFTER INSERT ON nodes BEGIN
            INSERT INTO nodes_fts(rowid, id, title, content, tags, project)
            VALUES (new.rowid, new.id, new.title, new.content, new.tags, new.project);
        END;

        CREATE TRIGGER IF NOT EXISTS nodes_fts_ad AFTER DELETE ON nodes BEGIN
            INSERT INTO nodes_fts(nodes_fts, rowid, id, title, content, tags, project)
            VALUES ('delete', old.rowid, old.id, old.title, old.content, old.tags, old.project);
        END;

        CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE ON nodes BEGIN
            INSERT INTO nodes_fts(nodes_fts, rowid, id, title, content, tags, project)
            VALUES ('delete', old.rowid, old.id, old.title, old.content, old.tags, old.project);
            INSERT INTO nodes_fts(rowid, id, title, content, tags, project)
            VALUES (new.rowid, new.id, new.title, new.content, new.tags, new.project);
        END;

        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
        CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
        CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project);
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
        CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON nodes(confidence);
        CREATE INDEX IF NOT EXISTS idx_observations_node ON observations(node_id);
        "#,
    )?;
    Ok(())
}
