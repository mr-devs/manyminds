# 16. Checks are saved in the user's data folder

- Status: Accepted
- Date: 2026-11-12

## Context

The owner asked for every check to be remembered on the user's machine and listed in the
sidebar. Until now the real app kept its database in memory.

## Decision

- The SQLite database lives at `<user data folder>/manyminds/manyminds.db`, found with
  `platformdirs`, or in the folder named by `MANYMINDS_DATA_DIR`.
- The folder is created with mode `0700` and the file with `0600`, because pasted text and
  reports are personal.
- At start-up, any job still marked queued or running was cut off when the app last closed. It
  is marked failed with kind `interrupted`. Nothing restarts by itself; the thread page offers
  **Try again**, which runs a new attempt and keeps the old transcript.
- A check can be deleted from its page after confirming. Deleting removes its leads, threads,
  jobs, transcripts and reports.
- `--demo` stays in memory and writes nothing.

## Consequences

- The API key is still never written anywhere; only checks are stored.
- SQLite does not overwrite deleted rows on disk at once, so deleted text may remain
  recoverable from the file with forensic tools until the space is reused.
- Schema changes from here on must go through a migration, since real data now exists.
