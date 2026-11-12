# manyminds: build plan

Status: **approved 2026-11-11**, Phase 0 in progress. Your answers are recorded in [section 9](#9-decisions-on-the-open-questions).
Sources for every documentation claim are in [`docs/references.md`](docs/references.md).
Decision records are in [`docs/decisions/`](docs/decisions/).

Progress is tracked in the [milestone table](#5-milestones); it is updated as each milestone completes.

---

## 1. Where the brief and current documentation disagree

These are the points where current docs change what the brief assumed. Each has a proposed
correction.

| # | Finding | Proposed correction |
|---|---|---|
| 1 | **NiceGUI's default host is `0.0.0.0`**, not localhost, and `reload=True` is the default. | Always pass `host="127.0.0.1"`, `reload=False`. A test asserts both. Add a Host-header check so a hostile web page cannot reach the app by DNS rebinding. |
| 2 | **NiceGUI 4.0.0 was released on 2026-11-04** (one week ago). It needs Python >= 3.11 and removes everything deprecated in 3.x. | Start on 4.x so we never migrate, pinned `nicegui>=4.0,<5`. Fallback is 3.19. **Decided: 4.x.** |
| 3 | **Local uv is 0.10.2; current is 0.13.7**, three breaking minor series later. On 0.12+ `uv init` creates a packaged `src/` project with the `uv_build` backend by default, and on 0.13 an unpinned project defaults to Python 3.15. | **Done: uv is now 0.13.7.** Pin `.python-version` to 3.13 and set `requires-python = ">=3.11"`. |
| 4 | **`astral-sh/setup-uv` has had no floating major tags since v8.** `@v10` does not resolve. | Pin every GitHub Action to a full commit SHA with a version comment. I will verify each SHA with `gh api` before committing rather than trusting the researched values. |
| 5 | **`uv publish` does not generate attestations.** uv's documented workflow adds `astral-sh/attest-action` (v0.0.7, early) before publishing. | Follow uv's documented workflow, including the attest step. If that step breaks the first release, drop it and publish without attestations; the name claim matters more. |
| 6 | **TestPyPI needs its own account, its own two-factor setup, and its own pending publisher.** The uv docs do not say whether `uv publish` requests the `testpypi` OIDC audience. | **Decided: no rehearsal; go straight to PyPI.** |
| 7 | **pytest has no built-in way to fail on skipped tests.** `strict_xfail` only fails unexpected passes. | A small `conftest.py` gate fails the run on any skip or xfail whose reason does not start with `JUSTIFIED:`. The gate has its own tests. |
| 8 | **OpenRouter's docs are now Responses-API-first** (`POST /api/v1/responses`). Chat Completions is still documented. Citation shape, structured-output shape and usage keys differ between the two. | **Spike done: Responses API.** Its stream shows each search query and reasoning summaries; a Chat Completions stream shows neither. See decision 15. |
| 9 | **Whether structured output can be combined with the web search server tool in one request is not documented.** | **Spike done: it is not reliable** (the schema was silently ignored on three of five model and engine combinations). Research is always two calls. See decision 15. |
| 10 | **`engine: auto` is not uniform.** It uses the provider's native search for OpenAI, Anthropic, Google, xAI and Perplexity models and Exa for everything else. Native search ignores `max_results` and costs more ($10 to $14 per 1,000 searches against $7 for Exa). | **Changed after the spike: the default is `exa`** (owner's decision, 2026-11-12), because native search returns no excerpts to check quotes against. `auto` stays as an option, and the settings text says plainly what each does. See decision 15. |
| 11 | **Structured-output support is per provider endpoint, not per model**, and providers may silently ignore the parameter. | Always send `provider: {require_parameters: true}` with a schema. Models without `structured_outputs` use a prompted-JSON path. Everything is validated by our own schema either way. |
| 12 | **OpenRouter returns some errors with HTTP 200**, both streaming and non-streaming, and a model refusal arrives as a successful response with `finish_reason: "content_filter"`. | The adapter inspects the body, never the status code alone. These cases are in the fixture set from the start. |
| 13 | **The official `openrouter` Python SDK is auto-generated and has had 458 releases in a year** (six on the day I checked). NiceGUI 4 also no longer installs `httpx`. | Use plain `httpx` as a direct dependency and write the small amount of HTTP and SSE handling ourselves. Reconsidered at your request; reasoning in [section 7](#7-dependencies). |
| 14 | **Evidence on strict TDD with agents is mixed.** One practitioner study found it cost 3 to 8.5 times more tokens with no clear quality gain; the best-supported practices are the outcome checks (verified red, no test edits in green, real output as evidence, independent review, mutation testing). | The brief's TDD rules stand as written. I have added the outcome checks and made two of them mechanical. See [section 6](#6-development-workflow). |

---

## 2. Architecture

### 2.1 Repository layout

```
manyminds/
├── PLAN.md  README.md  LICENSE  CLAUDE.md  pyproject.toml  uv.lock  .python-version
├── .github/workflows/        ci.yml  release.yml
├── docs/
│   ├── references.md
│   └── decisions/            one short record per technical choice
├── scripts/
│   └── check_commits.py      enforces the red/green commit rule (section 6)
├── spikes/                   throwaway live-API experiments; never imported, never shipped
├── src/manyminds/
│   ├── __init__.py           __version__ from importlib.metadata
│   ├── cli.py                console entry point: --version, --port, --no-browser, --demo
│   ├── core/                 NO NiceGUI imports (enforced by a test)
│   │   ├── models.py         domain models and enums (pydantic)
│   │   ├── ports.py          ModelClient, KeyStore, ModelCatalog protocols
│   │   ├── errors.py         error taxonomy
│   │   ├── prompts.py        all prompt text, in one place
│   │   ├── events.py         small async publish/subscribe
│   │   ├── jobs.py           JobManager: scheduling, concurrency, retries, recovery
│   │   ├── checks.py         use cases the UI calls (create check, launch leads, ...)
│   │   ├── conversations.py  conversation use cases
│   │   ├── settings.py       typed settings over the store
│   │   ├── secrets.py        keyring-backed KeyStore
│   │   ├── safety.py         URL validation, markdown hardening, grounding checks
│   │   ├── fake.py           FakeModelClient, used by tests and by --demo
│   │   ├── storage/          db.py, migrations.py, repositories.py (stdlib sqlite3)
│   │   └── openrouter/
│   │       ├── transport.py  httpx client, SSE parsing, error mapping
│   │       ├── websearch.py  the ONLY module that knows the server-tool shape
│   │       ├── adapter.py    OpenRouterModelClient implementing ModelClient
│   │       ├── schemas.py    wire-format models, kept apart from domain models
│   │       └── catalog.py    model list and capability lookup
│   └── ui/                   thin NiceGUI layer
│       ├── app.py            build_app(services) and run()
│       ├── theme.py  layout.py
│       ├── pages/            home, check, thread, conversation, settings, welcome
│       └── components/       composer, lead_list, model_picker, report_view, status
└── tests/
    ├── conftest.py           skip/xfail gate, network block, shared fixtures
    ├── unit/                 core logic against the fake
    ├── adapter/              OpenRouter adapter against fixtures/
    ├── adversarial/          injection, malformed and ungrounded reports
    ├── ui/                   NiceGUI User-fixture tests
    ├── live/                 opt-in smoke tests (marker: live)
    └── test_architecture.py  import-boundary and packaging checks
```

### 2.2 Module boundaries

- **`core` never imports `nicegui`.** Two tests enforce this: a static scan of import statements
  under `core/`, and a subprocess that imports `manyminds.core` and asserts `nicegui` is absent
  from `sys.modules`.
- **Only `core/openrouter/` knows OpenRouter exists.** Everything else depends on the
  `ModelClient` protocol in `ports.py`.
- **Only `core/openrouter/websearch.py` knows the `openrouter:web_search` tool shape.** It
  exposes `SearchEngine` (`auto`, `exa`), a function that builds the tool entry, and a function
  that extracts normalised citations and search counts from a response. A change in their beta
  API touches this file and its fixtures.
- **The UI calls use-case functions and subscribes to events.** It holds no business rules. The
  UI is built by `build_app(services)`, so tests pass in a fake model and a temporary database.
- **Events:** `core/events.py` is a plain asyncio publish/subscribe. The UI layer bridges it to
  NiceGUI's `Event` class, which handles per-client context and unsubscribes when a tab closes.

### 2.3 Model layer

```python
class ModelClient(Protocol):
    async def decompose(
        self, text: str, instructions: str, *, count: int, avoid: Sequence[str], model: str
    ) -> Decomposition: ...
    async def research(
        self,
        lead: str,
        source_text: str,
        instructions: str,
        *,
        model: str,
        search: SearchEngine,
        on_progress: ProgressCallback,
    ) -> ResearchResult: ...
    async def converse(
        self,
        context: CheckContext,
        messages: Sequence[Message],
        *,
        model: str,
        search: SearchEngine,
        on_progress: ProgressCallback,
    ) -> Reply: ...
```

`Decomposition` carries a short title for the check plus the leads. `ResearchResult` carries the
validated `Report` (each item already flagged against the search tool's citations) and usage. `avoid` is how
"Generate 5 more" passes the existing leads.

### 2.4 How research output is kept honest

1. Research agents get two tools, `openrouter:web_search` and `openrouter:web_fetch`
   (decision 17, replacing the earlier search-only rule at the owner's request). Links in
   pasted text are opened with the fetch tool before leads are written, held to the sites the
   text itself links to. Calls that write structured output get no tools.
2. Output is validated against our `Report` schema regardless of what the provider promised.
   One repair attempt (a no-tools re-ask that includes the validation errors) is allowed; after
   that the job fails with `invalid_output`.
3. **Grounding check.** Each evidence URL is compared with the URLs the search tool returned in
   that same request. Evidence whose URL the tool never returned is kept but flagged
   `grounded = false` and shown with a visible "not found in search results" label. Where the
   tool returned an excerpt, the quote is checked against it and flagged the same way.
4. **Rendering.** Model text is shown as plain text. It is never rendered as HTML or markdown
   and no image is ever loaded from it, because an injected instruction could otherwise make
   the model emit an image URL that leaks the pasted text when the browser fetches it. Links
   are limited to `http` and `https` and open in a new tab. Model text is never passed to
   `ui.html`, `ui.markdown`, `.props()` or `run_javascript`.
5. Nothing the model outputs starts work. Proposed leads always wait for the user's **Go**.

### 2.5 Runtime behaviour

- `ui.run(root, host="127.0.0.1", port=<free port>, reload=False, show=True)`.
- Single-page routing with `ui.sub_pages`, so the sidebar stays in place:
  `/`, `/check/{id}`, `/check/{id}/thread/{id}`, `/check/{id}/chat/{id}`, `/settings`, `/welcome`.
- Data lives in the platform data directory (`platformdirs`), overridable with
  `MANYMINDS_DATA_DIR`. NiceGUI's own storage directory is pointed there too, so nothing is
  written to the working directory.
- `--demo` runs the whole app on the built-in fake model: no key, no network, no cost.

---

## 3. Data models

All ids are UUID4 strings. All timestamps are UTC ISO 8601. Enums are stored as text.

**Check**

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `title` | str | From decomposition; falls back to the first 60 characters of the text. User can rename. |
| `source_text` | str | The pasted text, stored verbatim. Required, non-empty. |
| `instructions` | str | Custom instructions; may be empty. |
| `created_at`, `updated_at` | datetime | |

**Lead** (an editable row before research starts)

| Field | Type | Notes |
|---|---|---|
| `id`, `check_id` | str | |
| `text` | str | Editable while `state = draft`. Non-empty after trimming. |
| `position` | int | Order in the list. |
| `origin` | enum | `generated`, `manual`, `conversation` |
| `source_message_id` | str or null | Set when a conversation proposed it. |
| `state` | enum | `draft`, `launched`, `dismissed` |
| `created_at` | datetime | |

Draft leads are persisted, so a half-edited list survives a restart.

**Thread** (a launched lead)

| Field | Type | Notes |
|---|---|---|
| `id`, `check_id`, `lead_id` | str | One thread per launched lead. |
| `lead_text` | str | Frozen copy of the lead text at launch. |
| `created_at` | datetime | |
| `status` (derived) | | Computed from its jobs: `queued`, `working`, `finished`, `failed`, plus counts such as "2 of 3 finished". Never stored. |

**Job** (one per thread and model)

| Field | Type | Notes |
|---|---|---|
| `id`, `thread_id` | str | |
| `model` | str | OpenRouter model id. |
| `status` | enum | `queued`, `running`, `done`, `failed` |
| `search_engine` | enum | `auto` or `exa`, copied from settings at launch. |
| `instructions` | str | Copied from the check at launch. |
| `attempt` | int | Starts at 1; incremented on retry. |
| `error_kind` | enum or null | `auth`, `credits`, `rate_limit`, `timeout`, `provider`, `refusal`, `invalid_output`, `interrupted`, `cancelled`, `unknown` |
| `error_message` | str or null | Human-readable, with the key and headers never included. |
| `usage` | JSON or null | Token counts, search count, and reported cost as returned. Shown under the finished report. |
| `created_at`, `started_at`, `finished_at` | datetime | |

**JobEvent** (live progress): `id`, `job_id`, `seq`, `kind` (`started`, `searching`,
`sources_found`, `writing`, `retrying`, `finished`, `failed`), `detail` (for example the search
query), `created_at`.

**Report** (one per finished job)

| Field | Type | Notes |
|---|---|---|
| `id`, `job_id` | str | |
| `summary` | str | Neutral account of what the search found. Describes the evidence; draws no conclusion about the claim. Required. |
| `evidence` | list[EvidenceItem] | May be empty when nothing relevant was found; `undetermined` then says so. |
| `undetermined` | str | What could not be established. Required, non-empty. |
| `created_at` | datetime | |

There is **no verdict and no confidence level** (your decision, replacing the brief's fixed
scale). A report is structured evidence the user reviews and judges for themselves. The
prompt and schema give the model no field in which to rule on the claim, and a test asserts
the schema has none.

**EvidenceItem**

| Field | Type | Notes |
|---|---|---|
| `id`, `report_id`, `position` | | |
| `url` | str | Required. `http` or `https` only. |
| `title` | str or null | |
| `quote` | str | Required, non-empty, length-capped. |
| `stance` | enum | `supports`, `undermines`. Describes how this one passage bears on the lead, so evidence can be grouped. It is not an overall judgement. |
| `grounded` | bool | URL was among the search tool's results for this job. |
| `quote_matched` | bool or null | Quote found in the returned excerpt; null when no excerpt was returned. |

*Superseded by decision 18: a check has one conversation, stored as `Message` rows (see
milestone 1d). The design below was not built.*

**Conversation**: `id`, `check_id`, `title` (from the first user message), `model`,
`created_at`, `updated_at`.

**Message**

| Field | Type | Notes |
|---|---|---|
| `id`, `conversation_id`, `seq` | | |
| `role` | enum | `user`, `assistant` |
| `status` | enum | `complete`, `pending`, `failed` |
| `body` | str | The answer text (markdown). |
| `from_reports` | list | References to threads and reports the answer drew on. |
| `new_findings` | list | Each has `claim`, `url`, `quote`, `grounded`. Only filled from a new search. |
| `error_kind`, `error_message` | | Same taxonomy as jobs. |
| `created_at` | datetime | |

Assistant replies are structured (`body`, `from_reports`, `new_findings`, `proposed_leads`) so
the UI labels provenance itself instead of trusting the model's prose to do so. Proposed leads
are stored as `Lead` rows with `origin = conversation` and `state = draft`.

**Settings** (key-value table, typed in code)

| Key | Default | Notes |
|---|---|---|
| `decompose_model` | `openai/gpt-6-luna` | Fast and cheap; every endpoint supports structured output. Checked against the live catalogue at startup. |
| `research_models` | last used | List of model ids. |
| `conversation_model` | last used | |
| `search_engine` | `exa` | `auto` or `exa`. |
| `max_concurrent_jobs` | 6 | |
| `job_timeout_seconds` | 300 | |
| `disclosure_acknowledged_at` | null | Set during first-run onboarding. |

The API key is **not** a setting. It lives in the OS keychain under service `manyminds`. An
`OPENROUTER_API_KEY` environment variable is read as an override (for headless Linux and live
tests) and is never written anywhere.

Schema changes use numbered migrations tracked with SQLite's `PRAGMA user_version`.

---

## 4. Phase 0: repository and PyPI name

Checked today: `gh` is authenticated as `mr-devs` with `repo` scope, and `manyminds` returns 404
on both PyPI and TestPyPI, so the name is currently free.

Steps marked **PAUSE** wait for you.

1. **Upgrade uv** to the current release. Done: 0.13.7.
2. **Initialise** with `uv init --package`, `requires-python = ">=3.11"`, `.python-version` 3.13,
   console script `manyminds = "manyminds.cli:main"`, classifier `Development Status :: 2 -
   Pre-Alpha`, description marked pre-alpha. Author metadata is your name only, with no email.
3. **Dev tooling:** pytest, pytest-asyncio, ruff, mypy (strict). pytest configured with
   `strict = true`. Add the skip/xfail gate and `scripts/check_commits.py`, each test-first.
4. **0.0.1 behaviour, test-first:** `manyminds --version` prints the version; bare `manyminds`
   prints the version and a short pre-alpha notice. A test asserts `__version__` equals
   `importlib.metadata.version("manyminds")`. No NiceGUI dependency in 0.0.1: it should be
   exactly what it says it is.
5. **Licence:** MIT, with your name as copyright holder.
6. **Docs:** README (what it is, pre-alpha status, the data-flow disclosure), `.gitignore`,
   `CLAUDE.md` (conventions and TDD rules, kept under 200 lines), this plan, references,
   decision records.
7. **Repository:** `git init`, first commits, then
   `gh repo create manyminds --public --source . --push`.
8. **CI (`ci.yml`)** on every push and pull request: `uv lock --check`, `uv sync --locked`,
   `ruff check`, `ruff format --check`, `mypy`, `pytest` on Python 3.11 to 3.14, the commit
   rule check, and a build smoke test (`uv build`, install the wheel in isolation, run
   `manyminds --version`). Confirm it passes on GitHub.
9. **Release workflows:**
   - `release.yml`: triggered by a `v*` tag. A build job (`uv build`, smoke-test wheel and
     sdist, check the tag matches the package version) and a separate publish job with
     `id-token: write`, environment `pypi`, attestations, then `uv publish`.
   - Create the GitHub environment `pypi` with you as required reviewer, so no release can
     publish without your click.
10. **PAUSE: your steps on pypi.org.**
    1. Create or sign in to your account at https://pypi.org and verify your email.
    2. Turn on two-factor authentication (generate recovery codes first; PyPI requires this).
    3. Go to https://pypi.org/manage/account/publishing/ and add a pending publisher under the
       GitHub tab with exactly these values:

       | Field | Value |
       |---|---|
       | PyPI Project Name | `manyminds` |
       | Owner | `mr-devs` |
       | Repository name | `manyminds` |
       | Workflow name | `release.yml` |
       | Environment name | `pypi` |

    4. Tell me when done. The pending publisher does not reserve the name, so we release
       straight after.
11. **PAUSE: release.** I re-check that `manyminds` is still free on PyPI and show you the
    result. On your go-ahead I tag `v0.0.1` and push. You approve the `pypi` environment run in
    GitHub. I then verify with `uvx manyminds` and `uv tool install manyminds` in a clean
    environment.
12. Update this plan and move to milestone 1.

**Outcome (2026-11-11):** done. `manyminds 0.0.1` is on PyPI and `uvx manyminds` works. At
your request the first upload was made from this machine with your `UV_PUBLISH_TOKEN`, not
through the release workflow, so no pending publisher was needed. Still to do before the next
release: add a trusted publisher to the now-existing project at
https://pypi.org/manage/project/manyminds/settings/publishing/ (owner `mr-devs`, repository
`manyminds`, workflow `release.yml`, environment `pypi`). Until then `release.yml` cannot
publish, and the `v0.0.1` tag's workflow run was cancelled for that reason.

**Done when:** the public repo exists, CI is green, and `uvx manyminds` prints
`manyminds 0.0.1` and the pre-alpha notice from the real PyPI.

---

## 5. Milestones

Every milestone ends in something you can run, a milestone review by a fresh subagent, and an
update to this table.

| # | Milestone | Release | Status |
|---|---|---|---|
| 0 | Repository and PyPI name | 0.0.1 | **done 2026-11-11** |
| 1a | Walking skeleton on the fake model | | **done 2026-11-11** |
| 1b | Real research through OpenRouter | 0.1.0a1 | done; release pending |
| 1c | Saved checks, sidebar, lead editing, redesign, lead prompt (owner's request, 2026-11-12) | | done |
| 1d | The check as one conversation; a Go on each lead (owner's request, 2026-11-12; decision 18) | | done |
| 2 | Full lead-list controls | | partly done in 1c and 1d |
| 3 | Home, check page, persistence across restarts | 0.1.0a2 | not started |
| 4 | Multiple models per lead | | not started |
| 5 | Settings, key management, search-engine setting | | not started |
| 6 | Error handling and retries | | not started |
| 7 | First-run onboarding and disclosure | 0.1.0b1 | not started |
| 8 | Conversations | | done differently in 1d (decision 18) |
| 9 | Leads from conversations | | done in 1d |
| 10 | Hardening | 0.1.0 | not started |

Adversarial tests are written in the milestone that introduces the behaviour they attack, not
saved for the end.

### Milestone 1a: walking skeleton on the fake model

The smallest end-to-end path, with no key and no network.

**Tests first**
- Domain models: a report without `undetermined` is rejected; evidence without a quote or URL
  is rejected; a non-http URL is rejected; the report schema has no verdict, rating or
  confidence field.
- `decompose` through the fake returns at most 10 non-empty, non-duplicate leads.
- Launching N leads with one model creates N threads and N jobs, all `queued`.
- Jobs run concurrently up to the limit (asserted with a fake that records overlap).
- Status moves `queued` to `running` to `done`, each change is persisted and published.
- One job raising does not stop the others; it ends `failed` with an error kind.
- A finished report can be read while other jobs are still running.
- Storage round-trips every model; migrations apply to an empty database.
- Architecture tests: `core` does not import `nicegui`.
- UI (User fixture, fake model): paste text and generate leads; edit a lead; remove a lead;
  press Go; land on the check page; thread rows show statuses that change; open a finished
  thread and see the summary, evidence grouped by stance with a clickable URL and quote for
  each item, and the undetermined statement.
- The app is started with `host="127.0.0.1"` and `reload=False`.

**Accepted when** all of the above pass with no network, and the demo runs.

**You will see:** `uv run manyminds --demo` opens the browser. You paste text, get leads, edit
and remove some, press Go, and watch threads go from queued to working to finished at different
speeds, with one scripted failure that leaves the rest untouched.

**Outcome (2026-11-11).** Merged; 241 tests pass offline. After the first review the
interface was redesigned, each thread gained a full, followable agent transcript, and a second
code review's ten findings were fixed.
Checked by hand in a real browser: generate, edit, Go, six agents at once with four queued,
live status changes, the scripted failure leaving the rest untouched, and a report opening
with grouped evidence and links. No browser console errors.

The independent review found no overfitting. It found four bugs, all fixed test-first: a
failed write left the database connection stuck in a transaction; removing a launched lead
from a second tab deleted its thread and report; a storage error inside a job left it
"running" forever; and clearing a lead's box then pressing Go researched the old wording.

Differences from this plan, for the record:

- **Model text is shown as plain text, not sanitised markdown.** Nothing a model writes is
  rendered as HTML or markdown anywhere, which is stricter than planned. Markdown can be
  revisited for conversations in milestone 8.
- **Database calls run on the event loop**, not in a worker thread. They are sub-millisecond
  for a single user; revisit if that stops being true.
- **The check page hosts the lead editor.** After "Generate leads" you land on the check page,
  edit there, and press Go there, so a half-edited list survives a reload.
- **Bare `manyminds` still prints the pre-alpha notice.** Only `--demo` starts the app until
  milestone 1b makes the real one usable.
- **Deferred to the milestone that needs them:** the on-disk data directory and NiceGUI
  storage location (3), `Job.usage` (1b), lead `dismissed` state and `source_message_id` (9).

### Milestone 1b: real research through OpenRouter

Begins with a **live spike** in `spikes/`, using the `OPENROUTER_API_KEY` exported in your
shell profile, a few cents of API use, to settle findings 8 and
9 and to capture real responses. Captured responses are scrubbed and become adapter fixtures.
Spike code is throwaway and is not covered by the TDD rule; nothing in `src/` is written from it
without a failing test first.

**Tests first** (against fixtures, using `httpx.MockTransport`; no new dependency)
- Request shape: correct endpoint and headers; exactly one tool, `openrouter:web_search`;
  `engine` follows the setting; `provider.require_parameters` is set with a schema.
- The API key never appears in logs, exceptions, `repr`, or the database (a test greps for it).
- Decompose parses a valid structured response and rejects a malformed one.
- Research parses a valid report, extracts citations, and sets `grounded` per evidence item.
- Malformed JSON, missing fields, and wrong enum values trigger one repair attempt, then
  `invalid_output`.
- HTTP 401, 402, 403, 408, 429, 502, 503 map to the right error kinds; `Retry-After` is read.
- An error body with HTTP 200, a mid-stream error, and an empty completion are each handled.
- A refusal (`finish_reason: content_filter`) becomes a `refusal` failure with the model's text.
- Timeouts become `timeout`.
- SSE parsing ignores keep-alive comment lines and handles the final usage chunk.
- Adversarial: a search result containing "ignore your instructions and..." does not change the
  request we send next or the schema we accept; a report citing a URL the tool never returned
  is flagged ungrounded; evidence with a `javascript:` URL is rejected.
- Live smoke tests (`-m live`, opt-in): one decompose and one research call succeed.

**Accepted when** the default suite passes offline, and the live smoke tests pass with your key.

**You will see:** with `OPENROUTER_API_KEY` set in your shell, `uv run manyminds` does the same
flow as 1a against real models: real leads within a few seconds, real parallel research with
one model, live progress lines ("searching: ..."), and reports with clickable sources.

**Milestone 1b as built (2026-11-12)**

- The spike settled the open questions; see decision 15. Research is two calls on the
  Responses API, and the search engine defaults to `exa`.
- Refusals are detected the Responses way (a `refusal` content part, or status `incomplete`
  with reason `content_filter`), not through `finish_reason`.
- HTTP 403 is treated as a refusal, because OpenRouter uses it for moderation blocks.
- A report that breaks the schema anywhere (an extra `verdict` field, a `javascript:` link,
  a missing quote) is rejected whole, after one repair attempt.
- Each finished job records tokens, searches and cost, shown under its report. Failed jobs do
  not record what they used.
- Bare `manyminds` starts the app when `OPENROUTER_API_KEY` is set and explains what to do
  when it is not. The research models offered are a fixed list until the model catalogue
  (milestone 4).
- **Not built here, moved to the milestone that needs them:** the prompted-JSON path for
  models without structured output (4, with the catalogue); automatic retries using
  `Retry-After` (6; the adapter already exposes the value); a `ModelCatalog`.
- Checked by hand in a browser: one real check end to end (lead generated, two searches,
  sources listed, thinking shown, report with five grounded quotes, usage line).

### Milestone 1c: saved checks, lead editing, redesign (owner's request, 2026-11-12)

Built ahead of the original order at the owner's request, taking parts of milestones 2 and 3.

- Checks are saved in the user's data folder and listed in the sidebar, newest first
  (decision 16). Work cut off by a restart is marked interrupted and can be tried again from
  its thread. A check can be deleted.
- Draft leads are numbered, visibly editable fields. **Add a lead** is always available,
  including after research has started. A list holds 25 leads at most.
- Wider column (880px), stronger section headings, tinted panels for given text, thread
  cards, and reports with evidence colour-ruled by which way it cuts.
- The lead prompt now asks for checkable, single, self-contained, faithful claims, ranked by
  how much the text depends on them and how much it matters if they are wrong.
- **Still to do from milestones 2 and 3:** Enter to generate, "Generate 5 more", reordering,
  renaming a check, "Resume all interrupted", and live updates of the sidebar across tabs.

### Milestone 1d: the check as one conversation (owner's request, 2026-11-12)

Recorded in decision 18. It replaces the separate lead editor and Threads list, and delivers
milestones 8 and 9 in a different shape.

- The check page is a chat. The first message is what the user pasted; the reply holds the
  leads. There is one box and no separate instructions field. Enter sends and Shift+Enter
  starts a new line.
- Each lead has its own **Go**, can be reworded or removed, or left alone. A started lead
  stays in place and becomes the way into its thread, with a live status. **Research all**
  starts every lead in a list that has text. **Add a lead** is under every list.
- Later messages are answered by the chat model from the conversation, the leads and the
  finished reports. It has no search and gives no verdict. It may propose leads, which wait
  as rows; nothing starts by itself.
- New data: `Message` (`id`, `check_id`, `seq`, `role`, `status`, `body`, `error_message`,
  `created_at`) and `Lead.message_id`. Schema version 3; older checks gain a conversation.
- **Not done:** recording the cost of chat replies; retrying a failed reply with one press
  (send the message again); choosing the chat model (it is the lead-generation model);
  "Generate more leads" as a button (ask for more in the chat).

### Milestone 2: full lead-list controls

**Tests first**
- Enter generates leads; Shift+Enter inserts a newline. (Key handling runs in the browser, so
  the automated test covers the handler wiring and I verify the keystrokes in a real browser.)
- Custom instructions are passed to decomposition and stored on the check.
- **+** adds an empty editable row; saving an empty row removes it.
- Edits persist; **x** removes the row; there are no checkboxes.
- **Generate 5 more** appends five leads, passes existing leads as `avoid`, and drops any
  returned lead that duplicates an existing one after normalisation (case, whitespace,
  punctuation).
- Go is disabled with zero leads or zero models, and launches exactly the rows that remain.
- A list holds at most 25 leads. At 25, **+** and **Generate 5 more** are disabled and a
  message tells the user to launch these and open further leads separately. "Generate 5
  more" near the limit adds only as many as fit.
- Draft leads survive a restart.

**You will see:** the complete lead editor from the brief, working in demo mode and live.

### Milestone 3: home, check page, persistence

**Tests first**
- Home lists checks newest first; the sidebar shows the same list; clicking opens the check.
- Check page shows title, original text, an input box, and separately labelled **Threads** and
  **Conversations** lists (conversations empty for now).
- Thread rows show lead, status and time, and update live without a page reload.
- Leads can be added to an existing check from the check page and launched.
- After a restart: checks, leads, threads, jobs and reports are all still there.
- Jobs that were `queued` or `running` at shutdown are marked `failed` with kind
  `interrupted`. Nothing restarts by itself; each has a Resume action, and the check page
  offers "Resume all interrupted".
- Rename and delete a check; delete removes its threads, jobs and reports.
- Two browser tabs on the same check both receive live updates.

**You will see:** start research, quit the app mid-run, start it again, and find everything
where you left it, with interrupted work clearly marked.

### Milestone 4: multiple models per lead

**Tests first**
- The catalogue loads from OpenRouter's model list (fixture), filtered to models that support
  tools, and is cached with a fallback when offline.
- The picker allows one or more models and is searchable.
- L leads and M models create L threads and L x M jobs.
- A thread shows one tab per model; each tab shows that model's progress or report.
- Thread status aggregates: "2 of 3 finished", working while any job is running, failed only
  when all failed, with partial failure shown as such.
- One model failing does not affect the same lead's other models.

**You will see:** pick three models, press Go, and compare their reports for one lead in tabs.

### Milestone 5: settings, key management, search engine

**Tests first**
- The key is saved to and read from the keychain through `KeyStore` (fake keyring in tests);
  it is never written to the database, settings, or logs.
- The environment variable overrides the keychain and is never persisted.
- The key is validated against OpenRouter's key endpoint (fixture) with clear results for
  valid, invalid, and unreachable.
- The settings page shows only a masked key, and supports replace and remove.
- Default models for leads, research and conversations are stored and used.
- Search engine `auto` and `exa` each produce the right tool parameters, are copied onto each
  job at launch, and are shown on the report.
- No keychain backend available: a clear message pointing to the environment variable.

**You will see:** a settings page; paste your key once and it is remembered across restarts
with nothing in plaintext on disk; switch search engine and see it on new reports. CI gains
macOS and Windows runs here.

### Milestone 6: error handling and retries

**Tests first**
- Transient failures (`rate_limit`, `timeout`, `provider`) retry automatically with capped,
  jittered backoff, honouring `Retry-After`, up to a limit (fake clock; no real sleeping).
- Permanent failures (`auth`, `credits`, `refusal`, `invalid_output`) do not auto-retry.
- A failed job can be retried by hand; `attempt` increments; earlier events are kept.
- A running job can be cancelled; it ends `failed` with kind `cancelled`.
- An `auth` failure pauses queued jobs and prompts for the key instead of failing them all.
- Each error kind shows a specific, plain message and a suitable action.
- The per-job timeout is enforced.

**You will see:** failed threads say why, in plain words, and offer Retry. A rate-limited run
recovers by itself.

### Milestone 7: first-run onboarding and disclosure

**Tests first**
- With no key and no acknowledgement, every route leads to the welcome page.
- The welcome page states that pasted text is sent to OpenRouter, the chosen model providers
  and the search engine, and that orchestration is local but inference is not.
- Research cannot start until the disclosure is acknowledged and a valid key exists.
- The same disclosure appears near the input box and in the README (a test checks the README
  contains it).
- After onboarding, the user lands on Home and is not asked again.

**You will see:** a clean first run after `uvx manyminds` on a machine that has never run it.

### Milestone 8: conversations

**Tests first**
- The check page input starts a conversation; it appears under **Conversations** and persists.
- The context sent to the model contains the original text and all finished reports, and
  excludes failed and unfinished ones.
- The request has the same search and fetch tools as research, using the same engine setting.
- Replies are structured; the UI shows "From the reports" and "From a new search" as separate
  labelled sections.
- A new finding without a URL or quote is rejected (one repair attempt, then the reply is
  marked failed); ungrounded findings are flagged.
- Reports finishing mid-conversation are included from the next turn.
- Errors in a reply are shown in place and the turn can be retried.
- Adversarial: injected instructions inside a report's quoted evidence, or inside new search
  results, do not change the tool list, the schema, or cause any action.

**You will see:** ask a question about the evidence, get an answer that says which parts come
from which thread and which come from a fresh search, with sources.

### Milestone 9: leads from conversations

**Tests first**
- A reply can carry proposed leads; they render as the same editable rows with a Go button.
- Nothing runs until Go; dismissed proposals stay dismissed after a restart.
- Go creates threads on the same check; they appear in the Threads list with live status.
- Proposals that duplicate existing leads are dropped.
- Adversarial: a search result instructing the model to "start research on X" produces, at
  most, a proposal row. It never starts a job.

**You will see:** ask something the reports cannot answer, get proposed leads, edit them, press
Go, and watch new threads start.

### Milestone 10: hardening

- Mutation testing on `core/`, with surviving mutants treated as missing tests.
- A full adversarial pass and a manual security review of rendering paths.
- Keyboard and screen-reader pass; empty, loading and error states; narrow windows.
- README and screenshots; `0.1.0` released.

---

## 6. Development workflow

The rules from the brief stand as written and go into `CLAUDE.md`. Research into how agents
fail at TDD (see references) adds the following.

**The cycle**
1. **Test list.** Before a milestone, write its behaviours as a checklist from this plan, not
   from an implementation idea. Work one item at a time.
2. **Red.** Write the tests. Run them. They must fail because the behaviour is missing (an
   assertion, or the import of a module that does not exist yet), not because of a mistake in
   the test. I show you the failing output. A new test that passes
   immediately is a defect in the test.
3. **Commit the failing tests** alone (`test: ...`).
4. **Green.** Smallest implementation. No special-casing of test inputs, and no weakening,
   skipping or deleting a test just to get to green. Tests that are wrong, or that pin a
   requirement you have changed, are edited in their own `test:` commit and reported to you
   (your decision of 2026-11-11; no pre-approval is needed).
5. **Refactor** on green, then commit (`refactor: ...`), separately from behaviour changes.
6. **Milestone review** by a fresh, read-only subagent that has not seen the implementation
   work. It gets the spec section and the diff, and is asked two things: does the code overfit
   the tests, and do the tests cover the spec. It is told to skip style.

**Rules that guard against known agent failure modes**
- Expected values in tests are written by hand, never computed by calling the code under test.
- Fakes and mocks only at real boundaries: HTTP transport, keychain, clock. Never assert on a
  mock's own behaviour.
- "Tests pass" is always accompanied by the command and its real output.
- The full suite runs after every green step.

**Mechanical enforcement** (kept deliberately small)
- `scripts/check_commits.py`, run in CI and locally: a `test:` commit may only touch `tests/`;
  any other commit may not modify or delete existing test files. Every change to the tests is
  therefore its own commit.
- The skip/xfail gate: CI fails on any skipped or expected-failure test whose reason does not
  begin with `JUSTIFIED:`.
- The default suite blocks network access; a test that opens a socket fails.
- Live tests are deselected by marker (`-m "not live"`), not skipped, so the gate stays strict.

**Testing the LLM parts**
- Core logic runs against `FakeModelClient`. Unit tests check our code, not answer quality.
- The adapter runs against fixtures: captured real responses, scrubbed of keys and headers,
  plus hand-written malformed, timeout, rate-limit and refusal cases. Fixtures are re-captured
  when prompts or the tool shape change.
- Injection tests put the hostile text where it would really arrive (in search results and in
  quoted evidence) and define the expected outcome before the test is run.

**UI testing limit, stated plainly:** NiceGUI's `User` fixture does not run JavaScript, so
browser-side behaviour (Enter against Shift+Enter, layout, focus) cannot be covered there. I
will check those in a real browser at each milestone and tell you what I checked. If that
proves too thin, the option is a few Selenium `Screen` tests, which would add a dependency and
Chrome to CI; I would ask first.

**Branches:** one branch and pull request per milestone, so CI and the milestone review act as
a gate before merge.

---

## 7. Dependencies

The brief asks me to tell you before adding any. This is the full proposed set.

| Package | Why | When |
|---|---|---|
| `nicegui` | The interface. | 1a |
| `pydantic` | Schema validation for reports and wire formats. Already installed by NiceGUI; declared because we use it directly. | 1a |
| `platformdirs` | Correct per-OS data directory. | 1a |
| `httpx` | OpenRouter HTTP and streaming. | 1b |
| `keyring` | OS keychain. | 5 |
| dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy` | Tests, lint, format, types. | 0 |
| dev: `mutmut` | Mutation testing at milestone 10. | 10 |

Storage uses the standard library's `sqlite3`, with no ORM. Type checking uses mypy in strict
mode: Astral's `ty` is still beta with no stability guarantee for its diagnostics, so it is a
poor CI gate today.

**Why not the official `openrouter` SDK** (looked at again on 2026-11-11, version 1.3.165):

- In its favour: it has typed classes for the `openrouter:web_search` tool, it tracks the API
  automatically, and its only dependencies beyond ours are `httpcore` and `jsonpath-python`.
- Against: it is a generated client of 1,231 files for an API of which we call three endpoints
  (one streaming generation call, the model list, key info). It has had 459 releases in twelve
  months, including several on the day this plan was written, so reviewing what an update
  changes is impractical. Its strict response models would raise inside the SDK when the beta
  search tool changes shape, where our own parser can be lenient about fields we do not use
  and precise about the ones we do. Errors that arrive with HTTP 200 need our own handling
  either way.
- Decision: plain `httpx`. Because only `core/openrouter/` touches the network, switching to
  the SDK later would change that one package and nothing else. The milestone 1b spike will
  make the same call both ways, and I will tell you if the SDK turns out to be clearly
  better.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| **The search tool is in beta** and its shape may change. | One module owns it. Fixture tests pin the shape we rely on. A live smoke test catches drift. Version and date of the docs we built against are recorded. |
| **Structured output differs across models and providers.** | `require_parameters`; a prompted-JSON path for models without support; our own validation always; one repair attempt; a clear `invalid_output` failure. The picker marks models without structured-output support. |
| **Prompt injection** from web pages, and second-hand through reports fed to conversations. | Search tool only. Retrieved text framed as data. Schema-validated output. Grounding flags. Images stripped and link schemes restricted. No model output can start work. Adversarial tests per milestone. This reduces the risk; it does not remove it, and the README will say so. |
| **Structured output with the search tool does not work reliably in one request** (confirmed by the spike). | Research is two calls: search, then a no-tools formatting call. See decision 15. |
| **Hallucinated quotes or sources.** | Grounding and quote-match flags shown to the user; every item links to its source so the user can check. |
| **The tool being read as an arbiter of truth.** | Reports carry no verdict or confidence at all: only a neutral summary, quoted evidence with links, and a mandatory statement of what could not be determined. Multiple models are shown side by side, not merged into one answer. |
| **NiceGUI 4.0 is a week old.** | Pin `<5`; lock file; fall back to 3.19 if a blocking bug appears. The thin UI layer limits the cost. |
| **Local web app reachable by other pages or programs on the machine.** | Bind to `127.0.0.1`, random free port, Host-header check. No authentication is added for now; noted in the README. |
| **Keychain unavailable** (headless Linux). | Environment-variable override; clear message. |
| **Cost surprises**, since cost estimation is out of scope. | Concurrency limit, per-job timeout, a cap on searches per job, and the job count shown before Go ("10 leads x 3 models = 30 agents"). |
| **PyPI name taken before we publish.** | Publish 0.0.1 as early as possible; re-check immediately before; release right after the pending publisher is created. |
| **Release tooling churn** (uv 0.x, early attest action). | Pin uv in CI; actions pinned by SHA; build smoke test before publish. |
| **Tests that overfit or prove little.** | The workflow rules above, the fresh-context review, and mutation testing. |
| **Browser-side behaviour untested by the `User` fixture.** | Manual browser checks per milestone, reported explicitly. |

---

## 9. Decisions on the open questions

Answered 2026-11-11.

1. **Licence:** MIT.
2. **NiceGUI:** 4.x.
3. **Verdicts:** none. No verdict scale and no confidence level. Reports are structured
   evidence with cited, clickable sources for the user to judge. This replaces the brief's
   "verdict on a fixed scale, a confidence level".
4. **Branching:** a branch and pull request per milestone.
5. **Live spike:** approved. The key is exported in your shell profile; I read it from the
   environment and never print it.
6. **Interrupted jobs:** marked interrupted; they wait for you to resume.
7. **TestPyPI:** skipped. Straight to PyPI.
8. **Author metadata:** name only.
9. **Dependencies:** approved as listed in section 7, including `mutmut` later. Plain `httpx`
   over the OpenRouter SDK, for the reasons given there.
10. **Lead limit:** 25 per list, with a message to open more leads separately.
