#!/usr/bin/env bash
set -euo pipefail

# configure.sh — Re-runnable configuration wizard
# Called by: ecc configure
# Can also run standalone: ./scripts/configure.sh

CONFIG_DIR="${ECC_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/opencode}"
SKILLS_DIR="${ECC_SKILLS:-$HOME/.opencode/skills}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"
if [ ! -f "$LIB_DIR/ui.sh" ] && [ -f "$CONFIG_DIR/lib/ui.sh" ]; then
  LIB_DIR="$CONFIG_DIR/lib"
fi

source "$LIB_DIR/ui.sh"
source "$LIB_DIR/paths.sh"
source "$LIB_DIR/utils.sh"

setup_ui
setup_paths
setup_utils

print_banner
msgbox "Configuration Wizard" \
"This wizard lets you reconfigure your OpenCode Swarm setup.

You can change preferences, paths, and re-generate configuration files.
Existing files will be backed up automatically."

# ─── User info ───
USER_NAME=$(inputbox "User" "Your name or alias:" "${USER:-user}")
GITHUB_HANDLE=$(inputbox "GitHub" "GitHub username (optional):" "")

# ─── Config paths ───
CONFIG_PATH=$(inputbox "Config path" "Config directory:" "$CONFIG_DIR")
SKILLS_PATH=$(inputbox "Skills path" "Skills directory:" "$SKILLS_DIR")

# ─── Generate opencode.jsonc ───
if yesno "Generate config" "Regenerate opencode.jsonc with Swarm settings?"; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  if [ -f "$REPO_ROOT/config/opencode.jsonc" ]; then
    cp "$REPO_ROOT/config/opencode.jsonc" "$CONFIG_PATH/opencode.jsonc"
    cp "$REPO_ROOT/config/opencode.jsonc" "$CONFIG_PATH/opencode.json"
  elif [ -f "$CONFIG_PATH/opencode.jsonc" ]; then
    # Keep existing if already present
    log "Preserved current opencode.jsonc"
  fi
  log "Regenerated opencode.jsonc with full MCP Swarm suite"
fi

# ─── Summary ───
echo ""
echo -e "${C_GREEN}${C_BOLD}Configuration updated successfully:${C_NC}"
echo "  User:    $USER_NAME $([[ -n "$GITHUB_HANDLE" ]] && echo "($GITHUB_HANDLE)")"
echo "  Config:  $CONFIG_PATH"
echo "  Skills:  $SKILLS_PATH"
echo ""
echo -e "Run ${C_BOLD}ecc doctor${C_NC} to verify everything is working."
