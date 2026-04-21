"""Azure DevOps -> aikgraph connector.

Fetches work items and repository metadata for an Azure DevOps project
and writes them as markdown files with YAML frontmatter under a corpus
directory. Optionally clones each repo's default branch (shallow) so
the code ends up in the same corpus and the normal AST extractor can
build cross-links between PBIs/bugs/epics and real code symbols.

Stdlib only (urllib + subprocess for git). Entry point: `sync(...)`.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from aikgraph.extraction.ingest import _safe_filename, _yaml_str


API_VERSION = "7.1"
DEFAULT_LOOKBACK_DAYS = 365
WORKITEM_BATCH_SIZE = 200
HTTP_TIMEOUT = 30
MAX_RETRIES = 3
STATE_FILENAME = ".azure_sync_state.json"
WIQL_SIZE_LIMIT_MARKER = "WorkItemTrackingQueryResultSizeLimitExceededException"


# ---------------------------------------------------------------- HTTP


class _AzureHTTPError(RuntimeError):
    """HTTPError wrapper carrying status code and response body for callers
    that need to branch on specific Azure DevOps error codes."""

    def __init__(self, message: str, *, status: int, body: str) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def _auth_header(pat: str) -> dict[str, str]:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _request_json(
    url: str,
    headers: dict[str, str],
    *,
    method: str = "GET",
    body: dict | None = None,
) -> Any:
    data: bytes | None = None
    req_headers = dict(headers)
    req_headers.setdefault("Accept", "application/json")
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt + 1 < MAX_RETRIES:
                retry_after = exc.headers.get("Retry-After", "5")
                try:
                    delay = min(int(retry_after), 60)
                except ValueError:
                    delay = 5
                print(f"[azure] rate-limited; sleeping {delay}s")
                time.sleep(delay)
                last_exc = exc
                continue
            # Include response body for easier debugging (without PAT).
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:
                detail = ""
            raise _AzureHTTPError(
                f"azure API {method} {_redact(url)} failed: HTTP {exc.code} {detail}",
                status=exc.code,
                body=detail,
            ) from exc
        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt + 1 < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(
                f"azure API {method} {_redact(url)} failed: {exc.reason}"
            ) from exc

    raise RuntimeError(f"azure API {method} {_redact(url)} failed after retries: {last_exc}")


def _get_json(url: str, headers: dict[str, str]) -> Any:
    return _request_json(url, headers, method="GET")


def _post_json(url: str, body: dict, headers: dict[str, str]) -> Any:
    return _request_json(url, headers, method="POST", body=body)


def _redact(url: str) -> str:
    return re.sub(r"(https?://)[^@/]+@", r"\1<redacted>@", url)


# ---------------------------------------------------------------- state


def _load_state(target_dir: Path) -> dict:
    path = target_dir / STATE_FILENAME
    if not path.exists():
        return {"work_items": {}, "repos": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"work_items": {}, "repos": {}}
    state.setdefault("work_items", {})
    state.setdefault("repos", {})
    return state


def _save_state(target_dir: Path, state: dict) -> None:
    path = target_dir / STATE_FILENAME
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _resolve_since(state: dict, since_arg: str | None, full: bool) -> str | None:
    """Return the WIQL cutoff date as YYYY-MM-DD, or None to mean 'no cutoff'.

    Precedence: ``full`` beats ``since_arg`` beats stored cursor beats the
    default 365-day lookback. ``full=True`` drops the date filter entirely so
    a rescan picks up work items older than the default lookback window.
    """
    if full:
        return None
    if since_arg:
        _validate_iso_date(since_arg)
        return since_arg
    cursor = state.get("work_items", {}).get("last_changed_date")
    if cursor:
        # WIQL accepts 'YYYY-MM-DD' or ISO datetime; use what's stored.
        return cursor
    return _days_ago(DEFAULT_LOOKBACK_DAYS)


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _validate_iso_date(s: str) -> None:
    if not re.match(r"^\d{4}-\d{2}-\d{2}(T.*)?$", s):
        raise ValueError(f"--since must be YYYY-MM-DD (got {s!r})")


# ---------------------------------------------------------------- fetch


def _fetch_work_items(
    org: str, project: str, since: str | None, headers: dict[str, str]
) -> list[dict]:
    """WIQL query for IDs, then batch-hydrate with $expand=relations.

    Azure DevOps caps WIQL results at 20,000 items. We query half-open
    ``[lo, hi)`` windows on ``System.ChangedDate`` and bisect any window
    that trips the cap. ``since=None`` scans from a 1970 sentinel (used by
    ``--full``).
    """
    base = f"https://dev.azure.com/{urllib.parse.quote(org)}/{urllib.parse.quote(project)}/_apis"
    wiql_url = f"{base}/wit/wiql?api-version={API_VERSION}"

    lo_initial = since or "1970-01-01"
    # hi is exclusive; add a day so items changed today aren't excluded.
    hi_initial = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    all_ids: list[int] = []
    stack: list[tuple[str, str]] = [(lo_initial, hi_initial)]
    while stack:
        lo, hi = stack.pop()
        try:
            ids = _wiql_ids_in_window(wiql_url, lo, hi, headers)
        except _AzureHTTPError as exc:
            if exc.status == 400 and WIQL_SIZE_LIMIT_MARKER in exc.body:
                mid = _midpoint_date(lo, hi)
                if mid is None:
                    raise RuntimeError(
                        f"azure sync: >20000 work items share ChangedDate "
                        f"[{lo}, {hi}); cannot subdivide further"
                    ) from exc
                print(f"[azure] window [{lo}..{hi}) > 20000 items; splitting at {mid}")
                # LIFO order so we process the earlier half first.
                stack.append((mid, hi))
                stack.append((lo, mid))
                continue
            raise
        all_ids.extend(ids)

    if not all_ids:
        return []

    # Dedup defensively (boundary items are excluded on the hi side, but
    # belt-and-suspenders in case of timezone quirks).
    seen: set[int] = set()
    unique_ids: list[int] = []
    for wid in all_ids:
        if wid not in seen:
            seen.add(wid)
            unique_ids.append(wid)

    print(f"[azure] work items to hydrate: {len(unique_ids)}")
    hydrated: list[dict] = []
    for chunk in _chunks(unique_ids, WORKITEM_BATCH_SIZE):
        batch_url = f"{base}/wit/workitemsbatch?api-version={API_VERSION}"
        batch_body = {"ids": chunk, "$expand": "relations"}
        data = _post_json(batch_url, batch_body, headers)
        hydrated.extend(data.get("value", []))
    return hydrated


def _wiql_ids_in_window(
    wiql_url: str, lo: str, hi: str, headers: dict[str, str]
) -> list[int]:
    wiql_body = {
        "query": (
            "SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.ChangedDate] >= '{lo}' "
            f"AND [System.ChangedDate] < '{hi}' "
            "ORDER BY [System.ChangedDate] ASC"
        )
    }
    resp = _post_json(wiql_url, wiql_body, headers)
    return [row["id"] for row in resp.get("workItems", [])]


def _parse_window_date(s: str) -> datetime:
    s = s.strip()
    if "T" not in s:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    normalized = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _midpoint_date(lo: str, hi: str) -> str | None:
    """Midpoint between two WIQL date strings, or None if the window can no
    longer be subdivided. Returns ``YYYY-MM-DD`` when the span is at least
    two days, otherwise an ISO datetime with second precision."""
    lo_dt = _parse_window_date(lo)
    hi_dt = _parse_window_date(hi)
    delta = hi_dt - lo_dt
    if delta.total_seconds() <= 1:
        return None
    mid_dt = lo_dt + delta / 2
    if delta.days >= 2:
        return mid_dt.strftime("%Y-%m-%d")
    return mid_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_repos(org: str, project: str, headers: dict[str, str]) -> list[dict]:
    base = f"https://dev.azure.com/{urllib.parse.quote(org)}/{urllib.parse.quote(project)}/_apis"
    url = f"{base}/git/repositories?api-version={API_VERSION}"
    data = _get_json(url, headers)
    return data.get("value", [])


def _chunks(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


# ---------------------------------------------------------------- artifact links


_ARTIFACT_RE = re.compile(r"vstfs:///Git/(Commit|PullRequestId|Ref)/(.+)", re.IGNORECASE)


def _parse_artifact_link(
    uri: str, repo_id_to_name: dict[str, str]
) -> tuple[str, str] | None:
    """Parse a vstfs:// ArtifactLink URI into (kind, human-readable-id) or None."""
    m = _ARTIFACT_RE.match(uri)
    if not m:
        return None
    kind_raw, payload = m.group(1), m.group(2)
    # Azure encodes as "<projectGuid>%2F<repoGuid>%2F<identifier>". For branch
    # refs, the identifier can itself contain encoded slashes, so preserve
    # anything after the second %2F as the identifier.
    raw_parts = payload.split("%2F", 2)
    if len(raw_parts) < 3:
        raw_parts = payload.split("/", 2)
    if len(raw_parts) < 3:
        return None
    repo_id = urllib.parse.unquote(raw_parts[1]).lower()
    identifier = urllib.parse.unquote(raw_parts[2])
    repo_name = repo_id_to_name.get(repo_id, repo_id[:8])

    kind = kind_raw.lower()
    if kind == "commit":
        short = identifier[:7]
        return ("commit", f"{repo_name}@{short}")
    if kind == "pullrequestid":
        return ("pr", f"{repo_name}#{identifier}")
    if kind == "ref":
        branch = identifier
        if branch.startswith("GB"):
            branch = branch[2:]
        branch = branch.lstrip("/")
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/") :]
        return ("branch", f"{repo_name}:{branch}")
    return None


def _parse_workitem_relations(
    wi: dict, repo_id_to_name: dict[str, str]
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "parent_id": None,
        "related_ids": [],
        "related_commits": [],
        "related_prs": [],
        "related_branches": [],
    }
    for rel in wi.get("relations", []) or []:
        rel_type = rel.get("rel", "")
        url = rel.get("url", "")
        if rel_type == "System.LinkTypes.Hierarchy-Reverse":
            wid = _extract_workitem_id(url)
            if wid:
                out["parent_id"] = wid
        elif rel_type in (
            "System.LinkTypes.Hierarchy-Forward",
            "System.LinkTypes.Related",
        ):
            wid = _extract_workitem_id(url)
            if wid:
                out["related_ids"].append(wid)
        elif rel_type == "ArtifactLink" and url.startswith("vstfs://"):
            parsed = _parse_artifact_link(url, repo_id_to_name)
            if parsed is None:
                continue
            kind, label = parsed
            if kind == "commit":
                out["related_commits"].append(label)
            elif kind == "pr":
                out["related_prs"].append(label)
            elif kind == "branch":
                out["related_branches"].append(label)
    # Dedup while preserving order.
    for key in ("related_ids", "related_commits", "related_prs", "related_branches"):
        seen: set[str] = set()
        deduped: list[str] = []
        for item in out[key]:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        out[key] = deduped
    return out


def _extract_workitem_id(url: str) -> str | None:
    m = re.search(r"/workItems/(\d+)", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------- writers


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    try:
        import html2text  # type: ignore

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html).strip()
    except ImportError:
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(f'"{_yaml_str(v)}"' for v in values) + "]"


def _field(wi: dict, name: str, default: str = "") -> str:
    value = wi.get("fields", {}).get(name, default)
    if isinstance(value, dict):
        # Person fields come back as {"displayName": ..., "uniqueName": ...}
        return value.get("uniqueName") or value.get("displayName") or ""
    return "" if value is None else str(value)


def _write_work_item_md(
    wi: dict,
    target_dir: Path,
    *,
    org: str,
    project: str,
    repo_id_to_name: dict[str, str],
) -> Path:
    wid = str(wi.get("id", ""))
    fields = wi.get("fields", {})
    title = _field(wi, "System.Title", f"Work item {wid}")
    wtype = _field(wi, "System.WorkItemType", "WorkItem")
    state = _field(wi, "System.State")
    assigned = _field(wi, "System.AssignedTo")
    author = _field(wi, "System.CreatedBy")
    area = _field(wi, "System.AreaPath")
    iteration = _field(wi, "System.IterationPath")
    changed_at = _field(wi, "System.ChangedDate")
    description = _html_to_text(fields.get("System.Description", "") or "")
    acceptance = _html_to_text(
        fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "") or ""
    )

    rel = _parse_workitem_relations(wi, repo_id_to_name)
    source_url = (
        f"https://dev.azure.com/{urllib.parse.quote(org)}/"
        f"{urllib.parse.quote(project)}/_workitems/edit/{wid}"
    )
    now = datetime.now(timezone.utc).isoformat()

    frontmatter_lines = [
        "---",
        f'source_url: "{_yaml_str(source_url)}"',
        "type: work_item",
        f'work_item_id: "{wid}"',
        f'work_item_type: "{_yaml_str(wtype)}"',
        f'title: "{_yaml_str(title)}"',
        f'state: "{_yaml_str(state)}"',
        f'area_path: "{_yaml_str(area)}"',
        f'iteration_path: "{_yaml_str(iteration)}"',
        f'assigned_to: "{_yaml_str(assigned)}"',
        f'author: "{_yaml_str(author)}"',
        f"captured_at: {now}",
        f'changed_at: "{_yaml_str(changed_at)}"',
        'contributor: "azure-devops-sync"',
    ]
    if rel["parent_id"]:
        frontmatter_lines.append(f'parent_id: "{rel["parent_id"]}"')
    frontmatter_lines.append(f"related_ids: {_yaml_list(rel['related_ids'])}")
    frontmatter_lines.append(
        f"related_branches: {_yaml_list(rel['related_branches'])}"
    )
    frontmatter_lines.append(
        f"related_commits: {_yaml_list(rel['related_commits'])}"
    )
    frontmatter_lines.append(f"related_prs: {_yaml_list(rel['related_prs'])}")
    frontmatter_lines.append("---")

    body_lines = [
        "",
        f"# [{wtype}-{wid}] {title}",
        "",
        f"**State:** {state or '-'} · **Assigned:** {assigned or '-'}",
    ]
    related_bits: list[str] = []
    if rel["related_commits"]:
        related_bits.append("commits " + ", ".join(f"`{c}`" for c in rel["related_commits"]))
    if rel["related_prs"]:
        related_bits.append("PR " + ", ".join(f"`{p}`" for p in rel["related_prs"]))
    if rel["related_branches"]:
        related_bits.append(
            "branch " + ", ".join(f"`{b}`" for b in rel["related_branches"])
        )
    if related_bits:
        body_lines += ["", "**Related code:** " + " · ".join(related_bits)]
    if description:
        body_lines += ["", "## Description", "", description]
    if acceptance:
        body_lines += ["", "## Acceptance Criteria", "", acceptance]
    body_lines += ["", f"Source: {source_url}", ""]

    content = "\n".join(frontmatter_lines + body_lines)
    out_path = target_dir / f"workitem_{wid}.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def _write_repo_md(
    repo: dict,
    repos_root: Path,
    *,
    org: str,
    project: str,
    head_sha: str | None,
    branch: str | None = None,
) -> Path:
    name = repo.get("name", "repo")
    safe_name = re.sub(r"[^\w\-.]", "_", name).strip("_") or "repo"
    repo_dir = repos_root / safe_name
    repo_dir.mkdir(parents=True, exist_ok=True)

    # Prefer the branch we actually checked out; fall back to the API field.
    default_branch = branch or (repo.get("defaultBranch") or "").replace(
        "refs/heads/", ""
    )
    source_url = (
        f"https://dev.azure.com/{urllib.parse.quote(org)}/"
        f"{urllib.parse.quote(project)}/_git/{urllib.parse.quote(name)}"
    )
    now = datetime.now(timezone.utc).isoformat()
    frontmatter = [
        "---",
        f'source_url: "{_yaml_str(source_url)}"',
        "type: repo",
        f'repo_id: "{_yaml_str(repo.get("id", ""))}"',
        f'repo_name: "{_yaml_str(name)}"',
        f'default_branch: "{_yaml_str(default_branch)}"',
        f'head_sha: "{_yaml_str(head_sha or "")}"',
        f"captured_at: {now}",
        'contributor: "azure-devops-sync"',
        "---",
        "",
        f"# {name}",
        "",
        f"Default branch: {default_branch or '-'} · HEAD: {head_sha or '-'}",
        "",
        f"Source: {source_url}",
        "",
    ]
    out_path = repo_dir / "_repo.md"
    out_path.write_text("\n".join(frontmatter), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------- git


def _assert_git_available() -> None:
    try:
        subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "git not found on PATH — install git or pass --no-clone"
        ) from exc


def _git_env() -> dict[str, str]:
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        env=_git_env(),
    )


def _clone_or_update_repo(
    repo: dict,
    repos_root: Path,
    *,
    org: str,
    project: str,
    pat: str,
    full: bool,
    prior_head: str | None,
) -> tuple[str | None, str | None, bool]:
    """Clone (or refresh) a repo on its *true* default branch.

    The Azure DevOps ``defaultBranch`` API field can drift to a feature or
    bugfix branch, so we don't pass ``--branch`` on fresh clones — git follows
    the remote's symbolic HEAD, which is the branch the server actually serves
    by default. After clone we resolve the branch name locally and reuse it
    for incremental fetches.

    Returns ``(head_sha, branch, was_fetched)``. ``head_sha``/``branch`` are
    ``None`` if the clone failed.
    """
    name = repo.get("name", "")
    safe_name = re.sub(r"[^\w\-.]", "_", name).strip("_") or "repo"
    repo_dir = repos_root / safe_name

    encoded_pat = urllib.parse.quote(pat, safe="")
    auth_url = (
        f"https://{encoded_pat}@dev.azure.com/"
        f"{urllib.parse.quote(org)}/{urllib.parse.quote(project)}/_git/"
        f"{urllib.parse.quote(name)}"
    )
    clean_url = (
        f"https://dev.azure.com/{urllib.parse.quote(org)}/"
        f"{urllib.parse.quote(project)}/_git/{urllib.parse.quote(name)}"
    )

    # Fresh clone: either directory missing, not a git repo, or --full reset.
    needs_fresh_clone = full or not (repo_dir / ".git").exists()
    if needs_fresh_clone:
        if repo_dir.exists() and full:
            _rm_tree(repo_dir)
        repos_root.mkdir(parents=True, exist_ok=True)
        print(f"[azure] Cloning {name} (default branch)...")
        try:
            _run_git(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--single-branch",
                    auth_url,
                    str(repo_dir),
                ]
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            stderr = _redact(stderr)
            print(f"[azure] clone failed for {name}: {stderr.strip()[:200]}")
            return None, None, False
        # Strip PAT from remote URL immediately.
        try:
            _run_git(["remote", "set-url", "origin", clean_url], cwd=repo_dir)
        except subprocess.CalledProcessError:
            pass
        branch = _resolve_current_branch(repo_dir)
        head_sha = _resolve_head_sha(repo_dir)
        short = head_sha[:7] if head_sha else "?"
        print(f"[azure]   -> {name} on {branch or '?'} @ {short}")
        return head_sha, branch, True

    # Incremental fetch path — use whatever branch the local clone is on.
    branch = _resolve_current_branch(repo_dir) or (
        (repo.get("defaultBranch") or "refs/heads/main").replace("refs/heads/", "")
    )
    try:
        # Temporarily set PAT-auth remote for fetch, then restore.
        _run_git(["remote", "set-url", "origin", auth_url], cwd=repo_dir)
        _run_git(
            ["fetch", "--depth", "1", "origin", branch],
            cwd=repo_dir,
        )
        _run_git(["reset", "--hard", "FETCH_HEAD"], cwd=repo_dir)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        print(f"[azure] fetch failed for {name}: {_redact(stderr).strip()[:200]}")
        try:
            _run_git(["remote", "set-url", "origin", clean_url], cwd=repo_dir)
        except subprocess.CalledProcessError:
            pass
        return prior_head, branch, False
    finally:
        try:
            _run_git(["remote", "set-url", "origin", clean_url], cwd=repo_dir)
        except subprocess.CalledProcessError:
            pass

    head_sha = _resolve_head_sha(repo_dir)
    if head_sha and head_sha == prior_head:
        print(f"[azure] Skipping {name} (up to date @ {head_sha[:7]})")
        return head_sha, branch, False
    print(f"[azure] Updated {name} on {branch} -> {head_sha[:7] if head_sha else '?'}")
    return head_sha, branch, True


def _resolve_current_branch(repo_dir: Path) -> str | None:
    """Return the branch currently checked out in repo_dir, or None."""
    try:
        res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
        name = res.stdout.decode("ascii").strip()
        return name if name and name != "HEAD" else None
    except subprocess.CalledProcessError:
        return None


def _resolve_head_sha(repo_dir: Path) -> str | None:
    try:
        res = _run_git(["rev-parse", "HEAD"], cwd=repo_dir)
        return res.stdout.decode("ascii").strip() or None
    except subprocess.CalledProcessError:
        return None


def _rm_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------- public entry


def sync(
    org: str,
    project: str,
    target_dir: Path,
    pat: str,
    full: bool = False,
    clone_repos: bool = True,
    repos_filter: list[str] | None = None,
    since: str | None = None,
) -> dict[str, int]:
    """Fetch work items + repo metadata, and (unless clone_repos=False) clone
    each repo into target_dir/repos/<name>/.

    Returns counts: {"work_items": N, "repos": N, "cloned": N, "skipped": N}.
    """
    if not pat:
        raise ValueError("azure sync: PAT is empty")
    if not org or not project:
        raise ValueError("azure sync: org and project are required")

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if clone_repos:
        _assert_git_available()

    headers = _auth_header(pat)

    state = _load_state(target_dir) if not full else {"work_items": {}, "repos": {}}
    effective_since = _resolve_since(state, since, full)
    window = "all dates" if effective_since is None else f"ChangedDate >= {effective_since}"
    print(f"[azure] fetch window: {window}")

    # Repos first so we can resolve ArtifactLink repo ids to names.
    repos = _fetch_repos(org, project, headers)
    repo_id_to_name = {
        str(r.get("id", "")).lower(): r.get("name", "") for r in repos
    }
    filter_set = {r.lower() for r in repos_filter} if repos_filter else None

    repos_root = target_dir / "repos"
    cloned_count = 0
    skipped_count = 0
    repo_state = state.get("repos", {})

    for repo in repos:
        name = repo.get("name", "")
        prior = repo_state.get(name, {})
        head_sha: str | None = prior.get("head_sha")
        branch: str | None = prior.get("branch")
        if clone_repos and (filter_set is None or name.lower() in filter_set):
            head_sha, branch, was_fetched = _clone_or_update_repo(
                repo,
                repos_root,
                org=org,
                project=project,
                pat=pat,
                full=full,
                prior_head=prior.get("head_sha"),
            )
            if was_fetched:
                cloned_count += 1
            else:
                skipped_count += 1
        elif clone_repos and filter_set is not None and name.lower() not in filter_set:
            skipped_count += 1
        _write_repo_md(
            repo,
            repos_root if clone_repos else target_dir / "_repos",
            org=org,
            project=project,
            head_sha=head_sha,
            branch=branch,
        )
        repo_state[name] = {
            "head_sha": head_sha or "",
            "branch": branch or "",
            "cloned_at": datetime.now(timezone.utc).isoformat(),
        }

    # Work items.
    work_items = _fetch_work_items(org, project, effective_since, headers)
    for wi in work_items:
        _write_work_item_md(
            wi,
            target_dir,
            org=org,
            project=project,
            repo_id_to_name=repo_id_to_name,
        )

    # Advance the incremental cursor to max ChangedDate seen.
    if work_items:
        max_changed = max(
            _field(wi, "System.ChangedDate") for wi in work_items
        )
        if max_changed:
            state["work_items"]["last_changed_date"] = max_changed
    state["repos"] = repo_state
    _save_state(target_dir, state)

    return {
        "work_items": len(work_items),
        "repos": len(repos),
        "cloned": cloned_count,
        "skipped": skipped_count,
    }
