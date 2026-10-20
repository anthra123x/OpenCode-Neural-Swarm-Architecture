---
description: Query, traverse, and visualize the brain knowledge graph. Search nodes, explore connections, and audit memory health.
---

Execute brain graph operations based on the arguments:
- No arguments or "context": Call `get_brain_context()` to display the current project's brain state.
- "search <query>" or "recall <query>": Call `recall_graph(query=...)` to search the brain and expand neighbor connections.
- "traverse <node_id>": Call `traverse(start_node=..., depth=2)` to explore a node's graph neighborhood.
- "list" or "nodes": Call `list_entities()` to show all nodes in the project.
- "list <type>": Call `list_entities(node_type=...)` to filter by node type (decision, component, technology, etc).
- "audit" or "decay": Call `decay_audit(dry_run=true)` to review dormant nodes and confidence levels.
- "prune": Call `decay_audit(dry_run=false, prune_threshold=0.15)` to actually remove dormant nodes.
- "learn <lesson>": Call `record_learning(lesson=...)` to persist a new insight.
