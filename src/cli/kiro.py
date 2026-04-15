"""Kiro IDE/CLI skill + always-on steering installer."""

from __future__ import annotations

import sys
from pathlib import Path


_KIRO_STEERING = """\
---
inclusion: always
---

aikgraph: A knowledge graph of this project lives in `aikgraph-out/`. \
If `aikgraph-out/REPORT.md` exists, read it before answering architecture questions, \
tracing dependencies, or searching files — it contains god nodes, community structure, \
and surprising connections the graph found. Navigate by graph structure instead of grepping raw files.
"""

_KIRO_STEERING_MARKER = "aikgraph: A knowledge graph of this project"


def kiro_install(project_dir: Path | None = None) -> None:
    """Copy all aikgraph skill files + steering file for Kiro IDE/CLI."""
    project_dir = project_dir or Path(".")

    skill_src_dir = Path(__file__).parent.parent / "skill-kiro"
    if not skill_src_dir.is_dir():
        print(
            "error: skill-kiro/ folder not found in package - reinstall aikgraph",
            file=sys.stderr,
        )
        sys.exit(1)

    skill_dst_dir = project_dir / ".kiro" / "skills" / "aikgraph"
    skill_dst_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for src_file in sorted(skill_src_dir.glob("*.md")):
        dst_file = skill_dst_dir / src_file.name
        dst_file.write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
        copied += 1
    if copied == 0:
        print(
            "error: skill-kiro/ folder is empty - reinstall aikgraph",
            file=sys.stderr,
        )
        sys.exit(1)
    print(
        f"  {skill_dst_dir.relative_to(project_dir)}/  ->  {copied} skill files "
        f"(SKILL.md + {copied - 1} mode files)"
    )

    steering_dir = project_dir / ".kiro" / "steering"
    steering_dir.mkdir(parents=True, exist_ok=True)
    steering_dst = steering_dir / "aikgraph.md"
    if steering_dst.exists() and _KIRO_STEERING_MARKER in steering_dst.read_text(
        encoding="utf-8"
    ):
        print(f"  .kiro/steering/aikgraph.md  ->  already configured")
    else:
        steering_dst.write_text(_KIRO_STEERING, encoding="utf-8")
        print(f"  .kiro/steering/aikgraph.md  ->  always-on steering written")

    print()
    print("Kiro will now read the knowledge graph before every conversation.")
    print("Use /aikgraph to build or update the graph.")


def kiro_uninstall(project_dir: Path | None = None) -> None:
    """Remove aikgraph skill files + steering file for Kiro."""
    project_dir = project_dir or Path(".")
    removed: list[str] = []

    skill_dst_dir = project_dir / ".kiro" / "skills" / "aikgraph"
    if skill_dst_dir.is_dir():
        for f in sorted(skill_dst_dir.glob("*.md")):
            f.unlink()
            removed.append(str(f.relative_to(project_dir)))
        try:
            skill_dst_dir.rmdir()
        except OSError:
            pass

    steering_dst = project_dir / ".kiro" / "steering" / "aikgraph.md"
    if steering_dst.exists():
        steering_dst.unlink()
        removed.append(str(steering_dst.relative_to(project_dir)))

    print("Removed: " + (", ".join(removed) if removed else "nothing to remove"))
