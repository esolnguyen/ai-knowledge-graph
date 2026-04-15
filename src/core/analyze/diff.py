"""Compare two graph snapshots - used by the incremental --update flow."""
from __future__ import annotations

import networkx as nx


def _edge_key(G: nx.Graph, u: str, v: str, data: dict) -> tuple:
    if G.is_directed():
        return (u, v, data.get("relation", ""))
    return (min(u, v), max(u, v), data.get("relation", ""))


def _pluralize(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


def graph_diff(G_old: nx.Graph, G_new: nx.Graph) -> dict:
    """Compare two graph snapshots and return what changed.

    Returns:
        {
          "new_nodes": [{"id": ..., "label": ...}],
          "removed_nodes": [{"id": ..., "label": ...}],
          "new_edges": [{"source": ..., "target": ..., "relation": ..., "confidence": ...}],
          "removed_edges": [...],
          "summary": "3 new nodes, 5 new edges, 1 node removed"
        }
    """
    old_nodes = set(G_old.nodes())
    new_nodes = set(G_new.nodes())

    added_node_ids = new_nodes - old_nodes
    removed_node_ids = old_nodes - new_nodes

    new_nodes_list = [
        {"id": n, "label": G_new.nodes[n].get("label", n)} for n in added_node_ids
    ]
    removed_nodes_list = [
        {"id": n, "label": G_old.nodes[n].get("label", n)} for n in removed_node_ids
    ]

    old_edge_keys = {_edge_key(G_old, u, v, d) for u, v, d in G_old.edges(data=True)}
    new_edge_keys = {_edge_key(G_new, u, v, d) for u, v, d in G_new.edges(data=True)}

    added_edge_keys = new_edge_keys - old_edge_keys
    removed_edge_keys = old_edge_keys - new_edge_keys

    new_edges_list = [
        {
            "source": u,
            "target": v,
            "relation": d.get("relation", ""),
            "confidence": d.get("confidence", ""),
        }
        for u, v, d in G_new.edges(data=True)
        if _edge_key(G_new, u, v, d) in added_edge_keys
    ]

    removed_edges_list = [
        {
            "source": u,
            "target": v,
            "relation": d.get("relation", ""),
            "confidence": d.get("confidence", ""),
        }
        for u, v, d in G_old.edges(data=True)
        if _edge_key(G_old, u, v, d) in removed_edge_keys
    ]

    parts = []
    if new_nodes_list:
        parts.append(f"{_pluralize(len(new_nodes_list), 'new node')}")
    if new_edges_list:
        parts.append(f"{_pluralize(len(new_edges_list), 'new edge')}")
    if removed_nodes_list:
        parts.append(f"{_pluralize(len(removed_nodes_list), 'node')} removed")
    if removed_edges_list:
        parts.append(f"{_pluralize(len(removed_edges_list), 'edge')} removed")
    summary = ", ".join(parts) if parts else "no changes"

    return {
        "new_nodes": new_nodes_list,
        "removed_nodes": removed_nodes_list,
        "new_edges": new_edges_list,
        "removed_edges": removed_edges_list,
        "summary": summary,
    }
