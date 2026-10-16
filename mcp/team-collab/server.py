#!/usr/bin/env python3
"""
Team Collaboration MCP Server (Team Swarm Bus)
Enables multi-agent communication, project-scoped shared task board, status sync,
handoffs, and artifact exchange between specialized sub-agents across sessions.
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
from pathlib import Path
from contextlib import contextmanager

class ManagedConnection(sqlite3.Connection):
    """Close SQLite handles deterministically when short-lived tool scopes end."""
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

# Setup paths
DEFAULT_TEAM_DIR = Path.home() / ".opencode" / "team"
DB_PATH = Path(os.environ.get("OPENCODE_TEAM_DB", DEFAULT_TEAM_DIR / "team_collab.db"))

@contextmanager
def db_write_lock(conn, max_retries=10, base_delay=0.03):
    """
    Acquires immediate write lock on SQLite with exponential backoff and jitter.
    Guarantees that multiple concurrent OpenCode windows/processes never deadlock
    or fail with 'database is locked'.
    """
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

def format_relative_time(iso_str):
    if not iso_str:
        return "desconocido"
    try:
        t = datetime.datetime.fromisoformat(iso_str)
        now = datetime.datetime.now(datetime.timezone.utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        diff_sec = max(0, int((now - t).total_seconds()))
        if diff_sec < 5:
            return "hace un momento"
        if diff_sec < 60:
            return f"hace {diff_sec}s"
        diff_min = diff_sec // 60
        if diff_min < 60:
            return f"hace {diff_min}m"
        diff_hours = diff_min // 60
        if diff_hours < 24:
            return f"hace {diff_hours}h"
        return f"hace {diff_hours // 24}d"
    except Exception:
        return iso_str

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

def get_current_branch():
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except Exception:
        return ""

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None, factory=ManagedConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    with conn:
        # Agent status registry with compound primary key for project isolation
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_agents (
                agent_name TEXT NOT NULL,
                project TEXT NOT NULL DEFAULT 'default',
                status TEXT NOT NULL DEFAULT 'idle',
                current_task TEXT DEFAULT '',
                blockers TEXT DEFAULT '',
                window_id TEXT DEFAULT '',
                last_heartbeat TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (agent_name, project)
            )
        """)
        # Feed / Messages with project scope
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'status',
                priority TEXT NOT NULL DEFAULT 'normal',
                created_at TEXT NOT NULL
            )
        """)
        # Shared Task Board with project scope
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_tasks (
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
        # Shared Artifacts with project tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_artifacts (
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
        # Reactive Work Triggers between agents
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT 'default',
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                trigger_type TEXT NOT NULL DEFAULT 'contract',
                artifact_key TEXT DEFAULT '',
                summary TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                resolved_at TEXT DEFAULT ''
            )
        """)

        # Migration helper for existing databases missing columns or compound keys
        for col, col_def in [("project", "TEXT NOT NULL DEFAULT 'default'"),
                             ("window_id", "TEXT DEFAULT ''"),
                             ("last_heartbeat", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE team_agents ADD COLUMN {col} {col_def}")
            except sqlite3.OperationalError:
                pass

        for table in ["team_messages", "team_tasks", "team_artifacts"]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN project TEXT NOT NULL DEFAULT 'default'")
            except sqlite3.OperationalError:
                pass

        # Check if team_agents has compound primary key (agent_name, project)
        try:
            info = conn.execute("PRAGMA table_info(team_agents)").fetchall()
            pk_cols = [c["name"] for c in info if c["pk"] > 0]
            if len(pk_cols) < 2 or "project" not in pk_cols:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS team_agents_migrated (
                        agent_name TEXT NOT NULL,
                        project TEXT NOT NULL DEFAULT 'default',
                        status TEXT NOT NULL DEFAULT 'idle',
                        current_task TEXT DEFAULT '',
                        blockers TEXT DEFAULT '',
                        window_id TEXT DEFAULT '',
                        last_heartbeat TEXT DEFAULT '',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (agent_name, project)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO team_agents_migrated (agent_name, project, status, current_task, blockers, window_id, last_heartbeat, updated_at)
                    SELECT agent_name, COALESCE(project, 'default'), status, current_task, blockers, window_id, last_heartbeat, updated_at
                    FROM team_agents
                """)
                conn.execute("DROP TABLE team_agents")
                conn.execute("ALTER TABLE team_agents_migrated RENAME TO team_agents")
        except Exception:
            pass

        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_team_artifacts_key_proj ON team_artifacts(artifact_key, project)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_team_agents_name_proj ON team_agents(agent_name, project)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_triggers_to_proj ON team_triggers(to_agent, project, status)")
    return conn

# Tool Definitions
TOOLS = [
    {
        "name": "team_broadcast",
        "description": "Broadcast an update, handoff notification, or decision to the project's team bus so all sub-agents stay synchronized.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "description": "Agent name sending the message (e.g. 'orchestrator', 'backend', 'frontend', 'git-flow', 'qa-auditor', 'devops')"},
                "message": {"type": "string", "description": "Message content or progress summary"},
                "category": {"type": "string", "enum": ["status", "handoff", "question", "announcement", "warning"], "description": "Message classification"},
                "priority": {"type": "string", "enum": ["normal", "high", "urgent"], "description": "Priority level"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["sender", "message"]
        }
    },
    {
        "name": "team_read_feed",
        "description": "Read recent broadcast messages from teammates to catch up on what other agents completed in current or past sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of messages to retrieve (default 10)"},
                "category": {"type": "string", "description": "Optional category filter"},
                "since_id": {"type": "integer", "description": "Retrieve messages after this message ID"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            }
        }
    },
    {
        "name": "team_set_status",
        "description": "Update an agent's current working status, task, and any blockers on the project team board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent name (e.g. 'orchestrator', 'backend', 'frontend', 'git-flow', 'qa-auditor', 'devops')"},
                "status": {"type": "string", "enum": ["idle", "working", "blocked", "ready_for_review"], "description": "Current agent status"},
                "current_task": {"type": "string", "description": "Brief description of the current task being executed"},
                "blockers": {"type": "string", "description": "Any blockers or dependencies (optional)"},
                "window_id": {"type": "string", "description": "Optional window or terminal identifier (e.g. 'backend-term', 'window-1')"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["agent_name", "status"]
        }
    },
    {
        "name": "team_get_status",
        "description": "Retrieve a real-time snapshot of the development team for this project: active agents, tasks, artifacts, and cross-session progress.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            }
        }
    },
    {
        "name": "team_get_live_activity",
        "description": "Get real-time live activity across all terminal windows and sub-agents for this project: active windows, who is currently working, time since last activity, in-progress tasks, and new artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project scope (defaults to current project)"},
                "max_age_minutes": {"type": "integer", "description": "Minutes threshold to consider an agent actively working (default 30)"}
            }
        }
    },
    {
        "name": "team_heartbeat",
        "description": "Send a periodic heartbeat from the current window/session to notify all other OpenCode windows that this agent is actively running.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent name (e.g. 'backend', 'frontend', 'git-flow', 'qa-auditor', 'orchestrator')"},
                "window_id": {"type": "string", "description": "Optional terminal window or session identifier (e.g. 'window-backend', 'term-1')"},
                "current_task": {"type": "string", "description": "Optional brief task description"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["agent_name"]
        }
    },
    {
        "name": "team_post_task",
        "description": "Post a task on the shared team board (used by Orchestrator or agents to delegate work across sessions).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short, actionable task title"},
                "description": {"type": "string", "description": "Detailed task instructions, acceptance criteria, or context"},
                "assigned_to": {"type": "string", "description": "Target agent (e.g. 'backend', 'frontend', 'git-flow', 'qa-auditor', 'devops')"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "description": "Task priority"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "team_claim_task",
        "description": "Claim a task from the team board and mark it in_progress.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to claim"},
                "agent_name": {"type": "string", "description": "Agent claiming the task"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["task_id", "agent_name"]
        }
    },
    {
        "name": "team_update_task",
        "description": "Update the progress, status, or notes of a task on the team board.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to update"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "blocked", "review", "completed"], "description": "New task status"},
                "notes": {"type": "string", "description": "Progress notes, results, or links to shared artifacts"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["task_id", "status"]
        }
    },
    {
        "name": "team_list_tasks",
        "description": "List tasks from the shared team board with optional status or assignee filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (todo, in_progress, review, completed)"},
                "assigned_to": {"type": "string", "description": "Filter by assigned agent"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            }
        }
    },
    {
        "name": "team_share_artifact",
        "description": "Share a key contract or artifact (API spec, DB schema, UI component interface, test report) with other agents across sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "creator": {"type": "string", "description": "Agent creating this artifact"},
                "artifact_key": {"type": "string", "description": "Unique key (e.g. 'auth-api-spec', 'user-table-schema', 'navbar-props')"},
                "title": {"type": "string", "description": "Descriptive title"},
                "artifact_type": {"type": "string", "enum": ["api_spec", "db_schema", "ui_contract", "pr_plan", "test_report", "general"], "description": "Artifact type"},
                "content": {"type": "string", "description": "Full artifact content, specification, or code contract"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["creator", "artifact_key", "title", "content"]
        }
    },
    {
        "name": "team_get_artifact",
        "description": "Retrieve a shared artifact by its key to consume contracts or specifications created by other agents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_key": {"type": "string", "description": "Unique key of the artifact"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["artifact_key"]
        }
    },
    {
        "name": "team_handoff",
        "description": "Directly hand off work from one specialist to another across turns or sessions, updating task state and posting a notification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_agent": {"type": "string", "description": "Agent releasing the task (e.g. 'backend')"},
                "to_agent": {"type": "string", "description": "Target agent receiving the handoff (e.g. 'frontend', 'git-flow', 'qa-auditor')"},
                "task_id": {"type": "integer", "description": "Optional task ID being handed off"},
                "notes": {"type": "string", "description": "Handoff context, instructions, or pointers to artifacts"},
                "artifact_key": {"type": "string", "description": "Optional artifact key containing contracts or deliverables"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["from_agent", "to_agent", "notes"]
        }
    },
    {
        "name": "team_trigger_agent",
        "description": "Emit a reactive work trigger directed to another agent (e.g. backend triggers frontend or qa-auditor) with an attached contract, immediately notifying and activating the target agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_agent": {"type": "string", "description": "Agent initiating trigger (e.g. 'backend')"},
                "to_agent": {"type": "string", "description": "Target agent to activate (e.g. 'frontend', 'qa-auditor')"},
                "trigger_type": {"type": "string", "enum": ["contract", "api_spec", "db_schema", "review", "deploy"], "description": "Type of trigger"},
                "artifact_key": {"type": "string", "description": "Optional artifact or contract key"},
                "summary": {"type": "string", "description": "Description of work required for the target agent"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["to_agent", "summary"]
        }
    },
    {
        "name": "team_check_triggers",
        "description": "Check and claim pending reactive triggers assigned to an agent, retrieving the required contracts and instructions to start work immediately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name of agent checking triggers (e.g. 'frontend')"},
                "claim": {"type": "boolean", "description": "Whether to mark pending triggers as claimed (default true)"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["agent_name"]
        }
    },
    {
        "name": "team_wait_for_task",
        "description": "Wait for a task to reach completed or ready_for_review status without halting OpenCode iteration (polls safely up to timeout).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID of the task to wait for"},
                "timeout_seconds": {"type": "integer", "description": "Maximum seconds to wait (default 30, max 120)"},
                "project": {"type": "string", "description": "Project scope (defaults to current project)"}
            },
            "required": ["task_id"]
        }
    }
]

# Tool Implementations
def normalize_agent_name(name):
    if not name:
        return ""
    n = str(name).strip().lower()
    if n.startswith("@"):
        n = n[1:]
    if n in ("test", "tester", "qa", "test-auditor"):
        return "qa-auditor"
    if n in ("git", "github"):
        return "git-flow"
    if n in ("lead", "arch", "architect"):
        return "orchestrator"
    return n

def tool_team_broadcast(args):
    sender = normalize_agent_name(args.get("sender", ""))
    message = args.get("message", "").strip()
    category = args.get("category", "status").strip().lower()
    priority = args.get("priority", "normal").strip().lower()
    project = get_current_project(args.get("project"))

    if not sender or not message:
        return "Error: sender and message must not be empty."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO team_messages (project, sender, message, category, priority, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project, sender, message, category, priority, now))

    return f"✓ Broadcasted message from @{sender} [{project} | {category.upper()}]: '{message}'"

def tool_team_read_feed(args):
    limit = int(args.get("limit", 10))
    category = args.get("category", "")
    since_id = args.get("since_id")
    project = get_current_project(args.get("project"))

    conn = get_db()
    sql = "SELECT id, sender, message, category, priority, created_at FROM team_messages WHERE (project = ? OR project = 'default')"
    params = [project]
    if category:
        sql += " AND category = ?"
        params.append(category)
    if since_id is not None:
        sql += " AND id > ?"
        params.append(int(since_id))

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cur = conn.execute(sql, params)
    rows = cur.fetchall()

    if not rows:
        return f"No recent team messages found for project '{project}'."

    lines = [f"=== Team Activity Feed [{project}] ({len(rows)} message(s)) ==="]
    for r in reversed(rows):
        rel = format_relative_time(r['created_at'])
        lines.append(f"#{r['id']} [@{r['sender']}] ({r['category'].upper()}, {rel}): {r['message']}")

    return "\n".join(lines)

def tool_team_set_status(args):
    agent_name = normalize_agent_name(args.get("agent_name", ""))
    status = args.get("status", "idle").strip().lower()
    current_task = args.get("current_task", "").strip()
    blockers = args.get("blockers", "").strip()
    window_id = args.get("window_id", "").strip() or os.environ.get("OPENCODE_WINDOW", "").strip()
    project = get_current_project(args.get("project"))

    if not agent_name:
        return "Error: agent_name must not be empty."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO team_agents (agent_name, project, status, current_task, blockers, window_id, last_heartbeat, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_name, project) DO UPDATE SET
                status = excluded.status,
                current_task = excluded.current_task,
                blockers = excluded.blockers,
                window_id = CASE WHEN excluded.window_id != '' THEN excluded.window_id ELSE team_agents.window_id END,
                last_heartbeat = excluded.last_heartbeat,
                updated_at = excluded.updated_at
        """, (agent_name, project, status, current_task, blockers, window_id, now, now))

    win_info = f" [Window: {window_id}]" if window_id else ""
    return f"✓ Status updated for @{agent_name}{win_info} [{project}]: {status.upper()} (Task: {current_task or 'none'})"

def tool_team_heartbeat(args):
    agent_name = normalize_agent_name(args.get("agent_name", ""))
    window_id = args.get("window_id", "").strip() or os.environ.get("OPENCODE_WINDOW", "").strip()
    current_task = args.get("current_task", "").strip()
    project = get_current_project(args.get("project"))

    if not agent_name:
        return "Error: agent_name is required."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO team_agents (agent_name, project, status, current_task, blockers, window_id, last_heartbeat, updated_at)
            VALUES (?, ?, 'working', ?, '', ?, ?, ?)
            ON CONFLICT(agent_name, project) DO UPDATE SET
                current_task = CASE WHEN excluded.current_task != '' THEN excluded.current_task ELSE team_agents.current_task END,
                window_id = CASE WHEN excluded.window_id != '' THEN excluded.window_id ELSE team_agents.window_id END,
                last_heartbeat = excluded.last_heartbeat,
                updated_at = excluded.updated_at
        """, (agent_name, project, current_task, window_id, now, now))

    win_str = f" [{window_id}]" if window_id else ""
    return f"💓 Heartbeat acknowledged for @{agent_name}{win_str} in [{project}] at {now}"

def tool_team_get_status(args):
    project = get_current_project(args.get("project"))
    branch = get_current_branch()
    branch_str = f" (branch: `{branch}`)" if branch else ""

    conn = get_db()

    # Query agents for this project
    cur_agents = conn.execute("""
        SELECT agent_name, status, current_task, blockers, window_id, last_heartbeat, updated_at
        FROM team_agents
        WHERE project = ? OR project = 'default'
        ORDER BY agent_name
    """, (project,))
    agents = cur_agents.fetchall()

    # Query tasks for this project
    cur_tasks = conn.execute("""
        SELECT id, title, assigned_to, status, priority, notes
        FROM team_tasks
        WHERE project = ?
        ORDER BY CASE status
            WHEN 'in_progress' THEN 1
            WHEN 'todo' THEN 2
            WHEN 'review' THEN 3
            WHEN 'blocked' THEN 4
            WHEN 'completed' THEN 5
            ELSE 6 END, id DESC
        LIMIT 20
    """, (project,))
    tasks = cur_tasks.fetchall()

    # Query shared artifacts
    cur_artifacts = conn.execute("""
        SELECT artifact_key, title, creator, artifact_type, updated_at
        FROM team_artifacts
        WHERE project = ?
        ORDER BY updated_at DESC LIMIT 10
    """, (project,))
    artifacts = cur_artifacts.fetchall()

    # Query latest 3 messages
    cur_feed = conn.execute("""
        SELECT sender, message, category, created_at
        FROM team_messages
        WHERE project = ?
        ORDER BY id DESC LIMIT 3
    """, (project,))
    feed = cur_feed.fetchall()

    out = [
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║  ⚡ ᴏᴘᴇɴᴄᴏᴅᴇ ⟪ ꜱᴡᴀʀᴍ ᴇᴅɪᴛɪᴏɴ ⟫  |  Project: {project:<15} ║",
        f"╚══════════════════════════════════════════════════════════════╝\n",
        f"**Project Workspace**: `{project}`{branch_str}\n"
    ]

    # Agents Roster
    out.append("### 👥 Sub-Agents Status")
    known_roles = {
        "orchestrator": ("#8B5CF6", "Lead Architect & Coordination"),
        "backend": ("#3B82F6", "APIs, Databases, Migrations & TDD"),
        "frontend": ("#EC4899", "UI/UX, Components & Micro-interactions"),
        "git-flow": ("#10B981", "Git/GitHub, Conventional Commits & PRs"),
        "qa-auditor": ("#F59E0B", "Verification Loop & Security Audits"),
        "devops": ("#06B6D4", "Docker, Containers & CI/CD Pipelines")
    }

    registered_agents = {a["agent_name"]: a for a in agents}
    for role, (color, desc) in known_roles.items():
        if role in registered_agents:
            a = registered_agents[role]
            icon = "🟢" if a["status"] == "working" else "🟡" if a["status"] == "ready_for_review" else "🔴" if a["status"] == "blocked" else "⚪"
            task = f" → `{a['current_task']}`" if a["current_task"] else ""
            blocker = f" [BLOCKER: {a['blockers']}]" if a["blockers"] else ""
            win = f" [{a['window_id']}]" if a['window_id'] else ""
            time_val = a['last_heartbeat'] or a['updated_at']
            rel = format_relative_time(time_val)
            out.append(f"• {icon} **@{role}**{win} ({a['status'].upper()}, {rel}):{task}{blocker}")
        else:
            out.append(f"• ⚪ **@{role}** (IDLE): Ready for assignment")

    # Tasks Board
    out.append("\n### 📋 Project Task Board (Cross-Session)")
    if tasks:
        for t in tasks:
            assigned = f"[@{t['assigned_to']}]" if t['assigned_to'] else "[UNASSIGNED]"
            st = t['status'].upper()
            status_icon = "⏳" if t['status'] == 'in_progress' else "✅" if t['status'] == 'completed' else "📝" if t['status'] == 'todo' else "👀"
            out.append(f"• {status_icon} **#{t['id']}** {assigned} {t['title']} (`{st}`, Priority: {t['priority']})")
            if t['notes']:
                out.append(f"  └ Notes: {t['notes']}")
    else:
        out.append("• No tasks posted for this project yet. Use `team_post_task` to assign work.")

    # Shared Artifacts
    if artifacts:
        out.append("\n### 📦 Shared Project Artifacts & Contracts")
        for art in artifacts:
            rel = format_relative_time(art['updated_at'])
            out.append(f"• **`{art['artifact_key']}`** ({art['title']}) [{art['artifact_type'].upper()}] - by @{art['creator']} ({rel})")

    # Latest Activity
    if feed:
        out.append("\n### 💬 Recent Team Announcements")
        for m in feed:
            rel = format_relative_time(m['created_at'])
            out.append(f"• **@{m['sender']}** ({m['category']}, {rel}): {m['message']}")

    return "\n".join(out)

def tool_team_get_live_activity(args):
    project = get_current_project(args.get("project"))
    max_age_min = int(args.get("max_age_minutes", 30))
    branch = get_current_branch()
    branch_str = f" (branch: `{branch}`)" if branch else ""

    conn = get_db()
    # Query all agents for this project
    cur_agents = conn.execute("""
        SELECT agent_name, status, current_task, blockers, window_id, last_heartbeat, updated_at
        FROM team_agents
        WHERE project = ? OR project = 'default'
        ORDER BY updated_at DESC
    """, (project,))
    agents = cur_agents.fetchall()

    # Query active tasks (in_progress, review, todo)
    cur_tasks = conn.execute("""
        SELECT id, title, assigned_to, status, priority, updated_at
        FROM team_tasks
        WHERE project = ? AND status IN ('in_progress', 'todo', 'review')
        ORDER BY CASE status WHEN 'in_progress' THEN 1 WHEN 'review' THEN 2 ELSE 3 END, id DESC
        LIMIT 10
    """, (project,))
    active_tasks = cur_tasks.fetchall()

    # Query recent artifacts
    cur_art = conn.execute("""
        SELECT artifact_key, title, creator, artifact_type, updated_at
        FROM team_artifacts
        WHERE project = ?
        ORDER BY updated_at DESC LIMIT 5
    """, (project,))
    recent_artifacts = cur_art.fetchall()

    # Query latest feed
    cur_feed = conn.execute("""
        SELECT id, sender, message, category, priority, created_at
        FROM team_messages
        WHERE project = ?
        ORDER BY id DESC LIMIT 5
    """, (project,))
    recent_messages = cur_feed.fetchall()

    now_clock = datetime.datetime.now().strftime("%H:%M:%S")
    out = [
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  ⚡ ᴏᴘᴇɴᴄᴏᴅᴇ ⟪ ꜱᴡᴀʀᴍ ᴇᴅɪᴛɪᴏɴ ⟫  |  Project: {project:<15} ║",
        "║  📡 REAL-TIME MULTI-WINDOW ACTIVITY MONITOR                  ║",
        "╚══════════════════════════════════════════════════════════════╝",
        f"**Workspace**: `{project}`{branch_str} | **Live Clock**: `{now_clock}`\n",
        "### 🖥️ Active Windows & Agent Sessions"
    ]

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if not agents:
        out.append("• No active sessions recorded yet for this project.")
    else:
        for a in agents:
            time_val = a['last_heartbeat'] or a['updated_at']
            rel_time = format_relative_time(time_val)
            is_recent = False
            try:
                t = datetime.datetime.fromisoformat(time_val)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=datetime.timezone.utc)
                if (now_utc - t).total_seconds() <= max_age_min * 60:
                    is_recent = True
            except Exception:
                pass

            win_str = f" [Window: `{a['window_id']}`]" if a['window_id'] else ""
            if a['status'] == 'working' and is_recent:
                icon = "🟢 ACTIVE"
            elif a['status'] == 'blocked':
                icon = "🔴 BLOCKED"
            elif a['status'] == 'ready_for_review':
                icon = "🟡 REVIEW"
            elif not is_recent:
                icon = "⚪ IDLE/OFFLINE"
            else:
                icon = f"⚪ {a['status'].upper()}"

            task_info = f" → `{a['current_task']}`" if a['current_task'] else " (No current task)"
            blocker_info = f" ⚠️ **Blocker**: {a['blockers']}" if a['blockers'] else ""
            out.append(f"• **@{a['agent_name']}**{win_str} [{icon}] ({rel_time}):{task_info}{blocker_info}")

    out.append("\n### 📋 Tasks In Progress Across Windows")
    if active_tasks:
        for t in active_tasks:
            who = f"@{t['assigned_to']}" if t['assigned_to'] else "Unassigned"
            icon = "⏳" if t['status'] == 'in_progress' else "👀" if t['status'] == 'review' else "📝"
            rel = format_relative_time(t['updated_at'])
            out.append(f"• {icon} **#{t['id']}** [{t['status'].upper()}] {t['title']} ({who}, {rel})")
    else:
        out.append("• No active tasks currently.")

    if recent_artifacts:
        out.append("\n### 📦 Recently Published Contracts / Specs")
        for art in recent_artifacts:
            rel = format_relative_time(art['updated_at'])
            out.append(f"• **`{art['artifact_key']}`** ({art['title']}) [{art['artifact_type'].upper()}] by @{art['creator']} ({rel})")

    if recent_messages:
        out.append("\n### 💬 Latest Cross-Window Messages")
        for m in recent_messages:
            rel = format_relative_time(m['created_at'])
            out.append(f"• [#{m['id']}] **@{m['sender']}** ({m['category']}, {rel}): {m['message']}")

    return "\n".join(out)

def tool_team_post_task(args):
    title = args.get("title", "").strip()
    description = args.get("description", "").strip()
    assigned_to = normalize_agent_name(args.get("assigned_to", ""))
    priority = args.get("priority", "normal").strip().lower()
    project = get_current_project(args.get("project"))

    if not title:
        return "Error: title must not be empty."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            INSERT INTO team_tasks (project, title, description, assigned_to, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'todo', ?, ?, ?)
        """, (project, title, description, assigned_to, priority, now, now))
        task_id = cur.lastrowid

    target = f"assigned to @{assigned_to}" if assigned_to else "unassigned"
    return f"✓ Task #{task_id} posted on [{project}] board: '{title}' ({target}, Priority: {priority})"

def tool_team_claim_task(args):
    task_id = int(args.get("task_id", 0))
    agent_name = normalize_agent_name(args.get("agent_name", ""))
    project = get_current_project(args.get("project"))

    if not task_id or not agent_name:
        return "Error: task_id and agent_name are required."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        cur = conn.execute("""
            UPDATE team_tasks
            SET assigned_to = ?, status = 'in_progress', updated_at = ?
            WHERE id = ?
        """, (agent_name, now, task_id))
        if cur.rowcount == 0:
            return f"Task #{task_id} not found."

        cur_task = conn.execute("SELECT title, assigned_to, project FROM team_tasks WHERE id = ?", (task_id,)).fetchone()
        task_title = cur_task["title"] if cur_task else f"Task #{task_id}"

        conn.execute("""
            INSERT INTO team_agents (agent_name, project, status, current_task, updated_at)
            VALUES (?, ?, 'working', ?, ?)
            ON CONFLICT(agent_name, project) DO UPDATE SET
                status = 'working',
                current_task = excluded.current_task,
                updated_at = excluded.updated_at
        """, (agent_name, project, task_title, now))

    return f"✓ Task #{task_id} ('{task_title}') claimed by @{agent_name} in [{project}] and marked IN_PROGRESS."

def tool_team_update_task(args):
    task_id = int(args.get("task_id", 0))
    status = args.get("status", "in_progress").strip().lower()
    notes = args.get("notes", "").strip()

    if not task_id:
        return "Error: task_id is required."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        cur_task = conn.execute("SELECT title, assigned_to, project FROM team_tasks WHERE id = ?", (task_id,)).fetchone()
        if not cur_task:
            return f"Task #{task_id} not found."

        assigned_to = cur_task["assigned_to"]
        task_proj = cur_task["project"] or "default"
        task_title = cur_task["title"]

        conn.execute("""
            UPDATE team_tasks
            SET status = ?, notes = CASE WHEN ? != '' THEN ? ELSE notes END, updated_at = ?
            WHERE id = ?
        """, (status, notes, notes, now, task_id))

        # If completed or cancelled, check if assigned agent has any other in_progress tasks
        if status in ("completed", "cancelled") and assigned_to:
            cur_other = conn.execute("""
                SELECT COUNT(*) FROM team_tasks
                WHERE assigned_to = ? AND project = ? AND status = 'in_progress' AND id != ?
            """, (assigned_to, task_proj, task_id))
            if cur_other.fetchone()[0] == 0:
                conn.execute("""
                    INSERT INTO team_agents (agent_name, project, status, current_task, updated_at)
                    VALUES (?, ?, 'idle', '', ?)
                    ON CONFLICT(agent_name, project) DO UPDATE SET
                        status = 'idle',
                        current_task = '',
                        updated_at = excluded.updated_at
                """, (assigned_to, task_proj, now))

    if status == "completed":
        auto_checkpoint_team(task_proj, "task_completed", f"Task #{task_id} ('{task_title}') completed by @{assigned_to or 'team'}")

    return f"✓ Task #{task_id} updated to status '{status.upper()}'."

def tool_team_list_tasks(args):
    status = args.get("status", "")
    assigned_to = normalize_agent_name(args.get("assigned_to", ""))
    project = get_current_project(args.get("project"))

    conn = get_db()
    sql = "SELECT id, title, description, assigned_to, status, priority, notes, updated_at FROM team_tasks WHERE project = ?"
    params = [project]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if assigned_to:
        sql += " AND assigned_to = ?"
        params.append(assigned_to)

    sql += " ORDER BY id DESC LIMIT 25"
    cur = conn.execute(sql, params)
    rows = cur.fetchall()

    if not rows:
        return f"No tasks found for project '{project}' matching criteria."

    lines = [f"Shared Task Board for [{project}] ({len(rows)} item(s)):"]
    for r in rows:
        assignee = f"@{r['assigned_to']}" if r['assigned_to'] else "Unassigned"
        lines.append(f"• #{r['id']} [{r['status'].upper()}] {r['title']} ({assignee}, Priority: {r['priority']})")
        if r["notes"]:
            lines.append(f"  └ Notes: {r['notes']}")

    return "\n".join(lines)

def tool_team_share_artifact(args):
    creator = normalize_agent_name(args.get("creator", ""))
    artifact_key = args.get("artifact_key", "").strip()
    title = args.get("title", "").strip()
    artifact_type = args.get("artifact_type", "general").strip()
    content = args.get("content", "").strip()
    project = get_current_project(args.get("project"))

    if not creator or not artifact_key or not title or not content:
        return "Error: creator, artifact_key, title, and content must all be provided."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO team_artifacts (artifact_key, project, title, creator, artifact_type, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_key, project) DO UPDATE SET
                title = excluded.title,
                creator = excluded.creator,
                artifact_type = excluded.artifact_type,
                content = excluded.content,
                updated_at = excluded.updated_at
        """, (artifact_key, project, title, creator, artifact_type, content, now, now))

    # Reactive Cross-Agent Triggering:
    # If backend publishes API spec or schema, trigger frontend to begin consuming it
    if creator == "backend" or artifact_type in ("api_spec", "db_schema", "schema"):
        dispatch_trigger(
            from_agent=creator,
            to_agent="frontend",
            trigger_type=artifact_type,
            artifact_key=artifact_key,
            summary=f"Backend published contract '{artifact_key}' ({title}). Frontend action required: integrate in UI components.",
            project=project
        )

    # Automatic Zero-Compaction checkpoint
    auto_checkpoint_team(project, "artifact_published", f"Artifact '{artifact_key}' ({title}) published by @{creator}")

    return f"✓ Artifact '{artifact_key}' ({title}) saved by @{creator} in [{project}]. Reactive trigger dispatched to @frontend."

def tool_team_get_artifact(args):
    artifact_key = args.get("artifact_key", "").strip()
    project = get_current_project(args.get("project"))
    if not artifact_key:
        return "Error: artifact_key is required."

    conn = get_db()
    cur = conn.execute("""
        SELECT artifact_key, project, title, creator, artifact_type, content, updated_at
        FROM team_artifacts
        WHERE artifact_key = ? AND (project = ? OR project = 'default')
        ORDER BY (project = ?) DESC LIMIT 1
    """, (artifact_key, project, project))
    r = cur.fetchone()

    if not r:
        return f"Artifact '{artifact_key}' not found on [{project}] team board."

    return f"# [{r['artifact_type'].upper()}] {r['title']} (Key: {r['artifact_key']})\nProject: {r['project']} | Shared by: @{r['creator']} at {r['updated_at']}\n\n{r['content']}"

def tool_team_handoff(args):
    from_agent = normalize_agent_name(args.get("from_agent", ""))
    to_agent = normalize_agent_name(args.get("to_agent", ""))
    notes = args.get("notes", "").strip()
    task_id = args.get("task_id")
    artifact_key = args.get("artifact_key", "")
    project = get_current_project(args.get("project"))

    if not from_agent or not to_agent or not notes:
        return "Error: from_agent, to_agent, and notes are required."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        # Update from_agent to idle
        conn.execute("""
            INSERT INTO team_agents (agent_name, project, status, current_task, updated_at)
            VALUES (?, ?, 'idle', '', ?)
            ON CONFLICT(agent_name, project) DO UPDATE SET
                status = 'idle',
                current_task = '',
                updated_at = excluded.updated_at
        """, (from_agent, project, now))

        # Update to_agent to working
        current_task_desc = f"Handoff from @{from_agent}: {notes[:50]}"
        conn.execute("""
            INSERT INTO team_agents (agent_name, project, status, current_task, updated_at)
            VALUES (?, ?, 'working', ?, ?)
            ON CONFLICT(agent_name, project) DO UPDATE SET
                status = 'working',
                current_task = excluded.current_task,
                updated_at = excluded.updated_at
        """, (to_agent, project, current_task_desc, now))

        # If task_id provided, reassign or update task
        if task_id:
            conn.execute("""
                UPDATE team_tasks
                SET assigned_to = ?, status = 'in_progress', notes = ?, updated_at = ?
                WHERE id = ?
            """, (to_agent, f"Handed off from @{from_agent}: {notes}", now, int(task_id)))

        # Broadcast handoff announcement
        art_info = f" (Artifact: `{artifact_key}`)" if artifact_key else ""
        msg = f"🔄 HANDOFF: @{from_agent} handed off work to @{to_agent}.{art_info} Notes: {notes}"
        conn.execute("""
            INSERT INTO team_messages (project, sender, message, category, priority, created_at)
            VALUES (?, ?, ?, 'handoff', 'high', ?)
        """, (project, from_agent, msg, now))

    # Emit reactive trigger and auto-checkpoint
    dispatch_trigger(from_agent, to_agent, "handoff", artifact_key, notes, project)
    auto_checkpoint_team(project, "handoff", f"Handoff @{from_agent} ➔ @{to_agent}: {notes}")

    return f"✓ Handoff completed in [{project}]: @{from_agent} → @{to_agent}. {msg}"

# ─────────────────────────────────────────────────────────────
# REACTIVE WORK TRIGGERS & AUTO-CHECKPOINT HELPERS
# ─────────────────────────────────────────────────────────────

def auto_checkpoint_team(project, event_type, details):
    """Safely updates context_memory.db with auto-checkpoint on key milestones."""
    try:
        mem_db_path = Path(os.environ.get("OPENCODE_MEMORY_DB", Path.home() / ".opencode" / "memory" / "context_memory.db"))
        if mem_db_path.parent.exists():
            conn = sqlite3.connect(str(mem_db_path), timeout=10.0)
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            now_human = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content = f"# Auto-Checkpoint: [{project}]\n**Timestamp**: {now_human} UTC\n**Milestone Event**: `{event_type}`\n\n### Details\n{details}\n"
            conn.execute("""
                INSERT INTO memories (key, category, content, tags, project, created_at, updated_at)
                VALUES (?, 'decision', ?, 'auto_checkpoint, zero_compaction', ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    content = excluded.content,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
            """, (f"{project}-checkpoint-latest", content, project, now_iso, now_iso))
            conn.commit()
            conn.close()
    except Exception:
        pass

def dispatch_trigger(from_agent, to_agent, trigger_type, artifact_key, summary, project):
    """Emits a reactive trigger row, updates target agent to working, and broadcasts notification."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_db()
    with db_write_lock(conn):
        conn.execute("""
            INSERT INTO team_triggers (project, from_agent, to_agent, trigger_type, artifact_key, summary, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (project, from_agent, to_agent, trigger_type, artifact_key, summary, now))

        # Mark target agent as working on this trigger
        current_task_desc = f"⚡ Triggered by @{from_agent}: {summary[:55]}"
        conn.execute("""
            INSERT INTO team_agents (agent_name, project, status, current_task, updated_at)
            VALUES (?, ?, 'working', ?, ?)
            ON CONFLICT(agent_name, project) DO UPDATE SET
                status = 'working',
                current_task = excluded.current_task,
                updated_at = excluded.updated_at
        """, (to_agent, project, current_task_desc, now))

        # Add message to team bus
        conn.execute("""
            INSERT INTO team_messages (project, sender, message, category, priority, created_at)
            VALUES (?, ?, ?, 'handoff', 'high', ?)
        """, (project, from_agent, f"⚡ REACTIVE TRIGGER ➔ @{to_agent}: {summary} [Artifact: {artifact_key or 'none'}]", now))

def tool_team_trigger_agent(args):
    from_agent = normalize_agent_name(args.get("from_agent", "")) or "orchestrator"
    to_agent = normalize_agent_name(args.get("to_agent", ""))
    trigger_type = args.get("trigger_type", "task").strip()
    artifact_key = args.get("artifact_key", "").strip()
    summary = args.get("summary", "").strip()
    project = get_current_project(args.get("project"))

    if not to_agent or not summary:
        return "Error: to_agent and summary are required."

    dispatch_trigger(from_agent, to_agent, trigger_type, artifact_key, summary, project)
    auto_checkpoint_team(project, "agent_trigger", f"@{from_agent} triggered @{to_agent}: {summary}")
    return f"⚡ Reactive Trigger dispatched to @{to_agent} in [{project}]: {summary}"

def tool_team_check_triggers(args):
    agent_name = normalize_agent_name(args.get("agent_name", ""))
    project = get_current_project(args.get("project"))
    claim = args.get("claim", True)

    if not agent_name:
        return "Error: agent_name is required."

    conn = get_db()
    cur = conn.execute("""
        SELECT id, project, from_agent, to_agent, trigger_type, artifact_key, summary, status, created_at
        FROM team_triggers
        WHERE to_agent = ? AND (project = ? OR project = 'default') AND status = 'pending'
        ORDER BY id ASC
    """, (agent_name, project))
    triggers = cur.fetchall()

    if not triggers:
        return f"No pending triggers for @{agent_name} in [{project}]."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lines = [f"⚡ Pending Reactive Triggers for @{agent_name} [{project}] ({len(triggers)} trigger(s)):"]
    trigger_ids = []

    for t in triggers:
        trigger_ids.append(t["id"])
        art_info = f" | Artifact: `{t['artifact_key']}`" if t["artifact_key"] else ""
        lines.append(f"• Trigger #{t['id']} [{t['trigger_type'].upper()}] from @{t['from_agent']}: {t['summary']}{art_info}")
        if t["artifact_key"]:
            cur_art = conn.execute("SELECT content FROM team_artifacts WHERE artifact_key = ? LIMIT 1", (t["artifact_key"],)).fetchone()
            if cur_art:
                content_preview = cur_art["content"][:300] + ("..." if len(cur_art["content"]) > 300 else "")
                lines.append(f"  └ Contract Preview:\n```\n{content_preview}\n```")

    if claim:
        with db_write_lock(conn):
            for tid in trigger_ids:
                conn.execute("UPDATE team_triggers SET status = 'claimed', resolved_at = ? WHERE id = ?", (now, tid))
        lines.append(f"\n✓ All {len(trigger_ids)} trigger(s) claimed. @{agent_name} is actively executing them.")

    return "\n".join(lines)

def tool_team_wait_for_task(args):
    """Wait for a task to reach completed or ready_for_review status without halting OpenCode."""
    task_id = int(args.get("task_id", 0))
    timeout_sec = min(max(int(args.get("timeout_seconds", 30)), 1), 120)
    project = get_current_project(args.get("project"))

    if not task_id:
        return "Error: task_id is required."

    conn = get_db()
    try:
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            cur = conn.execute("SELECT id, title, assigned_to, status, notes FROM team_tasks WHERE id = ? AND (project = ? OR project = 'default')", (task_id, project))
            task = cur.fetchone()
            if not task:
                return f"Task #{task_id} not found in [{project}]."
            if task["status"] in ("completed", "ready_for_review", "blocked"):
                return f"✓ Task #{task_id} ('{task['title']}') reached {task['status'].upper()} (by @{task['assigned_to']}). Notes: {task['notes'] or 'None'}."
            time.sleep(1.0)

        cur = conn.execute("SELECT id, title, assigned_to, status FROM team_tasks WHERE id = ? AND (project = ? OR project = 'default')", (task_id, project))
        task = cur.fetchone()
        status_str = task["status"].upper() if task else "UNKNOWN"
        assigned = task["assigned_to"] if task else "unassigned"
        return f"⏳ Polling timeout ({timeout_sec}s): Task #{task_id} is currently {status_str} (assigned to @{assigned}). Iteration will continue without crashing."
    finally:
        conn.close()

TOOL_HANDLERS = {
    "team_broadcast": tool_team_broadcast,
    "team_read_feed": tool_team_read_feed,
    "team_set_status": tool_team_set_status,
    "team_get_status": tool_team_get_status,
    "team_get_live_activity": tool_team_get_live_activity,
    "team_heartbeat": tool_team_heartbeat,
    "team_post_task": tool_team_post_task,
    "team_claim_task": tool_team_claim_task,
    "team_update_task": tool_team_update_task,
    "team_list_tasks": tool_team_list_tasks,
    "team_share_artifact": tool_team_share_artifact,
    "team_get_artifact": tool_team_get_artifact,
    "team_handoff": tool_team_handoff,
    "team_trigger_agent": tool_team_trigger_agent,
    "team_check_triggers": tool_team_check_triggers,
    "team_wait_for_task": tool_team_wait_for_task,
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
                        "name": "team-collab-mcp",
                        "version": "2.0.0"
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
