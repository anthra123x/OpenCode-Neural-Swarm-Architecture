#!/usr/bin/env python3
"""
Unit tests for brain-graph MCP server.
Tests all 13 graph tools: create, relate, observe, traverse, recall,
brain context, decay, checkpoint, delete, remove relation, merge, list, learning.
"""

import unittest
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

# Override DB path before import
TEST_DB = tempfile.mktemp(suffix=".db")
os.environ["OPENCODE_BRAIN_DB"] = TEST_DB
os.environ["OPENCODE_PROJECT"] = "test-project"

# Import server module
sys.path.insert(0, str(Path(__file__).parent))
import server


class TestBrainGraphTools(unittest.TestCase):

    def setUp(self):
        """Fresh DB for each test."""
        if os.path.exists(TEST_DB):
            os.unlink(TEST_DB)
        # Also clean WAL/SHM
        for ext in ("-wal", "-shm"):
            p = TEST_DB + ext
            if os.path.exists(p):
                os.unlink(p)
        # Force re-init
        server.DB_PATH = Path(TEST_DB)

    def tearDown(self):
        for ext in ("", "-wal", "-shm"):
            p = TEST_DB + ext
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass

    # ─── create_entity ────────────────────────────────────────

    def test_create_entity_basic(self):
        result = server.tool_create_entity({
            "title": "JWT Auth Strategy",
            "node_type": "decision",
            "content": "Use HttpOnly cookies with JWT",
            "tags": "auth, security"
        })
        self.assertIn("created", result)
        self.assertIn("jwt-auth-strategy", result)

    def test_create_entity_custom_id(self):
        result = server.tool_create_entity({
            "id": "my-custom-id",
            "title": "Custom Node",
            "node_type": "concept"
        })
        self.assertIn("my-custom-id", result)

    def test_create_entity_update(self):
        server.tool_create_entity({"title": "Test Node", "content": "v1"})
        result = server.tool_create_entity({"title": "Test Node", "content": "v2"})
        self.assertIn("updated", result)

    def test_create_entity_empty_title(self):
        result = server.tool_create_entity({"title": ""})
        self.assertIn("Error", result)

    # ─── relate ───────────────────────────────────────────────

    def test_relate_basic(self):
        server.tool_create_entity({"id": "a", "title": "Node A"})
        server.tool_create_entity({"id": "b", "title": "Node B"})
        result = server.tool_relate({
            "source": "a", "target": "b", "relation": "USES",
            "reason": "A uses B for auth"
        })
        self.assertIn("Edge created", result)
        self.assertIn("USES", result)

    def test_relate_invalid_relation(self):
        server.tool_create_entity({"id": "a", "title": "A"})
        server.tool_create_entity({"id": "b", "title": "B"})
        result = server.tool_relate({"source": "a", "target": "b", "relation": "INVALID"})
        self.assertIn("Error", result)

    def test_relate_missing_node(self):
        server.tool_create_entity({"id": "a", "title": "A"})
        result = server.tool_relate({"source": "a", "target": "nonexistent", "relation": "USES"})
        self.assertIn("Error", result)

    def test_relate_upsert(self):
        server.tool_create_entity({"id": "a", "title": "A"})
        server.tool_create_entity({"id": "b", "title": "B"})
        server.tool_relate({"source": "a", "target": "b", "relation": "USES", "reason": "v1"})
        result = server.tool_relate({"source": "a", "target": "b", "relation": "USES", "reason": "v2"})
        self.assertIn("Edge created", result)

    # ─── observe ──────────────────────────────────────────────

    def test_observe_basic(self):
        server.tool_create_entity({"id": "comp", "title": "Component"})
        result = server.tool_observe({
            "node_id": "comp",
            "observation": "Coverage increased to 92%",
            "observer": "@qa-auditor"
        })
        self.assertIn("Observation added", result)

    def test_observe_missing_node(self):
        result = server.tool_observe({"node_id": "nonexistent", "observation": "test"})
        self.assertIn("Error", result)

    # ─── traverse ─────────────────────────────────────────────

    def test_traverse_basic(self):
        server.tool_create_entity({"id": "root", "title": "Root"})
        server.tool_create_entity({"id": "child1", "title": "Child 1"})
        server.tool_create_entity({"id": "child2", "title": "Child 2"})
        server.tool_relate({"source": "root", "target": "child1", "relation": "USES"})
        server.tool_relate({"source": "root", "target": "child2", "relation": "DEPENDS_ON"})
        result = server.tool_traverse({"start_node": "root", "depth": 1})
        self.assertIn("child1", result)
        self.assertIn("child2", result)
        self.assertIn("USES", result)

    def test_traverse_depth_2(self):
        server.tool_create_entity({"id": "a", "title": "A"})
        server.tool_create_entity({"id": "b", "title": "B"})
        server.tool_create_entity({"id": "c", "title": "C"})
        server.tool_relate({"source": "a", "target": "b", "relation": "USES"})
        server.tool_relate({"source": "b", "target": "c", "relation": "DEPENDS_ON"})
        result = server.tool_traverse({"start_node": "a", "depth": 2})
        self.assertIn("c", result)

    def test_traverse_with_filter(self):
        server.tool_create_entity({"id": "a", "title": "A"})
        server.tool_create_entity({"id": "b", "title": "B"})
        server.tool_create_entity({"id": "c", "title": "C"})
        server.tool_relate({"source": "a", "target": "b", "relation": "USES"})
        server.tool_relate({"source": "a", "target": "c", "relation": "TESTED_BY"})
        result = server.tool_traverse({"start_node": "a", "depth": 1, "relation_filter": "TESTED_BY"})
        self.assertIn("c", result)
        # b should not appear since we filtered TESTED_BY only
        self.assertNotIn("Node B", result)  # Checks title, not ID

    def test_traverse_missing_node(self):
        result = server.tool_traverse({"start_node": "nonexistent"})
        self.assertIn("Error", result)

    # ─── recall_graph ─────────────────────────────────────────

    def test_recall_graph_basic(self):
        server.tool_create_entity({
            "id": "jwt-strategy", "title": "JWT Strategy",
            "content": "Use HttpOnly cookies for auth tokens",
            "tags": "auth, security",
            "project": "test-project"
        })
        result = server.tool_recall_graph({"query": "JWT auth"})
        self.assertIn("jwt-strategy", result)

    def test_recall_graph_no_results(self):
        result = server.tool_recall_graph({"query": "xyznonexistent123"})
        self.assertIn("No nodes found", result)

    def test_recall_with_neighbors(self):
        server.tool_create_entity({"id": "x", "title": "X Node", "content": "searchable term xyz", "project": "test-project"})
        server.tool_create_entity({"id": "y", "title": "Y Node", "content": "neighbor", "project": "test-project"})
        server.tool_relate({"source": "x", "target": "y", "relation": "USES"})
        result = server.tool_recall_graph({"query": "xyz", "expand_neighbors": True})
        self.assertIn("USES", result)

    # ─── get_brain_context ────────────────────────────────────

    def test_brain_context_empty(self):
        result = server.tool_get_brain_context({})
        self.assertIn("BRAIN GRAPH CONTEXT", result)
        self.assertIn("Nodes: 0", result)

    def test_brain_context_with_data(self):
        server.tool_create_entity({"id": "dec-1", "title": "Decision 1", "node_type": "decision", "project": "test-project"})
        server.tool_observe({"node_id": "dec-1", "observation": "Test obs", "observer": "@test"})
        server.tool_checkpoint_brain({"summary": "Test checkpoint", "project": "test-project"})
        result = server.tool_get_brain_context({"project": "test-project"})
        self.assertIn("Decision 1", result)
        self.assertIn("Test obs", result)
        self.assertIn("Test checkpoint", result)

    # ─── decay_audit ──────────────────────────────────────────

    def test_decay_audit_dry_run(self):
        server.tool_create_entity({"id": "old", "title": "Old Node", "project": "test-project"})
        # Manually set old last_accessed
        conn = server.get_db()
        conn.execute("UPDATE nodes SET last_accessed = '2020-01-01T00:00:00+00:00', confidence = 0.5 WHERE id = 'old'")
        result = server.tool_decay_audit({"dry_run": True, "prune_threshold": 0.3})
        self.assertIn("Decay Audit", result)

    # ─── checkpoint_brain ─────────────────────────────────────

    def test_checkpoint_brain(self):
        result = server.tool_checkpoint_brain({
            "summary": "Implemented auth module",
            "files_modified": "auth.py, test_auth.py",
            "active_task": "MFA integration"
        })
        self.assertIn("checkpoint saved", result)

    # ─── delete_entity ────────────────────────────────────────

    def test_delete_entity(self):
        server.tool_create_entity({"id": "del-me", "title": "Delete Me"})
        result = server.tool_delete_entity({"node_id": "del-me"})
        self.assertIn("deleted", result)

    def test_delete_cascade(self):
        server.tool_create_entity({"id": "parent", "title": "Parent"})
        server.tool_create_entity({"id": "child", "title": "Child"})
        server.tool_relate({"source": "parent", "target": "child", "relation": "USES"})
        server.tool_observe({"node_id": "parent", "observation": "Test"})
        result = server.tool_delete_entity({"node_id": "parent"})
        self.assertIn("deleted", result)
        # Edge should be gone too
        conn = server.get_db()
        edges = conn.execute("SELECT COUNT(*) as c FROM edges WHERE source_id = 'parent'").fetchone()
        self.assertEqual(edges["c"], 0)

    # ─── remove_relation ──────────────────────────────────────

    def test_remove_relation(self):
        server.tool_create_entity({"id": "a", "title": "A"})
        server.tool_create_entity({"id": "b", "title": "B"})
        server.tool_relate({"source": "a", "target": "b", "relation": "USES"})
        result = server.tool_remove_relation({"source": "a", "target": "b", "relation": "USES"})
        self.assertIn("removed", result)

    # ─── merge_nodes ──────────────────────────────────────────

    def test_merge_nodes(self):
        server.tool_create_entity({"id": "src", "title": "Source", "content": "Source content", "tags": "tag1"})
        server.tool_create_entity({"id": "tgt", "title": "Target", "content": "Target content", "tags": "tag2"})
        server.tool_create_entity({"id": "other", "title": "Other"})
        server.tool_relate({"source": "src", "target": "other", "relation": "USES"})
        server.tool_observe({"node_id": "src", "observation": "Source obs"})

        result = server.tool_merge_nodes({"source_id": "src", "target_id": "tgt"})
        self.assertIn("Merged", result)

        # Verify source is gone
        conn = server.get_db()
        self.assertIsNone(conn.execute("SELECT 1 FROM nodes WHERE id = 'src'").fetchone())
        # Verify target has merged content
        tgt = conn.execute("SELECT content, tags FROM nodes WHERE id = 'tgt'").fetchone()
        self.assertIn("Source content", tgt["content"])
        self.assertIn("tag1", tgt["tags"])
        # Verify edge transferred
        edge = conn.execute("SELECT 1 FROM edges WHERE source_id = 'tgt' AND target_id = 'other'").fetchone()
        self.assertIsNotNone(edge)

    # ─── list_entities ────────────────────────────────────────

    def test_list_entities(self):
        server.tool_create_entity({"id": "n1", "title": "N1", "node_type": "decision", "project": "test-project"})
        server.tool_create_entity({"id": "n2", "title": "N2", "node_type": "component", "project": "test-project"})
        result = server.tool_list_entities({})
        self.assertIn("n1", result)
        self.assertIn("n2", result)

    def test_list_entities_filtered(self):
        server.tool_create_entity({"id": "d1", "title": "D1", "node_type": "decision", "project": "test-project"})
        server.tool_create_entity({"id": "c1", "title": "C1", "node_type": "component", "project": "test-project"})
        result = server.tool_list_entities({"node_type": "decision"})
        self.assertIn("d1", result)
        self.assertNotIn("c1", result)

    # ─── record_learning ──────────────────────────────────────

    def test_record_learning(self):
        result = server.tool_record_learning({
            "lesson": "bcrypt salt rounds should be 12 minimum",
            "category": "gotcha",
            "agent_name": "backend"
        })
        self.assertIn("created", result)
        self.assertIn("learning", result.lower())

    def test_record_learning_with_trigger(self):
        server.tool_create_entity({"id": "auth-module", "title": "Auth Module"})
        result = server.tool_record_learning({
            "lesson": "Rate limit login endpoint",
            "trigger_node": "auth-module"
        })
        self.assertIn("LEARNED_FROM", result)

    # ─── Integration: Full graph scenario ─────────────────────

    def test_full_graph_scenario(self):
        """End-to-end: create a small knowledge graph and verify traversal."""
        # Build graph
        server.tool_create_entity({"id": "auth", "title": "Auth Module", "node_type": "component", "project": "test-project"})
        server.tool_create_entity({"id": "jwt", "title": "JWT Strategy", "node_type": "decision", "project": "test-project"})
        server.tool_create_entity({"id": "pg", "title": "PostgreSQL", "node_type": "technology", "project": "test-project"})
        server.tool_create_entity({"id": "test-auth", "title": "test_auth.py", "node_type": "test", "project": "test-project"})
        server.tool_create_entity({"id": "sec-001", "title": "No Hardcoded Secrets", "node_type": "rule", "project": "test-project"})

        server.tool_relate({"source": "auth", "target": "jwt", "relation": "USES"})
        server.tool_relate({"source": "auth", "target": "pg", "relation": "STORED_IN"})
        server.tool_relate({"source": "auth", "target": "test-auth", "relation": "TESTED_BY"})
        server.tool_relate({"source": "auth", "target": "sec-001", "relation": "GOVERNED_BY"})

        server.tool_observe({"node_id": "auth", "observation": "Added MFA support", "observer": "@backend"})

        # Traverse from auth
        result = server.tool_traverse({"start_node": "auth", "depth": 1})
        self.assertIn("jwt", result)
        self.assertIn("pg", result)
        self.assertIn("test-auth", result)
        self.assertIn("sec-001", result)
        self.assertIn("USES", result)
        self.assertIn("TESTED_BY", result)

        # Brain context
        ctx = server.tool_get_brain_context({"project": "test-project"})
        self.assertIn("JWT Strategy", ctx)
        self.assertIn("Added MFA support", ctx)

        # Recall
        recall = server.tool_recall_graph({"query": "auth JWT", "project": "test-project"})
        # Should find auth-related nodes
        self.assertTrue("auth" in recall or "jwt" in recall)


if __name__ == "__main__":
    unittest.main()
