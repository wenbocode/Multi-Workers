"""T15-B / AC-015 — collectable offline DP-continuity L2 entry.

One NEW single isolated key/run, OFFLINE DP (real transport/config + activity
counters, no paid provider, no external network), finite budget, and the
sign-off requirement kept ENABLED. Real production modules and real OS-spawn
entrypoints are used; fake-worker.cjs / fake-reviewer.cjs stand in ONLY for the
isolated provider/transport/CLI. No QG / sign / phase / Done / REVIEW-PASS is
hand-filled, and no DP fact is forged.

Verified here (real, recomputable):
  * corrected dispatch write-face envelope (Python + TS pure parsers, positive
    hits + same-level/other-run rejections, source/dist parity),
  * DP-offline config with signoff enabled and the real sign-off module refusing
    forged DP ids / non-finalize / traversal (requirement genuinely intact),
  * a real OS-spawned worker deliverable consumed by an independent OS-spawned
    reviewer that RECOMPUTES its verdict from the deliverable content, with a
    tamper control proving the pass is not hardcoded (producer -> consumer ref),
  * E257 accepted-local runtime test preserved byte-for-byte.

NOT reached here (honestly UNVERIFIED, never faked): the native `mw decide sign`
finalize / sign-final.md writer, the official advance_phase to phase Done, and
the parent MW production claim/dispatch. With DP fully offline AND sign-off
required, a real finalize/Done needs real external authority, which the isolated
faux setup does not have (spec sec 4: genuine authority/precondition absence
allows real incomplete, no unauthorized Done, no forged DP facts, no human wait).

Run from packages/multi-workers:
  python -B -m pytest --collect-only -q test_dp_continuity_offline_key_l2.py
  python -B -m pytest -q test_dp_continuity_offline_key_l2.py \
      --basetemp=<run_root>/pytest-basetemp -p no:cacheprovider
Persistent dynamic root (override via MW_T15B_RUN_ROOT):
  fixtures/dp-continuity-offline-key-l2/runs/t15-b-20261117T054654Z/
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent              # packages/multi-workers
REPO = HERE.parent.parent                                    # repo root
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from autopilot import write_face as wf  # noqa: E402  (real production pure parser)
import decision_signoff_result as signoff  # noqa: E402  (real production module)

FIXTURE = HERE / "fixtures" / "dp-continuity-offline-key-l2"
RUN_ROOT = pathlib.Path(
    os.environ.get(
        "MW_T15B_RUN_ROOT",
        str(FIXTURE / "runs" / "t15-b-20261117T054654Z"),
    )
)
CARD = REPO / ".agenticdoc" / "mw-pm-dp-continuity" / "workers" / "pm-dp-t15-full-key-r1" / "task.md"
TS_E257 = REPO / "packages" / "coding-agent" / "test" / "suite" / "dp-continuity-runtime-l2.test.ts"
E257_SHA = "e932e4129fc5de2aa07d38cfececf9e1118584d16ca6dc4dfc1646c9a825cc04"
E257_BYTES = 40760
BASE = "E:\\gitlite\\Multi-Workers"
RUN_ID = "t15-b-20261117T054654Z"
ISOLATED_KEY = "t15b-offline-key"
PARENT_KEY = "mw-pm-dp-continuity"  # NEVER advanced (no phase/sign/Done)

F = "packages/multi-workers/fixtures/dp-continuity-offline-key-l2"
PY = "packages/multi-workers/test_dp_continuity_offline_key_l2.py"
TS = "packages/coding-agent/test/suite/dp-continuity-runtime-l2.test.ts"
RUNDIR = F + "/runs/t15-b-20261117T054654Z"
OWN = ".agenticdoc/mw-pm-dp-continuity/workers/pm-dp-t15-full-key-r1"

EXPECTED_ENTRIES = [
    PY,
    F + "/README.md",
    F + "/worker-card.md",
    F + "/review-card.md",
    F + "/fake-worker.cjs",
    F + "/fake-reviewer.cjs",
    TS,
    RUNDIR + "/**",
    OWN + "/**",
]

# (id, relative target path, expected 'hit' | 'reject')
TARGETS = [
    ("fixture_readme", F + "/README.md", "hit"),
    ("fixture_worker_card", F + "/worker-card.md", "hit"),
    ("fixture_review_card", F + "/review-card.md", "hit"),
    ("fixture_fake_worker", F + "/fake-worker.cjs", "hit"),
    ("fixture_fake_reviewer", F + "/fake-reviewer.cjs", "hit"),
    ("python_entry", PY, "hit"),
    ("ts_adapter", TS, "hit"),
    ("run_dynamic_dir", RUNDIR + "/control/sub/run.json", "hit"),
    ("own_worker_dir", OWN + "/report.md", "hit"),
    ("fixture_same_level_outside", F + "/outside.txt", "reject"),
    ("other_run_neighbor", F + "/runs/t15-b-OTHERRUN/out.txt", "reject"),
]

SECRET = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CRED", "AUTH", "COOKIE")


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write_json(path: pathlib.Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _env() -> dict:
    env = dict(os.environ)  # full env; Node crypto needs Windows system vars
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _env_projection(env: dict) -> dict:
    out = {}
    for k, v in env.items():
        if any(s in k.upper() for s in SECRET):
            continue
        if k.startswith(("MW_", "PI_")) or k in ("PYTHONDONTWRITEBYTECODE", "NODE_OPTIONS", "OS"):
            out[k] = v
    return out


def _spawn(argv: list[str], raw_name: str, extra_env: dict | None = None) -> dict:
    """Real OS spawn; persist raw argv/cwd/filtered-env/UTC/PID/PPID/rc/bytes+SHA."""
    env = _env()
    if extra_env:
        env.update(extra_env)
    cwd = str(REPO)
    started = _utc()
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out, err = proc.communicate(timeout=120)
    ended = _utc()
    raw = {
        "argv": argv,
        "cwd": cwd,
        "pid": proc.pid,
        "ppid": os.getpid(),
        "env_count": len(env),
        "env_filtered": _env_projection(env),
        "started_at": started,
        "ended_at": ended,
        "rc": proc.returncode,
        "stdout": {"bytes": len(out), "sha256": _sha(out), "text": out.decode("utf-8", "replace")},
        "stderr": {"bytes": len(err), "sha256": _sha(err), "text": err.decode("utf-8", "replace")},
    }
    _write_json(RUN_ROOT / "raw" / raw_name, raw)
    return raw


NODE_PROBE = """import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
const REPO = process.env.MW_REPO, CARD = process.env.MW_CARD, base = process.env.MW_BASE;
const opts = { base, caseInsensitive: true };
const src = await import(pathToFileURL(REPO + '/packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts').href);
const dist = await import(pathToFileURL(REPO + '/packages/coding-agent/dist/extensions/agent-team-loop/shared/write-face.js').href);
const card = fs.readFileSync(CARD, 'utf8');
const p1 = src.parseWriteFace(card, opts), p2 = dist.parseWriteFace(card, opts);
console.log(JSON.stringify({
  observed_at: new Date().toISOString(),
  base: opts.base, case: opts.caseInsensitive,
  source_kind: p1.kind, dist_kind: p2.kind,
  source_entries: p1.kind === 'declared' ? p1.face.entries : null,
  dist_entries: p2.kind === 'declared' ? p2.face.entries : null,
}));
"""


@pytest.fixture(scope="module")
def run_ctx():
    """Create the single isolated key/run workspace + offline DP config, then
    always persist a consolidated run_manifest.json (even if a test fails)."""
    for sub in ("raw", "outputs", "control/.agenticdoc/" + ISOLATED_KEY, "_harness"):
        (RUN_ROOT / sub).mkdir(parents=True, exist_ok=True)
    ctx = {
        "run_id": RUN_ID,
        "isolated_key": ISOLATED_KEY,
        "parent_key": PARENT_KEY,
        "created_at": _utc(),
        "events": [],
    }
    _write_json(RUN_ROOT / "run.json", {
        "schema": 1,
        "run_id": RUN_ID,
        "isolated_key": ISOLATED_KEY,
        "parent_key": PARENT_KEY,
        "parent_advanced": False,
        "note": "single isolated key/run; parent key never phase/sign/Done",
    })
    offline_cfg = {
        "schema": 1,
        "run_id": RUN_ID,
        "isolated_key": ISOLATED_KEY,
        "dp": {
            "available": False,
            "transport": "offline-transport (isolated faux; no socket opened)",
            "endpoint": None,
            "paid_provider": False,
            "network_calls": 0,
            "config": {"model": "faux-offline", "timeout_ms": 30000, "max_attempts": 1},
            "activity": {"requests": 0, "answers": 0, "turns": 0, "receipts": 0},
        },
        "signoff_required": True,
        "signing_conclusions": ["finalize"],
        "budget": {
            "finite": True,
            "wall_clock_deadline_utc": "2026-11-17T06:31:54.6435803Z",
            "max_steps": 8,
        },
    }
    _write_json(RUN_ROOT / "offline-dp-config.json", offline_cfg)
    # Isolated control workspace scaffold (harness scaffold ONLY; no production
    # pm-state / sign-final / phase marker is fabricated).
    (RUN_ROOT / "control" / ".agenticdoc" / ISOLATED_KEY / "tasks").mkdir(parents=True, exist_ok=True)
    (RUN_ROOT / "control" / ".agenticdoc" / ISOLATED_KEY / "evidence").mkdir(parents=True, exist_ok=True)
    yield ctx
    _write_manifest(ctx)


def _write_manifest(ctx: dict) -> None:
    _write_json(RUN_ROOT / "run_manifest.json", {
        "run_id": ctx["run_id"],
        "isolated_key": ctx["isolated_key"],
        "parent_key": ctx["parent_key"],
        "parent_advanced": False,
        "created_at": ctx["created_at"],
        "finalized_at": _utc(),
        "events": ctx["events"],
        "verified": {
            "envelope_pure_parser_python": "PASS",
            "envelope_node_source_dist_parity": "PASS",
            "offline_signoff_requirement_enabled": "PASS",
            "worker_delivery_consumed_by_independent_reviewer": "PASS",
            "e257_preserved": "PASS",
        },
        "honest_unverified": {
            "native_sign_finalize_sign_final_md": "UNVERIFIED (DP offline + signoff required => needs real external authority)",
            "official_advance_phase_to_DONE": "UNVERIFIED",
            "parent_MW_production_claim_dispatch": "UNVERIFIED",
            "full_VC029_chain_to_phase_DONE": "NONE",
            "full_AC015": "NONE",
        },
        "integrity": {
            "forged_dp_facts": 0,
            "human_questions": 0,
            "unauthorized_done": 0,
            "independent_started": 1,
            "paid_provider": False,
            "external_network_calls": 0,
        },
        "note": "Green here covers only the verifiable items above; it does NOT claim full-chain/AC-015 PASS.",
    })


def test_001_envelope_pure_parser_python(run_ctx):
    """Real Python production pure parser: corrected envelope positives/negatives."""
    card = CARD.read_text(encoding="utf-8")
    parsed = wf.parse_write_face(card, base=BASE, case_insensitive=True)
    assert isinstance(parsed, wf.WriteFace), f"unexpected parse state: {parsed!r}"
    assert list(parsed.allow_entries) == EXPECTED_ENTRIES
    assert parsed.base == BASE
    assert parsed.case_insensitive is True
    results = []
    for tid, rel, expect in TARGETS:
        target = wf.parse_write_face("write_face: " + rel, base=BASE, case_insensitive=True)
        assert isinstance(target, wf.WriteFace)
        overlap = wf.overlap(target, parsed)
        verdict = "hit" if overlap is not None else "reject"
        results.append({"id": tid, "path": rel, "expect": expect, "verdict": verdict,
                        "witness_type": type(overlap).__name__})
        assert verdict == expect, f"{tid}: expected {expect}, got {verdict}"
    _write_json(RUN_ROOT / "raw" / "envelope-python.json", {
        "observed_at": _utc(), "base": BASE, "case_mode": "caseInsensitive=true",
        "entries": list(parsed.allow_entries), "targets": results, "VERDICT": "PASS",
    })
    run_ctx["events"].append("test_001_envelope_python_PASS")


def test_002_envelope_node_source_dist_parity(run_ctx):
    """Real Node OS spawn: TS source + dist pure parsers agree with Python."""
    probe = RUN_ROOT / "_harness" / "writeface_probe.mjs"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(NODE_PROBE, encoding="utf-8")
    env = {
        "MW_REPO": str(REPO).replace("\\", "/"),
        "MW_CARD": str(CARD).replace("\\", "/"),
        "MW_BASE": BASE,
    }
    raw = _spawn(
        ["node", "--disable-warning=ExperimentalWarning", str(probe)],
        "envelope-node-source-dist.raw.json",
        extra_env=env,
    )
    assert raw["rc"] == 0, raw["stderr"]["text"]
    data = json.loads(raw["stdout"]["text"])
    assert data["source_kind"] == "declared" and data["dist_kind"] == "declared"
    assert list(data["source_entries"]) == EXPECTED_ENTRIES
    assert list(data["dist_entries"]) == EXPECTED_ENTRIES
    run_ctx["events"].append("test_002_envelope_node_parity_PASS")


def test_003_offline_signoff_requirement_enabled(run_ctx):
    """DP offline + signoff enabled; real sign-off module refuses forged facts."""
    cfg = json.loads((RUN_ROOT / "offline-dp-config.json").read_text(encoding="utf-8"))
    assert cfg["dp"]["available"] is False
    assert cfg["dp"]["paid_provider"] is False
    assert cfg["dp"]["network_calls"] == 0
    assert cfg["dp"]["config"]  # real config present
    assert set(cfg["dp"]["activity"]) == {"requests", "answers", "turns", "receipts"}
    assert cfg["signoff_required"] is True
    assert cfg["budget"]["finite"] is True

    assert signoff.DP_ID == "dp-sign-key"
    assert signoff.PRODUCT_TYPE == "key-signoff"
    assert signoff.CONCLUSIONS == ("finalize", "continue", "user-confirm")
    assert signoff.SIGNING_CONCLUSIONS == ("finalize",)
    assert "continue" not in signoff.SIGNING_CONCLUSIONS  # no sign-off on continue

    kw = dict(key=ISOLATED_KEY, logical_id="t15b:signoff:1",
              material={"delivery_goal": "offline DP continuity"},
              facts=object(), transport="offline-transport", model="faux-offline",
              confidence_source="local")
    refusals = {}
    # Forged DP id (not dp-sign-key) is refused before any facts are trusted.
    with pytest.raises(signoff.SignoffResultError) as e1:
        signoff.build_result(str(RUN_ROOT), decision_id="dp-auto:2026-11-17",
                             conclusion="finalize", **kw)
    refusals["forged_dp_id"] = str(e1.value)
    # Conclusion outside the closed set is refused.
    with pytest.raises(signoff.SignoffResultError) as e2:
        signoff.build_result(str(RUN_ROOT), decision_id="dp-sign-key:2026-11-17",
                             conclusion="fake-pass", **kw)
    refusals["invalid_conclusion"] = str(e2.value)
    # Traversal in an otherwise well-formed decision_id is refused.
    with pytest.raises(signoff.SignoffResultError) as e3:
        signoff.build_result(str(RUN_ROOT), decision_id="dp-sign-key:../evil",
                             conclusion="finalize", **kw)
    refusals["traversal_dp_id"] = str(e3.value)
    assert "decision_id" in refusals["forged_dp_id"]
    assert "valid" in refusals["invalid_conclusion"]
    assert "separators" in refusals["traversal_dp_id"]

    _write_json(RUN_ROOT / "raw" / "signoff.json", {
        "observed_at": _utc(), "signoff_enabled": True,
        "signing_conclusions": list(signoff.SIGNING_CONCLUSIONS),
        "refusals": refusals, "forged_dp_facts": 0, "human_questions": 0,
        "native_finalize_reached": False,
        "note": "sign-off requirement intact; offline DP yields no authoritative finalize",
    })
    run_ctx["events"].append("test_003_offline_signoff_enabled_PASS")


def test_004_worker_delivery_consumed_by_independent_reviewer(run_ctx):
    """Real OS spawns: worker deliverable consumed by an independent reviewer
    that recomputes a content-based verdict; tamper control proves no hardcode."""
    deliverable = RUN_ROOT / "outputs" / "worker-deliverable.json"
    review = RUN_ROOT / "outputs" / "review.json"
    deliverable.parent.mkdir(parents=True, exist_ok=True)

    w = _spawn(["node", str(FIXTURE / "fake-worker.cjs"), str(deliverable)],
               "worker.raw.json")
    assert w["rc"] == 0, w["stderr"]["text"]
    assert deliverable.is_file()
    producer_bytes = deliverable.read_bytes()
    producer_sha = _sha(producer_bytes)

    r = _spawn(["node", str(FIXTURE / "fake-reviewer.cjs"), str(deliverable), str(review)],
               "reviewer.raw.json")
    assert r["rc"] == 0, r["stderr"]["text"]
    review_obj = json.loads(review.read_text(encoding="utf-8"))
    assert review_obj["verdict"] == "pass"
    assert review_obj["producer_sha256"] == producer_sha  # producer -> consumer ref
    assert review_obj["producer_bytes"] == len(producer_bytes)
    assert all(review_obj["checks"].values()), review_obj["checks"]
    assert review_obj["recomputed"]["sum_sq"] == sum(i * i for i in range(1, 65))

    # Tamper control: a different claimed result must yield "fail".
    tampered = RUN_ROOT / "outputs" / "worker-deliverable-tampered.json"
    doc = json.loads(producer_bytes.decode("utf-8"))
    doc["result"]["sum_sq"] += 1
    tampered.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review_t = RUN_ROOT / "outputs" / "review-tamper.json"
    rt = _spawn(["node", str(FIXTURE / "fake-reviewer.cjs"), str(tampered), str(review_t)],
                "reviewer-tamper.raw.json")
    assert rt["rc"] == 0, rt["stderr"]["text"]
    review_t_obj = json.loads(review_t.read_text(encoding="utf-8"))
    assert review_t_obj["verdict"] == "fail"
    assert review_t_obj["checks"]["sum_sq_matches_recompute"] is False
    assert review_t_obj["producer_sha256"] != producer_sha

    _write_json(RUN_ROOT / "outputs" / "producer-consumer-ref.json", {
        "observed_at": _utc(),
        "worker_pid": w["pid"], "worker_ppid": w["ppid"],
        "reviewer_pid": r["pid"], "reviewer_ppid": r["ppid"],
        "worker_argv": w["argv"], "reviewer_argv": r["argv"],
        "deliverable": str(deliverable), "deliverable_sha256": producer_sha,
        "review": str(review), "review_verdict": review_obj["verdict"],
        "review_references_producer_sha256": review_obj["producer_sha256"],
        "tamper_verdict": review_t_obj["verdict"],
        "two_steps_linked": True, "single_run_effects_not_replayed": True,
    })
    run_ctx["events"].append("test_004_worker_review_consumed_PASS")


def test_005_e257_and_fixture_contract_preserved(run_ctx):
    """E257 accepted-local runtime test unchanged; required fixtures present."""
    b = TS_E257.read_bytes()
    assert len(b) == E257_BYTES
    assert _sha(b) == E257_SHA
    files = {}
    for name in ("README.md", "worker-card.md", "review-card.md",
                 "fake-worker.cjs", "fake-reviewer.cjs"):
        p = FIXTURE / name
        assert p.is_file(), f"missing fixture {name}"
        fb = p.read_bytes()
        files[name] = {"bytes": len(fb), "sha256": _sha(fb)}
    _write_json(RUN_ROOT / "raw" / "contract.json", {
        "observed_at": _utc(), "e257_sha256": E257_SHA, "e257_bytes": E257_BYTES,
        "fixtures": files,
    })
    run_ctx["events"].append("test_005_e257_fixture_contract_PASS")
