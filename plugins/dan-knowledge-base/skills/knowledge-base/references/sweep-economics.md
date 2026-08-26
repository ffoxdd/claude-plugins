# Why the sweep costs more than the writing

The expensive part of a sync is not distilling. It is the raw list-API
responses landing in the main session. A wiki search endpoint asked "what
changed since Tuesday?" will return every matching page's full property schema
— every empty property, every select-option list — to tell you a dozen page
identifiers: tens of thousands of tokens for a dozen useful lines, none of
which survive into a note.

## First: make the response small, rather than hiding a big one

Where a source allows it, a **server-side watermark filter plus a compact
projection** turns "what changed?" into a few lines. Then there is nothing to
delegate and no manifest to distrust. Check for that shape before reaching for
the fan-out below: delegation is a way to contain a large response, not a way
to make one small.

The usual cost of the compact projection is that it **omits timestamps**, which
is why the watermark comes from your own clock before the query.

### A source spread across several containers still qualifies

Repositories, workspaces, mailboxes, project boards — a source is often one
query per container. That is several small responses, and issuing them directly
is still the cheap shape.

It also buys something delegation cannot give back. **Which container an item
came from is carried by the call, not by the answer.** A main session that
asked about one repository knows every result belongs to it. Hand the same
queries to a subagent and the container becomes a *field* the model has to
carry correctly while merging result sets — exactly where it fails, plausibly
enough to be recorded as fact.

So prefer **N cheap calls whose containers are structural** over one delegated
merge whose containers are asserted. The threshold is not the number of calls
but whether each response is small.

## Otherwise: run the "what changed?" phase in a subagent

For sources with no server-side filter or no way to trim the response: give a
subagent **the watermarks and nothing else**, have it query the live sources,
and have it return a compact manifest — per changed item, an identifier, a
timestamp, a title, and one line on whether it looks substantive. The main
session decides what to fetch in full.

This is a case where fan-out pays, because **the sweep needs no context the
main session already holds** — not the notes, not the code, not the
conversation. Delegate it to the least capable model that can judge
"substantive or not" from a title and a timestamp.

**Don't delegate a sweep whose answer has to name a container.** It will file
items under the wrong one — not rarely, and not visibly. "Verify before
recording" costs about what fetching directly would have, so the delegation
bought nothing. Delegate a sweep when its answer is a *list of items*; keep it
when the answer is *items each labelled with where they came from*, unless the
label is one you can reconstruct without trusting the manifest. If such a sweep
has already run, confirm attribution against the source once, and stop
delegating that source next time.

## A deterministic script beats a model for the mechanical half

Where the fetch is fixed, specifiable work — pagination, deduplication,
stripping boilerplate, grouping by thread — a script is better than a model
call, and not only for cost. Truncation and dedup happen **before anything
reaches a model**, so redundant copies cost network time instead of context.
That inverts an intuition: the script can afford to fetch *more* than a
model-driven sweep would, because it discards the excess for free. A source
delivering one event as five near-identical copies is cheap to handle
exhaustively and expensive to handle selectively.

Two properties to hold such a script to:

- **Its stdout is the interface, and it stays small and clean** — a path, some
  counts, the new watermark, and anything it couldn't fetch. Raw content goes
  to files. That is what makes it safe for the main session to run directly:
  nothing sensitive reaches the session merely because the session ran the
  fetch.
- **A gap it reports is a note, not a hunt.** One conversation or container
  failing to fetch is passed through to the sync notes: no retries, no
  diagnosis. A source can stay stuck behind the others indefinitely, and
  chasing it costs more than the content is worth.

If such a script needs authentication that a tool you already run holds, it can
borrow that tool's credential store rather than minting a second credential.
Treat that store as **strictly read-only** — a partial write breaks the owner's
sign-in — and expect its location to move when the tool updates, so check the
plausible locations in order rather than pinning one.

## The same discipline applies to reading notes/

One case-insensitive multi-pattern grep rather than a call per term. The sweep
is not the only place where a dozen small round-trips cost more than one
deliberate call.
