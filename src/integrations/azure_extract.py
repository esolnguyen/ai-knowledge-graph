"""Turn Azure DevOps sync output into graph nodes and edges.

Reads `workitem_*.md` and `repos/<name>/_repo.md` markdown files produced by
`aikgraph.integrations.azure_devops.sync()` under `<watch_path>/raw/azure/`
and returns an extraction dict compatible with `build_from_json()`.

- Work items become `file_type: "document"` nodes.
- Repos become `file_type: "document"` nodes.
- Edges: work item hierarchy (`parent_of`), peer links (`related_to`), and
  work-item → repo links derived from ArtifactLink fields
  (`touches_commit`, `touches_pr`, `touches_branch`).
- Inferred `repo -> code` edges are added by `link_repos_to_code()` once the
  AST extractor has produced the code node ids.

Stdlib only. The parser is hand-rolled to match the exact YAML subset emitted
by `azure_devops._write_*_md()` — enough for us to avoid pulling in PyYAML.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_AZURE_SUBDIR = Path("raw") / "azure"
_WORK_ITEM_GLOB = "workitem_*.md"
_REPO_GLOB = "repos/*/_repo.md"


def extract_azure(watch_path: Path) -> dict[str, list]:
    """Scan `watch_path/raw/azure/` and build a node/edge extraction.

    Returns `{"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}`
    if the sync directory is missing or empty.
    """
    azure_dir = watch_path / _AZURE_SUBDIR
    empty = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}
    if not azure_dir.is_dir():
        return empty

    nodes: list[dict] = []
    edges: list[dict] = []

    # Repos first, so we can resolve artifact refs while parsing work items.
    repo_name_to_id: dict[str, str] = {}
    for path in sorted(azure_dir.glob(_REPO_GLOB)):
        fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
        name = fm.get("repo_name") or path.parent.name
        node_id = f"repo_{_safe_id(name)}"
        repo_name_to_id[name] = node_id
        # ArtifactLink URIs use the repo's display name; the on-disk directory
        # is the safe-filename form. Index both so lookups work either way.
        repo_name_to_id.setdefault(path.parent.name, node_id)
        nodes.append(_repo_node(path, fm, watch_path, node_id))

    workitem_ids: set[str] = set()
    parsed_workitems: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(azure_dir.glob(_WORK_ITEM_GLOB)):
        fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
        wid = fm.get("work_item_id", "")
        if not wid:
            continue
        parsed_workitems.append((path, fm))
        workitem_ids.add(wid)
        nodes.append(_workitem_node(path, fm, watch_path))

    for path, fm in parsed_workitems:
        wid = fm["work_item_id"]
        src_file = _rel(path, watch_path)
        src_id = f"workitem_{wid}"

        parent = fm.get("parent_id")
        if isinstance(parent, str) and parent and parent in workitem_ids:
            edges.append(_edge(
                source=f"workitem_{parent}",
                target=src_id,
                relation="parent_of",
                confidence="EXTRACTED",
                source_file=src_file,
            ))

        for related in _as_list(fm.get("related_ids")):
            if related in workitem_ids and related != wid:
                edges.append(_edge(
                    source=src_id,
                    target=f"workitem_{related}",
                    relation="related_to",
                    confidence="EXTRACTED",
                    source_file=src_file,
                ))

        # Collapse commit/PR/branch refs into one edge per (workitem, repo)
        # because `nx.Graph` is a simple graph — parallel edges would overwrite
        # each other and silently drop refs. Keep the individual refs as a list
        # attribute so queries can still surface them.
        repo_refs: dict[str, dict[str, list[str]]] = {}
        for ref_field, kind in (
            ("related_commits", "commits"),
            ("related_prs", "prs"),
            ("related_branches", "branches"),
        ):
            for ref in _as_list(fm.get(ref_field)):
                repo_name = _repo_name_from_ref(ref, kind)
                target = repo_name_to_id.get(repo_name)
                if target is None:
                    continue
                bucket = repo_refs.setdefault(
                    target, {"commits": [], "prs": [], "branches": []}
                )
                bucket[kind].append(ref)

        for target, buckets in repo_refs.items():
            edges.append(_edge(
                source=src_id,
                target=target,
                relation="touches_repo",
                confidence="EXTRACTED",
                source_file=src_file,
                commits=buckets["commits"],
                prs=buckets["prs"],
                branches=buckets["branches"],
            ))

    return {
        "nodes": nodes,
        "edges": edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def link_repos_to_code(
    azure_nodes: list[dict], code_nodes: list[dict]
) -> list[dict]:
    """Return inferred edges from each repo node to every code node that
    lives under its clone directory.

    Matches on the repo's on-disk path prefix (`raw/azure/repos/<dir>/`) which
    is derived from the repo node's `source_file` field. Edges are marked
    `confidence: "INFERRED"` so a consumer can filter them out if desired.
    """
    prefix_to_repo: dict[str, str] = {}
    for node in azure_nodes:
        nid = node.get("id", "")
        if not nid.startswith("repo_"):
            continue
        src = Path(node.get("source_file", ""))
        parts = src.parts
        if "repos" not in parts:
            continue
        idx = parts.index("repos")
        if idx + 1 >= len(parts):
            continue
        prefix = str(Path(*parts[: idx + 2])).replace("\\", "/") + "/"
        prefix_to_repo[prefix] = nid

    if not prefix_to_repo:
        return []

    edges: list[dict] = []
    for code in code_nodes:
        sf = str(code.get("source_file", "")).replace("\\", "/")
        if not sf:
            continue
        for prefix, repo_id in prefix_to_repo.items():
            if sf.startswith(prefix):
                edges.append(_edge(
                    source=repo_id,
                    target=code["id"],
                    relation="contains",
                    confidence="INFERRED",
                    source_file=sf,
                ))
                break
    return edges


# ---------------------------------------------------------------- node helpers


def _workitem_node(path: Path, fm: dict[str, Any], root: Path) -> dict:
    wid = fm["work_item_id"]
    title = fm.get("title") or f"Work item {wid}"
    wtype = fm.get("work_item_type", "WorkItem")
    label = f"[{wtype}-{wid}] {title}"[:120]
    return {
        "id": f"workitem_{wid}",
        "label": label,
        "file_type": "document",
        "source_file": _rel(path, root),
        "source_location": "L1",
        "work_item_type": wtype,
        "state": fm.get("state", ""),
        "assigned_to": fm.get("assigned_to", ""),
        "area_path": fm.get("area_path", ""),
        "iteration_path": fm.get("iteration_path", ""),
        "source_url": fm.get("source_url", ""),
    }


def _repo_node(path: Path, fm: dict[str, Any], root: Path, node_id: str) -> dict:
    name = fm.get("repo_name") or path.parent.name
    return {
        "id": node_id,
        "label": name,
        "file_type": "document",
        "source_file": _rel(path, root),
        "source_location": "L1",
        "default_branch": fm.get("default_branch", ""),
        "head_sha": fm.get("head_sha", ""),
        "source_url": fm.get("source_url", ""),
    }


def _edge(**kw: Any) -> dict:
    return kw


# ---------------------------------------------------------------- parsing


_KV_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")
_QUOTED_RE = re.compile(r'"((?:\\.|[^"\\])*)"')


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse the subset of YAML frontmatter that `_yaml_str`/`_yaml_list` emit."""
    if not text.startswith("---"):
        return {}
    lines = text.split("\n")
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    out: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KV_RE.match(line)
        if not m:
            continue
        out[m.group(1)] = _parse_value(m.group(2).strip())
    return out


def _parse_value(raw: str) -> Any:
    if raw.startswith("[") and raw.endswith("]"):
        return [_unescape(s) for s in _QUOTED_RE.findall(raw)]
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        return _unescape(raw[1:-1])
    return raw


def _unescape(s: str) -> str:
    # Reverse of _yaml_str: it escapes backslash and double-quote.
    return s.replace('\\"', '"').replace("\\\\", "\\")


# ---------------------------------------------------------------- utils


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_id(name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", name).strip("_") or "repo"


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [s for s in v if isinstance(s, str)]
    if isinstance(v, str) and v:
        return [v]
    return []


def _repo_name_from_ref(ref: str, kind: str) -> str:
    """Pull the repo name out of a related_{commits,prs,branches} payload.

    Formats (see azure_devops._parse_artifact_link):
      commits  -> "{repo}@{sha7}"
      prs      -> "{repo}#{id}"
      branches -> "{repo}:{branch}"
    """
    sep = {"commits": "@", "prs": "#", "branches": ":"}.get(kind)
    if sep and sep in ref:
        return ref.split(sep, 1)[0]
    return ref
