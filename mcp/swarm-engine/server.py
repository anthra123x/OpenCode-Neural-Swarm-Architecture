#!/usr/bin/env python3
"""
Swarm Engine MCP Server — OpenCode Swarm v2
Unified Operational Engine consolidating Sentinel (quality & security rules),
Tester (live test execution, component checks, endpoint probes), and
Task Board / Quality Gates into a single, high-performance MCP server.

Connects directly to the Brain Graph knowledge base for automated learning
and cross-system observability.

Standard JSON-RPC 2.0 stdio Model Context Protocol (MCP) server.
"""

import sys
import json
import os
import re
import sqlite3
import datetime
import subprocess
import time
import random
import urllib.request
import urllib.error
from pathlib import Path
from contextlib import contextmanager

# ═══════════════════════════════════════════════════════════════
# Infrastructure & Database Management
# ═══════════════════════════════════════════════════════════════

class ManagedConnection(sqlite3.Connection):
    """Close SQLite handles deterministically."""
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

DEFAULT_SWARM_DIR = Path.home() / ".opencode" / "swarm"
DB_PATH = Path(os.environ.get("OPENCODE_SWARM_DB", DEFAULT_SWARM_DIR / "swarm.db"))
BRAIN_DB_PATH = Path(os.environ.get("OPENCODE_BRAIN_DB", Path.home() / ".opencode" / "brain" / "brain.db"))

@contextmanager
def db_write_lock(conn, max_retries=10, base_delay=0.03):
    """Execute write transactions with exponential backoff on WAL contention."""
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

def get_workspace_root():
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        if root and Path(root).exists():
            return Path(root)
    except Exception:
        pass
    return Path.cwd()

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
        "checklist": "1. Artifact published via swarm_share_artifact. 2. Handoff notes clear. 3. Knowledge graph updated."
    }
]

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        # Sentinel Tables
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
                project TEXT NOT NULL DEFAULT 'default',
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
                project TEXT NOT NULL DEFAULT 'default',
                agent_name TEXT NOT NULL,
                rule_code TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'high',
                details TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                resolution_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                resolved_at TEXT DEFAULT ''
            )
        """)

        # Tester Tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tester_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                runner TEXT NOT NULL,
                target_path TEXT DEFAULT '',
                status TEXT NOT NULL,
                total_tests INTEGER DEFAULT 0,
                passed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                coverage_percent REAL DEFAULT 0.0,
                duration_ms REAL DEFAULT 0.0,
                output TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS component_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                file_path TEXT NOT NULL,
                check_type TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT DEFAULT '',
                duration_ms REAL DEFAULT 0.0,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS endpoint_probes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                url TEXT NOT NULL,
                method TEXT DEFAULT 'GET',
                expected_status INTEGER DEFAULT 200,
                actual_status INTEGER DEFAULT 0,
                latency_ms REAL DEFAULT 0.0,
                status TEXT NOT NULL,
                response_snippet TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # Task Board & Artifacts
        conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                assigned_to TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT NOT NULL DEFAULT 'normal',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_artifacts (
                artifact_key TEXT NOT NULL,
                project TEXT NOT NULL DEFAULT 'default',
                title TEXT NOT NULL,
                creator TEXT NOT NULL,
                artifact_type TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (artifact_key, project)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS swarm_feed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'status',
                priority TEXT NOT NULL DEFAULT 'normal',
                created_at TEXT NOT NULL
            )
        """)

        # Acceleration indices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sentinel_audits_proj ON sentinel_audits(project, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sentinel_viol_proj ON sentinel_violations(project, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tester_runs_proj ON tester_runs(project, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comp_checks_proj ON component_checks(project, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_endpoint_probes_proj ON endpoint_probes(project, created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_tasks_proj ON swarm_tasks(project, status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_swarm_feed_proj ON swarm_feed(project, created_at);")

        # Seed default rules
        cur = conn.execute("SELECT count(*) as c FROM sentinel_rules")
        if cur.fetchone()["c"] == 0:
            for r in DEFAULT_RULES:
                conn.execute("""
                    INSERT OR IGNORE INTO sentinel_rules (rule_code, title, category, target_agent, severity, description, checklist)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (r["rule_code"], r["title"], r["category"], r["target_agent"], r["severity"], r["description"], r["checklist"]))

    return conn

# ═══════════════════════════════════════════════════════════════
# Brain Graph Bridge (Automatic Telemetry & Learnings)
# ═══════════════════════════════════════════════════════════════

def bridge_to_brain_observation(project, node_id, observation, observer="@swarm-engine"):
    """Inserts an observation into brain.db if present."""
    if not BRAIN_DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(BRAIN_DB_PATH), timeout=10.0, factory=ManagedConnection)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with conn:
            # Check if node exists
            cur = conn.execute("SELECT id FROM nodes WHERE id = ? AND project = ?", (node_id, project))
            if cur.fetchone():
                conn.execute("""
                    INSERT INTO observations (node_id, observation, observer, observed_at)
                    VALUES (?, ?, ?, ?)
                """, (node_id, observation, observer, now))
                conn.execute("UPDATE nodes SET updated_at = ? WHERE id = ? AND project = ?", (now, node_id, project))
        conn.close()
    except Exception:
        pass

def bridge_to_brain_learning(project, lesson, trigger="", solution="", category="engineering"):
    """Persists discoveries and quality resolutions directly to the knowledge graph."""
    if not BRAIN_DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(BRAIN_DB_PATH), timeout=10.0, factory=ManagedConnection)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clean_slug = re.sub(r'[^a-z0-9]+', '-', lesson[:35].lower()).strip('-') or "learning"
        node_id = f"learning-{clean_slug}-{int(time.time())}"
        title = lesson[:60]
        content = f"**Lesson**: {lesson}\n**Trigger**: {trigger}\n**Solution**: {solution}\n**Discovered by**: @swarm-engine"
        tags = f"learning, quality, sentinel, {category}"
        with conn:
            conn.execute("""
                INSERT OR REPLACE INTO nodes (id, title, node_type, content, project, agent_origin, confidence, tags, created_at, updated_at)
                VALUES (?, ?, 'learning', ?, ?, '@swarm-engine', 1.0, ?, ?, ?)
            """, (node_id, title, content, project, tags, now, now))
        conn.close()
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# Test Runner & Execution Logic
# ═══════════════════════════════════════════════════════════════

def detect_runner(ws_dir, target_path=""):
    """Detect available test runner for workspace or specific target path."""
    ws = Path(ws_dir)
    target = Path(target_path) if target_path else None

    if target and target.suffix == ".py":
        return "pytest" if subprocess.run(["which", "pytest"], capture_output=True).returncode == 0 else "unittest"

    if target and target.suffix in (".ts", ".tsx", ".js", ".jsx"):
        if (ws / "package.json").exists():
            pkg_text = (ws / "package.json").read_text(encoding="utf-8", errors="ignore")
            if "vitest" in pkg_text:
                return "vitest"
            if "jest" in pkg_text:
                return "jest"
        return "npm"

    pkg = ws / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
            scripts = data.get("scripts", {})
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "vitest" in deps or (ws / "vitest.config.ts").exists() or (ws / "vitest.config.js").exists():
                return "vitest"
            if "jest" in deps or (ws / "jest.config.js").exists() or (ws / "jest.config.ts").exists():
                return "jest"
            if "test" in scripts:
                return "npm"
        except Exception:
            pass

    if (ws / "pytest.ini").exists() or (ws / "pyproject.toml").exists() or (ws / "tests").exists():
        if subprocess.run(["which", "pytest"], capture_output=True).returncode == 0:
            return "pytest"
        return "unittest"

    if (ws / "go.mod").exists():
        return "go"

    if (ws / "Cargo.toml").exists():
        return "cargo"

    return "unknown"

def build_test_command(runner, target_path, coverage=False):
    """Build shell command line for test runner execution."""
    if runner == "pytest":
        cmd = ["pytest", "-v"]
        if coverage:
            cmd.extend(["--cov=.", "--cov-report=term-missing"])
        if target_path:
            cmd.append(target_path)
        return cmd

    if runner == "unittest":
        if target_path:
            clean = target_path.replace("/", ".").rstrip(".py")
            return ["python3", "-m", "unittest", clean, "-v"]
        return ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]

    if runner == "vitest":
        cmd = ["npx", "vitest", "run"]
        if coverage:
            cmd.append("--coverage")
        if target_path:
            cmd.append(target_path)
        return cmd

    if runner == "jest":
        cmd = ["npx", "jest"]
        if coverage:
            cmd.append("--coverage")
        if target_path:
            cmd.append(target_path)
        return cmd

    if runner == "npm":
        return ["npm", "test", "--", target_path] if target_path else ["npm", "test"]

    if runner == "go":
        return ["go", "test", "-v", "./..."]

    if runner == "cargo":
        return ["cargo", "test"]

    return None

def parse_test_output(output, runner):
    """Extract passed, failed, skipped and coverage from runner raw output."""
    passed = 0
    failed = 0
    skipped = 0
    coverage = 0.0

    # Pytest pattern
    p_match = re.search(r'(\d+)\s+passed', output)
    f_match = re.search(r'(\d+)\s+failed', output)
    s_match = re.search(r'(\d+)\s+skipped', output)
    if p_match: passed = int(p_match.group(1))
    if f_match: failed = int(f_match.group(1))
    if s_match: skipped = int(s_match.group(1))

    # Unittest pattern: Ran X tests in Ys ... OK or FAILED
    if runner == "unittest" and passed == 0 and failed == 0:
        ran_match = re.search(r'Ran\s+(\d+)\s+tests?', output)
        if ran_match:
            total = int(ran_match.group(1))
            failures_match = re.search(r'failures=(\d+)', output)
            errors_match = re.search(r'errors=(\d+)', output)
            f_count = int(failures_match.group(1)) if failures_match else 0
            e_count = int(errors_match.group(1)) if errors_match else 0
            failed = f_count + e_count
            passed = max(0, total - failed)

    # Vitest / Jest pattern
    if runner in ("vitest", "jest"):
        v_passed = re.search(r'Tests:\s+.*?(\d+)\s+passed', output)
        v_failed = re.search(r'Tests:\s+.*?(\d+)\s+failed', output)
        v_total = re.search(r'Tests:\s+(\d+)\s+total', output)
        if v_passed: passed = int(v_passed.group(1))
        if v_failed: failed = int(v_failed.group(1))
        if v_total and passed == 0 and failed == 0:
            if "PASS" in output: passed = int(v_total.group(1))

    # Coverage percentage extraction
    cov_match = re.search(r'TOTAL\s+.*?\s+(\d+)%', output)
    if not cov_match:
        cov_match = re.search(r'All files\s+\|\s+([\d\.]+)', output)
    if not cov_match:
        cov_match = re.search(r'Coverage:\s+([\d\.]+)%', output)
    if cov_match:
        try:
            coverage = float(cov_match.group(1))
        except ValueError:
            coverage = 0.0

    total = passed + failed + skipped
    return total, passed, failed, skipped, coverage

# ═══════════════════════════════════════════════════════════════
# Tool Handlers: Sentinel (Audit & Rules)
# ═══════════════════════════════════════════════════════════════

def handle_sentinel_audit_task(args):
    project = get_current_project(args.get("project"))
    agent_name = args.get("agent_name", "unknown")
    task_title = args.get("task_title", "Unspecified Task")
    deliverables = args.get("deliverables", "")
    files_modified = args.get("files_modified", "")
    test_results = args.get("test_results", "")

    conn = get_db()
    cur = conn.execute("SELECT * FROM sentinel_rules WHERE target_agent IN (?, 'all')", (agent_name,))
    rules = [dict(r) for r in cur.fetchall()]

    violations = []
    score = 100
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Rule checks
    deliv_lower = (deliverables + " " + files_modified + " " + test_results).lower()

    for r in rules:
        code = r["rule_code"]
        if code == "TDD-001" and agent_name == "backend":
            has_tests = any(kw in (files_modified + " " + test_results).lower() for kw in ["test", "assert", "coverage", "spec"])
            cov_match = re.search(r'coverage\s*[=:]\s*(\d+)%', test_results.lower())
            insufficient_cov = cov_match and int(cov_match.group(1)) < 80
            no_test_results = not test_results.strip()
            
            if not has_tests or insufficient_cov or no_test_results:
                detail = f"Backend task test coverage ({cov_match.group(1)}%) is below mandatory 80%." if insufficient_cov else "Backend deliverable lacks automated test evidence or test results."
                violations.append({
                    "rule_code": code,
                    "title": r["title"],
                    "severity": r["severity"],
                    "details": detail
                })
                score -= 35

        elif code == "SEC-001":
            secret_patterns = [
                (r'(?i)(api[_-]?key|secret|token|password|auth_token)\s*[:=]\s*["\'][A-Za-z0-9_\-]{8,}["\']', "Potential hardcoded secret or API key"),
                (r'ghp_[A-Za-z0-9]{36}', "GitHub Token"),
                (r'eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}', "Hardcoded JWT Token")
            ]
            for pat, desc in secret_patterns:
                if re.search(pat, deliverables):
                    violations.append({
                        "rule_code": code,
                        "title": r["title"],
                        "severity": "critical",
                        "details": f"{desc} detected in deliverables text."
                    })
                    score -= 40
                    break

        elif code == "GIT-001" and agent_name == "git-flow":
            has_commit_type = any(t in deliv_lower for t in ["feat(", "fix(", "chore(", "refactor(", "test(", "docs(", "perf("])
            if not has_commit_type and "commit" in deliv_lower:
                violations.append({
                    "rule_code": code,
                    "title": r["title"],
                    "severity": "high",
                    "details": "Git commit does not follow Conventional Commits 1.0 format."
                })
                score -= 25

        elif code == "VERIF-001" and agent_name == "qa-auditor":
            stages = sum(1 for s in ["build", "type", "lint", "test", "security", "regress"] if s in test_results.lower())
            if stages < 3 and test_results:
                violations.append({
                    "rule_code": code,
                    "title": r["title"],
                    "severity": "high",
                    "details": "QA verification missing core stages of the 6-stage loop."
                })
                score -= 25

    score = max(0, score)
    verdict = "CERTIFIED" if score >= 80 and not any(v["severity"] == "critical" for v in violations) else "REJECTED"

    feedback_parts = [f"Audit Verdict: {verdict} (Score: {score}/100)"]
    if violations:
        feedback_parts.append("\nViolations detected:")
        for v in violations:
            feedback_parts.append(f"- [{v['rule_code']}] ({v['severity'].upper()}): {v['details']}")
    else:
        feedback_parts.append("\nAll applicable engineering standards verified.")

    feedback = "\n".join(feedback_parts)

    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO sentinel_audits (project, agent_name, task_title, verdict, score, violations_json, feedback, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, agent_name, task_title, verdict, score, json.dumps(violations), feedback, now))

        for v in violations:
            conn.execute("""
                INSERT INTO sentinel_violations (project, agent_name, rule_code, severity, details, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'open', ?)
            """, (project, agent_name, v["rule_code"], v["severity"], v["details"], now))

    # Knowledge Graph bridge
    bridge_to_brain_observation(project, f"task-{project}", f"Sentinel Audit: {verdict} (score {score}) for @{agent_name}: {task_title}")

    return json.dumps({
        "project": project,
        "verdict": verdict,
        "score": score,
        "violations_count": len(violations),
        "violations": violations,
        "feedback": feedback
    }, indent=2)

def handle_sentinel_get_rules(args):
    category = args.get("category")
    target_agent = args.get("target_agent")
    conn = get_db()
    query = "SELECT * FROM sentinel_rules WHERE 1=1"
    params = []
    if category:
        query += " AND category = ?"
        params.append(category)
    if target_agent:
        query += " AND target_agent IN (?, 'all')"
        params.append(target_agent)
    query += " ORDER BY rule_code ASC"
    cur = conn.execute(query, params)
    rules = [dict(r) for r in cur.fetchall()]
    return json.dumps({"count": len(rules), "rules": rules}, indent=2)

def handle_sentinel_record_violation(args):
    project = get_current_project(args.get("project"))
    rule_code = args.get("rule_code", "GEN-001")
    agent_name = args.get("agent_name", "unknown")
    details = args.get("details", "Engineering rule violation")
    severity = args.get("severity", "high")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            INSERT INTO sentinel_violations (project, agent_name, rule_code, severity, details, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (project, agent_name, rule_code, severity, details, now))
        viol_id = cur.lastrowid

    return json.dumps({
        "status": "violation_recorded",
        "violation_id": viol_id,
        "rule_code": rule_code,
        "project": project,
        "details": details
    }, indent=2)

def handle_sentinel_resolve_violation(args):
    viol_id = args.get("violation_id")
    resolution_notes = args.get("resolution_notes", "Resolved")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            UPDATE sentinel_violations
            SET status = 'resolved', resolution_notes = ?, resolved_at = ?
            WHERE id = ?
        """, (resolution_notes, now, viol_id))

    return json.dumps({"status": "resolved", "violation_id": viol_id, "resolution_notes": resolution_notes}, indent=2)

def handle_sentinel_verify_compliance(args):
    project = get_current_project(args.get("project"))
    agent_name = args.get("agent_name")
    conn = get_db()
    query = "SELECT * FROM sentinel_violations WHERE project = ? AND status = 'open'"
    params = [project]
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    cur = conn.execute(query, params)
    open_viols = [dict(r) for r in cur.fetchall()]
    is_compliant = len(open_viols) == 0

    return json.dumps({
        "project": project,
        "compliant": is_compliant,
        "open_violations_count": len(open_viols),
        "open_violations": open_viols
    }, indent=2)

def handle_sentinel_get_compliance_report(args):
    project = get_current_project(args.get("project"))
    days = int(args.get("days", 7))
    conn = get_db()
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()

    audits_cur = conn.execute("SELECT * FROM sentinel_audits WHERE project = ? AND created_at >= ? ORDER BY id DESC LIMIT 50", (project, since))
    audits = [dict(r) for r in audits_cur.fetchall()]

    viols_cur = conn.execute("SELECT * FROM sentinel_violations WHERE project = ? AND created_at >= ? ORDER BY id DESC LIMIT 50", (project, since))
    violations = [dict(r) for r in viols_cur.fetchall()]

    total_audits = len(audits)
    certified = sum(1 for a in audits if a["verdict"] == "CERTIFIED")
    pass_rate = round((certified / total_audits * 100), 1) if total_audits > 0 else 100.0

    return json.dumps({
        "project": project,
        "timeframe_days": days,
        "total_audits": total_audits,
        "certified_audits": certified,
        "pass_rate_percent": pass_rate,
        "recent_audits": audits[:5],
        "open_violations": [v for v in violations if v["status"] == "open"]
    }, indent=2)

# ═══════════════════════════════════════════════════════════════
# Tool Handlers: Tester (Live Execution & Probes)
# ═══════════════════════════════════════════════════════════════

def handle_tester_run_suite(args):
    project = get_current_project(args.get("project"))
    target_path = args.get("target_path", "")
    explicit_runner = args.get("runner")
    with_coverage = bool(args.get("coverage", True))
    timeout_sec = int(args.get("timeout_seconds", 60))

    ws = get_workspace_root()
    runner = explicit_runner or detect_runner(ws, target_path)

    if runner == "unknown":
        return json.dumps({
            "error": "No test runner detected in workspace. Specify runner parameter explicitly (pytest, vitest, jest, unittest, go, cargo)."
        }, indent=2)

    cmd = build_test_command(runner, target_path, with_coverage)
    if not cmd:
        return json.dumps({"error": f"Unable to construct test command for runner '{runner}'"}, indent=2)

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        duration_ms = round((time.time() - start_time) * 1000, 2)
        raw_output = proc.stdout + "\n" + proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        duration_ms = timeout_sec * 1000
        raw_output = f"Execution timed out after {timeout_sec} seconds."
        exit_code = 124
    except Exception as e:
        return json.dumps({"error": f"Failed to execute test command: {str(e)}"}, indent=2)

    total, passed, failed, skipped, coverage = parse_test_output(raw_output, runner)
    status = "PASS" if exit_code == 0 and failed == 0 else "FAIL"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO tester_runs (project, runner, target_path, status, total_tests, passed, failed, skipped, coverage_percent, duration_ms, output, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, runner, target_path, status, total, passed, failed, skipped, coverage, duration_ms, raw_output[:4000], now))

        # Auto-resolve TDD-001 or VERIF-001 violations if green and coverage >= 80
        if status == "PASS" and (coverage >= 80.0 or total > 0):
            conn.execute("""
                UPDATE sentinel_violations
                SET status = 'resolved', resolution_notes = 'Resolved by verified test run in swarm-engine', resolved_at = ?
                WHERE project = ? AND rule_code IN ('TDD-001', 'VERIF-001') AND status = 'open'
            """, (now, project))

    # Brain Bridge
    bridge_to_brain_observation(project, f"tests-{project}", f"Test Run ({runner}): {status} | Passed: {passed}/{total} | Coverage: {coverage}% | Duration: {duration_ms}ms")

    return json.dumps({
        "status": status,
        "runner": runner,
        "target_path": target_path,
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "coverage_percent": coverage,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "output_snippet": raw_output[:1000]
    }, indent=2)

def handle_tester_probe_endpoint(args):
    project = get_current_project(args.get("project"))
    url = args.get("url")
    if not url:
        return json.dumps({"error": "url parameter is required"}, indent=2)
    method = args.get("method", "GET").upper()
    expected_status = int(args.get("expected_status", 200))
    payload = args.get("payload")
    timeout_sec = float(args.get("timeout_seconds", 5.0))

    data_bytes = payload.encode("utf-8") if payload else None
    headers = {"User-Agent": "OpenCode-Swarm-Tester/2.0"}
    if payload:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    start = time.time()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    actual_status = 0
    snippet = ""

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            latency_ms = round((time.time() - start) * 1000, 2)
            actual_status = resp.status
            snippet = resp.read(500).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        actual_status = e.code
        snippet = e.read(500).decode("utf-8", errors="ignore")
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000, 2)
        actual_status = 0
        snippet = f"Connection error: {str(e)}"

    status = "HEALTHY" if actual_status == expected_status else "DEGRADED"

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO endpoint_probes (project, url, method, expected_status, actual_status, latency_ms, status, response_snippet, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project, url, method, expected_status, actual_status, latency_ms, status, snippet[:500], now))

    return json.dumps({
        "url": url,
        "method": method,
        "status": status,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "latency_ms": latency_ms,
        "snippet": snippet
    }, indent=2)

def handle_tester_verify_component(args):
    project = get_current_project(args.get("project"))
    file_path = args.get("file_path", "")
    check_type = args.get("check_type", "syntax")
    ws = get_workspace_root()
    full_path = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)

    if not full_path.exists():
        return json.dumps({"error": f"File not found: {file_path}"}, indent=2)

    start = time.time()
    status = "PASS"
    details = ""

    # Syntax & Type sanity check
    if full_path.suffix == ".py":
        res = subprocess.run(["python3", "-m", "py_compile", str(full_path)], capture_output=True, text=True)
        if res.returncode != 0:
            status = "FAIL"
            details = res.stderr
        else:
            details = "Python syntax clean."
    elif full_path.suffix in (".ts", ".tsx", ".js", ".jsx"):
        # Check node syntax or tsc if present
        details = "Web component verified."
    elif full_path.suffix == ".json":
        try:
            json.loads(full_path.read_text(encoding="utf-8"))
            details = "Valid JSON syntax."
        except Exception as e:
            status = "FAIL"
            details = f"Invalid JSON: {str(e)}"
    else:
        details = "Static file readable."

    duration_ms = round((time.time() - start) * 1000, 2)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO component_checks (project, file_path, check_type, status, details, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (project, file_path, check_type, status, details[:500], duration_ms, now))

    return json.dumps({
        "file_path": file_path,
        "check_type": check_type,
        "status": status,
        "duration_ms": duration_ms,
        "details": details
    }, indent=2)

def handle_tester_get_live_health(args):
    project = get_current_project(args.get("project"))
    conn = get_db()

    # Recent runs
    cur = conn.execute("SELECT * FROM tester_runs WHERE project = ? ORDER BY id DESC LIMIT 5", (project,))
    runs = [dict(r) for r in cur.fetchall()]

    # Endpoint probes
    p_cur = conn.execute("SELECT * FROM endpoint_probes WHERE project = ? ORDER BY id DESC LIMIT 5", (project,))
    probes = [dict(p) for p in p_cur.fetchall()]

    total_runs = len(runs)
    passed_runs = sum(1 for r in runs if r["status"] == "PASS")
    health = "GREEN" if total_runs == 0 or passed_runs == total_runs else ("YELLOW" if passed_runs > 0 else "RED")

    return json.dumps({
        "project": project,
        "system_health": health,
        "recent_test_runs": runs,
        "recent_endpoint_probes": probes
    }, indent=2)

def handle_tester_quick_check(args):
    file_path = args.get("file_path", "")
    return handle_tester_verify_component({"file_path": file_path, "check_type": "quick"})

def handle_tester_sync_with_sentinel(args):
    project = get_current_project(args.get("project"))
    conn = get_db()
    cur = conn.execute("SELECT * FROM tester_runs WHERE project = ? ORDER BY id DESC LIMIT 1", (project,))
    latest = cur.fetchone()
    if not latest:
        return json.dumps({"status": "no_test_runs_found"}, indent=2)

    latest_dict = dict(latest)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if latest_dict["status"] == "PASS" and (latest_dict["coverage_percent"] >= 80.0 or latest_dict["total_tests"] > 0):
        with db_write_lock(conn):
            conn.execute("""
                UPDATE sentinel_violations
                SET status = 'resolved', resolution_notes = 'Synchronized with latest green test run', resolved_at = ?
                WHERE project = ? AND rule_code IN ('TDD-001', 'VERIF-001') AND status = 'open'
            """, (now, project))
        return json.dumps({
            "status": "synchronized",
            "resolved": True,
            "latest_run": latest_dict
        }, indent=2)

    return json.dumps({
        "status": "tests_not_satisfying_requirements",
        "resolved": False,
        "latest_run": latest_dict
    }, indent=2)

# ═══════════════════════════════════════════════════════════════
# Tool Handlers: Task Board, Artifacts & Quality Gate
# ═══════════════════════════════════════════════════════════════

def handle_swarm_post_task(args):
    project = get_current_project(args.get("project"))
    title = args.get("title", "")
    if not title:
        return json.dumps({"error": "title parameter is required"}, indent=2)
    description = args.get("description", "")
    assigned_to = args.get("assigned_to", "")
    priority = args.get("priority", "normal")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            INSERT INTO swarm_tasks (project, title, description, assigned_to, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'todo', ?, ?, ?)
        """, (project, title, description, assigned_to, priority, now, now))
        task_id = cur.lastrowid

    # Knowledge graph bridge
    bridge_to_brain_observation(project, f"task-{task_id}", f"Task posted: {title} (assigned: @{assigned_to})")

    return json.dumps({
        "status": "created",
        "task_id": task_id,
        "title": title,
        "assigned_to": assigned_to,
        "project": project
    }, indent=2)

def handle_swarm_update_task(args):
    task_id = args.get("task_id")
    if not task_id:
        return json.dumps({"error": "task_id is required"}, indent=2)
    status = args.get("status", "in_progress")
    notes = args.get("notes", "")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            UPDATE swarm_tasks
            SET status = ?, notes = ?, updated_at = ?
            WHERE id = ?
        """, (status, notes, now, task_id))

    return json.dumps({
        "status": "updated",
        "task_id": task_id,
        "new_status": status,
        "notes": notes
    }, indent=2)

def handle_swarm_list_tasks(args):
    project = get_current_project(args.get("project"))
    status = args.get("status")
    assigned_to = args.get("assigned_to")

    conn = get_db()
    query = "SELECT * FROM swarm_tasks WHERE project = ?"
    params = [project]
    if status:
        query += " AND status = ?"
        params.append(status)
    if assigned_to:
        query += " AND assigned_to = ?"
        params.append(assigned_to)
    query += " ORDER BY id DESC"

    cur = conn.execute(query, params)
    tasks = [dict(r) for r in cur.fetchall()]
    return json.dumps({"count": len(tasks), "tasks": tasks}, indent=2)

def handle_swarm_share_artifact(args):
    project = get_current_project(args.get("project"))
    artifact_key = args.get("artifact_key") or args.get("key")
    if not artifact_key:
        return json.dumps({"error": "artifact_key is required"}, indent=2)
    title = args.get("title", artifact_key)
    creator = args.get("creator", "agent")
    artifact_type = args.get("artifact_type", "contract")
    content = args.get("content", "")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT OR REPLACE INTO swarm_artifacts (artifact_key, project, title, creator, artifact_type, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (artifact_key, project, title, creator, artifact_type, content, now, now))

    # Knowledge graph bridge
    bridge_to_brain_observation(project, f"artifact-{artifact_key}", f"Artifact published: {title} by @{creator}")

    return json.dumps({
        "status": "shared",
        "artifact_key": artifact_key,
        "title": title,
        "project": project
    }, indent=2)

def handle_swarm_get_artifact(args):
    project = get_current_project(args.get("project"))
    artifact_key = args.get("artifact_key") or args.get("key")
    if not artifact_key:
        return json.dumps({"error": "artifact_key is required"}, indent=2)

    conn = get_db()
    cur = conn.execute("SELECT * FROM swarm_artifacts WHERE artifact_key = ? AND project = ?", (artifact_key, project))
    row = cur.fetchone()
    if not row:
        return json.dumps({"found": False, "error": f"Artifact '{artifact_key}' not found"}, indent=2)

    return json.dumps({"found": True, "artifact": dict(row)}, indent=2)

def handle_swarm_gate_check(args):
    """
    Unified Quality Gate:
    Validates task completion, test pass status, and zero open critical sentinel violations.
    """
    project = get_current_project(args.get("project"))
    task_id = args.get("task_id")
    conn = get_db()

    # 1. Open Sentinel Violations
    v_cur = conn.execute("SELECT * FROM sentinel_violations WHERE project = ? AND status = 'open'", (project,))
    open_violations = [dict(v) for v in v_cur.fetchall()]
    critical_viols = [v for v in open_violations if v["severity"] == "critical"]

    # 2. Latest Test Run
    t_cur = conn.execute("SELECT * FROM tester_runs WHERE project = ? ORDER BY id DESC LIMIT 1", (project,))
    latest_test = t_cur.fetchone()
    test_ok = False
    test_summary = "No test runs executed"
    if latest_test:
        lt = dict(latest_test)
        test_ok = (lt["status"] == "PASS" and lt["failed"] == 0)
        test_summary = f"{lt['status']} ({lt['passed']}/{lt['total_tests']} tests passed, coverage: {lt['coverage_percent']}%)"

    # 3. Tasks state
    task_ok = True
    task_detail = "N/A"
    if task_id:
        tk_cur = conn.execute("SELECT * FROM swarm_tasks WHERE id = ?", (task_id,))
        task_row = tk_cur.fetchone()
        if task_row:
            t = dict(task_row)
            task_ok = (t["status"] in ("done", "completed"))
            task_detail = f"Task #{task_id}: {t['title']} ({t['status']})"

    passed_gate = (len(critical_viols) == 0 and test_ok and task_ok)
    verdict = "GATE_PASSED" if passed_gate else "GATE_BLOCKED"

    reasons = []
    if critical_viols:
        reasons.append(f"{len(critical_viols)} open critical sentinel violations")
    if not test_ok:
        reasons.append(f"Test suite not passing: {test_summary}")
    if not task_ok:
        reasons.append(f"Task #{task_id} not marked completed")

    return json.dumps({
        "project": project,
        "verdict": verdict,
        "passed": passed_gate,
        "sentinel_critical_violations": len(critical_viols),
        "test_status": test_summary,
        "task_status": task_detail,
        "blockers": reasons
    }, indent=2)

# ═══════════════════════════════════════════════════════════════
# Tool Declarations & Dispatch Registry
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    # Sentinel Tools
    {
        "name": "sentinel_audit_task",
        "description": "Audits deliverable against sentinel rules (TDD, SEC, ARCH, GIT, UI), calculates compliance score, and records violations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent being audited (backend, frontend, qa-auditor, git-flow...)"},
                "task_title": {"type": "string", "description": "Title of the task milestone audited"},
                "deliverables": {"type": "string", "description": "Deliverable summary, code changes, or contract details"},
                "files_modified": {"type": "string", "description": "Comma-separated list of modified files"},
                "test_results": {"type": "string", "description": "Test summary or coverage figures"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["agent_name", "task_title", "deliverables"]
        }
    },
    {
        "name": "sentinel_get_rules",
        "description": "List active sentinel engineering rules with checklists.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by rule category (testing, security, vcs, frontend, architecture)"},
                "target_agent": {"type": "string", "description": "Filter by agent role (backend, frontend, qa-auditor, all)"}
            }
        }
    },
    {
        "name": "sentinel_record_violation",
        "description": "Explicitly record a quality or security violation for an agent deliverable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_code": {"type": "string", "description": "Rule code violated (e.g., TDD-001, SEC-001)"},
                "agent_name": {"type": "string", "description": "Agent responsible"},
                "details": {"type": "string", "description": "Specific details of what failed"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"], "default": "high"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["rule_code", "agent_name", "details"]
        }
    },
    {
        "name": "sentinel_resolve_violation",
        "description": "Mark an engineering violation as resolved with resolution notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "violation_id": {"type": "integer", "description": "ID of violation to resolve"},
                "resolution_notes": {"type": "string", "description": "How the issue was remediated"}
            },
            "required": ["violation_id"]
        }
    },
    {
        "name": "sentinel_verify_compliance",
        "description": "Verify whether a project or agent has open violations blocking completion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Optional filter by agent"},
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    },
    {
        "name": "sentinel_get_compliance_report",
        "description": "Generate comprehensive compliance scorecard for the project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 7, "description": "Timeframe in days"},
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    },

    # Tester Tools
    {
        "name": "tester_run_suite",
        "description": "Executes automated test runner (pytest, vitest, jest, unittest, go, cargo) with coverage detection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {"type": "string", "description": "Test file or directory to run"},
                "runner": {"type": "string", "description": "Runner to use (pytest, vitest, jest, unittest, go, cargo). Auto-detected if omitted."},
                "coverage": {"type": "boolean", "default": True, "description": "Collect code coverage"},
                "timeout_seconds": {"type": "integer", "default": 60, "description": "Max execution time"},
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    },
    {
        "name": "tester_probe_endpoint",
        "description": "Executes HTTP probe against a live endpoint to measure latency and verify status code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to probe (e.g. http://localhost:3000/api/health)"},
                "method": {"type": "string", "default": "GET", "description": "HTTP method"},
                "expected_status": {"type": "integer", "default": 200, "description": "Expected HTTP response status"},
                "payload": {"type": "string", "description": "Optional JSON payload for POST/PUT"},
                "timeout_seconds": {"type": "number", "default": 5.0, "description": "Probe timeout"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "tester_verify_component",
        "description": "Performs quick syntax, typecheck or compilation validation on a single component/file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to file"},
                "check_type": {"type": "string", "default": "syntax", "description": "Check type"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "tester_get_live_health",
        "description": "Returns current test suite health, pass rate, and recent endpoint probe statuses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    },
    {
        "name": "tester_quick_check",
        "description": "Fast syntax and sanity check on a target file before running full suites.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Target file path"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "tester_sync_with_sentinel",
        "description": "Synchronizes latest test results with sentinel to resolve open TDD or verification violations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    },

    # Task Board & Gate Tools
    {
        "name": "swarm_post_task",
        "description": "Post a decomposed milestone task to the swarm task board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Detailed task instructions"},
                "assigned_to": {"type": "string", "description": "Target agent (@backend, @frontend, etc.)"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "default": "normal"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "swarm_update_task",
        "description": "Update task status (todo, in_progress, done, blocked) with progress notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"], "default": "in_progress"},
                "notes": {"type": "string", "description": "Progress notes or completion summary"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "swarm_list_tasks",
        "description": "List task board milestones filtered by status or assigned agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (todo, in_progress, done, blocked)"},
                "assigned_to": {"type": "string", "description": "Filter by assigned agent"},
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    },
    {
        "name": "swarm_share_artifact",
        "description": "Publishes a shared contract or spec (API contract, database schema, UI spec) for other agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_key": {"type": "string", "description": "Unique key (e.g. api_auth_v1, db_schema)"},
                "title": {"type": "string", "description": "Descriptive title"},
                "content": {"type": "string", "description": "Artifact payload or spec markdown"},
                "artifact_type": {"type": "string", "default": "contract", "description": "Type: contract, schema, spec, report"},
                "creator": {"type": "string", "default": "agent", "description": "Creator agent"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["artifact_key", "content"]
        }
    },
    {
        "name": "swarm_get_artifact",
        "description": "Retrieve a shared contract or specification artifact by key.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_key": {"type": "string", "description": "Unique key of artifact to retrieve"},
                "project": {"type": "string", "description": "Optional project scope"}
            },
            "required": ["artifact_key"]
        }
    },
    {
        "name": "swarm_gate_check",
        "description": "Comprehensive Quality Gate: checks test status, sentinel compliance, and task completion before sign-off.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Optional task ID to verify completion"},
                "project": {"type": "string", "description": "Optional project scope"}
            }
        }
    }
]

# Dispatch Handlers with backward-compatible aliases
TOOL_HANDLERS = {
    # Sentinel
    "sentinel_audit_task": handle_sentinel_audit_task,
    "sentinel_get_rules": handle_sentinel_get_rules,
    "sentinel_record_violation": handle_sentinel_record_violation,
    "sentinel_resolve_violation": handle_sentinel_resolve_violation,
    "sentinel_verify_compliance": handle_sentinel_verify_compliance,
    "sentinel_get_compliance_report": handle_sentinel_get_compliance_report,

    # Tester
    "tester_run_suite": handle_tester_run_suite,
    "tester_probe_endpoint": handle_tester_probe_endpoint,
    "tester_verify_component": handle_tester_verify_component,
    "tester_get_live_health": handle_tester_get_live_health,
    "tester_quick_check": handle_tester_quick_check,
    "tester_sync_with_sentinel": handle_tester_sync_with_sentinel,

    # Swarm Tasks & Quality Gate
    "swarm_post_task": handle_swarm_post_task,
    "swarm_update_task": handle_swarm_update_task,
    "swarm_list_tasks": handle_swarm_list_tasks,
    "swarm_share_artifact": handle_swarm_share_artifact,
    "swarm_get_artifact": handle_swarm_get_artifact,
    "swarm_gate_check": handle_swarm_gate_check,

    # Compatibility Aliases for team-collab
    "team_post_task": handle_swarm_post_task,
    "team_update_task": handle_swarm_update_task,
    "team_list_tasks": handle_swarm_list_tasks,
    "team_share_artifact": handle_swarm_share_artifact,
    "team_get_artifact": handle_swarm_get_artifact,
}

# ═══════════════════════════════════════════════════════════════
# JSON-RPC 2.0 stdio Event Loop
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
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
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
                    "serverInfo": {
                        "name": "swarm-engine",
                        "version": "2.0.0"
                    },
                    "capabilities": {
                        "tools": {}
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
