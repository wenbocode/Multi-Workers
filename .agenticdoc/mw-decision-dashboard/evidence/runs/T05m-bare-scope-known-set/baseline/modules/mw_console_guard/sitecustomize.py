"""sitecustomize — mw_console_guard activator (PYTHONPATH-injected site hook).

Loaded by CPython's site machinery whenever this directory is prepended to
PYTHONPATH (RQ-3 Q1: python -c, python -X utf8 -m pytest, venv-shadowed
sitecustomize all resolve this copy first). Injection contract:
PYTHONPATH=<this dir>;<existing> + MW_CONSOLE_GUARD=1. The guard itself is
gated on that env switch; import is a no-op without it (see mw_console_guard).
"""

import mw_console_guard
