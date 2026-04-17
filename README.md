# AI Knowledge Graph

> Transform any directory of source code, documentation, research papers, and images into a searchable knowledge graph, with community detection, a transparent audit trail, and three deliverables: an interactive HTML view, GraphRAG-compatible JSON, and a human-readable `REPORT.md`.

## Table of contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
  - [Build a graph](#build-a-graph)
  - [Explore the graph](#explore-the-graph)
  - [Keep the graph fresh](#keep-the-graph-fresh)
- [AI assistant integration](#ai-assistant-integration)
- [Command reference](#command-reference)
- [Development](#development)

---

## How it works

The pipeline runs in four stages:

1. **Detect**: walk the target directory and identify every supported source file.
2. **Extract**: parse each file with tree-sitter, emitting nodes for classes / functions / modules and edges for calls / imports.
3. **Build**: assemble a NetworkX graph, run Louvain community detection, score cohesion, and flag god nodes plus surprising cross-community edges.
4. **Export**: write `graph.json` (GraphRAG payload) and `REPORT.md` (audit write-up) under `<target>/aikgraph-out/`.

The AST-only `update` command covers this flow. For a **semantic tier** (cross-file conceptual edges, docs/README comprehension, image/PDF extraction, rationale edges), run the full `/aikgraph` flow from inside an AI coding assistant (see [AI assistant integration](#ai-assistant-integration)).

---

## Installation

From the repo root:

```bash
cd ~/source/aikgraph
pip install -e . --no-deps
```

Verify the CLI is on your `PATH`:

```bash
aikgraph --help
```

You should see `Usage: aikgraph <command>` followed by the command list.

---

## Usage

Examples target `~/projects/my-project` (any source folder works). Substitute your own path.

### Build a graph

```bash
aikgraph update ~/projects/my-project              # graph.json + REPORT.md
aikgraph update ~/projects/my-project --obsidian   # also export an Obsidian vault
```

Outputs land in `<target>/aikgraph-out/`:

| File / Folder | Purpose |
|---------------|---------|
| `graph.json` | Full graph payload (GraphRAG-compatible) |
| `REPORT.md` | Audit write-up covering god nodes, communities, and follow-up questions |
| `obsidian/` *(with `--obsidian`)* | Obsidian vault: one `.md` note per node with wikilinks, community overview notes, `graph.canvas`, and per-community colors in `.obsidian/graph.json` |

Expected final line:

```
[aikgraph watch] Rebuilt: N nodes, M edges, K communities
```

### Explore the graph

Export `GRAPH` once, then query:

```bash
GRAPH=~/projects/my-project/aikgraph-out/graph.json

aikgraph explain "AuthModule" --graph $GRAPH
aikgraph path "LoginForm" "UserRepository" --graph $GRAPH
aikgraph query "how does extraction talk to core" --graph $GRAPH
aikgraph query "auth flow" --dfs --budget 3000 --graph $GRAPH
```

Or `cd` into the target folder and drop `--graph`. It defaults to `./aikgraph-out/graph.json`.

| Command | Purpose |
|---------|---------|
| `aikgraph explain "<node>"` | Plain-language description of a node plus its neighbors |
| `aikgraph path "<a>" "<b>"` | Shortest path between two concepts |
| `aikgraph query "<q>"` | BFS traversal for wide context (add `--dfs` to trace a chain) |
| `aikgraph query "<q>" --budget N` | Cap answer at N tokens (default 2000) |

### Keep the graph fresh

Pick whichever fits your workflow:

| Approach | Command | When to use |
|----------|---------|-------------|
| **Manual** | `aikgraph update <path>` | One-off rebuilds after significant edits |
| **Git hook** | `aikgraph hook install` (in target repo) | Auto-rebuild on every commit / checkout |
| **File watcher** | `aikgraph watch <path>` (needs `watchdog`) | Live rebuild on save, 3s debounce |

Manage hooks with `aikgraph hook status` and `aikgraph hook uninstall`. The watcher runs in the foreground; `Ctrl+C` to stop.

---

## AI assistant integration

The AST-only `update` command is the LLM-free subset of a larger pipeline. The **semantic** tier (cross-file conceptual edges, docs/README comprehension, image/PDF extraction, rationale edges) runs as `/aikgraph` inside an AI coding assistant with the skill installed.

### Kiro

```bash
cd ~/projects/my-project
aikgraph kiro install
```

Installs:

- `~/.kiro/skills/aikgraph/SKILL.md` (global): skill that teaches Kiro when and how to invoke `aikgraph query "..."`, `aikgraph path "A" "B"`, `aikgraph explain "X"`, and the rest of the CLI. Installed once; picked up by Kiro across every project.
- `./.kiro/steering/aikgraph.md` (project-local): always-on steering that points Kiro at this project's `REPORT.md` before answering architecture questions
- `./.kiro/aikgraph-out/` (project-local): output directory where `aikgraph update` writes `graph.json` and `REPORT.md`

Run `aikgraph update` from the shell to build/refresh the graph.

### Claude Code

```bash
cd ~/projects/my-project
aikgraph claude install
```

Installs:

- `CLAUDE.md` section that points Claude Code at `REPORT.md` + graph.json
- PreToolUse hook that runs `aikgraph update` when code changes
- `.claude/aikgraph-out/`: project-local output directory

### GitHub Copilot CLI

```bash
cd ~/projects/my-project
aikgraph copilot install
```

Prepares `.copilot/aikgraph-out/` as the output directory. Run `aikgraph update` to populate it.

### Uninstalling

```bash
aikgraph <platform> uninstall   # platform: claude | copilot | kiro
```

---

## Command reference

### Graph construction (no LLM required)

```
aikgraph update <path>                   # AST extract + rebuild graph
aikgraph update <path> --obsidian        # also emit an Obsidian vault + graph.canvas
aikgraph cluster-only <path>             # re-cluster an existing graph.json
aikgraph watch <path>                    # auto-rebuild on save (needs watchdog)
```

### Open the Obsidian vault

After running `aikgraph update <path> --obsidian`, open `<path>/aikgraph-out/obsidian/` as a vault in Obsidian. You get:

- One note per graph node, with wikilinks (`[[neighbor]]`) to every connected node.
- One `_COMMUNITY_<name>.md` overview per community, listing members, cohesion, bridge nodes, and cross-community edges.
- `graph.canvas` for a structured community-grouped layout (open as an Obsidian Canvas).
- `.obsidian/graph.json` with per-community colors wired into Obsidian's built-in graph view.

### Content ingestion

```
aikgraph add <url>                       # fetch URL into ./raw, update the graph
```

### Platform installers

```
aikgraph install --platform claude|copilot|kiro
aikgraph claude   install|uninstall      # per-project CLAUDE.md + PreToolUse hook
aikgraph copilot  install|uninstall      # Copilot CLI skill
aikgraph kiro     install|uninstall      # Kiro skill folder + always-on steering
aikgraph hook     install|uninstall|status   # git post-commit / post-checkout hooks
```

---

## Development

Rebuild distributables:

```bash
python3 -m build            # wheel + sdist in dist/
```

Force-reinstall after `pyproject.toml` edits:

```bash
pip install -e . --no-deps --force-reinstall
```

Run without the console script:

```bash
python3 -m aikgraph <command>
```
