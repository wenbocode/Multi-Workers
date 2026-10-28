"""mw_console_guard -- windows subtree console guard (sitecustomize-mode).

Spec L2.  Injected via PYTHONPATH prefix + MW_CONSOLE_GUARD=1 by the runner.
Design-proven skeleton (RQ-3 Q2/Q3): idempotent patch of subprocess.Popen
so that calls with no explicit console semantics get CREATE_NO_WINDOW OR-ed in.

Contract (spec $2.3 / AC-005 / AC-006 / AC-007):
  - env switch only: no activation unless MW_CONSOLE_GUARD == "1"
  - explicit CREATE_NEW_CONSOLE / DETACHED_PROCESS flags are never rewritten
  - import is a no-op when inactive; patching failure fails OPEN (restore, warn)
  - POSIX: no-op
"""

import os
import sys

_patched = False            # module-level idempotency flag (double-import / re-patch self-check)


def _apply():
    """OR CREATE_NO_WINDOW into Popen creationflags when console semantics
    were not explicitly requested. Returns True on success (or nothing to do)."""
    import subprocess

    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return True  # non-Windows or ancient stdlib: nothing to guard

    orig = subprocess.Popen.__init__
    flag = subprocess.CREATE_NO_WINDOW
    EXPLICIT = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS

    def patched(self, *args, creationflags=0, **kwargs):
        """Guard wrapper (D-003): OR CREATE_NO_WINDOW when console semantics
        were not explicitly requested.

        NOTE (D-003 decision): creationflags passed POSITIONALLY (the 14th
        positional arg of Popen) is NOT supported - no signature mirroring.
        Because this wrapper declares `creationflags` keyword-only, such a call
        leaves the flag inside *args and collides with the explicit
        `creationflags=` keyword handed to the captured __init__: it fails LOUD
        with TypeError instead of silently running unguarded. Rationale:
        repo-wide grep found zero call sites using that positional form, so
        fail-loud is acceptable.
        """
        # OR CREATE_NO_WINDOW whenever the caller did not explicitly request
        # console semantics (CREATE_NEW_CONSOLE / DETACHED_PROCESS untouched).
        if (creationflags & EXPLICIT) == 0:
            creationflags = creationflags | flag
        return orig(self, *args, creationflags=creationflags, **kwargs)

    subprocess.Popen.__init__ = patched
    return True


def _activate():
    global _patched
    if _patched:
        return
    try:
        _apply()
        _patched = True
    except Exception as exc:                      # fail-open: never crash host
        sys.stderr.write(
            "mw_console_guard: patch failed, running unprotected: %r\n" % (exc,))


if os.name == "nt" and os.environ.get("MW_CONSOLE_GUARD") == "1":
    _activate()

del os, sys  # keep namespace clean (module still safely re-importable)
