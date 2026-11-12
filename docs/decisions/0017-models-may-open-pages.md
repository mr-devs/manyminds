# 17. Models may open pages as well as search

- Status: Accepted
- Date: 2026-11-12
- Replaces: the "search tool and nothing else" part of decision 10

## Context

The original brief said research agents get the search tool and nothing else. In use, that
left the app unable to do anything with a shared link, such as a YouTube video: the lead
generator saw only the address. The owner decided to use OpenRouter's page-fetch tool and to
remove the search-only rule.

A live spike (`spikes/fetch_spike.py`) showed that `openrouter:web_fetch` with the Exa engine
returns a page's extracted text on an output item (`url`, `title`, `content`), and for a
YouTube link returns the video's title and transcript, for about a tenth of a cent. The
`openrouter` engine returned raw page markup, which is far less useful. A page that cannot be
opened comes back as an item with `status: incomplete` and an `error`.

## Decision

- **Research agents** get `openrouter:web_search` and `openrouter:web_fetch` (up to six pages).
  A page an agent opened counts as a source the same way a search result does, and its text is
  what quotes are checked against.
- **Links in pasted text** are opened before leads are written: one call with the fetch tool
  only (up to three pages), then the usual no-tools call that writes the leads, given what the
  pages said. Text with no link is still a single call.
- For that first call the fetch tool is **held to the sites the pasted text itself links to**.
- The fetch engine is always `exa`.
- Calls that produce structured output (leads, reports) still get no tools.

## Consequences

- Pages are requested by OpenRouter and Exa, not from the user's computer, so the user's
  address is not revealed to the sites. The links are sent to those services.
- **A new risk.** An agent that can open any address can be steered by text on a page into
  opening an address that carries part of the pasted text or the lead with it. Limiting the
  lead-generation call to the linked sites closes this for that call. It stays open for
  research agents, which have to be able to open pages they find. The README says so.
- Unchanged defences: retrieved text is framed as data, output is validated against a fixed
  schema, model text is shown as plain text, and nothing a model writes starts work.
- Not yet covered: transcripts are not available for every video, and pages behind a login or
  a paywall cannot be read.
