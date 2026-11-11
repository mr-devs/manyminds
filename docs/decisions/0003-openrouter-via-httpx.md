# 3. All model calls through OpenRouter, using plain httpx

- Status: Accepted
- Date: 2026-11-11

## Context

Every model call goes through OpenRouter with the user's key. Options for the client are the official `openrouter` SDK, the `openai` SDK with a custom base URL, or plain HTTP.

## Decision

Use `httpx` directly, with our own small transport for requests, server-sent events and error mapping. The Chat Completions or Responses endpoint is chosen by a live spike in milestone 1b.

## Consequences

We own a little more code, but avoid an auto-generated SDK with several releases a day and keep full control of streaming and error handling. Tests use `httpx.MockTransport`, so no mocking library is needed.
