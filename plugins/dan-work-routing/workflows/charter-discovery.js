export const meta = {
  name: 'charter-discovery',
  description: 'Find the candidate charters in a programme by fanning probes over independent places work could be hiding',
  whenToUse: 'When an open-ended loop needs its next unit of work discovered rather than assigned, and the search partitions into independent probes. Pass {programme, probes: [{name, instructions}]}. Returns ranked avenues, or an empty list, which is the loop\'s termination signal.',
  phases: [
    { title: 'Probe', detail: 'one probe per place work could hide, cheapest capable tier' },
    { title: 'Judge', detail: 'drop topics, keep avenues, rank by what a negative would settle' },
  ],
}

// DISCOVERY is a workflow; the charter LOOP is not. Executing a charter can mean
// hours behind a job queue and a verdict that needs judging, and "until no avenue
// remains" is unbounded — a script would either block on the first long job or
// have to be re-entrant. So this returns the candidate list and stops. Picking,
// executing and recording stay where the judgment and the queue are.
//
// The primer's spawn test applies unchanged: each probe reads its own place and
// returns candidates, so the session pays for a list rather than for the search.
const { programme, probes } = args

// `falsifier` is required, and that is the whole filter. An avenue is a step whose
// outcome would change what happens next; if nothing can come back negative, it is
// a topic and it never finishes. Making the field mandatory forces each probe to
// decide which it found rather than leaving it for the judge to guess.
const CANDIDATES = {
  type: 'object',
  properties: {
    candidates: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          question: { type: 'string', description: 'Stated so a negative answer is possible' },
          avenue: { type: 'string', description: 'The specific work that would answer it' },
          falsifier: { type: 'string', description: 'What a negative result would look like, concretely' },
          evidence: { type: 'string', description: 'What was actually observed that suggests this, with locations' },
        },
        required: ['question', 'avenue', 'falsifier', 'evidence'],
      },
    },
    exhausted: { type: 'boolean', description: 'true when this probe found nothing — say so rather than padding' },
  },
  required: ['candidates', 'exhausted'],
}

const RANKED = {
  type: 'object',
  properties: {
    ranked: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          question: { type: 'string' },
          avenue: { type: 'string' },
          falsifier: { type: 'string' },
          why: { type: 'string', description: 'What settling this would unblock or remove' },
        },
        required: ['question', 'avenue', 'falsifier', 'why'],
      },
    },
    rejected: {
      type: 'array',
      description: 'Candidates dropped for being topics rather than avenues, with the reason — recorded so the next pass does not re-propose them',
      items: { type: 'string' },
    },
  },
  required: ['ranked', 'rejected'],
}

phase('Probe')
const found = await parallel(probes.map(probe => () =>
  agent(
    `Programme: ${programme}\n\n` +
    `Probe only this: ${probe.instructions}\n\n` +
    `Return candidate units of work. A candidate must be an AVENUE, not a topic: a ` +
    `specific step whose outcome would change what happens next. "Rank reflection may ` +
    `not hold here" is an avenue — it can be checked and either answer redirects the ` +
    `work. "Improve the scoring path" is a topic — nothing about it can come back ` +
    `negative, so nothing about it can finish.\n\n` +
    `Search the COMPLEMENT of what is already known where you can: the code that never ` +
    `mentions the concept rather than the code that does, the caveat whose stated ` +
    `expiry condition has since passed, the ledger row still marked open. Anything ` +
    `that already names the thing has been considered.\n\n` +
    `Report what you OBSERVED, not what would be nice to have. If this probe holds ` +
    `nothing, set exhausted and return no candidates — an empty probe is a real ` +
    `finding and padding it is how a loop invents work it does not have.`,
    { label: `probe:${probe.name}`, phase: 'Probe', schema: CANDIDATES },
  )
))

const candidates = found.filter(Boolean).flatMap(result => result.candidates)
const exhaustedProbes = found.filter(Boolean).filter(result => result.exhausted).length

log(`${candidates.length} candidate(s) from ${probes.length} probe(s); ${exhaustedProbes} exhausted`)

// No candidates is the answer, not a failure to find one. Returning it plainly is what
// lets a loop terminate honestly instead of manufacturing another round.
if (candidates.length === 0) {
  return { ranked: [], rejected: [], exhausted: true }
}

phase('Judge')
const judged = await agent(
  `Programme: ${programme}\n\n` +
  `These candidates came from independent probes, so they may overlap or restate each ` +
  `other:\n\n${JSON.stringify(candidates, null, 2)}\n\n` +
  `Merge duplicates. Drop any candidate whose falsifier does not describe a real ` +
  `negative outcome — that is the test for a topic wearing an avenue's clothes, and ` +
  `dropping it is the point rather than a loss. Record each drop and why, so the next ` +
  `pass does not re-propose it.\n\n` +
  `Rank what survives by what settling it would unblock or remove. An avenue that ` +
  `closes off a whole line when it comes back negative outranks one that only adds.`,
  { label: 'judge', phase: 'Judge', schema: RANKED },
)

return { ...judged, exhausted: false }
