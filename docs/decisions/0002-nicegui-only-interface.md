# 2. NiceGUI as the only interface

- Status: Accepted
- Date: 2026-11-11

## Context

The app needs a local browser interface written in Python, with no separate frontend.

## Decision

Use NiceGUI, at 4.x (`nicegui>=4.0,<5`), with single-page routing through `ui.sub_pages` and the `Event` class for pushing background updates to open pages.

## Consequences

Python 3.11 is the minimum. NiceGUI 4.0 is very new, so 3.19 is the fallback. The `User` test fixture does not run JavaScript, so some browser behaviour needs manual checks.
