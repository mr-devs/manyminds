# 15. Responses API, and research as two calls

- Status: Proposed (awaiting the owner's answer on the default search engine)
- Date: 2026-11-12

## Context

Milestone 1b began with a live spike (`spikes/`, 18 calls, about $0.18) to settle three
questions the documentation left open: Chat Completions or the Responses API; whether a JSON
schema can be combined with `openrouter:web_search` in one request; and `httpx` or the
`openrouter` SDK. Models used: `openai/gpt-6-luna`, `anthropic/claude-haiku-5.5`,
`google/gemini-3.5-flash-lite`, `deepseek/deepseek-v4-flash`. One claim, one or two searches
per call. Small sample: these are observations, not guarantees.

## What the spike showed

**Schema and search in one request is not reliable.**

| Model | Search engine used | Schema obeyed | Search results returned to us |
|---|---|---|---|
| gpt-6-luna | native (OpenAI) | yes | URLs only, and only with `include: ["web_search_call.action.sources"]`; no excerpts |
| gpt-6-luna | `exa` | **no, markdown came back** | URLs, titles and excerpts |
| claude-haiku-5.5 | `auto` (ran as an OpenRouter-run search) | **no** | URLs, titles and excerpts |
| deepseek-v4-flash | `auto` (Exa) | **no** | URLs, titles and excerpts |
| gemini-3.5-flash-lite | native (Google) | yes | nothing; evidence URLs were `vertexaisearch.cloud.google.com` redirects |

The schema was dropped silently, with HTTP 200 and `require_parameters: true` set. The same
happened on both APIs.

**Two calls worked on every model tried.** Call one: search, no schema. Call two: no tools,
strict schema, given the search results and the notes from call one. Three of three runs
returned a valid report; every evidence URL was one the search had returned; 11 of 12 quotes
were found verbatim in the returned excerpt (the twelfth had added quotation marks).

**Native search gives little to check against.** Without a schema, OpenAI's native search
returned citations with a URL (carrying `?utm_source=openai`) and title but no excerpt; Google's
returned no citations; Anthropic's (`engine: native`) ended `incomplete` with none. Non-native
engines return `url_citation` annotations with `url`, `title` and `content` (the excerpt).
Native search also cost more per call here (about $0.011 to $0.016 against $0.008).

**Responses API shows the work; Chat Completions hides it.** A Responses stream emits an output
item per search, with the query and the returned URLs, and reasoning summaries where the model
gives them. A Chat Completions stream of the same call carried only `content` and
`annotations`: no search queries at all. Both report cost in `usage.cost`.

**The SDK works but earns little.** The same streamed call through `openrouter` 1.3.170
succeeded with typed events. It is 1,225 Python files (7.6 MB) and adds `jsonpath-python`. The
raw stream is plain `data:` lines of JSON with about ten event types we care about.

## Decision

1. Use the **Responses API** (`POST /api/v1/responses`), streamed, for every call.
2. **Research is always two calls**: a search call with exactly one tool and no schema, then a
   no-tools formatting call with the strict report schema. Grounding flags are computed from
   the first call's annotations. The single-request path is not used, even where it works.
3. Stay on **plain `httpx`** (decision 3 stands).
4. **Proposed, needs the owner:** default the search engine to `exa`, not `auto`. See below.

## Consequences

- Each lead costs one extra small model call (about $0.0002 to $0.001 in the spike).
- The formatting call sees web text, so it also gets no tools and the data-not-instructions
  framing. Its output is still validated by our own schema, with one repair attempt.
- The "searching: ..." transcript lines and thinking come from Responses stream items. Not
  every model emits reasoning summaries.
- Citation URLs are compared after stripping tracking parameters such as `utm_source`.
- With `auto`, models with native search would produce evidence that cannot be quote-checked,
  and Google models would show redirect links. That is why item 4 proposes `exa` as the default,
  which contradicts the brief's "auto by default".
