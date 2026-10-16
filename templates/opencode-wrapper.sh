#!/usr/bin/env bash
# opencode — OpenCode Swarm Edition Launcher
# Wraps vanilla opencode with Swarm environment, MCP routing, and terminal branding

# Prefer customized Swarm Edition binary with Minecraft-style branding
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

# Set terminal window title with Swarm branding
if [[ -t 1 ]]; then
  echo -ne "\033]0;OPENCODE [SWARM] — ${PROJECT_NAME}\007"
fi

# Display distinctive Swarm identity banner on interactive startup
if [[ -t 1 ]] && [ "$#" -eq 0 ]; then
  echo -e "\033[1;38;5;141mOpenCode ── \033[1;38;5;51m[ SWARM EDITION v2.0 ]\033[0m"
  echo -e "\033[38;5;220m  -> Alias: \033[1;37mopencode-swarm\033[0m \033[2m(Multi-Agent Autonomous Swarm & Live Verification)\033[0m"
  echo -e "\033[38;5;102m  -> Workspace: \033[38;5;48m${PROJECT_NAME}\033[0m"
  echo ""
  sleep 0.1
fi

# Launch OpenCode (all agents, MCPs, and theme loaded from ~/.config/opencode)
exec "$REAL_OPENCODE" "$@"
