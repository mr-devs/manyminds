# References

Sources relied on for `PLAN.md`, gathered on 2026-11-11.

**How these were gathered.** Four research agents read the sources and reported back; the
project plan was written from their reports. Items marked **unverified** were either not
confirmed on a page that was actually opened, or are inferences. Short quotations from the TDD
sources came through a summarising fetch tool and should be re-checked against the original
before being repeated anywhere. Version numbers and model ids change quickly; re-check before
relying on them.

## uv

- Releases and changelog (0.13.7 current; 0.11, 0.12, 0.13 breaking changes):
  https://github.com/astral-sh/uv/releases ,
  https://github.com/astral-sh/uv/blob/0.13.7/CHANGELOG.md
- `uv init` and what it generates; packaged applications by default since 0.12:
  https://docs.astral.sh/uv/concepts/projects/init/ ,
  https://docs.astral.sh/uv/reference/cli/#uv-init
- `uv_build` backend and its version bound: https://docs.astral.sh/uv/concepts/build-backend/
- Dependency groups and `uv add --dev`:
  https://docs.astral.sh/uv/concepts/projects/dependencies/#development-dependencies
- Locking, `--locked`, `uv lock --check`: https://docs.astral.sh/uv/concepts/projects/sync/
- Committing `uv.lock`; `.python-version`: https://docs.astral.sh/uv/guides/projects/
- Building and publishing, `uv version`, TestPyPI index config, `--no-sources`:
  https://docs.astral.sh/uv/guides/package/
- `uv publish` reference (trusted publishing auto-detection, attestations):
  https://docs.astral.sh/uv/reference/cli/#uv-publish
- GitHub Actions integration and the recommended release workflow:
  https://docs.astral.sh/uv/guides/integration/github/
- Tools (`uvx`, `uv tool install`): https://docs.astral.sh/uv/guides/tools/ ,
  https://docs.astral.sh/uv/concepts/tools/
- `astral-sh/setup-uv` releases (no floating major tags since v8):
  https://github.com/astral-sh/setup-uv/releases
- Astral's trusted publishing example repository:
  https://github.com/astral-sh/trusted-publishing-examples
- **Unverified:** whether `uv publish` requests the `testpypi` OIDC audience automatically.

## PyPI publishing

- Pending publishers do not reserve a name:
  https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- Using a trusted publisher; `id-token: write` at job level:
  https://docs.pypi.org/trusted-publishers/using-a-publisher/
- Troubleshooting (reusable workflows unsupported):
  https://docs.pypi.org/trusted-publishers/troubleshooting/
- Pending publisher form field labels (from the site template):
  https://github.com/pypi/warehouse/blob/main/warehouse/templates/manage/account/publishing.html
- Mandatory two-factor authentication:
  https://docs.pypi.org/your-account/two-factor-authentication/
- Project name rules: https://docs.pypi.org/project-management/choosing-a-name/
- Attestations: https://docs.pypi.org/attestations/producing-attestations/
- Publishing with GitHub Actions (environment with manual approval):
  https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
- TestPyPI (separate account): https://packaging.python.org/en/latest/guides/using-testpypi/
- Runtime version access: https://packaging.python.org/en/latest/discussions/versioning/ ,
  https://packaging.python.org/en/latest/discussions/single-source-version/
- Name availability was checked directly on 2026-11-11: `https://pypi.org/pypi/manyminds/json`
  and the TestPyPI equivalent both returned 404.

## pytest, ruff, type checkers

- pytest `strict` option and configuration in `pyproject.toml`:
  https://docs.pytest.org/en/stable/reference/reference.html#confval-strict ,
  https://docs.pytest.org/en/stable/reference/customize.html#pyproject-toml
- Skips and xfails: https://docs.pytest.org/en/stable/how-to/skipping.html
- Exit codes (no code for skips): https://docs.pytest.org/en/stable/reference/exit-codes.html
- pytest-asyncio configuration:
  https://pytest-asyncio.readthedocs.io/en/latest/reference/configuration.html
- ruff configuration: https://docs.astral.sh/ruff/configuration/
- ty status (beta, `0.0.x` versioning): https://github.com/astral-sh/ty ,
  https://docs.astral.sh/ty/configuration/
- **Unverified:** the conftest-hook approach to failing on skips is common practice, not from
  official documentation.

## NiceGUI

The documentation site could not be quoted directly, so the agent read the source files that
generate it, in https://github.com/zauberzeug/nicegui (branch `main`). Each
`website/documentation/content/<name>_documentation.py` renders to
`https://nicegui.io/documentation/<name>`.

- Releases (4.0.0 on 2026-11-04; 3.0 and 4.0 breaking changes):
  https://github.com/zauberzeug/nicegui/releases ,
  https://github.com/zauberzeug/nicegui/releases/tag/v3.0.0 ,
  https://github.com/zauberzeug/nicegui/releases/tag/v4.0.0
- Testing (`User`, `Screen`, plugins, `main_file`, `user_simulation`):
  `website/documentation/content/section_testing.py`, `user_documentation.py`,
  `screen_documentation.py`; source in `nicegui/testing/`
- pytest example project: `examples/pytests/`; multi-user test: `examples/chat_app/`
- `ui.run` parameters and the `0.0.0.0` default host: `nicegui/ui_run.py`;
  configuration and deployment: `section_configuration_deployment.py`;
  `find_open_port`: `nicegui/native/native_mode.py`
- Pages, `ui.sub_pages`, navigation, layout: `section_pages_routing.py`,
  `sub_pages_documentation.py`, `navigate_documentation.py`, `page_layout_documentation.py`;
  examples `single_page_app/`, `modularization/`
- `Event` class and background tasks: `nicegui/event.py`, `event_documentation.py`,
  `nicegui/background_tasks.py`, `section_action_events.py`, `timer_documentation.py`
- Chat components and sanitisation: `nicegui/elements/chat_message.py`, `markdown.py`,
  `html.py`; example `chat_with_ai/`
- Styling and CSS layers: `section_styling_appearance.py`, `DEPENDENCIES.md`
- Security guidance: `section_security.py`
- Bundled LLM reference: `nicegui/llms.md`
- **Unverified:** Enter-submits and Shift+Enter-newline on a textarea is not documented;
  `keydown.enter.exact.prevent` should work from reading the client code but was not seen
  documented or tested. Running through a console script is not documented. The `pytest_plugins`
  route for enabling the testing plugin is not shown in the docs.

## OpenRouter

Pages under https://openrouter.ai/docs, read as markdown, plus live calls to the public models
API.

- Server tools overview and beta status: `/guides/features/server-tools`
- `openrouter:web_search` parameters, engines, pricing: `/guides/features/server-tools/web-search`
- Web search on the Responses API: `/api_reference/responses/web-search`
- Deprecated web plugin and `:online` suffix: `/guides/features/plugins/web-search`,
  `/guides/routing/model-variants/online`
- Structured outputs: `/guides/features/structured-outputs`
- Provider selection and `require_parameters`: `/guides/routing/provider-selection`
- Response healing plugin: `/guides/features/plugins/response-healing`
- Streaming: `/api_reference/streaming`
- Errors: `/api_reference/errors-and-debugging`; limits: `/api_reference/limits`
- API overview (finish reasons, annotations): `/api_reference/overview`
- Chat completion reference: `/api/api-reference/chat/create-a-chat-completion`
- Models: `/guides/overview/models`,
  `/api/api-reference/models/list-all-models-and-their-properties`,
  live `https://openrouter.ai/api/v1/models`
- App attribution headers: `/app-attribution`; quickstart: `/quickstart`
- Python SDK: `/client-sdks/python/overview`, https://pypi.org/pypi/openrouter/json
- Using the OpenAI SDK: `/guides/community/openai-sdk`
- **Unverified:** combining structured output with server tools in one request; whether
  citations arrive in Chat Completions stream chunks; whether `/api/v1/auth/key` still works as
  an alias for `/api/v1/key`; server-tool support on the Messages endpoint. Model quality
  rankings are inference from popularity and recency, not a documentation claim.

## Agent-driven test-driven development

- Anthropic, Claude Code best practices (verification, evidence, fresh-context review, hooks,
  what belongs in `CLAUDE.md`): https://code.claude.com/docs/en/best-practices
- Anthropic, memory and `CLAUDE.md` length: https://code.claude.com/docs/en/memory
- Anthropic, hooks guide (protecting files; shell edits bypass an edit-only matcher):
  https://code.claude.com/docs/en/hooks-guide
- Kent Beck, "Augmented Coding: Beyond the Vibes" (25 Jun 2025), on agents disabling or
  deleting tests, plan files and commit discipline:
  https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes
- Simon Willison, red/green TDD with agents:
  https://simonwillison.net/guides/agentic-engineering-patterns/red-green-tdd/
- Birgitta Böckeler, "TDD in the agent loop" (2026), observed failure modes and a small study
  finding higher cost with no clear quality gain:
  https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html
- Birgitta Böckeler, harness engineering (Apr 2026):
  https://martinfowler.com/articles/harness-engineering.html
- Emily Bache, reply on test lists (23 Sep 2026):
  https://coding-is-like-cooking.info/2026/09/the-last-year-has-changed-everything-i-knew-about-tdd-after-20-years/
- Zhong, Raghunathan, Carlini, "ImpossibleBench" (Oct 2025), measuring test tampering and
  special-casing, and what reduces it: https://arxiv.org/html/2510.20270
- Hora and Robbes (MSR 2026), agents add mocks more often than humans:
  https://arxiv.org/abs/2602.00409
- Alonso, Yovine, Braberman, "TDAD" (Mar 2026), procedural TDD instructions without test
  context increased regressions: https://arxiv.org/abs/2603.17973
- Alexander Opalic, separating test-writer and implementer contexts (30 Nov 2025):
  https://alexop.dev/posts/custom-tdd-workflow-claude-code-vue/
- obra/superpowers, test-driven development skill:
  https://raw.githubusercontent.com/obra/superpowers/main/skills/test-driven-development/SKILL.md
- Thoughtworks Technology Radar, feedback sensors for coding agents (Apr 2026):
  https://www.thoughtworks.com/radar/techniques/feedback-sensors-for-coding-agents
- OpenAI Codex best practices: https://learn.chatgpt.com/guides/best-practices
- Pydantic AI, testing with fake models: https://pydantic.dev/docs/ai/guides/testing/
- LangChain, integration testing with recorded cassettes:
  https://docs.langchain.com/oss/python/langchain/test/integration-testing
- OWASP, LLM prompt injection prevention cheat sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
- **Unverified in an opened source:** committing failing tests as a separate commit (a
  requirement of this project's brief regardless); CI gates on skips and xfails; treating
  coverage as a signal and not a target; Hypothesis specifically as an overfitting check.
