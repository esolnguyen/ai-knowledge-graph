"""Shared helpers: node classification and path categorization."""
from __future__ import annotations

from pathlib import Path

import networkx as nx

from aikgraph.extraction.detect import (
    CODE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PAPER_EXTENSIONS,
)


def node_community_map(communities: dict[int, list[str]]) -> dict[str, int]:
    """Invert communities dict: node_id -> community_id."""
    return {n: cid for cid, nodes in communities.items() for n in nodes}


def is_file_node(G: nx.Graph, node_id: str) -> bool:
    """Return True if node is a file-level hub or AST method/function stub.

    These are synthetic nodes created by the AST extractor and should be excluded
    from god nodes, surprising connections, and knowledge gap reporting.
    """
    attrs = G.nodes[node_id]
    label = attrs.get("label", "")
    if not label:
        return False
    source_file = attrs.get("source_file", "")
    if source_file and label == Path(source_file).name:
        return True
    if label.startswith(".") and label.endswith("()"):
        return True
    if label.endswith("()") and G.degree(node_id) <= 1:
        return True
    return False


def is_concept_node(G: nx.Graph, node_id: str) -> bool:
    """Return True if node is a manually-injected semantic concept, not a real entity."""
    data = G.nodes[node_id]
    source = data.get("source_file", "")
    if not source:
        return True
    if "." not in source.split("/")[-1]:
        return True
    return False


def file_category(path: str) -> str:
    ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in PAPER_EXTENSIONS:
        return "paper"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "doc"


def top_level_dir(path: str) -> str:
    """Return the first path component - used to detect cross-repo edges."""
    return path.split("/")[0] if "/" in path else path
