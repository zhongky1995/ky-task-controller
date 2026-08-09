# Contributing

Thanks for helping improve KY-TASK.

## Development workflow

1. Fork the repository and create a focused branch.
2. Keep controller policy changes separate from unrelated capability-registry changes.
3. Add or update tests for state transitions, dispatch gates, project affinity, write boundaries, and verification behavior.
4. Run the complete test suite before opening a pull request.

```bash
cd plugins/task-controller
python3 -m pytest -q
node --check mcp/server.mjs
```

## Design rules

- The controller owns final synthesis and final verification.
- Distributed lanes must use real independent workers.
- Native worker Sessions must preserve the resolved Codex project unless the user explicitly approves a task-scoped override.
- Never silently fall back from native Sessions to managed Sub Agents.
- Parallel writers must not share a durable write target.
- Implementation and independent review must remain separate.
- Public fixtures and tests must not contain customer data, credentials, local absolute paths, or conversation exports.

Please describe behavioral changes and their safety implications in the pull request.
