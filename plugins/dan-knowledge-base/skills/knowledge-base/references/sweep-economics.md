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

**And to an agent that holds the source's tools.** A source reached through an
MCP server can be queried only by an agent whose tool list names those MCP
tools. The routing plugin's cheap search agents hold file tools only, and one
handed an MCP sweep reports the server as *missing* rather than its own grant —
a plausible answer that is really a tooling fault. Define a repo-local agent
with exactly the source's read tools, its own cheap model, and nothing else.
The register records the same need from the other side: a source entry's
`requires.mcp` names the servers it depends on, which is what
`/dan-knowledge-base:setup` checks (see `configuring-sources.md`, *What a
source needs to be reachable at all*).

**Don't delegate a sweep whose answer has to name a container.** It will file
items under the wrong one — not rarely, and not visibly. "Verify before
recording" costs about what fetching directly would have, so the delegation
bought nothing. Delegate a sweep when its answer is a *list of items*; keep it
when the answer is *items each labelled with where they came from*, unless the
label is one you can reconstruct without trusting the manifest. If such a sweep
has already run, confirm attribution against the source once, and stop
delegating that source next time.

## An item too large to fetch is fetched in pieces, not skipped

A source that appends forever — a wiki page written into weekly for two years, a
long-running ticket thread — eventually produces a single item whose "give me
this whole thing" endpoint exceeds the tool-output limit. Every call fails, and
the same call fails next sync.

Treat that as the normal end state of a recurring item rather than an exception
to route around, and **descend the item's own structure instead**. Most such
APIs expose children separately from content: fetch the item's children with a
small page size, identify the one section you need from the titles and
timestamps that come back, then fetch that section's children, and so on.

Three calls of a few KB each, against one that cannot complete at any size. And
the descent gives back something the whole-item fetch cannot: **a modification
time per child**, so you can tell which sections actually changed since the
watermark rather than re-reading the entire item to find out. On a page where
one week of twenty changed, that is the difference between reading a section and
reading two years.

The cost is that the newest section's position is a property of the source —
appended at the end, or inserted at the top — and the descent has to know which.
That is a fact about one source, so it belongs in the register, not here.

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
