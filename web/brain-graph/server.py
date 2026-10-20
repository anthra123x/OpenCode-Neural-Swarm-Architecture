#!/usr/bin/env python3
"""
Brain Graph Visualizer Server
Serves real-time Obsidian-style neural network graph visualization directly
from ~/.opencode/brain/brain.db.
"""

import http.server
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.parse
from pathlib import Path

PORT = int(os.environ.get("BRAIN_GRAPH_PORT", "4848"))
DB_PATH = Path(os.environ.get("OPENCODE_BRAIN_DB", os.path.expanduser("~/.opencode/brain/brain.db")))
STATIC_DIR = Path(__file__).parent

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def fetch_graph_data():
    if not DB_PATH.exists():
        return {"nodes": [], "links": [], "stats": {"nodes": 0, "edges": 0}}

    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Fetch nodes
        nodes_rows = cur.execute("""
            SELECT id, title, node_type, project, agent_origin, confidence, tags, content, created_at, updated_at
            FROM nodes
        """).fetchall()

        # Fetch edges
        edges_rows = cur.execute("""
            SELECT source_id, target_id, relation, reason, weight
            FROM edges
        """).fetchall()

        conn.close()

        nodes = []
        node_ids = set()
        
        # Color & type classification
        type_palette = {
            "decision": "#A855F7",      # Purple (Decision/Agent)
            "architecture": "#EC4899",  # Pink
            "technology": "#3B82F6",    # Blue
            "component": "#14B8A6",     # Teal/Cyan
            "endpoint": "#10B981",      # Emerald Green
            "rule": "#F43F5E",          # Rose/Red
            "learning": "#F59E0B",      # Amber/Yellow
            "convention": "#8B5CF6",    # Violet
            "checkpoint": "#6366F1",    # Indigo
            "test": "#06B6D4"           # Cyan
        }

        # Identify "My agent" cluster nodes (active project or agent_origin)
        for row in nodes_rows:
            nid = row["id"]
            node_ids.add(nid)
            ntype = row["node_type"] or "concept"
            tags = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
            
            # Determine if part of active agent cluster
            is_agent = (
                row["agent_origin"] in ("@orchestrator", "@backend", "@frontend", "orchestrator") or
                row["project"] in ("opencode_config", "global") or
                "auth" in nid.lower() or "swarm" in nid.lower() or "rust" in nid.lower()
            )

            color = "#A855F7" if is_agent else type_palette.get(ntype, "#64748B")

            nodes.append({
                "id": nid,
                "label": row["title"] or nid,
                "type": ntype,
                "project": row["project"] or "global",
                "confidence": float(row["confidence"] or 1.0),
                "tags": tags,
                "is_agent": is_agent,
                "color": color,
                "snippet": (row["content"] or "")[:120]
            })

        links = []
        for row in edges_rows:
            src = row["source_id"]
            tgt = row["target_id"]
            # Only include link if both nodes exist in the dataset
            if src in node_ids and tgt in node_ids:
                links.append({
                    "source": src,
                    "target": tgt,
                    "relation": row["relation"] or "RELATED_TO",
                    "reason": row["reason"] or "",
                    "weight": float(row["weight"] or 1.0)
                })

        agent_nodes = [n["id"] for n in nodes if n["is_agent"]]

        return {
            "nodes": nodes,
            "links": links,
            "stats": {
                "nodes": len(nodes),
                "edges": len(links),
                "agent_cluster_size": len(agent_nodes),
                "timestamp": time.time()
            }
        }
    except Exception as e:
        return {"nodes": [], "links": [], "error": str(e), "stats": {"nodes": 0, "edges": 0}}

def fetch_node_detail(node_id):
    if not DB_PATH.exists():
        return None
    try:
        conn = get_db()
        cur = conn.cursor()
        node = cur.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not node:
            conn.close()
            return None
            
        observations = cur.execute("""
            SELECT observation, observer, created_at
            FROM observations
            WHERE node_id = ?
            ORDER BY created_at DESC
        """, (node_id,)).fetchall()

        outgoing = cur.execute("""
            SELECT target_id, relation, reason FROM edges WHERE source_id = ?
        """, (node_id,)).fetchall()

        incoming = cur.execute("""
            SELECT source_id, relation, reason FROM edges WHERE target_id = ?
        """, (node_id,)).fetchall()

        conn.close()

        return {
            "node": dict(node),
            "observations": [dict(o) for o in observations],
            "outgoing": [dict(e) for e in outgoing],
            "incoming": [dict(e) for e in incoming]
        }
    except Exception as e:
        return {"error": str(e)}

class BrainGraphHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html", "/graph"):
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(index_path.read_bytes())
                return
            else:
                self.send_error(404, "index.html not found")
                return

        elif path == "/api/graph":
            data = fetch_graph_data()
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path.startswith("/api/node/"):
            node_id = urllib.parse.unquote(path[len("/api/node/"):])
            detail = fetch_node_detail(node_id)
            if detail is None:
                self.send_error(404, f"Node {node_id} not found")
                return
            payload = json.dumps(detail).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
            return

        elif path == "/api/status":
            stats = {
                "status": "online",
                "db": str(DB_PATH),
                "exists": DB_PATH.exists(),
                "time": time.time()
            }
            payload = json.dumps(stats).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)
            return

        return super().do_GET()

    def log_message(self, format, *args):
        # Silent logging for performance
        pass

def run_server(port=PORT):
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), BrainGraphHandler)
    print(f"[✓] Brain Graph Visualizer active at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visualizer server...")
        server.server_close()

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(p)
