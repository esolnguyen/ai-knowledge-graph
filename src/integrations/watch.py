# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import json
import time
from pathlib import Path


from aikgraph.extraction.detect import (
    CODE_EXTENSIONS,
    DOC_EXTENSIONS,
    PAPER_EXTENSIONS,
    IMAGE_EXTENSIONS,
)

_WATCHED_EXTENSIONS = (
    CODE_EXTENSIONS | DOC_EXTENSIONS | PAPER_EXTENSIONS | IMAGE_EXTENSIONS
)
_CODE_EXTENSIONS = CODE_EXTENSIONS


def _merge_semantic_extract(
    result: dict, extract_path: Path, *, log_prefix: str = "[aikgraph update]"
) -> dict:
    """Merge a freshly-produced semantic extract (.aikgraph_extract.json) into *result*.

    New semantic nodes/edges from the extract take precedence over anything with
    the same id already in *result*. Returns the merged dict.
    """
    try:
        sem = json.loads(extract_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"{log_prefix} Failed to read {extract_path}: {exc}")
        return result

    existing_ids = {n["id"] for n in result.get("nodes", [])}
    new_nodes = [n for n in sem.get("nodes", []) if n["id"] not in existing_ids]
    merged = {
        "nodes": result.get("nodes", []) + new_nodes,
        "edges": result.get("edges", []) + sem.get("edges", []),
        "hyperedges": result.get("hyperedges", []) + sem.get("hyperedges", []),
        "input_tokens": result.get("input_tokens", 0) + sem.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0) + sem.get("output_tokens", 0),
    }
    print(
        f"{log_prefix} Merged {extract_path.name}: "
        f"+{len(new_nodes)} nodes, +{len(sem.get('edges', []))} edges, "
        f"+{len(sem.get('hyperedges', []))} hyperedges"
    )
    return merged


def _rebuild_code(
    watch_path: Path,
    *,
    follow_symlinks: bool = False,
    obsidian: bool = False,
    html: bool = False,
    svg: bool = False,
    semantic_extract: Path | None = None,
) -> bool:
    """Re-run AST extraction + build + cluster + report for code files. No LLM needed.

    If *semantic_extract* (default: ``.aikgraph_extract.json`` in CWD) exists, its
    nodes/edges are merged in before the existing-graph merge. This is how the
    agent pipeline hands freshly-extracted doc/paper/image data back to the CLI.

    Returns True on success, False on error.
    """
    try:
        from aikgraph.extraction.extract import extract
        from aikgraph.extraction.detect import detect
        from aikgraph.core.build import build_from_json
        from aikgraph.core.cluster import cluster, score_all
        from aikgraph.core.analyze import (
            god_nodes,
            surprising_connections,
            suggest_questions,
        )
        from aikgraph.output.report import generate
        from aikgraph.output.json_export import to_json

        detected = detect(
            watch_path, follow_symlinks=follow_symlinks, corpus_stats=False
        )
        code_files = [Path(f) for f in detected["files"]["code"]]

        if not code_files:
            print("[aikgraph watch] No code files found - nothing to rebuild.")
            return False

        result = extract(code_files, root=watch_path)

        # Fold in any Azure DevOps sync output (workitem_*.md, _repo.md under
        # raw/azure/). Does nothing when that directory is absent, so local
        # rebuilds that never ran `aikgraph update --project ...` are unaffected.
        from aikgraph.integrations.azure_extract import (
            extract_azure,
            link_repos_to_code,
        )

        azure = extract_azure(watch_path)
        if azure["nodes"]:
            repo_code_edges = link_repos_to_code(azure["nodes"], result["nodes"])
            result = {
                "nodes": result["nodes"] + azure["nodes"],
                "edges": result["edges"] + azure["edges"] + repo_code_edges,
                "hyperedges": result.get("hyperedges", []),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
            }
            print(
                f"[aikgraph update] Azure sync: +{len(azure['nodes'])} nodes, "
                f"+{len(azure['edges'])} work-item edges, "
                f"+{len(repo_code_edges)} repo->code edges"
            )

        # Merge any freshly-produced semantic extract from the agent pipeline.
        extract_path = semantic_extract or Path(".aikgraph_extract.json")
        if extract_path.exists():
            result = _merge_semantic_extract(result, extract_path)

        # Preserve semantic nodes/edges from a previous full run.
        # AST-only rebuild replaces code nodes; doc/paper/image nodes are kept.
        from aikgraph.utils.paths import resolve_out_dir

        out = resolve_out_dir(watch_path)
        existing_graph = out / "graph.json"
        if existing_graph.exists():
            try:
                existing = json.loads(existing_graph.read_text(encoding="utf-8"))
                code_ids = {
                    n["id"]
                    for n in existing.get("nodes", [])
                    if n.get("file_type") == "code"
                }
                # Drop stale azure nodes from the previous graph — we just
                # re-extracted them above and their attrs should win.
                fresh_ids = {n["id"] for n in result["nodes"]}
                sem_nodes = [
                    n for n in existing.get("nodes", [])
                    if n.get("file_type") != "code" and n["id"] not in fresh_ids
                ]
                sem_edges = [
                    e
                    for e in existing.get("links", existing.get("edges", []))
                    if e.get("confidence") in ("INFERRED", "AMBIGUOUS")
                    or (
                        e.get("source") not in code_ids
                        and e.get("target") not in code_ids
                    )
                ]
                result = {
                    "nodes": result["nodes"] + sem_nodes,
                    "edges": result["edges"] + sem_edges,
                    "hyperedges": existing.get("hyperedges", []),
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            except Exception:
                pass  # corrupt graph.json - proceed with AST-only

        detection = {
            "files": {
                "code": [str(f) for f in code_files],
                "document": [],
                "paper": [],
                "image": [],
            },
            "total_files": len(code_files),
            "total_words": detected.get("total_words", 0),
        }

        G = build_from_json(result)
        communities = cluster(G)
        cohesion = score_all(G, communities)
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        labels = {cid: "Community " + str(cid) for cid in communities}
        questions = suggest_questions(G, communities, labels)

        out.mkdir(exist_ok=True)

        report = generate(
            G,
            communities,
            cohesion,
            labels,
            gods,
            surprises,
            detection,
            {"input": 0, "output": 0},
            str(watch_path),
            suggested_questions=questions,
        )
        (out / "REPORT.md").write_text(report, encoding="utf-8")
        to_json(G, communities, str(out / "graph.json"))

        if obsidian:
            from aikgraph.output.obsidian import to_obsidian, to_canvas

            vault_dir = out / "obsidian"
            n_notes = to_obsidian(
                G,
                communities,
                str(vault_dir),
                community_labels=labels,
                cohesion=cohesion,
            )
            to_canvas(
                G, communities, str(vault_dir / "graph.canvas"), community_labels=labels
            )
            print(f"[aikgraph watch] Obsidian vault: {n_notes} notes in {vault_dir}")

        if html:
            try:
                from aikgraph.output.html import to_html

                html_path = out / "graph.html"
                to_html(G, communities, str(html_path), community_labels=labels)
                print(f"[aikgraph watch] HTML: {html_path}")
            except ValueError as exc:
                print(f"[aikgraph watch] HTML skipped: {exc}")
            except Exception as exc:
                print(f"[aikgraph watch] HTML failed: {exc}")

        if svg:
            try:
                from aikgraph.output.svg import to_svg

                svg_path = out / "graph.svg"
                to_svg(G, communities, str(svg_path), community_labels=labels)
                print(f"[aikgraph watch] SVG: {svg_path}")
            except ImportError as exc:
                print(f"[aikgraph watch] SVG skipped: {exc}")
            except Exception as exc:
                print(f"[aikgraph watch] SVG failed: {exc}")

        # clear stale needs_update flag if present
        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        print(
            f"[aikgraph watch] Rebuilt: {G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges, {len(communities)} communities"
        )
        print(f"[aikgraph watch] graph.json and REPORT.md updated in {out}")
        return True

    except Exception as exc:
        print(f"[aikgraph watch] Rebuild failed: {exc}")
        return False


def _notify_only(watch_path: Path) -> None:
    """Write a flag file and print a notification (fallback for non-code-only corpora)."""
    from aikgraph.utils.paths import resolve_out_dir

    flag = resolve_out_dir(watch_path) / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
    print(f"\n[aikgraph watch] New or changed files detected in {watch_path}")
    print(
        "[aikgraph watch] Non-code files changed - semantic re-extraction requires LLM."
    )
    print(
        "[aikgraph watch] Run `aikgraph update` to update the graph."
    )
    print(f"[aikgraph watch] Flag written to {flag}")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(p.suffix.lower() not in _CODE_EXTENSIONS for p in changed_paths)


def watch(watch_path: Path, debounce: float = 3.0) -> None:
    """
    Watch watch_path for new or modified files and auto-update the graph.

    For code-only changes: re-runs AST extraction + rebuild immediately (no LLM).
    For doc/paper/image changes: writes a needs_update flag and notifies the user
    to run `aikgraph update` (LLM extraction required).

    debounce: seconds to wait after the last change before triggering (avoids
    running on every keystroke when many files are saved at once).
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError as e:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from e

    last_trigger: float = 0.0
    pending: bool = False
    changed: set[Path] = set()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            if any(part.startswith(".") for part in path.parts):
                return
            if "aikgraph-out" in path.parts:
                return
            last_trigger = time.monotonic()
            pending = True
            changed.add(path)

    handler = Handler()
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    print(f"[aikgraph watch] Watching {watch_path.resolve()} - press Ctrl+C to stop")
    print(
        f"[aikgraph watch] Code changes rebuild graph automatically. "
        f"Doc/image changes require `aikgraph update`."
    )
    print(f"[aikgraph watch] Debounce: {debounce}s")

    try:
        while True:
            time.sleep(0.5)
            if pending and (time.monotonic() - last_trigger) >= debounce:
                pending = False
                batch = list(changed)
                changed.clear()
                print(f"\n[aikgraph watch] {len(batch)} file(s) changed")
                if _has_non_code(batch):
                    _notify_only(watch_path)
                else:
                    _rebuild_code(watch_path)
    except KeyboardInterrupt:
        print("\n[aikgraph watch] Stopped.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Watch a folder and auto-update the aikgraph graph"
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="Folder to watch (default: .)"
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=3.0,
        help="Seconds to wait after last change before updating (default: 3)",
    )
    args = parser.parse_args()
    watch(Path(args.path), debounce=args.debounce)
