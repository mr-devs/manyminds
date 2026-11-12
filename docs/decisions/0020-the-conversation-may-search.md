# 20. The conversation may search the web

- Status: Accepted
- Date: 2026-11-12
- Changes: "The chat model has no search" in decision 18

## Context

Decision 18 gave the main conversation no search, so that new evidence could only arrive
through research threads. The owner decided the conversation should be able to search when
it wants to.

## Decision

A reply is now worked out in up to three steps:

1. Links in the new message are opened, as before (decision 19).
2. **A look-up call** is given the conversation, the leads and the finished reports, with
   the search and page-opening tools. It decides whether a good answer needs facts these do
   not hold. If not, it says so and nothing is searched. If so, it searches and writes notes
   with sources. It uses the app's search-engine setting.
3. **The reply call**, with a fixed format and no tools, writes the answer from the reports
   and, when there are any, the search notes and the pages the search returned.

The reply is told to draw first on the reports, to mark anything taken from the new search
as such, and to give its URL. Searches and pages opened are saved as the reply's steps and
shown as they happen. If the look-up call fails, the reply is written from the reports and
the steps say the search failed.

## Consequences

- **A wider opening for misleading text.** The user's messages, which often contain pasted
  web text, are read as the user speaking. The look-up call reads them and can search and
  open any page, so text hidden in a paste could direct it, including to an address that
  carries part of the conversation with it. Before this decision only research agents, which
  treat pasted text as data, could do that. Nothing a model writes can start research or
  change anything saved, and replies are still shown as plain text.
- **What the conversation finds is not checked the way a report is.** A report's evidence is
  quoted and matched against what the search returned, and flagged when it does not match.
  A reply is prose. For anything that matters, start a lead.
- Every message now costs one extra call. In a live trial that was a fiftieth of a cent when
  nothing was searched and about 1.4 cents when it was.
