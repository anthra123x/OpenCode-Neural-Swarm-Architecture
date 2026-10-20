use chrono::Utc;
use rusqlite::{params, Connection, Result};
use serde_json::{json, Value};

use super::rules::SENTINEL_RULES;

pub fn sentinel_get_rules(category_opt: Option<&str>, target_agent_opt: Option<&str>) -> Value {
    let mut rules = Vec::new();
    for r in SENTINEL_RULES {
        if let Some(target) = target_agent_opt {
            if r.target_agent != "all" && r.target_agent != target {
                continue;
            }
        }
        if let Some(cat) = category_opt {
            if !r.description.to_lowercase().contains(&cat.to_lowercase()) {
                continue;
            }
        }
        rules.push(json!({
            "code": r.code,
            "name": r.name,
            "target_agent": r.target_agent,
            "severity": r.severity,
            "description": r.description,
            "checklist": r.checklist
        }));
    }
    json!({
        "count": rules.len(),
        "rules": rules
    })
}

pub fn sentinel_record_violation(
    conn: &Connection,
    rule_code: &str,
    agent_name: &str,
    details: &str,
    severity_opt: Option<&str>,
    task_title_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let sev = severity_opt.unwrap_or("high");
    let task = task_title_opt.unwrap_or("");
    let prj = project_opt.unwrap_or("global");
    let now = Utc::now().to_rfc3339();

    conn.execute(
        r#"
        INSERT INTO sentinel_violations (rule_code, agent_name, task_title, details, severity, project, resolved, created_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, 0, ?7)
        "#,
        params![rule_code, agent_name, task, details, sev, prj, now],
    )?;

    let id = conn.last_insert_rowid();
    Ok(json!({
        "status": "violation_recorded",
        "violation_id": id,
        "rule_code": rule_code,
        "severity": sev
    }))
}

pub fn sentinel_resolve_violation(conn: &Connection, violation_id: i64, notes: &str) -> Result<Value> {
    let now = Utc::now().to_rfc3339();
    let affected = conn.execute(
        "UPDATE sentinel_violations SET resolved = 1, resolution_notes = ?1, resolved_at = ?2 WHERE id = ?3",
        params![notes, now, violation_id],
    )?;

    Ok(json!({
        "status": if affected > 0 { "resolved" } else { "not_found" },
        "violation_id": violation_id
    }))
}

pub fn sentinel_verify_compliance(conn: &Connection, agent_opt: Option<&str>, project_opt: Option<&str>) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");
    let mut sql = "SELECT id, rule_code, agent_name, task_title, details, severity, created_at FROM sentinel_violations WHERE resolved = 0 AND (project = ?1 OR project = 'global')".to_string();
    if let Some(agent) = agent_opt {
        sql.push_str(&format!(" AND agent_name = '{}'", agent));
    }

    let mut stmt = conn.prepare(&sql)?;
    let violations = stmt
        .query_map(params![prj], |r| {
            Ok(json!({
                "id": r.get::<_, i64>(0)?,
                "rule_code": r.get::<_, String>(1)?,
                "agent_name": r.get::<_, String>(2)?,
                "task_title": r.get::<_, String>(3)?,
                "details": r.get::<_, String>(4)?,
                "severity": r.get::<_, String>(5)?,
                "created_at": r.get::<_, String>(6)?,
            }))
        })?
        .flatten()
        .collect::<Vec<_>>();

    let is_compliant = violations.is_empty();
    Ok(json!({
        "compliant": is_compliant,
        "open_violations_count": violations.len(),
        "violations": violations
    }))
}

pub fn sentinel_audit_task(
    conn: &Connection,
    agent_name: &str,
    task_title: &str,
    deliverables: &str,
    files_modified_opt: Option<&str>,
    test_results_opt: Option<&str>,
    project_opt: Option<&str>,
) -> Result<Value> {
    let mut score = 100;
    let mut infractions = Vec::new();
    let prj = project_opt.unwrap_or("global");

    let deliv_lower = deliverables.to_lowercase();
    let test_res = test_results_opt.unwrap_or("").to_lowercase();

    // Check TDD-001 for backend
    if agent_name.contains("backend") {
        if test_res.is_empty() && !deliv_lower.contains("test") && !deliv_lower.contains("coverage") {
            score -= 30;
            infractions.push("TDD-001: No test execution or coverage report found in backend deliverables.");
            let _ = sentinel_record_violation(
                conn,
                "TDD-001",
                agent_name,
                "Backend deliverable submitted without test suite execution",
                Some("critical"),
                Some(task_title),
                Some(prj),
            );
        }
    }

    // Check SEC-001 for hardcoded secrets
    let secret_patterns = ["sk-", "ghp_", "bearer ", "password =", "secret ="];
    for pat in secret_patterns {
        if deliv_lower.contains(pat) {
            score -= 40;
            infractions.push("SEC-001: Potential credential/secret detected in deliverables payload.");
            let _ = sentinel_record_violation(
                conn,
                "SEC-001",
                agent_name,
                &format!("Potential credential found matching pattern '{}'", pat),
                Some("critical"),
                Some(task_title),
                Some(prj),
            );
            break;
        }
    }

    let certified = score >= 80 && infractions.is_empty();

    Ok(json!({
        "status": if certified { "CERTIFIED" } else { "REJECTED" },
        "score": score,
        "agent": agent_name,
        "task": task_title,
        "infractions": infractions,
        "files_modified": files_modified_opt.unwrap_or(""),
        "certified": certified
    }))
}

pub fn sentinel_get_compliance_report(conn: &Connection, days_opt: Option<i64>, project_opt: Option<&str>) -> Result<Value> {
    let prj = project_opt.unwrap_or("global");
    let days = days_opt.unwrap_or(7);

    let total: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sentinel_violations WHERE project = ?1 OR project = 'global'",
            params![prj],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let open_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sentinel_violations WHERE resolved = 0 AND (project = ?1 OR project = 'global')",
            params![prj],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let resolved_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sentinel_violations WHERE resolved = 1 AND (project = ?1 OR project = 'global')",
            params![prj],
            |r| r.get(0),
        )
        .unwrap_or(0);

    let score = if total == 0 {
        100
    } else {
        (resolved_count * 100) / total
    };

    Ok(json!({
        "project": prj,
        "days": days,
        "compliance_score": score,
        "total_violations": total,
        "open_violations": open_count,
        "resolved_violations": resolved_count
    }))
}
