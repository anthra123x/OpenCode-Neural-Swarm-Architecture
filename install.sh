#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$REPO_DIR/lib/ui.sh"
source "$REPO_DIR/lib/paths.sh"
source "$REPO_DIR/lib/utils.sh"

setup_ui
setup_paths
setup_utils

# ──────────────── STEP: Welcome ────────────────

print_banner
msgbox "Welcome" \
"Welcome to the opencode Multi-Agent Swarm Configuration Manager!

This installer will set up:

  • 6 Specialized Sub-Agents (@orchestrator, @backend, @frontend, @git-flow, @qa-auditor, @devops)
  • 3 Native MCP Servers:
      - context-memory (Persistent context with SQLite FTS5)
      - team-collab (Inter-agent communication & task board)
      - swarm-sentinel (Engineering rules guardian & automated task auditor)
  • 34 ECC skills for engineering, testing, DB, design, infra
  • Engineering methodology & Swarm Lifecycle (INSTRUCTIONS.md)
  • Multi-agent rules & memory protocols (AGENTS.md)
  • Aesthetic TUI Theme & Custom Slash Commands (/team, /memory, etc.)

Two modes available:
  - Quickstart: minimal prompts, recommended
  - Manual: full control over every option

Total install size: ~1MB  |  Time: 30-60 seconds"

# ──────────────── STEP: Prerequisites ────────────────

PREREQ_FAIL=false
infobox "Checking" "Checking prerequisites..."

# Check bash version >= 4
if [[ ${BASH_VERSINFO[0]} -lt 4 ]]; then
  warn "bash 4+ required (found ${BASH_VERSINFO[0]})"
  PREREQ_FAIL=true
fi

# Check whiptail
if ! command -v whiptail &>/dev/null; then
  warn "whiptail not found — falling back to plain text mode"
  UI_WHIPTAIL=false
fi

# Check opencode or claude
if command -v opencode &>/dev/null; then
  AGENT_BIN="opencode"
  log "Found opencode at $(command -v opencode)"
elif command -v claude &>/dev/null; then
  AGENT_BIN="claude"
  log "Found Claude Code at $(command -v claude)"
else
  AGENT_BIN=""
  warn "Neither opencode nor claude found in PATH"
  warn "Install opencode: see https://opencode.ai"
fi

# Check python3 and SQLite FTS5
if detect_python; then
  if detect_sqlite_fts5; then
    log "Found Python 3 with SQLite FTS5 support: $(python3 --version)"
  else
    warn "Python 3 found but SQLite FTS5 extension missing (context-memory may use LIKE fallback)"
  fi
else
  warn "python3 not found — required for native MCP servers"
  PREREQ_FAIL=true
fi

# Check git
if command -v git &>/dev/null; then
  log "Found git: $(git --version | head -1)"
else
  warn "git not found — updates via 'ecc update' disabled"
fi

echo ""

if $PREREQ_FAIL; then
  msgbox "Prerequisites Failed" \
"Some prerequisites are missing. Please fix them and re-run:

  • bash >= 4
  • python3 (with sqlite3)

After installing, run ./install.sh again."
  exit 1
fi

# ──────────────── STEP: Select mode ────────────────

MODE=""
if yesno "Installation Mode" \
"Do you want Quickstart mode?

  [Yes] = Quickstart — install full Swarm suite (agents, MCPs, skills, TUI)
  [No]  = Manual — select components and custom paths"; then
  MODE="quickstart"
  infobox "Mode" "Quickstart selected — installing full Swarm suite"
else
  MODE="manual"
  infobox "Mode" "Manual selected — full configuration wizard"
fi

# ──────────────── STEP: Configuration ────────────────

USER_NAME=$(inputbox "User" "Enter your name or alias (for config headers):" "${USER:-user}")
GITHUB_HANDLE=$(inputbox "GitHub" "Enter your GitHub username (optional):" "")

if [[ "$MODE" == "manual" ]]; then
  CHOICES=$(
    checklist "Components" \
"Select components to install:" 20 68 8 \
  "CONFIG"   "Core configuration (JSONC, instructions, rules)" ON \
  "AGENTS"   "6 Specialized Sub-Agents (orchestrator, etc.)" ON \
  "MCP"      "Native MCP servers (context-memory & team-collab)" ON \
  "SKILLS"   "All 34 ECC engineering skills" ON \
  "COMMANDS" "Custom commands (/team, /memory, /backend, etc.)" ON \
  "TUI"      "Aesthetic TUI theme (tokyonight) & layout" ON \
  "PLUGINS"  "OpenCode plugins (team-hud)" ON \
  "LIBS"     "Shared libraries & CLI tools" ON
  )
else
  CHOICES="CONFIG AGENTS MCP SKILLS COMMANDS TUI PLUGINS LIBS"
fi

if [[ "$MODE" == "manual" ]]; then
  CONFIG_DIR=$(inputbox "Config path" "opencode config directory:" "$OPENCODE_CONFIG")
  SKILLS_DIR=$(inputbox "Skills path" "Skills directory:" "$OPENCODE_SKILLS")
else
  CONFIG_DIR="$OPENCODE_CONFIG"
  SKILLS_DIR="$OPENCODE_SKILLS"
fi

# ──────────────── STEP: Install ────────────────

SKILL_COUNT=$(count_dirs "$REPO_DIR/skills" 1)
AGENT_COUNT=$(count_dirs "$REPO_DIR/agents" 1)
[ "$AGENT_COUNT" -eq 0 ] && AGENT_COUNT=$(find "$REPO_DIR/agents" -name "*.md" 2>/dev/null | wc -l)

INSTALL_STEPS=12
CURRENT_STEP=0
do_step() {
  CURRENT_STEP=$((CURRENT_STEP + 1))
  local pct=$((CURRENT_STEP * 100 / INSTALL_STEPS))
  if [[ "$UI_WHIPTAIL" == "true" ]]; then
    echo "XXX"
    echo "$pct"
    echo "$1"
    echo "XXX"
  else
    echo -e "  [${pct}%] $1"
  fi
}

# Create base directories
infobox "Preparing" "Creating directories..."
mkdir -p "$CONFIG_DIR/agents"
mkdir -p "$CONFIG_DIR/commands"
mkdir -p "$CONFIG_DIR/plugins"
mkdir -p "$CONFIG_DIR/mcp"
mkdir -p "$SKILLS_DIR"
mkdir -p "$LOCAL_BIN"

# Backup existing config
if [ -d "$CONFIG_DIR" ]; then
  bk=$(backup_dir "$CONFIG_DIR")
  info "Backup created: $bk"
fi

# 1. Install Core Config
if echo "$CHOICES" | grep -q "CONFIG"; then
  do_step "Installing core configuration..."
  cp "$REPO_DIR/config/opencode.jsonc" "$CONFIG_DIR/opencode.jsonc"
  cp "$REPO_DIR/config/opencode.json" "$CONFIG_DIR/opencode.json"
  cp "$REPO_DIR/config/INSTRUCTIONS.md" "$CONFIG_DIR/INSTRUCTIONS.md"
  cp "$REPO_DIR/config/AGENTS.md" "$CONFIG_DIR/AGENTS.md"
  log "Core configuration installed to $CONFIG_DIR"
fi

# 2. Install TUI Theme & CLI Preferences
if echo "$CHOICES" | grep -q "TUI"; then
  do_step "Installing aesthetic TUI configuration..."
  if [ -f "$REPO_DIR/config/tui.json" ]; then
    cp "$REPO_DIR/config/tui.json" "$CONFIG_DIR/tui.json"
  fi
  if [ -f "$CONFIG_DIR/cli.json" ]; then
    python3 -c "import json; p='$CONFIG_DIR/cli.json'; d=json.load(open(p)); d['theme']={'name':'tokyonight','mode':'dark'}; json.dump(d,open(p,'w'),indent=2)" 2>/dev/null || true
  fi
  log "TUI configuration (tokyonight) installed"
fi

# 3. Install Specialized Agents
if echo "$CHOICES" | grep -q "AGENTS" && [ -d "$REPO_DIR/agents" ]; then
  do_step "Installing specialized sub-agents..."
  mkdir -p "$CONFIG_DIR/agents"
  cp "$REPO_DIR/agents/"*.md "$CONFIG_DIR/agents/" 2>/dev/null || true
  log "Specialized sub-agents installed to $CONFIG_DIR/agents/"
fi

# 4. Install Native MCP Servers
if echo "$CHOICES" | grep -q "MCP" && [ -d "$REPO_DIR/mcp" ]; then
  do_step "Installing native MCP servers..."
  mkdir -p "$CONFIG_DIR/mcp/context-memory"
  mkdir -p "$CONFIG_DIR/mcp/team-collab"
  mkdir -p "$CONFIG_DIR/mcp/swarm-sentinel"
  mkdir -p "$CONFIG_DIR/mcp/swarm-tester"
  cp -r "$REPO_DIR/mcp/context-memory/"* "$CONFIG_DIR/mcp/context-memory/"
  cp -r "$REPO_DIR/mcp/team-collab/"* "$CONFIG_DIR/mcp/team-collab/"
  cp -r "$REPO_DIR/mcp/swarm-sentinel/"* "$CONFIG_DIR/mcp/swarm-sentinel/"
  cp -r "$REPO_DIR/mcp/swarm-tester/"* "$CONFIG_DIR/mcp/swarm-tester/"
  chmod +x "$CONFIG_DIR/mcp/context-memory/server.py" "$CONFIG_DIR/mcp/team-collab/server.py" "$CONFIG_DIR/mcp/swarm-sentinel/server.py" "$CONFIG_DIR/mcp/swarm-tester/server.py"

  # Also copy to swarm/mcp if present
  if [ -d "$CONFIG_DIR/swarm/mcp" ]; then
    for srv in context-memory team-collab swarm-sentinel swarm-tester; do
      mkdir -p "$CONFIG_DIR/swarm/mcp/$srv"
      cp -r "$REPO_DIR/mcp/$srv/"* "$CONFIG_DIR/swarm/mcp/$srv/"
      chmod +x "$CONFIG_DIR/swarm/mcp/$srv/server.py"
    done
  fi

  # Create executable wrappers in ~/.local/bin
  for srv in context-memory team-collab swarm-sentinel swarm-tester; do
    cat > "$LOCAL_BIN/opencode-$srv" <<EOF
#!/usr/bin/env bash
if [ -f "$CONFIG_DIR/mcp/$srv/server.py" ]; then
  exec python3 "$CONFIG_DIR/mcp/$srv/server.py" "\$@"
elif [ -f "$CONFIG_DIR/swarm/mcp/$srv/server.py" ]; then
  exec python3 "$CONFIG_DIR/swarm/mcp/$srv/server.py" "\$@"
else
  echo "[!] Cannot find server.py for $srv in $CONFIG_DIR" >&2
  exit 1
fi
EOF
    chmod +x "$LOCAL_BIN/opencode-$srv"
  done

  log "Native MCP servers installed (context-memory, team-collab, swarm-sentinel, swarm-tester)"
fi

# 5. Install Skills
if echo "$CHOICES" | grep -q "SKILLS" && [ -d "$REPO_DIR/skills" ]; then
  do_step "Installing ECC engineering skills..."
  mkdir -p "$SKILLS_DIR"
  for skill_dir in "$REPO_DIR/skills"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    target="$SKILLS_DIR/$skill_name"
    mkdir -p "$target"
    cp -r "$skill_dir"/* "$target/"
  done
  find "$SKILLS_DIR" \( -name "*.sh" -o -name "*.mjs" -o -name "*.py" \) -exec chmod +x {} + 2>/dev/null || true
  log "$SKILL_COUNT skills installed to $SKILLS_DIR"
fi

# 6. Install Commands
if echo "$CHOICES" | grep -q "COMMANDS"; then
  do_step "Installing custom slash commands..."
  mkdir -p "$CONFIG_DIR/commands"
  if ls "$REPO_DIR/config/commands/"*.md &>/dev/null; then
    cp "$REPO_DIR/config/commands/"*.md "$CONFIG_DIR/commands/"
  fi
  log "Commands installed (/team, /memory, /backend, /frontend, /git-flow, /qa)"
fi

# 7. Install Plugins
if echo "$CHOICES" | grep -q "PLUGINS" && [ -d "$REPO_DIR/config/plugins" ]; then
  do_step "Installing OpenCode plugins..."
  mkdir -p "$CONFIG_DIR/plugins"
  cp -r "$REPO_DIR/config/plugins/"* "$CONFIG_DIR/plugins/" 2>/dev/null || true
  log "Plugins installed to $CONFIG_DIR/plugins/"
fi

# 8. Install Libraries
if echo "$CHOICES" | grep -q "LIBS"; then
  do_step "Installing shared libraries..."
  mkdir -p "$CONFIG_DIR/lib"
  cp "$REPO_DIR/lib/ui.sh" "$CONFIG_DIR/lib/ui.sh"
  cp "$REPO_DIR/lib/paths.sh" "$CONFIG_DIR/lib/paths.sh"
  cp "$REPO_DIR/lib/utils.sh" "$CONFIG_DIR/lib/utils.sh"
  log "Libraries installed to $CONFIG_DIR/lib/"
fi

# 9. Install ecc CLI
do_step "Installing ecc CLI..."
cp "$REPO_DIR/ecc" "$LOCAL_BIN/ecc"
chmod +x "$LOCAL_BIN/ecc"

log "ecc CLI installed to $LOCAL_BIN/ecc"

# 10. Copy scripts & templates
do_step "Installing management scripts..."
mkdir -p "$CONFIG_DIR/scripts"
for script in configure.sh uninstall.sh patch_opencode_ui.py; do
  if [ -f "$REPO_DIR/scripts/$script" ]; then
    cp "$REPO_DIR/scripts/$script" "$CONFIG_DIR/scripts/$script"
    chmod +x "$CONFIG_DIR/scripts/$script"
  fi
done

if [ -d "$REPO_DIR/templates" ]; then
  mkdir -p "$CONFIG_DIR/templates"
  cp -r "$REPO_DIR/templates/"* "$CONFIG_DIR/templates/" 2>/dev/null || true
fi

# 11. Customize OpenCode interface (Minecraft-style Swarm Edition logo & Web Cockpit footer)
if [ -f "$REPO_DIR/scripts/patch_opencode_ui.py" ]; then
  do_step "Customizing OpenCode interface (Minecraft-style Swarm Edition & Web Cockpit footer)..."
  mkdir -p "$CONFIG_DIR/bin"
  if python3 "$REPO_DIR/scripts/patch_opencode_ui.py" "$CONFIG_DIR/bin/opencode-swarm"; then
    log "Swarm Edition customized binary installed to $CONFIG_DIR/bin/opencode-swarm"
  else
    warn "Binary interface customization skipped (falling back to wrapper styling)"
  fi
fi

# Install OpenCode Swarm launcher wrapper
if [ -f "$REPO_DIR/templates/opencode-wrapper.sh" ]; then
  cp "$REPO_DIR/templates/opencode-wrapper.sh" "$LOCAL_BIN/opencode"
  cp "$REPO_DIR/templates/opencode-wrapper.sh" "$LOCAL_BIN/opencode-swarm"
  chmod +x "$LOCAL_BIN/opencode" "$LOCAL_BIN/opencode-swarm"
  log "OpenCode Swarm launcher installed to $LOCAL_BIN/opencode (alias: opencode-swarm)"
fi

# ──────────────── STEP: Post-install ────────────────

PATH_WARN=""
if ! in_path "$LOCAL_BIN"; then
  PATH_WARN="\n  • Add $LOCAL_BIN to your PATH:\n    export PATH=\"\$PATH:$LOCAL_BIN\""
  warn "$LOCAL_BIN not in PATH"
fi

SUMMARY="Installation complete!

  Config:  $CONFIG_DIR
  Agents:  6 specialized sub-agents installed
  MCP:     context-memory (FTS5) & team-collab active
  TUI:     tokyonight theme enabled
  Skills:  $SKILLS_DIR ($SKILL_COUNT skills)
  CLI:     $LOCAL_BIN/ecc
  User:    $USER_NAME $([[ -n "$GITHUB_HANDLE" ]] && echo "($GITHUB_HANDLE)")
$([[ -n "$PATH_WARN" ]] && echo "$PATH_WARN")

Next steps:
  • Run 'ecc doctor' to verify all components
  • Run 'ecc status' to inspect agents and MCP servers
  • Run 'ecc team' to view the development board
  • Launch opencode to enter the multi-agent swarm"

echo ""
msgbox "Summary" "$SUMMARY"

echo ""
echo -e "${C_CYAN}${C_BOLD}══════════════════════════════════════════════════════════${C_NC}"
echo -e "${C_CYAN}${C_BOLD}  🛡️  OpenCode Swarm Configuration Ready${C_NC}"
echo -e "${C_CYAN}${C_BOLD}══════════════════════════════════════════════════════════${C_NC}"
echo ""
echo -e "  ${C_BOLD}Specialized Agents:${C_NC}"
echo -e "    ${C_MAGENTA}• @orchestrator${C_NC}  — Team Lead & Architecture Planner"
echo -e "    ${C_BLUE}• @backend${C_NC}       — APIs, Databases & Server Logic"
echo -e "    ${C_RED}• @frontend${C_NC}      — UI/UX, Motion & Modern Web Design"
echo -e "    ${C_GREEN}• @git-flow${C_NC}      — Commits, Branching & Pull Requests"
echo -e "    ${C_YELLOW}• @qa-auditor${C_NC}   — Verification Loop & Security Audits"
echo -e "    ${C_CYAN}• @devops${C_NC}       — Docker, CI/CD & Deployments"
echo ""
echo -e "  ${C_BOLD}MCP Servers:${C_NC}"
echo -e "    ${C_GREEN}✓${C_NC} context-memory (SQLite FTS5 persistent memory)"
echo -e "    ${C_GREEN}✓${C_NC} team-collab    (Inter-agent Swarm Bus & task board)"
echo -e "    ${C_GREEN}✓${C_NC} swarm-sentinel (Autonomous Rules Guardian & Auditor)"
echo -e "    ${C_GREEN}✓${C_NC} swarm-tester   (Real-Time Continuous Testing & Probes)"
echo ""
echo -e "  ${C_BOLD}Available Commands in OpenCode:${C_NC}"
echo -e "    ${C_GREEN}/team${C_NC}      — View team status and task board"
echo -e "    ${C_GREEN}/memory${C_NC}    — Query and recall persistent context"
echo -e "    ${C_GREEN}/backend${C_NC}   — Delegate to backend specialist"
echo -e "    ${C_GREEN}/frontend${C_NC}  — Delegate to frontend specialist"
echo -e "    ${C_GREEN}/git-flow${C_NC}  — Delegate to git workflow manager"
echo -e "    ${C_GREEN}/qa${C_NC}        — Run verification loop & audits"
echo ""
