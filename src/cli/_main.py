"""aikgraph CLI entry point."""
from __future__ import annotations

import sys

from aikgraph.cli import commands
from aikgraph.cli.claude import claude_install, claude_uninstall
from aikgraph.cli.copilot import copilot_uninstall
from aikgraph.cli.kiro import kiro_install, kiro_uninstall
from aikgraph.cli.platforms import install


def _print_help() -> None:
    print("Usage: aikgraph <command>")
    print()
    print("Commands:")
    print(
        "  install [--platform P]  install aikgraph assistant integration (claude|copilot|kiro)"
    )
    print('  path "A" "B"            shortest path between two nodes in graph.json')
    print(
        "    --graph <path>          path to graph.json (default aikgraph-out/graph.json)"
    )
    print(
        '  explain "X"             plain-language explanation of a node and its neighbors'
    )
    print(
        "    --graph <path>          path to graph.json (default aikgraph-out/graph.json)"
    )
    print(
        "  add <url>               fetch a URL and save it to ./raw, then update the graph"
    )
    print('    --author "Name"         tag the author of the content')
    print('    --contributor "Name"    tag who added it to the corpus')
    print("    --dir <path>            target directory (default: ./raw)")
    print(
        "  watch <path>            watch a folder and rebuild the graph on code changes"
    )
    print(
        "  update <path>           re-extract code files and update the graph (no LLM needed)"
    )
    print(
        "    --obsidian              also export an Obsidian vault + graph.canvas"
    )
    print(
        "    --project <name>        also sync an Azure DevOps project (work items + repos)"
    )
    print(
        "                            requires AZURE_DEVOPS_PAT and AZURE_DEVOPS_ORG env vars"
    )
    print(
        "    --since YYYY-MM-DD      cap first-run work-item scan (default: 365d back)"
    )
    print(
        "    --full                  ignore state; force full rescan + re-clone"
    )
    print(
        "    --no-clone              skip git clone of project repos (metadata only)"
    )
    print(
        "    --repos a,b,c           clone only this subset of repos (comma-separated)"
    )
    print(
        "  cluster-only <path>     rerun clustering on an existing graph.json and regenerate report"
    )
    print('  query "<question>"       BFS traversal of graph.json for a question')
    print("    --dfs                   use depth-first instead of breadth-first")
    print("    --budget N              cap output at N tokens (default 2000)")
    print(
        "    --graph <path>          path to graph.json (default aikgraph-out/graph.json)"
    )
    print(
        "  save-result             save a Q&A result to aikgraph-out/memory/ for graph feedback loop"
    )
    print("    --question Q            the question asked")
    print("    --answer A              the answer to save")
    print(
        "    --type T                query type: query|path_query|explain (default: query)"
    )
    print("    --nodes N1 N2 ...       source node labels cited in the answer")
    print(
        "    --memory-dir DIR        memory directory (default: aikgraph-out/memory)"
    )
    print(
        "  benchmark [graph.json]  measure token reduction vs naive full-corpus approach"
    )
    print(
        "  hook install            install post-commit/post-checkout git hooks (all platforms)"
    )
    print("  hook uninstall          remove git hooks")
    print("  hook status             check if git hooks are installed")
    print(
        "  claude install          write aikgraph section to CLAUDE.md + PreToolUse hook (Claude Code)"
    )
    print(
        "  claude uninstall        remove aikgraph section from CLAUDE.md + PreToolUse hook"
    )
    print("  copilot install         prepare .copilot/aikgraph-out/ for GitHub Copilot")
    print("  copilot uninstall       remove legacy aikgraph skill from ~/.copilot/skills")
    print("  kiro install            write always-on steering + prepare .kiro/aikgraph-out/")
    print("  kiro uninstall          remove steering from .kiro/steering/")
    print()


def _parse_install_platform(args: list[str]) -> str:
    platform = "claude"
    i = 0
    while i < len(args):
        if args[i].startswith("--platform="):
            platform = args[i].split("=", 1)[1]
            i += 1
        elif args[i] == "--platform" and i + 1 < len(args):
            platform = args[i + 1]
            i += 2
        else:
            i += 1
    return platform


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _print_help()
        return

    cmd = sys.argv[1]

    if cmd == "install":
        install(platform=_parse_install_platform(sys.argv[2:]))
    elif cmd == "claude":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            claude_install()
        elif subcmd == "uninstall":
            claude_uninstall()
        else:
            print("Usage: aikgraph claude [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "copilot":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            from aikgraph.cli.copilot import copilot_install

            copilot_install()
        elif subcmd == "uninstall":
            copilot_uninstall()
        else:
            print("Usage: aikgraph copilot [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "kiro":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            kiro_install()
        elif subcmd == "uninstall":
            kiro_uninstall()
        else:
            print("Usage: aikgraph kiro [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "hook":
        commands.cmd_hook(sys.argv[2:])
    elif cmd == "query":
        commands.cmd_query(sys.argv[2:])
    elif cmd == "save-result":
        commands.cmd_save_result(sys.argv[2:])
    elif cmd == "path":
        commands.cmd_path(sys.argv[2:])
    elif cmd == "explain":
        commands.cmd_explain(sys.argv[2:])
    elif cmd == "add":
        commands.cmd_add(sys.argv[2:])
    elif cmd == "watch":
        commands.cmd_watch(sys.argv[2:])
    elif cmd == "cluster-only":
        commands.cmd_cluster_only(sys.argv[2:])
    elif cmd == "update":
        commands.cmd_update(sys.argv[2:])
    elif cmd == "benchmark":
        commands.cmd_benchmark(sys.argv[2:])
    else:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print("Run 'aikgraph --help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
