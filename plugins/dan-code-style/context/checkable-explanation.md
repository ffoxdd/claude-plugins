# The common thread: code as a checkable explanation

These conventions — long names, generous newlines, minimal
public surfaces over files organized top-down, collaborators-only
classes, dependency injection through interfaces, one factory
shared by production and the end-to-end tests, a testing pyramid
you deviate from when the problem insists — read, listed out, like
separate tastes. They aren't. Each is the same move made in a
different place, and the move is this:

**Make the structure of the code coincide with the best
explanation of the system — and let nothing vary that the
explanation doesn't account for.**

Everything else falls out of that principle and its two halves:
*reify what the explanation mentions* (give it a name and a
syntactic home) and *forbid what it doesn't* (no degree of freedom
without a name). The first half is generous; the second is strict;
the system works because you apply both.

## Every part of the explanation gets a home

If a true explanation of the system says "layer A talks to layer B
through X," but X exists only as a scatter of attribute calls
across a dozen sites, then the code disagrees with its own
explanation — X is real but homeless. Pulling the pattern out into
a named interface isn't tidiness; it's repairing the coincidence
between structure and explanation. The instinct to pull out a pattern
embedded in the calls to another layer is exactly this: anything the
explanation would mention must be a thing you can point at.

The visual-clarity rules are the same repair at the reading scale.
Explanations come in human-sized steps, and a unit of code — a
line, a function, a file — should be one step. That's why the
splitting metric was never line count but comprehension load:
a unit is too big precisely when it stops being one step of an
explanation and becomes several, forcing the reader to do the
decomposition the author skipped. Long, unabbreviated names are
the same idea at the smallest grain — each name carries its full
step of meaning in place, so reading never requires a side lookup.

Whitespace is the typography of the explanation. A written
argument breaks into paragraphs at its steps; spaced-out code
does the same, and the room-to-breathe rule — a blank line after
a block's ending token — is what lets a multi-line block be
perceived as one step rather than bleeding into the next.
Vertical alignment is the opposite move, which is why it's
banned: ASCII-art columns assert a relationship between
neighboring lines that the explanation doesn't carry, and they
falsify the one explanation git maintains automatically — the
diff. A one-token change that re-aligns a block reads as a
rewrite of the block, so the diff stops coinciding with the
change. Alignment is decoration bought at the cost of a
checkable record.

Cyclomatic complexity gives the same rule its control-flow form.
Each independent path through a function is a claim the
explanation must carry — that is literally what the metric
counts, and what a test suite must cover. A function with too
many paths is several steps crushed into one, and splitting it
does more than shrink it: the extraction demands a name, and the
name gives a syntactic home to a step that had been living
anonymously inside the control flow. Splitting on complexity and
reading at one altitude reinforce each other — the split
manufactures the lower tier that the altitude rule then
organizes.

Nesting depth is the same load measured vertically. Each level
of indentation is a clause held open — context the reader must
keep suspended until the code marches back out of the "V" — so
the tolerance is two levels at most, with zero as the ideal. And
the honest way to reach zero is reification again: a loop inside
a loop is an unnamed iteration pattern, while a higher-order
operation (map, filter, group-and-apply) is that same pattern
given a name from the language's own vocabulary. Where the
language lacks the vocabulary, forcing zero mints wrapper
functions that name nothing — "perform this thing over this
group" — and a name that carries no meaning is boilerplate, not
explanation. That is the easing clause applied honestly: the
constraint yields exactly where the names it would force are
empty.

## The file is the explanation, written top-down

One practice makes the coincidence literal rather than analogical:
organize each file highest abstraction first — public functions,
then the tier-1 private functions they call, then tier-2, and so
on down. That is the shape of a well-written argument: thesis
first, then supporting steps, each elaborated below. And it grants
the reader an argument's privilege — stop at any depth and leave
with a complete understanding at that grain.

The single-level-of-abstraction rule is what keeps each step
well-formed. A public function reads as a collection of tier-1
calls; a tier-1 function reads as tier-2 calls; every unit tells
its story in the vocabulary of the level one step below. A
function that mixes a tier-1 call with raw tier-3 manipulation is
several steps of the explanation crushed into one, forcing the
reader to change altitude mid-sentence — the same defect the
comprehension-load splitting rule exists to prevent, now stated
precisely: a human-sized step is one thought, at one altitude.

The minimal public interface is the strict half applied at the
module boundary. Every public symbol is a standing promise — a
clause the explanation must carry for every caller, forever, and
the hardest kind of clause to retract. So the surface is the
most minimal one that still expresses the domain, flexible only
where flexibility has earned its clause — and no smaller: a
call-site hack is a clause the surface refused to carry, the
sign it was minimized past expressiveness. Whatever stays
private only ever has to be explained to the file itself.

## Nothing varies without a name

The strict half. Every degree of freedom in a system — every place
where behavior can differ from one run, environment, or moment to
the next — is a clause the explanation must carry. An unnamed one
is a hole in the explanation: hidden state is the classic case, a
variable in the system's behavior that no signature admits to.

Collaborators-only classes enforce this at the unit scale. When
the only instance variables are injected collaborators, the class
*is* its role in the explanation: "given these collaborators, it
does this." There is no residue — no accumulated history that
makes the same call mean something different the second time.
Admin-type state (counters and the like) is admissible because it
is named and inert to the story. Anything else stateful must earn
its place with a specific reason, which is to say: with a clause
in the explanation.

The factory's minimal signature enforces it at the system scale,
and this is the sharpest instance of the whole principle. The
factory is the one construction path, matched to the production
grand instantiation — and its argument list is a complete sentence:
*these, and only these, are the respects in which an end-to-end
test environment may differ from reality.* Everything not in the
list is guaranteed identical, not assumed identical. The contract
between test and production isn't documented next to the code; it
is the code's own signature.

## Seams are the joints of the explanation

A seam is anywhere two parts of a system can vary independently.
Dependency injection through interfaces is often described as a
testing convenience, but under this reading it's something
stronger: it puts every seam where it can be seen. An interface
declares who may talk to whom and in what vocabulary; injection
moves the joint to the constructor, in plain sight, instead of
leaving it buried inside a method that reaches across layers.

Good explanations have few joints, all deliberate. So do good
systems: create exactly the seams that reality demands — the
environment boundary, the genuinely stateful resource — and make
each one a first-class, visible artifact. An accidental seam is a
lie the code tells about itself: a place where the system can vary
that its structure never admits to.

## Tests are the checkable half of the explanation

A test is a claim about the system that a computer re-verifies on
every run. The suite, taken together, is the explanation made
falsifiable — which recasts the testing positions as corollaries
rather than habits:

- **The pyramid is a default** because most true claims about a
  system are local ones, and local claims are cheap to check. It
  buys the most verified explanation per unit of effort.
- **Deviating from the pyramid is common and correct** because the
  claims worth checking follow the structure of the *problem*, not
  a doctrine. Where the problem's real shape demands a particular
  test strategy, following it is fidelity, not lapse.
- **End-to-end tests structured along user journeys** are the top
  of the explanation: "what is this system for, as experienced?" An
  e2e suite shaped like the user stories reads as a statement of
  the system's purpose — and stays honest because it must pass.
- **The factory is what attaches the checkable explanation to
  reality.** Tests that build the system through the shipping
  wiring are claims about the thing you deploy. Tests that build
  it through bespoke setup are claims about a lab replica, and the
  two drift silently apart.

## "Well-tested and explainable" is one property, not two

A system is testable exactly where its explanation is precise
enough to check; a test is an explanation read by a machine, and
an explanation is a test read by a human. Where explainability
goes missing, that's not bad luck — it marks a hole in the
explanation, and the hole is almost always an unnamed degree of
freedom: hidden state, an accidental seam, a second construction
path.

So the practices aren't a bundle of preferences that happen to
produce quality. They are one discipline — keep the code
coincident with a small, complete, checkable explanation of the
system — applied at every scale from a variable name to the
deployment story. And the discipline carries its own humility
clause: an explanation is judged by contact with the problem, so
any practice yields the moment the problem genuinely disagrees.
That isn't a caveat bolted onto the philosophy; it's the
philosophy applied to itself.
