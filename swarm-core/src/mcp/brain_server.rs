use rusqlite::Connection;
use serde_json::{json, Value};

use crate::brain::graph::*;
use crate::mcp::protocol::{ToolCallResult, ToolDefinition};

pub fn get_brain_tools() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "create_entity".into(),
            description: "Create or update a knowledge node in the brain graph. Each node represents an atomic concept: decision, component, endpoint, technology, learning, rule, etc.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique slug identifier"},
                    "title": {"type": "string", "description": "Human-readable name"},
                    "node_type": {"type": "string", "description": "Type classification of the node"},
                    "content": {"type": "string", "description": "Detailed content or specification"},
                    "tags": {"type": "string", "description": "Comma-separated tags"},
                    "agent_origin": {"type": "string", "description": "Originating agent (@backend, @user, etc.)"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["title"]
            }),
        },
        ToolDefinition {
            name: "relate".into(),
            description: "Create a directed typed edge between two nodes. Forms the neural connections of the brain graph (USES, DEPENDS_ON, TESTED_BY, GOVERNED_BY, CONTRADICTS, etc.).".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node ID"},
                    "target": {"type": "string", "description": "Target node ID"},
                    "relation": {"type": "string", "description": "Typed relation between nodes"},
                    "reason": {"type": "string", "description": "Why this connection exists"},
                    "weight": {"type": "number", "description": "Strength of relation"}
                },
                "required": ["source", "target", "relation"]
            }),
        },
        ToolDefinition {
            name: "observe".into(),
            description: "Add a granular observation to an existing node without rewriting its content.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "ID of node to observe"},
                    "observation": {"type": "string", "description": "Observation text"},
                    "observer": {"type": "string", "description": "Observer identifier"}
                },
                "required": ["node_id", "observation"]
            }),
        },
        ToolDefinition {
            name: "traverse".into(),
            description: "Navigate the brain graph from a starting node, following edges up to N hops.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "start_node": {"type": "string", "description": "Starting node ID"},
                    "depth": {"type": "integer", "description": "Max hops (default 2)"},
                    "relation_filter": {"type": "string", "description": "Filter by relation type"},
                    "direction": {"type": "string", "description": "Edge direction: outgoing, incoming, both"}
                },
                "required": ["start_node"]
            }),
        },
        ToolDefinition {
            name: "recall_graph".into(),
            description: "Hybrid search: FTS5 keyword match + graph neighbor expansion.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "project": {"type": "string", "description": "Project scope"},
                    "limit": {"type": "integer", "description": "Max results"},
                    "expand_neighbors": {"type": "boolean", "description": "Expand 1-hop connections"}
                },
                "required": ["query"]
            }),
        },
        ToolDefinition {
            name: "get_brain_context".into(),
            description: "Session bootstrap: returns compact summary of project's brain graph state.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "decay_audit".into(),
            description: "Audit node confidence levels using exponential decay. Reports dormant nodes and optionally prunes.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project scope"},
                    "prune_threshold": {"type": "number", "description": "Confidence threshold to prune"},
                    "dry_run": {"type": "boolean", "description": "Dry run mode"}
                }
            }),
        },
        ToolDefinition {
            name: "checkpoint_brain".into(),
            description: "Save a session checkpoint with summary, modified files, and active task.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of accomplishment"},
                    "files_modified": {"type": "string", "description": "Comma-separated files"},
                    "active_task": {"type": "string", "description": "Active task"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["summary"]
            }),
        },
        ToolDefinition {
            name: "delete_entity".into(),
            description: "Remove a node and all its edges and observations from the brain graph.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "ID of node to delete"}
                },
                "required": ["node_id"]
            }),
        },
        ToolDefinition {
            name: "remove_relation".into(),
            description: "Remove a specific edge between two nodes.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source node ID"},
                    "target": {"type": "string", "description": "Target node ID"},
                    "relation": {"type": "string", "description": "Relation to remove"}
                },
                "required": ["source", "target", "relation"]
            }),
        },
        ToolDefinition {
            name: "merge_nodes".into(),
            description: "Merge two nodes into one, combining edges, observations, and content.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "Source node to absorb"},
                    "target_id": {"type": "string", "description": "Target node that absorbs"},
                    "append_content": {"type": "boolean", "description": "Append source content"}
                },
                "required": ["source_id", "target_id"]
            }),
        },
        ToolDefinition {
            name: "list_entities".into(),
            description: "List nodes in the brain graph with optional filtering by type or project.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "node_type": {"type": "string", "description": "Filter by node type"},
                    "project": {"type": "string", "description": "Project scope"},
                    "min_confidence": {"type": "number", "description": "Minimum confidence"},
                    "limit": {"type": "integer", "description": "Max items"}
                }
            }),
        },
        ToolDefinition {
            name: "record_learning".into(),
            description: "Record a project learning/insight connected to trigger context.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "lesson": {"type": "string", "description": "Learning or insight"},
                    "category": {"type": "string", "description": "Category"},
                    "trigger_node": {"type": "string", "description": "Triggering node ID"},
                    "agent_name": {"type": "string", "description": "Discoverer agent"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["lesson"]
            }),
        },
    ]
}

pub fn handle_brain_tool(conn: &Connection, name: &str, args: &Value) -> ToolCallResult {
    let res = match name {
        "create_entity" => {
            let title = match args.get("title").and_then(|v| v.as_str()) {
                Some(t) => t,
                None => return ToolCallResult::error("Missing required parameter 'title'"),
            };
            create_entity(
                conn,
                args.get("id").and_then(|v| v.as_str()),
                title,
                args.get("node_type").and_then(|v| v.as_str()),
                args.get("content").and_then(|v| v.as_str()),
                args.get("tags").and_then(|v| v.as_str()),
                args.get("agent_origin").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "relate" => {
            let source = match args.get("source").and_then(|v| v.as_str()) {
                Some(s) => s,
                None => return ToolCallResult::error("Missing 'source'"),
            };
            let target = match args.get("target").and_then(|v| v.as_str()) {
                Some(t) => t,
                None => return ToolCallResult::error("Missing 'target'"),
            };
            let rel = match args.get("relation").and_then(|v| v.as_str()) {
                Some(r) => r,
                None => return ToolCallResult::error("Missing 'relation'"),
            };
            relate(
                conn,
                source,
                target,
                rel,
                args.get("reason").and_then(|v| v.as_str()),
                args.get("weight").and_then(|v| v.as_f64()),
            )
        }
        "observe" => {
            let nid = match args.get("node_id").and_then(|v| v.as_str()) {
                Some(n) => n,
                None => return ToolCallResult::error("Missing 'node_id'"),
            };
            let obs = match args.get("observation").and_then(|v| v.as_str()) {
                Some(o) => o,
                None => return ToolCallResult::error("Missing 'observation'"),
            };
            observe(conn, nid, obs, args.get("observer").and_then(|v| v.as_str()))
        }
        "traverse" => {
            let start = match args.get("start_node").and_then(|v| v.as_str()) {
                Some(s) => s,
                None => return ToolCallResult::error("Missing 'start_node'"),
            };
            let depth = args.get("depth").and_then(|v| v.as_u64()).map(|d| d as usize);
            traverse(
                conn,
                start,
                depth,
                args.get("relation_filter").and_then(|v| v.as_str()),
                args.get("direction").and_then(|v| v.as_str()),
            )
        }
        "recall_graph" => {
            let q = match args.get("query").and_then(|v| v.as_str()) {
                Some(query) => query,
                None => return ToolCallResult::error("Missing 'query'"),
            };
            let limit = args.get("limit").and_then(|v| v.as_u64()).map(|l| l as usize);
            recall_graph(
                conn,
                q,
                args.get("project").and_then(|v| v.as_str()),
                limit,
                args.get("expand_neighbors").and_then(|v| v.as_bool()),
            )
        }
        "get_brain_context" => get_brain_context(conn, args.get("project").and_then(|v| v.as_str())),
        "decay_audit" => decay_audit(
            conn,
            args.get("project").and_then(|v| v.as_str()),
            args.get("prune_threshold").and_then(|v| v.as_f64()),
            args.get("dry_run").and_then(|v| v.as_bool()),
        ),
        "checkpoint_brain" => {
            let summary = match args.get("summary").and_then(|v| v.as_str()) {
                Some(s) => s,
                None => return ToolCallResult::error("Missing 'summary'"),
            };
            checkpoint_brain(
                conn,
                summary,
                args.get("files_modified").and_then(|v| v.as_str()),
                args.get("active_task").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "delete_entity" => {
            let nid = match args.get("node_id").and_then(|v| v.as_str()) {
                Some(n) => n,
                None => return ToolCallResult::error("Missing 'node_id'"),
            };
            delete_entity(conn, nid)
        }
        "remove_relation" => {
            let src = match args.get("source").and_then(|v| v.as_str()) {
                Some(s) => s,
                None => return ToolCallResult::error("Missing 'source'"),
            };
            let tgt = match args.get("target").and_then(|v| v.as_str()) {
                Some(t) => t,
                None => return ToolCallResult::error("Missing 'target'"),
            };
            let rel = match args.get("relation").and_then(|v| v.as_str()) {
                Some(r) => r,
                None => return ToolCallResult::error("Missing 'relation'"),
            };
            remove_relation(conn, src, tgt, rel)
        }
        "merge_nodes" => {
            let src = match args.get("source_id").and_then(|v| v.as_str()) {
                Some(s) => s,
                None => return ToolCallResult::error("Missing 'source_id'"),
            };
            let tgt = match args.get("target_id").and_then(|v| v.as_str()) {
                Some(t) => t,
                None => return ToolCallResult::error("Missing 'target_id'"),
            };
            merge_nodes(conn, src, tgt, args.get("append_content").and_then(|v| v.as_bool()))
        }
        "list_entities" => {
            let limit = args.get("limit").and_then(|v| v.as_u64()).map(|l| l as usize);
            list_entities(
                conn,
                args.get("node_type").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
                args.get("min_confidence").and_then(|v| v.as_f64()),
                limit,
            )
        }
        "record_learning" => {
            let lesson = match args.get("lesson").and_then(|v| v.as_str()) {
                Some(l) => l,
                None => return ToolCallResult::error("Missing 'lesson'"),
            };
            record_learning(
                conn,
                lesson,
                args.get("category").and_then(|v| v.as_str()),
                args.get("trigger_node").and_then(|v| v.as_str()),
                args.get("agent_name").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        _ => return ToolCallResult::error(format!("Unknown brain tool: {}", name)),
    };

    match res {
        Ok(val) => ToolCallResult::success(serde_json::to_string_pretty(&val).unwrap_or_default()),
        Err(e) => ToolCallResult::error(format!("Brain error: {}", e)),
    }
}
