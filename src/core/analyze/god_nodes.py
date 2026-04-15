"""Top-degree real entities — the core abstractions."""
from __future__ import annotations

import networkx as nx

from ._filters import is_concept_node, is_file_node


def god_nodes(G: nx.Graph, top_n: int = 10) -> list[dict]:
    """Return the top_n most-connected real entities.

    File-level hub nodes are excluded: they accumulate import/contains edges
    mechanically and don't represent meaningful architectural abstractions.
    """
    degree = dict(G.degree())
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)
    result = []
    for node_id, deg in sorted_nodes:
        if is_file_node(G, node_id) or is_concept_node(G, node_id):
            continue
        result.append(
            {
                "id": node_id,
                "label": G.nodes[node_id].get("label", node_id),
                "edges": deg,
            }
        )
        if len(result) >= top_n:
            break
    return result
