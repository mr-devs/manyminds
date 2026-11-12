# 10. Treating retrieved content as untrusted data

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

Research agents and the conversation model read web content that may contain injected instructions.

## Decision

Give them the search tool and nothing else. Frame retrieved text as data in prompts. Require quoted evidence with URLs. Validate output against a schema. Show model text as plain text only, never as HTML or markdown, with links limited to http and https. No model output can start work; proposed leads wait for the user.

## Consequences

This lowers the risk but cannot remove it, and the README says so. Adversarial tests accompany each milestone that adds a new path for untrusted text.
