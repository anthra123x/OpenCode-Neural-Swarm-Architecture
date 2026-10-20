#!/usr/bin/env python3
"""
Migration script: context-memory (v1) → brain-graph (v2)
Converts flat key-value memories into graph nodes with auto-typed classification
and preserves all existing data.

Usage:
    python migrate.py [--dry-run]
"""

import sqlite3
import os
import sys
import re
import datetime
from pathlib import Path

# Source and target paths
SRC_DB = Path(os.environ.get("OPENCODE_MEMORY_DB",
    Path.home() / ".opencode" / "memory" / "context_memory.db"))
DST_DB = Path(os.environ.get("OPENCODE_BRAIN_DB",
    Path.home() / ".opencode" / "brain" / "brain.db"))

# Category → node_type mapping
CATEGORY_MAP = {
    "architecture": "architecture",
    "preference": "preference",
    "decision": "decision",
    "convention": "convention",
    "snippet": "snippet",
    "bugfix": "bug",
    "general": "concept",
    "learning": "learning",
}

# Key pattern → node_type heuristics
KEY_PATTERNS = [
    (r"learning:", "learning"),
    (r"tech-stack", "technology"),
    (r"api|endpoint|route", "endpoint"),
    (r"test|spec|coverage", "test"),
    (r"rule|policy|sec-", "rule"),
    (r"component|ui|widget", "component"),
    (r"migration|schema|table", "architecture"),
    (r"turn-log-", "checkpoint"),
]


def classify_node_type(key, category, content):
    """Infer node_type from key patterns and category."""
    # First check key patterns
    for pattern, ntype in KEY_PATTERNS:
        if re.search(pattern, key, re.IGNORECASE):
            return ntype
    # Fall back to category mapping
    return CATEGORY_MAP.get(category, "concept")


def slugify(text, max_len=60):
    s = re.sub(r'[^a-z0-9]+', '-', text.lower().strip()).strip('-')
    return s[:max_len] if s else "node"


def migrate(dry_run=False):
    if not SRC_DB.exists():
        print(f"⚠️  Source database not found: {SRC_DB}")
        print("   Nothing to migrate.")
        return

    print(f"📂 Source: {SRC_DB}")
    print(f"📂 Target: {DST_DB}")
    print(f"{'🔍 DRY RUN' if dry_run else '🚀 LIVE MIGRATION'}\n")

    # Connect to source
    src_conn = sqlite3.connect(str(SRC_DB))
    src_conn.row_factory = sqlite3.Row

    # Read all memories
    try:
        memories = src_conn.execute("""
            SELECT key, category, content, tags, project, created_at, updated_at
            FROM memories ORDER BY id
        """).fetchall()
    except Exception as e:
        print(f"Error reading source DB: {e}")
        return

    print(f"Found {len(memories)} memories to migrate.\n")

    if not memories:
        print("Nothing to migrate.")
        return

    if dry_run:
        # Just show what would happen
        type_counts = {}
        for m in memories:
            ntype = classify_node_type(m["key"], m["category"], m["content"])
            type_counts[ntype] = type_counts.get(ntype, 0) + 1

        print("Classification breakdown:")
        for ntype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  • {ntype}: {count} node(s)")

        print(f"\nTotal: {len(memories)} memories → {len(memories)} nodes")
        print("\nRun without --dry-run to execute migration.")
        return

    # Initialize target DB (importing from server.py)
    DST_DB.parent.mkdir(parents=True, exist_ok=True)

    # We'll initialize the schema directly
    dst_conn = sqlite3.connect(str(DST_DB), timeout=30.0)
    dst_conn.row_factory = sqlite3.Row
    dst_conn.execute("PRAGMA journal_mode = WAL;")
    dst_conn.execute("PRAGMA busy_timeout = 30000;")
    dst_conn.execute("PRAGMA synchronous = NORMAL;")
    dst_conn.execute("PRAGMA foreign_keys = ON;")

    # Read and execute schema
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        schema_sql = schema_path.read_text()
        # Execute each statement separately (skip PRAGMAs already set)
        for stmt in schema_sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.upper().startswith("PRAGMA"):
                try:
                    dst_conn.execute(stmt + ";")
                except Exception:
                    pass
    else:
        print(f"⚠️  Schema file not found at {schema_path}")
        print("   Please run the brain-graph server once first to initialize the DB.")
        return

    migrated = 0
    skipped = 0
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for m in memories:
        key = m["key"]
        node_id = slugify(key)
        node_type = classify_node_type(key, m["category"], m["content"])

        # Skip if already exists
        existing = dst_conn.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if existing:
            skipped += 1
            continue

        try:
            dst_conn.execute("""
                INSERT INTO nodes (id, title, node_type, content, project, agent_origin,
                    confidence, access_count, last_accessed, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node_id,
                key,  # Use original key as title
                node_type,
                m["content"],
                m["project"] or "global",
                "migration-v1",
                0.8,  # Migrated nodes start at slightly lower confidence
                1,
                now,
                m["tags"] or "",
                m["created_at"] or now,
                m["updated_at"] or now,
            ))
            migrated += 1
        except Exception as e:
            print(f"  ⚠️  Failed to migrate '{key}': {e}")
            skipped += 1

    dst_conn.commit()

    # Rebuild FTS
    try:
        dst_conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild');")
    except Exception:
        pass

    dst_conn.close()
    src_conn.close()

    print(f"✅ Migration complete!")
    print(f"   • Migrated: {migrated} node(s)")
    print(f"   • Skipped:  {skipped} (duplicates or errors)")
    print(f"   • Target:   {DST_DB}")
    print(f"\n💡 Old database preserved at: {SRC_DB}")
    print(f"   You can delete it after verifying the migration.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    migrate(dry_run=dry_run)
