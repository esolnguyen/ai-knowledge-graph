---
name: aikgraph
description: >
  Build a knowledge graph from any folder (code, docs, papers, images, video).
  Outputs: interactive HTML, GraphRAG-ready JSON, REPORT.md.
  Activate when asked to analyze a codebase, map dependencies, or build a knowledge graph.
---

# /aikgraph

Parse the invocation, match it to a file below, read that file, and follow it. Read only the one you need.

| Pattern | File |
|---------|------|
| `/aikgraph [<path>] [--mode deep] [--svg] [--graphml] [--neo4j] [--neo4j-push URI] [--mcp] [--no-viz] [--obsidian]` | `pipeline.md` |
| `--update` | `update.md` |
| `--cluster-only` | `cluster-only.md` |
| `--watch` | `watch.md` |
| `query "<question>" [--dfs] [--budget N]` | `query.md` |
| `path "<a>" "<b>"` | `path.md` |
| `explain "<node>"` | `explain.md` |
| `add <url> [--author NAME] [--contributor NAME]` | `add.md` |
| `hook install/uninstall/status` | `hooks.md` |
| `help` | Print the table above with one-line descriptions and stop. |

## Rules (all modes)do it 

- Never invent an edge. If unsure, tag it AMBIGUOUS.
- Never skip the corpus-size warning.
- Always show token cost in the report.
- Show cohesion as a raw number, never as a symbol.
- Warn before HTML viz on graphs with > 5 000 nodes.
