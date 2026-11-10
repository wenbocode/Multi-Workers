"""Bounded recovery in the operator service. The conductor cannot authorize this path.

The module reads the original managed brake and the append-only auto-decision
ledger, re-checks the policy/authority source against the operator grant, and
writes only the recovery state of the current trip. It never creates a grant,
changes the policy, resets a budget or writes a gate answer. Gate answers are
produced by the formal gate writer (``gate-writer.ts``); this handler only
consumes the three bound axes it wrote.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import uuid

import decision
import decision_lifecycle as lifecycle
import decision_points
import decision_policy as policy
import decision_validity as validity
import decision_wire as wire
import mw_common
import operator_authority
from . import config, conductor, dispatch as dispatch_writer, gate_effects, gates, roadmap, state

DP = "dp-gate-approve"
ACTION = "observe-brake"
EVENT = "mw-breaker-event: "
TRIP = re.compile(r"[0-9a-f]{32}")
GATE = re.compile(r"gate-[0-9]{4,}")
_LEGACY_START = "---"

#: The one formal prepared-answer writer. The approved source is preferred;
#: the packaged build is only a fallback for an install without dev tooling.
_REPO = pathlib.Path(__file__).resolve().parents[3]
_WRITER_SOURCE = _REPO / "packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts"
_WRITER_DIST = _REPO / "packages/coding-agent/dist/extensions/agent-team-loop/autopilot/gate-writer.js"
_TSX = _REPO / "node_modules/tsx/dist/cli.mjs"
_GATE_EFFECTS = frozenset({"not-started", "in-progress", "applied", "blocked", "failed", "unknown"})


class RecoveryBlocked(ValueError):
    """Safe reason for refusing a limited recovery."""


def _require(value, reason):
    if not value:
        raise RecoveryBlocked(reason)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _stamp(text):
    _require(isinstance(text, str) and text.strip(), "invalid-timestamp")
    stamp = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    _require(stamp.utcoffset() is not None, "invalid-timestamp")
    return stamp


def _safe_file(root, path):
    path = pathlib.Path(path)
    _require(root.resolve(strict=True) == root and path.is_relative_to(root)
             and path.resolve(strict=False) == path, "unexpected-project-path")
    return path


def _brake(root):
    return _safe_file(root, conductor.auto_brake_path(root))


def _ledger(root):
    return _safe_file(root, conductor.auto_decisions_path(root))


def _installed_file(path):
    """A protected install file: a regular file that never redirects outside the tree."""
    try:
        resolved = pathlib.Path(path).resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file() or not resolved.is_relative_to(_REPO):
        return None
    return resolved


def _writer_runtime():
    source = _installed_file(_WRITER_SOURCE)
    if source is not None:
        tsx = _installed_file(_TSX)
        _require(tsx is not None, "gate-writer-runtime-unavailable")
        return source, tsx
    built = _installed_file(_WRITER_DIST)
    _require(built is not None, "gate-writer-runtime-unavailable")
    return built, None


def _run_gate_writer(args):
    """Load the approved writer in a real node subprocess; never answer in Python."""
    module, tsx = _writer_runtime()
    node = shutil.which("node")
    _require(node is not None, "gate-writer-runtime-unavailable")
    runner = (
        f"import {{ answerPreparedGate }} from {json.dumps(module.as_uri())};\n"
        "import { readFileSync } from 'node:fs';\n"
        "const args = JSON.parse(readFileSync(0, 'utf8'));\n"
        "console.log(JSON.stringify(await answerPreparedGate(args)));\n"
    )
    with tempfile.TemporaryDirectory(prefix="mw-gate-writer-") as directory:
        script = pathlib.Path(directory) / "runner.mjs"
        script.write_text(runner, encoding="utf-8", newline="\n")
        command = [node, str(tsx), str(script)] if tsx is not None else [node, str(script)]
        try:
            proc = subprocess.run(
                command, input=json.dumps(args), cwd=str(_REPO), text=True,
                encoding="utf-8", capture_output=True, timeout=120, check=False,
                env={**os.environ, "NO_COLOR": "1"},
            )
        except (OSError, subprocess.SubprocessError):
            raise RecoveryBlocked("gate-writer-failed") from None
    _require(proc.returncode == 0, "gate-writer-failed")
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise RecoveryBlocked("gate-writer-failed") from None
    _require(isinstance(result, dict), "gate-writer-failed")
    return result


def _answer_gate(root, gate, req, result, grant, ref):
    """Deposit the real answer through ``answerPreparedGate`` and verify the file."""
    choice = result["choice"]
    basis = result["basis_text"]
    written = _run_gate_writer({
        "gateFile": str(gate.path),
        "lockFile": str(root / ".mw" / "gates.lock"),
        "answeredBy": grant["claim"],
        "decision": choice,
        "modelBasis": basis,
        "decisionRef": ref,
        "matterRef": gate.matter_ref,
        "substantiveVersion": gate.substantive_version,
    })
    _require(written.get("ok") is True, "gate-writer-refused")
    answered = gates.parse(gate.path)
    _require(answered.transport == "answered" and answered.business == choice
             and answered.decision_ref == ref and answered.model_basis == basis
             and answered.matter_ref == gate.matter_ref
             and answered.substantive_version == gate.substantive_version
             and answered.answered_by == grant["claim"], "gate-answer-unverified")
    return answered


def _legacy_trip(raw):
    """The real conductor brake is a YAML frontmatter file without a trip id.

    Derive a stable generation id from the frontmatter bytes only, so events
    appended later do not change the identity of the trip they observe.
    """
    if not raw.startswith(b"---\n") and not raw.startswith(b"---\r\n"):
        return None
    lines = raw.decode("utf-8").splitlines(keepends=True)
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == _LEGACY_START), None)
    if close is None:
        return None
    header = "".join(lines[:close + 1]).encode("utf-8")
    fields = {}
    for line in lines[1:close]:
        name, sep, value = line.partition(":")
        if sep and name in {"reason", "triggered_at"}:
            fields[name] = value.strip()
    reason = fields.get("reason")
    triggered = fields.get("triggered_at")
    _require(isinstance(reason, str) and reason and _stamp(triggered), "invalid-legacy-trip")
    return {"state": "tripped", "trip_id": _digest(header)[:32], "reason": reason,
            "triggered_at": triggered, "source": "conductor-brake"}


def _rows(raw):
    """Parse the trip generations and recovery events of the original brake.

    The conductor's real frontmatter trip is the first generation. Recovery
    only appends event lines to that same file; no second brake file exists.
    """
    if raw and not raw.endswith(b"\n"):
        raise RecoveryBlocked("truncated-brake")
    events = []
    legacy = _legacy_trip(raw)
    if legacy is not None:
        events.append(legacy)
    text = raw.decode("utf-8")
    for line in text.splitlines():
        if not line.startswith(EVENT):
            continue
        try:
            row = json.loads(line[len(EVENT):])
        except ValueError:
            raise RecoveryBlocked("invalid-brake-event") from None
        _require(isinstance(row, dict) and TRIP.fullmatch(str(row.get("trip_id", "")))
                 and row.get("state") in {"tripped", "observing", "clear"}, "invalid-brake-event")
        known = {event["trip_id"] for event in events}
        if row["state"] == "tripped":
            _require(row["trip_id"] not in known, "invalid-trip-generation")
            # A concrete new hard signal is a new generation even when the
            # previous generation is still tripped (same reason/second too).
            _require(not events or events[-1]["state"] in {"tripped", "observing", "clear"},
                     "invalid-trip-generation")
            _require(isinstance(row.get("reason"), str) and row["reason"]
                     and _stamp(row.get("triggered_at")), "unknown-trip")
        else:
            _require(events and row["trip_id"] == events[-1]["trip_id"]
                     and (events[-1]["state"], row["state"]) in
                     {("tripped", "observing"), ("observing", "clear")},
                     "invalid-brake-transition")
        if row["state"] == "observing":
            _require(isinstance(row.get("decision_ref"), str) and row["decision_ref"].startswith(DP + ":")
                     and TRIP.fullmatch(str(row.get("grant_ref", "")))
                     and type(row.get("amount")) is int and row["amount"] > 0
                     and isinstance(row.get("usage_source"), str) and row["usage_source"],
                     "unverified-observation")
        events.append(row)
    _require(events, "brake-generation-unverified")
    return events


def managed_brake_state(project_root):
    """Read the original file for an enrolled project. An uncertain state holds the brake."""
    try:
        rows = _rows(_brake(pathlib.Path(project_root)).read_bytes())
        last = rows[-1]
        return {**last, "active": last["state"] != "clear", "trip": last["trip_id"]}
    except (OSError, ValueError, TypeError, KeyError):
        return {"state": "unknown", "active": True, "reason": "brake-generation-unverified", "trip": None}


def _append(path, original, event):
    # The operator service is the exclusive writer under the original object's
    # deployed ACL. The caller also holds the project brake lock.
    _require(path.read_bytes() == original, "brake-changed")
    text = original.decode("utf-8") + EVENT + json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    _rows(text.encode("utf-8"))
    gates._write_atomic(path, text)


_TRIGGER_REASONS = {"burst-60s", "burst-1h", "repeat-decisions"}
_TRIGGER_FIELDS = {"schema", "purpose", "project_id", "reason_code",
                   "detail", "evidence", "request_id"}


def _trigger_request(root, frozen):
    """The narrow trigger payload: no path, state, trip id, origin or grant."""
    try:
        req = json.loads(frozen)
    except (ValueError, TypeError):
        raise RecoveryBlocked("invalid-brake-trigger") from None
    _require(isinstance(req, dict) and set(req) == _TRIGGER_FIELDS
             and type(req["schema"]) is int and req["schema"] == 1
             and req["purpose"] == "brake-trigger"
             and req["project_id"] == wire.project_id_for(root)
             and isinstance(req["reason_code"], str)
             and req["reason_code"] in _TRIGGER_REASONS
             and isinstance(req["detail"], str) and req["detail"].strip()
             and TRIP.fullmatch(str(req["request_id"]))
             and isinstance(req["evidence"], list) and req["evidence"]
             and len(req["evidence"]) <= 64
             and all(type(item) is int and item > 0 for item in req["evidence"])
             and len(set(req["evidence"])) == len(req["evidence"]),
             "invalid-brake-trigger")
    return req


def _trigger_evidence(root, req):
    """Verify the claimed hard signal against the real append-only ledger."""
    _path, _raw, rows = _read_ledger(root)
    by_seq = {row["seq"]: row for row in rows}
    try:
        selected = [by_seq[seq] for seq in req["evidence"]]
    except KeyError:
        raise RecoveryBlocked("trigger-evidence-missing") from None
    _require(all(row.get("phase") == "decide" and row.get("executed") is True
                 for row in selected), "trigger-evidence-missing")
    reason = req["reason_code"]
    if reason == "repeat-decisions":
        counts = {}
        for row in selected:
            signature = (row.get("gate_key"), row.get("rule_id"), row.get("reason_code"))
            counts[signature] = counts.get(signature, 0) + 1
        _require(any(count >= 2 for count in counts.values()), "trigger-evidence-missing")
        return selected
    window = 60 if reason == "burst-60s" else 3600
    threshold = conductor.AUTO_BURST_60S if reason == "burst-60s" else conductor.AUTO_BURST_1H
    stamps = [_stamp(row.get("decided_at")) for row in selected]
    newest = max(stamps)
    _require(sum(1 for stamp in stamps if (newest - stamp).total_seconds() <= window) >= threshold,
             "trigger-evidence-missing")
    return selected


def _trigger_ledger_row(req, trip):
    stamp = _now()
    return {
        "decision_id": "breaker@" + stamp.isoformat(timespec="seconds"),
        "phase": "decide", "mode": "live", "executed": False,
        "decision": "escalate", "reason_code": "breaker-tripped",
        "refusal_code": req["reason_code"], "detail": req["detail"],
        "decided_by": "conductor", "decided_at": stamp.isoformat(timespec="seconds"),
        "gate_id": None, "gate_kind": None, "gate_key": None,
        "rule_id": "auto-breaker", "rule_version": "1",
        "night": conductor.night_window_key(stamp), "prop_ok": False,
        "trip_id": trip, "trigger_request_id": req["request_id"],
    }


def brake_facts(root, _frozen=b""):
    """Read-only protected facts for a registered project's original object."""
    try:
        root = pathlib.Path(root)
        _require(root.is_dir(), "unexpected-project-path")
        path = _brake(root)
        if not path.is_file():
            return {"state": "unknown", "active": True, "reason": "brake-missing",
                    "trip_id": None, "generation_verified": False,
                    "brake_sha256": None, "ledger_seq": None}
        data = path.read_bytes()
        rows = _rows(data)
        last = rows[-1]
        ledger_seq = None
        if last["state"] == "tripped":
            try:
                _ledger_path, _ledger_raw, ledger_rows = _read_ledger(root)
            except RecoveryBlocked:
                ledger_rows = []
            ledger_seq = next((row["seq"] for row in ledger_rows
                               if row.get("reason_code") == "breaker-tripped"
                               and row.get("trip_id") == last["trip_id"]
                               and row.get("refusal_code") == last["reason"]), None)
            if ledger_seq is None:
                return {"state": "unknown", "active": True,
                        "reason": "brake-generation-unverified", "trip_id": None,
                        "generation_verified": False,
                        "brake_sha256": _digest(data), "ledger_seq": None}
        return {"state": last["state"], "active": last["state"] != "clear",
                "reason": last.get("reason"), "trip_id": last["trip_id"],
                "generation_verified": True, "brake_sha256": _digest(data),
                "ledger_seq": ledger_seq}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"state": "unknown", "active": True,
                "reason": "brake-generation-unverified", "trip_id": None,
                "generation_verified": False, "brake_sha256": None,
                "ledger_seq": None}


def trigger_managed_brake(root, frozen):
    """The protected original writer for one new brake generation.

    One narrow message: the client names a real reason/evidence/request id; the
    service chooses the registered root, object and a fresh non-reusable trip
    id. A replay of the same recorded request never writes twice.
    """
    if not _authorized(root, "ask", frozen, None):
        return {"ok": False, "reason": "operator-host-required"}
    try:
        root = pathlib.Path(root)
        req = _trigger_request(root, frozen)
        _trigger_evidence(root, req)
        lock = root / ".mw/h12-brake.lock"
        with gate_effects._lock(root / ".mw" / "brake-trigger.lock"):
            mw_common.acquire_lock(lock, retries=0)
            try:
                path = _brake(root)
                if not path.is_file():
                    raise RecoveryBlocked("brake-generation-unverified")
                before = path.read_bytes()
                rows = _rows(before)
                recorded = [row for row in rows
                            if row.get("request_id") == req["request_id"]]
                ledger = [row for row in conductor.auto_decision_rows(root)
                          if row.get("trigger_request_id") == req["request_id"]]
                if recorded:
                    event = recorded[-1]
                    _require(event["state"] == "tripped"
                             and event.get("reason") == req["reason_code"]
                             and event.get("detail") == req["detail"]
                             and event.get("evidence") == req["evidence"],
                             "trigger-request-conflict")
                    if not ledger:
                        conductor._append_auto_decision_row(
                            root, _trigger_ledger_row(req, event["trip_id"]))
                    else:
                        _require(ledger[0].get("trip_id") == event["trip_id"],
                                 "trigger-state-conflict")
                    return {"ok": True, "trip_id": event["trip_id"], "state": "tripped",
                            "created": False, "receipt_sha256": _digest(before)}
                last = rows[-1]
                if ledger:
                    _require(ledger[0].get("refusal_code") == req["reason_code"]
                             and ledger[0].get("detail") == req["detail"],
                             "trigger-request-conflict")
                    trip = ledger[0]["trip_id"]
                    _require(TRIP.fullmatch(str(trip)), "trigger-state-conflict")
                else:
                    trip = uuid.uuid4().hex
                event = {"state": "tripped", "trip_id": trip,
                         "reason": req["reason_code"],
                         "triggered_at": _now().isoformat(timespec="seconds"),
                         "request_id": req["request_id"],
                         "evidence": req["evidence"], "detail": req["detail"]}
                _append(path, before, event)
                after = path.read_bytes()
                if not ledger:
                    conductor._append_auto_decision_row(root, _trigger_ledger_row(req, trip))
                _require(managed_brake_state(root)["trip"] == trip, "brake-receipt-unknown")
                return {"ok": True, "trip_id": trip, "state": "tripped",
                        "created": True, "receipt_sha256": _digest(after)}
            finally:
                mw_common.release_lock(lock)
    except RecoveryBlocked as exc:
        return {"ok": False, "reason": str(exc)}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        reason = str(exc) if isinstance(exc, RecoveryBlocked) else "trigger-unknown"
        return {"ok": False, "reason": reason}


def recovery_matter(key, trip, reason, note, grant_ref):
    """Stable binding shared by the PM's prepared gate and the service."""
    return validity.matter_for(key, "auto-brake/" + trip, ACTION, [
        validity.DependencyState("trip", "structured", {"trip_id": trip, "reason": reason}),
        validity.DependencyState("note", "structured", note),
        validity.DependencyState("authorization", "ref", grant_ref),
    ], matter_kind="gate-action", contract_version="h12-v1", authority_required=True)


def _authorized(root, purpose, frozen, grant):
    """Ask the deployed service. A ContextVar or caller boolean is never enough."""
    try:
        import operator_host
        callback = operator_host.authorized_callback
        return callback(pathlib.Path(root), purpose, frozen, grant) is True
    except (ImportError, AttributeError, OSError, ValueError, TypeError):
        return False


def _tokens(value):
    return (isinstance(value, (list, tuple)) and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value))


def _bound_request(root, frozen, grant):
    """Shape and object binding of one frozen request, without re-checking the grant."""
    req = json.loads(frozen)
    _require(set(req) == {"schema", "purpose", "project_id", "key", "trip_id", "grant_ref",
                          "gate_id", "pm_note", "preparation", "action"}
             and type(req["schema"]) is int and req["schema"] == 1 and req["purpose"] == "h12"
             and req["action"] == ACTION and GATE.fullmatch(req["gate_id"]), "invalid-recovery-request")
    _require(TRIP.fullmatch(req["trip_id"]) and TRIP.fullmatch(req["grant_ref"])
             and req["project_id"] == wire.project_id_for(root)
             and all(req[k] == grant[k] for k in ("project_id", "key", "trip_id", "grant_ref")),
             "grant-binding-mismatch")
    _require(TRIP.fullmatch(str(grant.get("operation_id", ""))), "invalid-operation-id")
    return req


def _request(root, frozen, grant):
    req = _bound_request(root, frozen, grant)
    _require(grant.get("revoked") is False and _stamp(grant.get("recorded_at")) <= _now() < _stamp(grant.get("expires_at")),
             "preauthorization-expired-or-revoked")
    _require(_tokens(grant.get("scope")) and "recovery:breaker" in grant["scope"]
             and "observe-brake" in grant["scope"], "grant-scope-mismatch")
    _require(_tokens(grant.get("trusted_writers")), "trusted-writers-missing")
    _require(isinstance(grant.get("authority_source"), dict) and grant["authority_source"],
             "authority-source-missing")
    _require(isinstance(grant.get("usage_sources"), dict), "usage-source-missing")
    _require(isinstance(grant.get("authority_ref"), str) and grant["authority_ref"] in grant["authority_source"],
             "authority-ref-missing")
    _require(isinstance(grant.get("usage_source"), str) and grant["usage_source"],
             "usage-source-missing")
    _require(type(grant.get("amount")) is int and grant["amount"] == 1, "unsupported-spend")
    _require(isinstance(grant.get("unit"), str) and grant["unit"], "unknown-budget-unit")
    _require(_tokens(grant.get("observation_conditions")) and _tokens(grant.get("stop_conditions")),
             "recovery-plan-missing")
    rows = [r for r in state.read_index(root) if r["key"] == req["key"]]
    _require(len(rows) == 1 and rows[0]["claim_id"] == grant["claim"] and rows[0]["status"] == "active"
             and state.claim_state(grant["claim"]) == state.CLAIM_LIVE, "pm-claim-changed")
    return req


def _read_ledger(root):
    path = _ledger(root)
    raw = path.read_bytes()
    _require(raw.endswith(b"\n"), "incomplete-machine-history")
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise RecoveryBlocked("incomplete-machine-history") from None
        _require(isinstance(row, dict) and type(row.get("seq")) is int
                 and row["seq"] == len(rows) + 1, "incomplete-machine-history")
        rows.append(row)
    return path, raw, rows


def _policy_checks(load, grant, req, gate_scope, recovery_scope, ledger_digest):
    trusted = tuple(grant["trusted_writers"])
    sources = {}
    for ref, row in grant["authority_source"].items():
        _require(isinstance(row, dict), "invalid-protected-authority")
        parsed, issues = policy.parse_authority_record(row, trusted_writers=trusted)
        _require(not issues and parsed is not None and parsed.authority_ref == ref,
                 "invalid-protected-authority")
        _require(not parsed.revoked, "authority-revoked")
        sources[ref] = parsed
    _require(grant["authority_ref"] in sources, "authority-unresolved")
    _require(policy.evaluate_gate(
        load, choice="approve",
        hard_checks={"reason-cleared": True, "brake-generation-verified": True,
                     "policy-version-verified": True, "pm-claim-live": True},
        automation_enabled=True, required_scope=gate_scope, authority_source=sources,
        trusted_writers=trusted).allowed, "original-authority-missing")
    verdict = policy.evaluate_breaker_recovery(
        load, request={
            "required_scope": recovery_scope, "preauthorization_ref": grant["authority_ref"],
            "reason_elimination_evidence": ["auto-decisions:sha256=" + ledger_digest],
            "machine_checks": {"original-signal-cleared": True},
            "transport_available": True, "user_disabled": False,
            "channel": "pm-controlled-recovery", "origin": "pm-controlled",
            "tripped_chain": "auto-pass", "choice": "approve",
        }, authority_source=sources, trusted_writers=trusted,
        controlled_channels=("pm-controlled-recovery",))
    _require(verdict.allowed, "recovery-authority-missing")
    return sources


def _observation(root, req, grant):
    data = _brake(root).read_bytes()
    history = _rows(data)
    trips = [row for row in history if row["state"] == "tripped"]
    _require(len(trips) >= 1 and history[-1]["state"] == "tripped"
             and history[-1]["trip_id"] == req["trip_id"],
             "different-or-inactive-trip")
    trip = trips[-1]
    _require(trip["reason"] == grant["reason"], "different-or-inactive-trip")
    _require(trip["reason"] in {"burst-60s", "burst-1h", "repeat-decisions"},
             "unsupported-trip-reason")
    ledger, ledger_data, rows = _read_ledger(root)
    _require(any(row.get("reason_code") == "breaker-tripped"
                 and row.get("trip_id") == trip["trip_id"]
                 and row.get("refusal_code") == trip["reason"] for row in rows),
             "trip-evidence-missing")
    _require(conductor._auto_breaker_signal(rows, _now()) is None, "breaker-signal-present")
    cfg = config.load_config(root)
    _require(cfg.get("enabled") is True and cfg.get("paused") is False
             and cfg.get("auto_gate_mode") == "live", "automation-disabled-or-paused")
    path = _safe_file(root, policy.policy_path(root))
    raw = path.read_bytes()
    _require(_digest(raw) == grant.get("policy_sha256"), "policy-version-changed")
    load = policy.parse_policy(json.loads(raw))
    _require(load.usable and load.policy.recovery is not None and not load.recovery_issues,
             "recovery-policy-unavailable")
    rule = load.policy.recovery
    # The host records the actual usage source; the ledger bytes this request
    # reasons over are the current original file, not a caller-supplied hash.
    if "ledger_sha256" in grant:
        _require(grant["ledger_sha256"] == _digest(ledger_data), "ledger-version-changed")
    _require(rule.authority_ref == grant["authority_ref"]
             and list(rule.observation_conditions) == list(grant["observation_conditions"])
             and list(rule.stop_conditions) == list(grant["stop_conditions"]),
             "recovery-plan-changed")
    gate_scope = ("recovery:breaker", "key:" + req["key"], "action:" + ACTION)
    recovery_scope = ("recovery:breaker",)
    _require(set(gate_scope).issubset(set(grant["scope"])), "grant-scope-mismatch")
    _require(set(recovery_scope).issubset(set(grant["scope"])), "grant-scope-mismatch")
    sources = _policy_checks(load, grant, req, gate_scope, recovery_scope,
                             _digest(ledger_data))
    requested = grant["unit"]
    for limit in load.policy.hard_limits:
        descriptor = grant["usage_sources"].get(limit.usage_source)
        _require(descriptor == {"kind": "auto-decisions", "unit": limit.unit},
                 "unverified-budget-source")
        used = sum(row.get("executed") is True for row in rows) + sum(
            row["amount"] for row in history
            if row["state"] == "observing" and row["usage_source"] == limit.usage_source)
        _require(used <= limit.limit, "hard-budget-exhausted")
        if limit.unit == requested:
            _require(limit.usage_source == grant["usage_source"]
                     and policy.check_spend(load, unit=requested, amount=1,
                                            usage={requested: used}).allowed,
                     "hard-budget-exhausted")
    _require(load.policy.limit_for(requested) is not None, "unknown-budget-unit")
    gpath = _safe_file(root, root / ".agenticdoc/_autopilot/gates" / (req["gate_id"] + ".md"))
    gate = gates.parse(gpath)
    matter = recovery_matter(req["key"], req["trip_id"], trip["reason"], req["pm_note"],
                             req["grant_ref"])
    _require(gate.key == req["key"] and gate.kind == "stalled"
             and gate.matter_ref == matter.matter_key
             and gate.substantive_version == matter.substantive_version
             and gate.pm_note is not None and json.loads(gate.pm_note) == req["pm_note"]
             and req["pm_note"].get("planned_action") == ACTION, "prepared-gate-mismatch")
    material = {
        "gate_background": gate.question,
        "current_state": f"tripped {trip['trip_id']} ({trip['reason']})",
        "condition_evidence": [ledger.name + " sha256=" + _digest(ledger_data),
                               "budget source " + grant["usage_source"]],
        "pm_note": req["pm_note"],
    }
    _require(not decision_points.prepared_request_issues(
        DP, material, req["preparation"], actor_role="pm"), "invalid-preparation")
    _require(sources is not None, "authority-source-missing")
    return data, gate, material


def _client_store(root):
    cfg, error = decision.DecisionConfig.from_project(root)
    _require(not error and cfg.enabled and cfg.transport == "timi-decisions",
             "decision-transport-unavailable")
    snap = decision.credential_snapshot(cfg)
    redact = decision.credential_redactor(cfg, snapshot=snap)
    _require(redact is not None, "redaction-unavailable")
    return (decision.DecisionClient(cfg, project_root=root, credential_snapshot=snap),
            lifecycle.LifecycleStore.production(root, redact=redact))


def _refuse(exc):
    if isinstance(exc, RecoveryBlocked):
        return {"ok": False, "reason": str(exc)}
    return {"ok": False, "reason": "recovery-evidence-unavailable"}


def _facts(store, logical, key):
    rows = lifecycle.read_lifecycle(store)
    _require(not any(getattr(rows.stats, name) for name in
                     ("bad_json", "bad_utf8", "unknown_schema", "oversized_line", "incomplete_tail")),
             "incomplete-decision-ledger")
    return rows, [row for row in rows.events
                  if row.get("logical_id") == logical and row.get("key") == key
                  and row.get("project_id") == store.project_id]


def _recorded_request(facts, ref, key, store, material, preparation):
    requests = [row for row in facts if row.get("kind") == "request"
                and row.get("decision_id") == ref]
    if not requests:
        return None
    _require(len(requests) == 1, "conflicting-requests")
    row = requests[0]
    _require(row.get("key") == key and row.get("project_id") == store.project_id,
             "request-provenance-mismatch")
    _require(row.get("material") is None or row.get("material") == material,
             "checkpoint-material-changed")
    _require(row.get("preparation") is None or row.get("preparation") == preparation,
             "checkpoint-preparation-changed")
    return row


def _verify_answer(gate, req, grant, choice, basis, ref):
    """The original prepared gate must already carry exactly this answer."""
    matter = recovery_matter(req["key"], req["trip_id"], grant["reason"], req["pm_note"],
                             req["grant_ref"])
    _require(gate.transport == "answered" and gate.business == choice
             and gate.decision_ref == ref and gate.model_basis == basis
             and gate.matter_ref == matter.matter_key
             and gate.substantive_version == matter.substantive_version
             and gate.answered_by == grant["claim"] and gate.effect in _GATE_EFFECTS,
             "gate-answer-mismatch")
    return gate


def prepare_operator_recovery(root, frozen, grant):
    """Called in a reserved, bound service operation, outside the brake lock."""
    if not _authorized(root, "h12.prepare", frozen, grant):
        return {"ok": False, "reason": "operator-host-required"}
    try:
        root = pathlib.Path(root)
        req = _request(root, frozen, grant)
        before, gate, material = _observation(root, req, grant)
        client, store = _client_store(root)
        logical = grant["operation_id"]
        ref = DP + ":" + logical
        meta = lifecycle.DecisionMeta.create(req["key"], initiator_role="pm", logical_id=logical)
        actor = ("system", "pm:" + grant["claim"])
        _, facts = _facts(store, logical, req["key"])
        recorded = _recorded_request(facts, ref, req["key"], store, material,
                                     req["preparation"])
        if recorded is not None:
            _require(recorded.get("business_decisions") == 1,
                     "previous-request-refused")
            choice = recorded.get("choice")
            basis_id = recorded.get("basis_id")
            basis_text = recorded.get("basis_text")
            _require(isinstance(choice, str) and isinstance(basis_id, str)
                     and isinstance(basis_text, str), "recorded-decision-incomplete")
            if gate.transport == "pending" and gate.effect == "not-started":
                # A crash after the one model call but before the formal answer:
                # deposit the recorded answer without asking the model again.
                _answer_gate(root, gate, req, recorded, grant, ref)
            else:
                _verify_answer(gate, req, grant, choice, basis_text, ref)
            if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "consumed"
                       and row.get("decision_id") == ref and row.get("answer") == choice
                       for row in facts):
                _require(lifecycle.record_consumed(
                    store, meta, decision_id=ref, dp=DP, answer=choice, actor=actor,
                    event_id="h12-received-" + logical).recorded, "answer-not-recorded")
            return {"ok": True, "choice": choice, "basis_id": basis_id,
                    "basis_text": basis_text, "decision_ref": ref,
                    "before_sha256": _digest(before), "matter_ref": gate.matter_ref,
                    "substantive_version": gate.substantive_version,
                    "trip_id": req["trip_id"], "resumed": True}
        _require(gate.transport == "pending" and gate.effect == "not-started",
                 "gate-already-answered")
        _require(not any(row.get("kind") == "lifecycle" and row.get("lifecycle") in
                         {"executed", "settled"} for row in facts),
                 "checkpoint-inconsistent")
        _require(lifecycle.record_start(store, meta, decision_id=ref, actor=actor).recorded,
                 "start-not-recorded")
        _require(lifecycle.record_note(store, meta, decision_id=ref, pm_note=gate.pm_note,
                 prepared_at=req["preparation"]["prepared_at"], actor=actor).recorded,
                 "note-not-recorded")
        result = client.request_prepared(DP, material, req["preparation"], actor_role="pm",
                                         logical_id=logical,
                                         replay_check=lambda _dp, _lid: False)
        _require(lifecycle.record_request(store, meta, decision_id=ref, result=result,
                 material=material, preparation=req["preparation"], actor=actor).recorded,
                 "request-not-recorded")
        _require(result.get("available") is True and result.get("business_decisions") == 1,
                 "no-valid-gate-decision")
        answered = _answer_gate(root, gate, req, result, grant, ref)
        _require(lifecycle.record_consumed(store, meta, decision_id=ref, dp=DP,
                 answer=result["choice"], actor=actor,
                 event_id="h12-received-" + logical).recorded, "answer-not-recorded")
        return {"ok": True, "choice": result["choice"], "basis_id": result["basis_id"],
                "basis_text": result["basis_text"], "decision_ref": ref,
                "before_sha256": _digest(before), "matter_ref": gate.matter_ref,
                "substantive_version": gate.substantive_version,
                "trip_id": req["trip_id"], "effect": answered.effect, "resumed": False}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


def _recorded_observation(rows, ref, grant):
    for row in reversed(rows):
        if row["state"] == "observing" and row.get("decision_ref") == ref:
            _require(row["trip_id"] == grant["trip_id"] and row["grant_ref"] == grant["grant_ref"],
                     "observation-binding-mismatch")
            return row
    return None


def _recovery_gate_lock(root):
    return gate_effects._lock(root / ".mw" / "gates.lock")


def _record_receipt(store, meta, ref, logical, actor, facts, receipt):
    """Supplement the real execution/settlement receipts after an actual effect."""
    if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "executed"
               for row in facts):
        _require(lifecycle.record_executed(
            store, meta, decision_id=ref, dp=DP, action="record", result=receipt,
            reason=ACTION, actor=actor, event_id="h12-executed-" + logical).recorded,
            "execution-receipt-unknown")
    if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "settled"
               for row in facts):
        _require(lifecycle.record_settled(
            store, meta, decision_id=ref, dp=DP, outcome="ok", reason=receipt,
            actor=actor, event_id="h12-settled-" + logical).recorded, "settlement-unknown")


def apply_operator_recovery(root, frozen, grant, decision_result):
    """One service-serialized redemption after a real decision. No model call on replay."""
    if not _authorized(root, "h12.apply", frozen, grant):
        return {"ok": False, "reason": "operator-host-required"}
    try:
        root = pathlib.Path(root)
        req = _request(root, frozen, grant)
        logical = grant["operation_id"]
        ref = DP + ":" + logical
        _require(decision_result.get("ok") is True and TRIP.fullmatch(logical)
                 and decision_result.get("decision_ref") == ref, "unrelated-decision")
        _, store = _client_store(root)
        meta = lifecycle.DecisionMeta.create(req["key"], initiator_role="pm", logical_id=logical)
        actor = ("system", "pm:" + grant["claim"])
        _, facts = _facts(store, logical, req["key"])
        requests = [row for row in facts if row.get("kind") == "request"
                    and row.get("decision_id") == ref]
        _require(len(requests) == 1, "decision-record-mismatch")
        request = requests[0]
        _require(request.get("business_decisions") == 1
                 and request.get("basis_id") == decision_result.get("basis_id")
                 and request.get("basis_text") == decision_result.get("basis_text")
                 and request.get("choice") == decision_result.get("choice")
                 and any(row.get("lifecycle") == "consumed" and row.get("answer") == request["choice"]
                         for row in facts), "decision-record-mismatch")
        choice = request["choice"]
        basis_text = request["basis_text"]
        if choice != "approve":
            if not any(row.get("lifecycle") == "settled" for row in facts):
                _require(lifecycle.record_settled(
                    store, meta, decision_id=ref, dp=DP, outcome="inconclusive",
                    reason="brake remains engaged", actor=actor,
                    event_id="h12-settled-" + logical).recorded, "settlement-not-recorded")
            return {"ok": False, "reason": "brake-remains-engaged", "choice": choice,
                    "decision_ref": ref}
        gate = gates.parse(_safe_file(root, root / ".agenticdoc/_autopilot/gates" / (req["gate_id"] + ".md")))
        _verify_answer(gate, req, grant, choice, basis_text, ref)
        matter_lock = root / ".mw" / ("matter-" + hashlib.sha256(gate.matter_ref.encode()).hexdigest() + ".lock")
        brake_lock = root / ".mw/h12-brake.lock"
        with gate_effects._lock(matter_lock):
            mw_common.acquire_lock(brake_lock, retries=0)
            try:
                _request(root, frozen, grant)
                path = _brake(root)
                before = path.read_bytes()
                rows = _rows(before)
                observed = _recorded_observation(rows, ref, grant)
                if observed is not None:
                    # The actual brake bytes already carry this decision's effect:
                    # only the gate marker and the receipts may be completed.
                    receipt = _digest(before)
                    with _recovery_gate_lock(root):
                        current = gates.parse(gate.path)
                        _verify_answer(current, req, grant, choice, basis_text, ref)
                        if current.effect != "applied":
                            gate_effects._replace_effect(current, "applied")
                    _record_receipt(store, meta, ref, logical, actor, facts, receipt)
                    return {"ok": True, "state": "observing", "brake_state": "observing",
                            "effect": "applied", "trip_id": req["trip_id"],
                            "decision_ref": ref, "receipt": receipt,
                            "receipt_sha256": receipt, "resumed": True}
                _, gate, material = _observation(root, req, grant)
                _verify_answer(gate, req, grant, choice, basis_text, ref)
                _require(_digest(before) == decision_result.get("before_sha256")
                         and gate.matter_ref == decision_result.get("matter_ref")
                         and gate.substantive_version == decision_result.get("substantive_version"),
                         "recovery-basis-changed")
                _require(not decision_points.prepared_request_issues(
                    DP, material, req["preparation"], actor_role="pm", choice=choice,
                    basis_id=decision_result["basis_id"]), "prepared-basis-changed")
                if gate.effect in {"in-progress", "unknown"}:
                    # An earlier attempt reserved the matter but the object never
                    # proves the effect: inspect only, never repeat the write.
                    if gate.effect == "in-progress":
                        with _recovery_gate_lock(root):
                            current = gates.parse(gate.path)
                            if current.effect == "in-progress" and _recorded_observation(
                                    _rows(path.read_bytes()), ref, grant) is None:
                                gate_effects._replace_effect(current, "unknown")
                    return {"ok": False, "reason": "recovery-effect-unknown",
                            "state": "unknown", "effect": "unknown", "decision_ref": ref}
                _require(gate.effect not in {"blocked", "failed"}, "gate-effect-refused")
                if gate.effect == "applied":
                    # An applied marker without the brake's own receipt cannot
                    # authorize a second write; inspect the object instead.
                    return {"ok": False, "reason": "recovery-effect-unknown",
                            "state": "unknown", "effect": "applied", "decision_ref": ref}
                _require(gate.effect == "not-started", "recovery-effect-unknown")
                with _recovery_gate_lock(root):
                    current = gates.parse(gate.path)
                    _verify_answer(current, req, grant, choice, basis_text, ref)
                    _require(current.effect == "not-started", "recovery-effect-unknown")
                    gate_effects._replace_effect(current, "in-progress")
                event = dict(state="observing", trip_id=req["trip_id"],
                             grant_ref=req["grant_ref"], decision_ref=ref,
                             usage_source=grant["usage_source"], amount=1, reason=grant["reason"],
                             at=_now().isoformat(), observation_conditions=grant["observation_conditions"],
                             stop_conditions=grant["stop_conditions"])
                _append(path, before, event)
                after = path.read_bytes()
                _require(_rows(after)[-1] == event, "brake-receipt-unknown")
                receipt = _digest(after)
                with _recovery_gate_lock(root):
                    current = gates.parse(gate.path)
                    _require(current.transport == "answered" and current.business == choice
                             and current.decision_ref == ref, "gate-changed-during-recovery")
                    gate_effects._replace_effect(current, "applied")
                _record_receipt(store, meta, ref, logical, actor, facts, receipt)
                return {"ok": True, "state": "observing", "brake_state": "observing",
                        "effect": "applied", "trip_id": req["trip_id"],
                        "decision_ref": ref, "receipt": receipt,
                        "receipt_sha256": receipt, "resumed": False}
            finally:
                mw_common.release_lock(brake_lock)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


def _retrip(root, path, req, ref, reason, detail, observed_conditions, failed_checks):
    """Append a new trip generation over the still-active observation."""
    lock = root / ".mw/h12-brake.lock"
    mw_common.acquire_lock(lock, retries=0)
    try:
        before = path.read_bytes()
        history = _rows(before)
        observed = _recorded_observation(history, ref, {"trip_id": req["trip_id"],
                                                       "grant_ref": req["grant_ref"]})
        if observed is None or history[-1].get("decision_ref") != ref:
            last = history[-1]
            return {"ok": True, "state": last["state"], "retripped": False,
                    "trip_id": last["trip_id"], "decision_ref": ref,
                    "reason": "observation-superseded"}
        seed = (req["trip_id"] + ref + json.dumps(list(observed_conditions), sort_keys=True)
                + json.dumps(list(failed_checks), sort_keys=True) + detail)
        new_trip = _digest(seed.encode("utf-8"))[:32]
        event = dict(state="tripped", trip_id=new_trip, reason=reason,
                     triggered_at=_now().isoformat(), detail=detail,
                     decision_ref=ref, grant_ref=req["grant_ref"],
                     observed=list(observed_conditions), failed=list(failed_checks))
        _append(path, before, event)
        # Keep the canonical auto-decision ledger in step with the new
        # generation: the ordinary reader only verifies a trip that has its
        # own real ledger row. A crash between the two leaves an unverified
        # (unknown/active) generation, never a released brake.
        stamp = _now()
        conductor._append_auto_decision_row(root, {
            "decision_id": "breaker@" + stamp.isoformat(timespec="seconds"),
            "phase": "decide", "mode": "live", "executed": False,
            "decision": "escalate", "reason_code": "breaker-tripped",
            "refusal_code": reason, "detail": detail,
            "decided_by": "operator", "decided_at": stamp.isoformat(timespec="seconds"),
            "gate_id": None, "gate_kind": None, "gate_key": None,
            "rule_id": "auto-breaker", "rule_version": "1",
            "night": conductor.night_window_key(stamp), "prop_ok": False,
            "trip_id": new_trip, "decision_ref": ref,
        })
        after = path.read_bytes()
        _require(_rows(after)[-1]["trip_id"] == new_trip, "retrip-receipt-unknown")
        return {"ok": True, "state": "retripped", "retripped": True,
                "trip_id": new_trip, "decision_ref": ref, "receipt": _digest(after)}
    finally:
        mw_common.release_lock(lock)


def observe_operator_recovery(root, frozen, grant, *, observed_conditions=(), failed_checks=()):
    """Observe one limited recovery; a lost reason or stop condition re-trips.

    The caller must supply the same reserved operation binding. A retrip keeps
    the original trip/observing history and appends a new ``tripped`` event in
    the original brake file. A revoked, expired or superseded authorization
    also re-trips: it must never leave a live observing licence behind.
    """
    if not _authorized(root, "h12.observe", frozen, grant):
        return {"ok": False, "reason": "operator-host-required"}
    try:
        root = pathlib.Path(root)
        req = _bound_request(root, frozen, grant)
        logical = grant["operation_id"]
        ref = DP + ":" + logical
        path = _brake(root)
        history = _rows(path.read_bytes())
        observed = _recorded_observation(history, ref, grant)
        _require(observed is not None or any(
            row["state"] == "clear" and row.get("decision_ref") == ref for row in history),
            "no-active-observation")
        last = history[-1]
        if last["state"] != "observing" or last.get("decision_ref") != ref:
            return {"ok": True, "state": last["state"], "retripped": False,
                    "trip_id": last["trip_id"], "decision_ref": ref,
                    "reason": "observation-superseded"}
        try:
            _request(root, frozen, grant)
        except RecoveryBlocked as exc:
            # The authorization/claim/evidence of the limited recovery is gone:
            # re-engage the brake instead of refusing while leaving it live.
            return _retrip(root, path, req, ref, grant.get("reason") or "recovery-authorization-lost",
                           "limited recovery no longer authorized: " + str(exc),
                           observed_conditions, failed_checks)
        rule = policy.RecoveryRule(
            allowed_origins=("pm-controlled",),
            scope=("recovery:breaker",),
            authority_ref=grant["authority_ref"],
            observation_conditions=tuple(grant["observation_conditions"]),
            stop_conditions=tuple(grant["stop_conditions"]),
        )
        verdict = policy.RecoveryVerdict(
            True, ("recovery:breaker",), rule.observation_conditions, rule.stop_conditions,
            ("trip:" + req["trip_id"],), (), (), False, (),
        )
        observation = policy.observe_recovery(
            verdict, observed_conditions=observed_conditions, failed_checks=failed_checks)
        if not observation.retrip:
            return {"ok": True, "state": "observing", "retripped": False,
                    "trip_id": req["trip_id"], "decision_ref": ref}
        return _retrip(root, path, req, ref, grant["reason"],
                       "stop condition observed after limited recovery",
                       observed_conditions, failed_checks)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


# ── H11 halted-stage recovery ─────────────────────────────────────────────────

H11_ACTION = "recover-halted"
H11_PURPOSE = "h11"
_H11_RECOVERY_PREFIX = "> recovery: "
_H11_FOLLOW_UP = {"steer": "dp-pm-steer", "need_fix": "dp-auto"}
_BOUNDED_KIND = "dispatch-round"
_BOUNDED_ACTION_FIELDS = frozenset({
    "kind", "task_key", "task_type", "card_sha256", "write_face", "amount",
    "end_criterion",
})
_BOUNDED_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}")


def _bounded_action(note):
    """The one existing limited action the approved PM note names, if any.

    The note stays the H11 native note; this is an optional structured field on
    it, so notes that only carry observation authority keep working and can
    never be widened into a dispatch by this module.
    """
    if not isinstance(note, dict) or "bounded_action" not in note:
        return None
    action = note["bounded_action"]
    _require(isinstance(action, dict) and set(action) == _BOUNDED_ACTION_FIELDS,
             "invalid-bounded-action")
    _require(action.get("kind") == _BOUNDED_KIND, "invalid-bounded-action")
    _require(isinstance(action.get("task_key"), str)
             and _BOUNDED_KEY.fullmatch(action["task_key"]), "invalid-bounded-action")
    _require(isinstance(action.get("task_type"), str)
             and _BOUNDED_KEY.fullmatch(action["task_type"]), "invalid-bounded-action")
    _require(_hex64(action.get("card_sha256")), "invalid-bounded-action")
    _require(_tokens(action.get("write_face")), "invalid-bounded-action")
    _require(type(action.get("amount")) is int and action["amount"] == 1,
             "unsupported-spend")
    _require(isinstance(action.get("end_criterion"), str)
             and action["end_criterion"].strip(), "invalid-bounded-action")
    return {**action, "write_face": list(action["write_face"])}


def _bounded_baseline(root, key, note, used):
    """Freeze the real target task/card/queue before the model sees the note.

    This is a plan and its baseline, never evidence that anything happened. The
    target identity, card digest, write face, loop and cumulative usage all come
    from the original objects; the note only names them.
    """
    action = _bounded_action(note)
    if action is None:
        return None
    prefix = "ap-" + key + "-"
    task_key = action["task_key"]
    _require(task_key.startswith(prefix) and len(task_key) > len(prefix),
             "bounded-target-unverified")
    stem = task_key[len(prefix):]
    _require(task_key == dispatch_writer.task_key_for(key, stem),
             "bounded-target-unverified")
    card = _safe_file(root, root / ".agenticdoc" / key / "tasks" / (stem + ".md"))
    _require(card.is_file(), "bounded-card-unverified")
    _require(dispatch_writer.card_digest(card) == action["card_sha256"],
             "bounded-card-changed")
    card_info = dispatch_writer.dispatch_card(root, key, stem)
    _require(isinstance(card_info, dict), "bounded-card-unverified")
    face = dispatch_writer._card_write_face_entries(card_info)
    _require(face is not None and list(face) == action["write_face"],
             "bounded-write-face-changed")
    task_md = _safe_file(
        root, root / ".agenticdoc" / key / "workers" / task_key / "task.md")
    _require(task_md.is_file(), "bounded-target-unverified")
    labels = state.parse_task_labels(task_md)
    loop = str(labels.get("loop") or "").strip()
    attempt_raw = str(labels.get("attempt") or "").strip()
    _require(loop and re.fullmatch(r"[1-9][0-9]*", attempt_raw),
             "bounded-target-unverified")
    _require(str(labels.get("type") or "").strip() == action["task_type"],
             "bounded-target-unverified")
    queue = mw_common.workers_path(root)
    raw = queue.read_bytes() if queue.exists() else b""
    rows = [row for row in mw_common.parse_workers_file(queue)
            if row["task_key"] == task_key]
    _require(len(rows) <= 1, "bounded-target-conflict")
    if rows:
        _require(rows[0]["status"] in mw_common.RUN_TERMINAL_STATUSES,
                 "bounded-target-in-flight")
    return {
        **{name: action[name] for name in (
            "kind", "task_key", "task_type", "card_sha256", "write_face",
            "amount", "end_criterion")},
        "stem": stem,
        "loop": loop,
        "base_attempt": int(attempt_raw),
        "base_task_sha256": _digest(task_md.read_bytes()),
        "base_queue_sha256": _digest(raw),
        "base_used": used,
    }


def _bounded_objects(root, key, baseline):
    """Re-read the original target objects against the frozen baseline."""
    task_key = baseline["task_key"]
    stem = baseline["stem"]
    card = _safe_file(root, root / ".agenticdoc" / key / "tasks" / (stem + ".md"))
    _require(card.is_file() and dispatch_writer.card_digest(card)
             == baseline["card_sha256"], "bounded-card-changed")
    card_info = dispatch_writer.dispatch_card(root, key, stem)
    _require(isinstance(card_info, dict), "bounded-card-unverified")
    face = dispatch_writer._card_write_face_entries(card_info)
    _require(face is not None and list(face) == list(baseline["write_face"]),
             "bounded-write-face-changed")
    task_md = _safe_file(
        root, root / ".agenticdoc" / key / "workers" / task_key / "task.md")
    _require(task_md.is_file(), "bounded-target-changed")
    labels = state.parse_task_labels(task_md)
    attempt_raw = str(labels.get("attempt") or "").strip()
    _require(str(labels.get("loop") or "").strip() == baseline["loop"]
             and str(labels.get("type") or "").strip() == baseline["task_type"]
             and re.fullmatch(r"[1-9][0-9]*", attempt_raw),
             "bounded-target-changed")
    queue = mw_common.workers_path(root)
    raw = queue.read_bytes() if queue.exists() else b""
    rows = [row for row in mw_common.parse_workers_file(queue)
            if row["task_key"] == task_key]
    _require(len(rows) <= 1, "bounded-target-conflict")
    return task_md, task_md.read_bytes(), int(attempt_raw), raw, rows


def _bounded_evaluate(root, key, baseline, limit):
    """Classify the real objects as pending, dispatched or unknown."""
    task_md, task_raw, attempt, queue_raw, rows = _bounded_objects(
        root, key, baseline)
    used = _h11_used_rounds(root, key)
    _require(used <= limit.limit, "hard-budget-exhausted")
    if (attempt == baseline["base_attempt"]
            and _digest(task_raw) == baseline["base_task_sha256"]
            and _digest(queue_raw) == baseline["base_queue_sha256"]):
        return {"state": "pending", "used": used, "task_md": task_md,
                "task_raw": task_raw, "queue_raw": queue_raw, "rows": rows,
                "attempt": attempt}
    if (attempt == baseline["base_attempt"] + 1
            and used == baseline["base_used"] + 1 and rows
            and rows[0]["task_path"] == str(task_md)
            and rows[0]["origin"] == mw_common.WORKER_ORIGIN_CONDUCTOR):
        try:
            ordered = (_stamp(rows[0]["dispatched_at"]).replace(microsecond=0)
                       >= _stamp(baseline.get("at")).replace(microsecond=0))
        except (KeyError, ValueError, TypeError):
            ordered = False
        if ordered:
            return {"state": "dispatched", "used": used, "task_md": task_md,
                    "task_raw": task_raw, "queue_raw": queue_raw, "rows": rows,
                    "attempt": attempt}
    return {"state": "unknown", "used": used, "task_md": task_md,
            "task_raw": task_raw, "queue_raw": queue_raw, "rows": rows,
            "attempt": attempt}


def _record_bounded_receipt(store, meta, ref, logical, actor, receipt):
    """The real dispatch action and its settlement, never a task completion."""
    receipt_sha256 = _digest(json.dumps(
        receipt, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    result = json.dumps({**receipt, "receipt_sha256": receipt_sha256},
                        sort_keys=True, separators=(",", ":"))
    _require(lifecycle.record_executed(
        store, meta, decision_id=ref, dp=DP, action="direct-exec", result=result,
        reason="h11 bounded dispatch " + receipt["task_key"] + " attempt "
               + str(receipt["attempt"]),
        actor=actor, event_id="h11-bounded-executed-" + logical).recorded,
        "execution-receipt-unknown")
    _require(lifecycle.record_settled(
        store, meta, decision_id=ref, dp=DP, outcome="ok",
        reason="one bounded dispatch queued; worker task not complete",
        actor=actor, event_id="h11-bounded-settled-" + logical).recorded,
        "settlement-unknown")


def _bounded_receipt(state, baseline):
    queue_row = state["rows"][0] if state["rows"] else {}
    return {
        "task_key": baseline["task_key"],
        "attempt": state["attempt"],
        "task_sha256": _digest(state["task_raw"]),
        # ``dispatched_at`` identifies this one queue write and is stable when
        # the worker later moves the row to running/done; the mutable status
        # and the whole queue bytes are deliberately not part of the receipt.
        "dispatched_at": str(queue_row.get("dispatched_at") or ""),
        "used_rounds": state["used"],
    }


def _bounded_result(state, baseline, ref, *, resumed):
    receipt = _bounded_receipt(state, baseline)
    return {
        "ok": True,
        "state": "bounded-step-consumed",
        "dispatched": True,
        "task_key": baseline["task_key"],
        "attempt": state["attempt"],
        "used_rounds": state["used"],
        "decision_ref": ref,
        "end_criterion": baseline["end_criterion"],
        "receipt": receipt,
        "receipt_sha256": _digest(json.dumps(
            receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        "resumed": resumed,
    }


def _hex64(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _stage_version(stage):
    """Semantic version of one roadmap stage, stable across status/recovery lines."""
    payload = {
        "number": stage.number,
        "title": stage.title,
        "goal": stage.goal,
        "keys": [
            {"key": item.key, "role": item.role, "depends_on": list(item.depends_on)}
            for item in stage.keys
        ],
        "key_status": dict(sorted(stage.key_status.items())),
    }
    return _digest(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _parse_stop_record(text):
    """The recorded stop fact carried by the rejected halt gate.

    A free-form legacy rejection has no structured record; the caller keeps it
    fail-closed as a human stop with an unknown hard-guard state. A note that
    looks like a JSON record but does not satisfy the schema is refused, never
    silently downgraded to legacy.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        record = json.loads(text)
    except ValueError:
        return None
    if not isinstance(record, dict):
        raise RecoveryBlocked("invalid-stop-record")
    required = {"schema", "halt_origin", "stop_reason", "hard_guard_active",
                "hard_guard_cleared", "hard_guard_cleared_verified"}
    if not required.issubset(record):
        raise RecoveryBlocked("invalid-stop-record")
    _require(type(record["schema"]) is int and record["schema"] == 1,
             "invalid-stop-record")
    _require(record["halt_origin"] in policy.HALT_ORIGINS, "invalid-stop-record")
    _require(isinstance(record["stop_reason"], str) and record["stop_reason"].strip(),
             "invalid-stop-record")
    _require(type(record["hard_guard_active"]) is bool, "invalid-stop-record")
    _require(_tokens(record["hard_guard_cleared"]) or record["hard_guard_cleared"] == [],
             "invalid-stop-record")
    _require(type(record["hard_guard_cleared_verified"]) is bool, "invalid-stop-record")
    return record


def _halt_event(root, stage_number, gate_id):
    events = conductor.timeline.query_events(
        conductor.timeline.timeline_path(root)).events
    matched = [event for event in events
               if event.get("stage") == stage_number
               and gate_id in str(event.get("detail") or "")
               and "rejected" in str(event.get("detail") or "")
               and "halted" in str(event.get("detail") or "")]
    _require(matched, "halt-evidence-missing")
    return matched[-1]


def halted_stage_facts(project_root):
    """Read the one real halted stage, its halt gate and its recorded stop fact.

    The roadmap is the original object. The latest rejected stage-close gate is
    the recorded halt decision; the timeline must carry the matching
    ``rejected -> halted`` event. Nothing here is supplied by a request body.
    """
    root = pathlib.Path(project_root)
    _require(root.is_dir(), "halted-stage-unavailable")
    path = _safe_file(root, roadmap.roadmap_path(root))
    try:
        document = roadmap.load_roadmap(path)
    except (roadmap.RoadmapError, OSError):
        raise RecoveryBlocked("halted-stage-unavailable") from None
    halted = [stage for stage in document.stages if stage.status == "halted"]
    _require(len(halted) == 1, "halted-stage-unverified")
    stage = halted[0]
    directory = root / ".agenticdoc" / "_autopilot" / "gates"
    _require(directory.resolve(strict=False) == directory and directory.is_relative_to(root),
             "halt-evidence-unavailable")
    try:
        candidates = [gate for gate in gates.enumerate(directory)
                      if gate.kind == "stage-close" and gate.stage == stage.number
                      and gate.status == "rejected"]
    except (OSError, ValueError):
        raise RecoveryBlocked("halt-evidence-unavailable") from None
    _require(candidates, "halt-evidence-missing")
    halt_gate = max(candidates, key=lambda gate: (gate.answered_at or "", gate.id))
    event = _halt_event(root, stage.number, halt_gate.id)
    record = _parse_stop_record(halt_gate.note)
    if record is not None:
        origin = record["halt_origin"]
        reason = record["stop_reason"].strip()
        guard_active = record["hard_guard_active"]
        guard_cleared = tuple(record["hard_guard_cleared"])
        guard_verified = record["hard_guard_cleared_verified"]
    else:
        # A gate rejection is a human stop until a structured record proves a
        # technical origin. The unknown guard state keeps it halted for policy.
        origin = "user-stop"
        reason = (halt_gate.note or "").strip() or "stage-close rejected: " + halt_gate.id
        guard_active = None
        guard_cleared = ()
        guard_verified = False
    version = _stage_version(stage)
    gate_sha = _digest(halt_gate.path.read_bytes())
    stop = {
        "stage": stage.number,
        "stage_version": version,
        "halt_gate_id": halt_gate.id,
        "halt_gate_sha256": gate_sha,
        "halt_origin": origin,
        "stop_reason": reason,
        "hard_guard_active": guard_active,
        "hard_guard_cleared": list(guard_cleared),
        "hard_guard_cleared_verified": guard_verified,
        "timeline_seq": event.get("seq"),
    }
    stop["stop_sha256"] = _digest(
        json.dumps(stop, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {
        **stop,
        "title": stage.title,
        "goal": stage.goal,
        "keys": list(stage.key_names),
        "key_status": dict(stage.key_status),
        "halt_gate_note": halt_gate.note,
        "halt_gate_answered_by": halt_gate.answered_by,
    }


def halted_recovery_rows(text, stage_number):
    """Recovery records appended to the original roadmap for one stage."""
    rows = []
    for line in text.splitlines():
        if not line.startswith(_H11_RECOVERY_PREFIX):
            continue
        try:
            row = json.loads(line[len(_H11_RECOVERY_PREFIX):].strip())
        except ValueError:
            raise RecoveryBlocked("invalid-recovery-record") from None
        if not isinstance(row, dict):
            raise RecoveryBlocked("invalid-recovery-record")
        if row.get("stage") != stage_number:
            continue
        _require(row.get("schema") == 1 and isinstance(row.get("decision_ref"), str)
                 and isinstance(row.get("from_version"), str)
                 and _hex64(row.get("to_version")) and _hex64(row.get("stop_sha256")),
                 "invalid-recovery-record")
        rows.append(row)
    return rows


def _h11_history(root, stage_number):
    path = _safe_file(root, roadmap.roadmap_path(root))
    return halted_recovery_rows(path.read_text(encoding="utf-8"), stage_number)


def halted_recovery_matter(key, facts, note, grant_ref):
    """Stable binding shared by the PM's prepared gate and the service."""
    return validity.matter_for(
        key, "halted-stage/" + str(facts["stage"]) + "/" + facts["stage_version"],
        H11_ACTION,
        [
            validity.DependencyState("stage", "structured", {
                "stage": facts["stage"], "stage_version": facts["stage_version"]}),
            validity.DependencyState("stop", "structured", {
                "stop_sha256": facts["stop_sha256"]}),
            validity.DependencyState("note", "structured", note),
            validity.DependencyState("authorization", "ref", grant_ref),
        ],
        matter_kind="gate-action", contract_version="h11-v1",
        authority_required=True,
    )


def _h11_scope(key):
    return (H11_ACTION, "recovery:halted", "key:" + key)


def _h11_bound_request(root, frozen, grant):
    req = json.loads(frozen)
    required = {"schema", "purpose", "project_id", "key", "stage", "stage_version",
                "stop_sha256", "grant_ref", "gate_id", "pm_note", "preparation", "action"}
    _require(set(req) == required and type(req["schema"]) is int and req["schema"] == 1
             and req["purpose"] == H11_PURPOSE and req["action"] == H11_ACTION
             and type(req["stage"]) is int and req["stage"] > 0
             and GATE.fullmatch(req["gate_id"]) and _hex64(req["stage_version"])
             and _hex64(req["stop_sha256"]) and TRIP.fullmatch(req["grant_ref"])
             and isinstance(req["pm_note"], dict),
             "invalid-recovery-request")
    _require(req["project_id"] == wire.project_id_for(root)
             and all(req[name] == grant.get(name) for name in
                     ("project_id", "key", "stage", "grant_ref", "stage_version", "stop_sha256")),
             "grant-binding-mismatch")
    _require(TRIP.fullmatch(str(grant.get("operation_id", ""))), "invalid-operation-id")
    return req


def _h11_request(root, frozen, grant, *, source_bound=False):
    req = _h11_bound_request(root, frozen, grant)
    _require(grant.get("revoked") is False, "preauthorization-expired-or-revoked")
    if not source_bound:
        # A signed operator-host grant has its own expiry; a normal PM binding is
        # the protected authority record itself (revocation is read live), so it
        # has no caller-invented window.
        _require(_stamp(grant.get("recorded_at")) <= _now() < _stamp(grant.get("expires_at")),
                 "preauthorization-expired-or-revoked")
    _require(_tokens(grant.get("scope")), "grant-scope-mismatch")
    if source_bound:
        _require("recovery:halted" in grant["scope"], "grant-scope-mismatch")
    else:
        _require(set(_h11_scope(req["key"])).issubset(set(grant["scope"])),
                 "grant-scope-mismatch")
    _require(_tokens(grant.get("trusted_writers")), "trusted-writers-missing")
    _require(isinstance(grant.get("authority_source"), dict) and grant["authority_source"],
             "authority-source-missing")
    _require(isinstance(grant.get("authority_ref"), str)
             and grant["authority_ref"] in grant["authority_source"],
             "authority-ref-missing")
    _require(isinstance(grant.get("usage_sources"), dict), "usage-source-missing")
    _require(isinstance(grant.get("usage_source"), str) and grant["usage_source"],
             "usage-source-missing")
    _require(isinstance(grant.get("unit"), str) and grant["unit"], "unknown-budget-unit")
    _require(type(grant.get("amount")) is int and grant["amount"] == 1, "unsupported-spend")
    _require(_hex64(grant.get("policy_sha256")), "policy-version-missing")
    rows = [row for row in state.read_index(root) if row["key"] == req["key"]]
    _require(len(rows) == 1 and rows[0]["claim_id"] == grant["claim"]
             and rows[0]["status"] == "active"
             and state.claim_state(grant["claim"]) == state.CLAIM_LIVE, "pm-claim-changed")
    return req


def _h11_sources(grant):
    trusted = tuple(grant["trusted_writers"])
    sources = {}
    for ref, row in grant["authority_source"].items():
        _require(isinstance(row, dict), "invalid-protected-authority")
        parsed, issues = policy.parse_authority_record(row, trusted_writers=trusted)
        _require(not issues and parsed is not None and parsed.authority_ref == ref,
                 "invalid-protected-authority")
        sources[ref] = parsed
    _require(grant["authority_ref"] in sources, "authority-unresolved")
    return sources


def _h11_used_rounds(root, key):
    directory = pathlib.Path(root) / ".agenticdoc" / key / "workers"
    if not directory.is_dir():
        return 0
    labels = [state.parse_task_labels(path) for path in directory.glob("*/task.md")]
    _require(all(label.get("loop") for label in labels), "unverified-budget-source")
    return sum(state.used_rounds([directory]).values())


def _h11_observation(root, req, grant):
    facts = halted_stage_facts(root)
    _require(facts["stage"] == req["stage"]
             and facts["stage_version"] == req["stage_version"]
             and facts["stop_sha256"] == req["stop_sha256"], "stop-fact-changed")
    _require(facts["stop_reason"] == grant.get("reason"), "stop-fact-changed")
    note = req["pm_note"]
    _require(note.get("stop_reason") == facts["stop_reason"], "stop-fact-changed")
    _require(note.get("stage_version") == facts["stage_version"], "stop-fact-changed")
    _require(set(note.get("affected_keys") or ()) == set(facts["keys"]),
             "affected-keys-changed")
    _require(note.get("planned_action") in (None, H11_ACTION), "invalid-stop-action")
    cfg = config.load_config(root)
    _require(cfg.get("enabled") is True and cfg.get("paused") is False,
             "automation-disabled-or-paused")
    path = _safe_file(root, policy.policy_path(root))
    raw = path.read_bytes()
    _require(_digest(raw) == grant["policy_sha256"], "policy-version-changed")
    load = policy.parse_policy(json.loads(raw))
    _require(load.usable and load.policy is not None and load.policy.recovery is not None
             and not load.recovery_issues, "recovery-policy-unavailable")
    limit = load.policy.limit_for(grant["unit"])
    _require(limit is not None and limit.unit == "round", "unknown-budget-unit")
    _require(grant["usage_sources"].get(limit.usage_source)
             == {"kind": "task-card-rounds", "unit": "round"},
             "unverified-budget-source")
    used = _h11_used_rounds(root, req["key"])
    _require(used <= limit.limit, "hard-budget-exhausted")
    _require(policy.check_spend(load, unit=grant["unit"], amount=1,
                                usage={grant["unit"]: used}).allowed,
             "hard-budget-exhausted")
    bounded = _bounded_baseline(root, req["key"], note, used)
    remaining = limit.limit - used
    _require(note.get("residual_budget", {}).get(grant["unit"]) == remaining,
             "residual-budget-mismatch")
    sources = _h11_sources(grant)
    trusted = tuple(grant["trusted_writers"])
    gate_scope = ("key:" + req["key"], "action:gate-approve")
    original = policy.evaluate_gate(
        load, choice="approve",
        hard_checks={"halt-verified": True, "stop-record-verified": True,
                     "policy-version-verified": True, "pm-claim-live": True},
        automation_enabled=True, required_scope=gate_scope,
        authority_source=sources, trusted_writers=trusted)
    _require(original.allowed, "original-authority-missing")
    verdict = policy.evaluate_halted_recovery(
        load,
        request={
            "stage_halted": True, "halt_origin": facts["halt_origin"],
            "hard_guard_active": facts["hard_guard_active"],
            "hard_guard_cleared": list(facts["hard_guard_cleared"]),
            "hard_guard_cleared_verified": facts["hard_guard_cleared_verified"],
            "choice": "approve", "required_scope": ["recovery:halted"],
            "note": note,
        },
        usage={grant["unit"]: used}, authority_source=sources, trusted_writers=trusted)
    _require(verdict.allowed, "recovery-policy-refused:" + ",".join(
        issue.code for issue in verdict.reasons))
    gate_path = _safe_file(
        root, root / ".agenticdoc/_autopilot/gates" / (req["gate_id"] + ".md"))
    gate = gates.parse(gate_path)
    matter = halted_recovery_matter(req["key"], facts, note, req["grant_ref"])
    _require(gate.key == req["key"] and gate.kind == "stalled"
             and gate.matter_ref == matter.matter_key
             and gate.substantive_version == matter.substantive_version
             and gate.pm_note is not None and json.loads(gate.pm_note) == note,
             "prepared-gate-mismatch")
    material = {
        "gate_background": gate.question,
        "current_state": "stage " + str(facts["stage"]) + " halted ("
                         + facts["halt_origin"] + "): " + facts["stop_reason"],
        "condition_evidence": [
            "halt gate " + facts["halt_gate_id"] + " sha256=" + facts["halt_gate_sha256"],
            "stage version " + facts["stage_version"],
            "cumulative " + grant["unit"] + "=" + str(used) + " of " + str(limit.limit),
        ],
        # The model-facing note is the gate contract; the recovery note itself
        # stays bound to the prepared gate and is re-read from the real object.
        "pm_note": {
            "subject": "recover halted stage " + str(facts["stage"])
                       + " after eliminating the recorded stop",
            "planned_action": H11_ACTION,
            "basis": {
                "goal": str(note["target_plan"]),
                "evidence": "; ".join(str(item) for item in note["elimination_evidence"]),
                "budget": "residual " + grant["unit"] + "="
                          + str(note["residual_budget"][grant["unit"]])
                          + "; cumulative " + grant["unit"] + "=" + str(used)
                          + " of " + str(limit.limit),
                "authority": str(note["authority_ref"]),
            },
        },
    }
    if bounded is not None:
        material["condition_evidence"].extend([
            "bounded action " + bounded["task_key"],
            "bounded card " + bounded["card_sha256"],
        ])
        material["pm_note"]["basis"]["evidence"] += (
            "; bounded action dispatch one " + bounded["task_key"]
            + " round (card sha256=" + bounded["card_sha256"]
            + ", face=" + ",".join(bounded["write_face"])
            + ", base attempt=" + str(bounded["base_attempt"])
            + ", amount=" + str(bounded["amount"])
            + ", end: " + bounded["end_criterion"] + ")")
    _require(not decision_points.prepared_request_issues(
        DP, material, req["preparation"], actor_role="pm"), "invalid-preparation")
    return facts, gate, material, sources, used, load, bounded


def _verify_h11_answer(gate, req, facts, grant, choice, basis, ref):
    matter = halted_recovery_matter(req["key"], facts, req["pm_note"], req["grant_ref"])
    _require(gate.transport == "answered" and gate.business == choice
             and gate.decision_ref == ref and gate.model_basis == basis
             and gate.matter_ref == matter.matter_key
             and gate.substantive_version == matter.substantive_version
             and gate.answered_by == grant["claim"] and gate.effect in _GATE_EFFECTS,
             "gate-answer-mismatch")
    return gate


def _prepare_halted_recovery_core(root, frozen, grant, *, source_bound=False):
    try:
        root = pathlib.Path(root)
        req = _h11_request(root, frozen, grant, source_bound=source_bound)
        ref = DP + ":" + grant["operation_id"]
        history = _h11_history(root, req["stage"])
        _require(not history
                 or any(row.get("decision_ref") == ref for row in history),
                 "recovery-already-recorded")
        facts, gate, material, _sources, _used, _load, bounded = _h11_observation(
            root, req, grant)[:7]
        extra = {"bounded_step": bounded} if bounded is not None else {}
        client, store = _client_store(root)
        logical = grant["operation_id"]
        ref = DP + ":" + logical
        meta = lifecycle.DecisionMeta.create(req["key"], initiator_role="pm",
                                             logical_id=logical)
        actor = ("system", "pm:" + grant["claim"])
        _, rows = _facts(store, logical, req["key"])
        recorded = _recorded_request(rows, ref, req["key"], store, material,
                                     req["preparation"])
        if recorded is not None:
            _require(recorded.get("business_decisions") == 1,
                     "previous-request-refused")
            choice = recorded.get("choice")
            basis_id = recorded.get("basis_id")
            basis_text = recorded.get("basis_text")
            _require(isinstance(choice, str) and isinstance(basis_id, str)
                     and isinstance(basis_text, str), "recorded-decision-incomplete")
            if gate.transport == "pending" and gate.effect == "not-started":
                _answer_gate(root, gate, req, recorded, grant, ref)
            else:
                _verify_h11_answer(gate, req, facts, grant, choice, basis_text, ref)
            if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "consumed"
                       and row.get("decision_id") == ref and row.get("answer") == choice
                       for row in rows):
                _require(lifecycle.record_consumed(
                    store, meta, decision_id=ref, dp=DP, answer=choice, actor=actor,
                    event_id="h11-received-" + logical).recorded, "answer-not-recorded")
            return {"ok": True, "choice": choice, "basis_id": basis_id,
                    "basis_text": basis_text, "decision_ref": ref,
                    "before_sha256": _digest(
                        _safe_file(root, roadmap.roadmap_path(root)).read_bytes()),
                    "matter_ref": gate.matter_ref,
                    "substantive_version": gate.substantive_version,
                    "stage": req["stage"], "stage_version": facts["stage_version"],
                    "stop_sha256": facts["stop_sha256"], "resumed": True, **extra}
        _require(gate.transport == "pending" and gate.effect == "not-started",
                 "gate-already-answered")
        _require(not any(row.get("kind") == "lifecycle" and row.get("lifecycle") in
                         {"executed", "settled"} for row in rows),
                 "checkpoint-inconsistent")
        _require(lifecycle.record_start(store, meta, decision_id=ref, actor=actor).recorded,
                 "start-not-recorded")
        _require(lifecycle.record_note(store, meta, decision_id=ref, pm_note=gate.pm_note,
                 prepared_at=req["preparation"]["prepared_at"], actor=actor).recorded,
                 "note-not-recorded")
        result = client.request_prepared(DP, material, req["preparation"], actor_role="pm",
                                         logical_id=logical,
                                         replay_check=lambda _dp, _lid: False)
        _require(lifecycle.record_request(store, meta, decision_id=ref, result=result,
                 material=material, preparation=req["preparation"], actor=actor).recorded,
                 "request-not-recorded")
        _require(result.get("available") is True and result.get("business_decisions") == 1,
                 "no-valid-gate-decision")
        _answer_gate(root, gate, req, result, grant, ref)
        _require(lifecycle.record_consumed(store, meta, decision_id=ref, dp=DP,
                 answer=result["choice"], actor=actor,
                 event_id="h11-received-" + logical).recorded, "answer-not-recorded")
        return {"ok": True, "choice": result["choice"], "basis_id": result["basis_id"],
                "basis_text": result["basis_text"], "decision_ref": ref,
                "before_sha256": _digest(
                    _safe_file(root, roadmap.roadmap_path(root)).read_bytes()),
                "matter_ref": gate.matter_ref,
                "substantive_version": gate.substantive_version,
                "stage": req["stage"], "stage_version": facts["stage_version"],
                "stop_sha256": facts["stop_sha256"], "resumed": False, **extra}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


def prepare_halted_recovery(root, frozen, grant):
    """Called in a reserved, bound service operation; never by the normal tick."""
    if not _authorized(root, "h11.prepare", frozen, grant):
        return {"ok": False, "reason": "operator-host-required"}
    return _prepare_halted_recovery_core(root, frozen, grant)


def _h11_settle_non_approve(store, meta, ref, logical, actor, rows, choice):
    follow_up = _H11_FOLLOW_UP.get(choice)
    outcome = "pending" if follow_up else "inconclusive"
    reason = ("stage remains halted; prepared PM follow-up " + follow_up
              if follow_up else "stage recovery rejected; no legacy closure")
    if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "settled"
               for row in rows):
        _require(lifecycle.record_settled(
            store, meta, decision_id=ref, dp=DP, outcome=outcome, reason=reason,
            actor=actor, event_id="h11-handoff-" + logical).recorded,
            "settlement-not-recorded")
    return {"ok": False, "reason": "stage-remains-halted", "choice": choice,
            "decision_ref": ref, "follow_up": follow_up}


def _record_h11_receipt(store, meta, ref, logical, actor, rows, receipt):
    if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "executed"
               for row in rows):
        _require(lifecycle.record_executed(
            store, meta, decision_id=ref, dp=DP, action="record", result=receipt,
            reason=H11_ACTION, actor=actor, event_id="h11-executed-" + logical).recorded,
            "execution-receipt-unknown")
    if not any(row.get("kind") == "lifecycle" and row.get("lifecycle") == "settled"
               for row in rows):
        _require(lifecycle.record_settled(
            store, meta, decision_id=ref, dp=DP, outcome="ok", reason=receipt,
            actor=actor, event_id="h11-settled-" + logical).recorded,
            "settlement-unknown")


def _append_h11_recovery(text, record):
    line = _H11_RECOVERY_PREFIX + json.dumps(
        record, sort_keys=True, separators=(",", ":")) + "\n"
    return text if text.endswith("\n") else text + "\n", line


def _apply_halted_recovery_core(root, frozen, grant, decision_result, *, source_bound=False):
    try:
        root = pathlib.Path(root)
        req = _h11_request(root, frozen, grant, source_bound=source_bound)
        logical = grant["operation_id"]
        ref = DP + ":" + logical
        _require(decision_result.get("ok") is True and TRIP.fullmatch(logical)
                 and decision_result.get("decision_ref") == ref, "unrelated-decision")
        _, store = _client_store(root)
        meta = lifecycle.DecisionMeta.create(req["key"], initiator_role="pm",
                                             logical_id=logical)
        actor = ("system", "pm:" + grant["claim"])
        _, rows = _facts(store, logical, req["key"])
        requests = [row for row in rows if row.get("kind") == "request"
                    and row.get("decision_id") == ref]
        _require(len(requests) == 1, "decision-record-mismatch")
        request = requests[0]
        _require(request.get("business_decisions") == 1
                 and request.get("basis_id") == decision_result.get("basis_id")
                 and request.get("basis_text") == decision_result.get("basis_text")
                 and request.get("choice") == decision_result.get("choice")
                 and any(row.get("lifecycle") == "consumed"
                         and row.get("answer") == request["choice"] for row in rows),
                 "decision-record-mismatch")
        choice = request["choice"]
        basis_text = request["basis_text"]
        if choice != "approve":
            return _h11_settle_non_approve(store, meta, ref, logical, actor, rows, choice)
        matter = halted_recovery_matter(req["key"], halted_stage_facts(root),
                                        req["pm_note"], req["grant_ref"])
        matter_lock = root / ".mw" / ("matter-"
                                       + hashlib.sha256(matter.matter_key.encode()).hexdigest()
                                       + ".lock")
        roadmap_lock = root / ".mw" / "roadmap.lock"
        with gate_effects._lock(matter_lock):
            with gate_effects._lock(roadmap_lock):
                _h11_request(root, frozen, grant, source_bound=source_bound)
                path = _safe_file(root, roadmap.roadmap_path(root))
                before = path.read_bytes()
                text = before.decode("utf-8")
                history = halted_recovery_rows(text, req["stage"])
                recorded = [row for row in history if row.get("decision_ref") == ref]
                _require(not history or recorded, "recovery-already-recorded")
                gate_path = _safe_file(
                    root, root / ".agenticdoc/_autopilot/gates" / (req["gate_id"] + ".md"))
                if recorded:
                    facts = halted_stage_facts(root)
                    gate = gates.parse(gate_path)
                    _verify_h11_answer(gate, req, facts, grant, choice, basis_text, ref)
                    with _recovery_gate_lock(root):
                        current = gates.parse(gate_path)
                        _verify_h11_answer(current, req, facts, grant, choice, basis_text, ref)
                        if current.effect != "applied":
                            gate_effects._replace_effect(current, "applied")
                    receipt = _digest(before)
                    _record_h11_receipt(store, meta, ref, logical, actor, rows, receipt)
                    return {"ok": True, "state": "recovered", "effect": "applied",
                            "choice": choice, "stage": req["stage"], "decision_ref": ref,
                            "receipt": receipt, "receipt_sha256": receipt,
                            "version": recorded[0]["to_version"], "resumed": True}
                facts, gate, material, _sources, _used, _load, bounded = _h11_observation(
                    root, req, grant)
                _verify_h11_answer(gate, req, facts, grant, choice, basis_text, ref)
                _require(_digest(before) == decision_result.get("before_sha256")
                         and gate.matter_ref == decision_result.get("matter_ref")
                         and gate.substantive_version
                         == decision_result.get("substantive_version"),
                         "recovery-basis-changed")
                _require(not decision_points.prepared_request_issues(
                    DP, material, req["preparation"], actor_role="pm", choice=choice,
                    basis_id=decision_result["basis_id"]), "prepared-basis-changed")
                if gate.effect in {"in-progress", "unknown"}:
                    if gate.effect == "in-progress":
                        with _recovery_gate_lock(root):
                            current = gates.parse(gate_path)
                            if current.effect == "in-progress" and not halted_recovery_rows(
                                    path.read_text(encoding="utf-8"), req["stage"]):
                                gate_effects._replace_effect(current, "unknown")
                    return {"ok": False, "reason": "recovery-effect-unknown",
                            "state": "unknown", "effect": "unknown",
                            "decision_ref": ref}
                _require(gate.effect not in {"blocked", "failed"}, "gate-effect-refused")
                if gate.effect == "applied":
                    return {"ok": False, "reason": "recovery-effect-unknown",
                            "state": "unknown", "effect": "applied",
                            "decision_ref": ref}
                _require(gate.effect == "not-started", "recovery-effect-unknown")
                with _recovery_gate_lock(root):
                    current = gates.parse(gate_path)
                    _verify_h11_answer(current, req, facts, grant, choice, basis_text, ref)
                    _require(current.effect == "not-started", "recovery-effect-unknown")
                    gate_effects._replace_effect(current, "in-progress")
                previous = history[-1]["to_version"] if history else facts["stage_version"]
                to_version = _digest((previous + ":" + ref + ":"
                                      + facts["stop_sha256"]).encode("utf-8"))
                event = {
                    "schema": 1, "stage": req["stage"],
                    "halt_origin": facts["halt_origin"],
                    "stop_reason": facts["stop_reason"],
                    "halt_gate": facts["halt_gate_id"],
                    "stop_sha256": facts["stop_sha256"],
                    "stage_version": facts["stage_version"],
                    "from_version": previous, "to_version": to_version,
                    "decision_ref": ref, "grant_ref": req["grant_ref"],
                    "consumed": {grant["unit"]: _h11_used_rounds(root, req["key"])},
                    "residual": dict(req["pm_note"]["residual_budget"]),
                    "authority_ref": grant["authority_ref"],
                    "unit": grant["unit"],
                    "recovery_gate": req["gate_id"],
                    "at": _now().isoformat(),
                }
                if bounded is not None:
                    event["bounded_step"] = bounded
                base, line = _append_h11_recovery(text, event)
                new_text = base + line
                parsed = roadmap.parse_roadmap(new_text, strict=False)
                stages = [stage for stage in parsed.stages if stage.number == req["stage"]]
                _require(len(stages) == 1 and stages[0].status == "halted",
                         "recovery-write-unverified")
                _require(len(halted_recovery_rows(new_text, req["stage"]))
                         == len(history) + 1, "recovery-write-unverified")
                gates._write_atomic(path, new_text)
                after = path.read_bytes()
                _require(after == new_text.encode("utf-8"), "recovery-write-unverified")
                receipt = _digest(after)
                with _recovery_gate_lock(root):
                    current = gates.parse(gate_path)
                    _verify_h11_answer(current, req, facts, grant, choice, basis_text, ref)
                    _require(current.effect == "in-progress", "gate-changed-during-recovery")
                    gate_effects._replace_effect(current, "applied")
                _record_h11_receipt(store, meta, ref, logical, actor, rows, receipt)
                return {"ok": True, "state": "recovered", "effect": "applied",
                        "choice": choice, "stage": req["stage"], "decision_ref": ref,
                        "receipt": receipt, "receipt_sha256": receipt,
                        "version": to_version, "resumed": False}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


def apply_halted_recovery(root, frozen, grant, decision_result):
    """One service-serialized redemption after a real decision. No model on replay."""
    if not _authorized(root, "h11.apply", frozen, grant):
        return {"ok": False, "reason": "operator-host-required"}
    return _apply_halted_recovery_core(root, frozen, grant, decision_result)

# ── Normal PM entry: the protected authority source is the only grant ────────

_PM_SUBMISSION_FIELDS = frozenset(
    {"stage", "stage_version", "gate_id", "pm_note", "preparation"}
)


def pm_halted_recovery_ref(facts, note):
    """Stable binding id the PM's prepared gate and the handler share.

    This is a reference to the matter (stop fact + target version + note), not a
    new authorization. The authorization itself is the protected authority
    record named by ``note['authority_ref']``.
    """
    payload = {
        "stage": facts["stage"],
        "stage_version": facts["stage_version"],
        "stop_sha256": facts["stop_sha256"],
        "note": note,
    }
    return _digest(json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode("utf-8"))[:32]


def _authority_record_payload(record):
    """Lossless shape of an already-parsed source record, for the policy seam."""
    return {
        "authority_ref": record.authority_ref,
        "kind": record.kind,
        "scope": list(record.scope),
        "writer": record.writer,
        "revoked": record.revoked,
        "recorded_at": record.recorded_at,
        "supersedes": list(record.supersedes),
    }


def _pm_h11_binding(root, key, submission, authority):
    """Bind the PM-prepared note/target to the real stop facts and native source.

    No caller value becomes authority: the record, its scope, the trusted
    writers, the policy digest and the usage descriptor all come from the
    protected observation. The submission only selects the prepared gate, the
    note and the target version.
    """
    facts = halted_stage_facts(root)
    _require(submission["stage"] == facts["stage"]
             and submission["stage_version"] == facts["stage_version"],
             "stop-fact-changed")
    note = submission["pm_note"]
    _require(isinstance(note, dict), "invalid-pm-submission")
    _require(note.get("stage_version") == facts["stage_version"]
             and note.get("stop_reason") == facts["stop_reason"], "stop-fact-changed")
    authority_ref = note.get("authority_ref")
    _require(isinstance(authority_ref, str) and authority_ref, "authority-ref-missing")
    record = authority.records.get(authority_ref)
    _require(record is not None, "authority-unresolved")
    _require(not record.revoked, "authority-revoked")
    _require("recovery:halted" in record.scope, "grant-scope-mismatch")

    path = _safe_file(root, policy.policy_path(root))
    raw = path.read_bytes()
    digest = _digest(raw)
    _require(not authority.policy_sha256 or authority.policy_sha256 == digest,
             "policy-version-changed")
    load = policy.parse_policy(json.loads(raw))
    _require(load.usable and load.policy is not None
             and load.policy.recovery is not None and not load.recovery_issues,
             "recovery-policy-unavailable")
    limits = [limit for limit in load.policy.hard_limits if limit.unit == "round"]
    _require(len(limits) == 1, "unknown-budget-unit")
    limit = limits[0]
    usage = authority.usage_sources.get(limit.usage_source)
    _require(usage is not None and usage.kind == "task-card-rounds"
             and usage.unit == "round", "unverified-budget-source")

    grant_ref = pm_halted_recovery_ref(facts, note)
    matter = halted_recovery_matter(key, facts, note, grant_ref)
    operation_id = _digest(
        ("pm-halted:" + matter.matter_key + ":" + matter.substantive_version).encode("utf-8")
    )[:32]
    grant = {
        "project_id": authority.project_id,
        "key": key,
        "stage": facts["stage"],
        "stage_version": facts["stage_version"],
        "stop_sha256": facts["stop_sha256"],
        "grant_ref": grant_ref,
        "operation_id": operation_id,
        "claim": authority.claim_id,
        "revoked": record.revoked,
        "authority_source": {name: _authority_record_payload(item)
                             for name, item in authority.records.items()},
        "trusted_writers": list(authority.trusted_writers),
        "usage_sources": {name: {"kind": item.kind, "unit": item.unit}
                          for name, item in authority.usage_sources.items()},
        "authority_ref": authority_ref,
        "scope": list(record.scope),
        "reason": facts["stop_reason"],
        "unit": limit.unit,
        "amount": 1,
        "usage_source": limit.usage_source,
        "policy_sha256": digest,
    }
    request = {
        "schema": 1,
        "purpose": H11_PURPOSE,
        "project_id": authority.project_id,
        "key": key,
        "stage": facts["stage"],
        "stage_version": facts["stage_version"],
        "stop_sha256": facts["stop_sha256"],
        "grant_ref": grant_ref,
        "gate_id": submission["gate_id"],
        "pm_note": note,
        "preparation": submission["preparation"],
        "action": H11_ACTION,
    }
    frozen = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return facts, grant, frozen, matter


def run_pm_halted_recovery(project_root, key, submission):
    """Normal PM entry for one bounded halted-stage recovery.

    ``submission`` carries only the PM-prepared gate id, note, preparation and
    target version. The live claim, authority records, trusted writers, policy
    digest, cumulative hard budget and stop facts are re-read from their real
    objects here; a caller cannot pass a grant, records or ``checks=true``.
    """
    try:
        root = pathlib.Path(project_root)
        _require(isinstance(submission, dict)
                 and set(submission) == _PM_SUBMISSION_FIELDS, "invalid-pm-submission")
        _require(isinstance(key, str) and key, "invalid-pm-submission")
        authority = operator_authority.read_pm_authority(root, key)
        operator_authority.verify_pm_authority(authority)
        _facts_now, grant, frozen, _matter = _pm_h11_binding(root, key, submission, authority)
        prepared = _prepare_halted_recovery_core(root, frozen, grant, source_bound=True)
        if prepared.get("ok") is not True:
            return prepared
        # The source is re-read after the decision and immediately before the
        # effect: a revoked record or any material change refuses here.
        operator_authority.verify_pm_authority(authority)
        applied = _apply_halted_recovery_core(root, frozen, grant, prepared,
                                              source_bound=True)
        if applied.get("ok") is True:
            applied["view"] = read_halted_recovery_view(root, key)
        return applied
    except (operator_authority.AuthorityError, RecoveryBlocked) as exc:
        return {"ok": False, "reason": str(exc)}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


def read_halted_recovery_view(project_root, key):
    """Read-only bounded view of the latest recorded recovery for one stage.

    The conductor may use ``effective_version``/``remaining`` for its next tick,
    but the view always reports ``stage_status: halted``: it is a limit on one
    observation, never a claim that the stage resumed. Every read re-checks the
    original stop fact, the stage version chain, the current protected authority
    (revocation included) and the real cumulative hard budget.
    """
    try:
        root = pathlib.Path(project_root)
        _require(isinstance(key, str) and key, "invalid-pm-submission")
        facts = halted_stage_facts(root)
        rows = _h11_history(root, facts["stage"])
        _require(rows, "no-recorded-recovery")
        row = rows[-1]
        _require(row.get("stage_version") == facts["stage_version"]
                 and row.get("halt_origin") == facts["halt_origin"],
                 "recovery-basis-changed")
        _require(row["stop_sha256"] == facts["stop_sha256"], "stop-fact-changed")
        previous = rows[-2]["to_version"] if len(rows) > 1 else facts["stage_version"]
        _require(row["from_version"] == previous, "recovery-chain-broken")
        authority_ref = row.get("authority_ref")
        _require(isinstance(authority_ref, str) and authority_ref,
                 "recovery-authority-unverified")
        authority = operator_authority.read_pm_authority(root, key)
        operator_authority.verify_pm_authority(authority)
        record = authority.records.get(authority_ref)
        _require(record is not None, "authority-unresolved")
        _require(not record.revoked, "authority-revoked")
        _require("recovery:halted" in record.scope, "grant-scope-mismatch")
        if row["halt_origin"] in policy._HUMAN_HALT_ORIGINS:
            _require(record.kind in policy.HUMAN_AUTHORITY_KINDS
                     and "recovery:user-stop" in record.scope,
                     "user-stop-requires-explicit-authorization")
        raw = _safe_file(root, policy.policy_path(root)).read_bytes()
        _require(not authority.policy_sha256 or authority.policy_sha256 == _digest(raw),
                 "policy-version-changed")
        load = policy.parse_policy(json.loads(raw))
        _require(load.usable and load.policy is not None
                 and load.policy.recovery is not None and not load.recovery_issues,
                 "recovery-policy-unavailable")
        rule = load.policy.recovery
        _require(rule.authority_ref == authority_ref
                 or rule.authority_ref in record.supersedes,
                 "recovery-authority-unrelated")
        consumed = row.get("consumed")
        _require(isinstance(consumed, dict) and consumed, "recovery-usage-missing")
        current = {}
        remaining = {}
        for unit, at_recovery in consumed.items():
            limit = load.policy.limit_for(unit)
            _require(limit is not None and limit.unit == "round", "unknown-budget-unit")
            usage = authority.usage_sources.get(limit.usage_source)
            _require(usage is not None and usage.kind == "task-card-rounds"
                     and usage.unit == "round", "unverified-budget-source")
            used = _h11_used_rounds(root, key)
            _require(type(at_recovery) is int and used >= at_recovery,
                     "recovery-usage-lost")
            _require(used <= limit.limit, "hard-budget-exhausted")
            current[unit] = used
            remaining[unit] = limit.limit - used
        return {
            "ok": True,
            "state": "bounded-recovery",
            "recovery_scope": "one-observation",
            "stage": facts["stage"],
            "stage_status": "halted",
            "from_version": row["from_version"],
            "effective_version": row["to_version"],
            "decision_ref": row["decision_ref"],
            "halt_origin": row["halt_origin"],
            "stop": {
                "stage_version": facts["stage_version"],
                "stop_sha256": facts["stop_sha256"],
                "stop_reason": facts["stop_reason"],
                "halt_gate_id": facts["halt_gate_id"],
                "halt_gate_sha256": facts["halt_gate_sha256"],
            },
            "authority_ref": authority_ref,
            "authority_kind": record.kind,
            "consumed": dict(consumed),
            "current_consumed": current,
            "residual_at_recovery": dict(row.get("residual") or {}),
            "remaining": remaining,
            "observation_conditions": list(rule.observation_conditions),
            "stop_conditions": list(rule.stop_conditions),
            "recorded_at": row.get("at"),
        }
    except (operator_authority.AuthorityError, RecoveryBlocked) as exc:
        return {"ok": False, "reason": str(exc)}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)


def consume_bounded_halted_step(project_root, key):
    """Execute at most one real dispatch round from an approved H11 note.

    The note's ``bounded_action`` is only a target description: the live claim,
    protected authority, policy digest, cumulative hard budget and the original
    task/card/queue are re-read here. The action reuses the production
    ``autopilot.dispatch.dispatch`` writer, so the original task.md and queue
    row change and ``used_rounds`` grows by exactly one. A repeated call only
    inspects the real queue/task and the original lifecycle receipts; it never
    asks a model, dispatches a second round or resets usage. A crash window
    between the task.md write and the queue write is reported as unknown and is
    never "fixed" by redispatching. The roadmap stage stays halted.
    """
    try:
        root = pathlib.Path(project_root)
        _require(isinstance(key, str) and bool(_BOUNDED_KEY.fullmatch(key)),
                 "invalid-pm-submission")
        authority = operator_authority.read_pm_authority(root, key)
        operator_authority.verify_pm_authority(authority)
        facts = halted_stage_facts(root)
        rows = _h11_history(root, facts["stage"])
        _require(rows, "no-recorded-recovery")
        row = rows[-1]
        _require(row.get("stage_version") == facts["stage_version"]
                 and row.get("halt_origin") == facts["halt_origin"]
                 and row.get("stop_sha256") == facts["stop_sha256"],
                 "recovery-basis-changed")
        previous = rows[-2]["to_version"] if len(rows) > 1 else facts["stage_version"]
        _require(row.get("from_version") == previous, "recovery-chain-broken")
        authority_ref = row.get("authority_ref")
        _require(isinstance(authority_ref, str) and authority_ref,
                 "recovery-authority-unverified")
        record = authority.records.get(authority_ref)
        _require(record is not None, "authority-unresolved")
        _require(not record.revoked, "authority-revoked")
        _require("recovery:halted" in record.scope, "grant-scope-mismatch")
        if row.get("halt_origin") in policy._HUMAN_HALT_ORIGINS:
            _require(record.kind in policy.HUMAN_AUTHORITY_KINDS
                     and "recovery:user-stop" in record.scope,
                     "user-stop-requires-explicit-authorization")
        raw = _safe_file(root, policy.policy_path(root)).read_bytes()
        _require(not authority.policy_sha256
                 or authority.policy_sha256 == _digest(raw),
                 "policy-version-changed")
        load = policy.parse_policy(json.loads(raw))
        _require(load.usable and load.policy is not None
                 and load.policy.recovery is not None and not load.recovery_issues,
                 "recovery-policy-unavailable")
        rule = load.policy.recovery
        _require(rule.authority_ref == authority_ref
                 or rule.authority_ref in record.supersedes,
                 "recovery-authority-unrelated")
        limit = load.policy.limit_for(str(row.get("unit") or "round"))
        _require(limit is not None and limit.unit == "round", "unknown-budget-unit")
        usage = authority.usage_sources.get(limit.usage_source)
        _require(usage is not None and usage.kind == "task-card-rounds"
                 and usage.unit == "round", "unverified-budget-source")
        used = _h11_used_rounds(root, key)
        _require(used <= limit.limit, "hard-budget-exhausted")

        baseline = row.get("bounded_step")
        _require(isinstance(baseline, dict), "bounded-action-missing")
        _require(baseline.get("base_used") == (row.get("consumed") or {}).get(limit.unit),
                 "recovery-usage-lost")
        gate_id = row.get("recovery_gate")
        _require(isinstance(gate_id, str) and GATE.fullmatch(gate_id),
                 "bounded-recovery-gate-missing")
        gate_path = _safe_file(
            root, root / ".agenticdoc/_autopilot/gates" / (gate_id + ".md"))
        gate = gates.parse(gate_path)
        _require(gate.transport == "answered" and gate.business == "approve"
                 and gate.decision_ref == row.get("decision_ref")
                 and gate.effect == "applied", "bounded-recovery-gate-unverified")
        try:
            note = json.loads(gate.pm_note) if gate.pm_note else None
        except ValueError:
            note = None
        action = _bounded_action(note)
        _require(action is not None, "bounded-action-missing")
        _require(all(action[name] == baseline.get(name)
                     for name in _BOUNDED_ACTION_FIELDS), "bounded-action-changed")

        decision_ref = row.get("decision_ref")
        logical = decision_ref.partition(":")[2] if isinstance(decision_ref, str) else ""
        _require(isinstance(decision_ref, str) and decision_ref.startswith(DP + ":")
                 and TRIP.fullmatch(logical), "recovery-decision-unverified")
        _client, store = _client_store(root)
        meta = lifecycle.DecisionMeta.create(key, initiator_role="pm",
                                             logical_id=logical)
        actor = ("system", "pm:" + authority.claim_id)
        lock = root / ".mw" / ("h11-bounded-"
                                + hashlib.sha256(
                                    (key + ":" + decision_ref).encode("utf-8")
                                ).hexdigest()[:32] + ".lock")
        ordered = {**baseline, "at": row.get("at")}
        with gate_effects._lock(lock):
            operator_authority.verify_pm_authority(authority)
            facts_now = halted_stage_facts(root)
            _require(facts_now["stage"] == facts["stage"]
                     and facts_now["stage_version"] == facts["stage_version"]
                     and facts_now["stop_sha256"] == facts["stop_sha256"],
                     "recovery-basis-changed")
            history_now = _h11_history(root, facts_now["stage"])
            _require(history_now
                     and history_now[-1].get("decision_ref") == decision_ref,
                     "recovery-superseded")
            _require(_digest(_safe_file(root, policy.policy_path(root)).read_bytes())
                     == _digest(raw), "policy-version-changed")
            gate_now = gates.parse(gate_path)
            _require(gate_now.transport == "answered" and gate_now.business == "approve"
                     and gate_now.decision_ref == decision_ref
                     and gate_now.effect == "applied",
                     "bounded-recovery-gate-unverified")
            try:
                note_now = json.loads(gate_now.pm_note) if gate_now.pm_note else None
            except ValueError:
                note_now = None
            action_now = _bounded_action(note_now)
            _require(action_now is not None, "bounded-action-missing")
            _require(all(action_now[name] == baseline.get(name)
                         for name in _BOUNDED_ACTION_FIELDS),
                     "bounded-action-changed")
            current = _bounded_evaluate(root, key, ordered, limit)
            if current["state"] == "dispatched":
                _record_bounded_receipt(
                    store, meta, decision_ref, logical, actor,
                    _bounded_receipt(current, baseline))
                return _bounded_result(current, baseline, decision_ref, resumed=True)
            if current["state"] != "pending":
                return {"ok": False, "reason": "bounded-step-unknown",
                        "state": "unknown", "task_key": baseline["task_key"],
                        "decision_ref": decision_ref}
            _require(policy.check_spend(
                load, unit=limit.unit, amount=1,
                usage={limit.unit: current["used"]}).allowed,
                "hard-budget-exhausted")
            _require(current["used"] == baseline["base_used"],
                     "bounded-step-unknown")
            if current["rows"]:
                _require(current["rows"][0]["status"]
                         in mw_common.RUN_TERMINAL_STATUSES,
                         "bounded-target-in-flight")
            card_info = dispatch_writer.dispatch_card(root, key, baseline["stem"])
            prompt = str((card_info or {}).get("requirements") or "").strip()
            if not prompt:
                prompt = "Continue the original bounded task round."
            prompt += "\n\nEnd this bounded round when: " + baseline["end_criterion"]
            dispatched = dispatch_writer.dispatch(
                root, key, baseline["stem"], baseline["task_type"], prompt,
                loop=baseline["loop"], attempt=baseline["base_attempt"] + 1)
            if dispatched.ok is not True:
                return {"ok": False, "reason": "bounded-dispatch-refused",
                        "detail": dispatched.reason,
                        "task_key": baseline["task_key"]}
            after = _bounded_evaluate(root, key, ordered, limit)
            if after["state"] != "dispatched" or dispatched.row_verified is not True:
                return {"ok": False, "reason": "bounded-step-unknown",
                        "state": "unknown", "task_key": baseline["task_key"],
                        "decision_ref": decision_ref}
            _record_bounded_receipt(
                store, meta, decision_ref, logical, actor,
                _bounded_receipt(after, baseline))
            return _bounded_result(after, baseline, decision_ref, resumed=False)
    except (operator_authority.AuthorityError, RecoveryBlocked) as exc:
        return {"ok": False, "reason": str(exc)}
    except (OSError, ValueError, TypeError, AttributeError, KeyError, RuntimeError) as exc:
        return _refuse(exc)
