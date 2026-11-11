# 1. uv for all tooling

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

The project needs one tool for environments, dependencies, running, building and publishing.

## Decision

Use uv for everything, with the `uv_build` backend, a `src/` layout and a committed `uv.lock`. No pip, poetry, conda or requirements.txt. Pin the uv version in CI.

## Consequences

uv is still 0.x: the `uv_build` upper bound must be raised at each minor release, and breaking changes arrive between minors. `uv_build` only supports pure-Python packages, which is all we need.
