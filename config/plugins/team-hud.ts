/**
 * Team HUD Plugin for OpenCode (V2)
 * Sets up Swarm environment, terminal title, and orchestrator links.
 */
import { execFileSync } from "node:child_process"
import { existsSync } from "node:fs"
import os from "node:os"
import path from "node:path"

export default {
  id: "opencode-swarm-hud",
  async setup(ctx: any) {
    const xdgConfig = process.env.XDG_CONFIG_HOME?.trim() || path.join(os.homedir(), ".config")
    const opencodeHome = path.join(xdgConfig, "opencode")
    const swarmHome = path.join(opencodeHome, "swarm")
    let webServer = path.join(opencodeHome, "web", "server.py")
    if (!existsSync(webServer)) {
      webServer = path.join(swarmHome, "web", "server.py")
    }

    const location = (ctx?.location || {}) as any
    const projectDir = location.directory || location.project?.canonical || process.cwd()
    const projectName = path.basename(projectDir) || "workspace"
    let webPort = process.env.OPENCODE_WEB_PORT || "4040"

    // Set terminal title
    if (process.stdout && process.stdout.isTTY) {
      process.stdout.write(`\x1b]0;OPENCODE [SWARM] — ${projectName}\x07`)
    }

    if (existsSync(webServer)) {
      try {
        const output = execFileSync(
          "python3",
          [webServer, "--ensure", "--dir", projectDir, "--project", projectName],
          {
            encoding: "utf8",
            timeout: 3000,
            stdio: ["ignore", "pipe", "ignore"],
            env: process.env,
          },
        ).trim()
        if (/^\d+$/.test(output)) webPort = output
      } catch {
        // Fallback to default
      }
    }

    const baseUrl = `http://localhost:${webPort}`
    const cockpitUrl = `http://localhost:${webPort}/?project=${encodeURIComponent(projectName)}`
    process.env.OPENCODE_WEB_PORT = webPort
    process.env.OPENCODE_WEB_URL = baseUrl

    if (ctx?.agent?.transform) {
      await ctx.agent.transform((editor: any) => {
        const orchestrator = editor.get("orchestrator")
        if (orchestrator) {
          editor.update("orchestrator", (agent: any) => {
            agent.description = `[Swarm Lead] Orchestrator. Cockpit: ${cockpitUrl} | GetBrain: ${cockpitUrl}#brain | Live Tester: ${cockpitUrl}#tester`
          })
        }
      })
    }
  },
}
