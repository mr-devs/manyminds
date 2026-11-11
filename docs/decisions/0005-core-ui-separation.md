# 5. Core package with no NiceGUI imports

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

Logic must be testable without a browser.

## Decision

All logic lives in `manyminds.core`, which never imports `nicegui`. The UI is built by `build_app(services)` and only calls use-case functions and subscribes to events. Two architecture tests enforce the boundary.

## Consequences

UI tests stay few and thin. Core events need a small bridge to NiceGUI's `Event`.
