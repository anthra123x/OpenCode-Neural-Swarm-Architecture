#!/usr/bin/env python3
"""
Comprehensive End-to-End Workflow & Stability Test for OpenCode Swarm.
Tests:
  1. Multi-Project Agent Isolation (compound primary key prevents clobbering).
  2. Reactive Cross-Agent Triggering (Backend -> Frontend -> QA-Auditor).
  3. Automatic Zero-Compaction Checkpoint generation.
  4. Automatic agent transition to idle on task completion.
  5. Autonomous Continuous Learning & Feedback Loop (Memory, Tester, Sentinel).
"""

import sys
import os
import json
import time
from pathlib import Path
import importlib.util

# Paths
WORKSPACE_DIR = Path(__file__).resolve().parent.parent

# Load team collab server
team_spec = importlib.util.spec_from_file_location("team_collab_server", str(WORKSPACE_DIR / "mcp" / "team-collab" / "server.py"))
team_server = importlib.util.module_from_spec(team_spec)
team_spec.loader.exec_module(team_server)

# Load context memory server
mem_spec = importlib.util.spec_from_file_location("context_memory_server", str(WORKSPACE_DIR / "mcp" / "context-memory" / "server.py"))
mem_server = importlib.util.module_from_spec(mem_spec)
mem_spec.loader.exec_module(mem_server)

# Load sentinel server
sentinel_spec = importlib.util.spec_from_file_location("sentinel_server", str(WORKSPACE_DIR / "mcp" / "swarm-sentinel" / "server.py"))
sentinel_server = importlib.util.module_from_spec(sentinel_spec)
sentinel_spec.loader.exec_module(sentinel_server)

# Load tester server
tester_spec = importlib.util.spec_from_file_location("tester_server", str(WORKSPACE_DIR / "mcp" / "swarm-tester" / "server.py"))
tester_server = importlib.util.module_from_spec(tester_spec)
tester_spec.loader.exec_module(tester_server)

def log(msg):
    print(f"  [PASS] {msg}")

def header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def run_all_tests():
    # ─────────────────────────────────────────────────────────────────
    header("STAGE 1: Multi-Project Agent Isolation (Compound Primary Key)")
    proj_a = "proj-alpha-test"
    proj_b = "proj-beta-test"

    # Backend working in Alpha
    team_server.tool_team_set_status({
        "agent_name": "backend",
        "status": "working",
        "current_task": "Implementing Prisma models for Alpha",
        "project": proj_a
    })

    # Backend idle in Beta
    team_server.tool_team_set_status({
        "agent_name": "backend",
        "status": "idle",
        "current_task": "",
        "project": proj_b
    })

    status_a = team_server.tool_team_get_status({"project": proj_a})
    status_b = team_server.tool_team_get_status({"project": proj_b})

    assert "WORKING" in status_a and "Prisma models for Alpha" in status_a, "Alpha status lost!"
    assert "IDLE" in status_b, "Beta status was not idle!"
    log(f"Project '{proj_a}' and '{proj_b}' maintain independent @backend states without collision.")

    # ─────────────────────────────────────────────────────────────────
    header("STAGE 2: Reactive Triggering (Backend -> Frontend -> QA)")
    wf_proj = "e2e-workflow-demo"

    # Turn A: Backend shares API contract
    share_res = team_server.tool_team_share_artifact({
        "creator": "backend",
        "artifact_key": "catalog-v2-api",
        "title": "Catalog & Product API v2 Specification",
        "artifact_type": "api_spec",
        "content": "POST /api/v2/products\nGET /api/v2/products/{id}",
        "project": wf_proj
    })
    assert "Reactive trigger dispatched to @frontend" in share_res
    log("Backend published 'catalog-v2-api'. Reactive trigger auto-dispatched to @frontend.")

    # Verify Frontend status was automatically transitioned to working on this trigger
    st_frontend = team_server.tool_team_get_status({"project": wf_proj})
    assert "@frontend" in st_frontend and "WORKING" in st_frontend
    log("Team status immediately reflects @frontend is WORKING on the backend contract.")

    # Verify Auto-Checkpoint was created
    latest_chk = mem_server.tool_get_session_checkpoint({"project": wf_proj})
    assert "catalog-v2-api" in latest_chk or "Auto-Checkpoint" in latest_chk
    log("Auto-Checkpoint verified: Context memory updated silently in SQLite FTS5.")

    # Turn B: Frontend checks triggers and claims work
    triggers_res = team_server.tool_team_check_triggers({
        "agent_name": "frontend",
        "project": wf_proj,
        "claim": True
    })
    assert "catalog-v2-api" in triggers_res
    assert "claimed" in triggers_res
    log("Frontend claimed pending reactive trigger and received contract payload.")

    # Frontend publishes UI contract and triggers QA auditor
    ui_share = team_server.tool_team_share_artifact({
        "creator": "frontend",
        "artifact_key": "catalog-v2-ui",
        "title": "Catalog Grid & Motion Drawer UI Specs",
        "artifact_type": "ui_contract",
        "content": "export interface ProductCardProps { id: string, name: string }",
        "project": wf_proj
    })
    assert "saved by @frontend" in ui_share

    trigger_qa = team_server.tool_team_trigger_agent({
        "from_agent": "frontend",
        "to_agent": "qa-auditor",
        "trigger_type": "review",
        "artifact_key": "catalog-v2-ui",
        "summary": "Run E2E motion and accessibility verification on Catalog UI",
        "project": wf_proj
    })
    assert "Reactive Trigger dispatched to @qa-auditor" in trigger_qa
    log("Frontend published UI contract and dispatched reactive trigger to @qa-auditor.")

    # ─────────────────────────────────────────────────────────────────
    header("STAGE 3: Task Completion & Automatic Agent Idle Transition")
    # QA Auditor posts task, claims it, and completes it
    team_server.tool_team_post_task({
        "title": "Verify WCAG AA & Vitest Unit Tests",
        "assigned_to": "qa-auditor",
        "project": wf_proj
    })
    cur = team_server.get_db().execute("SELECT id FROM team_tasks WHERE project = ? ORDER BY id DESC LIMIT 1", (wf_proj,))
    qa_task_id = cur.fetchone()["id"]

    team_server.tool_team_claim_task({
        "task_id": qa_task_id,
        "agent_name": "qa-auditor",
        "project": wf_proj
    })
    st_qa_working = team_server.tool_team_get_status({"project": wf_proj})
    assert "WORKING" in st_qa_working

    # Complete the task
    team_server.tool_team_update_task({
        "task_id": qa_task_id,
        "status": "completed",
        "notes": "All 18 unit tests passing. Spring physics verified."
    })

    # QA Auditor should automatically be idle now
    st_qa_idle = team_server.tool_team_get_status({"project": wf_proj})
    assert "IDLE" in st_qa_idle
    log("QA Auditor automatically transitioned to IDLE upon completing task.")

    # ─────────────────────────────────────────────────────────────────
    header("STAGE 4: Autonomous Continuous Learning & Feedback Loop")
    # 1. Record explicit engineering lesson from an agent
    rec_res = mem_server.tool_record_project_learning({
        "project": wf_proj,
        "lesson": "SQLite WAL mode prevents reader/writer locking under concurrent swarm access",
        "trigger_context": "Database is locked OperationalError",
        "solution_or_rule": "Apply PRAGMA journal_mode=WAL and PRAGMA busy_timeout=30000",
        "category": "architecture",
        "agent_name": "backend"
    })
    assert "Project learning recorded" in rec_res
    log("Explicit project learning persisted into continuous feedback loop.")

    # 2. Autonomous feedback from Live Tester on test run
    tester_server.record_feedback_learning(
        wf_proj,
        "FastAPI requires lifespan context manager instead of on_event",
        "DeprecationWarning in startup event",
        "Use asynccontextmanager lifespan(app)",
        "testing"
    )
    log("Swarm Live Tester silently fed back execution lesson into context memory.")

    # 3. Autonomous feedback from Sentinel on audit violation/resolution
    sentinel_server.record_sentinel_learning(
        wf_proj,
        "qa-auditor",
        "QA Auditor must verify all 6 stages of verification loop",
        "Audit check failed for VERIF-001",
        "Execute build, types, lint, tests, security and regression",
        "audit"
    )
    log("Swarm Sentinel silently fed back audit compliance learning into context memory.")

    # 4. Verify learnings query and session bootstrap hydration
    learnings = mem_server.tool_get_project_learnings({"project": wf_proj})
    assert "SQLite WAL mode" in learnings
    assert "FastAPI requires lifespan" in learnings
    assert "QA Auditor must verify" in learnings

    bootstrap = mem_server.tool_get_session_bootstrap({"project": wf_proj})
    assert "Retroalimentación y Aprendizajes del Proyecto" in bootstrap
    assert "SQLite WAL mode" in bootstrap
    log("Session Bootstrap automatically hydrated subagents with project feedback and learnings.")

    # ─────────────────────────────────────────────────────────────────
    header("FINAL RESULT: ALL SWARM CLI WORKFLOW ASSERTIONS PASSED")
    print("""
  +------------------------------------------------------------------+
  |  ALL SWARM WORKFLOW STAGES VERIFIED WITH ZERO ERRORS             |
  |  - Multi-Project Isolated Agent States: PASSED                   |
  |  - Reactive Work Triggers (Backend -> Frontend -> QA): PASSED    |
  |  - Automatic Zero-Compaction Checkpoints: PASSED                 |
  |  - Automatic Idle Transition on Task Complete: PASSED            |
  |  - Autonomous Continuous Learning & Feedback Loop: PASSED        |
  +------------------------------------------------------------------+
    """)

if __name__ == "__main__":
    run_all_tests()
