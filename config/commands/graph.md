---
description: Query, traverse, and inspect the brain knowledge graph. Explore node relationships, decisions, and dependencies.
---

Execute brain graph operations based on the arguments:
- No arguments or "web" or "view": Display visual graph metrics and provide the direct interactive Obsidian graph link: `http://localhost:4848` (launched via `ecc graph`).
- "context": Call `get_brain_context()` to display the current project's brain state.
- "search <query>" or "recall <query>": Call `recall_graph(query=..., expand_neighbors=True)` to search the brain and expand neighbor connections.
- "traverse <node_id>": Call `traverse(start_node=..., depth=2)` to explore a node's graph neighborhood.
- "list" or "nodes": Call `list_entities()` to show all nodes in the project.
- "list <type>": Call `list_entities(node_type=...)` to filter by node type (decision, component, endpoint, etc).
- "audit" or "decay": Call `decay_audit(dry_run=True)` to review dormant nodes and confidence levels.
- "prune": Call `decay_audit(dry_run=False, prune_threshold=0.15)` to remove dormant nodes.
- "learn <lesson>": Call `record_learning(lesson=...)` to persist a new insight.
