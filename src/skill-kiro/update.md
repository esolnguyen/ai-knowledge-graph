# update (incremental)

Only re-extracts new/changed files since last run.

```bash
$(cat .aikgraph_python) -c "
import sys, json
from aikgraph.detect import detect_incremental, save_manifest
from pathlib import Path

result = detect_incremental(Path('INPUT_PATH'))
new_total = result.get('new_total', 0)
print(json.dumps(result, indent=2))
Path('.aikgraph_incremental.json').write_text(json.dumps(result))
if new_total == 0:
    print('No files changed since last run. Nothing to update.')
    raise SystemExit(0)
print(f'{new_total} new/changed file(s) to re-extract.')
"
```

If new files exist, first check whether all changed files are code files:

```bash
$(cat .aikgraph_python) -c "
import json
from pathlib import Path

result = json.loads(open('.aikgraph_incremental.json').read()) if Path('.aikgraph_incremental.json').exists() else {}
code_exts = {'.py','.ts','.js','.go','.rs','.java','.cpp','.c','.rb','.swift','.kt','.cs','.scala','.php','.cc','.cxx','.hpp','.h','.kts'}
new_files = result.get('new_files', {})
all_changed = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
print('code_only:', code_only)
"
```

If `code_only` is True: print `[aikgraph update] Code-only changes detected - skipping semantic extraction (no LLM needed)`, run only Step 3A (AST) on the changed files, skip Step 3B entirely (no subagents), then go straight to merge and Steps 4–8.

If `code_only` is False (any changed file is a doc/paper/image): run the full Steps 3A–3C pipeline as normal.

Then:

```bash
$(cat .aikgraph_python) -c "
import sys, json
from aikgraph.build import build_from_json
from aikgraph.output import to_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

# Load existing graph
existing_data = json.loads(Path('aikgraph-out/graph.json').read_text())
G_existing = json_graph.node_link_graph(existing_data, edges='links')

# Load new extraction
new_extraction = json.loads(Path('.aikgraph_extract.json').read_text())
G_new = build_from_json(new_extraction)

# Merge: new nodes/edges into existing graph
G_existing.update(G_new)
print(f'Merged: {G_existing.number_of_nodes()} nodes, {G_existing.number_of_edges()} edges')
" 
```

Then run Steps 4–8 on the merged graph as normal.

After Step 4, show the graph diff:

```bash
$(cat .aikgraph_python) -c "
import json
from aikgraph.analyze import graph_diff
from aikgraph.build import build_from_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

# Load old graph (before update) from backup written before merge
old_data = json.loads(Path('.aikgraph_old.json').read_text()) if Path('.aikgraph_old.json').exists() else None
new_extract = json.loads(Path('.aikgraph_extract.json').read_text())
G_new = build_from_json(new_extract)

if old_data:
    G_old = json_graph.node_link_graph(old_data, edges='links')
    diff = graph_diff(G_old, G_new)
    print(diff['summary'])
    if diff['new_nodes']:
        print('New nodes:', ', '.join(n['label'] for n in diff['new_nodes'][:5]))
    if diff['new_edges']:
        print('New edges:', len(diff['new_edges']))
"
```

Before the merge step, save the old graph: `cp aikgraph-out/graph.json .aikgraph_old.json`
Clean up after: `rm -f .aikgraph_old.json`

