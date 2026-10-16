#!/usr/bin/env python3
"""
GetBrain Knowledge Graph Synthesizer
Generates an interactive, living project knowledge graph connecting:
  - Sub-Agents (Specialists in active/idle states)
  - Tasks (In-progress, review, completed, todo)
  - Contracts & Artifacts (API specs, DB schemas, UI interfaces)
  - Context Memories (Architectural decisions, rules, conventions, session checkpoints)
  - Codebase Modules (High-fidelity architecture components, UI views, API routes, models, manifests)
"""

import os
import sys
import sqlite3
import datetime
import subprocess
from pathlib import Path

# Paths
DEFAULT_TEAM_DIR = Path.home() / ".opencode" / "team"
DEFAULT_MEM_DIR = Path.home() / ".opencode" / "memory"

AGENT_METADATA = {
    "orchestrator": {"color": "#8B5CF6", "glyph": "SYS", "title": "Lead Architect"},
    "backend":      {"color": "#3B82F6", "glyph": "API", "title": "Backend Specialist"},
    "frontend":     {"color": "#EC4899", "glyph": "UI", "title": "Frontend Specialist"},
    "git-flow":     {"color": "#10B981", "glyph": "GIT", "title": "Git Flow Manager"},
    "qa-auditor":   {"color": "#F59E0B", "glyph": "QA", "title": "QA & Security Auditor"},
    "devops":       {"color": "#06B6D4", "glyph": "OPS", "title": "DevOps & Containers"}
}

def get_db_connection(db_path):
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn
    except Exception:
        return None

def scan_project_modules(project_dir, max_files=8):
    """
    Intelligently scans the project workspace to discover core architectural
    files, UI components, API routes, DB models, manifests and tests.
    """
    if not project_dir:
        return []
    p = Path(project_dir).resolve()
    # Guard: never recursively scan the entire home directory or filesystem root!
    if not p.is_dir() or p == Path.home() or p == Path("/"):
        return []

    ignore_dirs = {
        "node_modules", ".git", ".next", ".cache", "dist", "build",
        "__pycache__", ".venv", "venv", ".idea", ".vscode", "coverage",
        ".turbo", ".output", "target"
    }

    arch_manifests = {
        "package.json", "tsconfig.json", "schema.prisma", "docker-compose.yml",
        "dockerfile", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod",
        "next.config.ts", "next.config.js", "vite.config.ts", "vite.config.js",
        "tailwind.config.ts", "tailwind.config.js", "opencode.jsonc", "opencode.json"
    }

    categorized = {
        "manifest": [],
        "entrypoint": [],
        "ui_component": [],
        "api_route": [],
        "db_model": [],
        "test_suite": [],
        "logic_service": [],
        "rule_doc": []
    }

    try:
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            rel_dir = os.path.relpath(root, p)
            if rel_dir != "." and rel_dir.count(os.sep) > 4:
                continue

            for f in files:
                if f.startswith("."):
                    continue
                ext = Path(f).suffix.lower()
                rel_path = os.path.join(rel_dir, f) if rel_dir != "." else f
                low = rel_path.lower()
                fname_low = f.lower()

                if fname_low in arch_manifests:
                    categorized["manifest"].append((rel_path, f, "manifest", os.path.getsize(os.path.join(root, f))))
                    continue

                if ext in [".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".prisma", ".go", ".rs"]:
                    if "test" in low or "spec" in low or "__tests__" in low:
                        categorized["test_suite"].append((rel_path, f, "test_suite", os.path.getsize(os.path.join(root, f))))
                    elif "component" in low or "/ui/" in low or "/views/" in low or "/components/" in low or (ext in [".tsx", ".jsx"] and not ("api/" in low or "route." in low)):
                        categorized["ui_component"].append((rel_path, f, "ui_component", os.path.getsize(os.path.join(root, f))))
                    elif "route." in low or "/api/" in low or "endpoint" in low or "controller" in low:
                        categorized["api_route"].append((rel_path, f, "api_route", os.path.getsize(os.path.join(root, f))))
                    elif "model" in low or "schema" in low or "prisma" in low or "migration" in low or ext == ".sql":
                        categorized["db_model"].append((rel_path, f, "db_model", os.path.getsize(os.path.join(root, f))))
                    elif "server." in low or "main." in low or "app." in low or "index." in low:
                        categorized["entrypoint"].append((rel_path, f, "entrypoint", os.path.getsize(os.path.join(root, f))))
                    else:
                        categorized["logic_service"].append((rel_path, f, "logic_service", os.path.getsize(os.path.join(root, f))))
                elif ext == ".md" and rel_dir == "." and f in ["README.md", "AGENTS.md", "INSTRUCTIONS.md", "DESIGN.md"]:
                    categorized["rule_doc"].append((rel_path, f, "config_rule", os.path.getsize(os.path.join(root, f))))
    except Exception:
        pass

    result = []
    # Curated selection of core architectural modules (max 8 total)
    for cat in ["manifest", "entrypoint", "ui_component", "api_route", "db_model", "test_suite"]:
        for item in categorized[cat][:1]:
            if len(result) < 8:
                result.append({"path": item[0], "name": item[1], "category": item[2], "size": item[3]})

    return result

def get_git_info(workspace_dir):
    branch = "main"
    commit = ""
    if not workspace_dir:
        return branch, commit
    try:
        branch = subprocess.check_output(
            ["git", "-C", str(workspace_dir), "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip() or "main"
    except Exception:
        pass
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(workspace_dir), "log", "-1", "--format=%h %s"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
    except Exception:
        pass
    return branch, commit

def build_project_brain(project_name="default", workspace_dir=None):
    """
    Synthesizes the dynamic GetBrain Knowledge Graph for the current project.
    Connects:
      - Project Hub
      - 6 Specialized Sub-Agents
      - Active Tasks from Task Board
      - Shared Artifacts & API Contracts
      - Persistent Context Memories & Session Checkpoints
      - Codebase Architecture Modules
    """
    team_db_path = Path(os.environ.get("OPENCODE_TEAM_DB", DEFAULT_TEAM_DIR / "team_collab.db"))
    mem_db_path = Path(os.environ.get("OPENCODE_MEMORY_DB", DEFAULT_MEM_DIR / "context_memory.db"))

    # Determine canonical aliases for project name
    aliases = {
        project_name,
        project_name.lower(),
        project_name.replace("_", "-"),
        project_name.replace("-", "_")
    }
    if workspace_dir:
        p_name = Path(workspace_dir).name
        aliases.add(p_name)
        aliases.add(p_name.lower())
        aliases.add(p_name.replace("_", "-"))
        aliases.add(p_name.replace("-", "_"))

    nodes = []
    links = []
    node_ids = set()

    def add_node(node_id, node_type, label, category, color, details=None, status="active", extra=None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        node_obj = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "category": category,
            "color": color,
            "status": status,
            "details": details or "",
            "extra": extra or {}
        }
        nodes.append(node_obj)

    def add_link(source_id, target_id, label, link_type="general", animated=False):
        if source_id not in node_ids or target_id not in node_ids:
            return
        links.append({
            "source": source_id,
            "target": target_id,
            "label": label,
            "type": link_type,
            "animated": animated
        })

    # 1. Project Hub Node
    current_branch, latest_commit = get_git_info(workspace_dir)
    hub_id = f"project:{project_name}"
    hub_details = f"**Project Workspace**: `{workspace_dir or project_name}`\n\n- **Git Branch**: `{current_branch}`"
    if latest_commit:
        hub_details += f"\n- **Latest Commit**: `{latest_commit}`"
    hub_details += f"\n- **Nexus ID**: `{project_name}`"

    add_node(
        node_id=hub_id,
        node_type="hub",
        label=f"Project: {project_name}",
        category="core",
        color="#7C3AED",
        details=hub_details
    )

    # 2. Add Specialized Agent Nodes
    conn_team = get_db_connection(team_db_path)
    agents_map = {}
    if conn_team:
        try:
            placeholders = ",".join("?" for _ in aliases)
            cur = conn_team.execute(f"""
                SELECT agent_name, status, current_task, blockers, window_id, last_heartbeat, updated_at
                FROM team_agents
                WHERE project IN ({placeholders}) OR project = 'default'
                ORDER BY agent_name
            """, list(aliases))
            for row in cur.fetchall():
                agents_map[row["agent_name"]] = dict(row)
        except Exception:
            pass

    for agent_key, meta in AGENT_METADATA.items():
        ag_data = agents_map.get(agent_key, {})
        status = ag_data.get("status", "idle")
        curr_task = ag_data.get("current_task", "")
        win_id = ag_data.get("window_id", "")
        last_hb = ag_data.get("last_heartbeat", ag_data.get("updated_at", ""))

        node_id = f"agent:{agent_key}"
        label = f"@{agent_key}"
        add_node(
            node_id=node_id,
            node_type="agent",
            label=label,
            category=agent_key,
            color=meta["color"],
            status=status,
            details=f"**{meta['title']}**\n- Status: `{status.upper()}`\n- Task: `{curr_task or 'idle'}`\n- Window: `{win_id or 'none'}`",
            extra={
                "glyph": meta["glyph"],
                "window_id": win_id,
                "current_task": curr_task,
                "last_heartbeat": last_hb,
                "role_title": meta["title"]
            }
        )
        add_link(hub_id, node_id, "participates_in", link_type="member")

    # 3. Add Shared Artifacts & Contracts
    artifacts = []
    if conn_team:
        try:
            placeholders = ",".join("?" for _ in aliases)
            cur = conn_team.execute(f"""
                SELECT artifact_key, title, creator, artifact_type, content, updated_at
                FROM team_artifacts
                WHERE project IN ({placeholders}) OR project = 'default'
                ORDER BY updated_at DESC LIMIT 15
            """, list(aliases))
            artifacts = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

    for art in artifacts:
        art_id = f"artifact:{art['artifact_key']}"
        art_color = "#10B981" if "api" in art["artifact_type"] else "#EC4899" if "ui" in art["artifact_type"] else "#3B82F6"
        add_node(
            node_id=art_id,
            node_type="artifact",
            label=art["title"] or art["artifact_key"],
            category=art["artifact_type"],
            color=art_color,
            details=art["content"][:600] + ("..." if len(art["content"]) > 600 else ""),
            extra={
                "artifact_key": art["artifact_key"],
                "creator": art["creator"],
                "artifact_type": art["artifact_type"],
                "full_content": art["content"],
                "updated_at": art["updated_at"]
            }
        )
        creator_id = f"agent:{art['creator']}"
        if creator_id in node_ids:
            add_link(creator_id, art_id, "published_contract", link_type="contract", animated=True)
        else:
            add_link(hub_id, art_id, "contract_of", link_type="contract")

        if art["artifact_type"] == "api_spec" and "agent:frontend" in node_ids:
            add_link(art_id, "agent:frontend", "consumed_by", link_type="dependency", animated=True)
        if art["artifact_type"] in ("ui_contract", "design_token") and "agent:qa-auditor" in node_ids:
            add_link(art_id, "agent:qa-auditor", "verified_by", link_type="dependency")

    # 4. Add Tasks from Task Board
    tasks = []
    if conn_team:
        try:
            placeholders = ",".join("?" for _ in aliases)
            cur = conn_team.execute(f"""
                SELECT id, title, description, assigned_to, status, priority, notes, updated_at
                FROM team_tasks
                WHERE project IN ({placeholders})
                ORDER BY id DESC LIMIT 20
            """, list(aliases))
            tasks = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

    for t in tasks:
        task_id = f"task:{t['id']}"
        t_color = "#F59E0B" if t["status"] == "in_progress" else "#10B981" if t["status"] == "completed" else "#6B7280"
        add_node(
            node_id=task_id,
            node_type="task",
            label=f"#{t['id']} {t['title'][:30]}",
            category=t["status"],
            color=t_color,
            status=t["status"],
            details=f"**Task #{t['id']}**: {t['title']}\n- Status: `{t['status'].upper()}`\n- Assignee: `@{t['assigned_to'] or 'none'}`\n- Priority: `{t['priority']}`\n\n{t['description']}\n\n*Notes*: {t['notes']}",
            extra=t
        )
        if t["assigned_to"]:
            assignee_id = f"agent:{t['assigned_to']}"
            if assignee_id in node_ids:
                is_anim = (t["status"] == "in_progress")
                add_link(assignee_id, task_id, "assigned_to", link_type="work", animated=is_anim)
            else:
                add_link(hub_id, task_id, "task_of", link_type="task")
        else:
            add_link(hub_id, task_id, "unassigned_task", link_type="task")

    # 5. Add Persistent Context Memories & Session Checkpoints
    conn_mem = get_db_connection(mem_db_path)
    memories = []
    if conn_mem:
        try:
            placeholders = ",".join("?" for _ in aliases)
            cur = conn_mem.execute(f"""
                SELECT id, key, category, content, tags, project, updated_at
                FROM memories
                WHERE project IN ({placeholders})
                ORDER BY updated_at DESC LIMIT 20
            """, list(aliases))
            memories = [dict(r) for r in cur.fetchall()]

            # If project has few memories, fetch up to 2 global memories as well
            if len(memories) < 2:
                cur_glob = conn_mem.execute("""
                    SELECT id, key, category, content, tags, project, updated_at
                    FROM memories
                    WHERE project = 'global'
                    ORDER BY updated_at DESC LIMIT 2
                """)
                memories.extend([dict(r) for r in cur_glob.fetchall()])
        except Exception:
            pass

    module_nodes_map = {}

    # 6. Add Codebase Module Nodes (if workspace provided)
    if workspace_dir:
        code_modules = scan_project_modules(workspace_dir, max_files=40)
        color_map = {
            "manifest":      "#F59E0B",
            "entrypoint":    "#8B5CF6",
            "ui_component":  "#EC4899",
            "api_route":     "#3B82F6",
            "db_model":      "#10B981",
            "logic_service": "#06B6D4",
            "test_suite":    "#EAB308",
            "config_rule":   "#64748B"
        }

        for mod in code_modules:
            mod_id = f"code:{mod['path']}"
            module_nodes_map[mod['name'].lower()] = mod_id
            module_nodes_map[mod['path'].lower()] = mod_id

            mod_color = color_map.get(mod["category"], "#38BDF8")
            add_node(
                node_id=mod_id,
                node_type="module",
                label=mod["name"],
                category=mod["category"],
                color=mod_color,
                details=f"**File Module**: `{mod['path']}`\n- Type: `{mod['category']}`\n- Size: `{mod['size']} bytes`\n- Workspace: `{workspace_dir}`",
                extra=mod
            )

            # Link to specialized agent by role responsibility
            if mod["category"] == "ui_component" and "agent:frontend" in node_ids:
                add_link("agent:frontend", mod_id, "crafts_component", link_type="code")
            elif mod["category"] in ("api_route", "db_model") and "agent:backend" in node_ids:
                add_link("agent:backend", mod_id, "implements_logic", link_type="code")
            elif mod["category"] == "test_suite" and "agent:qa-auditor" in node_ids:
                add_link("agent:qa-auditor", mod_id, "audits_tests", link_type="code")
            elif mod["category"] in ("manifest", "config_rule") and "agent:devops" in node_ids:
                add_link("agent:devops", mod_id, "configures_infra", link_type="code")
            elif mod["category"] == "entrypoint" and "agent:orchestrator" in node_ids:
                add_link("agent:orchestrator", mod_id, "architects_entry", link_type="code")
            else:
                add_link(hub_id, mod_id, "contains_file", link_type="code")

    # Connect memories and checkpoints to graph
    for m in memories:
        is_checkpoint = "checkpoint" in m["key"].lower() or "checkpoint" in m.get("tags", "").lower()
        mem_id = f"memory:{m['key']}"

        if is_checkpoint:
            m_color = "#A855F7" # Bright Violet for Checkpoints
            m_label = f"[CHK] {m['key'][:24]}"
        elif m["category"] == "architecture":
            m_color = "#8B5CF6"
            m_label = f"[ARCH] {m['key'][:24]}"
        elif m["category"] == "decision":
            m_color = "#F43F5E"
            m_label = f"[DEC] {m['key'][:24]}"
        elif m["category"] == "learning" or "learning" in m.get("tags", "").lower():
            m_color = "#10B981"
            m_label = f"[LRN] {m['key'][:24]}"
        else:
            m_color = "#EAB308"
            m_label = f"[MEM] {m['key'][:24]}"

        add_node(
            node_id=mem_id,
            node_type="memory",
            label=m_label,
            category="checkpoint" if is_checkpoint else m["category"],
            color=m_color,
            details=f"**[{m['category'].upper()}] {m['key']}** (Project: {m['project']})\n\n{m['content']}\n\n*Tags*: `{m.get('tags', '')}`",
            extra=m
        )

        # Connect memory to hub or orchestrator
        if "agent:orchestrator" in node_ids:
            add_link("agent:orchestrator", mem_id, "preserves_context", link_type="memory", animated=is_checkpoint)
        else:
            add_link(hub_id, mem_id, "memory_of", link_type="memory")

        # Semantic linking: if memory mentions a scanned module, connect them!
        content_low = (m["content"] + " " + m["key"] + " " + m.get("tags", "")).lower()
        linked_mods = 0
        for mod_key, mod_node_id in module_nodes_map.items():
            if len(mod_key) > 4 and mod_key in content_low:
                add_link(mem_id, mod_node_id, "governs_module", link_type="semantic")
                linked_mods += 1
                if linked_mods >= 3:
                    break

    # Connect tasks to modules if task references file/component
    for t in tasks:
        task_id = f"task:{t['id']}"
        t_text = (t["title"] + " " + (t.get("description") or "")).lower()
        for mod_key, mod_node_id in module_nodes_map.items():
            if len(mod_key) > 4 and mod_key in t_text:
                add_link(task_id, mod_node_id, "targets_file", link_type="work")
                break

    # Close DB handles
    if conn_team:
        try: conn_team.close()
        except: pass
    if conn_mem:
        try: conn_mem.close()
        except: pass

    stats = {
        "project": project_name,
        "workspace": workspace_dir or "",
        "branch": current_branch,
        "total_nodes": len(nodes),
        "total_links": len(links),
        "agents_count": len([n for n in nodes if n["type"] == "agent"]),
        "tasks_count": len([n for n in nodes if n["type"] == "task"]),
        "artifacts_count": len([n for n in nodes if n["type"] == "artifact"]),
        "memories_count": len([n for n in nodes if n["type"] == "memory"]),
        "modules_count": len([n for n in nodes if n["type"] == "module"]),
        "generated_at": datetime.datetime.now().isoformat()
    }

    return {
        "project": project_name,
        "workspace": workspace_dir or "",
        "branch": current_branch,
        "nodes": nodes,
        "links": links,
        "stats": stats
    }

if __name__ == "__main__":
    import json
    data = build_project_brain(Path.cwd().name, str(Path.cwd()))
    print(f"Synthesized GetBrain for {Path.cwd().name}: {data['stats']['total_nodes']} nodes, {data['stats']['total_links']} links.")
    print("Nodes summary:", json.dumps(data["stats"], indent=2))
