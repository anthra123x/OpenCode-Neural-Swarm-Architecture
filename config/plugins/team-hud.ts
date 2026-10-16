/**
 * Team HUD Plugin for OpenCode (V2)
 * Sets up Swarm environment, terminal title, and orchestrator metadata.
 */
import path from "node:path"

export default {
  id: "opencode-swarm-hud",
  async setup(ctx: any) {
    const location = (ctx?.location || {}) as any
    const projectDir = location.directory || location.project?.canonical || process.cwd()
    const projectName = path.basename(projectDir) || "workspace"

    // Set terminal title
    if (process.stdout && process.stdout.isTTY) {
      process.stdout.write(`\x1b]0;OPENCODE [SWARM] — ${projectName}\x07`)
    }

    if (ctx?.agent?.transform) {
      await ctx.agent.transform((editor: any) => {
        const orchestrator = editor.get("orchestrator")
        if (orchestrator) {
          editor.update("orchestrator", (agent: any) => {
            agent.description = `[Swarm Lead] Orchestrator & System Designer. Coordinates autonomous subagents and MCP workflows.`
          })
        }
      })
    }
  },
}
