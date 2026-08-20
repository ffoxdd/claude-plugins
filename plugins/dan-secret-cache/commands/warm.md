---
description: Resolve a secret once, with you watching, so later calls come from the cache
---

Warm the keychain cache for an `op://` reference the user names, so that agent-side calls
resolve without raising an approval nobody can see.

The approval this raises is the point rather than a cost to avoid: the user invoked this
command, so they are at the keyboard and expecting it. That is what makes it different from
the same prompt arriving mid-task.

1. If the user gave no reference, run `get-secret --list` to show what is already cached, and
   ask which reference to warm. Do not guess one.
2. Run `GET_SECRET_ALLOW_PROMPT=1 get-secret '<reference>' --refresh >/dev/null`, and tell the
   user to expect a 1Password approval on their desktop. Redirect to `/dev/null` — the value
   must not enter the transcript.
3. Confirm with `get-secret --list` that the reference is now listed. Report the reference,
   never the value.

If the resolve fails, report what `get-secret` printed on stderr rather than retrying: a
wrong reference and an unsigned-in account fail differently, and it says which.
