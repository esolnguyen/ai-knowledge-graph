"""Non-install subcommands: query, path, explain, add, watch, update, cluster-only, benchmark, save-result, hook."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def cmd_query(argv: list[str]) -> None:
    if len(argv) < 1:
        print(
            'Usage: aikgraph query "<question>" [--dfs] [--budget N] [--graph path]',
            file=sys.stderr,
        )
        sys.exit(1)
    from aikgraph.integrations.serve import (
        _score_nodes,
        _bfs,
        _dfs,
        _subgraph_to_text,
    )
    from networkx.readwrite import json_graph

    question = argv[0]
    use_dfs = "--dfs" in argv
    budget = 2000
    graph_path = "aikgraph-out/graph.json"
    rest = argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--budget" and i + 1 < len(rest):
            try:
                budget = int(rest[i + 1])
            except ValueError:
                print("error: --budget must be an integer", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif rest[i].startswith("--budget="):
            try:
                budget = int(rest[i].split("=", 1)[1])
            except ValueError:
                print("error: --budget must be an integer", file=sys.stderr)
                sys.exit(1)
            i += 1
        elif rest[i] == "--graph" and i + 1 < len(rest):
            graph_path = rest[i + 1]
            i += 2
        else:
            i += 1
    gp = Path(graph_path).resolve()
    if not gp.exists():
        print(f"error: graph file not found: {gp}", file=sys.stderr)
        sys.exit(1)
    if gp.suffix != ".json":
        print("error: graph file must be a .json file", file=sys.stderr)
        sys.exit(1)
    try:
        raw = json.loads(gp.read_text(encoding="utf-8"))
        try:
            G = json_graph.node_link_graph(raw, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(raw)
    except Exception as exc:
        print(f"error: could not load graph: {exc}", file=sys.stderr)
        sys.exit(1)
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scored = _score_nodes(G, terms)
    if not scored:
        print("No matching nodes found.")
        sys.exit(0)
    start = [nid for _, nid in scored[:5]]
    nodes, edges = (_dfs if use_dfs else _bfs)(G, start, depth=2)
    print(_subgraph_to_text(G, nodes, edges, token_budget=budget))


def cmd_save_result(argv: list[str]) -> None:
    import argparse

    p = argparse.ArgumentParser(prog="aikgraph save-result")
    p.add_argument("--question", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--type", dest="query_type", default="query")
    p.add_argument("--nodes", nargs="*", default=[])
    p.add_argument("--memory-dir", default="aikgraph-out/memory")
    opts = p.parse_args(argv)
    from aikgraph.extraction.ingest import save_query_result

    out = save_query_result(
        question=opts.question,
        answer=opts.answer,
        memory_dir=Path(opts.memory_dir),
        query_type=opts.query_type,
        source_nodes=opts.nodes or None,
    )
    print(f"Saved to {out}")


def cmd_path(argv: list[str]) -> None:
    if len(argv) < 2:
        print(
            'Usage: aikgraph path "<source>" "<target>" [--graph path]',
            file=sys.stderr,
        )
        sys.exit(1)
    from aikgraph.integrations.serve import _score_nodes
    from networkx.readwrite import json_graph
    import networkx as nx

    source_label = argv[0]
    target_label = argv[1]
    graph_path = "aikgraph-out/graph.json"
    rest = argv[2:]
    for i, a in enumerate(rest):
        if a == "--graph" and i + 1 < len(rest):
            graph_path = rest[i + 1]
    gp = Path(graph_path).resolve()
    if not gp.exists():
        print(f"error: graph file not found: {gp}", file=sys.stderr)
        sys.exit(1)
    raw = json.loads(gp.read_text(encoding="utf-8"))
    try:
        G = json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(raw)
    src_scored = _score_nodes(G, [t.lower() for t in source_label.split()])
    tgt_scored = _score_nodes(G, [t.lower() for t in target_label.split()])
    if not src_scored:
        print(f"No node matching '{source_label}' found.", file=sys.stderr)
        sys.exit(1)
    if not tgt_scored:
        print(f"No node matching '{target_label}' found.", file=sys.stderr)
        sys.exit(1)
    src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
    try:
        path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        print(f"No path found between '{source_label}' and '{target_label}'.")
        sys.exit(0)
    hops = len(path_nodes) - 1
    segments = []
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        edata = G.edges[u, v]
        rel = edata.get("relation", "")
        conf = edata.get("confidence", "")
        conf_str = f" [{conf}]" if conf else ""
        if i == 0:
            segments.append(G.nodes[u].get("label", u))
        segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
    print(f"Shortest path ({hops} hops):\n  " + " ".join(segments))


def cmd_explain(argv: list[str]) -> None:
    if len(argv) < 1:
        print('Usage: aikgraph explain "<node>" [--graph path]', file=sys.stderr)
        sys.exit(1)
    from aikgraph.integrations.serve import _find_node
    from networkx.readwrite import json_graph

    label = argv[0]
    graph_path = "aikgraph-out/graph.json"
    rest = argv[1:]
    for i, a in enumerate(rest):
        if a == "--graph" and i + 1 < len(rest):
            graph_path = rest[i + 1]
    gp = Path(graph_path).resolve()
    if not gp.exists():
        print(f"error: graph file not found: {gp}", file=sys.stderr)
        sys.exit(1)
    raw = json.loads(gp.read_text(encoding="utf-8"))
    try:
        G = json_graph.node_link_graph(raw, edges="links")
    except TypeError:
        G = json_graph.node_link_graph(raw)
    matches = _find_node(G, label)
    if not matches:
        print(f"No node matching '{label}' found.")
        sys.exit(0)
    nid = matches[0]
    d = G.nodes[nid]
    print(f"Node: {d.get('label', nid)}")
    print(f"  ID:        {nid}")
    print(
        f"  Source:    {d.get('source_file', '')} {d.get('source_location', '')}".rstrip()
    )
    print(f"  Type:      {d.get('file_type', '')}")
    print(f"  Community: {d.get('community', '')}")
    print(f"  Degree:    {G.degree(nid)}")
    neighbors = list(G.neighbors(nid))
    if neighbors:
        print(f"\nConnections ({len(neighbors)}):")
        for nb in sorted(neighbors, key=lambda n: G.degree(n), reverse=True)[:20]:
            edata = G.edges[nid, nb]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            print(f"  --> {G.nodes[nb].get('label', nb)} [{rel}] [{conf}]")
        if len(neighbors) > 20:
            print(f"  ... and {len(neighbors) - 20} more")


def cmd_add(argv: list[str]) -> None:
    if len(argv) < 1:
        print(
            "Usage: aikgraph add <url> [--author Name] [--contributor Name] [--dir ./raw]",
            file=sys.stderr,
        )
        sys.exit(1)
    from aikgraph.extraction.ingest import ingest

    url = argv[0]
    author: str | None = None
    contributor: str | None = None
    target_dir = Path("raw")
    rest = argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--author" and i + 1 < len(rest):
            author = rest[i + 1]
            i += 2
        elif rest[i] == "--contributor" and i + 1 < len(rest):
            contributor = rest[i + 1]
            i += 2
        elif rest[i] == "--dir" and i + 1 < len(rest):
            target_dir = Path(rest[i + 1])
            i += 2
        else:
            i += 1
    try:
        saved = ingest(url, target_dir, author=author, contributor=contributor)
        print(f"Saved to {saved}")
        print("Run /aikgraph --update in your AI assistant to update the graph.")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_watch(argv: list[str]) -> None:
    watch_path = Path(argv[0]) if argv else Path(".")
    if not watch_path.exists():
        print(f"error: path not found: {watch_path}", file=sys.stderr)
        sys.exit(1)
    from aikgraph.integrations.watch import watch as _watch

    try:
        _watch(watch_path)
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_cluster_only(argv: list[str]) -> None:
    watch_path = Path(argv[0]) if argv else Path(".")
    graph_json = watch_path / "aikgraph-out" / "graph.json"
    if not graph_json.exists():
        print(
            f"error: no graph found at {graph_json} — run /aikgraph first",
            file=sys.stderr,
        )
        sys.exit(1)
    from aikgraph.core.build import build_from_json
    from aikgraph.core.cluster import cluster, score_all
    from aikgraph.core.analyze import (
        god_nodes,
        surprising_connections,
        suggest_questions,
    )
    from aikgraph.output.report import generate
    from aikgraph.output.json_export import to_json

    print("Loading existing graph...")
    raw = json.loads(graph_json.read_text(encoding="utf-8"))
    G = build_from_json(raw)
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print("Re-clustering...")
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels)
    tokens = {"input": 0, "output": 0}
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        {},
        tokens,
        str(watch_path),
        suggested_questions=questions,
    )
    out = watch_path / "aikgraph-out"
    (out / "REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(out / "graph.json"))
    print(f"Done — {len(communities)} communities. REPORT.md and graph.json updated.")


def cmd_update(argv: list[str]) -> None:
    obsidian = "--obsidian" in argv
    positional = [a for a in argv if not a.startswith("--")]
    watch_path = Path(positional[0]) if positional else Path(".")
    if not watch_path.exists():
        print(f"error: path not found: {watch_path}", file=sys.stderr)
        sys.exit(1)
    from aikgraph.integrations.watch import _rebuild_code

    print(f"Re-extracting code files in {watch_path} (no LLM needed)...")
    ok = _rebuild_code(watch_path, obsidian=obsidian)
    if ok:
        print(
            "Code graph updated. For doc/paper/image changes run /aikgraph --update in your AI assistant."
        )
    else:
        print("Nothing to update or rebuild failed — check output above.")


def cmd_benchmark(argv: list[str]) -> None:
    from aikgraph.integrations.benchmark import run_benchmark, print_benchmark

    graph_path = argv[0] if argv else "aikgraph-out/graph.json"
    corpus_words = None
    detect_path = Path(".aikgraph_detect.json")
    if detect_path.exists():
        try:
            detect_data = json.loads(detect_path.read_text(encoding="utf-8"))
            corpus_words = detect_data.get("total_words")
        except Exception:
            pass
    result = run_benchmark(graph_path, corpus_words=corpus_words)
    print_benchmark(result)


def cmd_hook(argv: list[str]) -> None:
    from aikgraph.integrations.hooks import (
        install as hook_install,
        uninstall as hook_uninstall,
        status as hook_status,
    )

    subcmd = argv[0] if argv else ""
    if subcmd == "install":
        print(hook_install(Path(".")))
    elif subcmd == "uninstall":
        print(hook_uninstall(Path(".")))
    elif subcmd == "status":
        print(hook_status(Path(".")))
    else:
        print("Usage: aikgraph hook [install|uninstall|status]", file=sys.stderr)
        sys.exit(1)
