pub mod brain_server;
pub mod engine_server;
pub mod protocol;

use std::io::{self, BufRead, Write};
use rusqlite::Connection;
use serde_json::json;

use crate::brain::db::open_brain_db;
use crate::engine::db::open_swarm_db;
use self::brain_server::{get_brain_tools, handle_brain_tool};
use self::engine_server::{get_engine_tools, handle_engine_tool};
use self::protocol::{JsonRpcError, JsonRpcRequest, JsonRpcResponse};

pub fn run_mcp_server(mode: &str) -> io::Result<()> {
    let brain_conn: Option<Connection> = if mode == "brain" || mode == "all" {
        open_brain_db(None).ok()
    } else {
        None
    };

    let engine_conn: Option<Connection> = if mode == "engine" || mode == "all" {
        open_swarm_db(None).ok()
    } else {
        None
    };

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut reader = stdin.lock();
    let mut writer = stdout.lock();

    let mut line_buffer = String::new();

    while reader.read_line(&mut line_buffer)? > 0 {
        let trimmed = line_buffer.trim();
        if trimmed.is_empty() {
            line_buffer.clear();
            continue;
        }

        let req: Result<JsonRpcRequest, _> = serde_json::from_str(trimmed);
        match req {
            Ok(r) => {
                let id = r.id.clone();
                let method = r.method.as_str();

                match method {
                    "initialize" => {
                        let resp = JsonRpcResponse {
                            jsonrpc: "2.0".to_string(),
                            id,
                            result: Some(json!({
                                "protocolVersion": "2024-11-05",
                                "capabilities": {
                                    "tools": {}
                                },
                                "serverInfo": {
                                    "name": format!("swarm-core-{}", mode),
                                    "version": "2.0.0"
                                }
                            })),
                            error: None,
                        };
                        writeln!(writer, "{}", serde_json::to_string(&resp)?)?;
                        writer.flush()?;
                    }
                    "notifications/initialized" => {
                        // Notification: no response needed
                    }
                    "ping" => {
                        let resp = JsonRpcResponse {
                            jsonrpc: "2.0".to_string(),
                            id,
                            result: Some(json!({})),
                            error: None,
                        };
                        writeln!(writer, "{}", serde_json::to_string(&resp)?)?;
                        writer.flush()?;
                    }
                    "tools/list" => {
                        let mut all_tools = Vec::new();
                        if mode == "brain" || mode == "all" {
                            all_tools.extend(get_brain_tools());
                        }
                        if mode == "engine" || mode == "all" {
                            all_tools.extend(get_engine_tools());
                        }

                        let resp = JsonRpcResponse {
                            jsonrpc: "2.0".to_string(),
                            id,
                            result: Some(json!({ "tools": all_tools })),
                            error: None,
                        };
                        writeln!(writer, "{}", serde_json::to_string(&resp)?)?;
                        writer.flush()?;
                    }
                    "tools/call" => {
                        let params = r.params.unwrap_or(json!({}));
                        let tool_name = params.get("name").and_then(|v| v.as_str()).unwrap_or("");
                        let tool_args = params.get("arguments").cloned().unwrap_or(json!({}));

                        let is_brain_tool = get_brain_tools().iter().any(|t| t.name == tool_name);
                        let is_engine_tool = get_engine_tools().iter().any(|t| t.name == tool_name);

                        let call_result = if is_brain_tool {
                            if let Some(ref bc) = brain_conn {
                                handle_brain_tool(bc, tool_name, &tool_args)
                            } else {
                                protocol::ToolCallResult::error("Brain database is not initialized")
                            }
                        } else if is_engine_tool {
                            if let Some(ref ec) = engine_conn {
                                handle_engine_tool(ec, tool_name, &tool_args)
                            } else {
                                protocol::ToolCallResult::error("Swarm engine database is not initialized")
                            }
                        } else {
                            protocol::ToolCallResult::error(format!("Tool '{}' not recognized by server", tool_name))
                        };

                        let resp = JsonRpcResponse {
                            jsonrpc: "2.0".to_string(),
                            id,
                            result: Some(serde_json::to_value(&call_result)?),
                            error: None,
                        };
                        writeln!(writer, "{}", serde_json::to_string(&resp)?)?;
                        writer.flush()?;
                    }
                    _ => {
                        if id.is_some() {
                            let resp = JsonRpcResponse {
                                jsonrpc: "2.0".to_string(),
                                id,
                                result: None,
                                error: Some(JsonRpcError {
                                    code: -32601,
                                    message: format!("Method not found: {}", method),
                                    data: None,
                                }),
                            };
                            writeln!(writer, "{}", serde_json::to_string(&resp)?)?;
                            writer.flush()?;
                        }
                    }
                }
            }
            Err(e) => {
                let resp = JsonRpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: None,
                    result: None,
                    error: Some(JsonRpcError {
                        code: -32700,
                        message: format!("Parse error: {}", e),
                        data: None,
                    }),
                };
                writeln!(writer, "{}", serde_json::to_string(&resp)?)?;
                writer.flush()?;
            }
        }
        line_buffer.clear();
    }

    Ok(())
}
