# Adding a live source

A source is not trustworthy because its first query returned a plausible
result. Every trap below has cost somebody real time, and each one fails
*quietly* — a wrong answer that looks like a right one. Interrogate a new source
against this list before it feeds anything committed, and record what you find
in the register.

## The trap classes

**An unrecognized argument may be silently ignored.** Pass a scope filter under
the wrong parameter name and some APIs neither error nor warn — they return the
unscoped result, which reads exactly like a scoped one, just larger. A count
that surprises you is the only symptom, and it is easy to rationalize.

> **Assert scope with a control.** Point the same query at a container you know
> holds nothing and require an empty result. A filter you cannot prove is
> applied is a filter you should assume isn't. Record the control's identifier
> in the register so the assertion can be re-run when the query changes.

**The compact projection may omit the timestamps you want to sort or watermark
by.** Sorting knobs can exist and still be useless, because the values they sort
on aren't in the response. Hence taking the watermark from your own clock,
before the query.

**Defaults commonly exclude rows.** Completed items, sub-items, archived
containers, and deleted-but-recoverable records are all frequently excluded
unless asked for — and "what got finished" is usually the single most
interesting thing a sync can report. Enumerate a query's defaults explicitly
before trusting any count it returns.

**The same event delivered twice is not the same content.** Two people's
independently generated summaries of one meeting emphasize different things, so a
copy arriving after an earlier one was already distilled is worth reading rather
than skipping — expect to add, not to find a duplicate. Three consequences:

- **Dedupe on the event's own date, read from its content** — never on delivery
  time. A source can deliver an old event's record long after the fact, and
  keying on arrival files it under the wrong day. Prefer a date in the record's
  own footer or metadata over one mentioned in its prose, since a summary saying
  "ships on the 10th" would otherwise date the event to the 10th.
- **Deduplication only reaches copies inside one window.** Copies landing on
  either side of a watermark can't be collapsed, which is exactly the case where
  each covers a different part of the event.
- **Keep a small committed ledger of what has been delivered**, keyed the same
  way the dedup is, so a recurrence is flagged mechanically at the point of
  reading instead of depending on whoever runs the sync remembering this. Keep
  the first copy's details, prune old entries, and commit it beside the
  watermarks.
- **Don't ask for a diff between two such copies.** Independently generated
  prose differs nearly everywhere it agrees in substance, so a line diff reports
  almost everything as changed. Compare the new copy against `notes/` instead —
  which is also the only place the earlier one still exists, since intake is
  never committed.

**A whitelist cannot notice its source moving.** If a source is swept by
matching a sender, a domain, or a label, that filter goes *silent* rather than
loud the day the source changes it — you get zero results and no error. So:

> Scan the whole window for the **shape** of the content — its recognizable
> recurring phrases — and flag matches from unrecognized senders rather than
> dropping them. Record the currently observed sender as a baseline and report
> when the observed one differs from it.

**Match a source's identity as loosely as correctness allows.** A pinned exact
address breaks the moment a local-part changes (`no-reply@` becoming
`notifications@`); a domain match survives it and is no less correct.

**A single call with no pagination cursor truncates silently.** Detect the
at-limit condition — a returned count equal to the limit — and report it, rather
than losing the remainder without noticing.

**Some sources cannot be listed by recency at all**, so they cannot be
watermarked. Those are followed **by reference**: when another source links one,
pull it then. Record the stable identifiers of the ones that recur, and mark the
source as reactive in the register rather than leaving an empty watermark that
looks stale forever.

**A filter's scope may resolve separately from where you set it.** A workspace or
account identifier passed as a server flag may not reach the individual
operations, which then fail claiming no workspace is configured. Where a source
has more than one place to say the same thing, find out which one the operations
actually read.

## What to record in the register

For each source, in the repo's `CLAUDE.md`:

- **What it feeds** — which notes, and what is explicitly out of scope
- **How it is reached** — CLI, MCP server, or script; and whether it is
  read-only, plus what makes it so. A read-only mode enforced by the tool turns
  "never write back" from a standing intention into a mechanical fact, which is
  worth having and worth noting so a later rewrite of the config keeps it
- **The watermark** — its format (ISO-8601, epoch milliseconds, an opaque
  cursor) and whether the boundary is inclusive
- **The exact query**, including every argument whose default would exclude rows
- **The control assertion** that proves scoping works, and its expected result
- **Traps found, dated.** A trap can be fixed upstream, and the date is what
  lets a later reader decide whether to re-test it
- **Whether it can carry personal records**, and the route if so

Two habits keep the register useful rather than decorative:

**Write a trap down the first time it costs you.** The register is not
documentation of the obvious — it is the accumulated record of every way a
source has already misled someone. The second occurrence is the one it saves,
and you cannot predict which trap that will be.

**Prefer configuration read live over configuration maintained by hand.** Where
a source exposes the property you would otherwise hardcode — which conversations
you belong to, which containers are private, which are archived — read it at
sweep time. Then a new container is handled correctly with no config change, and
there is no hand-maintained list to fall out of date. Hardcode only what the
source will not tell you.

## Credentials

A source's credential belongs in whatever store already owns it — the tool's own
config, a secret manager, the OS keychain — and **not** in the MCP server
definition or a committed file. An entry carrying no secret is one you can paste
into a chat, re-create from scratch, or commit as an example, which is most of
what makes a setup reproducible. Check the permissions of any config a tool
writes for you; some are created world-readable.
