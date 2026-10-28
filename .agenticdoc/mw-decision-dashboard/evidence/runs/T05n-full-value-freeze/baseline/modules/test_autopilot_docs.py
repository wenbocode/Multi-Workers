"""test_autopilot_docs.py — README/UPDATE doc parity for `mw autopilot verify`
(T-10, AC-010).

Pinned here (and only here — no whole-file snapshots, prose may change):

* the fenced `mw autopilot verify --help` block tagged
  `<!-- mw-autopilot-verify:help -->` in README is byte-identical (after EOL /
  trailing-space normalization, at a pinned 80-column width) to the real
  `python mw.py autopilot verify --help` output, so the manual cannot drift
  from the CLI surface silently (same contract as test_rag_docs.py VC-206);
* the frozen machine-layer semantics are anchored by regex: machine file path,
  env resolution order, `MW_AUTOPILOT_FILE` no-fallback, "empty value =
  undecided", out-of-domain key warn+ignore, `--project` required before `--`,
  `clear` never deletes the file, and the both-sides-same-version rollout;
* UPDATE.md §1 carries the A1b/A2b content anchors and §2 carries the CLI row
  with its project/machine 层级.

Any of these anchors disappearing turns the test red, which is the point: the
docs are the frozen contract for the machine/project layers.
"""
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
MW_PY = HERE / "mw.py"
README_PATH = HERE / "README.md"
UPDATE_PATH = HERE / "UPDATE.md"

HELP_TAG = "mw-autopilot-verify:help"

# (label, regex) — every one must be present in README.md.
README_ANCHORS = (
    ("machine file path", r"~/.agents/autopilot-defaults\.json"),
    ("env hard override", r"`MW_AUTOPILOT_FILE`"),
    ("env home override", r"`MW_AUTOPILOT_HOME`"),
    ("env resolution order", r"`MW_AUTOPILOT_HOME`\s*→\s*`HOME`\s*→\s*`USERPROFILE`"),
    ("env file set-but-missing no fallback", r"指向的文件不存在时不回落到其它位置"),
    ("machine-overridable pair", r"`xkey_verify_cmd`\s*\+\s*`xkey_verify_cwd`"),
    ("empty value means undecided", r"空值即未决定"),
    ("out-of-domain example keys", r"`xkey_repair`\s*/\s*`xkey_verify_timeout_s`"),
    ("out-of-domain warn and ignore", r"告警并忽略"),
    ("project flag required before separator", r"必填且必须在\s*`--`\s*之前"),
    ("clear never deletes the file", r"永不删除文件"),
    ("both sides same version rollout", r"先\s*`mw build --install`\s*，再重启各 pi 窗口的\s*`serve`"),
)


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _normalize(text: str) -> str:
    """The only allowed manual/CLI differences (parity contract)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _tagged_block(manual: str, tag: str) -> str:
    pattern = re.compile(
        r"<!-- " + re.escape(tag) + r" -->\s*```[A-Za-z]*\n(.*?)```",
        re.DOTALL,
    )
    match = pattern.search(manual)
    if match is None:
        raise AssertionError(f"README has no tagged fenced block for {tag!r}")
    return match.group(1)


def _help_output(*argv: str) -> str:
    """Real `mw autopilot verify ... --help`, pinned to an 80-column terminal.

    argparse derives its wrap width from ``COLUMNS`` (shutil.get_terminal_size),
    so the subprocess env pins it to make the byte comparison deterministic.
    """
    env = dict(os.environ)
    env.update({"COLUMNS": "80", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    result = subprocess.run(
        [sys.executable, str(MW_PY), "autopilot", "verify", *argv, "--help"],
        capture_output=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.decode("utf-8")


def _table_row(text: str, label: str) -> str:
    pattern = re.compile(r"^\|\s*" + re.escape(label) + r"\s*\|.*$", re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"no markdown table row labelled {label!r}")
    return match.group(0)


def test_readme_help_block_matches_cli() -> None:
    manual = README_PATH.read_text(encoding="utf-8")
    block = _normalize(_tagged_block(manual, HELP_TAG))
    actual = _normalize(_help_output())
    assert block == actual, (
        "README fenced `mw autopilot verify --help` block drifted from the CLI:\n"
        f"--- README ---\n{block}\n--- CLI ---\n{actual}"
    )
    # Subcommand names and the usage line are part of the byte-parity block.
    for token in ("usage: mw.py autopilot verify", "set", "show", "clear"):
        assert token in block, f"help block missing {token!r}"
    # `--project` is required and only visible in the per-action help; pin the
    # real help output so the README prose cannot claim a different contract.
    set_help = _normalize(_help_output("set"))
    assert "--project PROJECT" in set_help, set_help
    assert "--timeout SEC" in set_help, set_help
    _verify(
        "AC-010",
        fenced_block="byte-identical",
        block_bytes=len(block.encode("utf-8")),
        usage_line=block.splitlines()[0],
        set_help_project_required=True,
    )


def test_readme_semantic_anchors_present() -> None:
    manual = README_PATH.read_text(encoding="utf-8")
    missing = [label for label, pattern in README_ANCHORS if not re.search(pattern, manual)]
    assert not missing, f"README lost frozen semantics anchors: {missing}"
    _verify("AC-010", readme_anchors=len(README_ANCHORS), missing=0)


def test_update_matrix_has_project_machine_cli_row() -> None:
    update = UPDATE_PATH.read_text(encoding="utf-8")
    rows = [
        line
        for line in update.splitlines()
        if line.startswith("|") and "mw autopilot verify" in line
    ]
    assert rows, "UPDATE.md §2 has no `mw autopilot verify` row"
    assert any("项目/机器" in row for row in rows), rows
    for token in ("--project", "空值即未决定", "永不删除文件"):
        assert any(token in row for row in rows), f"CLI row missing {token!r}"
    _verify("AC-010", update_matrix_rows=len(rows), layer="项目/机器")


def test_update_anchor_table_has_a1b_a2b() -> None:
    update = UPDATE_PATH.read_text(encoding="utf-8")
    a1b = _table_row(update, "A1b")
    for token in ("GATE_KINDS", "xkey-gate-guard: blocked", "[XKEY_GATE]"):
        assert token in a1b, f"A1b row missing {token!r}: {a1b}"
    a2b = _table_row(update, "A2b")
    assert "sourcesContent" in a2b, f"A2b row missing sourcesContent: {a2b}"
    _verify("AC-010", a1b="content anchor", a2b="sourcemap anchor")
