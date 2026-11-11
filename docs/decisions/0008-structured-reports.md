# 8. One validated report schema, with no verdict

- Status: Accepted
- Date: 2026-11-11

## Context

Every research agent must return the same structure. The original brief asked for a verdict on
a fixed scale and a confidence level. On review the owner decided against both: the app gathers
evidence so the user can judge, and should not rule on what is true.

## Decision

A `Report` has a neutral summary of what was found, evidence items (URL, quoted passage, and
whether that passage supports or undermines the lead), and a mandatory statement of what could
not be determined. It has no verdict, rating or confidence field, and a test asserts that. Our
own validation always runs, whatever the provider promised. Evidence is flagged when its URL
was not among the search results.

## Consequences

The per-item stance is the only judgement the model records, and it is about one passage, not
the claim. Models without native structured-output support use a prompted-JSON path with one
repair attempt.
