"""Resolve where aikgraph should read/write its output directory.

The output dir defaults to ``./aikgraph-out`` but is redirected under the
assistant-specific config directory (``.kiro``, ``.claude``, ``.copilot``)
when the corresponding install has been run. Each installer drops a
``.aikgraph_marker`` file so detection is unambiguous.
"""
from __future__ import annotations

import os
from pathlib import Path


PLATFORM_DIRS: tuple[str, ...] = (".kiro", ".claude", ".copilot")
OUT_NAME = "aikgraph-out"
MARKER = ".aikgraph_marker"


def platform_out_dir(platform: str, project_dir: Path | str | None = None) -> Path:
    """Return the aikgraph-out path under ``<platform>/`` (``.kiro`` etc.)."""
    root = Path(project_dir) if project_dir is not None else Path(".")
    return root / f".{platform.lstrip('.')}" / OUT_NAME


def resolve_out_dir(project_dir: Path | str | None = None) -> Path:
    """Return the aikgraph output directory for *project_dir*.

    Priority:
      1. ``$AIKGRAPH_OUT`` environment variable
      2. ``<project>/<platform>/aikgraph-out`` if a marker file is present
         (checked in order: ``.kiro``, ``.claude``, ``.copilot``)
      3. ``<project>/aikgraph-out`` (legacy default — returned even if
         missing so callers can create it)
    """
    env = os.environ.get("AIKGRAPH_OUT")
    if env:
        return Path(env)

    root = Path(project_dir) if project_dir is not None else Path(".")
    for platform_dir in PLATFORM_DIRS:
        candidate = root / platform_dir / OUT_NAME
        if (candidate / MARKER).is_file():
            return candidate

    return root / OUT_NAME


def write_marker(out_dir: Path) -> None:
    """Create *out_dir* and drop the marker file so the resolver finds it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = out_dir / MARKER
    if not marker.exists():
        marker.write_text("aikgraph\n", encoding="utf-8")
