# cluster-only

Skip extraction. Load existing `aikgraph-out/graph.json` and re-run clustering:

```bash
$(cat .aikgraph_python) -c "
import sys, json
from aikgraph.cluster import cluster, score_all
from aikgraph.analyze import god_nodes, surprising_connections
from aikgraph.report import generate
from aikgraph.output import to_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

data = json.loads(Path('aikgraph-out/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

detection = {'total_files': 0, 'total_words': 99999, 'needs_graph': True, 'warning': None,
             'files': {'code': [], 'document': [], 'paper': []}}
tokens = {'input': 0, 'output': 0}

communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, '.')
Path('aikgraph-out/REPORT.md').write_text(report)
to_json(G, communities, 'aikgraph-out/graph.json')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
}
Path('.aikgraph_analysis.json').write_text(json.dumps(analysis, indent=2))
print(f'Re-clustered: {len(communities)} communities')
"
```

Then run Steps 5–9 as normal (label communities, generate viz, benchmark, clean up, report).

