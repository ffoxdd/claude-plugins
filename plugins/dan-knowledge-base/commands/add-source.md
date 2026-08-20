---
description: Declare a new live source — run the trap list against it, then write both halves of the register
---

Add one source to this knowledge base's register. The point of doing this as a
command rather than by hand is that the trap list gets **run** rather than read,
and the register section gets written while the answers are still in front of
you.

Read `${CLAUDE_PLUGIN_ROOT}/skills/knowledge-base/references/adding-a-source.md`
before starting — it is the list this command executes — and
`references/configuring-sources.md` for the two-file contract.

If the user named a source in the arguments, start with that one. Otherwise ask
what it is.

1. **Establish the reach.** Is it an MCP server, a CLI, or a shipped adapter
   (`email`, `chat`)? Confirm it actually responds before designing a query
   against it. If it is a shipped adapter, run `/dan-knowledge-base:setup` first —
   there is no point interrogating a source you cannot yet call.

2. **Find the cheapest "what changed?" call.** Ask, in this order: does it
   support a server-side filter on a modification time, and can the response be
   projected down to a few fields? A source that answers yes to both needs no
   adapter and no subagent — record it with `"adapter": null`. Only when the
   answer is no does the sweep need delegating; `references/sweep-economics.md`
   covers which shape you are in.

3. **Run the trap list.** Each of these is a question to answer against the live
   source, not a box to tick:

   - **Prove the scope filter applies.** Point the same query at a container you
     know is empty and require zero results. If you cannot find one, say so
     explicitly — an unprovable filter is worth recording as unproven.
   - **Ask what the defaults exclude.** Completed items, sub-items, archived
     containers. Name them, and set them explicitly in the query.
   - **Find whether the response carries timestamps at all.** If it does not,
     the watermark must come from your own clock before the query.
   - **Determine whether the boundary is inclusive.** Query with a watermark
     equal to a known item's timestamp and see whether that item comes back.
   - **Check for silent truncation.** Is there a cursor? If not, what is the
     limit, and how would you know you hit it?
   - **Ask how the same event could arrive twice**, and what its own date is
     called in the payload — as distinct from its delivery time.
   - **Ask what would happen if the source moved** — changed sender, renamed
     label. Would the sweep go loud, or silent? If silent, design the shape
     signature that catches it.

4. **Pick a starting watermark deliberately.** Default to something recent — a
   day or two back, not the epoch. The first sync's job is to prove the wiring,
   and a backfill of all history is both expensive and the worst possible thing
   to review.

5. **Write the machine half.** Add the entry to `.knowledge-base.json`:
   `adapter`, `feeds`, `watermark` (`format` and `boundary`), `scope_control`,
   plus whatever vocabulary the adapter needs. Copy the shape from
   `${CLAUDE_PLUGIN_ROOT}/config/example.json`. For a source that cannot be
   listed by recency, set `"reactive": true` and no watermark.

6. **Write the prose half.** Add a subsection to `## Sources` in the repo's
   `CLAUDE.md`: what it feeds and what is out of scope, how it is reached and
   whether it is read-only, every trap you found **with today's date**, and the
   control assertion's expected result. Restate no value that lives in the JSON —
   point at it.

7. **Seed the watermark** in `notes/.sync-state`, with a note saying this is a
   first run and what window it covers.

8. **Offer one scoped sync** against that source alone, so the wiring is proven
   on a small window before it runs beside everything else. Do not run it
   unbidden.

If the source can carry per-person records, say so before writing anything, and
read `references/chat-sources.md` for the split that handles it — a deterministic
fetch whose stdout stays clean, and an isolated reader that returns structural
facts only. Record which conversations or containers are dense in the config, and
record the decision and its date in the prose.
