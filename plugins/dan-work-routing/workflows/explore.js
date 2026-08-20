export const meta = {
  name: 'explore',
  description: 'Answer one bounded question by fanning readers over disjoint slices of a codebase',
  whenToUse: 'When answering means opening more files than the answer is worth, and the reading partitions cleanly by directory or subsystem. Pass {question, slices: [{name, instructions}]}.',
  phases: [
    { title: 'Read', detail: 'one reader per slice, cheapest capable tier' },
    { title: 'Synthesize', detail: 'one writer over the readers\' conclusions' },
  ],
}

// The primer's spawn test, encoded: each reader loads only its own slice, so
// this session never sees the files — it pays for conclusions, not contents.
// Slices must be disjoint; overlapping slices re-read the same files N times,
// which is the case the primer routes to serial instead.
const { question, slices } = args

const FINDINGS = {
  type: 'object',
  properties: {
    conclusion: { type: 'string', description: 'What this slice says about the question — the answer, not a file tour' },
    evidence: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          location: { type: 'string', description: 'file path, with line numbers when they matter' },
          fact: { type: 'string' },
        },
        required: ['location', 'fact'],
      },
    },
    deadEnd: { type: 'boolean', description: 'true when this slice holds nothing relevant' },
  },
  required: ['conclusion', 'evidence', 'deadEnd'],
}

phase('Read')
const findings = await parallel(slices.map(slice => () =>
  agent(
    `Question: ${question}\n\nRead only this slice: ${slice.instructions}\n\n` +
    'Return what the slice contributes to the question. Cite the locations your ' +
    'conclusion rests on. If the slice is irrelevant, say so briefly rather than stretching.',
    { label: `read:${slice.name}`, phase: 'Read', model: 'haiku', effort: 'low', schema: FINDINGS },
  )))

const relevant = findings.filter(Boolean).filter(finding => !finding.deadEnd)
log(`${relevant.length}/${slices.length} slices relevant`)

// The barrier is genuine: synthesis needs every slice's conclusion at once.
phase('Synthesize')
const answer = await agent(
  `Question: ${question}\n\nPer-slice findings:\n${JSON.stringify(relevant, null, 2)}\n\n` +
  'Synthesize one direct answer. Keep the citations that carry it; drop the rest. ' +
  'Where slices disagree, say which evidence wins and why.',
  { label: 'synthesize', phase: 'Synthesize' },
)

return { answer, slicesRead: slices.length, slicesRelevant: relevant.length }
