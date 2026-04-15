"""GraphML export for Gephi / yEd."""
from __future__ import annotations

import networkx as nx

from aikgraph.core.analyze._filters import node_community_map as _node_community_map


def to_graphml(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
) -> None:
    """Export graph as GraphML with community IDs as node attributes."""
    H = G.copy()
    node_community = _node_community_map(communities)
    for node_id in H.nodes():
        H.nodes[node_id]["community"] = node_community.get(node_id, -1)
    nx.write_graphml(H, output_path)
