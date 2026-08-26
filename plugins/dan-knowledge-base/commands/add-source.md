---
description: Declare a new live source — run the trap list against it, then write both halves of the register
---

Add one source to this knowledge base's register. Doing this as a command
rather than by hand means the trap list gets **run** rather than read, and the
register section gets written while the answers are in front of you.

Read `${CLAUDE_PLUGIN_ROOT}/skills/knowledge-base/references/adding-a-source.md`
before starting — it is the list this command executes — and
`references/configuring-sources.md` for the two-file contract.

If the user named a source in the arguments, start with that one. Otherwise ask
what it is.

1. **Establish the reach.** Is it an MCP server, a CLI, or a shipped adapter
   (`email`, `chat`)? Confirm it responds before designing a query against it.
   If it is a shipped adapter, run `/dan-knowledge-base:setup` first.

2. **Find the cheapest "what changed?" call.** Does it support a server-side
   filter on a modification time, and can the response be projected down to a
   few fields? A source answering yes to both needs no adapter and no subagent
   — record it with `"adapter": null`. Otherwise `references/sweep-economics.md`
   covers which shape you are in.

3. **Run the trap list.** Answer every trap in `adding-a-source.md` against the
   live source, recording each answer — a question to answer, not a box to
   tick. If a control container cannot be found, say so: an unprovable filter
   is worth recording as unproven.

4. **Pick a starting watermark deliberately.** Default to a day or two back,
   not the epoch. The first sync's job is to prove the wiring, and a backfill of
   all history is both expensive and the worst possible thing to review.

5. **Write the machine half.** Add the entry to `.knowledge-base.json`:
   `adapter`, `feeds`, `watermark` (`format` and `boundary`), `scope_control`,
   plus whatever vocabulary the adapter needs. Copy the shape from
   `${CLAUDE_PLUGIN_ROOT}/config/example.json`. For a source that cannot be
   listed by recency, set `"reactive": true` and no watermark.

6. **Write the prose half.** Add a subsection to `## Sources` in the repo's
   `CLAUDE.md`, covering what `adding-a-source.md` says to record, every trap
   **with today's date**. Restate no value that lives in the JSON — point at it.

7. **Seed the watermark** in `notes/.sync-state`, with a note saying this is a
   first run and what window it covers.

8. **Offer one scoped sync** against that source alone, so the wiring is proven
   on a small window before it runs beside everything else. Do not run it
   unbidden.

If the source can carry per-person records, say so before writing anything, and
read `references/chat-sources.md` for the split that handles it. Record which
conversations or containers are dense in the config, and the decision and its
date in the prose.
