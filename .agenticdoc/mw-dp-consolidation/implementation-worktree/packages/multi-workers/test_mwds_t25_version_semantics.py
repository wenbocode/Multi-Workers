"""test_mwds_t25_version_semantics.py — T-25 at the service layer (C-31).

``mw-dispatch-card-gate`` wave 16, C-31: the bundled TS producer rendered
``envelope_producer: agent-team-loop-pm@0.0.0`` because a bundle cannot resolve
``packages/coding-agent/package.json`` at runtime. ``0.0.0`` used to be a
recognized dotted-numeric release, so a perfectly current TS dispatch was
*provably older than the baseline* and the service would label it
``failed(producer-skew ...)`` — a false skew on the normal path.

What this file pins:

1. ``0.0.0`` (and the empty version) is an *unknown* version: never
   ``producer-skew``; the T-09/T-14 fail-closed ``envelope missing`` refusal is
   kept, annotated ``producer-version-unknown`` in the reason, and the T-14
   escape hatch cannot downgrade it;
2. a real release still compares by semver (the T-14 three branches regress);
3. the build injects the real version into the extension bundle
   (``mw._build_bundle(out=<tmp>)`` — the tracked dist artifact is never
   touched, no ``build --install``).

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_mwds_t25_version_semantics.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher  # noqa: E402
import mw  # noqa: E402
from launcher import (  # noqa: E402
    ENVELOPE_PRODUCER_BASELINE,
    ENVELOPE_PRODUCER_BASELINE_SEMVER,
    _load_providers,
    _parse_workers_file,
    _poll_once,
    _serialize_entry,
    classify_envelope_refusal,
    producer_version_before_baseline,
    producer_version_is_unknown,
)

_HERMETIC_CONFIG = {
    "credentials": {"timi": {"sources": [{"env": "TIMI_API_KEY"}]}},
    "providers": {"timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"}},
}

# The C-31 producer shape: identity line present, version is the all-zero
# placeholder, canonical envelope absent (a real missing section).
_C31_CODING = (
    "type: coding\n"
    "envelope_producer: agent-team-loop-pm@0.0.0\n"
    "Do something useful.\n"
)

# Control: an actually-old producer (T-14 branch b must be untouched).
_OLD_CODING = (
    "type: coding\n"
    "envelope_producer: autopilot-conductor@0.60.0\n"
    "Do something useful.\n"
)

# Control: a current producer version, envelope still missing (branch missing).
_CURRENT_CODING = (
    "type: coding\n"
    f"envelope_producer: agent-team-loop-pm@{ENVELOPE_PRODUCER_BASELINE_SEMVER}\n"
    "Do something useful.\n"
)


@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return _load_providers(path)


class _FakeProc:
    returncode = None

    def poll(self) -> None:
        return None


def _write_card(tmp_path: pathlib.Path, text: str, key: str = "t025") -> pathlib.Path:
    directory = tmp_path / ".agenticdoc" / "test-key" / "workers" / key
    directory.mkdir(parents=True, exist_ok=True)
    card = directory / "task.md"
    card.write_text(text, encoding="utf-8")
    return card


def _entry(task_path: pathlib.Path, **overrides: str) -> dict[str, str]:
    entry = {
        "cli": "pi", "provider": "timi", "task_path": str(task_path),
        "task_key": task_path.parent.name, "status": "pending",
        "dispatched_at": "2026-10-12T00:00:00+00:00",
        "updated_at": "2026-10-12T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


def _enable_fallback(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".agenticdoc" / "_autopilot" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"envelope_fallback": True}), encoding="utf-8")


def _poll(
    tmp_path: pathlib.Path,
    providers: dict,
    monkeypatch: pytest.MonkeyPatch,
    entries: list[dict[str, str]],
) -> dict:
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "absent-machine-config.json"))
    monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
    queue_file = tmp_path / ".agenticdoc" / "_workers.parallel"
    queue_file.write_text(
        "".join(_serialize_entry(entry) + "\n" for entry in entries), encoding="utf-8"
    )
    running: dict = {}
    _poll_once(tmp_path, providers, running, {}, [], None)
    return running


def _statuses(tmp_path: pathlib.Path) -> dict[str, str]:
    queue_file = tmp_path / ".agenticdoc" / "_workers.parallel"
    return {row["task_key"]: row["status"] for row in _parse_workers_file(queue_file)}


def _worker_log(card: pathlib.Path) -> str:
    path = card.parent / "worker.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── 1. `0.0.0` is an unknown version, never skew ─────────────────────────────

class TestUnknownVersionSemantics:
    def test_all_zero_and_empty_versions_are_unknown(self) -> None:
        assert producer_version_is_unknown("0.0.0") is True
        assert producer_version_is_unknown("0.0") is True
        assert producer_version_is_unknown("0") is True
        assert producer_version_is_unknown("") is True
        assert producer_version_is_unknown("0.0.1") is False
        assert producer_version_is_unknown("0.83.0") is False
        assert producer_version_is_unknown("unknown") is False

    def test_zero_version_is_not_provably_older_than_the_baseline(self) -> None:
        assert producer_version_before_baseline("0.0.0") is False
        assert producer_version_before_baseline("0") is False

    def test_c31_card_is_missing_not_skew_and_stays_explanable(self, tmp_path: pathlib.Path) -> None:
        card = _write_card(tmp_path, _C31_CODING)
        verdict = classify_envelope_refusal(_entry(card))
        assert verdict is not None, "a genuinely missing envelope must still be refused"
        assert verdict["kind"] == "missing", verdict
        assert verdict["kind"] != "skew"
        assert "producer-skew" not in verdict["reason"]
        assert verdict["reason"].startswith("envelope missing: ")
        assert launcher._PRODUCER_VERSION_UNKNOWN_MARKER in verdict["reason"]
        assert f"producer=agent-team-loop-pm@0.0.0" in verdict["reason"]
        assert f"baseline={ENVELOPE_PRODUCER_BASELINE}" in verdict["reason"]
        print(f"[T-25 evidence] C-31 verdict kind={verdict['kind']} reason={verdict['reason']}")

    def test_zero_version_row_fails_and_audits_the_unknown_version(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        card = _write_card(tmp_path, _C31_CODING)
        running = _poll(tmp_path, providers, monkeypatch, [_entry(card)])
        log = _worker_log(card)
        print(f"[T-25 evidence] C-31 row worker.log:\n{log}")
        assert running == {}, "an incomplete envelope must not spawn"
        assert _statuses(tmp_path)["t025"] == "failed"
        assert "failed(producer-skew" not in log, "0.0.0 must never be labelled skew"
        assert "envelope missing:" in log
        assert launcher._PRODUCER_VERSION_UNKNOWN_MARKER in log

    def test_escape_hatch_cannot_downgrade_an_unknown_version(
        self,
        tmp_path: pathlib.Path,
        providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Requirement 2 (fail-closed unchanged): the hatch only covers skew and
        # legacy; a `missing` verdict (which is what 0.0.0 now is) is untouched.
        _enable_fallback(tmp_path)
        card = _write_card(tmp_path, _C31_CODING)
        running = _poll(tmp_path, providers, monkeypatch, [_entry(card)])
        log = _worker_log(card)
        print(f"[T-25 evidence] C-31 + fallback row log:\n{log}")
        assert running == {}, "the hatch must not inject a skeleton for a `missing` verdict"
        assert _statuses(tmp_path)["t025"] == "failed"
        assert "[ENVELOPE_FALLBACK]" not in log
        assert "<!-- mw-envelope-fallback -->" not in card.read_text(encoding="utf-8")

    def test_a_real_old_release_is_still_skew(self, tmp_path: pathlib.Path) -> None:
        card = _write_card(tmp_path, _OLD_CODING)
        verdict = classify_envelope_refusal(_entry(card))
        assert verdict is not None and verdict["kind"] == "skew"
        assert "failed(producer-skew autopilot-conductor@0.60.0" in verdict["reason"]
        print(f"[T-25 evidence] old release verdict kind={verdict['kind']} reason={verdict['reason']}")

    def test_a_current_release_keeps_the_plain_missing_refusal(self, tmp_path: pathlib.Path) -> None:
        card = _write_card(tmp_path, _CURRENT_CODING)
        verdict = classify_envelope_refusal(_entry(card))
        assert verdict is not None and verdict["kind"] == "missing"
        assert launcher._PRODUCER_VERSION_UNKNOWN_MARKER not in verdict["reason"]
        print(f"[T-25 evidence] current release verdict kind={verdict['kind']}")

    def test_semver_comparison_regresses_the_t14_matrix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(launcher, "ENVELOPE_PRODUCER_BASELINE_SEMVER", "0.83.0")
        assert producer_version_before_baseline("0.60.0") is True
        assert producer_version_before_baseline("0.82.9") is True
        assert producer_version_before_baseline("0.83.0") is False
        assert producer_version_before_baseline("0.84.0") is False
        assert producer_version_before_baseline("1.0.0") is False
        print("[T-25 evidence] semver matrix 0.60.0/0.82.9=old 0.83.0/0.84.0/1.0.0=not-old")


# ── 2. the build injects the real version ────────────────────────────────────

class TestBuildVersionInjection:
    def test_framework_version_comes_from_the_existing_source(self) -> None:
        package = (
            pathlib.Path(mw.__file__).resolve().parent.parent
            / "coding-agent" / "package.json"
        )
        assert package.is_file()
        expected = json.loads(package.read_text(encoding="utf-8"))["version"]
        assert mw._framework_version() == expected
        print(f"[T-25 evidence] framework version source = {expected}")

    def test_built_bundle_carries_the_version_literal(self, tmp_path: pathlib.Path) -> None:
        import shutil

        if shutil.which("node") is None:
            pytest.skip("node unavailable — cannot build the extension bundle here")
        version = mw._framework_version()
        assert version, "the version source must be readable to prove the injection"
        out = tmp_path / "agent-team-loop.js"
        ok, message = mw._build_bundle(out=out)
        print(f"[T-25 evidence] build(out=<tmp>) ok={ok} message={message}")
        assert ok, message
        text = out.read_text(encoding="utf-8")
        version_hits = text.count(version)
        zero_hits = text.count("0.0.0")
        print(
            f"[T-25 evidence] bundle version({version})_hits={version_hits} "
            f"0.0.0_hits={zero_hits}"
        )
        assert version_hits >= 1, "the emitted bundle must carry the injected version"
        # The injected literal is the first link of the VERSION chain; the only
        # remaining "0.0.0" is the last-resort fallback, after the injection.
        assert text.index(f'"{version}"') < text.index('"0.0.0"')

    def test_real_repo_bundle_before_after_counts(self) -> None:
        """Report-only: the pre-cutover repo bundle is the C-31 baseline."""
        repo_bundle = pathlib.Path(mw.__file__).resolve().parent / "dist" / "extensions" / "agent-team-loop.js"
        if not repo_bundle.is_file():
            pytest.skip("repo bundle absent")
        text = repo_bundle.read_text(encoding="utf-8", errors="replace")
        version = mw._framework_version()
        print(
            f"[T-25 evidence] repo bundle (pre-cutover artifact) "
            f"version({version})_hits={text.count(version)} 0.0.0_hits={text.count('0.0.0')}"
        )
