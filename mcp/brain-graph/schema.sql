-- ═══════════════════════════════════════════════════════════════
-- BRAIN GRAPH: Knowledge Graph con Typed Edges para OpenCode Swarm v2
-- Base de datos neural para agentes autónomos con:
--   • Nodos tipados (decisiones, componentes, endpoints, tests, reglas)
--   • Edges dirigidos con vocabulario de relaciones
--   • Observations granulares sobre nodos
--   • FTS5 full-text search
--   • Confidence decay para auto-pruning
-- ═══════════════════════════════════════════════════════════════

PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 30000;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- ┌─────────────────────────────────────────────────────────────┐
-- │  NODES: Unidades atómicas de conocimiento                    │
-- └─────────────────────────────────────────────────────────────┘
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

-- ┌─────────────────────────────────────────────────────────────┐
-- │  EDGES: Relaciones tipadas y dirigidas entre nodos           │
-- └─────────────────────────────────────────────────────────────┘
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

-- ┌─────────────────────────────────────────────────────────────┐
-- │  OBSERVATIONS: Hechos granulares sobre nodos                 │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    observation TEXT NOT NULL,
    observer TEXT DEFAULT '',
    observed_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  SESSION CHECKPOINTS: Snapshots de sesión para bootstrap     │
-- └─────────────────────────────────────────────────────────────┘
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT 'global',
    summary TEXT NOT NULL,
    files_modified TEXT DEFAULT '',
    active_task TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- ┌─────────────────────────────────────────────────────────────┐
-- │  FTS5: Full-text search sobre nodos                          │
-- └─────────────────────────────────────────────────────────────┘
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    id, title, content, tags, project,
    content=nodes, content_rowid=rowid
);

-- Triggers para mantener FTS sincronizado
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

-- Índices para traversal rápido
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON nodes(confidence);
CREATE INDEX IF NOT EXISTS idx_observations_node ON observations(node_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project);
