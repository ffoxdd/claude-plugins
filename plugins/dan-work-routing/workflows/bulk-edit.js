export const meta = {
  name: 'bulk-edit',
  description: 'Apply one fully-specified mechanical edit across many files, fan-out width scaled by work per item',
  whenToUse: 'When the decision is already made and only the typing remains — a rename, a signature change, a lint fix — across more files than one agent should hold. Pass {edit, files, filesPerAgent?}. Not for edits that need judgment per site; those are not mechanical and do not belong at this tier.',
  phases: [
    { title: 'Edit', detail: 'bulk-editor agents over disjoint file batches', model: 'haiku' },
  ],
}

// The primer's fan-out scaling rule, encoded: width follows work per item, not
// item count. Batching many small edits under one agent keeps the fixed spawn
// overhead a fraction of the work instead of the whole bill; twelve agents over
// twelve one-line edits is overhead as the entire bill.
const { edit, files, filesPerAgent = 10 } = args

const batches = []
for (let start = 0; start < files.length; start += filesPerAgent) {
  batches.push(files.slice(start, start + filesPerAgent))
}
log(`${files.length} files in ${batches.length} batch(es)`)

const OUTCOME = {
  type: 'object',
  properties: {
    edited: { type: 'array', items: { type: 'string' }, description: 'path:line locations actually changed' },
    skipped: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          reason: { type: 'string', description: 'why this file was left alone — ambiguity, no match, would need a design decision' },
        },
        required: ['file', 'reason'],
      },
    },
  },
  required: ['edited', 'skipped'],
}

// pipeline, not parallel: batches are independent, so nothing needs a barrier.
// The bulk-editor agent definition pins the tier (haiku, low) and the boundary:
// apply exactly the specified change, and stop rather than guess on ambiguity.
phase('Edit')
const outcomes = await pipeline(
  batches,
  (batch, _, index) => agent(
    `Edit specification:\n${edit}\n\nApply it to exactly these files, and stay inside them:\n` +
    batch.map(file => `- ${file}`).join('\n'),
    { label: `edit:batch-${index + 1}`, phase: 'Edit', agentType: 'dan-work-routing:bulk-editor', schema: OUTCOME },
  ),
)

const landed = outcomes.filter(Boolean)
const skipped = landed.flatMap(outcome => outcome.skipped)
if (skipped.length) log(`${skipped.length} file(s) skipped — see result for reasons`)

// A batch that threw takes its files with it, so say so rather than returning a
// short list that reads as a complete one.
const lost = batches.filter((_, index) => !outcomes[index])
if (lost.length) {
  log(`${lost.length} batch(es) failed — ${lost.flat().length} file(s) NOT edited`)
}

return {
  edited: landed.flatMap(outcome => outcome.edited),
  skipped,
  batchesLost: lost.length,
  filesNotAttempted: lost.flat(),
}
