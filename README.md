# manyminds

**Status: pre-alpha.** This release only claims the package name. The `manyminds` command
prints its version and a short notice; the application is not built yet. See
[`PLAN.md`](https://github.com/mr-devs/manyminds/blob/main/PLAN.md) for what is coming.

## What it will be

A Python app that helps you check claims you find on the web. It runs on your own machine with
your own [OpenRouter](https://openrouter.ai) API key, and its only interface is a local
browser app.

You paste a piece of text. The app proposes *leads*: specific threads that could be researched
to see whether the text is supported by evidence. You edit that list, and one research agent
per lead runs in parallel and writes a focused report of quoted, linked evidence. You can read
finished reports while others are still running, then chat about the evidence and start more
research.

manyminds gathers evidence for you to judge. It does not issue verdicts on what is true.

## Where your text goes

Orchestration is local; inference is not. Text you paste is sent to OpenRouter, to the model
providers you choose, and to the web search engine used for research. Your API key is kept in
your operating system's keychain. The app listens on localhost only.

## Install

```
uvx manyminds
```

or

```
uv tool install manyminds
```

## Development

Everything runs through [uv](https://docs.astral.sh/uv/):

```
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy
```

Development follows strict test-driven development; the rules are in
[`CLAUDE.md`](https://github.com/mr-devs/manyminds/blob/main/CLAUDE.md).

## Licence

MIT. See [`LICENSE`](https://github.com/mr-devs/manyminds/blob/main/LICENSE).
