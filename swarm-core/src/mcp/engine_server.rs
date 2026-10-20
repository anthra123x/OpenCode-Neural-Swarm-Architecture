use rusqlite::Connection;
use serde_json::{json, Value};

use crate::engine::tasks::*;
use crate::mcp::protocol::{ToolCallResult, ToolDefinition};
use crate::sentinel::auditor::*;
use crate::tester::probe::tester_probe_endpoint;
use crate::tester::runner::*;

pub fn get_engine_tools() -> Vec<ToolDefinition> {
    vec![
        ToolDefinition {
            name: "sentinel_audit_task".into(),
            description: "Audits agent deliverables against active Sentinel rules and emits quality score (0-100).".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Agent responsible"},
                    "task_title": {"type": "string", "description": "Task milestone title"},
                    "deliverables": {"type": "string", "description": "Summary of deliverables and contracts"},
                    "files_modified": {"type": "string", "description": "Comma-separated files modified"},
                    "test_results": {"type": "string", "description": "Test summary or coverage figures"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["agent_name", "task_title", "deliverables"]
            }),
        },
        ToolDefinition {
            name: "sentinel_get_rules".into(),
            description: "Lists active Sentinel engineering rules with checklists.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by rule category"},
                    "target_agent": {"type": "string", "description": "Filter by agent role"}
                }
            }),
        },
        ToolDefinition {
            name: "sentinel_record_violation".into(),
            description: "Explicitly records a quality or security violation for an agent deliverable.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "rule_code": {"type": "string", "description": "Rule code violated (e.g. TDD-001, SEC-001)"},
                    "agent_name": {"type": "string", "description": "Agent responsible"},
                    "details": {"type": "string", "description": "Specific details of what failed"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "task_title": {"type": "string", "description": "Related task title"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["rule_code", "agent_name", "details"]
            }),
        },
        ToolDefinition {
            name: "sentinel_resolve_violation".into(),
            description: "Marks an engineering violation as resolved with resolution notes.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "violation_id": {"type": "integer", "description": "ID of violation to resolve"},
                    "resolution_notes": {"type": "string", "description": "How the issue was remediated"}
                },
                "required": ["violation_id", "resolution_notes"]
            }),
        },
        ToolDefinition {
            name: "sentinel_verify_compliance".into(),
            description: "Verifies whether a project or agent has open violations blocking completion.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Filter by agent"},
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "sentinel_get_compliance_report".into(),
            description: "Generates comprehensive compliance scorecard for the project.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Timeframe in days"},
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "tester_run_suite".into(),
            description: "Executes automated test runner (pytest, vitest, jest, cargo, go) with coverage detection.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "target_path": {"type": "string", "description": "Test file or directory"},
                    "runner": {"type": "string", "description": "Runner to use"},
                    "coverage": {"type": "boolean", "description": "Collect code coverage"},
                    "timeout_seconds": {"type": "integer", "description": "Max execution time"},
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "tester_probe_endpoint".into(),
            description: "Executes HTTP probe against a live endpoint to measure latency and verify status code.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to probe"},
                    "method": {"type": "string", "description": "HTTP method (GET/POST)"},
                    "expected_status": {"type": "integer", "description": "Expected status (default 200)"},
                    "payload": {"type": "string", "description": "Optional JSON payload for POST"},
                    "timeout_seconds": {"type": "number", "description": "Probe timeout in seconds"}
                },
                "required": ["url"]
            }),
        },
        ToolDefinition {
            name: "tester_verify_component".into(),
            description: "Performs quick syntax, compilation or validation check on a single component/file.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to file"},
                    "check_type": {"type": "string", "description": "Check type"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["file_path"]
            }),
        },
        ToolDefinition {
            name: "tester_get_live_health".into(),
            description: "Returns current test suite health, pass rate, and recent test statuses.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "tester_quick_check".into(),
            description: "Fast syntax and sanity check on a target file before running full suites.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Target file path"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["file_path"]
            }),
        },
        ToolDefinition {
            name: "tester_sync_with_sentinel".into(),
            description: "Synchronizes latest test results with sentinel to resolve open TDD violations.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "swarm_post_task".into(),
            description: "Post a decomposed milestone task to the swarm task board.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Detailed task instructions"},
                    "assigned_to": {"type": "string", "description": "Target agent"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["title"]
            }),
        },
        ToolDefinition {
            name: "swarm_update_task".into(),
            description: "Update task status (todo, in_progress, done, blocked) with progress notes.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID"},
                    "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"]},
                    "notes": {"type": "string", "description": "Progress notes"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["task_id"]
            }),
        },
        ToolDefinition {
            name: "swarm_list_tasks".into(),
            description: "List task board milestones filtered by status or assigned agent.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status"},
                    "assigned_to": {"type": "string", "description": "Filter by agent"},
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
        ToolDefinition {
            name: "swarm_share_artifact".into(),
            description: "Publishes a shared contract or spec (API contract, DB schema, UI spec) for other agents.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "artifact_key": {"type": "string", "description": "Unique key (e.g. api_auth_v1)"},
                    "title": {"type": "string", "description": "Descriptive title"},
                    "content": {"type": "string", "description": "Artifact payload or spec markdown"},
                    "artifact_type": {"type": "string", "description": "Type: contract, schema, spec"},
                    "creator": {"type": "string", "description": "Creator agent"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["artifact_key", "content"]
            }),
        },
        ToolDefinition {
            name: "swarm_get_artifact".into(),
            description: "Retrieve a shared contract or specification artifact by key.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "artifact_key": {"type": "string", "description": "Unique key of artifact"},
                    "project": {"type": "string", "description": "Project scope"}
                },
                "required": ["artifact_key"]
            }),
        },
        ToolDefinition {
            name: "swarm_gate_check".into(),
            description: "Comprehensive Quality Gate: checks test status, sentinel compliance, and task completion before sign-off.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID to verify completion"},
                    "project": {"type": "string", "description": "Project scope"}
                }
            }),
        },
    ]
}

pub fn handle_engine_tool(conn: &Connection, name: &str, args: &Value) -> ToolCallResult {
    let res = match name {
        "sentinel_audit_task" => {
            let agent = match args.get("agent_name").and_then(|v| v.as_str()) {
                Some(a) => a,
                None => return ToolCallResult::error("Missing 'agent_name'"),
            };
            let title = match args.get("task_title").and_then(|v| v.as_str()) {
                Some(t) => t,
                None => return ToolCallResult::error("Missing 'task_title'"),
            };
            let deliv = match args.get("deliverables").and_then(|v| v.as_str()) {
                Some(d) => d,
                None => return ToolCallResult::error("Missing 'deliverables'"),
            };
            sentinel_audit_task(
                conn,
                agent,
                title,
                deliv,
                args.get("files_modified").and_then(|v| v.as_str()),
                args.get("test_results").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "sentinel_get_rules" => Ok(sentinel_get_rules(
            args.get("category").and_then(|v| v.as_str()),
            args.get("target_agent").and_then(|v| v.as_str()),
        )),
        "sentinel_record_violation" => {
            let rule = match args.get("rule_code").and_then(|v| v.as_str()) {
                Some(r) => r,
                None => return ToolCallResult::error("Missing 'rule_code'"),
            };
            let agent = match args.get("agent_name").and_then(|v| v.as_str()) {
                Some(a) => a,
                None => return ToolCallResult::error("Missing 'agent_name'"),
            };
            let details = match args.get("details").and_then(|v| v.as_str()) {
                Some(d) => d,
                None => return ToolCallResult::error("Missing 'details'"),
            };
            sentinel_record_violation(
                conn,
                rule,
                agent,
                details,
                args.get("severity").and_then(|v| v.as_str()),
                args.get("task_title").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "sentinel_resolve_violation" => {
            let vid = match args.get("violation_id").and_then(|v| v.as_i64()) {
                Some(id) => id,
                None => return ToolCallResult::error("Missing 'violation_id'"),
            };
            let notes = match args.get("resolution_notes").and_then(|v| v.as_str()) {
                Some(n) => n,
                None => return ToolCallResult::error("Missing 'resolution_notes'"),
            };
            sentinel_resolve_violation(conn, vid, notes)
        }
        "sentinel_verify_compliance" => sentinel_verify_compliance(
            conn,
            args.get("agent_name").and_then(|v| v.as_str()),
            args.get("project").and_then(|v| v.as_str()),
        ),
        "sentinel_get_compliance_report" => sentinel_get_compliance_report(
            conn,
            args.get("days").and_then(|v| v.as_i64()),
            args.get("project").and_then(|v| v.as_str()),
        ),
        "tester_run_suite" => tester_run_suite(
            conn,
            args.get("target_path").and_then(|v| v.as_str()),
            args.get("runner").and_then(|v| v.as_str()),
            args.get("coverage").and_then(|v| v.as_bool()),
            args.get("timeout_seconds").and_then(|v| v.as_u64()),
            args.get("project").and_then(|v| v.as_str()),
        ),
        "tester_probe_endpoint" => {
            let url = match args.get("url").and_then(|v| v.as_str()) {
                Some(u) => u,
                None => return ToolCallResult::error("Missing 'url'"),
            };
            let status = args.get("expected_status").and_then(|v| v.as_u64()).map(|s| s as u16);
            let to = args.get("timeout_seconds").and_then(|v| v.as_f64());
            Ok(tester_probe_endpoint(
                url,
                args.get("method").and_then(|v| v.as_str()),
                status,
                args.get("payload").and_then(|v| v.as_str()),
                to,
            ))
        }
        "tester_verify_component" => {
            let fp = match args.get("file_path").and_then(|v| v.as_str()) {
                Some(f) => f,
                None => return ToolCallResult::error("Missing 'file_path'"),
            };
            tester_verify_component(
                conn,
                fp,
                args.get("check_type").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "tester_get_live_health" => tester_get_live_health(conn, args.get("project").and_then(|v| v.as_str())),
        "tester_quick_check" => {
            let fp = match args.get("file_path").and_then(|v| v.as_str()) {
                Some(f) => f,
                None => return ToolCallResult::error("Missing 'file_path'"),
            };
            tester_quick_check(conn, fp, args.get("project").and_then(|v| v.as_str()))
        }
        "tester_sync_with_sentinel" => tester_sync_with_sentinel(conn, args.get("project").and_then(|v| v.as_str())),
        "swarm_post_task" => {
            let title = match args.get("title").and_then(|v| v.as_str()) {
                Some(t) => t,
                None => return ToolCallResult::error("Missing 'title'"),
            };
            let desc = args.get("description").and_then(|v| v.as_str()).unwrap_or("");
            let assigned = args.get("assigned_to").and_then(|v| v.as_str()).unwrap_or("@backend");
            swarm_post_task(
                conn,
                title,
                desc,
                assigned,
                args.get("priority").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "swarm_update_task" => {
            let tid = match args.get("task_id").and_then(|v| v.as_i64()) {
                Some(id) => id,
                None => return ToolCallResult::error("Missing 'task_id'"),
            };
            let status = args.get("status").and_then(|v| v.as_str()).unwrap_or("in_progress");
            swarm_update_task(
                conn,
                tid,
                status,
                args.get("notes").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "swarm_list_tasks" => swarm_list_tasks(
            conn,
            args.get("status").and_then(|v| v.as_str()),
            args.get("assigned_to").and_then(|v| v.as_str()),
            args.get("project").and_then(|v| v.as_str()),
        ),
        "swarm_share_artifact" => {
            let key = match args.get("artifact_key").and_then(|v| v.as_str()) {
                Some(k) => k,
                None => return ToolCallResult::error("Missing 'artifact_key'"),
            };
            let title = args.get("title").and_then(|v| v.as_str()).unwrap_or(key);
            let content = match args.get("content").and_then(|v| v.as_str()) {
                Some(c) => c,
                None => return ToolCallResult::error("Missing 'content'"),
            };
            swarm_share_artifact(
                conn,
                key,
                title,
                content,
                args.get("artifact_type").and_then(|v| v.as_str()),
                args.get("creator").and_then(|v| v.as_str()),
                args.get("project").and_then(|v| v.as_str()),
            )
        }
        "swarm_get_artifact" => {
            let key = match args.get("artifact_key").and_then(|v| v.as_str()) {
                Some(k) => k,
                None => return ToolCallResult::error("Missing 'artifact_key'"),
            };
            swarm_get_artifact(conn, key, args.get("project").and_then(|v| v.as_str()))
        }
        "swarm_gate_check" => swarm_gate_check(
            conn,
            args.get("task_id").and_then(|v| v.as_i64()),
            args.get("project").and_then(|v| v.as_str()),
        ),
        _ => return ToolCallResult::error(format!("Unknown engine tool: {}", name)),
    };

    match res {
        Ok(val) => ToolCallResult::success(serde_json::to_string_pretty(&val).unwrap_or_default()),
        Err(e) => ToolCallResult::error(format!("Engine error: {}", e)),
    }
}
