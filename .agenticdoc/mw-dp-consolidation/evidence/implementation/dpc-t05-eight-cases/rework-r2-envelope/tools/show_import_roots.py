"""Print the real import roots the tests/CLI resolve for the shared modules.

The T10 dependency window only means something if the imports resolve inside the
implementation copy; this prints each module's ``__file__`` and its parent.
"""

from __future__ import annotations

import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent
KEY = EVIDENCE.parents[3]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"

sys.path.insert(0, str(PKG))

import decision_book  # noqa: E402
import decision_lifecycle  # noqa: E402
import decision_task_state  # noqa: E402
import decision_wire  # noqa: E402

modules = {
    module.__name__: {
        "file": module.__file__,
        "import_root": str(pathlib.Path(module.__file__).resolve().parent),
        "inside_copy": pathlib.Path(module.__file__).resolve().parent
        == PKG.resolve(),
    }
    for module in (decision_book, decision_wire, decision_lifecycle, decision_task_state)
}
print(json.dumps({"package_copy": PKG.as_posix(), "modules": modules}, ensure_ascii=False, indent=2))
