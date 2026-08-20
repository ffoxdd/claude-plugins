# dan-secret-cache

Resolve secrets through `get-secret`, which caches in the login keychain, rather than calling
the secret manager on every use.

```
/plugin install dan-secret-cache@ffoxdd
```

## Why a cache rather than just calling `op`

1Password grants its approval to the *process* that asks, and that grant dies with the
process. Claude Code's Bash tool spawns a new shell for every tool call, so nothing approved
is ever reused: each resolution from inside a session is a fresh approval. Worse, it is raised
on the desktop rather than in the terminal, so a session sees only a command that took a
little longer and succeeded — and goes on spending approvals it cannot observe.

`get-secret` answers from the keychain without contacting 1Password at all. One approval per
secret on first use, none afterwards.

## What it ships

- **`get-secret`** on the Bash tool's PATH. `get-secret <op-reference>` resolves;
  `--refresh` re-reads and re-caches; `--invalidate <reference>` drops a copy; `--list` says
  what is cached, without prompting or printing any value.
- **A hook** denying `op read` and naming the replacement. It binds only where `get-secret` is
  on PATH, so it never strands a machine that does not have it. Discovery — `op item list`,
  `op item get` — is untouched.
- **`/dan-secret-cache:warm`** for the first resolve, where the approval is expected because
  you asked for it.

## The one thing to know

A cold cache **fails rather than prompts** when no terminal is attached, naming what would
warm it. That is deliberate: a dialog nobody can answer is a hang, not a question. Warm a
reference from your terminal, or with the command above, and agent-side calls stop paying for
it. `GET_SECRET_ALLOW_PROMPT=1` overrides when you know someone is watching.
