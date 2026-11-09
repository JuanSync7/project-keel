"""
title: Atomic text and bytes publication
kind: script
layer: n/a
summary: Publishes UTF-8 text or bytes through exclusive sibling temporary files, retaining an existing target's permissions or applying the creation umask to 0666 for a new target. Flushes and fsyncs before os.replace; any publication error removes the temporary file and propagates. Identical contents leave the target untouched.
effect: writes
rerun: fixed-point
rerun_proof: test:tests/unit/scripts/test_atomic_write.py
"""

import os
import stat
import uuid
from typing import Optional, Union

__all__ = ["write_if_changed"]


def write_if_changed(path: str, data: Union[str, bytes]) -> bool:
    """Publish UTF-8 text or bytes to path, returning whether contents changed.

    Preserve an existing target's mode, or create with 0666 filtered by the
    current umask. Create missing parents, fsync before atomic replacement,
    and remove the sibling temporary file before propagating an error.
    """
    content = data.encode("utf-8") if isinstance(data, str) else data
    mode: Optional[int]
    try:
        with open(path, "rb") as fh:
            if fh.read() == content:
                return False
            mode = stat.S_IMODE(os.fstat(fh.fileno()).st_mode)
    except FileNotFoundError:  # noqa: DROP001 -- a missing target is created below
        mode = None
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    scratch = os.path.join(folder, ".atomic-%s.tmp" % uuid.uuid4().hex)
    # Exclusive creation honours the umask without changing process-wide state;
    # a collision must fail before cleanup can remove a file we do not own.
    created = False
    try:
        with open(scratch, "xb") as stream:
            created = True
            stream.write(content)
            if mode is not None:
                os.chmod(scratch, mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(scratch, path)
    except BaseException:
        if created:
            os.unlink(scratch)
        raise
    return True
