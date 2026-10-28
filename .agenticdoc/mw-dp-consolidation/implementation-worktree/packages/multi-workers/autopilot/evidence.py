"""evidence.py - per-gate evidence snapshot sidecar + provenance resolution.

Task T-06 / AC-029 (key ``mw-autopilot-slot-capacity``).  Standalone: this
module owns no conductor state and is not wired into the tick yet (that is
T-07); it is a pure toolkit the conductor, doctor and panels can share.

Why this module exists
----------------------
"Auto-release" (answering a gate or closing a stage without a human) is only
sound when two independent layers agree:

  * the **value layer** - what the verdict-producing sources say, and
  * the **binding layer** - whether the bytes those sources point at are
    pinned (``path`` + ``sha256`` + ``mtime_ns``) at gate creation and again
    at gate consumption.

There is no single linear precedence, the sources answer three different propositions -
what the framework recorded on disk (``l3-verdict.txt``), what a
fresh recompute of the terminal round says (``l3-verdict-provenance.json``),
and whether the project declared that record wrong (a correction sidecar).  A
flat priority table reverses on real data (E2 ``feature-l3-readcap-injection``:
record ``meets`` / correction ``below``; FM ``gui-shell-spike``: record
``below`` / recompute ``meets``), so the rule is instead fail-closed:

  * verdict-producing sources take the MINIMUM (``meets`` > ``below`` >
    ``indeterminate``): one dissenting ``below`` blocks auto-release;
  * a correction is a **one-way dispute**: it can only pull ``meets`` down to
    ``below``, never the other way;
  * ``bound`` requires value layer ``meets`` AND binding layer present and
    matching; a missing binding is ``not bound`` - never a default ``bound``.

Sidecar
-------
One JSON file per gate, ``<gates>/gate-NNNN.evidence.json`` (schema string
exactly ``gate-evidence/1``), written at gate creation (``reason="created"``)
and at first consumption (``reason="consumed"``).  The two snapshots' sha256
difference is ``changed[]`` - the machine-detectable "evidence was rewritten
inside the answer window" criterion (the real 2026-09-24T16:47:33Z rewrite of
three E2 ``l3-verdict.txt`` files left zero ``l3-verdict`` timeline events).

Hard contracts:
  * this module creates nothing outside ``<gates>/``;
  * existing evidence files (``l3-verdict.txt`` and friends) are read-only
    inputs - hashed, never rewritten;
  * a corrupt sidecar is never overwritten (audit history outranks the newer
    record), mirroring ``_persist_l3_provenance``;
  * field names follow the frozen design table
    (``evidence/research/design-evidence-provenance-20260926.md`` section F3.3
    and ``design-gate-schema-presentation-20260926.md`` section D1.1).
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Iterable, Mapping, Sequence

from autopilot import gates

__all__ = [
    "BINDING_BOUND",
    "BINDING_PARTIAL",
    "BINDING_UNBOUND",
    "EVIDENCE_ROLES",
    "EVIDENCE_SCHEMA",
    "INDETERMINATE",
    "Resolution",
    "SNAPSHOT_REASONS",
    "STATUS_BOUND",
    "STATUS_INDETERMINATE",
    "STATUS_NOT_BOUND",
    "TAKEN_BY",
    "VERDICT_VALUES",
    "ValueResolution",
    "binding_of",
    "changed",
    "evidence_digest",
    "gate_file_record",
    "infer_role",
    "norm_path",
    "read_sidecar",
    "record_snapshot",
    "resolve",
    "resolve_value",
    "sidecar_changed",
    "sidecar_path",
    "snapshot",
    "write_sidecar",
]

# --- Protocol constants -------------------------------------------------------

# Frozen schema string (design F3.3): never reuse for an incompatible shape.
EVIDENCE_SCHEMA = "gate-evidence/1"

# The two snapshot points per gate. Written once each, idempotent by reason.
SNAPSHOT_REASONS: tuple[str, ...] = ("created", "consumed")

# The sidecar writer is the conductor only; an answerer must never write it.
TAKEN_BY = "conductor"

# Derived-record value domain (``conductor._VERDICT_VALUES``). ``indeterminate``
# is the fail-closed third state, not a recorded verdict.
VERDICT_VALUES: tuple[str, ...] = ("meets", "below")
INDETERMINATE = "indeterminate"
_VERDICT_RANK = {"meets": 2, "below": 1, INDETERMINATE: 0}

# Binding layer (design F3.5): present-and-matching = ``bound``.
BINDING_BOUND = "bound"
BINDING_PARTIAL = "partial"
BINDING_UNBOUND = "unbound"

# Overall auto-release status: ``bound`` iff value meets AND binding bound.
STATUS_BOUND = "bound"
STATUS_NOT_BOUND = "not bound"
STATUS_INDETERMINATE = INDETERMINATE

# Frozen role closed set (design F3.3); free-form roles are rejected.
EVIDENCE_ROLES: tuple[str, ...] = (
    "l3-verdict",
    "l3-report",
    "achieved",
    "quality-gate-report",
    "pm-state",
    "dossier",
    "worker-output",
    "worker-report",
    "worker-trace",
    "roadmap",
    "goal",
    "gate-file",
)

GATE_ID_RE = re.compile(r"^gate-\d+$")
_GATE_FILE_RE = re.compile(r"^gate-\d+\.md$")
_DOSSIER_RE = re.compile(r"^stage-\d+-close\.md$")
_QUALITY_GATE_RE = re.compile(r"^quality-gate-report.*\.md$")

# Snapshot-point claims (RQ-14 / design CR-*): a claimed-done key that is not
# ``bound`` is a dispute, never a silent success.
_CLAIMED_TERMINAL = frozenset({"done", "closed"})


# --- Path + hashing primitives ------------------------------------------------


def norm_path(value: object) -> str:
    """Project-relative, slash-separated path form (``_xkey_norm_path``)."""
    text = str(value).strip().strip("`'\"")
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _sha256_and_size(path: pathlib.Path) -> tuple[str, int]:
    """Exact whole-file byte sha256 plus byte count in one read pass."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1 << 16)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _snapshot_one(path_str: str) -> dict:
    """One ``{path, sha256, mtime_ns, bytes}`` record; missing => Nones."""
    path = pathlib.Path(path_str)
    try:
        mtime_ns = path.stat().st_mtime_ns
        sha256, size = _sha256_and_size(path)
    except OSError:
        return {"path": path_str, "sha256": None, "mtime_ns": None, "bytes": None}
    return {
        "path": path_str,
        "sha256": sha256,
        "mtime_ns": mtime_ns,
        "bytes": size,
    }


def snapshot(paths: Iterable[object]) -> list[dict]:
    """Pure evidence snapshot: ``[{path, sha256, mtime_ns, bytes}, ...]``.

    No global state, no caching, no directory creation.  An unreadable or
    missing pointer yields ``sha256=None`` (fail-closed upstream), never an
    exception.  Input order is preserved; duplicate paths are deduplicated by
    their normalized form (first occurrence wins).
    """
    records: list[dict] = []
    seen: set[str] = set()
    for raw in paths:
        key = norm_path(raw)
        if key in seen:
            continue
        seen.add(key)
        records.append(_snapshot_one(key))
    return records


def changed(before: Sequence[Mapping] | None, after: Sequence[Mapping] | None) -> list[str]:
    """Sorted paths whose sha256 differs between two snapshots.

    A path counts as changed when it appears on one side only (including a
    deletion: ``sha256=None``) or when both sides hash to different bytes.
    Missing-on-both-sides is not a change.
    """
    before_map = {
        norm_path(record.get("path", "")): record.get("sha256") for record in before or ()
    }
    after_map = {
        norm_path(record.get("path", "")): record.get("sha256") for record in after or ()
    }
    return sorted(
        path
        for path in set(before_map) | set(after_map)
        if before_map.get(path) != after_map.get(path)
    )


def _canonical_evidence(evidence: Sequence[Mapping] | None) -> list[dict]:
    """Canonical evidence entry order/fields used for hashing and storage."""
    entries: list[dict] = []
    for raw in evidence or ():
        path = norm_path(raw.get("path", ""))
        sha256 = raw.get("sha256")
        entries.append(
            {
                "path": path,
                "role": raw.get("role") or infer_role(path) or "",
                "exists": bool(raw.get("exists", sha256 is not None)),
                "bytes": raw.get("bytes"),
                "sha256": sha256,
                "mtime_ns": raw.get("mtime_ns"),
            }
        )
    entries.sort(key=lambda entry: entry["path"])
    return entries


def evidence_digest(evidence: Sequence[Mapping] | None) -> str:
    """``sha256(canonical_json(evidence))`` (sorted by path; design F3.3):
    one comparison instead of a per-entry walk."""
    payload = json.dumps(
        _canonical_evidence(evidence), ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def infer_role(path: object) -> str | None:
    """Map a pointer to the frozen role closed set (None when unrecognized)."""
    normalized = norm_path(path)
    name = normalized.rsplit("/", 1)[-1]
    if name == "l3-verdict.txt":
        return "l3-verdict"
    if name == "l3-report.md":
        return "l3-report"
    if name == "achieved.md":
        return "achieved"
    if name == "pm-state.md":
        return "pm-state"
    if name == "_roadmap.md":
        return "roadmap"
    if name == "goal.md":
        return "goal"
    if _GATE_FILE_RE.match(name):
        return "gate-file"
    if _DOSSIER_RE.match(name):
        return "dossier"
    if _QUALITY_GATE_RE.match(name):
        return "quality-gate-report"
    if "/workers/" in normalized or normalized.startswith("workers/"):
        if name == "output.md":
            return "worker-output"
        if name == "report.md":
            return "worker-report"
        if name in ("trace.log", "worker.log"):
            return "worker-trace"
    return None


def _normalize_evidence(
    evidence: Sequence[Mapping] | None,
    roles: Mapping[str, str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Canonical evidence entries + the pointers that could not be bound.

    An unrecognized role is not silently skipped: the path lands in the
    returned ``unresolved`` list so "not bound" stays distinguishable from
    "bound and matching".  A readable-but-missing pointer keeps its entry with
    ``sha256=None`` AND is listed in ``unresolved``.
    """
    role_map = roles or {}
    entries: list[dict] = []
    unresolved: list[str] = []
    for raw in evidence or ():
        path = norm_path(raw.get("path", ""))
        role = raw.get("role") or role_map.get(path) or infer_role(path)
        if role not in EVIDENCE_ROLES:
            unresolved.append(path)
            continue
        sha256 = raw.get("sha256")
        entries.append(
            {
                "path": path,
                "role": role,
                "exists": sha256 is not None,
                "bytes": raw.get("bytes"),
                "sha256": sha256,
                "mtime_ns": raw.get("mtime_ns"),
            }
        )
        if sha256 is None:
            unresolved.append(path)
    entries.sort(key=lambda entry: entry["path"])
    return entries, _dedupe(unresolved)


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# --- Sidecar read / write -----------------------------------------------------


def sidecar_path(gates_dir: pathlib.Path | str, gate_id: object) -> pathlib.Path:
    """``<gates>/gate-NNNN.evidence.json``; rejects anything else (no traversal)."""
    gate_id_str = str(gate_id)
    if not GATE_ID_RE.match(gate_id_str):
        raise ValueError(
            f"invalid gate id {gate_id_str!r}: expected gate-<digits>"
        )
    return pathlib.Path(gates_dir) / f"{gate_id_str}.evidence.json"


def parse_sidecar(text: str) -> dict | None:
    """Parse a sidecar document; ``None`` for anything off-contract."""
    try:
        document = json.loads(text)
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    if document.get("schema") != EVIDENCE_SCHEMA:
        return None
    if not isinstance(document.get("snapshots"), list):
        return None
    return document


def read_sidecar(gates_dir: pathlib.Path | str, gate_id: object) -> dict | None:
    """Read-only sidecar access.  Never creates a directory or a file.

    Missing, unreadable, wrong-schema or corrupt input all return ``None``.
    """
    path = sidecar_path(gates_dir, gate_id)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_sidecar(text)


def write_sidecar(
    gates_dir: pathlib.Path | str, gate_id: object, document: Mapping
) -> bool:
    """Atomic sidecar write (``tmp`` + ``os.replace``), inside ``<gates>/``.

    A corrupt/hand-edited existing sidecar is never overwritten (returns
    ``False``); audit history outranks the newer record.  Returns ``True`` iff
    new bytes landed.
    """
    if not isinstance(document, Mapping) or document.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError(
            f"sidecar document must be a mapping with schema == {EVIDENCE_SCHEMA!r}"
        )
    path = sidecar_path(gates_dir, gate_id)
    if path.exists():
        try:
            existing = parse_sidecar(path.read_text(encoding="utf-8"))
        except OSError:
            existing = None
        if existing is None:
            return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def _normalize_scope(scope: Mapping | None) -> dict:
    stage = None
    key = None
    if isinstance(scope, Mapping):
        raw_stage = scope.get("stage")
        if isinstance(raw_stage, int) and not isinstance(raw_stage, bool):
            stage = raw_stage
        raw_key = scope.get("key")
        if isinstance(raw_key, str) and raw_key:
            key = raw_key
    return {"stage": stage, "key": key}


def _normalize_gate_file(gate_file: Mapping | pathlib.Path | str | None) -> dict | None:
    if gate_file is None:
        return None
    if isinstance(gate_file, Mapping):
        raw = dict(gate_file)
    else:
        raw = {"path": gate_file}
    path = norm_path(raw.get("path", ""))
    sha256 = raw.get("sha256")
    mtime_ns = raw.get("mtime_ns")
    if sha256 is None or mtime_ns is None:
        probe = _snapshot_one(path)
        if sha256 is None:
            sha256 = probe["sha256"]
        if mtime_ns is None:
            mtime_ns = probe["mtime_ns"]
    return {
        "path": path,
        "status": raw.get("status"),
        "answered_at": raw.get("answered_at"),
        "answered_by": raw.get("answered_by"),
        "sha256": sha256,
        "mtime_ns": mtime_ns,
    }


def gate_file_record(
    path: object,
    *,
    status: str | None = None,
    answered_at: str | None = None,
    answered_by: str | None = None,
) -> dict:
    """Build the frozen ``gate_file`` snapshot entry for ``record_snapshot``.

    `status`/`answered_at`/`answered_by` are claimed values and are therefore
    recorded as data only - they never feed the resolution decision.
    """
    probe = _snapshot_one(norm_path(path))
    return {
        "path": probe["path"],
        "status": status,
        "answered_at": answered_at,
        "answered_by": answered_by,
        "sha256": probe["sha256"],
        "mtime_ns": probe["mtime_ns"],
    }


def record_snapshot(
    gates_dir: pathlib.Path | str,
    gate_id: object,
    *,
    reason: str,
    kind: str,
    scope: Mapping | None = None,
    gate_file: Mapping | pathlib.Path | str | None = None,
    evidence: Sequence[Mapping] | None = None,
    roles: Mapping[str, str] | None = None,
    unresolved: Sequence[object] = (),
    roster_digest: str | None = None,
    taken_at: str | None = None,
) -> bool:
    """Append one ``created``/``consumed`` snapshot to the gate sidecar.

    Idempotent by ``reason`` (a second call for the same reason is a zero-write
    and returns ``False``).  For ``reason="consumed"`` the ``changed[]`` list
    is computed against the ``created`` snapshot's evidence by sha256 - the
    machine-detectable "rewritten inside the answer window" criterion.  Files
    are created only under ``<gates>/``.
    """
    if reason not in SNAPSHOT_REASONS:
        raise ValueError(f"unknown snapshot reason {reason!r}: {SNAPSHOT_REASONS}")
    if kind not in gates.GATE_KINDS:
        raise ValueError(f"unknown gate kind {kind!r}: {gates.GATE_KINDS}")

    path = sidecar_path(gates_dir, gate_id)
    document: dict | None = None
    if path.exists():
        document = read_sidecar(gates_dir, gate_id)
        if document is None:
            return False  # corrupt/off-contract: never overwritten
    if document is None:
        document = {
            "schema": EVIDENCE_SCHEMA,
            "gate_id": str(gate_id),
            "kind": kind,
            "scope": _normalize_scope(scope),
            "snapshots": [],
        }
    snapshots = document.get("snapshots")
    if not isinstance(snapshots, list):
        return False
    if any(
        isinstance(existing, Mapping) and existing.get("reason") == reason
        for existing in snapshots
    ):
        return False  # already recorded at this point -> zero-write

    normalized, inferred_unresolved = _normalize_evidence(evidence, roles)
    changed_paths: list[str] = []
    if reason == "consumed":
        created = next(
            (
                existing
                for existing in snapshots
                if isinstance(existing, Mapping) and existing.get("reason") == "created"
            ),
            None,
        )
        if created is not None:
            changed_paths = changed(created.get("evidence"), normalized)

    entry = {
        "reason": reason,
        "taken_at": taken_at or _iso_now(),
        "taken_by": TAKEN_BY,
        "gate_file": _normalize_gate_file(gate_file),
        "evidence": normalized,
        "evidence_digest": evidence_digest(normalized),
        "unresolved": _dedupe(
            [norm_path(item) for item in unresolved] + inferred_unresolved
        ),
        "changed": changed_paths,
        "roster_digest": roster_digest,
    }
    new_document = dict(document)
    new_document["snapshots"] = list(snapshots) + [entry]
    return write_sidecar(gates_dir, gate_id, new_document)


def sidecar_changed(sidecar: Mapping | None) -> list[str]:
    """Union of ``changed[]`` across a sidecar's snapshots."""
    out: list[str] = []
    if not isinstance(sidecar, Mapping):
        return out
    snapshots = sidecar.get("snapshots")
    if not isinstance(snapshots, list):
        return out
    for snap in snapshots:
        if isinstance(snap, Mapping):
            for path in snap.get("changed") or ():
                if path not in out:
                    out.append(path)
    return out


# --- Binding layer ------------------------------------------------------------


def binding_of(
    evidence: Sequence[Mapping] | None = None,
    *,
    sidecar: Mapping | None = None,
    expected_paths: Sequence[object] | None = None,
) -> tuple[str, list[str]]:
    """Binding-layer verdict + reasons: ``bound`` / ``partial`` / ``unbound``.

    ``bound`` means every expected pointer is present AND sha-pinned AND (when
    a sidecar is given) both snapshots exist and each ``evidence_digest``
    recomputes.  Anything less is ``partial`` or ``unbound`` - never a default
    ``bound``.
    """
    expected = {norm_path(path) for path in expected_paths or ()}
    if sidecar is not None:
        return _sidecar_binding(sidecar, expected)
    if evidence is None:
        return BINDING_UNBOUND, ["no-evidence"]
    normalized, _ = _normalize_evidence(evidence)
    if not normalized:
        return BINDING_UNBOUND, ["no-evidence"]
    missing = [entry["path"] for entry in normalized if entry.get("sha256") is None]
    present = {
        entry["path"] for entry in normalized if entry.get("sha256") is not None
    }
    missing.extend(sorted(expected - present - set(missing)))
    missing = _dedupe(missing)
    if not present:
        return BINDING_UNBOUND, _dedupe(missing + ["no-evidence"])
    if missing:
        return BINDING_PARTIAL, missing
    return BINDING_BOUND, []


def _sidecar_binding(sidecar: Mapping, expected: set[str]) -> tuple[str, list[str]]:
    snapshots = sidecar.get("snapshots") if isinstance(sidecar, Mapping) else None
    if not isinstance(snapshots, list) or not snapshots:
        return BINDING_UNBOUND, ["no-snapshot"]
    by_reason: dict[str, Mapping] = {}
    for snap in snapshots:
        if isinstance(snap, Mapping) and isinstance(snap.get("reason"), str):
            by_reason.setdefault(snap["reason"], snap)
    reasons: list[str] = []
    if not set(SNAPSHOT_REASONS) <= set(by_reason):
        reasons.append("incomplete-window")
    present: set[str] = set()
    missing: list[str] = []
    for snap in by_reason.values():
        raw_evidence = snap.get("evidence")
        normalized, _ = _normalize_evidence(raw_evidence)
        for entry in normalized:
            if entry.get("sha256") is None:
                missing.append(entry["path"])
            else:
                present.add(entry["path"])
        if evidence_digest(raw_evidence) != snap.get("evidence_digest"):
            reasons.append("digest-mismatch")
        for path in snap.get("unresolved") or ():
            missing.append(norm_path(path))
    for path in sorted(expected - present):
        missing.append(path)
    missing = _dedupe(missing)
    if reasons:
        return BINDING_PARTIAL, _dedupe(reasons + missing)
    if not present:
        return BINDING_UNBOUND, _dedupe(missing + ["no-evidence"])
    if missing:
        return BINDING_PARTIAL, missing
    return BINDING_BOUND, []


# --- Provenance resolution ----------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ValueResolution:
    """Value-layer outcome: the fail-closed minimum plus dispute kinds."""

    value: str
    disputes: tuple[str, ...]
    sources: dict[str, str | None]

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "disputes": list(self.disputes),
            "sources": dict(self.sources),
        }


@dataclasses.dataclass(frozen=True)
class Resolution:
    """Full layered outcome: value + binding -> auto-release status."""

    value: str
    binding: str
    status: str
    auto_release: bool
    drift: bool
    disputes: tuple[str, ...]
    reasons: tuple[str, ...]
    sources: dict[str, str | None]

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "binding": self.binding,
            "status": self.status,
            "auto_release": self.auto_release,
            "drift": self.drift,
            "disputes": list(self.disputes),
            "reasons": list(self.reasons),
            "sources": dict(self.sources),
        }


def _record_sha_from_evidence(
    evidence: Sequence[Mapping] | None, correction: Mapping
) -> str | None:
    """The current ``l3-verdict.txt`` sha, for correction byte-binding."""
    if not evidence:
        return None
    target = norm_path(correction.get("recorded_path") or "")
    for raw in evidence:
        if target and norm_path(raw.get("path", "")) == target:
            return raw.get("sha256")
    candidates = [
        raw
        for raw in evidence
        if (raw.get("role") or infer_role(raw.get("path", ""))) == "l3-verdict"
    ]
    if len(candidates) == 1:
        return candidates[0].get("sha256")
    return None


def _correction_in_force(
    correction: Mapping, record_sha256: str | None, record_value: str | None
) -> tuple[bool, str]:
    """A correction is in force only when its byte binding (or the documented
    weak value binding) still holds; otherwise it is stale.  One-way by
    construction: this never licenses an upgrade."""
    original_sha = correction.get("original_sha256")
    if isinstance(original_sha, str) and original_sha:
        if not record_sha256:
            return False, "unverifiable"
        return original_sha == record_sha256, "sha256"
    original_value = correction.get("original_value")
    if original_value in VERDICT_VALUES and original_value == record_value:
        return True, "value-weak"
    return False, "unbound"


def resolve_value(
    sources: Sequence[Mapping] = (),
    *,
    correction: Mapping | None = None,
    record_sha256: str | None = None,
    evidence: Sequence[Mapping] | None = None,
) -> ValueResolution:
    """Fail-closed minimum over verdict-producing sources + one-way correction.

    Sources are mappings like ``{"role": "l3-verdict", "value": "meets"}``.
    ``value=None`` means "not available" and is skipped; anything outside
    ``{"meets", "below"}`` votes ``indeterminate`` (worse than ``below``).
    A correction can only pull the result down to ``below`` (or make it
    ``indeterminate`` when stale) - never up.
    """
    disputes: list[str] = []
    values: dict[str, str | None] = {}
    worst: str | None = None
    for index, source in enumerate(sources or ()):
        role = str(source.get("role") or f"source-{index}")
        raw = source.get("value")
        if raw in VERDICT_VALUES:
            value: str | None = raw
        elif raw is None:
            value = None
        else:
            value = INDETERMINATE
        values[role] = value
        if value is None:
            continue
        if worst is None or _VERDICT_RANK[value] < _VERDICT_RANK[worst]:
            worst = value
    if worst is None:
        value = INDETERMINATE
        disputes.append("no-credible-source")
    else:
        value = worst

    if correction is not None:
        if not isinstance(correction, Mapping):
            disputes.append("correction-malformed")
            value = INDETERMINATE
        else:
            if record_sha256 is None:
                record_sha256 = _record_sha_from_evidence(evidence, correction)
            record_value = next(
                (src.get("value") for src in sources or () if src.get("role") == "l3-verdict"),
                None,
            )
            in_force, basis = _correction_in_force(
                correction, record_sha256, record_value
            )
            if not in_force:
                disputes.append("correction-stale")
                value = INDETERMINATE
            else:
                if basis == "value-weak":
                    disputes.append("correction-weak-binding")
                corrected = correction.get("corrected_value")
                counted_as_done = correction.get("counted_as_done")
                if corrected == "below" or counted_as_done is False:
                    disputes.append("correction")
                    if _VERDICT_RANK[value] > _VERDICT_RANK["below"]:
                        value = "below"
                elif corrected == "meets":
                    # ONE-WAY: an upward correction is recorded and ignored.
                    disputes.append("correction-upward-ignored")
    return ValueResolution(
        value=value, disputes=tuple(_dedupe(disputes)), sources=values
    )


def resolve(
    *,
    sources: Sequence[Mapping] = (),
    correction: Mapping | None = None,
    record_sha256: str | None = None,
    evidence: Sequence[Mapping] | None = None,
    before: Sequence[Mapping] | None = None,
    after: Sequence[Mapping] | None = None,
    sidecar: Mapping | None = None,
    expected_paths: Sequence[object] | None = None,
    claimed: str | None = None,
) -> Resolution:
    """Resolve value + binding into an auto-release status.

    ``status == "bound"`` (the only auto-release) requires value ``meets``
    AND binding ``bound`` AND no drift.  A missing binding is ``not bound``;
    drift or an indeterminate value is ``indeterminate``; both block.
    """
    value_result = resolve_value(
        sources,
        correction=correction,
        record_sha256=record_sha256,
        evidence=evidence,
    )
    binding, binding_reasons = binding_of(
        evidence, sidecar=sidecar, expected_paths=expected_paths
    )
    drifts: list[str] = []
    if sidecar is not None:
        drifts = sidecar_changed(sidecar)
    if before is not None and after is not None:
        drifts = changed(before, after)
    drift = bool(drifts)

    disputes = list(value_result.disputes)
    if drift:
        disputes.append("drift")
    if claimed in _CLAIMED_TERMINAL and value_result.value != "meets":
        disputes.append("claimed-done-without-bound-meets")

    if value_result.value == INDETERMINATE:
        status = STATUS_INDETERMINATE
    elif drift:
        status = STATUS_INDETERMINATE
    elif value_result.value == "meets" and binding == BINDING_BOUND:
        status = STATUS_BOUND
    else:
        status = STATUS_NOT_BOUND

    return Resolution(
        value=value_result.value,
        binding=binding,
        status=status,
        auto_release=status == STATUS_BOUND,
        drift=drift,
        disputes=tuple(_dedupe(disputes)),
        reasons=tuple(_dedupe(list(binding_reasons) + drifts)),
        sources=dict(value_result.sources),
    )
