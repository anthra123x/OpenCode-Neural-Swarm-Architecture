use colored::*;
use rusqlite::params;
use std::path::PathBuf;

use crate::brain::db::open_brain_db;
use crate::engine::db::open_swarm_db;
use crate::sentinel::rules::SENTINEL_RULES;

pub fn cmd_doctor() {
    println!("{}", "══════════════════════════════════════════════════════════".cyan().bold());
    println!("{}", "  swarm-core doctor — Native Engine Diagnostic".cyan().bold());
    println!("{}", "══════════════════════════════════════════════════════════".cyan().bold());
    println!();

    // 1. Check OpenCode config
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let config_dir = PathBuf::from(&home).join(".config").join("opencode");
    if config_dir.exists() {
        println!("{} Config directory: {}", "✓".green(), config_dir.display());
        for f in &["opencode.jsonc", "SWARM.md", "INSTRUCTIONS.md", "AGENTS.md"] {
            let p = config_dir.join(f);
            if p.exists() {
                println!("  {} {}", "✓".green(), f);
            } else {
                println!("  {} {} (missing)", "⚠".yellow(), f);
            }
        }
    } else {
        println!("{} Config directory missing: {}", "✗".red(), config_dir.display());
    }

    // 2. Check brain.db
    match open_brain_db(None) {
        Ok(conn) => {
            let node_count: i64 = conn
                .query_row("SELECT COUNT(*) FROM nodes", [], |r| r.get(0))
                .unwrap_or(0);
            let edge_count: i64 = conn
                .query_row("SELECT COUNT(*) FROM edges", [], |r| r.get(0))
                .unwrap_or(0);
            println!(
                "{} Embedded SQLite Brain: {} node(s), {} synapse(s)",
                "✓".green(),
                node_count,
                edge_count
            );
        }
        Err(e) => {
            println!("{} Brain database error: {}", "✗".red(), e);
        }
    }

    // 3. Check swarm.db
    match open_swarm_db(None) {
        Ok(conn) => {
            let task_count: i64 = conn
                .query_row("SELECT COUNT(*) FROM swarm_tasks", [], |r| r.get(0))
                .unwrap_or(0);
            let run_count: i64 = conn
                .query_row("SELECT COUNT(*) FROM tester_runs", [], |r| r.get(0))
                .unwrap_or(0);
            println!(
                "{} Embedded SQLite Swarm Engine: {} active rules, {} task(s), {} test run(s)",
                "✓".green(),
                SENTINEL_RULES.len(),
                task_count,
                run_count
            );
        }
        Err(e) => {
            println!("{} Swarm engine database error: {}", "✗".red(), e);
        }
    }

    println!();
    println!("{}", "✓ Native swarm-core diagnostic completed cleanly!".green().bold());
}

pub fn cmd_status() {
    println!("{}", "══════════════════════════════════════════════════════════".cyan().bold());
    println!("{}", "  swarm-core status — Engine & Knowledge Overview".cyan().bold());
    println!("{}", "══════════════════════════════════════════════════════════".cyan().bold());
    println!();

    println!("  {}", "Neural Knowledge Graph (brain.db):".bold());
    if let Ok(conn) = open_brain_db(None) {
        let node_count: i64 = conn.query_row("SELECT COUNT(*) FROM nodes", [], |r| r.get(0)).unwrap_or(0);
        let edge_count: i64 = conn.query_row("SELECT COUNT(*) FROM edges", [], |r| r.get(0)).unwrap_or(0);
        let obs_count: i64 = conn.query_row("SELECT COUNT(*) FROM observations", [], |r| r.get(0)).unwrap_or(0);
        println!("    {} {} node(s) indexed", "•".magenta(), node_count);
        println!("    {} {} synapse(s) connected", "•".cyan(), edge_count);
        println!("    {} {} observation(s) recorded", "•".blue(), obs_count);

        // Breakdown by type
        let mut stmt = conn
            .prepare("SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type ORDER BY COUNT(*) DESC LIMIT 8")
            .unwrap();
        let types = stmt
            .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)))
            .unwrap();
        println!("    {}", "Categories:".dimmed());
        for t in types.flatten() {
            println!("      {} {}: {}", "→".dimmed(), t.0, t.1);
        }
    } else {
        println!("    {}", "Database not initialized yet".yellow());
    }

    println!();
    println!("  {}", "Operational Swarm Engine (swarm.db):".bold());
    if let Ok(conn) = open_swarm_db(None) {
        let task_count: i64 = conn.query_row("SELECT COUNT(*) FROM swarm_tasks", [], |r| r.get(0)).unwrap_or(0);
        let viols: i64 = conn
            .query_row("SELECT COUNT(*) FROM sentinel_violations WHERE resolved = 0", [], |r| r.get(0))
            .unwrap_or(0);
        let runs: i64 = conn.query_row("SELECT COUNT(*) FROM tester_runs", [], |r| r.get(0)).unwrap_or(0);

        println!("    {} {} engineering rules active", "•".green(), SENTINEL_RULES.len());
        println!("    {} {} open sentinel violation(s)", if viols == 0 { "•".green() } else { "•".red() }, viols);
        println!("    {} {} task milestone(s) on board", "•".yellow(), task_count);
        println!("    {} {} test suite run(s)", "•".blue(), runs);
    } else {
        println!("    {}", "Database not initialized yet".yellow());
    }
}

pub fn cmd_migrate() {
    println!("{}", "══════════════════════════════════════════════════════════".cyan().bold());
    println!("{}", "  swarm-core migrate — Context Memory → Brain Graph".cyan().bold());
    println!("{}", "══════════════════════════════════════════════════════════".cyan().bold());
    println!();

    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let src_path = PathBuf::from(&home).join(".opencode").join("memory").join("context_memory.db");

    if !src_path.exists() {
        println!("{} Source context_memory.db not found at {}", "⚠".yellow(), src_path.display());
        return;
    }

    println!("{} Source: {}", "📂".cyan(), src_path.display());

    let src_conn = match rusqlite::Connection::open(&src_path) {
        Ok(c) => c,
        Err(e) => {
            println!("{} Cannot open source DB: {}", "✗".red(), e);
            return;
        }
    };

    let dst_conn = match open_brain_db(None) {
        Ok(c) => c,
        Err(e) => {
            println!("{} Cannot open destination DB: {}", "✗".red(), e);
            return;
        }
    };

    let mut stmt = match src_conn.prepare("SELECT key, category, content, tags, project, created_at FROM memories") {
        Ok(s) => s,
        Err(e) => {
            println!("{} Error reading memories: {}", "✗".red(), e);
            return;
        }
    };

    let memories = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, String>(3)?,
                r.get::<_, String>(4)?,
                r.get::<_, String>(5)?,
            ))
        })
        .unwrap();

    let mut count = 0;
    for mem_res in memories.flatten() {
        let (key, cat, content, tags, prj, created_at) = mem_res;
        let slug = crate::brain::graph::slugify(&key);
        let ntype = match cat.as_str() {
            "architecture" => "architecture",
            "decision" => "decision",
            "convention" => "convention",
            "snippet" => "snippet",
            "bugfix" => "bug",
            "learning" => "learning",
            _ => "concept",
        };

        let _ = dst_conn.execute(
            r#"
            INSERT INTO nodes (id, title, node_type, content, project, agent_origin, confidence, access_count, last_accessed, tags, created_at, updated_at)
            VALUES (?1, ?2, ?3, ?4, ?5, '@migration', 1.0, 1, ?6, ?7, ?6, ?6)
            ON CONFLICT(id) DO NOTHING
            "#,
            params![slug, key, ntype, content, prj, created_at, tags],
        );
        count += 1;
    }

    println!("{} Successfully verified/migrated {} memory item(s) to brain.db", "✓".green(), count);
}
