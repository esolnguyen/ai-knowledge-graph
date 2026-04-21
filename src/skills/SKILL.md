---
name: aikgraph
description: Query prebuilt knowledge graphs of Azure DevOps projects and local codebases via the `aikgraph` CLI. Graphs live under `~/.kiro/aikgraph-out/<project>/` (global, shared across repos) or `<repo>/.kiro/aikgraph-out/` (project-local). Pick the right graph before answering any architecture, dependency, or "where does X live" question.
---

# aikgraph

Run the `aikgraph` CLI through the shell tool. Do not reimplement the pipeline inline.

## Where graphs live (read before querying)

Graphs are stored in **one** of two locations. Check both before giving up:

| Location | When it's used |
|---|---|
| `~/.kiro/aikgraph-out/<project>/graph.json` | Built with `aikgraph update --project <name>` — one folder per Azure DevOps project, shared across repos (the **default** for Azure DevOps graphs). |
| `<repo>/.kiro/aikgraph-out/graph.json` | Built with plain `aikgraph update <path>` from inside a repo. |

Any explicit `$AIKGRAPH_OUT` env var overrides both.

## Step 0 — discover which graphs exist

Always run this first when the user asks a structural question, before running `find`/`grep` or reading source:

```bash
ls ~/.kiro/aikgraph-out/ 2>/dev/null
ls ./.kiro/aikgraph-out/ 2>/dev/null
```

Interpret the results:

- Subfolders under `~/.kiro/aikgraph-out/` (e.g. `X-Platform-Testing/`, `Billing/`) → each is an Azure DevOps project graph. Pick one per the rules below.
- `graph.json` directly inside `./.kiro/aikgraph-out/` → a single project-local graph.
- Neither exists → tell the user no graph is built yet and suggest `aikgraph update …`. Do not fabricate answers from file scans.

## Step 1 — pick the right project graph

When multiple project subfolders exist under `~/.kiro/aikgraph-out/`:

1. **User named a project** (e.g. "in X-Platform-Testing, …", "for the Billing project"): match the name (case-insensitive, hyphens/underscores are interchangeable) against subfolder names under `~/.kiro/aikgraph-out/`. Use that path.
2. **User did not name one, and only one subfolder exists:** use it.
3. **User did not name one, and multiple subfolders exist:** **ask** which project they mean. List the available subfolders. Do not guess.
4. **User is asking about the repo they're in** (path-based question, not project-name): prefer `./.kiro/aikgraph-out/graph.json` if present.

Store the chosen path; reuse it for follow-up questions in the same turn without re-asking.

## Step 2 — read the report first (once per session or project switch)

```bash
cat ~/.kiro/aikgraph-out/<project>/REPORT.md
```

This gives god nodes, community labels, and surprising cross-file connections — the map of what questions the graph can answer well. Skim it before the first query.

## Step 3 — query the graph

Always pass `--graph <full path>` so you hit the project you selected:

```bash
GRAPH=~/.kiro/aikgraph-out/<project>/graph.json

# neighborhood / broad context
aikgraph query "<question>" --graph "$GRAPH"

# trace one chain deeper
aikgraph query "<question>" --dfs --graph "$GRAPH"

# cap answer tokens
aikgraph query "<question>" --budget 1500 --graph "$GRAPH"

# shortest path between two named symbols
aikgraph path "LoginController" "UserRepository" --graph "$GRAPH"

# one node + immediate neighbors
aikgraph explain "SessionMiddleware" --graph "$GRAPH"
```

Alternative: export once and drop the `--graph` flag for the rest of the session.

```bash
export AIKGRAPH_OUT=~/.kiro/aikgraph-out/<project>
aikgraph query "<question>"
```

Answer using **only** the subgraph the CLI returns. Cite `source_location` when you quote a fact. If the graph doesn't contain the answer, say so — do not invent edges, and only then fall back to `grep`/`find`/file reads (and say explicitly that you're falling back).

## Step 4 — rebuild if stale

If the user reports recent code changes and the graph looks out of date:

```bash
# project-local graph
aikgraph update <repo-path>

# Azure DevOps project graph (incremental; reuses prior state)
AZURE_DEVOPS_PAT=<pat> AZURE_DEVOPS_ORG=<org> \
  aikgraph update --project <name> <repo-path>
```

## Commands reference

| Goal | Command |
|---|---|
| Build/refresh a project-local graph | `aikgraph update <path>` |
| Build/refresh an Azure DevOps project graph | `AZURE_DEVOPS_PAT=… AZURE_DEVOPS_ORG=… aikgraph update --project <name> <path>` |
| Watch folder and auto-rebuild on change | `aikgraph watch <path>` |
| Re-cluster existing graph (no extraction) | `aikgraph cluster-only <path>` |
| Query (BFS — broad context) | `aikgraph query "<q>" --graph <path>` |
| Query (DFS — trace a chain) | `aikgraph query "<q>" --dfs --graph <path>` |
| Shortest path between two concepts | `aikgraph path "A" "B" --graph <path>` |
| Explain a single node | `aikgraph explain "X" --graph <path>` |
| Add a URL (tweet, arXiv, PDF, page) to the corpus | `aikgraph add <url>` |
| Benchmark token savings | `aikgraph benchmark <path-to-graph.json>` |
| Git post-commit auto-rebuild | `aikgraph hook {install\|uninstall\|status}` |

## Examples

```bash
# Discover
ls ~/.kiro/aikgraph-out/
# → X-Platform-Testing/  Billing/

# Orient
cat ~/.kiro/aikgraph-out/X-Platform-Testing/REPORT.md

# Ask
aikgraph query "how does the extraction service authenticate?" \
  --graph ~/.kiro/aikgraph-out/X-Platform-Testing/graph.json

# Trace
aikgraph path "LoginController" "UserRepository" \
  --graph ~/.kiro/aikgraph-out/X-Platform-Testing/graph.json

# Pin one project for a whole session
export AIKGRAPH_OUT=~/.kiro/aikgraph-out/X-Platform-Testing
aikgraph explain "SessionMiddleware"

# Refresh an Azure DevOps project graph
export AZURE_DEVOPS_PAT=<pat>
export AZURE_DEVOPS_ORG=MyOrg
aikgraph update --project X-Platform-Testing --since 2025-10-21 ~/source/xplatform-staging
```

## Rules

- Always call aikgraph through the shell tool — never write raw Python against `graph.json`.
- Resolve the right graph path **before** the first query. Don't start querying the wrong project and hope the user corrects you.
- When multiple projects exist and the user didn't name one, ask — don't guess.
- Cite `source_location` from query output when answering.
- If the graph is empty on a topic, say so and only then fall back to `grep`/`find` (and say you're falling back).
