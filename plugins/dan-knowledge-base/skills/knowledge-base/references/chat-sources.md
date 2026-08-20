# Chat as a source

Chat is the highest-value live source and the most dangerous one. It carries
decisions that were never written down anywhere else, and it carries them
interleaved with whatever people happened to paste into a thread.

It also cannot be handled the way the other sources are. A wiki page or a task
board has a shape you can filter; a conversation's usefulness and its
sensitivity are the same sentences. So the design below is not "a sweep with
extra care" — it is a different division of labour, and every part of it exists
because a simpler arrangement failed.

Written against Slack's API shape, since that is where it was worked out. The
structure transfers to any platform with conversations, membership, and a
privacy flag.

## Scope is membership, read live

Enumerate the conversations the authenticated user is **a member of** — not every
conversation that exists. On Slack that is `users.conversations`, which is
membership-scoped, rather than `conversations.list`, which returns all public
channels regardless of membership.

The payoff is that there is nothing to maintain. Joining a conversation, or
being added to one, includes it in the next sync automatically: no starring, no
hand-kept list, and no channel silently missing because nobody updated a config.

## Let the platform's privacy metadata drive the handling tier

Most workspaces have a convention about where personal data is allowed —
commonly, private channels only. Where one exists, **the platform already stores
the fact you would otherwise hardcode**: every channel carries a private flag,
readable live. So the tiering needs no per-channel configuration, and a newly
created private channel is handled safely with zero config.

Three tiers, in decreasing order of restriction:

1. **Designated dense channels** — the handful whose ordinary traffic is
   per-person records (billing operations, eligibility, support triage). These
   get a **structural-facts-only summary**, never a scrubbed verbatim pull:
   policy decisions, mechanics, defect patterns with counts, named business
   entities. Scrubbing a message that is nine-tenths personal detail redacts it
   to nothing, so a summary loses no durable content. This is the one tier that
   needs naming by hand, and the names belong in the repo's register, not in the
   script.
2. **Every other private channel** — where personal data is *permitted* but
   rare. Pulled verbatim, marked **scrub-mandatory**: the isolated agent must
   actively scrub the section, and falls back to a structural summary if
   personal detail turns out to dominate.
3. **Public channels and direct messages** — where the convention says there
   should be nothing to find. The gate here is a **backstop**, and it stays
   precisely because it has caught real personal data in a group DM. A
   convention describes what people intend, not what they did.

## Boundaries and truncation

- **The history boundary is usually inclusive.** Slack's `oldest` includes the
  message at that timestamp, so a watermark taken from the newest message
  reprocesses it on every single sync. Filter with a strict `>`.
- **A history call with no pagination cursor truncates silently.** Detect the
  at-limit condition — a returned count equal to the limit — and report it,
  rather than losing the remainder unremarked.
- **Thread replies are a separate fetch.** A channel's history returns parent
  messages, and on a busy channel the substance is almost entirely in the
  replies. Fetching parents only produces an export that looks complete and
  contains none of the discussion.

## The script does the mechanical half, and it runs in the main session

Membership lookup, per-conversation incremental fetch, thread replies, noise
filtering, collapsing link unfurls that merely restate the linked page, grouping,
and computing the new watermark are all deterministic. None of it is a judgment
call worth re-deriving each sync, and a script doing it means redundant content
costs network time instead of context.

**Run that script from the main session, not from inside the isolated agent.**
This is the counterintuitive part, and it was arrived at by the other
arrangement failing repeatedly:

> An isolated sub-agent spawned to handle sensitive content will have its own
> permission classifier deny the very script call it was spawned to make —
> reasoning that this work belongs in an isolated agent, with no way to see that
> it *is* one. The wrapper's appended system prompt does not reach the
> classifier, and allowlist entries do not help, because that evaluation runs
> independently of the allowlist.

The durable fix is not to argue with the classifier but to remove the
sub-agent's need to shell out at all. Give it file reading and editing and
nothing else, and there is nothing left to deny.

That is only safe because **the script's stdout is clean by construction** — the
output path, the new watermark, and any gaps, and nothing else. Raw content goes
straight to the gitignored export file. Nothing sensitive reaches the main
session merely because the main session ran the fetch.

## The isolated agent does the judgment half

It reads and edits files, runs no commands, and returns only a confirmation —
never raw content echoed back through its output.

Its job is a **faithful gate, not a summary**, with the designated-channel
summaries as the deliberate exception. Concretely:

- Replace each designated channel's placeholder with a structural-facts-only
  summary, read from the raw side file that placeholder names.
- Scan everything else for stray personal data, omit what it finds, and note the
  omission at the top of the file so the omission is visible rather than
  invisible.

**Raw text for the designated channels goes to side files outside the repo**,
which the isolated agent reads and the main session deletes once the summaries
are written. That is sensitive data at rest, briefly, on local disk — a real
trade-off, worth making as a recorded decision rather than a side effect. Write
the decision and its date into the register.

Then the export is normal intake: distil it into notes, move it to
`inbox/processed/`, advance the watermark.

## A gap is a note, not a hunt

One conversation failing to fetch gets passed through to the sync notes. No
retries, no diagnosis. A conversation can sit stuck behind the others
indefinitely, and chasing it costs far more than the content is worth.

## What authentication costs, and who decides

Reading conversation history as a person, rather than as an installed app,
generally means a **user token** — and a user token carries that person's entire
read access to the workspace. Nothing about the export narrows it; the narrowing
comes from the tool's own read-only mode and from the filtering above.

Two consequences worth stating plainly in the register:

- **Read-only enforced by the tool is worth more than read-only intended by the
  operator.** A mode that rejects write calls outright makes "never write back"
  a mechanical fact rather than good behaviour, and it survives someone
  rewriting the config later.
- **Distributing such a tool to colleagues is a different decision from one
  person using it.** Each additional user authenticates with their own full read
  scope, and an installed app would have been visible to workspace
  administrators in a way a personal token is not. Whether the pipeline's
  handling of personal data is sound is an engineering question you can answer;
  whether the organization accepts that token model is not, and it wants an
  explicit sign-off rather than an inference from the first question's answer.
