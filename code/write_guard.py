"""R0 safety harness: refuse any file write, rename or delete outside the workspace.

Import this module first (or `exec` it in the first cell of a working-copy notebook).
It installs a CPython audit hook that raises PermissionError when code tries to:
  * open a file in a write/append/create mode outside the allowed roots, or
  * rename, remove, rmdir, mkdir, chmod or truncate a path outside the allowed roots.
Allowed root: this repository.
Reads are never blocked.

Audit hooks cannot be removed once installed; that is intentional.
"""
import os
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))   # repository root


def _resolve(p):
    if isinstance(p, int):  # file descriptor; opened earlier through a checked path
        return None
    if isinstance(p, bytes):
        p = os.fsdecode(p)
    return os.path.realpath(os.fspath(p))


def is_allowed(p):
    r = _resolve(p)
    if r is None:
        return True
    if r == "/dev/null":
        return True
    return r == WORKSPACE or r.startswith(WORKSPACE + os.sep)


_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_PATH_EVENTS = {
    "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,), "os.chmod": (0,),
    "os.truncate": (0,), "os.rename": (0, 1), "os.replace": (0, 1),
    "os.symlink": (1,), "os.link": (1,), "shutil.rmtree": (0,),
    "shutil.copyfile": (1,), "shutil.move": (1,),
}


def _hook(event, args):
    if event == "open":
        path, mode, flags = args
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
                  (isinstance(flags, int) and flags & _WRITE_FLAGS)
        if writing and path is not None and not is_allowed(path):
            raise PermissionError(f"[write_guard] write refused outside workspace: {path}")
    elif event in _PATH_EVENTS:
        for i in _PATH_EVENTS[event]:
            if i < len(args) and args[i] is not None and not is_allowed(args[i]):
                raise PermissionError(f"[write_guard] {event} refused outside workspace: {args[i]}")


if not getattr(sys, "_write_guard_installed", False):
    sys.addaudithook(_hook)
    sys._write_guard_installed = True
