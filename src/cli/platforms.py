"""Platform registry and shared install helpers."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("aikgraphy")
except Exception:
    __version__ = "unknown"


_SKILL_REGISTRATION = (
    "\n# aikgraph\n"
    "- **aikgraph** (`~/.claude/skills/aikgraph/SKILL.md`) "
    "- any input to knowledge graph. Trigger: `/aikgraph`\n"
    "When the user types `/aikgraph`, invoke the Skill tool "
    'with `skill: "aikgraph"` before doing anything else.\n'
)


_PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {
        "skill_file": "skill.md",
        "skill_dst": Path(".claude") / "skills" / "aikgraph" / "SKILL.md",
        "claude_md": True,
    },
    "copilot": {
        "skill_file": "skill-copilot.md",
        "skill_dst": Path(".copilot") / "skills" / "aikgraph" / "SKILL.md",
        "claude_md": False,
    },
}


def _check_skill_version(skill_dst: Path) -> None:
    """Warn if the installed skill is from an older aikgraph version."""
    version_file = skill_dst.parent / ".aikgraph_version"
    if not version_file.exists():
        return
    installed = version_file.read_text(encoding="utf-8").strip()
    if installed != __version__:
        print(
            f"  warning: skill is from aikgraph {installed}, package is {__version__}. Run 'aikgraph install' to update."
        )


def install(platform: str = "claude") -> None:
    """Install the aikgraph skill for the given platform."""
    if platform == "kiro":
        from aikgraph.cli.kiro import kiro_install

        kiro_install()
        return

    if platform not in _PLATFORM_CONFIG:
        print(
            f"error: unknown platform '{platform}'. Choose from: {', '.join(_PLATFORM_CONFIG)}, kiro",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = _PLATFORM_CONFIG[platform]
    skill_src = Path(__file__).parent.parent / cfg["skill_file"]
    if not skill_src.exists():
        print(
            f"error: {cfg['skill_file']} not found in package - reinstall aikgraph",
            file=sys.stderr,
        )
        sys.exit(1)

    skill_dst = Path.home() / cfg["skill_dst"]
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    (skill_dst.parent / ".aikgraph_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")

    if cfg["claude_md"]:
        claude_md = Path.home() / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8")
            if "aikgraph" in content:
                print(f"  CLAUDE.md        ->  already registered (no change)")
            else:
                claude_md.write_text(
                    content.rstrip() + _SKILL_REGISTRATION, encoding="utf-8"
                )
                print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
        else:
            claude_md.parent.mkdir(parents=True, exist_ok=True)
            claude_md.write_text(_SKILL_REGISTRATION.lstrip(), encoding="utf-8")
            print(f"  CLAUDE.md        ->  created at {claude_md}")

    print()
    print("Done. Open your AI coding assistant and type:")
    print()
    print("  /aikgraph .")
    print()
