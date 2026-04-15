# hooks

```bash
aikgraph hook install    # install
aikgraph hook uninstall  # remove
aikgraph hook status     # check
```

After every `git commit`, the hook detects which code files changed (via `git diff HEAD~1`), re-runs AST extraction on those files, and rebuilds `graph.json` and `REPORT.md`. Doc/image changes are ignored by the hook - run `/aikgraph --update` manually for those.

If a post-commit hook already exists, aikgraph appends to it rather than replacing it.
