"""Generate questions the graph is uniquely positioned to answer."""
from __future__ import annotations

import networkx as nx

from ._filters import is_concept_node, is_file_node, node_community_map


def _ambiguous_edge_questions(G: nx.Graph) -> list[dict]:
    out = []
    for u, v, data in G.edges(data=True):
        if data.get("confidence") != "AMBIGUOUS":
            continue
        ul = G.nodes[u].get("label", u)
        vl = G.nodes[v].get("label", v)
        relation = data.get("relation", "related to")
        out.append(
            {
                "type": "ambiguous_edge",
                "question": f"What is the exact relationship between `{ul}` and `{vl}`?",
                "why": f"Edge tagged AMBIGUOUS (relation: {relation}) - confidence is low.",
            }
        )
    return out


def _bridge_node_questions(
    G: nx.Graph,
    node_community: dict[str, int],
    community_labels: dict[int, str],
) -> list[dict]:
    if G.number_of_edges() == 0:
        return []
    betweenness = nx.betweenness_centrality(G)
    bridges = sorted(
        [
            (n, s)
            for n, s in betweenness.items()
            if not is_file_node(G, n) and not is_concept_node(G, n) and s > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    out = []
    for node_id, score in bridges:
        label = G.nodes[node_id].get("label", node_id)
        cid = node_community.get(node_id)
        comm_label = (
            community_labels.get(cid, f"Community {cid}")
            if cid is not None
            else "unknown"
        )
        neighbors = list(G.neighbors(node_id))
        neighbor_comms = {
            node_community.get(n) for n in neighbors if node_community.get(n) != cid
        }
        if not neighbor_comms:
            continue
        other_labels = [
            community_labels.get(c, f"Community {c}") for c in neighbor_comms
        ]
        out.append(
            {
                "type": "bridge_node",
                "question": f"Why does `{label}` connect `{comm_label}` to {', '.join(f'`{l}`' for l in other_labels)}?",
                "why": f"High betweenness centrality ({score:.3f}) - this node is a cross-community bridge.",
            }
        )
    return out


def _verify_inferred_questions(G: nx.Graph) -> list[dict]:
    degree = dict(G.degree())
    top_nodes = sorted(
        [(n, d) for n, d in degree.items() if not is_file_node(G, n)],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    out = []
    for node_id, _ in top_nodes:
        inferred = [
            (u, v, d)
            for u, v, d in G.edges(node_id, data=True)
            if d.get("confidence") == "INFERRED"
        ]
        if len(inferred) < 2:
            continue
        label = G.nodes[node_id].get("label", node_id)
        others = []
        for u, v, d in inferred[:2]:
            src_id = d.get("_src", u)
            if src_id not in G.nodes:
                src_id = u
            tgt_id = d.get("_tgt", v)
            if tgt_id not in G.nodes:
                tgt_id = v
            other_id = tgt_id if src_id == node_id else src_id
            others.append(G.nodes[other_id].get("label", other_id))
        out.append(
            {
                "type": "verify_inferred",
                "question": f"Are the {len(inferred)} inferred relationships involving `{label}` (e.g. with `{others[0]}` and `{others[1]}`) actually correct?",
                "why": f"`{label}` has {len(inferred)} INFERRED edges - model-reasoned connections that need verification.",
            }
        )
    return out


def _isolated_node_questions(G: nx.Graph) -> list[dict]:
    isolated = [
        n
        for n in G.nodes()
        if G.degree(n) <= 1 and not is_file_node(G, n) and not is_concept_node(G, n)
    ]
    if not isolated:
        return []
    labels = [G.nodes[n].get("label", n) for n in isolated[:3]]
    return [
        {
            "type": "isolated_nodes",
            "question": f"What connects {', '.join(f'`{l}`' for l in labels)} to the rest of the system?",
            "why": f"{len(isolated)} weakly-connected nodes found - possible documentation gaps or missing edges.",
        }
    ]


def _low_cohesion_questions(
    G: nx.Graph,
    communities: dict[int, list[str]],
    community_labels: dict[int, str],
) -> list[dict]:
    from aikgraph.core.cluster import cohesion_score

    out = []
    for cid, nodes in communities.items():
        score = cohesion_score(G, nodes)
        if score < 0.15 and len(nodes) >= 5:
            label = community_labels.get(cid, f"Community {cid}")
            out.append(
                {
                    "type": "low_cohesion",
                    "question": f"Should `{label}` be split into smaller, more focused modules?",
                    "why": f"Cohesion score {score} - nodes in this community are weakly interconnected.",
                }
            )
    return out


def suggest_questions(
    G: nx.Graph,
    communities: dict[int, list[str]],
    community_labels: dict[int, str],
    top_n: int = 7,
) -> list[dict]:
    """Generate questions the graph is uniquely positioned to answer.

    Based on: AMBIGUOUS edges, bridge nodes, underexplored god nodes, isolated nodes,
    and low-cohesion communities. Each question has 'type', 'question', and 'why' fields.
    """
    node_community = node_community_map(communities)

    questions: list[dict] = []
    questions.extend(_ambiguous_edge_questions(G))
    questions.extend(_bridge_node_questions(G, node_community, community_labels))
    questions.extend(_verify_inferred_questions(G))
    questions.extend(_isolated_node_questions(G))
    questions.extend(_low_cohesion_questions(G, communities, community_labels))

    if not questions:
        return [
            {
                "type": "no_signal",
                "question": None,
                "why": (
                    "Not enough signal to generate questions. "
                    "This usually means the corpus has no AMBIGUOUS edges, no bridge nodes, "
                    "no INFERRED relationships, and all communities are tightly cohesive. "
                    "Add more files or run with --mode deep to extract richer edges."
                ),
            }
        ]

    return questions[:top_n]
