#!/usr/bin/env python3
"""
Brain Graph MCP Server — OpenCode Swarm v2
Knowledge graph with typed nodes, directed edges, observations, FTS5 search,
confidence decay, and multi-hop traversal for autonomous agent memory.

Replaces the flat key-value context-memory with a neural graph architecture
inspired by Obsidian's knowledge graph.

Standard JSON-RPC 2.0 stdio Model Context Protocol (MCP) server.
"""

import sys
import json
import os
import re
import math
import sqlite3
import datetime
import subprocess
import time
import random
from pathlib import Path
from contextlib import contextmanager

# ═══════════════════════════════════════════════════════════════
# Infrastructure (shared patterns, deduplicated from 4→1)
# ═══════════════════════════════════════════════════════════════

class ManagedConnection(sqlite3.Connection):
    """Close SQLite handles deterministically."""
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

DEFAULT_DB_DIR = Path.home() / ".opencode" / "brain"
DB_PATH = Path(os.environ.get("OPENCODE_BRAIN_DB", DEFAULT_DB_DIR / "brain.db"))

# Confidence decay constant: ~50% after 70 days without access
DECAY_LAMBDA = 0.01

# Valid node types
NODE_TYPES = frozenset({
    "concept", "decision", "component", "endpoint", "file", "test",
    "rule", "learning", "technology", "agent", "task", "checkpoint",
    "preference", "bug", "convention", "snippet", "architecture"
})

# Valid relation vocabulary
RELATIONS = frozenset({
    "USES", "DEPENDS_ON", "TESTED_BY", "GOVERNED_BY", "EXPOSES",
    "IMPLEMENTS", "CONTRADICTS", "SUPERSEDES", "CAUSED_BY",
    "LEARNED_FROM", "PRODUCED_BY", "REQUIRES", "BLOCKS",
    "PART_OF", "RELATED_TO", "TRIGGERS", "EXTENDS", "STORED_IN",
    "CONFIGURES", "DOCUMENTS", "FIXES", "BREAKS", "MIGRATES"
})


@contextmanager
def db_write_lock(conn, max_retries=10, base_delay=0.03):
    """Acquire immediate write lock with exponential backoff and jitter."""
    for attempt in range(max_retries):
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
                return
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            if ("locked" in err_msg or "busy" in err_msg) and attempt < max_retries - 1:
                sleep_time = (base_delay * (1.6 ** attempt)) + random.uniform(0.01, 0.04)
                time.sleep(sleep_time)
                continue
            raise


def get_current_project(explicit=None):
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env_proj = os.environ.get("OPENCODE_PROJECT", "").strip()
    if env_proj:
        return env_proj
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        if root:
            return Path(root).name
    except Exception:
        pass
    return Path.cwd().name or "global"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def slugify(text, max_len=60):
    """Convert text to a URL-safe slug for node IDs."""
    s = re.sub(r'[^a-z0-9]+', '-', text.lower().strip()).strip('-')
    return s[:max_len] if s else "node"


def format_relative_time(iso_str):
    if not iso_str:
        return "unknown"
    try:
        t = datetime.datetime.fromisoformat(iso_str)
        n = datetime.datetime.now(datetime.timezone.utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        diff = max(0, int((n - t).total_seconds()))
        if diff < 5: return "just now"
        if diff < 60: return f"{diff}s ago"
        m = diff // 60
        if m < 60: return f"{m}m ago"
        h = m // 60
        if h < 24: return f"{h}h ago"
        return f"{h // 24}d ago"
    except Exception:
        return iso_str


# ═══════════════════════════════════════════════════════════════
# Database Initialization
# ═══════════════════════════════════════════════════════════════

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.execute("""
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
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                relation TEXT NOT NULL,
                reason TEXT DEFAULT '',
                weight REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                UNIQUE(source_id, target_id, relation)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                observation TEXT NOT NULL,
                observer TEXT DEFAULT '',
                observed_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'global',
                summary TEXT NOT NULL,
                files_modified TEXT DEFAULT '',
                active_task TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        # FTS5
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    id, title, content, tags, project,
                    content=nodes, content_rowid=rowid
                )
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS nodes_fts_ai AFTER INSERT ON nodes BEGIN
                    INSERT INTO nodes_fts(rowid, id, title, content, tags, project)
                    VALUES (new.rowid, new.id, new.title, new.content, new.tags, new.project);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS nodes_fts_ad AFTER DELETE ON nodes BEGIN
                    INSERT INTO nodes_fts(nodes_fts, rowid, id, title, content, tags, project)
                    VALUES ('delete', old.rowid, old.id, old.title, old.content, old.tags, old.project);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE ON nodes BEGIN
                    INSERT INTO nodes_fts(nodes_fts, rowid, id, title, content, tags, project)
                    VALUES ('delete', old.rowid, old.id, old.title, old.content, old.tags, old.project);
                    INSERT INTO nodes_fts(rowid, id, title, content, tags, project)
                    VALUES (new.rowid, new.id, new.title, new.content, new.tags, new.project);
                END;
            """)
            try:
                conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild');")
            except Exception:
                pass
        except sqlite3.OperationalError:
            pass

        # Indices
        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation)",
            "CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project)",
            "CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type)",
            "CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON nodes(confidence)",
            "CREATE INDEX IF NOT EXISTS idx_observations_node ON observations(node_id)",
            "CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project)",
        ]:
            conn.execute(idx_sql)
    return conn


# ═══════════════════════════════════════════════════════════════
# Tool Definitions
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "create_entity",
        "description": "Create or update a knowledge node in the brain graph. Each node represents an atomic concept: a decision, component, endpoint, technology, learning, rule, or any meaningful unit of knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Unique slug identifier (e.g. 'auth-jwt-strategy', 'post-api-users'). Auto-generated from title if omitted."},
                "title": {"type": "string", "description": "Human-readable name (e.g. 'JWT Auth Strategy')"},
                "node_type": {"type": "string", "enum": list(NODE_TYPES), "description": "Type classification of the node"},
                "content": {"type": "string", "description": "Detailed content, rationale, specification, or description"},
                "tags": {"type": "string", "description": "Comma-separated tags (e.g. 'auth, security, jwt')"},
                "agent_origin": {"type": "string", "description": "Agent that created this node (e.g. '@backend', '@user')"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "relate",
        "description": "Create a directed typed edge between two nodes. Forms the neural connections of the brain graph. Use typed relations like USES, DEPENDS_ON, TESTED_BY, CONTRADICTS, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source node ID"},
                "target": {"type": "string", "description": "Target node ID"},
                "relation": {"type": "string", "enum": list(RELATIONS), "description": "Typed relation between nodes"},
                "reason": {"type": "string", "description": "Why this connection exists"},
                "weight": {"type": "number", "description": "Strength of relation 0.0-2.0 (default 1.0)"}
            },
            "required": ["source", "target", "relation"]
        }
    },
    {
        "name": "observe",
        "description": "Add a granular observation to an existing node without rewriting its content. Observations track evolution over time (e.g. 'Coverage increased to 92%', 'Added MFA support').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "ID of the node to observe"},
                "observation": {"type": "string", "description": "The observation text"},
                "observer": {"type": "string", "description": "Who made the observation (e.g. '@qa-auditor', '@user')"}
            },
            "required": ["node_id", "observation"]
        }
    },
    {
        "name": "traverse",
        "description": "Navigate the brain graph from a starting node, following edges up to N hops. Returns connected nodes and their relationships. Use for contextual retrieval like 'what tests cover this endpoint?' or 'what decisions impact this component?'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_node": {"type": "string", "description": "Node ID to start traversal from"},
                "depth": {"type": "integer", "description": "Max hops to traverse (default 2, max 5)"},
                "relation_filter": {"type": "string", "description": "Optional: only follow edges of this relation type (e.g. 'TESTED_BY')"},
                "direction": {"type": "string", "enum": ["outgoing", "incoming", "both"], "description": "Edge direction to follow (default 'both')"}
            },
            "required": ["start_node"]
        }
    },
    {
        "name": "recall_graph",
        "description": "Hybrid search: FTS5 keyword match + graph neighbor expansion. Finds relevant nodes by text and also returns their immediate graph connections for richer context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or keywords"},
                "project": {"type": "string", "description": "Project scope (defaults to current project + global)"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
                "expand_neighbors": {"type": "boolean", "description": "Also return 1-hop neighbors of matched nodes (default true)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_brain_context",
        "description": "Session bootstrap: returns a compact summary of the brain graph for the current project — key nodes by type, recent observations, active edges, and latest checkpoint. Use at session start.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            }
        }
    },
    {
        "name": "decay_audit",
        "description": "Audit node confidence levels using exponential decay based on access recency. Reports dormant nodes and optionally prunes those below threshold.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project scope (defaults to current project)"},
                "prune_threshold": {"type": "number", "description": "Confidence below which nodes are pruned (default 0.15, set 0 to disable pruning)"},
                "dry_run": {"type": "boolean", "description": "If true, only report without deleting (default true)"}
            }
        }
    },
    {
        "name": "checkpoint_brain",
        "description": "Save a session checkpoint with summary, modified files, and active task for cross-session continuity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary of what was accomplished"},
                "files_modified": {"type": "string", "description": "Comma-separated list of modified files"},
                "active_task": {"type": "string", "description": "Current active task description"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "delete_entity",
        "description": "Remove a node and all its edges and observations from the brain graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "ID of the node to delete"}
            },
            "required": ["node_id"]
        }
    },
    {
        "name": "remove_relation",
        "description": "Remove a specific edge between two nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source node ID"},
                "target": {"type": "string", "description": "Target node ID"},
                "relation": {"type": "string", "description": "Relation type to remove"}
            },
            "required": ["source", "target", "relation"]
        }
    },
    {
        "name": "merge_nodes",
        "description": "Merge two nodes into one, combining their edges, observations, and content. The target node absorbs the source.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "Node to be absorbed (will be deleted)"},
                "target_id": {"type": "string", "description": "Node that absorbs the source (will be kept)"},
                "append_content": {"type": "boolean", "description": "If true, append source content to target (default true)"}
            },
            "required": ["source_id", "target_id"]
        }
    },
    {
        "name": "list_entities",
        "description": "List nodes in the brain graph with optional filtering by type, project, or confidence threshold.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_type": {"type": "string", "description": "Filter by node type"},
                "project": {"type": "string", "description": "Project scope (defaults to current project + global)"},
                "min_confidence": {"type": "number", "description": "Minimum confidence threshold (default 0)"},
                "limit": {"type": "integer", "description": "Max results (default 30)"}
            }
        }
    },
    {
        "name": "record_learning",
        "description": "Record a project learning/insight as a node with automatic tagging and optional relation to the triggering context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lesson": {"type": "string", "description": "The learning or insight"},
                "category": {"type": "string", "description": "Category (gotcha, pattern, optimization, bug, convention)"},
                "trigger_node": {"type": "string", "description": "Optional node ID that triggered this learning"},
                "agent_name": {"type": "string", "description": "Agent that discovered this"},
                "project": {"type": "string", "description": "Project scope"}
            },
            "required": ["lesson"]
        }
    },
]


# ═══════════════════════════════════════════════════════════════
# Tool Implementations
# ═══════════════════════════════════════════════════════════════

def _touch_access(conn, node_id):
    """Update access_count and last_accessed for confidence maintenance."""
    conn.execute(
        "UPDATE nodes SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
        (now_iso(), node_id)
    )


def tool_create_entity(args):
    title = args.get("title", "").strip()
    if not title:
        return "Error: 'title' is required."

    node_id = args.get("id", "").strip() or slugify(title)
    node_type = args.get("node_type", "concept").strip().lower()
    content = args.get("content", "").strip()
    tags = args.get("tags", "").strip()
    agent_origin = args.get("agent_origin", "").strip()
    project = get_current_project(args.get("project"))

    if node_type not in NODE_TYPES:
        node_type = "concept"

    now = now_iso()
    conn = get_db()
    with db_write_lock(conn):
        existing = conn.execute("SELECT id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE nodes SET title=?, node_type=?, content=?, tags=?,
                    agent_origin=?, project=?, updated_at=?,
                    access_count = access_count + 1, last_accessed=?,
                    confidence = MIN(1.0, confidence + 0.1)
                WHERE id = ?
            """, (title, node_type, content, tags, agent_origin, project, now, now, node_id))
            return f"✓ Node '{node_id}' updated in [{project}]. Type: {node_type}"
        else:
            conn.execute("""
                INSERT INTO nodes (id, title, node_type, content, project, agent_origin,
                    confidence, access_count, last_accessed, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1.0, 1, ?, ?, ?, ?)
            """, (node_id, title, node_type, content, project, agent_origin, now, tags, now, now))
            return f"✓ Node '{node_id}' created in [{project}]. Type: {node_type}"


def tool_relate(args):
    source = args.get("source", "").strip()
    target = args.get("target", "").strip()
    relation = args.get("relation", "").strip().upper()
    reason = args.get("reason", "").strip()
    weight = float(args.get("weight", 1.0))

    if not source or not target:
        return "Error: 'source' and 'target' node IDs are required."
    if relation not in RELATIONS:
        return f"Error: Invalid relation '{relation}'. Valid: {', '.join(sorted(RELATIONS))}"

    conn = get_db()
    # Verify both nodes exist
    for nid in (source, target):
        if not conn.execute("SELECT 1 FROM nodes WHERE id = ?", (nid,)).fetchone():
            return f"Error: Node '{nid}' does not exist. Create it first with create_entity."

    now = now_iso()
    with db_write_lock(conn):
        try:
            conn.execute("""
                INSERT INTO edges (source_id, target_id, relation, reason, weight, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source, target, relation, reason, weight, now))
        except sqlite3.IntegrityError:
            conn.execute("""
                UPDATE edges SET reason=?, weight=?, created_at=?
                WHERE source_id=? AND target_id=? AND relation=?
            """, (reason, weight, now, source, target, relation))

    return f"✓ Edge created: {source} —[{relation}]→ {target}" + (f" (reason: {reason})" if reason else "")


def tool_observe(args):
    node_id = args.get("node_id", "").strip()
    observation = args.get("observation", "").strip()
    observer = args.get("observer", "").strip()

    if not node_id or not observation:
        return "Error: 'node_id' and 'observation' are required."

    conn = get_db()
    if not conn.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,)).fetchone():
        return f"Error: Node '{node_id}' does not exist."

    now = now_iso()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO observations (node_id, observation, observer, observed_at)
            VALUES (?, ?, ?, ?)
        """, (node_id, observation, observer, now))
        # Boost confidence on observation (capped at 1.0)
        conn.execute("""
            UPDATE nodes SET confidence = MIN(1.0, confidence + 0.05),
                access_count = access_count + 1, last_accessed = ?, updated_at = ?
            WHERE id = ?
        """, (now, now, node_id))

    return f"✓ Observation added to '{node_id}' by {observer or 'system'}."


def tool_traverse(args):
    start_node = args.get("start_node", "").strip()
    depth = min(int(args.get("depth", 2)), 5)
    relation_filter = args.get("relation_filter", "").strip().upper()
    direction = args.get("direction", "both").strip().lower()

    if not start_node:
        return "Error: 'start_node' is required."

    conn = get_db()
    root = conn.execute("SELECT id, title, node_type, content, confidence FROM nodes WHERE id = ?", (start_node,)).fetchone()
    if not root:
        return f"Error: Node '{start_node}' does not exist."

    _touch_access(conn, start_node)

    visited = {start_node}
    frontier = [start_node]
    result_nodes = [dict(root)]
    result_edges = []

    for hop in range(depth):
        next_frontier = []
        for nid in frontier:
            # Outgoing edges
            if direction in ("outgoing", "both"):
                sql = "SELECT source_id, target_id, relation, reason, weight FROM edges WHERE source_id = ?"
                params = [nid]
                if relation_filter and relation_filter in RELATIONS:
                    sql += " AND relation = ?"
                    params.append(relation_filter)
                for e in conn.execute(sql, params).fetchall():
                    result_edges.append(dict(e))
                    if e["target_id"] not in visited:
                        visited.add(e["target_id"])
                        next_frontier.append(e["target_id"])
                        n = conn.execute("SELECT id, title, node_type, content, confidence FROM nodes WHERE id = ?",
                                         (e["target_id"],)).fetchone()
                        if n:
                            result_nodes.append(dict(n))

            # Incoming edges
            if direction in ("incoming", "both"):
                sql = "SELECT source_id, target_id, relation, reason, weight FROM edges WHERE target_id = ?"
                params = [nid]
                if relation_filter and relation_filter in RELATIONS:
                    sql += " AND relation = ?"
                    params.append(relation_filter)
                for e in conn.execute(sql, params).fetchall():
                    result_edges.append(dict(e))
                    if e["source_id"] not in visited:
                        visited.add(e["source_id"])
                        next_frontier.append(e["source_id"])
                        n = conn.execute("SELECT id, title, node_type, content, confidence FROM nodes WHERE id = ?",
                                         (e["source_id"],)).fetchone()
                        if n:
                            result_nodes.append(dict(n))

        frontier = next_frontier
        if not frontier:
            break

    # Format output
    out = [f"### 🧠 Graph Traversal from `{start_node}` (depth={depth}, direction={direction})"]
    if relation_filter:
        out.append(f"Filter: `{relation_filter}` edges only\n")

    out.append(f"**Nodes found: {len(result_nodes)}** | **Edges found: {len(result_edges)}**\n")

    out.append("#### Nodes")
    for n in result_nodes:
        conf = f" (conf: {n['confidence']:.2f})" if n.get('confidence') is not None else ""
        marker = " ← START" if n["id"] == start_node else ""
        out.append(f"• **`{n['id']}`** [{n['node_type']}]{conf}{marker}: {n.get('title', '')}")

    if result_edges:
        out.append("\n#### Edges")
        seen_edges = set()
        for e in result_edges:
            edge_key = (e["source_id"], e["target_id"], e["relation"])
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                reason = f" — {e['reason']}" if e.get("reason") else ""
                out.append(f"• `{e['source_id']}` —[{e['relation']}]→ `{e['target_id']}`{reason}")

    return "\n".join(out)


def tool_recall_graph(args):
    query = args.get("query", "").strip()
    if not query:
        return "Error: 'query' is required."

    project = get_current_project(args.get("project"))
    limit = int(args.get("limit", 10))
    expand = args.get("expand_neighbors", True)
    if isinstance(expand, str):
        expand = expand.lower() != "false"

    conn = get_db()

    # FTS5 search
    fts_query = ' OR '.join(f'"{w}"' for w in query.split() if w)
    try:
        rows = conn.execute("""
            SELECT n.id, n.title, n.node_type, n.content, n.confidence, n.tags, n.project
            FROM nodes n
            JOIN nodes_fts f ON n.rowid = f.rowid
            WHERE nodes_fts MATCH ? AND (n.project = ? OR n.project = 'global')
            ORDER BY rank
            LIMIT ?
        """, (fts_query, project, limit)).fetchall()
    except Exception:
        # Fallback to LIKE search
        rows = conn.execute("""
            SELECT id, title, node_type, content, confidence, tags, project
            FROM nodes
            WHERE (project = ? OR project = 'global')
                AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)
            ORDER BY updated_at DESC LIMIT ?
        """, (project, f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()

    if not rows:
        return f"No nodes found matching '{query}' in [{project}]."

    # Touch access for matched nodes
    for r in rows:
        _touch_access(conn, r["id"])

    out = [f"### 🔍 Brain Recall: '{query}' [{project}]", f"**{len(rows)} node(s) found**\n"]

    neighbor_ids = set()
    for r in rows:
        conf = f" (conf: {r['confidence']:.2f})" if r['confidence'] is not None else ""
        tags = f" | tags: {r['tags']}" if r['tags'] else ""
        out.append(f"• **`{r['id']}`** [{r['node_type']}]{conf}{tags}")
        content_preview = r['content'][:200] + "..." if len(r['content']) > 200 else r['content']
        if content_preview:
            out.append(f"  └ {content_preview}")

        # Collect neighbor IDs for expansion
        if expand:
            for e in conn.execute("SELECT target_id, relation FROM edges WHERE source_id = ?", (r["id"],)).fetchall():
                neighbor_ids.add((r["id"], e["target_id"], e["relation"], "out"))
            for e in conn.execute("SELECT source_id, relation FROM edges WHERE target_id = ?", (r["id"],)).fetchall():
                neighbor_ids.add((e["source_id"], r["id"], e["relation"], "in"))

    if neighbor_ids:
        out.append(f"\n#### Connected Nodes ({len(neighbor_ids)} edge(s))")
        for src, tgt, rel, _dir in list(neighbor_ids)[:20]:
            out.append(f"• `{src}` —[{rel}]→ `{tgt}`")

    return "\n".join(out)


def tool_get_brain_context(args):
    project = get_current_project(args.get("project"))
    conn = get_db()

    # Count totals
    total_nodes = conn.execute("SELECT COUNT(*) as c FROM nodes WHERE project = ? OR project = 'global'", (project,)).fetchone()["c"]
    total_edges = conn.execute("""
        SELECT COUNT(*) as c FROM edges e
        JOIN nodes n ON e.source_id = n.id
        WHERE n.project = ? OR n.project = 'global'
    """, (project,)).fetchone()["c"]

    out = [
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║  🧠 BRAIN GRAPH CONTEXT — Project: {project:<24} ║",
        f"║  Nodes: {total_nodes:<6} | Edges: {total_edges:<6}                        ║",
        f"╚══════════════════════════════════════════════════════════════╝\n",
    ]

    # Key nodes by type (decisions, architecture, components first)
    priority_types = ["decision", "architecture", "component", "technology", "convention", "preference"]
    for ntype in priority_types:
        nodes = conn.execute("""
            SELECT id, title, confidence, updated_at FROM nodes
            WHERE (project = ? OR project = 'global') AND node_type = ?
            ORDER BY confidence DESC, updated_at DESC LIMIT 5
        """, (project, ntype)).fetchall()
        if nodes:
            out.append(f"### {ntype.upper()}S")
            for n in nodes:
                rel = format_relative_time(n["updated_at"])
                out.append(f"• **`{n['id']}`** — {n['title']} (conf: {n['confidence']:.2f}, {rel})")
            out.append("")

    # Recent observations
    obs = conn.execute("""
        SELECT o.observation, o.observer, o.observed_at, o.node_id
        FROM observations o
        JOIN nodes n ON o.node_id = n.id
        WHERE n.project = ? OR n.project = 'global'
        ORDER BY o.observed_at DESC LIMIT 5
    """, (project,)).fetchall()
    if obs:
        out.append("### RECENT OBSERVATIONS")
        for o in obs:
            rel = format_relative_time(o["observed_at"])
            out.append(f"• [{o['node_id']}] {o['observation']} (by {o['observer'] or 'system'}, {rel})")
        out.append("")

    # Recent learnings
    learnings = conn.execute("""
        SELECT id, title, content FROM nodes
        WHERE (project = ? OR project = 'global') AND node_type = 'learning'
        ORDER BY created_at DESC LIMIT 5
    """, (project,)).fetchall()
    if learnings:
        out.append("### LEARNINGS")
        for l in learnings:
            out.append(f"• **`{l['id']}`** — {l['title']}: {l['content'][:150]}")
        out.append("")

    # Latest checkpoint
    cp = conn.execute("""
        SELECT summary, files_modified, active_task, created_at FROM checkpoints
        WHERE project = ? ORDER BY id DESC LIMIT 1
    """, (project,)).fetchone()
    if cp:
        out.append("### LAST CHECKPOINT")
        out.append(f"• **Summary**: {cp['summary']}")
        if cp['files_modified']:
            out.append(f"• **Files**: {cp['files_modified']}")
        if cp['active_task']:
            out.append(f"• **Active task**: {cp['active_task']}")
        out.append(f"• **When**: {format_relative_time(cp['created_at'])}")

    # Dormant warning
    dormant = conn.execute("""
        SELECT COUNT(*) as c FROM nodes
        WHERE (project = ? OR project = 'global') AND confidence < 0.3
    """, (project,)).fetchone()["c"]
    if dormant > 0:
        out.append(f"\n⚠️ **{dormant} dormant node(s)** with low confidence. Run `decay_audit` to review.")

    return "\n".join(out)


def tool_decay_audit(args):
    project = get_current_project(args.get("project"))
    prune_threshold = float(args.get("prune_threshold", 0.15))
    dry_run = args.get("dry_run", True)
    if isinstance(dry_run, str):
        dry_run = dry_run.lower() != "false"

    conn = get_db()
    now_dt = datetime.datetime.now(datetime.timezone.utc)

    # Recalculate confidence for all project nodes
    nodes = conn.execute("""
        SELECT id, confidence, last_accessed, access_count, node_type
        FROM nodes WHERE project = ? OR project = 'global'
    """, (project,)).fetchall()

    updated = 0
    dormant = []
    pruned = []

    for n in nodes:
        last_acc = n["last_accessed"]
        if not last_acc:
            days_idle = 999
        else:
            try:
                la = datetime.datetime.fromisoformat(last_acc)
                if la.tzinfo is None:
                    la = la.replace(tzinfo=datetime.timezone.utc)
                days_idle = max(0, (now_dt - la).total_seconds() / 86400)
            except Exception:
                days_idle = 999

        # Exponential decay: c(t) = c₀ × e^(-λ × days)
        new_conf = n["confidence"] * math.exp(-DECAY_LAMBDA * days_idle)
        # Boost for high access count (popular nodes decay slower)
        if n["access_count"] > 10:
            new_conf = min(1.0, new_conf * 1.1)

        new_conf = round(max(0.0, min(1.0, new_conf)), 4)

        if abs(new_conf - n["confidence"]) > 0.005:
            conn.execute("UPDATE nodes SET confidence = ? WHERE id = ?", (new_conf, n["id"]))
            updated += 1

        if new_conf < prune_threshold and prune_threshold > 0:
            if dry_run:
                dormant.append((n["id"], n["node_type"], new_conf))
            else:
                pruned.append((n["id"], n["node_type"], new_conf))
                conn.execute("DELETE FROM nodes WHERE id = ?", (n["id"],))

    out = [f"### 🔬 Decay Audit [{project}]"]
    out.append(f"• **Nodes audited**: {len(nodes)}")
    out.append(f"• **Confidence recalculated**: {updated}")
    out.append(f"• **Decay λ**: {DECAY_LAMBDA} (50% at ~70 days idle)")

    if dormant:
        out.append(f"\n#### ⚠️ Dormant Nodes (below {prune_threshold}) — DRY RUN")
        for nid, ntype, conf in dormant[:20]:
            out.append(f"• `{nid}` [{ntype}] — confidence: {conf:.4f}")
        out.append(f"\nSet `dry_run: false` to prune these {len(dormant)} node(s).")

    if pruned:
        out.append(f"\n#### 🗑️ Pruned Nodes ({len(pruned)})")
        for nid, ntype, conf in pruned:
            out.append(f"• `{nid}` [{ntype}] — was: {conf:.4f}")

    return "\n".join(out)


def tool_checkpoint_brain(args):
    summary = args.get("summary", "").strip()
    if not summary:
        return "Error: 'summary' is required."

    files_modified = args.get("files_modified", "").strip()
    active_task = args.get("active_task", "").strip()
    project = get_current_project(args.get("project"))
    now = now_iso()

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO checkpoints (project, summary, files_modified, active_task, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (project, summary, files_modified, active_task, now))

    return f"✓ Brain checkpoint saved for [{project}]: {summary[:100]}"


def tool_delete_entity(args):
    node_id = args.get("node_id", "").strip()
    if not node_id:
        return "Error: 'node_id' is required."

    conn = get_db()
    exists = conn.execute("SELECT id, title FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if not exists:
        return f"Error: Node '{node_id}' does not exist."

    with db_write_lock(conn):
        # CASCADE handles edges and observations via FK
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

    return f"✓ Node '{node_id}' ({exists['title']}) deleted with all edges and observations."


def tool_remove_relation(args):
    source = args.get("source", "").strip()
    target = args.get("target", "").strip()
    relation = args.get("relation", "").strip().upper()

    if not source or not target or not relation:
        return "Error: 'source', 'target', and 'relation' are required."

    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            DELETE FROM edges WHERE source_id = ? AND target_id = ? AND relation = ?
        """, (source, target, relation))

    if cur.rowcount == 0:
        return f"No edge found: {source} —[{relation}]→ {target}"
    return f"✓ Edge removed: {source} —[{relation}]→ {target}"


def tool_merge_nodes(args):
    source_id = args.get("source_id", "").strip()
    target_id = args.get("target_id", "").strip()
    append_content = args.get("append_content", True)
    if isinstance(append_content, str):
        append_content = append_content.lower() != "false"

    if not source_id or not target_id:
        return "Error: 'source_id' and 'target_id' are required."
    if source_id == target_id:
        return "Error: Cannot merge a node with itself."

    conn = get_db()
    source = conn.execute("SELECT * FROM nodes WHERE id = ?", (source_id,)).fetchone()
    target = conn.execute("SELECT * FROM nodes WHERE id = ?", (target_id,)).fetchone()

    if not source:
        return f"Error: Source node '{source_id}' does not exist."
    if not target:
        return f"Error: Target node '{target_id}' does not exist."

    now = now_iso()
    with db_write_lock(conn):
        # Append content
        if append_content and source["content"]:
            new_content = target["content"] + "\n\n---\n[Merged from " + source_id + "]\n" + source["content"]
            conn.execute("UPDATE nodes SET content = ?, updated_at = ? WHERE id = ?",
                         (new_content, now, target_id))

        # Merge tags
        src_tags = set(t.strip() for t in source["tags"].split(",") if t.strip())
        tgt_tags = set(t.strip() for t in target["tags"].split(",") if t.strip())
        merged_tags = ", ".join(sorted(src_tags | tgt_tags))
        conn.execute("UPDATE nodes SET tags = ? WHERE id = ?", (merged_tags, target_id))

        # Redirect edges pointing to source → target
        for edge in conn.execute("SELECT * FROM edges WHERE source_id = ?", (source_id,)).fetchall():
            if edge["target_id"] != target_id:
                try:
                    conn.execute("INSERT OR IGNORE INTO edges (source_id, target_id, relation, reason, weight, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                 (target_id, edge["target_id"], edge["relation"], edge["reason"], edge["weight"], now))
                except Exception:
                    pass
        for edge in conn.execute("SELECT * FROM edges WHERE target_id = ?", (source_id,)).fetchall():
            if edge["source_id"] != target_id:
                try:
                    conn.execute("INSERT OR IGNORE INTO edges (source_id, target_id, relation, reason, weight, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                 (edge["source_id"], target_id, edge["relation"], edge["reason"], edge["weight"], now))
                except Exception:
                    pass

        # Move observations
        conn.execute("UPDATE observations SET node_id = ? WHERE node_id = ?", (target_id, source_id))

        # Delete source (CASCADE cleans remaining edges)
        conn.execute("DELETE FROM nodes WHERE id = ?", (source_id,))

    return f"✓ Merged '{source_id}' into '{target_id}'. All edges and observations transferred."


def tool_list_entities(args):
    project = get_current_project(args.get("project"))
    node_type = args.get("node_type", "").strip().lower()
    min_conf = float(args.get("min_confidence", 0))
    limit = int(args.get("limit", 30))

    conn = get_db()
    sql = "SELECT id, title, node_type, confidence, access_count, updated_at, tags FROM nodes WHERE (project = ? OR project = 'global')"
    params = [project]

    if node_type:
        sql += " AND node_type = ?"
        params.append(node_type)
    if min_conf > 0:
        sql += " AND confidence >= ?"
        params.append(min_conf)

    sql += " ORDER BY confidence DESC, updated_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return f"No nodes found in [{project}]" + (f" of type '{node_type}'" if node_type else "") + "."

    out = [f"### 📊 Brain Nodes [{project}]" + (f" — type: {node_type}" if node_type else "")]
    out.append(f"**{len(rows)} node(s)**\n")

    for r in rows:
        rel = format_relative_time(r["updated_at"])
        tags = f" | {r['tags']}" if r['tags'] else ""
        out.append(f"• **`{r['id']}`** [{r['node_type']}] conf:{r['confidence']:.2f} access:{r['access_count']} ({rel}){tags}")

    return "\n".join(out)


def tool_record_learning(args):
    lesson = args.get("lesson", "").strip()
    if not lesson:
        return "Error: 'lesson' is required."

    category = args.get("category", "gotcha").strip().lower()
    trigger_node = args.get("trigger_node", "").strip()
    agent_name = args.get("agent_name", "swarm").strip()
    project = get_current_project(args.get("project"))

    slug = slugify(lesson[:40])
    node_id = f"learning-{slug}-{int(time.time()) % 100000}"

    result = tool_create_entity({
        "id": node_id,
        "title": lesson[:120],
        "node_type": "learning",
        "content": lesson,
        "tags": f"learning, {category}, {agent_name}",
        "agent_origin": f"@{agent_name}",
        "project": project
    })

    if trigger_node:
        tool_relate({
            "source": node_id,
            "target": trigger_node,
            "relation": "LEARNED_FROM",
            "reason": f"Discovered by @{agent_name} while working on {trigger_node}"
        })
        result += f"\n✓ Linked to trigger node '{trigger_node}' via LEARNED_FROM."

    return result


# ═══════════════════════════════════════════════════════════════
# Handler Registry
# ═══════════════════════════════════════════════════════════════

TOOL_HANDLERS = {
    "create_entity": tool_create_entity,
    "relate": tool_relate,
    "observe": tool_observe,
    "traverse": tool_traverse,
    "recall_graph": tool_recall_graph,
    "get_brain_context": tool_get_brain_context,
    "decay_audit": tool_decay_audit,
    "checkpoint_brain": tool_checkpoint_brain,
    "delete_entity": tool_delete_entity,
    "remove_relation": tool_remove_relation,
    "merge_nodes": tool_merge_nodes,
    "list_entities": tool_list_entities,
    "record_learning": tool_record_learning,
}


# ═══════════════════════════════════════════════════════════════
# MCP JSON-RPC 2.0 Stdio Loop
# ═══════════════════════════════════════════════════════════════

def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception as e:
            sys.stderr.write(f"Invalid JSON: {e}\n")
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "brain-graph-mcp",
                        "version": "1.0.0"
                    }
                }
            }
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            handler = TOOL_HANDLERS.get(tool_name)
            if handler:
                try:
                    text_output = handler(tool_args)
                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": text_output}]
                        }
                    }
                except Exception as e:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "isError": True,
                            "content": [{"type": "text", "text": f"Error executing {tool_name}: {str(e)}"}]
                        }
                    }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Tool not found: {tool_name}"}]
                    }
                }
        else:
            if msg_id is not None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not supported: {method}"}
                }
            else:
                continue

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
