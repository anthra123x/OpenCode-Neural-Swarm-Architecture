#!/usr/bin/env bash
# opencode — OpenCode Swarm Edition Launcher
# Wraps vanilla opencode with per-project Swarm Web Cockpit sessions and terminal branding

# Prefer customized Swarm Edition binary with Minecraft-style branding & session web URL
SWARM_BIN="$HOME/.config/opencode/bin/opencode-swarm"
if [ -x "$SWARM_BIN" ]; then
  REAL_OPENCODE="$SWARM_BIN"
elif [ -x "/usr/bin/opencode" ]; then
  REAL_OPENCODE="/usr/bin/opencode"
else
  REAL_OPENCODE=$(type -ap opencode | grep -v "$HOME/.local/bin/opencode" | head -n 1)
fi

# Detect project workspace directory and project name
PROJECT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

# Locate Swarm Web server script
SERVER_SCRIPT="$HOME/.config/opencode/web/server.py"
if [ ! -f "$SERVER_SCRIPT" ]; then
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [ -f "$REPO_DIR/web/server.py" ]; then
    SERVER_SCRIPT="$REPO_DIR/web/server.py"
  fi
fi

# Ensure dedicated web session & GetBrain monitoring server for this project
SERVER_PORT="4040"
if [ -f "$SERVER_SCRIPT" ]; then
  PORT_DETECTED=$(python3 "$SERVER_SCRIPT" --ensure --dir "$PROJECT_DIR" --project "$PROJECT_NAME" 2>/dev/null || echo "4040")
  if [ -n "$PORT_DETECTED" ]; then
    SERVER_PORT="$PORT_DETECTED"
    export OPENCODE_WEB_PORT="$SERVER_PORT"
    export OPENCODE_WEB_URL="http://localhost:$SERVER_PORT"
  fi
fi

# Intercept quick CLI command: 'opencode web'
if [ "$1" = "web" ] || [ "$1" = "--web" ]; then
  echo -e "\033[1;38;5;141mOpenCode ── \033[1;38;5;51m[ TELEMETRIA WEB ]\033[0m"
  echo -e "\033[38;5;220m  -> Workspace: \033[1;37m${PROJECT_NAME}\033[0m"
  echo -e "\033[38;5;39m  -> Sesion Web: \033[1;4;38;5;75mhttp://localhost:${SERVER_PORT}\033[0m"
  echo ""
  xdg-open "http://localhost:${SERVER_PORT}/?project=${PROJECT_NAME}" 2>/dev/null || sensible-browser "http://localhost:${SERVER_PORT}/?project=${PROJECT_NAME}" 2>/dev/null || true
  exit 0
fi

# Set terminal window title with Swarm branding
if [[ -t 1 ]]; then
  echo -ne "\033]0;OPENCODE [SWARM] — ${PROJECT_NAME}\007"
fi

# Display distinctive Swarm identity banner on interactive startup
if [[ -t 1 ]] && [ "$#" -eq 0 ]; then
  echo -e "\033[1;38;5;141mOpenCode ── \033[1;38;5;51m[ SWARM EDITION v2.0 ]\033[0m"
  echo -e "\033[38;5;220m  -> Alias: \033[1;37mopencode-swarm\033[0m \033[2m(Multi-Agent Autonomous Swarm & Live Verification)\033[0m"
  echo -e "\033[38;5;102m  -> Workspace: \033[38;5;48m${PROJECT_NAME}\033[0m"
  echo -e "\033[38;5;39m  -> Web Telemetria: \033[1;4;38;5;75mhttp://localhost:${SERVER_PORT}\033[0m"
  echo ""
  sleep 0.2
fi

# Launch OpenCode (all agents, MCPs, and theme loaded from ~/.config/opencode)
exec "$REAL_OPENCODE" "$@"
