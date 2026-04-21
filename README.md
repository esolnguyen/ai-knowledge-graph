# AI Knowledge Graph

> Transform any directory of source code, documentation, research papers, and images into a searchable knowledge graph, with community detection, a transparent audit trail, and three deliverables: an interactive HTML view, GraphRAG-compatible JSON, and a human-readable `REPORT.md`.

## Table of contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Usage](#usage)
  - [Build a graph](#build-a-graph)
  - [Explore the graph](#explore-the-graph)
  - [Keep the graph fresh](#keep-the-graph-fresh)
  - [Sync Azure DevOps](#sync-azure-devops)
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

## Quickstart

End-to-end: build a graph over one or more repos, wire up Kiro, and let Kiro read the graph.

### 1. Collect the code you want graphed into one folder

Pick a workspace folder (anywhere on disk). Clone every repo you want in the graph underneath it:

```bash
mkdir -p ~/projects/my-workspace
cd ~/projects/my-workspace

git clone git@github.com:your-org/service-a.git
git clone git@github.com:your-org/service-b.git
git clone git@github.com:your-org/shared-lib.git
```

The graph treats the workspace as one unit — cross-repo calls and imports become real edges.

### 2. Build the graph inside that folder

```bash
cd ~/projects/my-workspace
aikgraph update .
```

Output lands **inside the workspace**, not in your home directory:

```
~/projects/my-workspace/
├── service-a/
├── service-b/
├── shared-lib/
└── aikgraph-out/            <-- created by `aikgraph update`
    ├── graph.json
    ├── REPORT.md
    ├── graph.html           (open in browser)
    ├── graph.svg
    └── obsidian/            (open as an Obsidian vault)
```

> **Heads up:** `aikgraph update` never writes to `~/.kiro/` or any home-directory location. Outputs are always project-local.

### 3. Install the Kiro skill

```bash
cd ~/projects/my-workspace
aikgraph kiro install
```

This does two things:

- Drops the skill at `~/.kiro/skills/aikgraph/SKILL.md` — **global**, so Kiro picks it up across every project.
- Writes `./.kiro/steering/aikgraph.md` and prepares `./.kiro/aikgraph-out/` — **project-local**. After this, `aikgraph update` will write the graph under `./.kiro/aikgraph-out/` instead of `./aikgraph-out/` (the marker file redirects the output path).

Re-run the update so outputs land in the Kiro-aware location:

```bash
aikgraph update .
ls .kiro/aikgraph-out/     # graph.json, REPORT.md, graph.html, ...
```

### 4. Open Kiro and ask about the code

Open the workspace in Kiro. The always-on steering file tells Kiro to read `./.kiro/aikgraph-out/REPORT.md` before answering architecture questions, and the skill teaches it to run `aikgraph query`, `aikgraph path`, and `aikgraph explain` for targeted lookups. Ask things like:

- "Walk me through how service-a calls shared-lib."
- "What are the god nodes in this workspace?"
- "Shortest path from `LoginForm` to `UserRepository`."

When code changes, re-run `aikgraph update .` (or set up `aikgraph watch .` / `aikgraph hook install` — see [Keep the graph fresh](#keep-the-graph-fresh)).

---

## Usage

Examples target `~/projects/my-project` (any source folder works). Substitute your own path.

### Build a graph

```bash
aikgraph update ~/projects/my-project                            # JSON + REPORT only (default)
aikgraph update ~/projects/my-project --html --svg --obsidian    # generate all extra outputs
aikgraph update ~/projects/my-project --html                     # add interactive HTML only
```

Outputs land in `<target>/aikgraph-out/`:

| File / Folder | Purpose | Opt in |
|---------------|---------|--------|
| `graph.json` | Full graph payload (GraphRAG-compatible) | always |
| `REPORT.md` | Audit write-up covering god nodes, communities, and follow-up questions | always |
| `graph.html` | Interactive vis.js visualization (dark theme, search, community legend) | `--html` |
| `graph.svg` | Static matplotlib render (needs `matplotlib`) | `--svg` |
| `obsidian/` | Obsidian vault: one `.md` note per node with wikilinks, community overview notes, `graph.canvas`, and per-community colors in `.obsidian/graph.json` | `--obsidian` |

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

### Sync Azure DevOps

Pull an Azure DevOps project's work items and repos into the same graph as your code. Work items (PBIs, bugs, epics) become document nodes; repos become document nodes and their default-branch checkouts feed the AST extractor, so cross-links between tickets and real code symbols show up as edges.

Set credentials once, then pass `--project` to `aikgraph update`:

```bash
export AZURE_DEVOPS_ORG="your-org"
export AZURE_DEVOPS_PAT="..."           # PAT with Work Items (Read) + Code (Read)

aikgraph update ~/projects/my-workspace --project MyProject
```

What happens:

1. Work items and repos are fetched into `<target>/raw/azure/` as markdown with YAML frontmatter.
2. Each repo's default branch is shallow-cloned under `<target>/raw/azure/repos/<name>/`.
3. The normal AST extractor runs over the cloned code, and the Azure extractor emits `parent_of` / `related_to` / `touches_repo` edges from work-item relations plus `contains` edges from repos to code symbols.
4. The built graph is written under `~/.kiro/aikgraph-out/<project>/` (override with `AIKGRAPH_OUT=<path>`) so it lives globally, not inside the scanned directory.

Incremental state is stored in `<target>/raw/azure/.azure_sync_state.json` — subsequent runs only fetch work items changed since the last cursor and only re-fetch repos whose HEAD moved.

| Flag | Purpose |
|------|---------|
| `--project <name>` | Azure DevOps project to sync (required to trigger the sync) |
| `--since YYYY-MM-DD` | Cap the first-run work-item scan window (default: 365 days back) |
| `--full` | Ignore saved state; force a full rescan and re-clone |
| `--no-clone` | Skip the git clone step — fetch work items + repo metadata only |
| `--repos a,b,c` | Clone only this subset of repos (comma-separated names) |

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
aikgraph update <path>                            # AST extract + rebuild (graph.json + REPORT.md only)
aikgraph update <path> --html --svg --obsidian    # opt into extra outputs
aikgraph update <path> --project <name>           # also sync Azure DevOps (work items + repos)
   [--since YYYY-MM-DD] [--full] [--no-clone] [--repos a,b,c]
aikgraph cluster-only <path>             # re-cluster an existing graph.json
aikgraph watch <path>                    # auto-rebuild on save (needs watchdog)
```

Azure DevOps sync requires `AZURE_DEVOPS_ORG` and `AZURE_DEVOPS_PAT` in the environment. See [Sync Azure DevOps](#sync-azure-devops) for details.

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
