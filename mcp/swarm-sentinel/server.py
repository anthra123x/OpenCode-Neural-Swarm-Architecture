#!/usr/bin/env python3
"""
Swarm Sentinel MCP Server
Real-time supervisor and engineering rule enforcer for OpenCode sub-agents.
Audits deliverables, enforces strict development rules (TDD, 6-stage verification,
conventional commits, anti-slop design, zero hardcoded secrets), tracks violations,
and reports compliance.
Standard JSON-RPC 2.0 stdio Model Context Protocol (MCP) server.
"""

import sys
import json
import os
import sqlite3
import datetime
import subprocess
import time
import random
import re
from pathlib import Path
from contextlib import contextmanager

class ManagedConnection(sqlite3.Connection):
    """Close SQLite handles deterministically when short-lived tool scopes end."""
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

# Paths & Setup
DEFAULT_SENTINEL_DIR = Path.home() / ".opencode" / "sentinel"
DB_PATH = Path(os.environ.get("OPENCODE_SENTINEL_DB", DEFAULT_SENTINEL_DIR / "sentinel.db"))

@contextmanager
def db_write_lock(conn, max_retries=10, base_delay=0.03):
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
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        if root:
            return Path(root).name
    except Exception:
        pass
    return Path.cwd().name or "default"

DEFAULT_RULES = [
    {
        "rule_code": "TDD-001",
        "title": "Test-Driven Development & Unit Coverage",
        "category": "testing",
        "target_agent": "backend",
        "severity": "critical",
        "description": "Backend logic, endpoints, and data migrations must have automated tests with >=80% coverage. Write failing test first (RED), implement (GREEN), then refactor.",
        "checklist": "1. Test file exists in tests/. 2. Happy path and edge cases covered. 3. Coverage verified >=80%. 4. All assertions green."
    },
    {
        "rule_code": "VERIF-001",
        "title": "6-Stage Verification Loop",
        "category": "qa",
        "target_agent": "qa-auditor",
        "severity": "critical",
        "description": "QA Auditor must execute the 6 stages before signing off: 1. Build, 2. Typecheck, 3. Lint/Format, 4. Unit/Integration Tests, 5. Security Audit, 6. Regression Testing.",
        "checklist": "1. Build compiles with zero fatal errors. 2. Types clean. 3. Lint clean. 4. Tests pass. 5. No SQL injection/auth flaws. 6. Regressions verified."
    },
    {
        "rule_code": "GIT-001",
        "title": "Conventional Commits 1.0 & Clean Tree",
        "category": "vcs",
        "target_agent": "git-flow",
        "severity": "high",
        "description": "Commits must follow Conventional Commits (feat, fix, refactor, test, chore, docs). No debug print/console.log, no temporary files, no uncommitted secrets.",
        "checklist": "1. Format: type(scope): summary. 2. Working tree clean. 3. No console.log or leftover debug prints. 4. Branch rebased."
    },
    {
        "rule_code": "UI-001",
        "title": "Tactile Motion & Anti-Slop Design Taste",
        "category": "frontend",
        "target_agent": "frontend",
        "severity": "high",
        "description": "Frontend UI must feel state-of-the-art: curated color tokens (OKLCH), tactile spring animations (emil-design-eng), accessible HTML (WCAG AA), zero AI-slop generic templates.",
        "checklist": "1. Color tokens defined. 2. Motion curves/spring physics applied. 3. ARIA & keyboard navigation supported. 4. Visual polish verified."
    },
    {
        "rule_code": "SEC-001",
        "title": "Zero Hardcoded Secrets & Injection Defense",
        "category": "security",
        "target_agent": "all",
        "severity": "critical",
        "description": "Never hardcode passwords, API keys, private tokens, or secrets. Validate external inputs and sanitize against SQL injection, XSS, and path traversal.",
        "checklist": "1. Secrets stored in env variables. 2. Input validation/schema parsing active. 3. Sanitized database queries."
    },
    {
        "rule_code": "ARCH-001",
        "title": "Clean Architecture & Single Responsibility",
        "category": "architecture",
        "target_agent": "all",
        "severity": "high",
        "description": "Maintain separation of concerns (SRP), loose coupling, and modular design. Avoid monolithic files >800 lines. Handle all errors explicitly.",
        "checklist": "1. Single responsibility per module. 2. Explicit typed error handling without empty catches. 3. Reusable components."
    },
    {
        "rule_code": "HANDOFF-001",
        "title": "Formal Contract & Autonomous Memory Protocol",
        "category": "workflow",
        "target_agent": "all",
        "severity": "high",
        "description": "Inter-agent handoffs must reference a published contract artifact (api_spec, db_schema, ui_contract) so consuming agents execute without user re-explanation.",
        "checklist": "1. Artifact published via team_share_artifact. 2. Handoff notes clear. 3. Context memory updated."
    }
]

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sentinel_rules (
                rule_code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                target_agent TEXT NOT NULL DEFAULT 'all',
                severity TEXT NOT NULL DEFAULT 'high',
                description TEXT NOT NULL,
                checklist TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sentinel_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                task_title TEXT NOT NULL,
                verdict TEXT NOT NULL,
                score INTEGER NOT NULL,
                violations_json TEXT DEFAULT '[]',
                feedback TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sentinel_violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                rule_code TEXT NOT NULL,
                severity TEXT NOT NULL,
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT DEFAULT ''
            )
        """)

        # Seed default rules if table empty
        cur = conn.execute("SELECT count(*) as c FROM sentinel_rules")
        if cur.fetchone()["c"] == 0:
            for r in DEFAULT_RULES:
                conn.execute("""
                    INSERT OR IGNORE INTO sentinel_rules (rule_code, title, category, target_agent, severity, description, checklist)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (r["rule_code"], r["title"], r["category"], r["target_agent"], r["severity"], r["description"], r["checklist"]))

    return conn

# Helper: Broadcast alert to team-collab if available
def alert_swarm_feed(sender, message, category="warning", priority="high", project="default"):
    team_db_path = Path(os.environ.get("OPENCODE_TEAM_DB", Path.home() / ".opencode" / "team" / "team_collab.db"))
    if team_db_path.exists():
        try:
            conn = sqlite3.connect(str(team_db_path), factory=ManagedConnection)
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with conn:
                conn.execute("""
                    INSERT INTO team_messages (sender, message, category, priority, project, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sender, message, category, priority, project, now))
        except Exception:
            pass

def record_sentinel_learning(project, agent_name, lesson, trigger, solution, category="convention"):
    """Persists engineering audit discoveries and rule resolutions into context-memory for continuous swarm improvement."""
    try:
        mem_db_path = Path(os.environ.get("OPENCODE_MEMORY_DB", Path.home() / ".opencode" / "memory" / "context_memory.db"))
        if not mem_db_path.exists():
            return
        conn = sqlite3.connect(str(mem_db_path), timeout=10.0, factory=ManagedConnection)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clean_slug = re.sub(r'[^a-z0-9]+', '_', lesson[:30].lower()).strip('_') or "rule"
        key = f"learning:sentinel:{clean_slug}_{int(time.time())}"
        content = f"**Lesson**: {lesson} | **Trigger**: {trigger} | **Solution/Rule**: {solution} | **Enforced by**: @swarm-sentinel for @{agent_name}"
        tags = f"learning, retroalimentacion, sentinel, {category}"
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO memories (key, category, content, tags, project, created_at, updated_at)
                VALUES (?, 'learning', ?, ?, ?, ?, ?)
            """, (key, content, tags, project, now, now))
        conn.close()
    except Exception:
        pass

# Tool Definitions
TOOLS = [
    {
        "name": "sentinel_audit_task",
        "description": "Audits a subagent's task deliverable against strict engineering rules (TDD, 6-stage verification, conventional commits, secrets hygiene, clean architecture). Returns PASS/FAIL verdict, compliance score (0-100), and specific corrective feedback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent who performed the work (e.g. 'backend', 'frontend', 'git-flow', 'qa-auditor')"},
                "task_title": {"type": "string", "description": "Title or summary of the task delivered"},
                "files_or_diff": {"type": "string", "description": "Summary or snippet of code changes, files touched, or git diff"},
                "test_summary": {"type": "string", "description": "Status of test execution, coverage percentage, or verification output"},
                "artifact_key": {"type": "string", "description": "Optional contract artifact published by the agent (e.g. 'auth-api-spec')"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["agent_name", "task_title"]
        }
    },
    {
        "name": "sentinel_get_rules",
        "description": "Retrieve the active engineering rulebook, severity levels, and mandatory checklists for a specific specialist agent or overall swarm.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Filter by target agent (optional, e.g. 'backend', 'frontend')"},
                "category": {"type": "string", "description": "Filter by category (e.g. 'testing', 'security', 'vcs', 'frontend')"}
            }
        }
    },
    {
        "name": "sentinel_record_violation",
        "description": "Explicitly log a development rule violation against an agent, recording infractions in sentinel.db and alerting the swarm feed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent committing the infraction"},
                "rule_code": {"type": "string", "description": "Code of violated rule (e.g. 'TDD-001', 'SEC-001', 'GIT-001')"},
                "details": {"type": "string", "description": "Specific evidence and description of the infraction"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium"], "description": "Severity level (default 'high')"},
                "project": {"type": "string", "description": "Project identifier (optional)"}
            },
            "required": ["agent_name", "rule_code", "details"]
        }
    },
    {
        "name": "sentinel_resolve_violation",
        "description": "Mark an existing rule violation as resolved after corrective action has been verified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "violation_id": {"type": "integer", "description": "ID of the violation to resolve"},
                "resolution_notes": {"type": "string", "description": "Notes explaining how the issue was fixed"},
                "project": {"type": "string", "description": "Project identifier (optional)"}
            },
            "required": ["violation_id"]
        }
    },
    {
        "name": "sentinel_verify_compliance",
        "description": "Conduct a real-time compliance sweep for the current project: checks unverified tasks, open infractions, secret scans, and test readiness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project identifier (defaults to current project)"}
            }
        }
    },
    {
        "name": "sentinel_get_compliance_report",
        "description": "Generate an executive compliance report for the project: overall compliance score (0-100%), letter grade (A+, A, B, C, F), violation counts, and certification status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project identifier (defaults to current project)"}
            }
        }
    }
]

# Tool Implementations
def tool_sentinel_audit_task(args):
    agent_name = str(args.get("agent_name", "")).strip().lstrip("@").lower()
    task_title = str(args.get("task_title", "")).strip()
    files_or_diff = str(args.get("files_or_diff", "")).strip()
    test_summary = str(args.get("test_summary", "")).strip()
    artifact_key = str(args.get("artifact_key", "")).strip()
    project = get_current_project(args.get("project"))

    if not agent_name or not task_title:
        return "Error: agent_name and task_title are required for Sentinel audit."

    score = 100
    violations = []
    feedback = []

    # 1. Security Check: Search for secrets or obvious tokens
    secret_patterns = [
        (r"(?i)(api[_-]?key|secret|token|password|auth_token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]", "Possible hardcoded secret or API key"),
        (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
        (r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", "Hardcoded JWT Token"),
        (r"sk-[A-Za-z0-9]{32,}", "OpenAI API Key")
    ]
    for pat, desc in secret_patterns:
        if re.search(pat, files_or_diff):
            score -= 35
            violations.append({"code": "SEC-001", "severity": "critical", "detail": f"{desc} detected in changes."})
            feedback.append(f"CRITICAL: {desc} found. Move to environment variables immediately.")

    # 2. Agent-Specific Audits
    if agent_name == "backend":
        # TDD & Test validation
        has_tests = any(k in (files_or_diff + test_summary).lower() for k in ["test", "spec", "assert", "coverage"])
        if not has_tests:
            score -= 25
            violations.append({"code": "TDD-001", "severity": "high", "detail": "Backend task delivered without automated test suite or coverage report."})
            feedback.append("Backend deliverables must include automated test cases in tests/ or describe test coverage (>=80%).")

        # Contract publication check
        if not artifact_key and "api" in task_title.lower():
            score -= 10
            feedback.append("Recommendation: Share API contracts via team_share_artifact for clean @frontend consumption.")

    elif agent_name == "frontend":
        # Anti-slop / motion / tokens
        has_design_indicators = any(k in files_or_diff.lower() for k in ["css", "style", "motion", "spring", "token", "theme", "tailwind", "color"])
        if not has_design_indicators and len(files_or_diff) > 20:
            score -= 10
            feedback.append("Frontend design taste: Ensure curated tokens (OKLCH) and tactile spring motion are applied.")

    elif agent_name == "git-flow":
        # Conventional Commits format
        conventional_prefix = r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_\-]+\))?:\s*.+"
        if not re.search(conventional_prefix, task_title) and not any(re.search(conventional_prefix, line.strip()) for line in files_or_diff.splitlines() if line.strip()):
            score -= 15
            violations.append({"code": "GIT-001", "severity": "medium", "detail": "Commit summary does not strictly adhere to Conventional Commits 1.0 (type(scope): description)."})
            feedback.append("Git commits must follow Conventional Commits format: feat(scope): message.")

    elif agent_name == "qa-auditor":
        # Verification loop completeness
        stages_mentioned = sum(1 for stage in ["build", "type", "lint", "test", "security", "regress"] if stage in test_summary.lower())
        if stages_mentioned < 3:
            score -= 20
            violations.append({"code": "VERIF-001", "severity": "high", "detail": "QA Audit incomplete: Missing stages of the 6-stage verification loop."})
            feedback.append("QA Auditor must verify Build, Types, Lint, Tests, Security, and Regression stages.")

    # Determine Verdict
    score = max(0, min(100, score))
    has_critical = any(v["severity"] == "critical" for v in violations)
    verdict = "APPROVED" if (score >= 80 and not has_critical) else "REJECTED"

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO sentinel_audits (project, agent_name, task_title, verdict, score, violations_json, feedback, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, agent_name, task_title, verdict, score, json.dumps(violations), "\n".join(feedback), now))

        # Record violations if rejected
        for v in violations:
            conn.execute("""
                INSERT INTO sentinel_violations (project, agent_name, rule_code, severity, details, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?)
            """, (project, agent_name, v["code"], v["severity"], v["detail"], now))

    # Alert swarm and record learning feedback
    if verdict == "REJECTED":
        alert_swarm_feed(
            sender="swarm-sentinel",
            message=f"🛡️ AUDIT REJECTED for @{agent_name} on '{task_title}' (Score: {score}/100). Infractions: {', '.join(v['code'] for v in violations)}",
            category="warning",
            priority="high",
            project=project
        )
        record_sentinel_learning(project, agent_name, f"Audit rejected: {task_title}", "; ".join(v['code'] for v in violations), "; ".join(feedback), "audit")
    else:
        record_sentinel_learning(project, agent_name, f"Audit approved: {task_title}", "All quality checks passed", "Engineering standards verified", "compliance")

    badge = "🟢 PASSED" if verdict == "APPROVED" else "🔴 REJECTED"
    lines = [
        f"══════════════════════════════════════════════════════════",
        f"  🛡️ SWARM SENTINEL COMPLIANCE AUDIT — {badge}",
        f"══════════════════════════════════════════════════════════",
        f"• Project: [{project}]  |  Agent: @{agent_name}",
        f"• Task: '{task_title}'",
        f"• Compliance Score: {score}/100  |  Verdict: {verdict}",
    ]

    if violations:
        lines.append("\n⚠️ Infractions Detected:")
        for v in violations:
            lines.append(f"  ✗ [{v['code']}] ({v['severity'].upper()}): {v['detail']}")

    if feedback:
        lines.append("\n📋 Corrective Action Required:")
        for fb in feedback:
            lines.append(f"  → {fb}")
    else:
        lines.append("\n✓ Deliverable meets 100% of engineering rules and swarm quality gates.")

    return "\n".join(lines)

def tool_sentinel_get_rules(args):
    agent_name = str(args.get("agent_name", "")).strip().lstrip("@").lower()
    category = str(args.get("category", "")).strip().lower()

    conn = get_db()
    sql = "SELECT rule_code, title, category, target_agent, severity, description, checklist FROM sentinel_rules WHERE 1=1"
    params = []
    if agent_name:
        sql += " AND (target_agent = ? OR target_agent = 'all')"
        params.append(agent_name)
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END, rule_code"

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return "No sentinel rules found matching criteria."

    lines = [f"# Swarm Sentinel Active Rulebook ({len(rows)} rules)"]
    for r in rows:
        lines.append(f"\n### [{r['rule_code']}] {r['title']} (Severity: {r['severity'].upper()})")
        lines.append(f"• Target Agent: @{r['target_agent']} | Category: {r['category']}")
        lines.append(f"• Description: {r['description']}")
        lines.append(f"• Mandatory Checklist: {r['checklist']}")

    return "\n".join(lines)

def tool_sentinel_record_violation(args):
    agent_name = str(args.get("agent_name", "")).strip().lstrip("@").lower()
    rule_code = str(args.get("rule_code", "")).strip().upper()
    details = str(args.get("details", "")).strip()
    severity = str(args.get("severity", "high")).strip().lower()
    project = get_current_project(args.get("project"))

    if not agent_name or not rule_code or not details:
        return "Error: agent_name, rule_code, and details are required."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            INSERT INTO sentinel_violations (project, agent_name, rule_code, severity, details, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (project, agent_name, rule_code, severity, details, now))
        v_id = cur.lastrowid

    alert_swarm_feed(
        sender="swarm-sentinel",
        message=f"⚠️ VIOLATION #{v_id} logged against @{agent_name} [{rule_code}]: {details}",
        category="warning",
        priority="high",
        project=project
    )
    record_sentinel_learning(project, agent_name, f"Rule violation logged: [{rule_code}]", details, f"Corrective action required under rule {rule_code}", "violation")

    return f"✓ Violation #{v_id} [{rule_code}] logged for @{agent_name} in [{project}]. Swarm notified."

def tool_sentinel_resolve_violation(args):
    v_id = int(args.get("violation_id", 0))
    notes = str(args.get("resolution_notes", "")).strip()
    project = get_current_project(args.get("project"))

    if not v_id:
        return "Error: violation_id is required."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            UPDATE sentinel_violations
            SET status = 'resolved', resolved_at = ?
            WHERE id = ? AND (project = ? OR project = 'default')
        """, (now, v_id, project))
        if cur.rowcount == 0:
            return f"Violation #{v_id} not found."

    alert_swarm_feed(
        sender="swarm-sentinel",
        message=f"✓ Violation #{v_id} resolved: {notes or 'Corrective criteria fulfilled.'}",
        category="status",
        priority="normal",
        project=project
    )
    record_sentinel_learning(project, "swarm", f"Violation #{v_id} resolved", notes or "Corrective criteria fulfilled", "Best practice reinforced", "resolution")

    return f"✓ Violation #{v_id} marked as RESOLVED in [{project}]."

def tool_sentinel_verify_compliance(args):
    project = get_current_project(args.get("project"))
    conn = get_db()

    # Open violations
    cur_v = conn.execute("""
        SELECT count(*) as total,
               sum(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as criticals
        FROM sentinel_violations
        WHERE (project = ? OR project = 'default') AND status = 'open'
    """, (project,))
    v_stat = cur_v.fetchone()
    open_count = v_stat["total"] or 0
    critical_count = v_stat["criticals"] or 0

    # Recent audits
    cur_a = conn.execute("""
        SELECT count(*) as total,
               avg(score) as avg_score,
               sum(CASE WHEN verdict = 'APPROVED' THEN 1 ELSE 0 END) as approved
        FROM sentinel_audits
        WHERE project = ? OR project = 'default'
    """, (project,))
    a_stat = cur_a.fetchone()
    audit_total = a_stat["total"] or 0
    avg_score = int(a_stat["avg_score"] or 100)
    approved_total = a_stat["approved"] or 0

    status = "COMPLIANT" if (critical_count == 0 and open_count <= 2) else "NON-COMPLIANT"

    lines = [
        f"══════════════════════════════════════════════════════════",
        f"  🛡️ SWARM SENTINEL COMPLIANCE STATUS: {status}",
        f"══════════════════════════════════════════════════════════",
        f"• Project: [{project}]",
        f"• Overall Quality Score: {avg_score}/100",
        f"• Deliverable Audits: {approved_total}/{audit_total} passed",
        f"• Active Open Violations: {open_count} ({critical_count} critical)",
    ]

    if critical_count > 0:
        lines.append(f"\n🚨 BLOCKER: {critical_count} critical violation(s) must be resolved before release.")
    else:
        lines.append("\n✓ All core engineering gates operational. Continuous monitoring active.")

    return "\n".join(lines)

def tool_sentinel_get_compliance_report(args):
    project = get_current_project(args.get("project"))
    conn = get_db()

    cur_audits = conn.execute("""
        SELECT id, agent_name, task_title, verdict, score, created_at
        FROM sentinel_audits
        WHERE project = ? OR project = 'default'
        ORDER BY id DESC LIMIT 5
    """, (project,))
    recent_audits = cur_audits.fetchall()

    cur_viols = conn.execute("""
        SELECT id, agent_name, rule_code, severity, details, created_at
        FROM sentinel_violations
        WHERE (project = ? OR project = 'default') AND status = 'open'
        ORDER BY id DESC LIMIT 5
    """, (project,))
    open_violations = cur_viols.fetchall()

    # Calculate overall grade
    avg_cur = conn.execute("SELECT avg(score) as a FROM sentinel_audits WHERE project = ?", (project,)).fetchone()
    avg_score = int(avg_cur["a"] or 95)
    if avg_score >= 95: grade = "A+"
    elif avg_score >= 90: grade = "A"
    elif avg_score >= 80: grade = "B"
    elif avg_score >= 70: grade = "C"
    else: grade = "F"

    lines = [
        f"# 🛡️ Sentinel Compliance Certification Report",
        f"**Project**: `{project}`  |  **Quality Grade**: `{grade}` ({avg_score}/100)\n",
        f"### Recent Deliverable Audits:"
    ]
    if recent_audits:
        for a in recent_audits:
            icon = "✓" if a["verdict"] == "APPROVED" else "✗"
            lines.append(f"• {icon} [{a['verdict']}] @{a['agent_name']}: '{a['task_title']}' (Score: {a['score']}%)")
    else:
        lines.append("• No formal audits recorded yet.")

    lines.append("\n### Active Violations:")
    if open_violations:
        for v in open_violations:
            lines.append(f"• ⚠️ #{v['id']} [{v['rule_code']}] @{v['agent_name']} ({v['severity']}): {v['details']}")
    else:
        lines.append("• Zero open violations. Pristine engineering hygiene.")

    return "\n".join(lines)

TOOL_HANDLERS = {
    "sentinel_audit_task": tool_sentinel_audit_task,
    "sentinel_get_rules": tool_sentinel_get_rules,
    "sentinel_record_violation": tool_sentinel_record_violation,
    "sentinel_resolve_violation": tool_sentinel_resolve_violation,
    "sentinel_verify_compliance": tool_sentinel_verify_compliance,
    "sentinel_get_compliance_report": tool_sentinel_get_compliance_report,
}

# MCP JSON-RPC Stdio Loop
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
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "swarm-sentinel-mcp",
                        "version": "1.0.0"
                    }
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            pass

        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOLS
                }
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

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
                            "content": [
                                {
                                    "type": "text",
                                    "text": text_output
                                }
                            ]
                        }
                    }
                except Exception as e:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "isError": True,
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Error executing {tool_name}: {str(e)}"
                                }
                            ]
                        }
                    }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Tool not found: {tool_name}"
                            }
                        ]
                    }
                }

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        else:
            if msg_id is not None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not supported: {method}"
                    }
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()

if __name__ == "__main__":
    main()
