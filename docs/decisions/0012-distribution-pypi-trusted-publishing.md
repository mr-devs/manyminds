# 12. Distribute on PyPI through trusted publishing

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

The first distribution target is `uv tool install manyminds` and `uvx manyminds`. Installers and code signing are out of scope.

## Decision

Publish from a tag-triggered GitHub Actions workflow using `uv build` and `uv publish` with PyPI trusted publishing, a protected `pypi` environment that requires manual approval, and actions pinned by commit SHA. Claim the name with an honest pre-alpha 0.0.1.

## Consequences

No long-lived PyPI token exists. Attestations depend on an early-stage action and may be dropped if it blocks a release. The first release, 0.0.1, was uploaded by hand with an API token to claim the name quickly; later releases use the workflow once a trusted publisher is added to the project.
