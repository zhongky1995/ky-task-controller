# Repository Risk Scan

Use this reference when planning complex work in a local repo or file tree. The scan feeds the capacity boundary: it estimates how much can be handled safely in one run.

## Lightweight Scan

Prefer fast, read-only commands:

```bash
pwd
git status --short
rg --files | wc -l
rg --files -g 'README*' -g 'AGENTS.md' -g 'package.json' -g 'pyproject.toml' -g 'requirements*.txt' -g 'Cargo.toml' -g 'go.mod' -g 'pom.xml' -g 'build.gradle*' -g 'Makefile' -g 'docker-compose*.yml'
rg --files -g '*test*' -g '*spec*' | head -50
```

Then inspect only the relevant docs, manifests, entry points, and nearby code.

## Size Heuristic

Use file count as a rough signal, not a decision by itself:

- Tiny: fewer than 50 files. Usually safe to inspect directly.
- Small: 50-200 files. Identify entry points and tests before editing.
- Medium: 200-1000 files. Plan by subsystem and verify boundaries before touching shared code.
- Large: 1000-5000 files. Require targeted search and staged implementation.
- Very large: more than 5000 files. Avoid broad assumptions; use narrow slices, tests, and explicit stop/go checkpoints.

Ignore generated/vendor folders when possible: `node_modules`, `.git`, `dist`, `build`, `coverage`, `.next`, `.venv`, `vendor`.

## Complexity Score

Score 1-3 each:

- Scope: number of files/modules/artifacts likely touched.
- Dependency surface: number of external systems, APIs, shared modules, or stakeholders.
- Risk: possibility of data loss, production breakage, compliance issue, user-facing regression, or irreversible edit.
- Ambiguity: how unclear the goal, boundary, acceptance criteria, or existing architecture is.

Interpretation:

- 4-5: direct execution with short plan.
- 6-8: normal plan with verification.
- 9-10: staged plan; inspect before editing; ask decisive questions.
- 11-12: high-risk; require explicit checkpoint before substantial execution.

## Capacity Signals

Treat repo work as high capacity demand when any of these are true:

- More than 1000 relevant files, or relevant files cannot be narrowed quickly.
- The change likely crosses multiple subsystems, packages, or data models.
- Tests are absent, slow, flaky, or hard to identify.
- The task requires architecture discovery before a safe edit.
- Existing dirty changes overlap the intended work.

When capacity demand is high, prefer project decomposition: inspect, choose a narrow first slice, edit, verify, then expand.

## Repo-Aware Task Contract Additions

For code tasks, add these to `任务契约 v0`:

- Repo size and likely project type.
- Relevant files or subsystems identified so far.
- Dirty worktree risk, if any.
- Test/verification options found.
- Files or areas that should not be touched.

## Hallucination Reduction Rules

- Prefer source files, tests, configs, and official docs over naming guesses.
- Search before asserting architecture.
- Verify package scripts before running them.
- Do not invent APIs, routes, schemas, env vars, or tests.
- If the repo contains user changes, preserve them and work around them.
- If no tests exist, state the manual verification path before editing.
