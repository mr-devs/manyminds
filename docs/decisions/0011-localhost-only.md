# 11. Bind to localhost only

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

The app holds the user's key and data and has no authentication. NiceGUI binds to `0.0.0.0` by default.

## Decision

Always start with `host="127.0.0.1"`, `reload=False` and a free port, and reject requests whose Host header is not a localhost name. A test asserts the startup arguments.

## Consequences

The app is not reachable from other machines. Other programs on the same machine can still reach it, which is noted in the README.
