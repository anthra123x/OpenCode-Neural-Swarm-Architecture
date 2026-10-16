#!/usr/bin/env bash
set -euo pipefail

# uninstall.sh — Standalone uninstaller
# Called by: ecc uninstall
# Can run standalone: ./scripts/uninstall.sh

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

echo -e "${C_RED}${C_BOLD}══════════════════════════════════════════${C_NC}"
echo -e "${C_RED}${C_BOLD}  Uninstall opencode Configuration${C_NC}"
echo -e "${C_RED}${C_BOLD}══════════════════════════════════════════${C_NC}"
echo ""
echo "This will remove:"
echo "  • $CONFIG_DIR"
echo "  • $SKILLS_DIR"
echo "  • $HOME/.local/bin/ecc"
echo "  • $HOME/.local/bin/opencode-*"
echo ""
echo "Backups will be created before removal."
echo ""

if ! yesno "Confirm" "Proceed with uninstall?"; then
  echo "Cancelled."
  exit 0
fi

# Backup
echo ""
info "Creating backups..."
bk_config=""
bk_skills=""
if [ -d "$CONFIG_DIR" ]; then
  bk_config=$(backup_dir "$CONFIG_DIR")
  log "Config backed up: $bk_config"
fi
if [ -d "$SKILLS_DIR" ]; then
  bk_skills=$(backup_dir "$SKILLS_DIR")
  log "Skills backed up: $bk_skills"
fi

# Remove
echo ""
info "Removing files..."
rm -rf "$CONFIG_DIR" 2>/dev/null && log "Removed config: $CONFIG_DIR" || warn "Config not found"
rm -rf "$SKILLS_DIR" 2>/dev/null && log "Removed skills: $SKILLS_DIR" || warn "Skills not found"
rm -f "$HOME/.local/bin/ecc" "$HOME/.local/bin/opencode-swarm" "$HOME/.local/bin/opencode-"* 2>/dev/null && log "Removed CLI tools and wrappers from $HOME/.local/bin" || true

echo ""
echo -e "${C_GREEN}${C_BOLD}Uninstall complete${C_NC}"
echo ""
echo "Backups available at:"
[ -n "$bk_config" ] && echo "  $bk_config"
[ -n "$bk_skills" ] && echo "  $bk_skills"
echo ""
echo "To reinstall later:"
echo "  git clone https://github.com/anthra123x/opencode_config.git"
echo "  cd opencode_config && ./install.sh"
