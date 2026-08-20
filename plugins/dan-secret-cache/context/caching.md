# Resolving secrets

A preference, not a mechanism. It rests on two facts about how secret managers and agents
meet; the facts are worth knowing either way, and caching is one defensible response.

**The first fact:** a secret manager gated on biometrics raises its approval on the desktop,
not in the terminal. A session sees a command that took a little longer and then succeeded,
so it reads its own exit status as evidence that resolving was free. It is not, and the
person approving is the only party who can see the cost.

**The second fact:** that approval is granted to a *process*, and dies with it. A Claude Code
Bash call is a new shell every time, so nothing approved is ever reused — every resolution
from inside a session is a fresh approval, raised where nobody is looking.

**The rule:** resolve through `get-secret <op-reference>`, never `op read`. It answers from
the login keychain without contacting 1Password at all, so a secret costs one approval on
first use and none afterwards. A hook in this plugin denies the raw form and names the
replacement, turning a prompt into a retry — and it binds only where `get-secret` is on PATH,
so uninstalling the plugin stops the convention rather than stranding you.

- **A cached secret is held until something rejects it.** There is no expiry, because
  checking one against the manager would cost the approval the cache exists to avoid. Treat
  an authentication failure as the signal: `get-secret --invalidate <reference>`, then retry
  once, rather than concluding the secret is wrong.
- **A cold cache fails rather than prompting.** With no terminal on stderr, `get-secret`
  refuses and names what would warm it, because a dialog nobody can answer is a hang rather
  than a question. Warm it from a terminal, or with `/dan-secret-cache:warm`.
- **Discovery is exempt and worth paying for once.** `op item list` and `op item get` have no
  cached form and prompt every time. The waste is not looking an item up, it is looking the
  *same* item up twice: carry its reference and field layout for the rest of the session, and
  write it down where the work lives. `get-secret --list` says what is already cached and
  prompts for nothing.
- **Two dialogs can ask, and they are fixed in different places.** The manager's biometric prompt
  comes from its desktop app, and is the one the cache removes; Claude Code's permission prompt
  comes from `permissions.allow` in `~/.claude/settings.json`, and no amount of caching touches
  it. A command can be silent at one layer and still prompt at the other, so when approvals
  persist, establish which layer is asking before changing anything — the answer decides which
  file to edit. A `get-secret` call made *inside* an already-allowlisted command is a subprocess
  and raises neither.
- **Resolving a secret is worth leaving un-allowlisted.** `Bash(get-secret --list)` and
  `Bash(get-secret --invalidate *)` are safe to allow, since neither can print a secret value. A
  bare `get-secret <reference>` is not: its output *is* the secret, so an allowlisted call would
  drop it into the transcript unprompted. Widening to `Bash(get-secret *)` gives that up — the
  prompt is what keeps the rule below from resting on good intentions alone.
- **Never echo a resolved value** into the conversation, a command line, or a file. Reference
  it and let it resolve at runtime — `export TOKEN="$(get-secret 'op://…')"`, never a literal.
  Materializing it copies it into the transcript, scrollback, shell history, and `ps`.
