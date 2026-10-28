"""mutants.py - T05j mutation checks (guards, never used as the RED).

Usage: ``python mutants.py <package-copy> <mutation>``

Each mutation removes exactly one part of the seam implementation in a throwaway
copy of the package, so the new tests must fail on it. The mutations

``no_bind``         drop the per-call pin of a caller-owned client;
``no_coverage``     accept any caller-owned redactor without verification;
``no_capture``      build the capture redactor without the snapshot;
``no_cli_pin``      hand the CLI client no snapshot (its own resolution).

Nothing here writes to the working tree: the target is a temporary copy.
"""

from __future__ import annotations

import pathlib
import sys

PACKAGE = pathlib.Path(sys.argv[1])
MUTATION = sys.argv[2]


def _edit(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"mutation anchor not found in {path.name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def no_bind(package: pathlib.Path) -> None:
    _edit(
        package / "decision_points.py",
        "    try:\n        client._pinned_credential_snapshot = snapshot\n    except AttributeError as exc:",
        "    try:\n        pass\n    except AttributeError as exc:",
    )


def no_coverage(package: pathlib.Path) -> None:
    _edit(
        package / "decision_points.py",
        "    if scope is None or snapshot is None:\n        return None\n    secret = getattr(snapshot, \"api_key\", None)",
        "    return None\n    secret = getattr(snapshot, \"api_key\", None)",
    )


def no_capture(package: pathlib.Path) -> None:
    _edit(
        package / "decision_points.py",
        "                cfg, extra_secrets=known_secret_superset(snapshot), snapshot=snapshot\n            )\n            if cfg is not None",
        "                cfg, extra_secrets=known_secret_superset(snapshot)\n            )\n            if cfg is not None",
    )


def no_cli_pin(package: pathlib.Path) -> None:
    _edit(
        package / "mw.py",
        "    client = decision.DecisionClient(\n        cfg, project_root=project_dir, credential_snapshot=credential_snapshot\n    )",
        "    client = decision.DecisionClient(cfg, project_root=project_dir)",
    )


MUTATIONS = {
    "no_bind": no_bind,
    "no_coverage": no_coverage,
    "no_capture": no_capture,
    "no_cli_pin": no_cli_pin,
}


def main() -> int:
    mutation = MUTATIONS.get(MUTATION)
    if mutation is None:
        raise SystemExit(f"unknown mutation {MUTATION!r}")
    mutation(PACKAGE)
    print(f"applied {MUTATION} to {PACKAGE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
