# 4. Web search behind our own interface

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

Search uses OpenRouter's `openrouter:web_search` server tool, which is in beta. The user setting has two options, `auto` (default) and `exa`.

## Decision

One module, `core/openrouter/websearch.py`, builds the tool entry and extracts citations and usage. Nothing else references the tool's shape. The engine setting is copied onto each job at launch.

## Consequences

A change in the beta API touches one module and its fixtures. `auto` behaves differently per model (native search for some providers, Exa for the rest), which the settings text explains.
