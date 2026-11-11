# 13. Strict TDD with a small set of mechanical checks

- Status: Accepted
- Date: 2026-11-11

## Context

Agents doing TDD are known to weaken tests, special-case inputs and write tests that mirror the implementation. Guidance in a file is advisory only.

## Decision

Follow the red, commit, green, refactor, independent-review cycle from the brief. Add three mechanical checks: a commit rule (test commits touch only tests; other commits do not modify existing tests), a CI gate on unjustified skips and xfails, and a network block in the default suite. Review each milestone with a fresh, read-only subagent.

## Consequences

Some ceremony and extra cost per change. Evidence on test-first with agents is mixed; the outcome checks are the best-supported part, so those are the ones enforced.
