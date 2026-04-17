from __future__ import annotations

import atexit
import hashlib
import json
import os
import threading
from pathlib import Path


_INDEX_NAME = "index.json"
_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: dict[Path, dict[str, dict]] = {}
_INDEX_DIRTY: set[Path] = set()


def _index_path(cdir: Path) -> Path:
    return cdir / _INDEX_NAME


def _load_index(cdir: Path) -> dict[str, dict]:
    """Return the in-memory index for *cdir*, loading from disk on first access."""
    with _INDEX_LOCK:
        if cdir in _INDEX_CACHE:
            return _INDEX_CACHE[cdir]
        p = _index_path(cdir)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, json.JSONDecodeError):
            data = {}
        _INDEX_CACHE[cdir] = data
        return data


def _save_index(cdir: Path) -> None:
    with _INDEX_LOCK:
        if cdir not in _INDEX_DIRTY:
            return
        data = _INDEX_CACHE.get(cdir, {})
        p = _index_path(cdir)
        tmp = p.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, p)
        except OSError:
            tmp.unlink(missing_ok=True)
            return
        _INDEX_DIRTY.discard(cdir)


def _index_key(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(Path(path).resolve())


def _index_lookup(path: Path, root: Path) -> str | None:
    """Return the cached hash for *path* if mtime+size still match; else None.

    This is the fast path that avoids reading + hashing the whole file.
    """
    try:
        st = path.stat()
    except OSError:
        return None
    cdir = cache_dir(root)
    data = _load_index(cdir)
    entry = data.get(_index_key(path, root))
    if entry is None:
        return None
    if entry.get("mtime_ns") == st.st_mtime_ns and entry.get("size") == st.st_size:
        h = entry.get("hash")
        return h if isinstance(h, str) else None
    return None


def _index_update(path: Path, root: Path, h: str) -> None:
    """Record (mtime_ns, size, hash) for *path* so the next run can fast-path."""
    try:
        st = path.stat()
    except OSError:
        return
    cdir = cache_dir(root)
    data = _load_index(cdir)
    key = _index_key(path, root)
    with _INDEX_LOCK:
        data[key] = {
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
            "hash": h,
        }
        _INDEX_DIRTY.add(cdir)


def flush_cache_index() -> None:
    """Persist any pending cache-index updates to disk. Idempotent; thread-safe."""
    with _INDEX_LOCK:
        dirty = list(_INDEX_DIRTY)
    for d in dirty:
        _save_index(d)


atexit.register(flush_cache_index)


def _body_content(content: bytes) -> bytes:
    """Strip YAML frontmatter from Markdown content, returning only the body."""
    text = content.decode(errors="replace")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].encode()
    return content


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """SHA256 of file contents + path relative to root.

    Using a relative path (not absolute) makes cache entries portable across
    machines and checkout directories, so shared caches and CI work correctly.
    Falls back to the resolved absolute path if the file is outside root.

    For Markdown files (.md), only the body below the YAML frontmatter is hashed,
    so metadata-only changes (e.g. reviewed, status, tags) do not invalidate the cache.
    """
    p = Path(path)
    raw = p.read_bytes()
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    h = hashlib.sha256()
    h.update(content)
    h.update(b"\x00")
    try:
        rel = p.resolve().relative_to(Path(root).resolve())
        h.update(str(rel).encode())
    except ValueError:
        h.update(str(p.resolve()).encode())
    return h.hexdigest()


def cache_dir(root: Path = Path(".")) -> Path:
    """Returns the cache/ subdir under the resolved aikgraph-out/ - creates it if needed."""
    from aikgraph.utils.paths import resolve_out_dir

    d = resolve_out_dir(root) / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cached(path: Path, root: Path = Path(".")) -> dict | None:
    """Return cached extraction for this file if hash matches, else None.

    Fast path: if (mtime_ns, size) in the index matches the file, reuse the
    stored hash without reading file contents. Otherwise hash the file and
    update the index so the next call is fast.

    Cache value: stored as <cache_dir>/{hash}.json.
    Returns None if no cache entry or file has changed.
    """
    h = _index_lookup(path, root)
    if h is None:
        try:
            h = file_hash(path, root)
        except OSError:
            return None
        _index_update(path, root, h)
    entry = cache_dir(root) / f"{h}.json"
    if not entry.exists():
        return None
    try:
        return json.loads(entry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cached(path: Path, result: dict, root: Path = Path(".")) -> None:
    """Save extraction result for this file.

    Stores as <cache_dir>/{hash}.json where hash = SHA256 of current file contents.
    Updates the mtime/size index so subsequent runs can skip hashing.
    result should be a dict with 'nodes' and 'edges' lists.
    """
    h = file_hash(path, root)
    _index_update(path, root, h)
    entry = cache_dir(root) / f"{h}.json"
    tmp = entry.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(result), encoding="utf-8")
        os.replace(tmp, entry)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def cached_files(root: Path = Path(".")) -> set[str]:
    """Return set of file paths that have a valid cache entry (hash still matches)."""
    d = cache_dir(root)
    return {p.stem for p in d.glob("*.json") if p.name != _INDEX_NAME}


def clear_cache(root: Path = Path(".")) -> None:
    """Delete all cache entries (keyed JSON blobs) and the mtime/size index."""
    d = cache_dir(root)
    for f in d.glob("*.json"):
        f.unlink()
    with _INDEX_LOCK:
        _INDEX_CACHE.pop(d, None)
        _INDEX_DIRTY.discard(d)


def check_semantic_cache(
    files: list[str],
    root: Path = Path("."),
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Check semantic extraction cache for a list of absolute file paths.

    Returns (cached_nodes, cached_edges, cached_hyperedges, uncached_files).
    Uncached files need Claude extraction; cached files are merged directly.
    """
    cached_nodes: list[dict] = []
    cached_edges: list[dict] = []
    cached_hyperedges: list[dict] = []
    uncached: list[str] = []

    for fpath in files:
        result = load_cached(Path(fpath), root)
        if result is not None:
            cached_nodes.extend(result.get("nodes", []))
            cached_edges.extend(result.get("edges", []))
            cached_hyperedges.extend(result.get("hyperedges", []))
        else:
            uncached.append(fpath)

    return cached_nodes, cached_edges, cached_hyperedges, uncached


def save_semantic_cache(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
    root: Path = Path("."),
) -> int:
    """Save semantic extraction results to cache, keyed by source_file.

    Groups nodes and edges by source_file, then saves one cache entry per file.
    Returns the number of files cached.
    """
    from collections import defaultdict

    by_file: dict[str, dict] = defaultdict(
        lambda: {"nodes": [], "edges": [], "hyperedges": []}
    )
    for n in nodes:
        src = n.get("source_file", "")
        if src:
            by_file[src]["nodes"].append(n)
    for e in edges:
        src = e.get("source_file", "")
        if src:
            by_file[src]["edges"].append(e)
    for h in hyperedges or []:
        src = h.get("source_file", "")
        if src:
            by_file[src]["hyperedges"].append(h)

    saved = 0
    for fpath, result in by_file.items():
        p = Path(fpath)
        if not p.is_absolute():
            p = Path(root) / p
        if p.exists():
            save_cached(p, result, root)
            saved += 1
    return saved
