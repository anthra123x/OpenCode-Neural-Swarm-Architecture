/**
 * OpenCode Brain Graph TUI Plugin (Native TypeScript & SolidJS)
 *
 * Injects a neural knowledge graph HUD into OpenCode's sidebar.content slot
 * directly beneath the MCP section, rendering real-time nodes, synapses,
 * and the highlighted agent cluster matching Image 2.
 */
import { createSignal, onMount, onCleanup, Show } from "solid-js"
import { Database } from "bun:sqlite"
import path from "node:path"
import os from "node:os"

interface BrainStats {
  nodes: number
  edges: number
  tech: number
  learnings: number
  arch: number
  recentCluster: string
}

function queryBrainStats(): BrainStats {
  const dbPath = path.join(os.homedir(), ".opencode", "brain", "brain.db")
  try {
    const db = new Database(dbPath, { readonly: true })
    const nodeRow = db.query("SELECT COUNT(*) as count FROM nodes").get() as any
    const edgeRow = db.query("SELECT COUNT(*) as count FROM edges").get() as any
    const typeRows = db.query("SELECT node_type, COUNT(*) as count FROM nodes GROUP BY node_type").all() as any[]
    
    let tech = 0
    let learnings = 0
    let arch = 0
    for (const r of typeRows) {
      if (r.node_type === "technology") tech = r.count
      else if (r.node_type === "learning") learnings = r.count
      else if (r.node_type === "architecture" || r.node_type === "checkpoint") arch += r.count
    }

    db.close()
    return {
      nodes: nodeRow?.count || 0,
      edges: edgeRow?.count || 0,
      tech,
      learnings,
      arch,
      recentCluster: "My agent",
    }
  } catch {
    return {
      nodes: 0,
      edges: 0,
      tech: 0,
      learnings: 0,
      arch: 0,
      recentCluster: "My agent",
    }
  }
}

function BrainGraphWidget(props: { context: any; sessionID?: string }) {
  const ctx = props.context
  const [open, setOpen] = createSignal(true)
  const [stats, setStats] = createSignal<BrainStats>(queryBrainStats())

  // Reactive periodic refresh of the neural topology
  let timer: any
  onMount(() => {
    setStats(queryBrainStats())
    timer = setInterval(() => {
      setStats(queryBrainStats())
    }, 4000)
  })

  onCleanup(() => {
    if (timer) clearInterval(timer)
  })

  const textColor = () => ctx?.theme?.text?.base || "#e2e8f0"
  const mutedColor = () => ctx?.theme?.text?.muted || "#64748b"

  const openVisualizer = () => {
    try {
      Bun.spawn(["xdg-open", "http://localhost:4848"], {
        stdout: "ignore",
        stderr: "ignore",
      })
    } catch {
      // Fallback if headless
    }
    if (ctx?.ui?.toast?.show) {
      ctx.ui.toast.show({
        variant: "info",
        title: "Neural Graph",
        message: "Visualizer open at http://localhost:4848",
      })
    }
  }

  return (
    <box flexDirection="column" gap={0} minWidth={0} marginTop={1}>
      {/* Clickable Header Accordion */}
      <box
        flexDirection="row"
        gap={1}
        minWidth={0}
        onMouseDown={() => setOpen(!open())}
      >
        <text fg={textColor()}>{open() ? "▼" : "▶"}</text>
        <text wrapMode="none" truncate={true}>
          <b fg={textColor()}>Brain Graph</b>
          <span style={{ fg: mutedColor() }}>
            {" "}({stats().nodes} nodes · {stats().edges} syn)
          </span>
        </text>
      </box>

      {/* Expanded Neural Network Topology */}
      <Show when={open()}>
        <box flexDirection="column" gap={0} paddingLeft={1} paddingTop={0}>
          {/* Micro-canvas ASCII Force-directed cluster */}
          <box flexDirection="column" gap={0}>
            <text fg="#64748b" wrapMode="none">
              {"   "}╭── ● tech ({stats().tech})
            </text>
            <box flexDirection="row" gap={1}>
              <text fg="#a855f7" wrapMode="none">
                ●──🟣 [My Agent]──●
              </text>
              <text fg="#38bdf8" wrapMode="none">
                learn ({stats().learnings})
              </text>
            </box>
            <text fg="#64748b" wrapMode="none">
              {"   "}╰── ● arch ({stats().arch})
            </text>
          </box>

          {/* Active Agent Cluster & Metrics */}
          <box flexDirection="column" gap={0} marginTop={1}>
            <box flexDirection="row" gap={1}>
              <text fg="#a855f7">●</text>
              <text fg={textColor()} wrapMode="none">
                Cluster: <b fg="#c084fc">{stats().recentCluster}</b>
              </text>
              <text fg="#10b981" wrapMode="none">
                [Active]
              </text>
            </box>
            <box flexDirection="row" gap={1}>
              <text fg="#64748b">·</text>
              <text fg={mutedColor()} wrapMode="none">
                Synapses: <b fg={textColor()}>{stats().edges}</b> live connections
              </text>
            </box>
            <box flexDirection="row" gap={1}>
              <text fg="#64748b">·</text>
              <text fg={mutedColor()} wrapMode="none">
                Lead Agent: <b fg="#818cf8">@orchestrator</b>
              </text>
            </box>
          </box>

          {/* Action trigger for full interactive D3 web visualizer */}
          <box
            flexDirection="row"
            gap={1}
            marginTop={1}
            onMouseUp={openVisualizer}
          >
            <text fg="#c084fc" wrapMode="none">
              [ 🌐 Open 2D D3 Graph (:4848) ]
            </text>
          </box>
        </box>
      </Show>
    </box>
  )
}

export default {
  id: "opencode-brain-graph",
  setup(ctx: any) {
    if (ctx?.ui?.slot) {
      ctx.ui.slot({
        append: "sidebar.content",
        render: (props: any) => (
          <BrainGraphWidget context={ctx} sessionID={props?.sessionID} />
        ),
      })
    }
  },
}
