---
name: aikgraph
description: >
  Interact with the project's aikgraph knowledge graph. Activate for any
  architecture / dependency / "where does X live" question, for tracing call
  paths, for shortest-path lookups between symbols, for explaining a node, for
  rebuilding the graph after edits, for ingesting external URLs, for auto-
  rebuild on save, for re-clustering, for installing commit hooks, or for
  saving Q&A results back into the graph.
---

# aikgraph skill

This project ships with a precomputed knowledge graph. The graph lives under
`.kiro/aikgraph-out/` when Kiro is installed, otherwise `aikgraph-out/` at the
project root. Use the graph **before** grepping raw files for structural
questions — it already surfaces god-nodes, communities, and cross-file edges.

The skill drives everything through the `aikgraph` shell command — never hand-
roll Python snippets against `graph.json`.

## Workflow

1. **Orient.** Read `aikgraph-out/REPORT.md` (or `.kiro/aikgraph-out/REPORT.md`)
   if it exists. It summarises god nodes, community structure, and surprising
   connections.
2. **Check freshness.** If the user just edited code this session, run
   `aikgraph update` before querying.
3. **Pick the narrowest command** from the table below.
4. **Cite what you used.** Name the nodes and edges the graph surfaced. If the
   graph is silent on something, say so — never invent an edge.
5. **Save the answer** with `aikgraph save-result` so the next rebuild folds
   the Q&A back into the graph.

## Command map

| Intent | Command |
|---|---|
| Open-ended "how does X work?" / traversal around a concept | `aikgraph query "<question>" [--dfs] [--budget N]` |
| Shortest path between two concepts / "does A reach B?" | `aikgraph path "A" "B"` |
| Explain one node and its immediate neighbours | `aikgraph explain "X"` |
| Rebuild the graph after code changes (no LLM) | `aikgraph update [<path>] [--obsidian]` |
| Re-cluster an existing graph, regenerate REPORT.md | `aikgraph cluster-only [<path>]` |
| Auto-rebuild on save (code-only is instant; docs/images flag `needs_update`) | `aikgraph watch [<path>]` |
| Pull a URL into `./raw` then update the graph | `aikgraph add <url> [--author N] [--contributor N] [--dir DIR]` |
| Install/remove/inspect the git post-commit hook | `aikgraph hook [install\|uninstall\|status]` |
| Persist a Q&A back into the graph | `aikgraph save-result --question Q --answer A [--type query\|path_query\|explain] [--nodes …]` |
| Measure token reduction vs. naïve full-corpus prompts | `aikgraph benchmark [graph.json]` |

## Command reference

### `aikgraph query "<question>" [--dfs] [--budget N] [--graph <path>]`
BFS traversal of `graph.json` anchored on symbols mentioned in the question.
Returns a ranked subgraph capped at N tokens (default 2000). Use `--dfs` to
follow one chain deeper; `--budget` to tighten or expand. Works best when the
question names concrete symbols or concepts. If the output reports no matching
nodes, broaden the wording or `aikgraph update` and retry.

### `aikgraph path "A" "B" [--graph <path>]`
Shortest path between two nodes. Use for "does A depend on B?", "how do these
two subsystems connect?", "what's the bridge between X and Y?".

### `aikgraph explain "X" [--graph <path>]`
Plain-language explanation of node X and its immediate neighbours. Use for
"what is this class for?", "what does this function touch?".

### `aikgraph update [<path>] [--obsidian]`
Re-runs AST extraction and rebuilds `graph.json` + `REPORT.md`. No LLM needed
for code. Add `--obsidian` to also emit an Obsidian vault + `graph.canvas`.
For doc/paper/image changes an LLM pass is required — mention this and let the
user decide before re-extracting.

### `aikgraph cluster-only [<path>]`
Skip extraction. Loads existing `graph.json`, re-runs community detection and
scoring, and regenerates `REPORT.md`. Use after tweaking clustering logic or
when only the narrative output is stale.

### `aikgraph watch [<path>]`
Observes `<path>` for file changes. Code-only bursts trigger an immediate AST
rebuild; doc/paper/image changes write an `aikgraph-out/needs_update` flag and
prompt the user to `aikgraph update`. Good background companion for agentic
workflows. Ctrl-C stops it.

### `aikgraph add <url> [--author Name] [--contributor Name] [--dir <path>]`
Fetches the URL into `./raw/` (or `--dir`). Auto-handles Twitter/X via oEmbed,
arXiv abstracts, PDFs, images, and generic webpages (converted to Markdown).
Tag `--author` (who wrote it) and `--contributor` (who added it) so the
provenance makes it into the graph. Run `aikgraph update` afterwards.

### `aikgraph hook [install|uninstall|status]`
Installs a git post-commit/post-checkout hook. After each commit the hook
diffs HEAD~1, re-runs AST extraction on changed code files, and updates
`graph.json` + `REPORT.md`. Doc/image changes are skipped — run
`aikgraph update` manually for those.

### `aikgraph save-result --question Q --answer A [--type T] [--nodes …]`
Persists a Q&A into `aikgraph-out/memory/`. `--type` is `query`, `path_query`,
or `explain` (default `query`). `--nodes` lists the node labels cited in the
answer. The next `aikgraph update` folds the memory back in as graph nodes so
future queries can cite prior answers.

### `aikgraph benchmark [graph.json]`
Reports token reduction vs. a naïve "stuff the whole corpus in the prompt"
approach. Useful when justifying the graph to stakeholders or when the corpus
has more than ~5k words.

## Rules

- **Never invent an edge.** If the graph doesn't show it, it isn't there — say
  so and offer to run `aikgraph update` instead of guessing.
- **Prefer graph commands over grep** when the question is structural.
- **Always cite** the nodes/edges you used so the user can verify.
- **Respect confidence tags** — treat `EXTRACTED` as fact, `INFERRED` as a
  reasonable lead, `AMBIGUOUS` as "worth checking, might be wrong".
- **After answering**, save the result with `aikgraph save-result` so the
  graph improves over time.
- **If the graph is empty, missing, or older than recent edits**, tell the
  user and run `aikgraph update` before continuing.
