# Handling secrets

A credential must never enter a transcript. There is no aggregate form of a
password, so the discipline is simply never to materialize one.

- **Never echo a resolved secret** into the conversation, a command line, or a
  file. Reference it by its address in the secrets manager and let it resolve
  at runtime — `export SSHPASS="$(<resolve-command>)"` then `sshpass -e …`,
  never `sshpass -p '<literal>'`. A materialized value lands in the transcript,
  scrollback, shell history, and `ps`.
- **The same holds for a value that arrives from outside** — pasted by the
  user, or surfaced in earlier tool output. Don't repeat it.
- **If a secret is exposed in plaintext, say so** and recommend rotating it.
- **Look a secret up once per integration.** Discovery costs an approval each
  time, which is worth paying once; the waste is looking the same item up
  twice. Carry the reference and field layout for the session and write the
  reference down where the work lives.
- **A resolve you cannot see may be costing someone an approval.** A manager
  gated on biometrics prompts on the desktop, not in the terminal, so a
  resolve looks free and is not. Resolve once and carry the value; when a run
  needs several, say so first.
