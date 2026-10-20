/**
 * OpenCode Brain Graph Server Plugin
 * Exposes neural graph metadata, query capabilities, and MCP lifecycle coordination.
 */
import path from "node:path"
import os from "node:os"

export default {
  id: "opencode-brain-graph",
  async setup(ctx: any) {
    const dbPath = path.join(os.homedir(), ".opencode", "brain", "brain.db")
    // Store path in ctx if needed
    if (ctx?.storage?.memory) {
      ctx.storage.memory("brain-db-path", dbPath)
    }
  },
}
