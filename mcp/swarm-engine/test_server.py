#!/usr/bin/env python3
"""
Unit tests for Swarm Engine MCP Server.
Tests Sentinel auditing, live tester logic, task board, artifacts, quality gate,
and brain knowledge graph bridge.
"""

import os
import sys
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

import server

class TestSwarmEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_swarm.db"
        self.brain_db_path = Path(self.temp_dir.name) / "test_brain.db"

        # Point server DBs to temp paths
        server.DB_PATH = self.db_path
        server.BRAIN_DB_PATH = self.brain_db_path

        # Setup brain db schema for bridge testing
        conn_b = sqlite3.connect(str(self.brain_db_path))
        with conn_b:
            conn_b.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project TEXT NOT NULL,
                    agent_origin TEXT,
                    confidence REAL DEFAULT 1.0,
                    tags TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn_b.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    observation TEXT NOT NULL,
                    observer TEXT,
                    observed_at TEXT NOT NULL
                )
            """)
        conn_b.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_init_and_default_rules(self):
        conn = server.get_db()
        cur = conn.execute("SELECT count(*) as c FROM sentinel_rules")
        count = cur.fetchone()["c"]
        self.assertGreaterEqual(count, 7)

    def test_sentinel_get_rules(self):
        res = json.loads(server.handle_sentinel_get_rules({"category": "testing"}))
        self.assertIn("rules", res)
        self.assertTrue(any(r["rule_code"] == "TDD-001" for r in res["rules"]))

    def test_sentinel_audit_task_certified(self):
        args = {
            "agent_name": "backend",
            "task_title": "Implement JWT Auth Service",
            "deliverables": "Added AuthService with clean architecture. Unit tests passing with 90% coverage.",
            "files_modified": "auth.py, tests/test_auth.py",
            "test_results": "12 passed, 0 failed, 90% coverage",
            "project": "test-proj"
        }
        res = json.loads(server.handle_sentinel_audit_task(args))
        self.assertEqual(res["verdict"], "CERTIFIED")
        self.assertEqual(res["score"], 100)
        self.assertEqual(res["violations_count"], 0)

    def test_sentinel_audit_task_rejected_missing_tests(self):
        args = {
            "agent_name": "backend",
            "task_title": "Implement Payment Endpoint",
            "deliverables": "Added Stripe webhook handler without any automated specs.",
            "files_modified": "payment.py",
            "test_results": "",
            "project": "test-proj"
        }
        res = json.loads(server.handle_sentinel_audit_task(args))
        self.assertEqual(res["verdict"], "REJECTED")
        self.assertLess(res["score"], 80)
        self.assertTrue(any(v["rule_code"] == "TDD-001" for v in res["violations"]))

    def test_sentinel_record_and_resolve_violation(self):
        rec_args = {
            "rule_code": "SEC-001",
            "agent_name": "backend",
            "details": "Hardcoded secret key in config file",
            "severity": "critical",
            "project": "test-proj"
        }
        rec_res = json.loads(server.handle_sentinel_record_violation(rec_args))
        viol_id = rec_res["violation_id"]
        self.assertIsNotNone(viol_id)

        # Check compliance
        comp = json.loads(server.handle_sentinel_verify_compliance({"project": "test-proj"}))
        self.assertFalse(comp["compliant"])
        self.assertEqual(comp["open_violations_count"], 1)

        # Resolve
        resol_res = json.loads(server.handle_sentinel_resolve_violation({
            "violation_id": viol_id,
            "resolution_notes": "Moved secret to .env and updated config parser"
        }))
        self.assertEqual(resol_res["status"], "resolved")

        # Re-check compliance
        comp_after = json.loads(server.handle_sentinel_verify_compliance({"project": "test-proj"}))
        self.assertTrue(comp_after["compliant"])
        self.assertEqual(comp_after["open_violations_count"], 0)

    def test_sentinel_compliance_report(self):
        # Audit a task first
        server.handle_sentinel_audit_task({
            "agent_name": "frontend",
            "task_title": "Build User Profile Modal",
            "deliverables": "Created accessible modal with OKLCH tokens and spring animations.",
            "project": "test-proj"
        })
        rep = json.loads(server.handle_sentinel_get_compliance_report({"project": "test-proj", "days": 1}))
        self.assertEqual(rep["total_audits"], 1)
        self.assertEqual(rep["certified_audits"], 1)
        self.assertEqual(rep["pass_rate_percent"], 100.0)

    def test_swarm_tasks_lifecycle(self):
        # Post task
        post_res = json.loads(server.handle_swarm_post_task({
            "title": "Migrate database schema",
            "description": "Add user_roles table",
            "assigned_to": "backend",
            "priority": "high",
            "project": "test-proj"
        }))
        self.assertEqual(post_res["status"], "created")
        task_id = post_res["task_id"]

        # List tasks
        list_res = json.loads(server.handle_swarm_list_tasks({"project": "test-proj"}))
        self.assertEqual(list_res["count"], 1)
        self.assertEqual(list_res["tasks"][0]["title"], "Migrate database schema")

        # Update task
        up_res = json.loads(server.handle_swarm_update_task({
            "task_id": task_id,
            "status": "done",
            "notes": "Migration applied cleanly."
        }))
        self.assertEqual(up_res["status"], "updated")
        self.assertEqual(up_res["new_status"], "done")

    def test_swarm_artifacts_share_and_get(self):
        share_res = json.loads(server.handle_swarm_share_artifact({
            "artifact_key": "api_v1_spec",
            "title": "API Spec v1",
            "content": "# OpenAPI Spec\n/users: get",
            "creator": "backend",
            "project": "test-proj"
        }))
        self.assertEqual(share_res["status"], "shared")

        get_res = json.loads(server.handle_swarm_get_artifact({
            "artifact_key": "api_v1_spec",
            "project": "test-proj"
        }))
        self.assertTrue(get_res["found"])
        self.assertEqual(get_res["artifact"]["title"], "API Spec v1")

    def test_compatibility_aliases(self):
        # team_post_task alias
        handler_post = server.TOOL_HANDLERS["team_post_task"]
        post_res = json.loads(handler_post({
            "title": "Aliased task test",
            "project": "alias-proj"
        }))
        self.assertEqual(post_res["status"], "created")

        # team_share_artifact alias
        handler_art = server.TOOL_HANDLERS["team_share_artifact"]
        art_res = json.loads(handler_art({
            "artifact_key": "alias_art",
            "content": "some content",
            "project": "alias-proj"
        }))
        self.assertEqual(art_res["status"], "shared")

    def test_parse_test_output(self):
        # Pytest output
        pytest_out = "===== 15 passed, 2 skipped in 0.45s =====\nTOTAL 120 12 90%"
        total, p, f, s, cov = server.parse_test_output(pytest_out, "pytest")
        self.assertEqual(p, 15)
        self.assertEqual(s, 2)
        self.assertEqual(f, 0)
        self.assertEqual(cov, 90.0)

        # Unittest output
        unittest_out = "Ran 8 tests in 0.05s\n\nOK"
        total, p, f, s, cov = server.parse_test_output(unittest_out, "unittest")
        self.assertEqual(p, 8)
        self.assertEqual(f, 0)

    def test_component_check_syntax(self):
        valid_py = Path(self.temp_dir.name) / "valid.py"
        valid_py.write_text("x = 42\ndef hello(): return x\n")
        res = json.loads(server.handle_tester_verify_component({
            "file_path": str(valid_py),
            "check_type": "syntax",
            "project": "test-proj"
        }))
        self.assertEqual(res["status"], "PASS")

        invalid_py = Path(self.temp_dir.name) / "invalid.py"
        invalid_py.write_text("def broken(:\n")
        res_inv = json.loads(server.handle_tester_verify_component({
            "file_path": str(invalid_py),
            "check_type": "syntax",
            "project": "test-proj"
        }))
        self.assertEqual(res_inv["status"], "FAIL")

    def test_swarm_gate_check_flow(self):
        # Initial check: no tests run yet -> GATE_BLOCKED
        gate_init = json.loads(server.handle_swarm_gate_check({"project": "gate-proj"}))
        self.assertFalse(gate_init["passed"])
        self.assertEqual(gate_init["verdict"], "GATE_BLOCKED")

        # Record a successful test run
        conn = server.get_db()
        now = "2026-10-19T22:00:00Z"
        with conn:
            conn.execute("""
                INSERT INTO tester_runs (project, runner, status, total_tests, passed, failed, skipped, coverage_percent, created_at)
                VALUES ('gate-proj', 'pytest', 'PASS', 10, 10, 0, 0, 92.5, ?)
            """, (now,))

        # Post and complete a task
        task_res = json.loads(server.handle_swarm_post_task({
            "title": "Gate Feature",
            "project": "gate-proj"
        }))
        task_id = task_res["task_id"]
        server.handle_swarm_update_task({"task_id": task_id, "status": "done"})

        # Check gate again -> GATE_PASSED
        gate_ok = json.loads(server.handle_swarm_gate_check({"project": "gate-proj", "task_id": task_id}))
        self.assertTrue(gate_ok["passed"])
        self.assertEqual(gate_ok["verdict"], "GATE_PASSED")

    def test_brain_bridge_observation_and_learning(self):
        # Create a node in brain db
        conn_b = sqlite3.connect(str(self.brain_db_path))
        with conn_b:
            conn_b.execute("""
                INSERT INTO nodes (id, title, node_type, content, project, created_at, updated_at)
                VALUES ('task-bridge-test', 'Bridge Task', 'task', 'testing bridge', 'bridge-proj', '2026-10-19', '2026-10-19')
            """)
        conn_b.close()

        # Bridge observation
        server.bridge_to_brain_observation("bridge-proj", "task-bridge-test", "QA Audit signoff passed")
        conn_b = sqlite3.connect(str(self.brain_db_path))
        cur = conn_b.execute("SELECT * FROM observations WHERE node_id = 'task-bridge-test'")
        row = cur.fetchone()
        self.assertIsNotNone(row)

        # Bridge learning
        server.bridge_to_brain_learning("bridge-proj", "Always use WAL mode in sqlite", "lock contention", "PRAGMA journal_mode=WAL")
        cur_l = conn_b.execute("SELECT * FROM nodes WHERE node_type = 'learning'")
        row_l = cur_l.fetchone()
        self.assertIsNotNone(row_l)
        conn_b.close()


if __name__ == "__main__":
    unittest.main()
