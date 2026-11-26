"""Makes every file and folder a process creates readable by its owner alone.

The adapters write fetched text, the credential writers write keys and
sessions, and both land on a disk other accounts may share. A mode given file by
file is one a new write site can forget, so each entry point sets the process
umask once instead, before it creates anything: a new file is 0600 and a new
folder 0700, whatever the caller's own umask was.

On Windows there are no mode bits for this to clear, and a file's ACL is the
control, so it does nothing there.
"""

import os

OWNER_ONLY = 0o077


def owner_only():
    if os.name != "nt":
        os.umask(OWNER_ONLY)
