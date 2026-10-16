"""goal.md loader + write gate (mw-goal-gate-write-intent).

Two things are pinned here:

1. `mw._goal_gate_install` installs the repo template `goal.ts` into pi's global
   extensions dir (idempotent, drift-overwriting) — the file used to exist only
   as a hand-installed copy in `~/.pi/agent/extensions/` with no tests (debt
   Q-GOAL-1 in `.agenticdoc/_scratch/quality-gate-drift-guard-20260902.md`).
2. the bash write-intent classifier between the template's
   `GOAL-GATE-CLASSIFIER-BEGIN/END` sentinels, executed verbatim by node.

The vectors are the regression lock for the 2026-10-16 report ("reading goal.md
gets blocked too; only writes should be"): the old classifier gated every
command that merely *mentioned* goal.md, so read-only python/node one-liners
(goal mtime bookkeeping, goal-alignment reads) were hard-blocked for workers
and prompted for a yes/no confirmation in interactive windows.

The classifier is extracted from the shipped template text (not a copy) so the
test cannot drift from what mw installs; node does the TypeScript stripping, so
the block needs no hand-maintained regex surgery.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Final

import pytest

import mw

TEMPLATE: Final = pathlib.Path(mw.__file__).parent / "goal.ts"
BEGIN: Final = "// GOAL-GATE-CLASSIFIER-BEGIN"
END: Final = "// GOAL-GATE-CLASSIFIER-END"

# Read-only commands: the gate must NOT fire (session must not prompt/block).
READ_ONLY_COMMANDS: Final = [
    "type .agenticdoc\\goal.md",
    "Get-Content -Raw -Encoding UTF8 .agenticdoc/goal.md",
    "cat .agenticdoc/goal.md",
    "head -40 .agenticdoc/goal.md",
    "wc -l goal.md",
    "ls -l .agenticdoc/goal.md",
    "Select-String -Path .agenticdoc/goal.md -Pattern Goal",
    "grep -n 'Goal' .agenticdoc/goal.md",
    "grep -rn 'rm' .agenticdoc/goal.md",
    "rg -n 'copy' -- .agenticdoc/goal.md",
    "git diff -- .agenticdoc/goal.md",
    "git log -1 -- .agenticdoc/goal.md",
    "git show HEAD:.agenticdoc/goal.md",
    "git ls-files --error-unmatch .agenticdoc/goal.md",
    "node -e \"const fs=require('node:fs');console.log(fs.readFileSync('.agenticdoc/goal.md','utf8'))\"",
    "node -e \"const fs=require('node:fs');console.log(fs.statSync('.agenticdoc/goal.md').mtimeMs)\"",
    "python -X utf8 -c \"import os;print(os.stat('.agenticdoc/goal.md').st_mtime_ns)\"",
    (
        "python -X utf8 -c \"from pathlib import Path;p=Path('.agenticdoc/goal.md');"
        "print(p.read_text(encoding='utf-8'))\""
    ),
    "python -c \"print(open('.agenticdoc/goal.md','r',encoding='utf-8').read())\"",
    "python -c \"import pathlib;print(pathlib.Path('.agenticdoc/goal.md').read_text())\"",
    "pwsh -c \"Get-Content .agenticdoc/goal.md\"",
    "powershell -Command \"Get-Content -Raw '.agenticdoc/goal.md'\"",
    "cp .agenticdoc/goal.md /tmp/goal.bak",
    "copy goal.md %TEMP%\\goal.bak",
    "Copy-Item .agenticdoc/goal.md $env:TEMP\\goal.bak",
    "sed -n '1,20p' .agenticdoc/goal.md",
    "perl -ne 'print' goal.md",
    "awk '{print $1}' goal.md",
    "Set-Location H:/git/Multi-Workers; Get-Content -Raw .agenticdoc/goal.md",
    "cd H:/git/Multi-Workers && python -X utf8 -c \"print(open('.agenticdoc/goal.md').read())\"",
    "rm /tmp/other.md",
]

# Write commands: the gate MUST fire (writes stay gated).
WRITE_COMMANDS: Final = [
    "echo x > .agenticdoc/goal.md",
    "echo x >> goal.md",
    "cat x | tee .agenticdoc/goal.md",
    "Set-Content -Path .agenticdoc/goal.md -Value x",
    "Add-Content goal.md x",
    "Clear-Content .agenticdoc/goal.md",
    "Out-File goal.md",
    "rm .agenticdoc/goal.md",
    "del goal.md",
    "Remove-Item .agenticdoc/goal.md",
    "Move-Item .agenticdoc/goal.md goal.md.bak",
    "mv goal.md goal.md.bak",
    "mv other.md goal.md",
    "Rename-Item goal.md goal.bak",
    "git checkout -- .agenticdoc/goal.md",
    "git restore .agenticdoc/goal.md",
    "git reset --hard HEAD -- .agenticdoc/goal.md",
    "git stash push -- .agenticdoc/goal.md",
    "sed -i 's/a/b/' .agenticdoc/goal.md",
    "perl -i -pe 's/a/b/' goal.md",
    "cp other.md goal.md",
    "copy other.md goal.md",
    "Copy-Item other.md .agenticdoc/goal.md",
    "python -c \"open('.agenticdoc/goal.md','w').write('x')\"",
    "python -X utf8 -c \"from pathlib import Path;Path('.agenticdoc/goal.md').write_text('x')\"",
    "python -X utf8 -c \"from pathlib import Path;p=Path('.agenticdoc/goal.md');p.write_text('x')\"",
    "node -e \"require('node:fs').writeFileSync('.agenticdoc/goal.md','x')\"",
    "pwsh -c \"Set-Content goal.md 'x'\"",
    "truncate -s 0 .agenticdoc/goal.md",
    "shred -u goal.md",
]

# Node harness: strip the sentinel block into a temp .mts, import it, judge every
# case, and print a JSON map. `--experimental-strip-types` does the TS removal, so
# the executed code is exactly the shipped text.
_NODE_HARNESS: Final = (
    "import { readFileSync } from 'node:fs';"
    "const mod=await import(process.env.MW_GOAL_GATE_MODULE);"
    "const cmds=JSON.parse(readFileSync(process.env.MW_GOAL_GATE_CASES,'utf8'));"
    "const out=cmds.map((c)=>[c,mod.bashWritesGoalMd(c)]);"
    "console.log('MW_GOAL_GATE_JSON_BEGIN'+JSON.stringify(out)+'MW_GOAL_GATE_JSON_END');"
)


def _classifier_block() -> str:
    """The pure classifier text between the template's sentinels (fail-closed)."""
    text = TEMPLATE.read_text(encoding="utf-8")
    assert BEGIN in text, f"classifier begin sentinel missing from {TEMPLATE}"
    assert END in text, f"classifier end sentinel missing from {TEMPLATE}"
    body = text.split(BEGIN, 1)[1].split(END, 1)[0]
    assert "function bashWritesGoalMd" in body, "extracted block has no bashWritesGoalMd"
    return body


def _judge(commands: list[str], tmp_path: pathlib.Path) -> dict[str, bool]:
    """Run the template's classifier over `commands`, fail-closed on any breakage."""
    node = shutil.which("node")
    if node is None:
        pytest.fail("node interpreter not found; the goal gate classifier cannot be measured (fail-closed)")
    module = tmp_path / "goal-gate-extract.mts"
    module.write_text(f"{_classifier_block()}\nexport {{ bashWritesGoalMd }};\n", encoding="utf-8")
    cases = tmp_path / "goal-gate-cases.json"
    cases.write_text(json.dumps(commands), encoding="utf-8")
    env = dict(
        **os.environ,
        MW_GOAL_GATE_MODULE=module.as_uri(),
        MW_GOAL_GATE_CASES=str(cases),
    )
    proc = subprocess.run(
        [node, "--experimental-strip-types", "--input-type=module", "-e", _NODE_HARNESS],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or "MW_GOAL_GATE_JSON_BEGIN" not in proc.stdout:
        pytest.fail(
            f"node classifier harness failed (exit {proc.returncode}):\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    payload = proc.stdout.split("MW_GOAL_GATE_JSON_BEGIN", 1)[1].split("MW_GOAL_GATE_JSON_END", 1)[0]
    judged = json.loads(payload)
    assert len(judged) == len(commands), "harness returned a different number of verdicts than cases"
    return {cmd: bool(verdict) for cmd, verdict in judged}


class TestClassifierExtraction:
    """The extraction contract the node harness depends on (AC-005)."""

    def test_sentinels_and_pure_block(self) -> None:
        body = _classifier_block()
        assert "GOAL_REF" in body and "splitSegments" in body
        # The block must stay free of runtime imports: it is executed standalone.
        assert "@earendil-works/pi-coding-agent" not in body
        assert "require(" not in body

    def test_template_exists_next_to_mw_py(self) -> None:
        assert TEMPLATE.is_file(), f"goal.ts template missing: {TEMPLATE}"


class TestClassifierVectors:
    """The regression lock: reads pass, writes stay gated (AC-001 / AC-002)."""

    def test_read_only_commands_are_not_gated(self, tmp_path: pathlib.Path) -> None:
        verdicts = _judge(READ_ONLY_COMMANDS, tmp_path)
        gated = [cmd for cmd, verdict in verdicts.items() if verdict]
        assert gated == [], f"read-only commands must not be gated: {gated}"

    def test_write_commands_are_gated(self, tmp_path: pathlib.Path) -> None:
        verdicts = _judge(WRITE_COMMANDS, tmp_path)
        missed = [cmd for cmd, verdict in verdicts.items() if not verdict]
        assert missed == [], f"write commands must stay gated: {missed}"

    def test_empty_and_non_goal_commands_are_not_gated(self, tmp_path: pathlib.Path) -> None:
        verdicts = _judge(["", "ls", "rm -rf /tmp/nothing.md", "git status"], tmp_path)
        assert not any(verdicts.values()), verdicts


class TestGoalGateInstall:
    """`mw._goal_gate_install`: template → pi global extensions dir.

    Isolated via PI_CODING_AGENT_DIR (mw_common.global_ext_dir honors it)."""

    def test_installs_when_absent(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agent_dir = tmp_path / "pi-agent"
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
        ok, msg = mw._goal_gate_install()
        assert ok, msg
        assert "installed" in msg
        dst = agent_dir / "extensions" / "goal.ts"
        assert dst.is_file()
        assert dst.read_bytes() == TEMPLATE.read_bytes()

    def test_idempotent_when_identical(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agent_dir = tmp_path / "pi-agent"
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
        mw._goal_gate_install()
        ok, msg = mw._goal_gate_install()
        assert ok, msg
        assert "up-to-date" in msg

    def test_overwrites_drifted_copy(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The 2026-10-16 over-broad heuristic was exactly such a drift."""
        agent_dir = tmp_path / "pi-agent"
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent_dir))
        dst = agent_dir / "extensions" / "goal.ts"
        dst.parent.mkdir(parents=True)
        dst.write_text("// drifted hand-install (gated every goal.md mention)\n", encoding="utf-8")
        ok, msg = mw._goal_gate_install()
        assert ok, msg
        assert "installed" in msg
        assert dst.read_bytes() == TEMPLATE.read_bytes()
