# 6. A small model-layer interface with a built-in fake

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

The rest of the code should not depend on OpenRouter directly, and tests must not use the network.

## Decision

Define a `ModelClient` protocol with `decompose`, `research` and `converse`. Ship `FakeModelClient` inside the package so tests and a `--demo` mode both use it.

## Consequences

The app can be run and demonstrated without a key or cost. The fake must be kept honest: it returns domain objects through the same validation as the real adapter.
