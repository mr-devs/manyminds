# 7. Jobs on asyncio, persisted in SQLite

- Status: Accepted
- Date: 2026-11-11

## Context

Each (lead, model) pair is a job that runs concurrently, survives restarts and reports status live.

## Decision

A `JobManager` runs jobs as asyncio tasks under a concurrency limit, with each job isolated from the others' failures. State is stored with the standard library's `sqlite3` (no ORM), with numbered migrations tracked by `PRAGMA user_version`. On startup, unfinished jobs are marked interrupted and wait for the user to resume them, because resuming spends money.

## Consequences

No extra dependency for storage. Database calls are short and run on the event loop for now; move them to a worker thread if they ever become slow. Schema changes need a migration each time.
