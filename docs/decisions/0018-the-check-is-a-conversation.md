# 18. A check is one running conversation

- Status: Accepted
- Date: 2026-11-12
- Replaces: the separate lead editor and Threads list of milestones 1a and 1c, and the
  planned design of milestones 8 and 9 (conversations as separate items under a check)

## Context

The owner asked for the page where claims are entered to become the main, central chat,
styled like an ordinary chatbot: one box for the text and any instructions, leads that can
each be started with their own **Go**, removed, or left alone, and the chat continuing
beneath them, for example to summarise what the research threads found.

## Decision

- **A check is a conversation.** It is a list of messages. The first is what the user
  pasted; the reply to it holds the generated leads. Every later message gets a reply from
  the chat model.
- **One box.** There is no separate instructions field. The lead generator and the chat
  model are told that the user's message holds the material to examine *and may hold the
  user's requests about the work*, which they should follow. Every other tagged block
  (linked pages, reports, earlier replies) stays data, never instructions.
- **Leads belong to the reply that put them forward** and are shown under it. Each has its
  own Go, which starts that lead only, with the model chosen beside the message box. A
  started lead stays where it is and becomes the way into its thread, with a live status.
  "Research all" under a list starts every lead in it that has text.
- **The chat model has no search.** It is given the conversation so far, every lead with how
  far its research has got, and the finished reports. It answers from the reports only, with
  no verdict. When an answer needs research that has not been done, it proposes leads, which
  appear as rows like any others. Nothing a model writes starts work.
- Links the user puts in a new message are opened first, held to the sites in that message,
  exactly as for the first message (decision 17).
- Replies are structured (`reply`, `leads`) and validated, with one repair attempt. The reply
  text is shown as plain text.
- A reply still awaited when the app closes is marked as stopped at the next start.

## Consequences

- **A weaker boundary, accepted.** Pasted text is often copied from the web, and it now sits
  in the same box as the user's own requests, so the lead generator and the chat model cannot
  tell a request the user typed from one hidden in what they pasted. The effect is bounded:
  those two calls have no tools beyond opening the links in the message itself, their output
  is a fixed format shown as plain text, and proposed leads start nothing. Research agents,
  which can search and open pages, still receive the pasted text as data only.
- The chat can only be as good as the reports. It cannot check anything itself; it has to
  propose a lead. This keeps the search-capable agents the only place where new evidence
  enters, with its sources checked against what the search returned.
- The reply's claims about the reports are not checked mechanically. The planned labelled
  sections ("from the reports", "from a new search") are dropped with the search.
- The cost of chat replies is not yet recorded or shown.
- Checks made before this change gain a conversation when the database is upgraded: the
  pasted text (with any instructions) as the first message and a reply holding their leads.
