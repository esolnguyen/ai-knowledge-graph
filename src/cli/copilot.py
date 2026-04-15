"""GitHub Copilot CLI skill uninstall (install routes through platforms.install)."""
from __future__ import annotations

from pathlib import Path

from aikgraph.cli.platforms import _PLATFORM_CONFIG


def copilot_uninstall() -> None:
    """Remove the aikgraph skill from ~/.copilot/skills/aikgraph/."""
    skill_dst = Path.home() / _PLATFORM_CONFIG["copilot"]["skill_dst"]
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
