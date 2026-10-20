use chrono::Utc;
use rusqlite::{params, Connection, Result};
use serde_json::{json, Value};

pub fn swarm_post_task(
    conn: &Connection,
    title: &str,
    description: &str,
    assigned_to: &str,
    priority_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let prio = priority_opt.unwrap_or("normal");
    let prj = project_opt.unwrap_or("global");
    let now = Utc::now().to_rfc3339();

    conn.execute(
        r#"
        INSERT INTO swarm_tasks (title, description, assigned_to, status, priority, project, created_at, updated_at)
        VALUES (?1, ?2, ?3, 'todo', ?4, ?5, ?6, ?6)
        "#,
        params![title, description, assigned_to, prio, prj, now],
    )?;

    let id = conn.last_insert_rowid();
    Ok(json!({
        "status": "task_posted",
        "task_id": id,
        "title": title,
        "assigned_to": assigned_to
    }))
}

pub fn swarm_update_task(
    conn: &Connection,
    task_id: i64,
    status: &str,
    notes_opt: Option<&str>,
    _project_opt: Option<&str>,
) -> Result<Value> {
    let now = Utc::now().to_rfc3339();
    let notes = notes_opt.unwrap_or("");

    let affected = conn.execute(
        "UPDATE swarm_tasks SET status = ?1, notes = ?2, updated_at = ?3 WHERE id = ?4",
        params![status, notes, now, task_id],
    )?;

    Ok(json!({
        "status": if affected > 0 { "updated" } else { "not_found" },
        "task_id": task_id,
        "task_status": status
    }))
}

pub fn swarm_list_tasks(
    conn: &Connection,
    status_opt: Option<&str>,
    assigned_to_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");

    let mut sql = "SELECT id, title, description, assigned_to, status, priority, notes, updated_at FROM swarm_tasks WHERE (project = ?1 OR project = 'global')".to_string();
    if let Some(st) = status_opt {
        sql.push_str(&format!(" AND status = '{}'", st));
    }
    if let Some(agent) = assigned_to_opt {
        sql.push_str(&format!(" AND assigned_to = '{}'", agent));
    }
    sql.push_str(" ORDER BY updated_at DESC LIMIT 50");

    let mut stmt = conn.prepare(&sql)?;
    let tasks = stmt
        .query_map(params![prj], |r| {
            Ok(json!({
                "id": r.get::<_, i64>(0)?,
                "title": r.get::<_, String>(1)?,
                "description": r.get::<_, String>(2)?,
                "assigned_to": r.get::<_, String>(3)?,
                "status": r.get::<_, String>(4)?,
                "priority": r.get::<_, String>(5)?,
                "notes": r.get::<_, String>(6)?,
                "updated_at": r.get::<_, String>(7)?,
            }))
        })?
        .flatten()
        .collect::<Vec<_>>();

    Ok(json!({
        "count": tasks.len(),
        "tasks": tasks
    }))
}

pub fn swarm_share_artifact(
    conn: &Connection,
    artifact_key: &str,
    title: &str,
    content: &str,
    artifact_type_opt: Option<&str>,
    creator_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let a_type = artifact_type_opt.unwrap_or("contract");
    let creator = creator_opt.unwrap_or("@backend");
    let prj = project_opt.unwrap_or("global");
    let now = Utc::now().to_rfc3339();

    conn.execute(
        r#"
        INSERT INTO swarm_artifacts (key, title, content, artifact_type, creator, project, created_at, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?7)
        ON CONFLICT(key) DO UPDATE SET
            title = excluded.title,
            content = excluded.content,
            artifact_type = excluded.artifact_type,
            updated_at = excluded.updated_at
        "#,
        params![artifact_key, title, content, a_type, creator, prj, now],
    )?;

    Ok(json!({
        "status": "artifact_shared",
        "key": artifact_key,
        "title": title,
        "type": a_type
    }))
}

pub fn swarm_get_artifact(conn: &Connection, artifact_key: &str, _project_opt: Option<&str>) -> Result<Value> {
    let res = conn.query_row(
        "SELECT key, title, content, artifact_type, creator, updated_at FROM swarm_artifacts WHERE key = ?1",
        params![artifact_key],
        |r| {
            Ok(json!({
                "key": r.get::<_, String>(0)?,
                "title": r.get::<_, String>(1)?,
                "content": r.get::<_, String>(2)?,
                "type": r.get::<_, String>(3)?,
                "creator": r.get::<_, String>(4)?,
                "updated_at": r.get::<_, String>(5)?,
            }))
        },
    );

    match res {
        Ok(art) => Ok(json!({ "found": true, "artifact": art })),
        Err(_) => Ok(json!({ "found": false, "key": artifact_key })),
    }
}

pub fn swarm_gate_check(conn: &Connection, task_id_opt: Option<i64>, project_opt: Option<&str>) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");

    let open_violations: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sentinel_violations WHERE resolved = 0 AND severity = 'critical' AND (project = ?1 OR project = 'global')",
            params![prj],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let failed_runs: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM tester_runs WHERE status = 'failed' AND (project = ?1 OR project = 'global')",
            params![prj],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let mut task_done = true;
    if let Some(tid) = task_id_opt {
        let status: String = conn
            .query_row("SELECT status FROM swarm_tasks WHERE id = ?1", params![tid], |r| r.get(0))
            .unwrap_or_else(|_| "unknown".to_string());
        task_done = status == "done";
    }

    let gate_passed = open_violations == 0 && failed_runs == 0 && task_done;

    Ok(json!({
        "status": if gate_passed { "GATE_PASSED" } else { "GATE_FAILED" },
        "gate_passed": gate_passed,
        "critical_violations": open_violations,
        "failed_test_runs": failed_runs,
        "task_done": task_done
    }))
}
