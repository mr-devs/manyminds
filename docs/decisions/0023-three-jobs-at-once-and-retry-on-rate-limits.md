# 23. Three research jobs at once, and a wait and retry when rate limited

- Status: Accepted
- Date: 2026-11-16
- Changes: the limit of six jobs at once from the original plan

## Context

Since decision 22 a research job is one call in which the model searches and opens pages over
many rounds, and each round is a request to the model. OpenRouter limits how many requests an
account may make to one model in a minute; for a new account using GPT-6 Luna the limit was
20. Six jobs started together passed it within 15 seconds and every one was stopped part-way
through. The message shown was only "OpenRouter is limiting requests right now", which gave
the owner nothing to act on.

Measured on 2026-11-16 with the same leads: six at once, three of six stopped; three at once,
all finished with no limit reached.

## Decision

- At most three research jobs run at once (`MAX_CONCURRENT` in `core/jobs.py`). The rest wait
  their turn, as before.
- A job stopped by a rate limit waits 60 seconds, or longer if OpenRouter asks for longer, and
  starts again, up to twice. It keeps its place while it waits, so fewer jobs run in the
  meantime. The wait and its reason are recorded in the thread's transcript. Other failures
  are not retried.
- A rate-limit message carries OpenRouter's own reason, with the API key removed as for every
  upstream message.

## Consequences

- Six leads take about twice as long as before.
- A retried job starts from the beginning, and the rounds of the stopped attempt have already
  been billed. Their cost is not recorded, because a stopped call reports no usage.
- Lead generation, chat replies and the report are not retried; they fail with the reason.
- Accounts with higher limits could run more at once. The number is a constant, not a setting.
