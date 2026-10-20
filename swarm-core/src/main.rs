mod brain;
mod cli;
mod engine;
mod mcp;
mod sentinel;
mod tester;

use clap::{Parser, Subcommand};
use colored::*;

#[derive(Parser)]
#[command(name = "swarm-core")]
#[command(author = "OpenCode Swarm Team")]
#[command(version = "2.0.0")]
#[command(about = "High-performance neural knowledge graph and operational quality engine for OpenCode", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run as an MCP (Model Context Protocol) server over stdio
    Mcp {
        /// Mode: 'brain' (brain-graph), 'engine' (swarm-engine), or 'all' (unified)
        #[arg(default_value = "all")]
        mode: String,
    },
    /// Run diagnostic checks on OpenCode Swarm installation and databases
    Doctor,
    /// Inspect brain graph statistics, active sentinel rules, and task board
    Status,
    /// Migrate legacy context-memory.db to brain.db
    Migrate,
    /// Probe an HTTP endpoint for status and latency
    Probe {
        /// URL to probe
        url: String,
        /// Expected status code (default 200)
        #[arg(short, long, default_value_t = 200)]
        status: u16,
    },
    /// Run automated test suite
    Test {
        /// Target path or test file
        #[arg(default_value = ".")]
        path: String,
        /// Specific runner to use (pytest, vitest, cargo, etc.)
        #[arg(short, long)]
        runner: Option<String>,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Mcp { mode } => {
            if let Err(e) = mcp::run_mcp_server(&mode) {
                eprintln!("{} MCP server error: {}", "✗".red(), e);
                std::process::exit(1);
            }
        }
        Commands::Doctor => {
            cli::cmd_doctor();
        }
        Commands::Status => {
            cli::cmd_status();
        }
        Commands::Migrate => {
            cli::cmd_migrate();
        }
        Commands::Probe { url, status } => {
            let res = tester::probe::tester_probe_endpoint(&url, Some("GET"), Some(status), None, Some(5.0));
            println!("{}", serde_json::to_string_pretty(&res).unwrap());
        }
        Commands::Test { path, runner } => {
            if let Ok(conn) = engine::db::open_swarm_db(None) {
                let res = tester::runner::tester_run_suite(&conn, Some(&path), runner.as_deref(), Some(true), Some(60), None);
                match res {
                    Ok(val) => println!("{}", serde_json::to_string_pretty(&val).unwrap()),
                    Err(e) => eprintln!("Test error: {}", e),
                }
            } else {
                eprintln!("Failed to open swarm.db");
            }
        }
    }
}
