"""Obsidian vault and canvas export."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import networkx as nx

from aikgraph.core.analyze._filters import node_community_map as _node_community_map
from aikgraph.output._common import COMMUNITY_COLORS


def _safe_name(label: str) -> str:
    cleaned = re.sub(
        r'[\\/*?:"<>|#^[\]]',
        "",
        label.replace("\r\n", " ").replace("\r", " ").replace("\n", " "),
    ).strip()
    cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned or "unnamed"


def _build_node_filenames(G: nx.Graph) -> dict[str, str]:
    node_filename: dict[str, str] = {}
    seen_names: dict[str, int] = {}
    for node_id, data in G.nodes(data=True):
        base = _safe_name(data.get("label", node_id))
        if base in seen_names:
            seen_names[base] += 1
            node_filename[node_id] = f"{base}_{seen_names[base]}"
        else:
            seen_names[base] = 0
            node_filename[node_id] = base
    return node_filename


_FTYPE_TAG = {
    "code": "aikgraph/code",
    "document": "aikgraph/document",
    "paper": "aikgraph/paper",
    "image": "aikgraph/image",
}


def to_obsidian(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_dir: str,
    community_labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Export graph as an Obsidian vault with wikilinks and community overview notes."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    node_community = _node_community_map(communities)
    node_filename = _build_node_filenames(G)

    def _dominant_confidence(node_id: str) -> str:
        confs = [edata.get("confidence", "EXTRACTED") for _, _, edata in G.edges(node_id, data=True)]
        if not confs:
            return "EXTRACTED"
        return Counter(confs).most_common(1)[0][0]

    # Write one .md file per node
    for node_id, data in G.nodes(data=True):
        label = data.get("label", node_id)
        cid = node_community.get(node_id)
        community_name = (community_labels or {}).get(cid, f"Community {cid}") if cid is not None else f"Community {cid}"

        ftype = data.get("file_type", "")
        ftype_tag = _FTYPE_TAG.get(ftype, f"aikgraph/{ftype}" if ftype else "aikgraph/document")
        node_tags = [ftype_tag, f"aikgraph/{_dominant_confidence(node_id)}", f"community/{community_name.replace(' ', '_')}"]

        lines: list[str] = [
            "---",
            f'source_file: "{data.get("source_file", "")}"',
            f'type: "{ftype}"',
            f'community: "{community_name}"',
        ]
        if data.get("source_location"):
            lines.append(f'location: "{data["source_location"]}"')
        lines.append("tags:")
        for tag in node_tags:
            lines.append(f"  - {tag}")
        lines += ["---", "", f"# {label}", ""]

        neighbors = list(G.neighbors(node_id))
        if neighbors:
            lines.append("## Connections")
            for neighbor in sorted(neighbors, key=lambda n: G.nodes[n].get("label", n)):
                edge_data = G.edges[node_id, neighbor]
                lines.append(f"- [[{node_filename[neighbor]}]] - `{edge_data.get('relation', '')}` [{edge_data.get('confidence', 'EXTRACTED')}]")
            lines.append("")

        lines.append(" ".join(f"#{t}" for t in node_tags))
        (out / f"{node_filename[node_id]}.md").write_text("\n".join(lines), encoding="utf-8")

    # Inter-community edge counts
    inter_community_edges: dict[int, dict[int, int]] = {cid: {} for cid in communities}
    for u, v in G.edges():
        cu, cv = node_community.get(u), node_community.get(v)
        if cu is not None and cv is not None and cu != cv:
            inter_community_edges.setdefault(cu, {}); inter_community_edges.setdefault(cv, {})
            inter_community_edges[cu][cv] = inter_community_edges[cu].get(cv, 0) + 1
            inter_community_edges[cv][cu] = inter_community_edges[cv].get(cu, 0) + 1

    def _community_reach(node_id: str) -> int:
        return len({node_community[nb] for nb in G.neighbors(node_id)
                     if nb in node_community and node_community[nb] != node_community.get(node_id)})

    # Write community overview notes
    community_notes_written = 0
    for cid, members in communities.items():
        community_name = (community_labels or {}).get(cid, f"Community {cid}") if cid is not None else f"Community {cid}"
        coh_value = cohesion.get(cid) if cohesion else None

        lines: list[str] = ["---", "type: community"]
        if coh_value is not None:
            lines.append(f"cohesion: {coh_value:.2f}")
        lines += [f"members: {len(members)}", "---", "", f"# {community_name}", ""]

        if coh_value is not None:
            desc = "tightly connected" if coh_value >= 0.7 else "moderately connected" if coh_value >= 0.4 else "loosely connected"
            lines.append(f"**Cohesion:** {coh_value:.2f} - {desc}")
        lines += [f"**Members:** {len(members)} nodes", "", "## Members"]

        for nid in sorted(members, key=lambda n: G.nodes[n].get("label", n)):
            d = G.nodes[nid]
            entry = f"- [[{node_filename[nid]}]]"
            if d.get("file_type"): entry += f" - {d['file_type']}"
            if d.get("source_file"): entry += f" - {d['source_file']}"
            lines.append(entry)
        lines.append("")

        comm_tag = community_name.replace(" ", "_")
        lines += ["## Live Query (requires Dataview plugin)", "", "```dataview",
                   f"TABLE source_file, type FROM #community/{comm_tag}", "SORT file.name ASC", "```", ""]

        cross = inter_community_edges.get(cid, {})
        if cross:
            lines.append("## Connections to other communities")
            for other_cid, cnt in sorted(cross.items(), key=lambda x: -x[1]):
                other_name = (community_labels or {}).get(other_cid, f"Community {other_cid}") if other_cid is not None else f"Community {other_cid}"
                lines.append(f"- {cnt} edge{'s' if cnt != 1 else ''} to [[_COMMUNITY_{_safe_name(other_name)}]]")
            lines.append("")

        bridges = [(nid, G.degree(nid), _community_reach(nid)) for nid in members if _community_reach(nid) > 0]
        bridges.sort(key=lambda x: (-x[2], -x[1]))
        if bridges[:5]:
            lines.append("## Top bridge nodes")
            for nid, deg, reach in bridges[:5]:
                lines.append(f"- [[{node_filename[nid]}]] - degree {deg}, connects to {reach} {'community' if reach == 1 else 'communities'}")

        (out / f"_COMMUNITY_{_safe_name(community_name)}.md").write_text("\n".join(lines), encoding="utf-8")
        community_notes_written += 1

    # Write .obsidian/graph.json for community colors
    obsidian_dir = out / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    graph_config = {"colorGroups": [
        {"query": f"tag:#community/{label.replace(' ', '_')}",
         "color": {"a": 1, "rgb": int(COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)].lstrip("#"), 16)}}
        for cid, label in sorted((community_labels or {}).items())
    ]}
    (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2), encoding="utf-8")

    return G.number_of_nodes() + community_notes_written


def to_canvas(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    node_filenames: dict[str, str] | None = None,
) -> None:
    """Export graph as an Obsidian Canvas file with community groups."""
    CANVAS_COLORS = ["1", "2", "3", "4", "5", "6"]

    if node_filenames is None:
        node_filenames = _build_node_filenames(G)

    num_communities = len(communities)
    cols = math.ceil(math.sqrt(num_communities)) if num_communities > 0 else 1

    sorted_cids = sorted(communities.keys())
    group_sizes: dict[int, tuple[int, int]] = {}
    for cid in sorted_cids:
        n = len(communities[cid])
        w = max(600, 220 * math.ceil(math.sqrt(n)) if n > 0 else 600)
        h = max(400, 100 * math.ceil(n / 3) + 120 if n > 0 else 400)
        group_sizes[cid] = (w, h)

    rows = math.ceil(num_communities / cols) if num_communities > 0 else 1
    col_widths = []
    for ci in range(cols):
        max_w = max((group_sizes[sorted_cids[ri * cols + ci]][0]
                      for ri in range(rows) if ri * cols + ci < len(sorted_cids)), default=0)
        col_widths.append(max_w)
    row_heights = []
    for ri in range(rows):
        max_h = max((group_sizes[sorted_cids[ri * cols + ci]][1]
                      for ci in range(cols) if ri * cols + ci < len(sorted_cids)), default=0)
        row_heights.append(max_h)

    gap = 80
    group_layout: dict[int, tuple[int, int, int, int]] = {}
    for idx, cid in enumerate(sorted_cids):
        ci, ri = idx % cols, idx // cols
        gx = sum(col_widths[:ci]) + ci * gap
        gy = sum(row_heights[:ri]) + ri * gap
        group_layout[cid] = (gx, gy, *group_sizes[cid])

    all_canvas_nodes: set[str] = set()
    for members in communities.values():
        all_canvas_nodes.update(members)

    canvas_nodes: list[dict] = []
    canvas_edges: list[dict] = []

    for idx, cid in enumerate(sorted_cids):
        community_name = (community_labels or {}).get(cid, f"Community {cid}") if cid is not None else f"Community {cid}"
        gx, gy, gw, gh = group_layout[cid]
        canvas_nodes.append({"id": f"g{cid}", "type": "group", "label": community_name,
                             "x": gx, "y": gy, "width": gw, "height": gh,
                             "color": CANVAS_COLORS[idx % len(CANVAS_COLORS)]})

        for m_idx, node_id in enumerate(sorted(communities[cid], key=lambda n: G.nodes[n].get("label", n))):
            col, row = m_idx % 3, m_idx // 3
            fname = node_filenames.get(node_id, _safe_name(G.nodes[node_id].get("label", node_id)))
            canvas_nodes.append({"id": f"n_{node_id}", "type": "file",
                                 "file": f"aikgraph/obsidian/{fname}.md",
                                 "x": gx + 20 + col * 200, "y": gy + 80 + row * 80,
                                 "width": 180, "height": 60})

    all_edges = sorted(
        ((edata.get("weight", 1.0), u, v,
          f"{edata.get('relation', '')} [{edata.get('confidence', 'EXTRACTED')}]".strip())
         for u, v, edata in G.edges(data=True) if u in all_canvas_nodes and v in all_canvas_nodes),
        key=lambda x: -x[0],
    )[:200]
    for _, u, v, label in all_edges:
        canvas_edges.append({"id": f"e_{u}_{v}", "fromNode": f"n_{u}", "toNode": f"n_{v}", "label": label})

    Path(output_path).write_text(json.dumps({"nodes": canvas_nodes, "edges": canvas_edges}, indent=2), encoding="utf-8")