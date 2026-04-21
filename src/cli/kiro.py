"""Kiro IDE/CLI always-on steering + skill installer."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from aikgraph.utils.paths import platform_out_dir, write_marker


_KIRO_OUT = ".kiro/aikgraph-out"

_KIRO_STEERING = f"""\
---
inclusion: always
---

# aikgraph — use the graph before scanning files

This project ships a prebuilt knowledge graph at `{_KIRO_OUT}/graph.json` with a
summary at `{_KIRO_OUT}/REPORT.md`.

BEFORE running `find`, `grep`, `rg`, or reading source files to answer any
architecture, dependency, call-chain, "where does X live", "how does X reach Y",
or "what uses X" question, run aikgraph via the `shell` tool:

- `aikgraph query "<question>"`       neighborhood / broad context
- `aikgraph query "<q>" --dfs`        trace one chain deeper
- `aikgraph path "A" "B"`             shortest path between two symbols
- `aikgraph explain "X"`              one node + its immediate neighbors

Fall back to `find`/`grep` only when the graph returns nothing relevant or the
question is plainly non-structural (e.g. "find all TODO comments", "what files
were changed today"). When you do fall back, say so explicitly.

Read `{_KIRO_OUT}/REPORT.md` once per session to orient on god nodes and
community structure. If the graph looks stale after edits, run
`aikgraph update` before querying.

IMPORTANT: Run aikgraph commands through the `shell` tool. Do NOT output raw
<bash> markdown blocks.
"""

_KIRO_STEERING_MARKER = "# aikgraph — use the graph before scanning files"


def _skill_source() -> Path:
    """Return the path to the bundled SKILL.md inside the installed package."""
    return Path(str(resources.files("aikgraph").joinpath("skills", "SKILL.md")))


def _global_skill_dir() -> Path:
    return Path.home() / ".kiro" / "skills" / "aikgraph"


def kiro_install(project_dir: Path | None = None) -> None:
    """Install the aikgraph skill globally + wire up project-local steering/output.

    Skill goes to `~/.kiro/skills/aikgraph/SKILL.md` so Kiro loads it across all
    projects. Steering and output dir stay project-local because they reference
    the specific graph under `<project>/.kiro/aikgraph-out/`.
    """
    project_dir = project_dir or Path(".")

    skill_src = _skill_source()
    skill_dir = _global_skill_dir()
    skill_dst = skill_dir / "SKILL.md"
    if not skill_src.is_file():
        print(f"  warning: bundled skill not found at {skill_src}; skipping")
    else:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_dst.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  {skill_dst}  ->  query skill installed (global)")

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

    out_dir = platform_out_dir("kiro", project_dir)
    write_marker(out_dir)
    print(f"  {out_dir}/  ->  output directory ready")

    print()
    print("Kiro will now read the knowledge graph before every conversation")
    print("and knows how to query it via the aikgraph skill.")
    print(f"Run `aikgraph update` from the shell to populate {out_dir}/.")


def kiro_uninstall(project_dir: Path | None = None) -> None:
    """Remove aikgraph steering (project-local) + skill (global)."""
    project_dir = project_dir or Path(".")
    removed: list[str] = []

    steering_dst = project_dir / ".kiro" / "steering" / "aikgraph.md"
    if steering_dst.exists():
        steering_dst.unlink()
        removed.append(str(steering_dst.relative_to(project_dir)))

    skill_dir = _global_skill_dir()
    if skill_dir.exists():
        for child in skill_dir.iterdir():
            if child.is_file():
                child.unlink()
        try:
            skill_dir.rmdir()
            removed.append(str(skill_dir))
        except OSError:
            pass

    print("Removed: " + (", ".join(removed) if removed else "nothing to remove"))
