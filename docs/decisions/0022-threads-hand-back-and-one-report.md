# 22. Threads hand back their findings; the conversation writes the one report

- Status: Accepted
- Date: 2026-11-13
- Replaces: the structured report of decision 8 and the second call of decision 15

## Context

Each research job made two calls: one that searched and wrote notes, and one that turned the
notes into a report in a fixed format. In use the report read as a shortened copy of the
notes. The owner asked for it to go: threads should work like sub-agents sent off on single
tasks that feed back into the main conversation, which writes one report once every lead has
finished, whether it succeeded or not. The owner accepted losing the per-quote check and
keeping a check on links only.

## Decision

- **Research is one call.** What the agent writes last is its findings, in markdown, and is
  what it hands back. Anything it wrote earlier is shown as progress.
- **A link check replaces the quote check.** Every web address in the findings is compared
  with the pages the search returned and the pages the agent opened. Those that match
  neither are listed under the findings as "Links the search did not return", and the
  conversation is told about them too.
- **Each job that ends puts a hand-back in the conversation**: the lead, whether it finished
  or failed, and, folded away, its findings or the reason it stopped.
- **When no started lead is still waiting or running, the conversation writes one report**
  from everything handed back. It has no tools, is told to give no verdict, and may propose
  further leads, which start nothing. If research ends while a reply is being written, the
  report waits for that reply. If every lead failed there is nothing to write from, and no
  report is written.
- Leads the user never started are ignored. Starting more leads later leads to a further
  report covering everything.
- Markdown is formatted by the app's own reader; nothing is handed to the browser as markup.
- Reports saved in the old form are read as notes, so earlier checks still open.

## Consequences

- **Quotes are no longer checked against their sources.** A quotation in the findings may be
  inexact and nothing will flag it. Only made-up or mistyped addresses are caught.
- **No verdict is now a matter of instruction, not of format.** The old report had no field
  for one. Findings and the report are free text; the prompts forbid a verdict, and the
  report's reply format still rejects extra fields, but prose can carry an opinion.
- Evidence is no longer grouped into what supports and what undermines by the app; the agent
  is asked to say which for each source.
- **The report is written without being asked for**, at the cost of one call each time the
  running leads run out. Starting leads one at a time, each after the last has finished,
  produces a report after each.
- A lead costs about a third less, having one call instead of two.
- While the report is being written the check is busy: a message cannot be sent and the
  check cannot be deleted.
