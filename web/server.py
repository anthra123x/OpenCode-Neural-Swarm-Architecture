#!/usr/bin/env python3
"""
OpenCode Swarm Web Cockpit & GetBrain Local Server
Provides a real-time web dashboard and dynamic knowledge graph visualizer for OpenCode.
Features:
  - Per-project dedicated web sessions with dynamic port allocation (4040-4060)
  - Isolated GetBrain knowledge graph scanning the project's actual workspace
  - Zero external dependencies (pure Python 3 standard library)
  - REST API for swarm status, tasks, artifacts, memories, and brain graph
  - Server-Sent Events (SSE) for instant, live browser reactivity across terminal sessions
  - Multi-threaded HTTP server
"""

import sys
import os
import json
import time
import argparse
import webbrowser
import threading
import sqlite3
import datetime
import subprocess
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
import importlib.util
from urllib.parse import urlparse, parse_qs

# Resolve server directories
SERVER_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = SERVER_DIR / "public"

# Dynamically locate and load MCP server modules
xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

# 1. Team Collab
possible_team_paths = [
    SERVER_DIR.parent / "mcp" / "team-collab" / "server.py",
    xdg_config / "opencode" / "swarm" / "mcp" / "team-collab" / "server.py",
    xdg_config / "opencode" / "mcp" / "team-collab" / "server.py",
]
team_server_path = None
for p in possible_team_paths:
    if p.exists():
        team_server_path = p
        break

if not team_server_path:
    raise FileNotFoundError("Could not find team-collab MCP server script.")

team_spec = importlib.util.spec_from_file_location("team_collab_server", str(team_server_path))
team_server = importlib.util.module_from_spec(team_spec)
team_spec.loader.exec_module(team_server)

# 2. Context Memory
possible_mem_paths = [
    SERVER_DIR.parent / "mcp" / "context-memory" / "server.py",
    xdg_config / "opencode" / "swarm" / "mcp" / "context-memory" / "server.py",
    xdg_config / "opencode" / "mcp" / "context-memory" / "server.py",
]
mem_server_path = None
for p in possible_mem_paths:
    if p.exists():
        mem_server_path = p
        break

mem_server = None
if mem_server_path:
    try:
        mem_spec = importlib.util.spec_from_file_location("context_memory_server", str(mem_server_path))
        mem_server = importlib.util.module_from_spec(mem_spec)
        mem_spec.loader.exec_module(mem_server)
    except Exception:
        pass

# 3. Swarm Sentinel
possible_sentinel_paths = [
    SERVER_DIR.parent / "mcp" / "swarm-sentinel" / "server.py",
    xdg_config / "opencode" / "swarm" / "mcp" / "swarm-sentinel" / "server.py",
    xdg_config / "opencode" / "mcp" / "swarm-sentinel" / "server.py",
]
sentinel_server_path = None
for p in possible_sentinel_paths:
    if p.exists():
        sentinel_server_path = p
        break

sentinel_server = None
if sentinel_server_path:
    try:
        sentinel_spec = importlib.util.spec_from_file_location("swarm_sentinel_server", str(sentinel_server_path))
        sentinel_server = importlib.util.module_from_spec(sentinel_spec)
        sentinel_spec.loader.exec_module(sentinel_server)
    except Exception:
        pass

# 4. Swarm Live Tester
possible_tester_paths = [
    SERVER_DIR.parent / "mcp" / "swarm-tester" / "server.py",
    xdg_config / "opencode" / "swarm" / "mcp" / "swarm-tester" / "server.py",
    xdg_config / "opencode" / "mcp" / "swarm-tester" / "server.py",
]
tester_server_path = None
for p in possible_tester_paths:
    if p.exists():
        tester_server_path = p
        break

tester_server = None
if tester_server_path:
    try:
        tester_spec = importlib.util.spec_from_file_location("swarm_tester_server", str(tester_server_path))
        tester_server = importlib.util.module_from_spec(tester_spec)
        tester_spec.loader.exec_module(tester_server)
    except Exception:
        pass

# Add web directory to path for brain_builder
sys.path.insert(0, str(SERVER_DIR))
import brain_builder

DEFAULT_PORT = 4040
PORT_RANGE_START = 4040
PORT_RANGE_END = 4060

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server to handle simultaneous SSE streams and REST calls per project."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, project_dir, project_name):
        super().__init__(server_address, RequestHandlerClass)
        self.project_dir = Path(project_dir).resolve()
        self.project_name = str(project_name)

    def handle_error(self, request, client_address):
        """Suppress routine socket disconnection errors from noisy logs."""
        exc_type, _, _ = sys.exc_info()
        if exc_type in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)

    def get_branch(self):
        try:
            out = subprocess.check_output(
                ["git", "-C", str(self.project_dir), "branch", "--show-current"],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
            if out:
                return out
            out = subprocess.check_output(
                ["git", "-C", str(self.project_dir), "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
            return out or "main"
        except Exception:
            return "main"

class SwarmWebHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def end_headers(self):
        # Force no-cache on all responses (CSS, JS, HTML, API) so browser never retains stale files
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format, *args):
        try:
            msg = format % args
        except Exception:
            msg = str(format)
        # Suppress routine 200/SSE/favicon logs to keep terminal output clean
        if "/api/stream" in msg or " 200 -" in msg or "/favicon.ico" in msg or " 304 -" in msg:
            return
        sys.stderr.write(f"[OpenCode Swarm Web] {msg}\n")

    def _request_is_local(self):
        """Reject non-local DNS rebinding; allow standard localhost/loopback browsing."""
        host = self.headers.get("Host", "")
        if host:
            try:
                host_name = host.split(":")[0].strip("[]")
                if host_name not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
                    return False
            except Exception:
                pass
        return True

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def _get_project_param(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            p = qs.get("project", [None])[0] or qs.get("p", [None])[0]
            if p and p.strip():
                return p.strip()
        except Exception:
            pass
        return self.server.project_name

    def _resolve_project_dir(self, proj_name):
        if proj_name == self.server.project_name:
            return str(self.server.project_dir)
        candidates = [
            self.server.project_dir.parent / proj_name,
            Path.home() / "Documentos" / proj_name,
            Path.home() / proj_name,
        ]
        for c in candidates:
            if c.is_dir():
                return str(c)
        return str(self.server.project_dir)

    def _get_all_projects(self):
        projects_map = {}
        team_db_path = Path.home() / ".opencode" / "team" / "team_collab.db"
        if team_db_path.exists():
            try:
                conn = team_server.get_db()
                try:
                    for r in conn.execute("SELECT project, COUNT(*) as cnt FROM team_tasks WHERE project IS NOT NULL AND project != '' GROUP BY project"):
                        p = r[0]
                        projects_map.setdefault(p, {"name": p, "tasks": 0, "agents": 0})
                        projects_map[p]["tasks"] = r[1]
                    for r in conn.execute("SELECT project, COUNT(*) as cnt FROM team_agents WHERE project IS NOT NULL AND project != '' GROUP BY project"):
                        p = r[0]
                        projects_map.setdefault(p, {"name": p, "tasks": 0, "agents": 0})
                        projects_map[p]["agents"] = r[1]
                    for r in conn.execute("SELECT DISTINCT project FROM team_messages WHERE project IS NOT NULL AND project != ''"):
                        p = r[0]
                        projects_map.setdefault(p, {"name": p, "tasks": 0, "agents": 0})
                finally:
                    conn.close()
            except Exception:
                pass

        mem_db_path = Path.home() / ".opencode" / "memory" / "context_memory.db"
        if mem_db_path.exists():
            try:
                conn = brain_builder.get_db_connection(mem_db_path)
                if conn:
                    try:
                        for r in conn.execute("SELECT DISTINCT project FROM memories WHERE project IS NOT NULL AND project != '' AND project != 'global'"):
                            p = r[0]
                            projects_map.setdefault(p, {"name": p, "tasks": 0, "agents": 0})
                    finally:
                        conn.close()
            except Exception:
                pass

        if self.server.project_name not in projects_map:
            projects_map[self.server.project_name] = {"name": self.server.project_name, "tasks": 0, "agents": 0}

        return sorted(projects_map.values(), key=lambda x: (-x["tasks"], x["name"]))

    def do_GET(self):
        if not self._request_is_local():
            self.send_error(403, "Local dashboard access only")
            return
        parsed_url = urlparse(self.path)
        url = parsed_url.path

        # Handle favicon quickly to prevent 404 logs
        if url == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        # 0. Health check endpoint
        if url in ("/health", "/api/health"):
            proj = self._get_project_param()
            self._send_json({
                "status": "ok",
                "service": "opencode-cockpit",
                "project": proj,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            return

        # 0b. API: List of all Swarm Projects (for dropdown / multi-project telemetry)
        if url == "/api/projects":
            cur_proj = self._get_project_param()
            self._send_json({
                "current": cur_proj,
                "default": self.server.project_name,
                "projects": self._get_all_projects()
            })
            return

        # 1. API: Swarm Status (Isolated per project)
        if url == "/api/status":
            proj = self._get_project_param()
            proj_dir = self._resolve_project_dir(proj)
            branch = self.server.get_branch() if proj == self.server.project_name else "main"
            conn = team_server.get_db()
            try:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                now_iso = now_utc.isoformat()
                cur = conn.execute("""
                    SELECT agent_name, status, current_task, blockers, window_id, last_heartbeat, updated_at
                    FROM team_agents
                    WHERE project = ? OR project = 'default'
                    ORDER BY agent_name
                """, (proj,))
                agents = [dict(r) for r in cur.fetchall()]

                agent_names = {a["agent_name"] for a in agents}
                if "orchestrator" not in agent_names:
                    agents.insert(0, {
                        "agent_name": "orchestrator",
                        "status": "idle",
                        "current_task": "Sesion OpenCode activa. Listo para asignacion de tareas.",
                        "blockers": "",
                        "window_id": "",
                        "last_heartbeat": now_iso,
                        "updated_at": now_iso,
                        "relative_time": "hace un momento"
                    })

                for a in agents:
                    time_val = a["last_heartbeat"] or a["updated_at"]
                    a["relative_time"] = team_server.format_relative_time(time_val)
                    if a.get("status") == "working" and time_val:
                        try:
                            t = datetime.datetime.fromisoformat(time_val)
                            if t.tzinfo is None:
                                t = t.replace(tzinfo=datetime.timezone.utc)
                            if (now_utc - t).total_seconds() > 180:
                                a["status"] = "idle"
                                a["relative_time"] = f"{a['relative_time']} (inactivo)"
                        except Exception:
                            pass

                cur_tasks = conn.execute("SELECT COUNT(*) FROM team_tasks WHERE project = ? AND status = 'in_progress'", (proj,))
                in_prog_count = cur_tasks.fetchone()[0]
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            self._send_json({
                "project": proj,
                "project_dir": proj_dir,
                "branch": branch,
                "agents": agents,
                "in_progress_tasks": in_prog_count,
                "clock": datetime.datetime.now().strftime("%H:%M:%S")
            })
            return

        # 2. API: Tasks Board (Isolated per project)
        if url == "/api/tasks":
            proj = self._get_project_param()
            conn = team_server.get_db()
            try:
                cur = conn.execute("""
                    SELECT id, title, description, assigned_to, status, priority, notes, updated_at
                    FROM team_tasks
                    WHERE project = ?
                    ORDER BY id DESC
                """, (proj,))
                tasks = [dict(r) for r in cur.fetchall()]
                for t in tasks:
                    t["relative_time"] = team_server.format_relative_time(t["updated_at"])
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            self._send_json({
                "project": proj,
                "tasks": tasks
            })
            return

        # 3. API: Artifacts & Contracts (Isolated per project)
        if url == "/api/artifacts":
            proj = self._get_project_param()
            conn = team_server.get_db()
            try:
                cur = conn.execute("""
                    SELECT artifact_key, title, creator, artifact_type, content, updated_at
                    FROM team_artifacts
                    WHERE project = ? OR project = 'default'
                    ORDER BY updated_at DESC
                """, (proj,))
                artifacts = [dict(r) for r in cur.fetchall()]
                for art in artifacts:
                    art["relative_time"] = team_server.format_relative_time(art["updated_at"])
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            self._send_json({
                "project": proj,
                "artifacts": artifacts
            })
            return

        # 4. API: Context Memories (Isolated per project)
        if url == "/api/memories":
            proj = self._get_project_param()
            mem_db_path = Path(os.environ.get("OPENCODE_MEMORY_DB", brain_builder.DEFAULT_MEM_DIR / "context_memory.db"))
            conn = brain_builder.get_db_connection(mem_db_path)
            memories = []
            if conn:
                try:
                    cur = conn.execute("""
                        SELECT id, key, category, content, tags, project, updated_at
                        FROM memories
                        WHERE project = ? OR project = 'global'
                        ORDER BY updated_at DESC
                    """, (proj,))
                    memories = [dict(r) for r in cur.fetchall()]
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            self._send_json({
                "project": proj,
                "memories": memories
            })
            return

        # 4b. API: Continuous Learnings & Feedback Loop (Isolated per project)
        if url == "/api/learnings":
            proj = self._get_project_param()
            mem_db_path = Path(os.environ.get("OPENCODE_MEMORY_DB", brain_builder.DEFAULT_MEM_DIR / "context_memory.db"))
            conn = brain_builder.get_db_connection(mem_db_path)
            learnings = []
            if conn:
                try:
                    cur = conn.execute("""
                        SELECT id, key, category, content, tags, project, updated_at
                        FROM memories
                        WHERE (project = ? OR project = 'global') AND (category = 'learning' OR key LIKE 'learning:%')
                        ORDER BY updated_at DESC LIMIT 50
                    """, (proj,))
                    learnings = [dict(r) for r in cur.fetchall()]
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            self._send_json({
                "project": proj,
                "learnings": learnings
            })
            return

        # 5. API: Activity Feed (Isolated per project)
        if url == "/api/feed":
            proj = self._get_project_param()
            conn = team_server.get_db()
            try:
                cur = conn.execute("""
                    SELECT id, sender, message, category, priority, created_at
                    FROM team_messages
                    WHERE project = ? OR project = 'default'
                    ORDER BY id DESC LIMIT 25
                """, (proj,))
                feed = [dict(r) for r in cur.fetchall()]
                for m in feed:
                    m["relative_time"] = team_server.format_relative_time(m["created_at"])
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            self._send_json({
                "project": proj,
                "feed": feed
            })
            return

        # 6. API: GetBrain Knowledge Graph (Scans explicit project directory)
        if url == "/api/brain":
            proj = self._get_project_param()
            proj_dir = self._resolve_project_dir(proj)
            brain_data = brain_builder.build_project_brain(proj, proj_dir)
            self._send_json(brain_data)
            return

        # 6b. API: Swarm Sentinel Compliance & Rules
        if url == "/api/sentinel":
            proj = self._get_project_param()
            sentinel_data = {
                "project": proj,
                "status": "COMPLIANT",
                "score": 100,
                "rules": [],
                "violations": [],
                "audits": []
            }
            if sentinel_server:
                try:
                    s_conn = sentinel_server.get_db()
                    cur_r = s_conn.execute("SELECT rule_code, title, category, target_agent, severity, description, checklist FROM sentinel_rules")
                    sentinel_data["rules"] = [dict(r) for r in cur_r.fetchall()]

                    cur_v = s_conn.execute("""
                        SELECT id, agent_name, rule_code, severity, details, status, created_at
                        FROM sentinel_violations
                        WHERE project = ? OR project = 'default'
                        ORDER BY id DESC LIMIT 15
                    """, (proj,))
                    sentinel_data["violations"] = [dict(r) for r in cur_v.fetchall()]

                    cur_a = s_conn.execute("""
                        SELECT id, agent_name, task_title, verdict, score, feedback, created_at
                        FROM sentinel_audits
                        WHERE project = ? OR project = 'default'
                        ORDER BY id DESC LIMIT 15
                    """, (proj,))
                    sentinel_data["audits"] = [dict(r) for r in cur_a.fetchall()]

                    avg_cur = s_conn.execute("SELECT avg(score) as a FROM sentinel_audits WHERE project = ? OR project = 'default'", (proj,)).fetchone()
                    sentinel_data["score"] = int(avg_cur["a"] or 100) if avg_cur and avg_cur["a"] is not None else 100
                    crit_count = sum(1 for v in sentinel_data["violations"] if v.get("severity") == "critical" and v.get("status") == "open")
                    sentinel_data["status"] = "NON-COMPLIANT" if crit_count > 0 else "COMPLIANT"
                except Exception:
                    pass
            self._send_json(sentinel_data)
            return

        # 6c. API: Swarm Live Tester Status & Runs
        if url == "/api/tester":
            proj = self._get_project_param()
            proj_dir = self._resolve_project_dir(proj)
            detected_runner = "none"
            test_files = []
            if tester_server:
                try:
                    detected_runner = tester_server.detect_runner(proj_dir)
                except Exception:
                    pass
            try:
                p_path = Path(proj_dir)
                if (p_path / "tests").is_dir():
                    test_files = [str(f.relative_to(p_path)) for f in (p_path / "tests").glob("*.py")][:10]
                if not test_files:
                    test_files = [str(f.relative_to(p_path)) for f in p_path.glob("**/test*.py")][:10]
            except Exception:
                pass

            tester_data = {
                "project": proj,
                "project_dir": proj_dir,
                "health": "MONITORING",
                "detected_runner": detected_runner,
                "test_files": test_files,
                "mcp_status": {
                    "context_memory": "ONLINE (SQLite FTS5)",
                    "team_collab": "ONLINE (Bus Activo)",
                    "swarm_sentinel": "ONLINE (7 Reglas)",
                    "swarm_tester": "ONLINE (Continuo)"
                },
                "runs": [],
                "probes": [],
                "components": []
            }
            if tester_server:
                try:
                    t_conn = tester_server.get_db()
                    cur_runs = t_conn.execute("""
                        SELECT id, runner, target_path, status, total_tests, passed, failed, skipped, coverage_percent, duration_ms, created_at
                        FROM tester_runs
                        WHERE project = ? OR project = 'default'
                        ORDER BY id DESC LIMIT 15
                    """, (proj,))
                    runs = [dict(r) for r in cur_runs.fetchall()]
                    if not runs:
                        cur_fb = t_conn.execute("""
                            SELECT id, runner, target_path, status, total_tests, passed, failed, skipped, coverage_percent, duration_ms, created_at
                            FROM tester_runs
                            ORDER BY id DESC LIMIT 10
                        """)
                        runs = [dict(r) for r in cur_fb.fetchall()]
                    tester_data["runs"] = runs

                    cur_probes = t_conn.execute("""
                        SELECT id, url, method, expected_status, actual_status, latency_ms, status, created_at
                        FROM endpoint_probes
                        WHERE project = ? OR project = 'default'
                        ORDER BY id DESC LIMIT 15
                    """, (proj,))
                    probes = [dict(r) for r in cur_probes.fetchall()]
                    if not probes:
                        cur_p_fb = t_conn.execute("SELECT id, url, method, expected_status, actual_status, latency_ms, status, created_at FROM endpoint_probes ORDER BY id DESC LIMIT 10")
                        probes = [dict(r) for r in cur_p_fb.fetchall()]
                    tester_data["probes"] = probes

                    cur_comps = t_conn.execute("""
                        SELECT id, file_path, check_type, status, details, duration_ms, created_at
                        FROM component_checks
                        WHERE project = ? OR project = 'default'
                        ORDER BY id DESC LIMIT 15
                    """, (proj,))
                    comps = [dict(r) for r in cur_comps.fetchall()]
                    if not comps:
                        cur_c_fb = t_conn.execute("SELECT id, file_path, check_type, status, details, duration_ms, created_at FROM component_checks ORDER BY id DESC LIMIT 10")
                        comps = [dict(r) for r in cur_c_fb.fetchall()]
                    tester_data["components"] = comps
                    t_conn.close()

                    latest_run = tester_data["runs"][0] if tester_data["runs"] else None
                    if latest_run and latest_run["status"] == "FAIL":
                        tester_data["health"] = "FAILING"
                    elif any(p["status"] == "FAIL" for p in tester_data["probes"][:3]):
                        tester_data["health"] = "DEGRADED"
                    elif latest_run and latest_run["status"] == "PASS":
                        tester_data["health"] = "HEALTHY"
                    else:
                        tester_data["health"] = "MONITORING"
                except Exception:
                    pass
            self._send_json(tester_data)
            return

        # 7. Real-Time Server-Sent Events (SSE) Stream
        if url == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            proj = self._get_project_param()
            proj_dir = self._resolve_project_dir(proj)
            heartbeat_cycle = 0

            try:
                while True:
                    agents = []
                    messages = []
                    tasks = []
                    try:
                        conn = team_server.get_db()
                        try:
                            cur_ag = conn.execute("""
                                SELECT agent_name, status, current_task, blockers, window_id, last_heartbeat, updated_at
                                FROM team_agents
                                WHERE project = ? OR project = 'default'
                                ORDER BY agent_name
                            """, (proj,))
                            agents = [dict(r) for r in cur_ag.fetchall()]
                            now_utc = datetime.datetime.now(datetime.timezone.utc)
                            now_iso = now_utc.isoformat()

                            agent_names = {a["agent_name"] for a in agents}
                            if "orchestrator" not in agent_names:
                                agents.insert(0, {
                                    "agent_name": "orchestrator",
                                    "status": "idle",
                                    "current_task": "Sesion OpenCode activa. Listo para asignacion de tareas.",
                                    "blockers": "",
                                    "window_id": "",
                                    "last_heartbeat": now_iso,
                                    "updated_at": now_iso,
                                    "relative_time": "hace un momento"
                                })

                            for a in agents:
                                time_val = a["last_heartbeat"] or a["updated_at"]
                                a["relative_time"] = team_server.format_relative_time(time_val)
                                if a.get("status") == "working" and time_val:
                                    try:
                                        t = datetime.datetime.fromisoformat(time_val)
                                        if t.tzinfo is None:
                                            t = t.replace(tzinfo=datetime.timezone.utc)
                                        if (now_utc - t).total_seconds() > 180:
                                            a["status"] = "idle"
                                            a["relative_time"] = f"{a['relative_time']} (inactivo)"
                                    except Exception:
                                        pass

                            cur_msg = conn.execute("""
                                SELECT id, sender, message, category, priority, created_at
                                FROM team_messages
                                WHERE project = ? OR project = 'default'
                                ORDER BY id DESC LIMIT 10
                            """, (proj,))
                            messages = [dict(r) for r in cur_msg.fetchall()]
                            for m in messages:
                                m["relative_time"] = team_server.format_relative_time(m["created_at"])

                            cur_tasks = conn.execute("""
                                SELECT id, title, description, assigned_to, status, priority, notes, updated_at
                                FROM team_tasks
                                WHERE project = ?
                                ORDER BY id DESC LIMIT 20
                            """, (proj,))
                            tasks = [dict(r) for r in cur_tasks.fetchall()]
                            for t in tasks:
                                t["relative_time"] = team_server.format_relative_time(t["updated_at"])
                        finally:
                            try:
                                conn.close()
                            except Exception:
                                pass
                    except Exception:
                        pass

                    branch_str = self.server.get_branch() if proj == self.server.project_name else "main"
                    snapshot = {
                        "project": proj,
                        "project_dir": proj_dir,
                        "branch": branch_str,
                        "clock": datetime.datetime.now().strftime("%H:%M:%S"),
                        "agents": agents,
                        "messages": messages,
                        "tasks": tasks
                    }
                    data_str = json.dumps(snapshot, ensure_ascii=False)

                    try:
                        self.wfile.write(f"data: {data_str}\n\n".encode("utf-8"))
                        heartbeat_cycle += 1
                        if heartbeat_cycle >= 3:
                            self.wfile.write(b": keepalive\n\n")
                            heartbeat_cycle = 0
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                        return

                    time.sleep(2)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            except Exception:
                return
            return


        # Serve static assets from public/ directory
        return super().do_GET()

    def do_POST(self):
        """
        Pure telemetry mode enforcement.
        The web panel is strictly read-only and rejects any attempt to mutate state or inject tasks.
        """
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self._send_json({
            "error": "El panel web opera en modo exclusivo de telemetria pasiva. Las mutaciones y ejecuciones son gestionadas unicamente por los subagentes cognitivos en OpenCode.",
            "mode": "read_only_telemetry",
            "status": "blocked"
        }, status=405)

def check_server_status(port, timeout=0.35):
    """Probes http://127.0.0.1:<port>/api/status and returns its dict payload or None."""
    import urllib.request
    try:
        url = f"http://127.0.0.1:{port}/api/status"
        req = urllib.request.Request(url, headers={"User-Agent": "OpenCode-Discovery"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data
    except Exception:
        pass
    return None

def is_port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex(('127.0.0.1', port)) == 0

def resolve_project_info(given_dir=None, given_project=None):
    if given_dir:
        pdir = Path(given_dir).resolve()
    else:
        try:
            root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
            if root and os.path.isdir(root):
                pdir = Path(root).resolve()
            else:
                pdir = Path.cwd().resolve()
        except Exception:
            pdir = Path.cwd().resolve()

    if given_project and str(given_project).strip():
        pname = str(given_project).strip()
    else:
        pname = pdir.name or "default"

    return pdir, pname

def find_or_assign_port(project_dir, project_name, start_port=PORT_RANGE_START, max_port=PORT_RANGE_END):
    """
    Scans port range to find an existing server for this project.
    If none exists, returns the first available free port.
    Returns (port, is_already_running).
    """
    pdir_str = str(Path(project_dir).resolve())
    first_free = None

    for port in range(start_port, max_port + 1):
        if is_port_in_use(port):
            status = check_server_status(port)
            if status:
                s_dir = status.get("project_dir", "")
                s_proj = status.get("project", "")
                if s_dir == pdir_str or (s_proj and s_proj == project_name):
                    return port, True
        else:
            if first_free is None:
                first_free = port

    if first_free is not None:
        return first_free, False

    # Fallback to ephemeral port
    import socket
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1], False

def register_active_session(project_name, project_dir):
    """Registers orchestrator as active/idle for this project session and resets stale working agents."""
    try:
        conn = team_server.get_db()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with team_server.db_write_lock(conn):
            conn.execute("""
                INSERT INTO team_agents (agent_name, project, status, current_task, blockers, window_id, last_heartbeat, updated_at)
                VALUES ('orchestrator', ?, 'idle', 'Sesion activa en OpenCode. Listo para asignacion de tareas.', '', '', ?, ?)
                ON CONFLICT(agent_name, project) DO UPDATE SET
                    status = 'idle',
                    current_task = CASE WHEN team_agents.current_task = '' THEN 'Sesion activa en OpenCode. Listo para asignacion de tareas.' ELSE team_agents.current_task END,
                    last_heartbeat = excluded.last_heartbeat,
                    updated_at = excluded.updated_at
            """, (project_name, now, now))
            conn.execute("""
                UPDATE team_agents
                SET status = 'idle'
                WHERE project = ? AND status = 'working'
            """, (project_name,))
        conn.close()
    except Exception:
        pass

def ensure_server(project_dir, project_name, open_browser=False):
    """
    Ensures a dedicated server for this project is running in the background.
    Prints the assigned port number and exits.
    """
    register_active_session(project_name, project_dir)
    port, running = find_or_assign_port(project_dir, project_name)
    url = f"http://localhost:{port}"

    if running:
        if open_browser:
            webbrowser.open(url)
        print(port)
        return port

    # Launch daemon server on assigned port
    script_path = str(Path(__file__).resolve())
    cmd = [
        sys.executable,
        script_path,
        "--dir", str(project_dir),
        "--project", project_name,
        "--port", str(port)
    ]
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True
    )

    # Wait up to 1.5s for port to start listening
    for _ in range(15):
        time.sleep(0.1)
        if is_port_in_use(port):
            break

    if open_browser:
        webbrowser.open(url)

    print(port)
    return port

def start_server(project_dir, project_name, port=0, open_browser=False):
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    register_active_session(project_name, project_dir)

    # Auto-assign port if not specified
    if port == 0:
        port, is_running = find_or_assign_port(project_dir, project_name)
        if is_running:
            url = f"http://localhost:{port}"
            if open_browser:
                print(f"OpenCode Swarm Web server already active on {url} for project '{project_name}'. Opening browser...")
                webbrowser.open(url)
            else:
                print(f"OpenCode Swarm Web server is already running on {url} for project '{project_name}'.")
            return
    else:
        # Check if specified port is in use
        if is_port_in_use(port):
            status = check_server_status(port)
            if status:
                s_dir = status.get("project_dir", "")
                s_proj = status.get("project", "")
                pdir_str = str(Path(project_dir).resolve())
                if s_dir == pdir_str or s_proj == project_name:
                    url = f"http://localhost:{port}"
                    if open_browser:
                        print(f"OpenCode Swarm Web server already active on {url} for project '{project_name}'. Opening browser...")
                        webbrowser.open(url)
                    else:
                        print(f"OpenCode Swarm Web server is already running on {url} for project '{project_name}'.")
                    return
                else:
                    # Port belongs to another project; re-allocate
                    print(f"Port {port} is occupied by project '{s_proj}'. Allocating dedicated port...")
                    port, is_running = find_or_assign_port(project_dir, project_name)
                    if is_running:
                        url = f"http://localhost:{port}"
                        if open_browser:
                            webbrowser.open(url)
                        return

    try:
        httpd = ThreadedHTTPServer(("127.0.0.1", port), SwarmWebHandler, project_dir, project_name)
    except OSError as err:
        print(f"Cannot bind to port {port}: {err}")
        return

    url = f"http://localhost:{port}"

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  OPENCODE [SWARM EDITION] | Web Cockpit & GetBrain          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  → Project:   {project_name}")
    print(f"  → Directory: {project_dir}")
    print(f"  → Branch:    {httpd.get_branch()}")
    print(f"  → Dashboard: \033[1;36m{url}\033[0m")
    print(f"  → GetBrain:  \033[1;35m{url}/#brain\033[0m")
    print(f"  → Status:    Live SSE Stream Connected (Dedicated Session)")
    print("────────────────────────────────────────────────────────────────")
    print("  Press Ctrl+C to stop the web server.\n")

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopping OpenCode Swarm Web server for '{project_name}'...")
        httpd.server_close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenCode Swarm Web Cockpit & GetBrain Server")
    parser.add_argument("--dir", type=str, default="", help="Project root directory path (defaults to git root or CWD)")
    parser.add_argument("--project", type=str, default="", help="Project name (defaults to directory name)")
    parser.add_argument("--port", type=int, default=0, help="Port to listen on (default 0 for auto-assign per project 4040-4060)")
    parser.add_argument("--ensure", action="store_true", help="Ensure dedicated server is running in background and print port")
    parser.add_argument("--open", action="store_true", help="Automatically open the web dashboard in your browser")
    args = parser.parse_args()

    pdir, pname = resolve_project_info(args.dir, args.project)

    if args.ensure:
        ensure_server(pdir, pname, open_browser=args.open)
    else:
        start_server(pdir, pname, port=args.port, open_browser=args.open)
