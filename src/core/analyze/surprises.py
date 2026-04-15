"""Surprising connections: cross-file and cross-community edges ranked by non-obviousness."""
from __future__ import annotations

import networkx as nx

from ._filters import (
    file_category,
    is_concept_node,
    is_file_node,
    node_community_map,
    top_level_dir,
)


def surprising_connections(
    G: nx.Graph,
    communities: dict[int, list[str]] | None = None,
    top_n: int = 5,
) -> list[dict]:
    """Find connections that are genuinely surprising - not obvious from file structure.

    Strategy:
    - Multi-file corpora: cross-file edges between real entities (not concept nodes),
      ranked by a composite surprise score.
    - Single-file / single-source corpora: cross-community edges that bridge
      distant parts of the graph (betweenness centrality on edges).

    Concept nodes (empty source_file, or injected semantic annotations) are excluded
    from surprising connections because they are intentional, not discovered.
    """
    source_files = {
        data.get("source_file", "")
        for _, data in G.nodes(data=True)
        if data.get("source_file", "")
    }
    is_multi_source = len(source_files) > 1

    if is_multi_source:
        return _cross_file_surprises(G, communities or {}, top_n)
    return _cross_community_surprises(G, communities or {}, top_n)


def _surprise_score(
    G: nx.Graph,
    u: str,
    v: str,
    data: dict,
    node_community: dict[str, int],
    u_source: str,
    v_source: str,
) -> tuple[int, list[str]]:
    """Score how surprising a cross-file edge is. Returns (score, reasons)."""
    score = 0
    reasons: list[str] = []

    conf = data.get("confidence", "EXTRACTED")
    conf_bonus = {"AMBIGUOUS": 3, "INFERRED": 2, "EXTRACTED": 1}.get(conf, 1)
    score += conf_bonus
    if conf in ("AMBIGUOUS", "INFERRED"):
        reasons.append(f"{conf.lower()} connection - not explicitly stated in source")

    cat_u = file_category(u_source)
    cat_v = file_category(v_source)
    if cat_u != cat_v:
        score += 2
        reasons.append(f"crosses file types ({cat_u} ↔ {cat_v})")

    if top_level_dir(u_source) != top_level_dir(v_source):
        score += 2
        reasons.append("connects across different repos/directories")

    cid_u = node_community.get(u)
    cid_v = node_community.get(v)
    if cid_u is not None and cid_v is not None and cid_u != cid_v:
        score += 1
        reasons.append("bridges separate communities")

    if data.get("relation") == "semantically_similar_to":
        score = int(score * 1.5)
        reasons.append("semantically similar concepts with no structural link")

    deg_u = G.degree(u)
    deg_v = G.degree(v)
    if min(deg_u, deg_v) <= 2 and max(deg_u, deg_v) >= 5:
        score += 1
        peripheral = (
            G.nodes[u].get("label", u) if deg_u <= 2 else G.nodes[v].get("label", v)
        )
        hub = G.nodes[v].get("label", v) if deg_u <= 2 else G.nodes[u].get("label", u)
        reasons.append(
            f"peripheral node `{peripheral}` unexpectedly reaches hub `{hub}`"
        )

    return score, reasons


def _resolve_endpoint(G: nx.Graph, data: dict, key: str, fallback: str) -> str:
    """Return data[key] if it's a valid node id, else fallback."""
    candidate = data.get(key, fallback)
    return candidate if candidate in G.nodes else fallback


def _cross_file_surprises(
    G: nx.Graph, communities: dict[int, list[str]], top_n: int
) -> list[dict]:
    """Cross-file edges between real code/doc entities, ranked by composite surprise score."""
    node_community = node_community_map(communities)
    candidates = []

    for u, v, data in G.edges(data=True):
        relation = data.get("relation", "")
        if relation in ("imports", "imports_from", "contains", "method"):
            continue
        if is_concept_node(G, u) or is_concept_node(G, v):
            continue
        if is_file_node(G, u) or is_file_node(G, v):
            continue

        u_source = G.nodes[u].get("source_file", "")
        v_source = G.nodes[v].get("source_file", "")
        if not u_source or not v_source or u_source == v_source:
            continue

        score, reasons = _surprise_score(
            G, u, v, data, node_community, u_source, v_source
        )
        src_id = _resolve_endpoint(G, data, "_src", u)
        tgt_id = _resolve_endpoint(G, data, "_tgt", v)
        candidates.append(
            {
                "_score": score,
                "source": G.nodes[src_id].get("label", src_id),
                "target": G.nodes[tgt_id].get("label", tgt_id),
                "source_files": [
                    G.nodes[src_id].get("source_file", ""),
                    G.nodes[tgt_id].get("source_file", ""),
                ],
                "confidence": data.get("confidence", "EXTRACTED"),
                "relation": relation,
                "why": (
                    "; ".join(reasons) if reasons else "cross-file semantic connection"
                ),
            }
        )

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    for c in candidates:
        c.pop("_score")

    if candidates:
        return candidates[:top_n]

    return _cross_community_surprises(G, communities, top_n)


def _cross_community_surprises(
    G: nx.Graph,
    communities: dict[int, list[str]],
    top_n: int,
) -> list[dict]:
    """Edges that bridge different communities (or high-betweenness if no communities)."""
    if not communities:
        if G.number_of_edges() == 0:
            return []
        betweenness = nx.edge_betweenness_centrality(G)
        top_edges = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[
            :top_n
        ]
        result = []
        for (u, v), score in top_edges:
            data = G.edges[u, v]
            result.append(
                {
                    "source": G.nodes[u].get("label", u),
                    "target": G.nodes[v].get("label", v),
                    "source_files": [
                        G.nodes[u].get("source_file", ""),
                        G.nodes[v].get("source_file", ""),
                    ],
                    "confidence": data.get("confidence", "EXTRACTED"),
                    "relation": data.get("relation", ""),
                    "note": f"Bridges graph structure (betweenness={score:.3f})",
                }
            )
        return result

    node_community = node_community_map(communities)

    surprises = []
    for u, v, data in G.edges(data=True):
        cid_u = node_community.get(u)
        cid_v = node_community.get(v)
        if cid_u is None or cid_v is None or cid_u == cid_v:
            continue
        if is_file_node(G, u) or is_file_node(G, v):
            continue
        relation = data.get("relation", "")
        if relation in ("imports", "imports_from", "contains", "method"):
            continue
        confidence = data.get("confidence", "EXTRACTED")
        src_id = _resolve_endpoint(G, data, "_src", u)
        tgt_id = _resolve_endpoint(G, data, "_tgt", v)
        surprises.append(
            {
                "source": G.nodes[src_id].get("label", src_id),
                "target": G.nodes[tgt_id].get("label", tgt_id),
                "source_files": [
                    G.nodes[src_id].get("source_file", ""),
                    G.nodes[tgt_id].get("source_file", ""),
                ],
                "confidence": confidence,
                "relation": relation,
                "note": f"Bridges community {cid_u} → community {cid_v}",
                "_pair": tuple(sorted([cid_u, cid_v])),
            }
        )

    order = {"AMBIGUOUS": 0, "INFERRED": 1, "EXTRACTED": 2}
    surprises.sort(key=lambda x: order.get(x["confidence"], 3))

    seen_pairs: set[tuple] = set()
    deduped = []
    for s in surprises:
        pair = s.pop("_pair")
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            deduped.append(s)
    return deduped[:top_n]
