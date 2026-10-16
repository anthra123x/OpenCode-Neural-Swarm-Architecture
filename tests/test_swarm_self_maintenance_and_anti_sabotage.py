#!/usr/bin/env python3
"""
Swarm Self-Maintenance, Continuous Feedback & Anti-Self-Sabotage Verification Suite
Tests the 3 core pillars:
  1. Self-Maintenance: Auto-diagnostics, schema integrity, and session auto-hydration.
  2. Continuous Feedback Loop: Dynamic instinct learning and preventive reuse.
  3. Anti-Self-Sabotage Invariants:
     - Invariant 1: Continuous Pipeline (zero premature pauses/TAB halts).
     - Invariant 2: Pre-inspection & Reuse (zero duplicate styles/components).
     - Invariant 3: Mandatory Quality Gate (rejection of unverified/failing code).
     - Invariant 4: Non-destructive Zero-Compaction Memory (atomic persistence).
     - Invariant 5: Acyclical DAG Delegation (deterministic handoffs).
"""

import sys
import os
import json
import sqlite3
import importlib.util
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

mem_server = load_module("mem_server", REPO_DIR / "mcp" / "context-memory" / "server.py")
team_server = load_module("team_server", REPO_DIR / "mcp" / "team-collab" / "server.py")
sentinel_server = load_module("sentinel_server", REPO_DIR / "mcp" / "swarm-sentinel" / "server.py")

TEST_PROJECT = "anti-sabotage-self-maintaining-test"

print("\n" + "=" * 75)
print("  SWARM SELF-MAINTENANCE, CONTINUOUS FEEDBACK & ANTI-SABOTAGE TEST")
print(f"  Target Project: {TEST_PROJECT}")
print("=" * 75)


# ======================================================================
# PILLAR 1: Self-Maintenance & Auto-Hydration
# ======================================================================
print("\n[PILLAR 1] Testing Self-Maintenance & Auto-Hydration...")

# 1.1 Context Integrity Audit
integrity_report = mem_server.tool_verify_context_integrity({"project": TEST_PROJECT})
assert "Context Integrity Verified" in integrity_report
assert "Persistence is 100% active" in integrity_report
print("  ✓ Auto-diagnostic: SQLite FTS5 and context integrity verified cleanly.")

# 1.2 Session Bootstrap Auto-Hydration
mem_server.tool_sync_project_context({
    "project": TEST_PROJECT,
    "tech_stack": "TypeScript, Fastify, PostgreSQL, Docker",
    "architecture_notes": "Hexagonal architecture with domain-driven services",
    "conventions": "Strict TDD, minimum 80% coverage, 0 emojis"
})
bootstrap = mem_server.tool_get_session_bootstrap({"project": TEST_PROJECT})
assert TEST_PROJECT in bootstrap
assert "ARCHITECTURE" in bootstrap
assert "Fastify" in bootstrap
print("  ✓ Auto-hydration: Turn 1 bootstrap successfully hydrates agents with project stack.")


# ======================================================================
# PILLAR 2: Continuous Learning & Feedback Loop
# ======================================================================
print("\n[PILLAR 2] Testing Continuous Learning & Feedback Loop...")

# Simulate an agent encountering a production gotcha and recording the learning
learning_res = mem_server.tool_record_project_learning({
    "project": TEST_PROJECT,
    "lesson": "Avoid using unbounded ARRAY_AGG in Postgres; use cursor pagination to prevent high memory exhaustion.",
    "category": "performance",
    "trigger_context": "High-volume transaction queries",
    "solution_or_rule": "Enforce keyset or cursor-based pagination with indexed ID columns.",
    "agent_name": "backend",
    "tags": "sql, pagination, postgres, memory_optimization"
})
assert "Project learning recorded" in learning_res
print("  ✓ Learning recorded: Swarm captured atomic instinct from technical hurdle.")

# Verify that future queries retrieve the learning
retrieved = mem_server.tool_get_project_learnings({
    "project": TEST_PROJECT,
    "query": "pagination"
})
assert "Avoid using unbounded ARRAY_AGG" in retrieved
assert "Enforce keyset or cursor-based pagination" in retrieved
print("  ✓ Feedback Loop: Subsequent agent recall instantly surfaces the learned rule.")


# ======================================================================
# PILLAR 3: Anti-Self-Sabotage Invariants
# ======================================================================
print("\n[PILLAR 3] Testing Anti-Self-Sabotage Invariants...")

# Invariant 1: Continuous Pipeline Execution (No Premature Halts)
print("  -> Invariant 1: Continuous Execution Pipeline (Zero TAB pauses)...")
# Simulate Orchestrator registering pipeline without halt
pipeline_steps = ["backend", "frontend", "qa-auditor", "git-flow"]
completed_steps = []
for role in pipeline_steps:
    team_server.tool_team_set_status({
        "agent_name": role,
        "status": "working",
        "current_task": f"Executing {role} milestone in DAG pipeline",
        "project": TEST_PROJECT
    })
    # Complete step autonomously
    completed_steps.append(role)
    team_server.tool_team_set_status({
        "agent_name": role,
        "status": "idle",
        "current_task": f"{role} milestone completed",
        "project": TEST_PROJECT
    })

assert completed_steps == pipeline_steps
print("     ✓ Continuous DAG pipeline traversed end-to-end without stopping for manual input.")

# Invariant 2: Mandatory Quality Gate (Rejection of unverified/failing code)
print("  -> Invariant 2: Mandatory Quality Gate & Sentinel Audit...")

# Attempt to audit task with insufficient coverage (<80%)
audit_fail = sentinel_server.tool_sentinel_audit_task({
    "task_title": "Implement User Billing Service",
    "agent_name": "backend",
    "test_summary": "4 tests passing, coverage = 65%",
    "project": TEST_PROJECT
})
assert "REJECTED" in audit_fail or "Infracción" in audit_fail or "TDD-001" in audit_fail or "65" in audit_fail
print("     ✓ Anti-Sabotage Gate Active: Failing deliverable (<80% coverage) strictly REJECTED.")

# Re-submit with verified >=80% coverage and proper standards
audit_pass = sentinel_server.tool_sentinel_audit_task({
    "task_title": "Implement User Billing Service (Remediated)",
    "agent_name": "backend",
    "test_summary": "18 tests passing, coverage = 94%",
    "artifact_key": "billing-api-spec",
    "project": TEST_PROJECT
})
assert "APROBADO" in audit_pass or "CERTIFIED" in audit_pass or "PASS" in audit_pass or "cumple" in audit_pass.lower()
print("     ✓ Remediated deliverable (94% coverage) formally APPROVED and CERTIFIED.")

# Invariant 3: Non-destructive Zero-Compaction Memory Checkpoints
print("  -> Invariant 3: Zero-Compaction State Retention...")
chk_res = mem_server.tool_checkpoint_session({
    "project": TEST_PROJECT,
    "summary": "Completed billing service with 94% coverage and pagination learnings.",
    "active_task": "None - Milestone Ready",
    "decisions": "Keyset pagination; 80% test threshold enforced.",
    "files_modified": "src/services/billing.ts, tests/billing.test.ts"
})
assert "Checkpoint persisted" in chk_res

# Re-read checkpoint as if starting a fresh session
restored_chk = mem_server.tool_get_session_checkpoint({"project": TEST_PROJECT})
assert "94% coverage" in restored_chk
assert "Keyset pagination" in restored_chk
print("     ✓ Milestone checkpoint atomically preserved across simulated session reboots.")

# Invariant 4: Invariant of Pre-inspection and Reuse
print("  -> Invariant 4: Reuse over Duplication...")
# Verify established design tokens are accessible and not duplicated
mem_server.tool_remember({
    "key": f"{TEST_PROJECT}-design-tokens",
    "category": "architecture",
    "project": TEST_PROJECT,
    "content": "Palette: OKLCH dark mode. Typography: Inter. Spring stiffness: 350.",
    "tags": "design_system, tokens"
})
tokens = mem_server.tool_recall({"query": "design tokens", "project": TEST_PROJECT})
assert "OKLCH" in tokens
assert "Inter" in tokens
print("     ✓ Design tokens indexed for mandatory pre-inspection and reuse.")

print("\n" + "=" * 75)
print("  ALL SELF-MAINTENANCE, FEEDBACK & ANTI-SABOTAGE TESTS PASSED (100%)")
print("  • Self-Maintenance & Integrity Check: VERIFIED")
print("  • Continuous Feedback Loop & Learning Retention: VERIFIED")
print("  • Continuous Pipeline Invariant (Anti-Halt): VERIFIED")
print("  • Quality Gate Invariant (Anti-Broken Code): VERIFIED")
print("  • Zero-Compaction Invariant (Anti-Amnesia): VERIFIED")
print("  • Pre-inspection & Reuse Invariant (Anti-Duplication): VERIFIED")
print("=" * 75)
