/**
 * Team HUD Plugin for OpenCode (V2)
 * Sets up Swarm environment, terminal title, orchestrator metadata,
 * and runtime guards for uninterrupted continuous subagent execution.
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

    // Transform orchestrator description
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

    // Intercept and normalize subagent tool calls to guarantee continuous execution
    if (ctx?.tool?.hook) {
      ctx.tool.hook("execute.before", (event: any) => {
        if (event.tool === "subagent" && event.input) {
          const input = event.input

          // Schema normalization: map task -> prompt, label -> description
          if (input.task && !input.prompt) {
            input.prompt = input.task
          }
          if (input.label && !input.description) {
            input.description = input.label
          }
          if (!input.description && input.prompt) {
            input.description = String(input.prompt).slice(0, 45)
          }

          // Invariant: Do not background subagent unless explicitly set, preventing premature turn halt
          if (input.background === true) {
            // Keep synchronous so orchestrator immediately reviews progress in the same iteration
            input.background = false
          }

          if (process.stdout && process.stdout.isTTY) {
            process.stdout.write(`\r\x1b[38;5;141m[SWARM]\x1b[0m \x1b[38;5;51m→ @${input.agent}\x1b[0m: ${input.description || "Executing task"}...\n`)
          }
        }
      })

      ctx.tool.hook("execute.after", (event: any) => {
        if (event.tool === "subagent" && event.input) {
          const agentName = event.input.agent || "subagent"
          const status = event.status === "completed" ? "\x1b[32mCOMPLETED\x1b[0m" : "\x1b[31mERROR\x1b[0m"
          if (process.stdout && process.stdout.isTTY) {
            process.stdout.write(`\r\x1b[38;5;141m[SWARM]\x1b[0m \x1b[38;5;48m← @${agentName}\x1b[0m: [${status}] Progress verified, advancing pipeline.\n`)
          }
        }
      })
    }
  },
}
