"""GitHub Copilot CLI project-local install: prepare .copilot/aikgraph-out/."""
from __future__ import annotations

from pathlib import Path

from aikgraph.utils.paths import platform_out_dir, write_marker


def copilot_install(project_dir: Path | None = None) -> None:
    """Create .copilot/aikgraph-out/ so `aikgraph update` writes output there."""
    project_dir = project_dir or Path(".")
    out_dir = platform_out_dir("copilot", project_dir)
    write_marker(out_dir)
    print(f"  {out_dir}/  ->  output directory ready")
    print()
    print(f"Run `aikgraph update` from the shell to populate {out_dir}/.")


def copilot_uninstall() -> None:
    """Remove any legacy global aikgraph skill from ~/.copilot/skills/aikgraph/."""
    skill_dst = Path.home() / ".copilot" / "skills" / "aikgraph" / "SKILL.md"
    removed: list[str] = []
    if skill_dst.exists():
        skill_dst.unlink()
        removed.append(f"skill removed: {skill_dst}")
    version_file = skill_dst.parent / ".aikgraph_version"
    if version_file.exists():
        version_file.unlink()
    for d in (
        skill_dst.parent,
        skill_dst.parent.parent,
        skill_dst.parent.parent.parent,
    ):
        try:
            d.rmdir()
        except OSError:
            break
    print("; ".join(removed) if removed else "nothing to remove")
