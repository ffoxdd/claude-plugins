# Why the sweep costs more than the writing

The expensive part of a sync is not distilling. It is the raw list-API responses
landing in the main session.

A wiki search endpoint asked "what changed since Tuesday?" will happily return
every matching page's full property schema — every empty property, every
database's entire select-option list — in order to tell you a dozen page
identifiers. That is tens of thousands of tokens to answer a question whose
useful answer is a dozen lines, and none of it survives into a note.

## First: make the response small, rather than hiding a big one

Where a source allows it, a **server-side watermark filter plus a compact
projection** turns "what changed?" into a few lines. Then there is nothing to
delegate, no subagent overhead to pay, and no manifest to distrust — the main
session just asks and gets a short answer.

Prefer that shape whenever a source offers it, and check whether it does before
reaching for the fan-out below. It is strictly better: delegation is a way to
contain a large response, not a way to make one small.

The cost of the compact projection is usually that it **omits timestamps**,
which is precisely why the watermark is taken from your own clock before the
query rather than from the newest returned item.

### A source spread across several containers still qualifies

Repositories, workspaces, mailboxes, project boards — a source is often not one
query but one query per container. That does not make it a big response; it
makes it several small ones, and issuing them directly is still the cheap shape.

It also buys something delegation cannot give back. **Which container an item
came from is carried by the call, not by the answer.** A main session that asked
about one repository knows every result belongs to it, so nothing can file that
repository's item under another. Hand the same queries to a subagent and the
container stops being structural and becomes a *field* — one the model has to
carry correctly while merging several result sets, which is exactly where it
fails, and fails plausibly enough to be recorded as fact.

So prefer **N cheap calls whose containers are structural** over one delegated
merge whose containers are asserted. The threshold is not the number of calls
but whether each response is small.

## Otherwise: run the "what changed?" phase in a subagent

For sources with no server-side filter, or no way to trim the response:

Give a subagent **the watermarks and nothing else**, have it query the live
sources, and have it return a compact manifest — for each changed item, an
identifier, a timestamp, a title, and one line on whether it looks substantive.
The main session then decides what to fetch in full.

This is one of the cases where fan-out actually pays, and the reason is worth
being explicit about: **the sweep needs no context the main session already
holds.** Not the notes, not the code, not the conversation — just the
watermarks. Re-transmitting context is the usual reason delegation backfires,
and here there is none to re-transmit.

Delegate it to the least capable model that can do the job. Judging
"substantive or not" from a title and a timestamp is not work that needs the
expensive one.

**Don't delegate a sweep whose answer has to name a container.** A sweep
covering several repositories or several workspaces will file items under the
wrong one — not rarely, and not visibly: a manifest is read as fact by whatever
writes the notes, and a wrong repository name looks exactly like a right one.
"Verify it before recording" is the obvious response and a poor one, because
verifying costs about what fetching directly would have cost, so the delegation
bought nothing.

The real fix is upstream, in the section above: make the container the axis of
the call instead of a field in the answer. Delegate a sweep when its answer is a
*list of items*; keep it when the answer is a *list of items each labelled with
where it came from*, unless that label is one you can reconstruct without
trusting the manifest.

If a sweep has already run and its attribution matters, confirm it against the
source — but treat that as a signal to stop delegating this source next time
rather than as a step to repeat every sync.

## A deterministic script beats a model for the mechanical half

Where the fetch involves fixed, specifiable work — pagination, deduplication,
stripping boilerplate, grouping by thread — a script is better than a model
call, and not only for cost. Truncation and dedup happen **before anything
reaches a model**, so redundant copies cost network time instead of context.

That inverts an intuition worth naming: the script can afford to fetch *more*
than a model-driven sweep would, because it discards the excess for free. A
source whose every notification body contains its payload twice, or that
delivers one event as five near-identical copies, is cheap to handle exhaustively
and expensive to handle selectively.

Two properties to hold a script like this to:

- **Its stdout is the interface, and it stays small and clean** — a path, some
  counts, the new watermark, and anything it couldn't fetch. Raw content goes to
  files. That is what makes it safe for the main session to run directly.
- **A gap it reports is a note, not a hunt.** One conversation or container
  failing to fetch gets passed through to the sync notes: no retries, no
  diagnosis. A source can stay stuck behind the others indefinitely, and chasing
  it costs more than the content is worth. Say it was missed and move on.

If such a script needs authentication that a tool you already run holds, it can
often borrow that tool's existing credential store rather than minting a second
credential — no new app registration, no second consent, nothing extra to
rotate. If it does, treat that store as **strictly read-only**: it is a guest in
another tool's credentials, and a partial write breaks the owner's sign-in. Also
expect the location to move under you when that tool updates, so check the
plausible locations in order rather than pinning one.

## The same discipline applies to reading notes/

One case-insensitive multi-pattern grep rather than a call per term. The sweep
is not the only place where a dozen small round-trips cost more than one
deliberate call.
