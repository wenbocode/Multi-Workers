"""Run the read-only ``npm run check`` substeps and record them.

The full ``npm run check`` is not equivalent (it runs ``biome --write``, tsgo and
the browser smoke check), so only the read-only substeps are run here.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
LOG = pathlib.Path(__file__).resolve().parent / "logs" / "check-substeps.log"
STEPS = (
    "check:pinned-deps",
    "check:ts-imports",
    "check:shrinkwrap",
    "check:install-lock:coding-agent",
)


def main() -> int:
    lines = [
        "read-only check substeps (full 'npm run check' NOT run: it contains",
        "biome --write, tsgo, browser-smoke; not equivalent)",
        "",
    ]
    worst = 0
    for step in STEPS:
        lines.append(f"> npm run {step}")
        proc = subprocess.run(
            ["npm", "run", step],
            cwd=REPO,
            capture_output=True,
            text=True,
            shell=True,
        )
        lines.append((proc.stdout + proc.stderr).rstrip())
        lines.append(f"rc={proc.returncode}")
        lines.append("")
        worst = max(worst, proc.returncode)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return worst


sys.exit(main())
