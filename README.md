# manyminds

**Status: early alpha.** The core loop works on real models: paste text, get leads, research
them in parallel, read cited reports, and come back to saved checks later. Settings,
conversations about the evidence and key storage are still to come. See
[`PLAN.md`](https://github.com/mr-devs/manyminds/blob/main/PLAN.md) for what is done and what is
next.

## What it is

A Python app that helps you check claims you find on the web. It runs on your own machine with
your own [OpenRouter](https://openrouter.ai) API key, and its only interface is a local
browser app.

You paste a piece of text. The app proposes *leads*: specific threads that could be researched
to see whether the text is supported by evidence. You edit that list, and one research agent
per lead runs in parallel and writes a focused report of quoted, linked evidence. You can read
finished reports while others are still running, and open any thread to see what the agent
searched for and found.

manyminds gathers evidence for you to judge. It does not issue verdicts on what is true. Each
piece of evidence links to its source, and is flagged when the link or the quote could not be
matched to what the search actually returned.

## Where your text goes

Orchestration is local; inference is not. Text you paste is sent to OpenRouter, to the model
provider behind each model you choose, and to the [Exa](https://exa.ai) search engine, which
runs the web searches. The app listens on localhost only.

Checks are saved on your computer only, in your user data folder (on macOS,
`~/Library/Application Support/manyminds`), in a file only your account can read. Set
`MANYMINDS_DATA_DIR` to keep them somewhere else. Deleting a check in the app removes its
text, leads and reports from that file.

Your API key is read from the `OPENROUTER_API_KEY` environment variable. It is never written to
disk, logged or printed. Storing it in the operating system's keychain is planned.

If the text you paste contains links, the app opens them (through OpenRouter and Exa, not from
your computer) so that leads can be drawn from what they say. For a YouTube link that is the
video's title and transcript.

Research agents search the web and open pages, which can contain text written to mislead a
model. What they read is treated as material to examine and their output is checked against a
fixed format, but no defence here is complete: a page could in principle steer an agent into
opening an address that carries part of your text with it. Read the sources yourself, and do
not paste anything you would not want sent to these services.

## Run

```
export OPENROUTER_API_KEY=...     # create one at https://openrouter.ai/keys
uvx manyminds
```

A lead costs roughly one to two US cents with the default model, most of it the web searches.
The cost of each finished thread is shown under its report.

To look around with placeholder data, no key and no cost:

```
uvx manyminds --demo
```

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
