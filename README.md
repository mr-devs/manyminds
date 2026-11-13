# manyminds

**Status: early alpha.** The core loop works on real models: paste text, get leads, research
them in parallel, read their findings and one report on them all, ask about what was found, and come back to saved checks
later. Settings and key storage are still to come. See
[`PLAN.md`](https://github.com/mr-devs/manyminds/blob/main/PLAN.md) for what is done and what is
next.

## What it is

A Python app that helps you check claims you find on the web. It runs on your own machine with
your own [OpenRouter](https://openrouter.ai) API key, and its only interface is a local
browser app.

Each check is a conversation. You paste a piece of text or a link, with anything you want to
say about how to check it. The app replies with *leads*: specific threads that could be
researched to see whether the text is supported by evidence. Press **Go** on the leads you
care about, reword or remove others, or leave them. Each started lead gets its own research
agent, which runs alongside the others. When an agent finishes, its findings appear in the
conversation: sources with links and quoted passages, and what it could not find out. Once
every lead you started has finished, the conversation writes a single report from all of
them. Open any thread to see what its agent searched for and read.

The conversation continues underneath. Ask it to summarise what the threads found or to
suggest further leads. It answers from the threads' findings first, and can run a quick web
search of its own when they do not hold the answer; it says which is which. What it finds
that way has no check on its links, as a thread's findings do, so start a lead for anything that
matters.

manyminds gathers evidence for you to judge. It does not issue verdicts on what is true.
Findings link to their sources, and any link an agent wrote that its searches never returned
is listed as such. Quotations are not checked against their sources, so read the source
before relying on one.

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

You can paste a screenshot or other image into the box, or attach one with the paperclip.
Attached images are sent to OpenRouter and the model provider, which describes them; they are
saved with the check on your computer and deleted with it.

If a link will not open, as posts on X often will not, the app looks for the same material
elsewhere, such as a mirror or archive. That step is given the link only, not your words.
Images in your text or on the opened pages are shown to the model, which describes what is
visible. The reply lists what was opened and what each image was taken to show, so you can
check it. A description guides what is researched; it is never counted as evidence. Video is
not watched, and a link that needs these extra steps can cost a few cents.

What you paste and what you ask for share one box, so the app cannot tell a request you
typed from one hidden in text you pasted. Such text could steer what the conversation
searches for or opens. It cannot start research or change anything you have saved.

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
The cost of each finished thread is shown under its findings.

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
