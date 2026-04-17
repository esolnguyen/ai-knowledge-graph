"""Platform registry and shared install helpers."""
from __future__ import annotations

import sys

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("aikgraphy")
except Exception:
    __version__ = "unknown"


def install(platform: str = "claude") -> None:
    """Install the aikgraph integration for the given platform."""
    if platform == "kiro":
        from aikgraph.cli.kiro import kiro_install

        kiro_install()
        return

    if platform == "claude":
        from aikgraph.cli.claude import claude_install

        claude_install()
        return

    if platform == "copilot":
        from aikgraph.cli.copilot import copilot_install

        copilot_install()
        return

    print(
        f"error: unknown platform '{platform}'. Choose from: claude, copilot, kiro",
        file=sys.stderr,
    )
    sys.exit(1)
