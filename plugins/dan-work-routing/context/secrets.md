# Handling secrets

A credential is a sensitive value under the same rule as member data: it must
not enter a transcript. The ladder does not apply — there is no aggregate form
of a password — so the discipline is simply never to materialize one.

- **Never echo a resolved secret value** into the conversation, a command line,
  or a file — not the password, key, or token itself. Reference it by its
  address in the secrets manager and let it resolve at runtime
  (`export SSHPASS="$(<resolve-command>)"` then `sshpass -e …`, never
  `sshpass -p '<literal>'`). Materializing the value copies it into the
  transcript, terminal scrollback, shell history, and the process list (`ps`) —
  everywhere a secrets manager exists to keep it out of.

- **This holds even when the value arrives from outside** — pasted by the user,
  or surfaced in earlier tool output. Don't repeat it; keep it
  referenced-only.

- **If a secret does get exposed in plaintext, say so** and recommend rotating
  it. A quiet exposure is worse than an awkward one.

- **Look a secret up once per integration.** Discovery — asking the secrets
  manager what exists and what fields an item has — typically costs an approval
  each time, and that is worth paying once. The waste is not looking an item
  up, it is looking the *same* item up twice. Once a secret's reference and
  field layout are known, carry them for the rest of the session and write the
  reference down where the work lives, rather than re-fetching to re-read one
  field.

- **A resolution you cannot see may be costing someone an approval.** A secrets
  manager gated on biometrics raises its prompt on the desktop, not in the
  terminal: the command simply takes longer and then succeeds, so a session
  reads its own exit status as evidence that resolving was free. It is not.
  Treat every resolve as though it interrupts a person — resolve once and carry
  the value for the rest of the work rather than re-resolving per call, and when
  a run needs several, say so first rather than spending their attention a
  prompt at a time without mentioning it.

