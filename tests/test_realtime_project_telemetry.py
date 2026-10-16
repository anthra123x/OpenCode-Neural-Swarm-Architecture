#!/usr/bin/env python3
"""
Test Suite for Real-Time Project Telemetry & Cross-Session Observability
Validates:
1. /api/projects lists all active projects with task and agent counts.
2. /api/status, /api/tasks, /api/feed, /api/stream accept and filter by ?project=.
3. Auto-registration of orchestrator session and cleanup of stale ghost agents.
4. Read-only invariant (POST returns 405).
"""

import unittest
import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://127.0.0.1:4040"

def fetch_json(endpoint):
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, headers={"Host": "127.0.0.1", "User-Agent": "Telemetry-Test"})
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return json.loads(resp.read().decode("utf-8"))

class TestRealtimeProjectTelemetry(unittest.TestCase):
    def test_01_api_projects_list(self):
        data = fetch_json("/api/projects")
        self.assertIn("projects", data)
        self.assertIn("current", data)
        self.assertIn("default", data)
        projs = [p["name"] for p in data["projects"]]
        self.assertIn("enterprise-event-gateway", projs)
        self.assertIn("omicron", projs)
        # Verify tasks count is present
        e_proj = next(p for p in data["projects"] if p["name"] == "enterprise-event-gateway")
        self.assertGreaterEqual(e_proj["tasks"], 15)

    def test_02_tasks_by_project_query(self):
        # Query enterprise-event-gateway
        data_e = fetch_json("/api/tasks?project=enterprise-event-gateway")
        self.assertEqual(data_e["project"], "enterprise-event-gateway")
        self.assertGreaterEqual(len(data_e["tasks"]), 15)

        # Query omicron
        data_o = fetch_json("/api/tasks?project=omicron")
        self.assertEqual(data_o["project"], "omicron")
        self.assertIsInstance(data_o["tasks"], list)

    def test_03_status_and_orchestrator_presence(self):
        data = fetch_json("/api/status?project=omicron")
        self.assertEqual(data["project"], "omicron")
        agent_names = [a["agent_name"] for a in data["agents"]]
        self.assertIn("orchestrator", agent_names)
        
        # Verify that orchestrator is in idle/ready state and has relative time
        orch = next(a for a in data["agents"] if a["agent_name"] == "orchestrator")
        self.assertEqual(orch["status"], "idle")
        self.assertTrue(orch["relative_time"])

        # Verify no stale working agents older than 180s remain in working state
        for a in data["agents"]:
            self.assertNotEqual(a.get("status"), "working", f"Agent @{a['agent_name']} should not be stuck in working state")

    def test_04_read_only_mode_post_rejection(self):
        url = f"{BASE_URL}/api/tasks"
        req = urllib.request.Request(
            url,
            data=json.dumps({"title": "Disallowed Task"}).encode("utf-8"),
            headers={"Host": "127.0.0.1", "Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                self.fail(f"Expected 405 Method Not Allowed, got {resp.status}")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 405)

    def test_05_sse_stream_project_filtering(self):
        url = f"{BASE_URL}/api/stream?project=enterprise-event-gateway"
        req = urllib.request.Request(url, headers={"Host": "127.0.0.1"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            # First line is data: ...
            line1 = resp.readline().decode("utf-8")
            line2 = resp.readline().decode("utf-8")
            data_line = line1 if line1.startswith("data:") else line2
            self.assertTrue(data_line.startswith("data:"), f"Expected data: prefix, got {data_line}")
            payload = json.loads(data_line[5:].strip())
            self.assertEqual(payload["project"], "enterprise-event-gateway")
            self.assertGreaterEqual(len(payload["tasks"]), 15)

if __name__ == "__main__":
    unittest.main()
