# 9. API key in the operating system keychain

- Status: Accepted (requirement)
- Date: 2026-11-11

## Context

The user's OpenRouter key must never be in plaintext files, logs or the database.

## Decision

Store it with `keyring` behind a `KeyStore` protocol. An `OPENROUTER_API_KEY` environment variable is read as an override and never persisted. Tests assert the key does not appear in logs, exceptions or the database.

## Consequences

Headless Linux may have no keychain backend, so the environment variable is the documented fallback.
