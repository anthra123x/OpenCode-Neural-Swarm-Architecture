use std::collections::{HashSet, VecDeque};
use chrono::Utc;
use rusqlite::{params, Connection, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[allow(dead_code)]

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub id: String,
    pub title: String,
    pub node_type: String,
    pub content: String,
    pub project: String,
    pub agent_origin: String,
    pub confidence: f64,
    pub access_count: i64,
    pub last_accessed: String,
    pub tags: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub id: i64,
    pub source_id: String,
    pub target_id: String,
    pub relation: String,
    pub reason: String,
    pub weight: f64,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Observation {
    pub id: i64,
    pub node_id: String,
    pub observation: String,
    pub observer: String,
    pub observed_at: String,
}

pub fn slugify(text: &str) -> String {
    let s = text
        .to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '-' })
        .collect::<String>();
    let parts: Vec<&str> = s.split('-').filter(|p| !p.is_empty()).collect();
    let res = parts.join("-");
    if res.is_empty() {
        "node".to_string()
    } else {
        res.chars().take(60).collect()
    }
}

pub fn get_current_project() -> String {
    if let Ok(p) = std::env::var("OPENCODE_PROJECT") {
        return p;
    }
    if let Ok(dir) = std::env::current_dir() {
        if let Some(name) = dir.file_name() {
            return name.to_string_lossy().to_string();
        }
    }
    "global".to_string()
}

pub fn create_entity(
    conn: &Connection,
    id_opt: Option<&str>,
    title: &str,
    node_type: Option<&str>,
    content: Option<&str>,
    tags: Option<&str>,
    agent_origin: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let id = id_opt
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| slugify(title));
    let n_type = node_type.unwrap_or("concept");
    let cnt = content.unwrap_or("");
    let tgs = tags.unwrap_or("");
    let origin = agent_origin.unwrap_or("@user");
    let prj = project_opt.unwrap_or_else(|| "global");
    let now = Utc::now().to_rfc3339();

    conn.execute(
        r#"
        INSERT INTO nodes (id, title, node_type, content, project, agent_origin, confidence, access_count, last_accessed, tags, created_at, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1.0, 1, ?7, ?8, ?7, ?7)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            node_type = excluded.node_type,
            content = excluded.content,
            tags = excluded.tags,
            updated_at = excluded.updated_at,
            access_count = nodes.access_count + 1,
            last_accessed = excluded.last_accessed
        "#,
        params![id, title, n_type, cnt, prj, origin, now, tgs],
    )?;

    Ok(json!({
        "status": "created",
        "id": id,
        "title": title,
        "type": n_type,
        "project": prj,
        "confidence": 1.0
    }))
}

pub fn relate(
    conn: &Connection,
    source: &str,
    target: &str,
    relation: &str,
    reason: Option<&str>,
    weight_opt: Option<f64>,
) -> Result<Value> {
    let rsn = reason.unwrap_or("");
    let w = weight_opt.unwrap_or(1.0);
    let now = Utc::now().to_rfc3339();

    conn.execute(
        r#"
        INSERT INTO edges (source_id, target_id, relation, reason, weight, created_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6)
        ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
            reason = excluded.reason,
            weight = excluded.weight
        "#,
        params![source, target, relation.to_uppercase(), rsn, w, now],
    )?;

    Ok(json!({
        "status": "connected",
        "source": source,
        "target": target,
        "relation": relation.to_uppercase(),
        "weight": w
    }))
}

pub fn observe(conn: &Connection, node_id: &str, observation: &str, observer: Option<&str>) -> Result<Value> {
    let obs_by = observer.unwrap_or("@user");
    let now = Utc::now().to_rfc3339();

    conn.execute(
        r#"
        INSERT INTO observations (node_id, observation, observer, observed_at)
        VALUES (?1, ?2, ?3, ?4)
        "#,
        params![node_id, observation, obs_by, now],
    )?;

    // Increment access
    let _ = conn.execute(
        "UPDATE nodes SET access_count = access_count + 1, last_accessed = ?1 WHERE id = ?2",
        params![now, node_id],
    );

    Ok(json!({
        "status": "observed",
        "node_id": node_id,
        "observation": observation,
        "observer": obs_by
    }))
}

pub fn traverse(
    conn: &Connection,
    start_node: &str,
    depth: Option<usize>,
    relation_filter: Option<&str>,
    direction: Option<&str>,
) -> Result<Value> {
    let max_depth = depth.unwrap_or(2).min(5);
    let dir = direction.unwrap_or("both");
    let rel_filter = relation_filter.map(|r| r.to_uppercase());

    let mut visited: HashSet<String> = HashSet::new();
    let mut queue: VecDeque<(String, usize)> = VecDeque::new();
    queue.push_back((start_node.to_string(), 0));
    visited.insert(start_node.to_string());

    let mut nodes_out = Vec::new();
    let mut edges_out = Vec::new();

    while let Some((curr, curr_depth)) = queue.pop_front() {
        if curr_depth >= max_depth {
            continue;
        }

        // Query outgoing
        if dir == "both" || dir == "outgoing" {
            let mut stmt = conn.prepare(
                "SELECT id, source_id, target_id, relation, reason, weight, created_at FROM edges WHERE source_id = ?1",
            )?;
            let rows = stmt.query_map(params![curr], |row| {
                Ok(Edge {
                    id: row.get(0)?,
                    source_id: row.get(1)?,
                    target_id: row.get(2)?,
                    relation: row.get(3)?,
                    reason: row.get(4)?,
                    weight: row.get(5)?,
                    created_at: row.get(6)?,
                })
            })?;

            for edge_res in rows {
                if let Ok(edge) = edge_res {
                    if let Some(ref rf) = rel_filter {
                        if &edge.relation != rf {
                            continue;
                        }
                    }
                    let nxt = edge.target_id.clone();
                    edges_out.push(edge);
                    if !visited.contains(&nxt) {
                        visited.insert(nxt.clone());
                        queue.push_back((nxt, curr_depth + 1));
                    }
                }
            }
        }

        // Query incoming
        if dir == "both" || dir == "incoming" {
            let mut stmt = conn.prepare(
                "SELECT id, source_id, target_id, relation, reason, weight, created_at FROM edges WHERE target_id = ?1",
            )?;
            let rows = stmt.query_map(params![curr], |row| {
                Ok(Edge {
                    id: row.get(0)?,
                    source_id: row.get(1)?,
                    target_id: row.get(2)?,
                    relation: row.get(3)?,
                    reason: row.get(4)?,
                    weight: row.get(5)?,
                    created_at: row.get(6)?,
                })
            })?;

            for edge_res in rows {
                if let Ok(edge) = edge_res {
                    if let Some(ref rf) = rel_filter {
                        if &edge.relation != rf {
                            continue;
                        }
                    }
                    let nxt = edge.source_id.clone();
                    edges_out.push(edge);
                    if !visited.contains(&nxt) {
                        visited.insert(nxt.clone());
                        queue.push_back((nxt, curr_depth + 1));
                    }
                }
            }
        }
    }

    // Retrieve details for all visited nodes
    for nid in &visited {
        let mut stmt = conn.prepare(
            "SELECT id, title, node_type, content, project, confidence, tags FROM nodes WHERE id = ?1",
        )?;
        if let Ok(mut rows) = stmt.query(params![nid]) {
            if let Ok(Some(row)) = rows.next() {
                nodes_out.push(json!({
                    "id": row.get::<_, String>(0)?,
                    "title": row.get::<_, String>(1)?,
                    "type": row.get::<_, String>(2)?,
                    "content": row.get::<_, String>(3)?,
                    "project": row.get::<_, String>(4)?,
                    "confidence": row.get::<_, f64>(5)?,
                    "tags": row.get::<_, String>(6)?,
                }));
            }
        }
    }

    Ok(json!({
        "root": start_node,
        "depth": max_depth,
        "nodes_found": nodes_out.len(),
        "edges_found": edges_out.len(),
        "nodes": nodes_out,
        "edges": edges_out
    }))
}

pub fn recall_graph(
    conn: &Connection,
    query: &str,
    project_opt: Option<&str>,
    limit_opt: Option<usize>,
    expand_neighbors: Option<bool>,
) -> Result<Value> {
    let limit = limit_opt.unwrap_or(10);
    let prj = project_opt.unwrap_or("global");
    let expand = expand_neighbors.unwrap_or(true);

    let clean_query = query.replace('"', "").replace('\'', "");
    let mut stmt = conn.prepare(
        r#"
        SELECT n.id, n.title, n.node_type, n.content, n.project, n.confidence, n.tags
        FROM nodes_fts fts
        JOIN nodes n ON fts.id = n.id
        WHERE nodes_fts MATCH ?1 AND (n.project = ?2 OR n.project = 'global')
        ORDER BY rank
        LIMIT ?3
        "#,
    )?;

    let mut matches = Vec::new();
    let mut matched_ids = Vec::new();

    let rows = stmt.query_map(params![clean_query, prj, limit], |row| {
        Ok(json!({
            "id": row.get::<_, String>(0)?,
            "title": row.get::<_, String>(1)?,
            "type": row.get::<_, String>(2)?,
            "content": row.get::<_, String>(3)?,
            "project": row.get::<_, String>(4)?,
            "confidence": row.get::<_, f64>(5)?,
            "tags": row.get::<_, String>(6)?,
        }))
    });

    if let Ok(r) = rows {
        for item in r.flatten() {
            if let Some(id_str) = item.get("id").and_then(|v| v.as_str()) {
                matched_ids.push(id_str.to_string());
            }
            matches.push(item);
        }
    }

    let mut connections = Vec::new();
    if expand && !matched_ids.is_empty() {
        for mid in &matched_ids {
            let mut estmt = conn.prepare(
                "SELECT source_id, target_id, relation, reason FROM edges WHERE source_id = ?1 OR target_id = ?1 LIMIT 5",
            )?;
            let erows = estmt.query_map(params![mid], |r| {
                Ok(json!({
                    "source": r.get::<_, String>(0)?,
                    "target": r.get::<_, String>(1)?,
                    "relation": r.get::<_, String>(2)?,
                    "reason": r.get::<_, String>(3)?,
                }))
            });
            if let Ok(iter) = erows {
                for edge in iter.flatten() {
                    connections.push(edge);
                }
            }
        }
    }

    Ok(json!({
        "query": query,
        "count": matches.len(),
        "results": matches,
        "connections": connections
    }))
}

pub fn get_brain_context(conn: &Connection, project_opt: Option<&str>) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");

    let mut stmt = conn.prepare(
        r#"
        SELECT id, title, node_type, content, confidence, updated_at
        FROM nodes
        WHERE (project = ?1 OR project = 'global') AND confidence >= 0.2
        ORDER BY updated_at DESC
        LIMIT 25
        "#,
    )?;

    let nodes = stmt
        .query_map(params![prj], |r| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "title": r.get::<_, String>(1)?,
                "type": r.get::<_, String>(2)?,
                "content": r.get::<_, String>(3)?,
                "confidence": r.get::<_, f64>(4)?,
                "updated_at": r.get::<_, String>(5)?,
            }))
        })?
        .flatten()
        .collect::<Vec<_>>();

    let mut obs_stmt = conn.prepare(
        r#"
        SELECT o.node_id, o.observation, o.observer, o.observed_at
        FROM observations o
        JOIN nodes n ON o.node_id = n.id
        WHERE n.project = ?1 OR n.project = 'global'
        ORDER BY o.observed_at DESC
        LIMIT 10
        "#,
    )?;

    let observations = obs_stmt
        .query_map(params![prj], |r| {
            Ok(json!({
                "node_id": r.get::<_, String>(0)?,
                "observation": r.get::<_, String>(1)?,
                "observer": r.get::<_, String>(2)?,
                "observed_at": r.get::<_, String>(3)?,
            }))
        })?
        .flatten()
        .collect::<Vec<_>>();

    Ok(json!({
        "project": prj,
        "total_active_nodes": nodes.len(),
        "recent_nodes": nodes,
        "recent_observations": observations
    }))
}

pub fn decay_audit(
    conn: &Connection,
    project_opt: Option<&str>,
    prune_threshold_opt: Option<f64>,
    dry_run_opt: Option<bool>,
) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");
    let threshold = prune_threshold_opt.unwrap_or(0.15);
    let dry_run = dry_run_opt.unwrap_or(true);

    let mut stmt = conn.prepare(
        "SELECT id, title, confidence, last_accessed, updated_at FROM nodes WHERE project = ?1 OR project = 'global'",
    )?;

    let mut pruned = Vec::new();
    let mut dormant = Vec::new();

    let rows = stmt.query_map(params![prj], |r| {
        Ok((
            r.get::<_, String>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, f64>(2)?,
            r.get::<_, String>(3)?,
            r.get::<_, String>(4)?,
        ))
    })?;

    for row_res in rows.flatten() {
        let (id, title, conf, _last, _upd) = row_res;
        if conf < threshold {
            if !dry_run {
                let _ = conn.execute("DELETE FROM nodes WHERE id = ?1", params![id]);
            }
            pruned.push(json!({"id": id, "title": title, "confidence": conf}));
        } else if conf < 0.5 {
            dormant.push(json!({"id": id, "title": title, "confidence": conf}));
        }
    }

    Ok(json!({
        "dry_run": dry_run,
        "prune_threshold": threshold,
        "pruned_count": pruned.len(),
        "dormant_count": dormant.len(),
        "pruned": pruned,
        "dormant": dormant
    }))
}

pub fn checkpoint_brain(
    conn: &Connection,
    summary: &str,
    files_modified_opt: Option<&str>,
    active_task_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");
    let now = Utc::now();
    let ts = now.format("%Y%m%d%H%M%S").to_string();
    let node_id = format!("checkpoint-{}", ts);
    let title = format!("Session Checkpoint {}", now.format("%Y-%m-%d %H:%M"));

    let content = format!(
        "Summary: {}\nFiles: {}\nActive Task: {}",
        summary,
        files_modified_opt.unwrap_or(""),
        active_task_opt.unwrap_or("")
    );

    create_entity(
        conn,
        Some(&node_id),
        &title,
        Some("checkpoint"),
        Some(&content),
        Some("checkpoint, session"),
        Some("@orchestrator"),
        Some(prj),
    )?;

    Ok(json!({
        "status": "checkpoint_created",
        "checkpoint_id": node_id,
        "summary": summary
    }))
}

pub fn delete_entity(conn: &Connection, node_id: &str) -> Result<Value> {
    let affected = conn.execute("DELETE FROM nodes WHERE id = ?1", params![node_id])?;
    Ok(json!({
        "status": if affected > 0 { "deleted" } else { "not_found" },
        "node_id": node_id
    }))
}

pub fn remove_relation(conn: &Connection, source: &str, target: &str, relation: &str) -> Result<Value> {
    let affected = conn.execute(
        "DELETE FROM edges WHERE source_id = ?1 AND target_id = ?2 AND relation = ?3",
        params![source, target, relation.to_uppercase()],
    )?;
    Ok(json!({
        "status": if affected > 0 { "removed" } else { "not_found" },
        "source": source,
        "target": target,
        "relation": relation
    }))
}

pub fn merge_nodes(conn: &Connection, source_id: &str, target_id: &str, append_content: Option<bool>) -> Result<Value> {
    let append = append_content.unwrap_or(true);

    if append {
        let src_content: String = conn
            .query_row("SELECT content FROM nodes WHERE id = ?1", params![source_id], |r| r.get(0))
            .unwrap_or_default();

        if !src_content.is_empty() {
            let _ = conn.execute(
                "UPDATE nodes SET content = content || '\n\n' || ?1 WHERE id = ?2",
                params![src_content, target_id],
            );
        }
    }

    // Re-link edges
    let _ = conn.execute("UPDATE OR IGNORE edges SET source_id = ?1 WHERE source_id = ?2", params![target_id, source_id]);
    let _ = conn.execute("UPDATE OR IGNORE edges SET target_id = ?1 WHERE target_id = ?2", params![target_id, source_id]);
    // Re-link observations
    let _ = conn.execute("UPDATE observations SET node_id = ?1 WHERE node_id = ?2", params![target_id, source_id]);
    // Delete source
    let _ = conn.execute("DELETE FROM nodes WHERE id = ?1", params![source_id]);

    Ok(json!({
        "status": "merged",
        "absorbed_id": source_id,
        "surviving_id": target_id
    }))
}

pub fn list_entities(
    conn: &Connection,
    node_type_opt: Option<&str>,
    project_opt: Option<&str>,
    min_confidence_opt: Option<f64>,
    limit_opt: Option<usize>,
) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");
    let min_conf = min_confidence_opt.unwrap_or(0.0);
    let limit = limit_opt.unwrap_or(30);

    let mut sql = "SELECT id, title, node_type, project, confidence, tags FROM nodes WHERE (project = ?1 OR project = 'global') AND confidence >= ?2".to_string();
    if let Some(nt) = node_type_opt {
        sql.push_str(&format!(" AND node_type = '{}'", nt));
    }
    sql.push_str(&format!(" ORDER BY updated_at DESC LIMIT {}", limit));

    let mut stmt = conn.prepare(&sql)?;
    let items = stmt
        .query_map(params![prj, min_conf], |r| {
            Ok(json!({
                "id": r.get::<_, String>(0)?,
                "title": r.get::<_, String>(1)?,
                "type": r.get::<_, String>(2)?,
                "project": r.get::<_, String>(3)?,
                "confidence": r.get::<_, f64>(4)?,
                "tags": r.get::<_, String>(5)?,
            }))
        })?
        .flatten()
        .collect::<Vec<_>>();

    Ok(json!({
        "count": items.len(),
        "entities": items
    }))
}

pub fn record_learning(
    conn: &Connection,
    lesson: &str,
    category_opt: Option<&str>,
    trigger_node_opt: Option<&str>,
    agent_name_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let cat = category_opt.unwrap_or("gotcha");
    let prj = project_opt.unwrap_or("global");
    let agent = agent_name_opt.unwrap_or("@backend");
    let title = format!("Learning: {}", lesson.chars().take(50).collect::<String>());
    let node_id = slugify(&title);

    create_entity(
        conn,
        Some(&node_id),
        &title,
        Some("learning"),
        Some(lesson),
        Some(&format!("learning, {}", cat)),
        Some(agent),
        Some(prj),
    )?;

    if let Some(trig) = trigger_node_opt {
        relate(conn, &node_id, trig, "LEARNED_FROM", Some("Context of discovery"), Some(1.0))?;
    }

    Ok(json!({
        "status": "learning_recorded",
        "id": node_id,
        "lesson": lesson,
        "category": cat
    }))
}
