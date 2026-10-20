use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct SentinelRule {
    pub code: &'static str,
    pub name: &'static str,
    pub target_agent: &'static str,
    pub severity: &'static str,
    pub description: &'static str,
    pub checklist: &'static [&'static str],
}

pub const SENTINEL_RULES: &[SentinelRule] = &[
    SentinelRule {
        code: "TDD-001",
        name: "Test-Driven Development",
        target_agent: "backend",
        severity: "critical",
        description: "Unit tests are mandatory with >=80% coverage before marking tasks complete.",
        checklist: &[
            "Test suite file exists alongside or in tests/ directory",
            "Code coverage is measured and reaches >= 80%",
            "Negative edge cases and error branches tested",
        ],
    },
    SentinelRule {
        code: "VERIF-001",
        name: "6-Stage Verification Loop",
        target_agent: "qa-auditor",
        severity: "critical",
        description: "Must verify Build, Types, Lint, Tests, Security, and Regressions prior to signoff.",
        checklist: &[
            "1. Build/Syntax check passed cleanly",
            "2. Type checking verified with zero errors",
            "3. Linter enforcement verified",
            "4. Automated unit/integration tests all green",
            "5. OWASP defensive audit clean",
            "6. Regression checks against core flows passed",
        ],
    },
    SentinelRule {
        code: "GIT-001",
        name: "Conventional Commits 1.0",
        target_agent: "git-flow",
        severity: "high",
        description: "All commits must follow Conventional Commits 1.0 format with clean status.",
        checklist: &[
            "Format: type(scope): subject (feat, fix, refactor, docs, chore)",
            "Git working tree clean without untracked artifacts or caches",
            "Atomic commit philosophy maintained",
        ],
    },
    SentinelRule {
        code: "UI-001",
        name: "Anti-Slop UI & Tactile Motion",
        target_agent: "frontend",
        severity: "high",
        description: "Anti-slop design, curated color tokens, spring physics, and WCAG AA accessibility.",
        checklist: &[
            "Curated color palette with semantic tokens (no plain raw defaults)",
            "Responsive layout tested for mobile and desktop",
            "Spring-based transitions and micro-interactions implemented",
            "Semantic HTML and WCAG AA contrast compliance",
        ],
    },
    SentinelRule {
        code: "SEC-001",
        name: "Zero Hardcoded Secrets & Defense in Depth",
        target_agent: "all",
        severity: "critical",
        description: "Never hardcode API keys, tokens, or credentials. Sanitize inputs and prepare SQL.",
        checklist: &[
            "No API keys, JWT secrets or credentials in codebase",
            "All configuration loaded via environment variables / .env",
            "Input boundary validation and sanitization applied",
            "Parameterized queries or ORM used to prevent SQL injection",
        ],
    },
    SentinelRule {
        code: "ARCH-001",
        name: "Clean Architecture & SRP",
        target_agent: "all",
        severity: "high",
        description: "Single Responsibility Principle, modular files (<800 lines), and typed errors.",
        checklist: &[
            "Files kept under 800 lines",
            "Clear separation of concerns (controller -> service -> model)",
            "Typed error handling (no empty catch blocks or discarded errors)",
        ],
    },
    SentinelRule {
        code: "HANDOFF-001",
        name: "Formal Shared Contracts",
        target_agent: "all",
        severity: "high",
        description: "Share explicit contracts via swarm_share_artifact before delegating between agents.",
        checklist: &[
            "API schemas or data models documented as shared artifacts",
            "Dependencies between frontend and backend declared in graph",
            "Delivery status explicitly marked with test outcomes",
        ],
    },
];
