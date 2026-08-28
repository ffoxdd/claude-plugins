# Code conventions

Design defaults for the code Claude writes, held loosely: any of them yields
when the problem at hand genuinely disagrees. One principle generates them —
**the structure of the code coincides with the best explanation of the system,
and nothing varies that the explanation doesn't account for.** Reify what the
explanation mentions (a name and a syntactic home); forbid what it doesn't (no
degree of freedom without a name). Decide uncovered cases from that.

## Standard form

- Build things the most normal way, in the field's own terms of art. Ask what
  this problem is called and how its canonical treatment is shaped, then use
  that shape and vocabulary unless a real constraint forbids it.
- No jank. A workaround that routes around the design instead of modeling the
  problem is a signal to re-derive the principled form, not to ship the
  workaround with a comment. When the principled form appears mid-build,
  refactor toward it.
- Name the deviation where it lives: what the standard way is and which
  constraint rules it out.

## Naming

- A name is mechanically derivable from its concept: a reader who knows the
  concept arrives at the same name without a translation table.
- Spell words out, in every identifier — public or private, type or local:
  `index` not `idx`, `configuration` not `config`, `SuitDecomposition` not
  `SuitDecomp`. Exceptions: canonical ecosystem names (`config/`, the `config`
  field of `package.json`), shared vocabulary (`id`, `url`, `api`, `json`,
  `http`), and a single-letter counter in a tight loop.
- One name per concept, everywhere: type `GameSessionStore`, then
  `gameSessionStore` as attribute, parameter, and variable. Strict about
  singular versus plural — the form matches one-or-many and never varies.
- Don't stutter against the namespace: `io::Error` not `io::IoError`,
  `strategic::SCORE_VERSION` not `strategic::STRATEGIC_SCORE_VERSION`,
  `tile/category.ts` exporting `TileCategory`.
- The filename is the primary identifier in the language's file-case:
  `PresidioAnalyzer` lives in `presidio_analyzer.py`, its tests in
  `presidio_analyzer_test.py`. A file of peer units is named for their shared
  theme. Never `base.py`, `types.py`, `utils.py`, `helpers.py`.
- Interfaces get the plain domain name and implementations the qualified one:
  `PaymentGateway`, `StripePaymentGateway`. Methods are named for the domain
  operation (`charge`), not the mechanics (`post_card_request`); shape-names
  belong only to genuine I/O adapters.

## Structure

- Newspaper order in every file, function, module, and directory: the highest
  abstraction first, details below. Public functions, then the tier-1 private
  functions they call, then tier-2, and so on down.
- Each unit operates at one level of abstraction. Extract intention-revealing
  sub-functions even when called once; structure documents, comments don't.
- Split by comprehension load, not line count: a unit is too big when the
  reader must hold too many things at once. Long conditional chains are that
  load in branching form, and each extraction mints a name one tier down.
- Nesting: zero levels is the ideal, two the tolerance. Flatten with guard
  clauses and higher-order collection operations (map, filter, group-and-apply)
  before wrapper functions; ease off where reaching zero would force a function
  that names nothing or fights the framework's idiom.
- Confident code: preconditions, defaults, edge cases, and errors are handled at
  the top and exit in place; past the guards, the body assumes the happy path.
  Early returns over nested if/else. (Avdi Grimm, *Confident Ruby*.)
- A pattern living as a scatter of calls across sites is invisible and
  untestable. Extract it into a named interface.
- Composition over inheritance: shared behaviour is a module of free functions
  the types import, not a base class they extend.
- The smallest public surface that still expresses the domain without hacks —
  a call-site workaround means the surface is too small, not that the caller
  should route around it. One canonical way per concept: no `choose` beside
  `choose_with_metadata` — the richest signature is the API, callers who need
  less use a subset, and optimizations (skipping expensive fields, logging,
  caching) never fork it.
- No re-exports from `__init__.py`, a barrel `index.ts`, or `mod.rs`; import
  from the defining module. The exception is a published library's stable API.
- One implementation per piece of knowledge. Before writing a non-trivial
  operation, ask whether the codebase already does it — from what you have
  seen first, a targeted search only if it plausibly exists. Two named
  exceptions: short-lived code where a shared abstraction would cost more than
  it is worth (flag the local duplication), and incidental duplication of code
  that encodes different concepts. DRY is one source of truth for one piece of
  knowledge, not deduplication of similar text.
- No shotgun surgery. When one conceptual change ripples across many files —
  parallel lists, duplicated constants, dense cross-references — restructure so
  it lives in one place.

## Dependencies and testing

- Inject dependencies through interfaces. Instance variables are the injected
  collaborators, wired in the constructor, and the main method is pure work
  over them; any other state earns its place with a named reason.
- Dependency parameters are required, never defaulted, so the wiring is visible
  at the call site. A default is fine only when intrinsic to the object (`id`
  defaulting to a generated UUID), never to hide a knob or spare call sites.
- Production and end-to-end tests build the system through one shared factory
  whose arguments are only the dependencies a test environment must swap;
  everything else is constructed inside, identically. The signature is the
  documentation of where test and production may differ.
- Encapsulation and testing ratchet together: a small surface is a small
  contract, and tests against it pin the contract so everything behind it can
  change. Test-setup pain means a missing boundary, not more mocks.
- The testing pyramid is a default; deviate where the problem demands, and
  shape end-to-end suites along the app's real user journeys.
- Verify behaviour in an isolated test scenario whose fixtures build exactly
  the situation — repeatable, and it joins the suite. A check against shared
  dev proves nothing after it runs; dev keeps only the final integration smoke
  against real external systems.

## Formatting

- Spaced out: blank lines between logical steps, and a multi-line block has a
  blank line on both sides. Only consecutive single-line entries pack. The
  first child hugs its container's opening token, nothing precedes the closing
  token, and a comment introducing a block belongs to it — blank line above the
  comment, none between.
- Never align: no continuation lines under an opening paren, no vertical
  columns across neighbouring lines (padded DDL, aligned trailing comments). A
  continuation line is indented one step past its parent. A comment that would
  trail in a column goes on its own line above. Only a code block in a rendered
  design document may align.
- YAML: block style by default; flow style only for an entry that fits within
  the line width (~100 unless the project is tighter), never wrapped inside a
  flow construct. Comments on their own line above the entry they describe.

## Comments and documentation

- A comment explains why or how, never what. Test: does it say something the
  name and signature cannot? If not, delete it.
- Describe current state, never history: no "we used to", "previously",
  "renamed from", "Sprint B will fill this", and no defending the design
  against rejected alternatives. The subtler form is contrastive reassurance —
  "you won't hit X", "no waiting period", "this reads as informative rather
  than redundant" — which only lands for a reader who saw the old state. If a
  claim's only content is the absence of something the reader never expected,
  cut it. Rationale that matters goes in a decisions doc, framed forward
  (principles → consequences).
- Never cite a design-doc path, directory, or dev history from code
  (`see foo.md § X`). State the why in place; docs are discovered, not
  hardcoded.
- Don't write content that mirrors live state — folder listings, file
  inventories, "current" enumerations of things that grow. Describe the pattern
  or the access method; a directory tree is its own index.
- Code blocks inside markdown documents wrap at 64 columns, hard: narrow
  viewers soft-wrap longer lines mid-word. Move a trailing comment to its own
  line above, split wide statements, and verify after editing.
- A PR description describes the branch's shape and what gates the merge. No
  commit lists (the Commits tab is live) and no counts CI reports live; a
  number appears only as a dated, won't-be-re-measured measurement.
- A doc marked self-contained carries no cross-references; inline what it
  needs.

## Published artifacts

- The source file is the deliverable; the published page is a rendering of it.
  Source lives where its subject lives (the repo's `docs/`, the notes tree),
  never in a session scratchpad.
- Publish when the deliverable has an audience. Analysis that answers a
  question in the conversation stays in the conversation.
- One artifact, one source path: republishing the path updates in place, a new
  path mints a duplicate. Record the URL beside the source.

