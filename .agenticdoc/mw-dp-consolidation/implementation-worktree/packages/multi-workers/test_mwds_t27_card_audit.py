"""test_mwds_t27_card_audit.py — L1 tests for autopilot/card_audit.py (T-06, AC-006).

Key ``mw-dispatch-card-gate``.  Four behavior classes required by the card:

1. **normal** — cards are collected, dispatches resolve to card ids, digests
   equal ``mw_common.sha256_eol_normalized``, CLI exit 0;
2. **missing card** (缺卡) — a dispatch names a card absent from ``tasks/``
   ⇒ ``missing_cards`` diff + exit 1 even without ``--strict`` (AC-006
   "卡片集合 ⊉ 派发集合 ⇒ 红并列差集");
3. **unlisted dispatch** (未登记派发) — a header-less historical ``task.md``
   lands in ``unlisted_dispatches``, is **not** red by default, and fails only
   under ``--strict`` (spec P-07 migration compatibility);
4. **equal-length tamper** (等长篡改) — an equal-length content substitution
   changes the digest and, because the dispatch records the original digest in
   its ``card_sha256:`` header, the audit reports it in ``tampered_cards`` and
   exits non-zero **without** ``--strict``; restoring the original bytes
   restores the green verdict (AC-006 篡改⇒红⇒恢复⇒绿).
5. **boundary** (T-12/F-06) — header-less dispatches are split by the
   task.md mtime versus ``launcher.ENVELOPE_ENFORCE_SINCE``: pre-boundary
   historical rows stay in ``unlisted_dispatches`` (strict-only), post-boundary
   rows land in ``unlisted_after_boundary`` and are red by default, while a
   card-less dispatch carrying the G-2 canonical headings (the T-10 generator
   shape) is not counted at all.

Plus edge coverage: the explicit non-card exclusion rule, body prose that
mentions ``card_path`` must not count as a reference, the fenced-frontmatter
header form, CRLF/LF digest stability, and a real CLI subprocess smoke test.

All fixtures build their own tree under ``tmp_path``; the real ``.agenticdoc``
is never written.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import card_audit  # noqa: E402

KEY = "mw-demo"
MODULE = pathlib.Path(card_audit.__file__)


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _make_key(tmp_path: pathlib.Path, key: str = KEY) -> tuple[pathlib.Path, pathlib.Path]:
    root = tmp_path / ".agenticdoc"
    key_dir = root / key
    (key_dir / "tasks").mkdir(parents=True)
    (key_dir / "workers").mkdir()
    return root, key_dir


def _write_card(key_dir: pathlib.Path, name: str, text: str) -> pathlib.Path:
    path = key_dir / "tasks" / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _write_dispatch(key_dir: pathlib.Path, worker: str, text: str) -> pathlib.Path:
    worker_dir = key_dir / "workers" / worker
    worker_dir.mkdir(parents=True, exist_ok=True)
    path = worker_dir / "task.md"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _run_cli(root: pathlib.Path, key: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(MODULE), "--root", str(root), "--key", key, *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _set_mtime(path: pathlib.Path, iso: str) -> None:
    """Pin a fixture file's mtime so the F-06 boundary arithmetic is explicit.

    The audit classifies a header-less dispatch by its ``task.md`` mtime versus
    ``launcher.ENVELOPE_ENFORCE_SINCE``; a fixture must state the time it
    claims instead of inheriting "now".
    """
    ts = datetime.datetime.fromisoformat(iso).replace(tzinfo=datetime.timezone.utc).timestamp()
    os.utime(path, (ts, ts))


# ── 1. normal ───────────────────────────────────────────────────────────────

def test_normal_dispatches_resolve_and_digest(tmp_path, capsys):
    root, key_dir = _make_key(tmp_path)
    alpha = _write_card(key_dir, "T-01-alpha.md", "# T-01\n\nbody alpha\n")
    beta = _write_card(key_dir, "T-02-beta.md", "# T-02\n\nbody beta\n")
    _write_dispatch(
        key_dir,
        "w-one",
        f"type: coding\ncard_path: .agenticdoc/{KEY}/tasks/T-01-alpha.md\n\nbody\n",
    )
    _write_dispatch(key_dir, "w-two", "type: coding\ncard_path: tasks/T-02-beta.md\n\nbody\n")

    result = card_audit.audit(root, KEY)

    assert result["cards"] == ["tasks/T-01-alpha.md", "tasks/T-02-beta.md"]
    assert [d["card"] for d in result["dispatched"]] == ["tasks/T-01-alpha.md", "tasks/T-02-beta.md"]
    assert [d["worker"] for d in result["dispatched"]] == ["workers/w-one", "workers/w-two"]
    assert all(d["in_cards"] for d in result["dispatched"])
    assert result["missing_cards"] == []
    assert result["unlisted_dispatches"] == []
    # digests are exactly the EOL-normalized sha256 of the cards
    assert result["digests"]["tasks/T-01-alpha.md"] == mw_common.sha256_eol_normalized(alpha)
    assert result["digests"]["tasks/T-02-beta.md"] == mw_common.sha256_eol_normalized(beta)
    # default = not red
    assert card_audit.has_findings(result, strict=False) is False
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 0
    out = capsys.readouterr().out
    assert "cards (2)" in out and "dispatched (2)" in out and "-> OK" in out
    _verify("VC-t27-normal", workers=2, cards=2, missing=0, unlisted=0)


def test_normal_accepts_key_relative_and_absolute_card_paths(tmp_path):
    root, key_dir = _make_key(tmp_path)
    card = _write_card(key_dir, "T-03-gamma.md", "# gamma\n")
    _write_dispatch(key_dir, "w-rel", f"type: coding\ncard_path: {KEY}/tasks/T-03-gamma.md\n\nx\n")
    _write_dispatch(key_dir, "w-abs", f"type: coding\ncard_path: {card}\n\nx\n")
    _write_dispatch(key_dir, "w-front", f"---\ntype: coding\ncard_path: tasks/T-03-gamma.md\n---\nbody\n")

    result = card_audit.audit(root, KEY)
    assert result["missing_cards"] == []
    assert result["unlisted_dispatches"] == []
    assert {d["worker"]: d["card"] for d in result["dispatched"]} == {
        "workers/w-abs": "tasks/T-03-gamma.md",
        "workers/w-front": "tasks/T-03-gamma.md",
        "workers/w-rel": "tasks/T-03-gamma.md",
    }
    _verify("VC-t27-forms", resolved=3)


def test_non_card_files_excluded_by_explicit_rule(tmp_path):
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-04-delta.md", "# real card\n")
    _write_card(key_dir, "_template.md", "template\n")
    _write_card(key_dir, "TEMPLATE.md", "template\n")
    _write_card(key_dir, "README.md", "readme\n")
    (key_dir / "tasks" / "notes.txt").write_text("not md\n", encoding="utf-8")

    result = card_audit.audit(root, KEY)
    assert result["cards"] == ["tasks/T-04-delta.md"]
    assert set(result["digests"]) == {"tasks/T-04-delta.md"}
    assert card_audit.is_card_file(key_dir / "tasks" / "T-04-delta.md") is True
    assert card_audit.is_card_file(key_dir / "tasks" / "_template.md") is False
    assert card_audit.is_card_file(key_dir / "tasks" / "TEMPLATE.md") is False
    assert card_audit.is_card_file(key_dir / "tasks" / "README.md") is False
    _verify("VC-t27-exclusion", cards=len(result["cards"]))


def test_body_prose_mentioning_card_path_is_not_a_reference(tmp_path):
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-05-eps.md", "# eps\n")
    prose = _write_dispatch(
        key_dir,
        "w-prose",
        "type: coding\n\n写入允许面：仅两个新文件；缺 card_path 头的历史派发计入 unlisted。\n",
    )
    # Pre-boundary historical row: the body prose still must not count as a
    # header reference (F-06 keeps it in the strict-only historical bucket).
    _set_mtime(prose, "2026-08-01T00:00:00+00:00")
    result = card_audit.audit(root, KEY)
    assert result["dispatched"] == []
    assert result["unlisted_dispatches"] == ["workers/w-prose"]
    assert result["unlisted_after_boundary"] == []
    _verify("VC-t27-prose", unlisted=len(result["unlisted_dispatches"]))


def test_post_boundary_unlisted_is_red_by_default(tmp_path, capsys):
    # F-06: a header-less dispatch whose task.md was written at/after the
    # boundary is a genuinely dropped reference, red without --strict.
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-01-alpha.md", "# alpha\n")
    dropped = _write_dispatch(key_dir, "w-dropped", "type: coding\n\nno card_path header\n")
    _set_mtime(dropped, "2026-10-13T00:00:00+00:00")

    result = card_audit.audit(root, KEY)
    assert result["unlisted_dispatches"] == []
    assert result["unlisted_after_boundary"] == ["workers/w-dropped"]
    assert card_audit.has_findings(result, strict=False) is True
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 1
    out = capsys.readouterr().out
    assert "unlisted_after_boundary [always FAIL]" in out
    assert "workers/w-dropped" in out and "-> FAIL" in out
    _verify("VC-t27-unlisted-after", after=1, exit_nonstrict=1)


def test_post_boundary_canonical_cardless_dispatch_is_not_unlisted(tmp_path):
    # T-10's legitimate card-less auto dispatch carries the G-2 canonical
    # headings and no card_path; it must not be counted, or --strict would be
    # permanently unusable after the cutover (F-06).
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-01-alpha.md", "# alpha\n")
    t10 = _write_dispatch(
        key_dir,
        "ap-k-t05",
        "type: phase-writer\n\n## 上下文\n\n自动派发（无任务卡；种子）。\n\n"
        "## 要求\n\n实现 X。\n\n## 交付格式\n\n产物 report.md。\n",
    )
    _set_mtime(t10, "2026-10-13T00:00:00+00:00")

    result = card_audit.audit(root, KEY)
    assert result["dispatched"] == []
    assert result["unlisted_dispatches"] == []
    assert result["unlisted_after_boundary"] == []
    assert card_audit.has_findings(result, strict=False) is False
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 0
    _verify("VC-t27-t10-cardless", red=False)


# ── 2. missing card ─────────────────────────────────────────────────────────

def test_missing_card_is_red_and_listed_as_diff(tmp_path, capsys):
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-01-alpha.md", "# alpha\n")
    _write_dispatch(key_dir, "w-ok", "type: coding\ncard_path: tasks/T-01-alpha.md\n\nx\n")
    _write_dispatch(key_dir, "w-gone", "type: coding\ncard_path: tasks/T-99-gone.md\n\nx\n")

    result = card_audit.audit(root, KEY)
    assert result["missing_cards"] == ["tasks/T-99-gone.md"]
    assert result["unlisted_dispatches"] == []
    assert card_audit.has_findings(result, strict=False) is True
    # missing is red even without --strict
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 1
    out = capsys.readouterr().out
    assert "missing_cards (1)" in out and "tasks/T-99-gone.md" in out and "-> FAIL" in out
    _verify("VC-t27-missing", missing=result["missing_cards"], exit_nonstrict=1)


# ── 3. unlisted dispatch (migration compatibility) ──────────────────────────

def test_unlisted_dispatch_not_red_unless_strict(tmp_path, capsys):
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-01-alpha.md", "# alpha\n")
    legacy = _write_dispatch(key_dir, "w-legacy", "type: coding\n\nlegacy dispatch, no card reference\n")
    manual = _write_dispatch(key_dir, "w-manual", "type: review\n\nmanual queue row\n")
    # Pre-boundary: both are historical rows (P-07 migration compatibility).
    _set_mtime(legacy, "2026-08-01T00:00:00+00:00")
    _set_mtime(manual, "2026-08-01T00:00:00+00:00")

    result = card_audit.audit(root, KEY)
    assert result["dispatched"] == []
    assert result["missing_cards"] == []
    assert result["unlisted_dispatches"] == ["workers/w-legacy", "workers/w-manual"]
    assert result["unlisted_after_boundary"] == []
    # default: historical dispatches are not red
    assert card_audit.has_findings(result, strict=False) is False
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 0
    out = capsys.readouterr().out
    assert "unlisted_dispatches [not red (use --strict to fail)]" in out and "-> OK" in out
    # strict: same tree fails
    assert card_audit.has_findings(result, strict=True) is True
    assert card_audit.main(["--root", str(root), "--key", KEY, "--strict"]) == 1
    out_strict = capsys.readouterr().out
    assert "unlisted_dispatches [strict: FAIL]" in out_strict and "-> FAIL" in out_strict
    _verify("VC-t27-unlisted", unlisted=len(result["unlisted_dispatches"]), nonstrict=0, strict=1)


# ── 4. equal-length tamper ──────────────────────────────────────────────────

def test_equal_length_tamper_is_red_and_restore_recovers(tmp_path, capsys):
    root, key_dir = _make_key(tmp_path)
    original = "# T-01\n\nvalue=AAAA\n"
    card = _write_card(key_dir, "T-01-alpha.md", original)
    recorded = card_audit.card_digest(card)
    _write_dispatch(
        key_dir,
        "w-one",
        f"type: coding\ncard_path: tasks/T-01-alpha.md\ncard_sha256: {recorded}\n\nx\n",
    )
    baseline = card_audit.audit(root, KEY)
    assert baseline["tampered_cards"] == []
    assert baseline["digests"]["tasks/T-01-alpha.md"] == recorded
    assert card_audit.has_findings(baseline, strict=False) is False
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 0
    capsys.readouterr()

    tampered = original.replace("AAAA", "BBBB")
    assert len(tampered) == len(original) and tampered != original
    card.write_text(tampered, encoding="utf-8", newline="")
    tampered_digest = card_audit.card_digest(card)
    assert tampered_digest != recorded

    after = card_audit.audit(root, KEY)
    assert after["digests"]["tasks/T-01-alpha.md"] == tampered_digest
    assert after["tampered_cards"] == [
        {
            "worker": "workers/w-one",
            "task_key": "w-one",
            "card": "tasks/T-01-alpha.md",
            "recorded": recorded,
            "current": tampered_digest,
        }
    ]
    # 篡改 ⇒ 红, and NOT only under --strict.
    assert card_audit.has_findings(after, strict=False) is True
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 1
    out = capsys.readouterr().out
    assert "tampered_cards [always FAIL] (1)" in out and "-> FAIL" in out

    card.write_text(original, encoding="utf-8", newline="")
    restored = card_audit.audit(root, KEY)
    assert restored["tampered_cards"] == []
    assert restored["digests"]["tasks/T-01-alpha.md"] == recorded
    assert card_audit.has_findings(restored, strict=False) is False
    assert card_audit.main(["--root", str(root), "--key", KEY]) == 0
    _verify(
        "VC-t27-tamper",
        recorded=recorded[:12],
        tampered=tampered_digest[:12],
        restored=card_audit.card_digest(card)[:12],
        equal_length=len(tampered) == len(original),
    )


def test_tamper_cli_subprocess_red_then_restore_green(tmp_path):
    # The card's mandated counterexample, through the real CLI exit code:
    # 等长篡改 ⇒ 非零退出 ⇒ 恢复 ⇒ 零退出.
    root, key_dir = _make_key(tmp_path)
    original = "value=AAAA\n"
    card = _write_card(key_dir, "T-01-alpha.md", original)
    digest = card_audit.card_digest(card)
    _write_dispatch(
        key_dir,
        "w-one",
        f"type: coding\ncard_path: tasks/T-01-alpha.md\ncard_sha256: {digest}\n\nx\n",
    )
    ok = _run_cli(root, KEY)
    assert ok.returncode == 0, ok.stdout

    card.write_text(original.replace("AAAA", "BBBB"), encoding="utf-8", newline="")
    red = _run_cli(root, KEY)
    assert red.returncode == 1, red.stdout
    assert "tampered_cards [always FAIL] (1)" in red.stdout

    card.write_text(original, encoding="utf-8", newline="")
    again = _run_cli(root, KEY)
    assert again.returncode == 0, again.stdout
    _verify("VC-t27-tamper-cli", tampered_exit=red.returncode, restored_exit=again.returncode)


def test_digest_is_eol_normalized(tmp_path):
    root, key_dir = _make_key(tmp_path)
    lf = _write_card(key_dir, "T-01-alpha.md", "# T-01\nline\n")
    lf_digest = card_audit.card_digest(lf)
    crlf = key_dir / "tasks" / "T-06-crlf.md"
    crlf.write_bytes(b"# T-01\r\nline\r\n")
    assert card_audit.card_digest(crlf) == lf_digest
    _verify("VC-t27-eol", digest=lf_digest[:12])


# ── CLI subprocess / error path ─────────────────────────────────────────────

def test_cli_subprocess_exit_codes(tmp_path):
    root, key_dir = _make_key(tmp_path)
    _write_card(key_dir, "T-01-alpha.md", "# alpha\n")
    _write_dispatch(key_dir, "w-one", "type: coding\ncard_path: tasks/T-01-alpha.md\n\nx\n")

    ok = _run_cli(root, KEY)
    assert ok.returncode == 0, ok.stderr
    assert "-> OK" in ok.stdout

    _write_dispatch(key_dir, "w-legacy", "type: coding\n\nlegacy\n")
    # Pin the fixture's claimed creation time (pre-boundary historical row).
    _set_mtime(key_dir / "workers" / "w-legacy" / "task.md", "2026-08-01T00:00:00+00:00")
    assert _run_cli(root, KEY).returncode == 0
    assert _run_cli(root, KEY, "--strict").returncode == 1

    missing = _run_cli(root, "no-such-key")
    assert missing.returncode == 2
    assert "key dir not found" in missing.stderr
    _verify("VC-t27-cli", ok=0, strict=1, no_key=2)


def test_parse_card_path_reads_only_header_region(tmp_path):
    root, key_dir = _make_key(tmp_path)
    header = _write_dispatch(
        key_dir,
        "w-header",
        "type: coding\ncard_path: tasks/a.md\ncard_sha256: abc123\n\ncard_path: body.md\ncard_sha256: body\n",
    )
    body = _write_dispatch(key_dir, "w-body", "type: coding\n\ncard_path: not-a-header\ncard_sha256: body\n")
    front = _write_dispatch(
        key_dir, "w-front", "---\ncard_path: tasks/f.md\ncard_sha256: fff\n---\nbody\n"
    )
    assert card_audit.parse_card_path(header) == "tasks/a.md"
    assert card_audit.parse_card_sha256(header) == "abc123"
    assert card_audit.parse_card_path(body) == ""
    assert card_audit.parse_card_sha256(body) == ""
    assert card_audit.parse_card_path(front) == "tasks/f.md"
    assert card_audit.parse_card_sha256(front) == "fff"
    _verify("VC-t27-header-region", header="tasks/a.md", body="", sha256="abc123")
