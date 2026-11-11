# 14. mypy (strict) and ruff

- Status: Accepted
- Date: 2026-11-11

## Context

CI needs linting, formatting and type checking, all run through uv.

## Decision

Use ruff for linting and formatting and mypy in strict mode for types, configured in `pyproject.toml`.

## Consequences

Astral's ty is faster but still beta with no stability guarantee for diagnostics; revisit when it stabilises.
