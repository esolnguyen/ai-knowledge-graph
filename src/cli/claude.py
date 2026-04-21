"""Claude Code project-local install: CLAUDE.md section + PreToolUse hook."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

from aikgraph.utils.paths import platform_out_dir, write_marker


_CLAUDE_OUT = ".claude/aikgraph-out"

_SETTINGS_HOOK = {
    "matcher": "Glob|Grep",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"[ -f {_CLAUDE_OUT}/graph.json ] && "
                "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\","
                f"\"additionalContext\":\"aikgraph: Knowledge graph exists. Read {_CLAUDE_OUT}/REPORT.md "
                "for god nodes and community structure before searching raw files.\"}}' "
                "|| true"
            ),
        }
    ],
}


_CLAUDE_MD_SECTION = f"""\
## aikgraph

This project has a aikgraph knowledge graph at {_CLAUDE_OUT}/.

Rules:
- Before answering architecture or codebase questions, read {_CLAUDE_OUT}/REPORT.md for god nodes and community structure
- If {_CLAUDE_OUT}/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `aikgraph update` to keep the graph current
"""

_CLAUDE_MD_MARKER = "## aikgraph"


def _skill_source() -> Path:
    """Return the path to the bundled SKILL.md inside the installed package."""
    return Path(str(resources.files("aikgraph").joinpath("skills", "SKILL.md")))


def _global_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "aikgraph"


def _install_claude_skill() -> None:
    """Copy the bundled SKILL.md to ~/.claude/skills/aikgraph/SKILL.md."""
    skill_src = _skill_source()
    skill_dir = _global_skill_dir()
    skill_dst = skill_dir / "SKILL.md"
    if not skill_src.is_file():
        print(f"  warning: bundled skill not found at {skill_src}; skipping")
        return
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dst.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  {skill_dst}  ->  query skill installed (global)")


def _uninstall_claude_skill() -> None:
    """Remove ~/.claude/skills/aikgraph/ (drop the installed skill)."""
    skill_dir = _global_skill_dir()
    if not skill_dir.exists():
        return
    for child in skill_dir.iterdir():
        if child.is_file():
            child.unlink()
    try:
        skill_dir.rmdir()
        print(f"  {skill_dir}  ->  skill removed")
    except OSError:
        pass


def claude_install(project_dir: Path | None = None) -> None:
    """Write the aikgraph section to the local CLAUDE.md and register the hook."""
    project_dir = project_dir or Path(".")
    target = project_dir / "CLAUDE.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _CLAUDE_MD_MARKER in content:
            print("aikgraph already configured in CLAUDE.md")
        else:
            content = content.rstrip() + "\n\n" + _CLAUDE_MD_SECTION
            target.write_text(content, encoding="utf-8")
            print(f"aikgraph section written to {target.resolve()}")
    else:
        target.write_text(_CLAUDE_MD_SECTION, encoding="utf-8")
        print(f"aikgraph section written to {target.resolve()}")

    _install_claude_skill()
    _install_claude_hook(project_dir)

    out_dir = platform_out_dir("claude", project_dir)
    write_marker(out_dir)
    print(f"  {out_dir}/  ->  output directory ready")

    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")
    print(f"Run `aikgraph update` to populate {out_dir}/.")


def claude_uninstall(project_dir: Path | None = None) -> None:
    """Remove the aikgraph section from the local CLAUDE.md and deregister the hook."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if not target.exists():
        print("No CLAUDE.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
    if _CLAUDE_MD_MARKER not in content:
        print("aikgraph section not found in CLAUDE.md - nothing to do")
        return

    cleaned = re.sub(
        r"\n*## aikgraph\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"aikgraph section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")

    _uninstall_claude_hook(project_dir or Path("."))
    _uninstall_claude_skill()


def _install_claude_hook(project_dir: Path) -> None:
    """Add aikgraph PreToolUse hook to .claude/settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_tool = hooks.setdefault("PreToolUse", [])

    hooks["PreToolUse"] = [
        h
        for h in pre_tool
        if not (h.get("matcher") == "Glob|Grep" and "aikgraph" in str(h))
    ]
    hooks["PreToolUse"].append(_SETTINGS_HOOK)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook registered")


def _uninstall_claude_hook(project_dir: Path) -> None:
    """Remove aikgraph PreToolUse hook from .claude/settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    filtered = [
        h
        for h in pre_tool
        if not (h.get("matcher") == "Glob|Grep" and "aikgraph" in str(h))
    ]
    if len(filtered) == len(pre_tool):
        return
    settings["hooks"]["PreToolUse"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook removed")
