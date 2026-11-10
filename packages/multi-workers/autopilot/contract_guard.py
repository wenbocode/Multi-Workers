"""contract_guard.py - AC/VC contract identity + change authorization (G3).

Key mw-gate-verdict-hardening, task T-04 (design D-011/D-014/D-015/D-016).

This is the single home of the G3 decision logic. It is a pure module: every
parse/hash/diff/authorization helper takes its input as an argument, no path is
hardcoded, and there is no module-level file access. The only file IO is the
explicit freeze sidecar read/write, and the root directory is injected by the
caller. It never imports ``conductor`` (the dependency stays one-way,
``conductor -> contract_guard``).

Contract surface:

  - ``parse_acs(spec_text)``  AC-### -> AC cell text, from the spec.md table
    (regex ``^\\|\\s*(AC-\\d{3})\\s*\\|\\s*(.*?)\\s*\\|\\s*$``).
  - ``parse_vcs(design_text)``  VC-### -> canonical block text. The block shape
    mirrors ``.tmp/msc-gen-evidence-req.py:parse_vcs`` (assert / Layer / Output
    / Source); the identity covers the five-tuple.
  - ``canonical_sha(field_id, text)``  per-identity sha256 over
    ``id + "\\x1f" + text`` (no whole-text whitespace folding, trailing line
    whitespace never counts).
  - ``family_sha(entries)``  one stable digest over the sorted family map.
  - ``extract_contract(spec_text, design_text)``  the ``{id: sha256}`` identity
    of both families.
  - ``freeze_path`` / ``build_freeze`` / ``read_freeze`` / ``write_freeze`` /
    ``freeze_contract``  the ``<key>/evidence/contract-freeze.json`` sidecar
    (shape: design D-015). A missing or corrupt sidecar reads back as ``None``
    ("no identity anchor"), never as an exception.
  - ``diff_contract(identity, freeze)``  added / removed / changed id sets,
    current text vs freeze.
  - ``find_authorizing_gate`` / ``authorizing_gates``  the approval record:
    ``status == "approved"`` and ``authorizes`` contains ``contract-change`` and
    ``gate.key == key``. The kind is deliberately not bound, and ``note`` /
    ``answered_by`` are never read (AC-012 is constructive).
  - ``evaluate(key_dir, gates_dir)``  the composed verdict consumed by the
    conductor done gate (T-10) and the CLI/doctor surface (T-11).

T20 (AC-024/AC-025/AC-028/AC-029/AC-052) adds two strict machine layers at the
end of this module: :func:`assess_goal_adoption` + :func:`apply_goal_adoption`
(only a valid approve whose note names the current goal version moves the
baseline) and :func:`assess_freeze_change` + :func:`refreeze_approved_change`
(a frozen-entry change needs the complete note, exactly the approved item/version
set, and appends an adoption row instead of rewriting the contract text).
Existing ``evaluate`` behaviour is unchanged; the strict layers are additive.

Deliberately not used: the gate ``subject_sha256`` field (no production writer,
dead path) and ``git diff`` (fail-open: ``advance done`` runs before commit in
long keys). The identity anchor is the freeze sidecar only.
"""
from __future__ import annotations

import contextlib
import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Iterable, Mapping

import mw_common
import decision_lifecycle
import decision_policy
import decision_validity
import decision_wire

from autopilot import gates, state

# --- Contract constants -------------------------------------------------------

#: The action type that authorizes changing frozen AC/VC text.
CONTRACT_CHANGE_ACTION = "contract-change"

#: Freeze sidecar identity (design D-015).
FREEZE_SCHEMA = 1
FREEZE_FILE_NAME = "contract-freeze.json"
FREEZE_DIR_NAME = "evidence"
FREEZE_GENERATOR = "mw autopilot contract-freeze"

#: Key-relative inputs. The key directory is always injected by the caller.
SPEC_FILE_NAME = "spec.md"
DESIGN_FILE_NAME = "design.md"

#: AC table row: `| AC-001 | text |` (spec.md).
AC_LINE_RE = re.compile(r"^\|\s*(AC-\d{3})\s*\|\s*(.*?)\s*\|\s*$")

#: VC block: `VC-001: assert` + `Layer: Lx Output: [VERIFY] ... Source: ...`.
#: Semantics copied from `.tmp/msc-gen-evidence-req.py:parse_vcs`; the path
#: dependency is not (this module only ever parses caller-supplied text).
VC_BLOCK_RE = re.compile(
    r"VC-(\d{3}):\s*(.+?)\n\s*Layer:\s*(\S+)\s+Output:\s*(\[VERIFY\][^\n]*?)\s+Source:\s*([^\n]+)"
)

#: Canonical field separator. Not a character that occurs in either file.
_FIELD_SEP = "\x1f"


# --- Text identity ------------------------------------------------------------


def parse_acs(spec_text: str) -> dict[str, str]:
    """AC-### -> AC cell text, scanning every line of the spec.md AC table.

    A line that does not open with ``| AC-<digits> |`` is ignored. The cell is
    stripped of surrounding whitespace by the regex, so editor noise never
    enters the identity; the text inside the cell is otherwise untouched (no
    whitespace folding), so a rewritten body is always detected.
    """
    acs: dict[str, str] = {}
    for line in spec_text.splitlines():
        match = AC_LINE_RE.match(line)
        if match is not None:
            acs[match.group(1)] = match.group(2)
    return acs


def parse_vcs(design_text: str) -> dict[str, str]:
    """VC-### -> canonical five-tuple text (assert/Layer/Output/Source).

    The identity text is the four parsed fields joined by ``\\x1f``; together
    with the id it forms the five-tuple that :func:`canonical_sha` hashes.
    ``finditer`` keeps source order, but the returned mapping is used in sorted
    order by the callers.
    """
    vcs: dict[str, str] = {}
    for match in VC_BLOCK_RE.finditer(design_text):
        vc_id = "VC-" + match.group(1)
        assert_text = match.group(2).strip()
        layer = match.group(3).strip()
        output = match.group(4).strip()
        source = match.group(5).strip()
        vcs[vc_id] = _FIELD_SEP.join((assert_text, layer, output, source))
    return vcs


def canonical_sha(field_id: str, text: str) -> str:
    """sha256 over ``id + \\x1f + text`` for one AC/VC identity.

    ``\\r`` is already removed by ``splitlines()`` and the cell text is
    stripped by the parsers, so neither CRLF rewrites nor trailing blanks move
    the identity, while any body rewrite does.
    """
    return hashlib.sha256(
        (field_id + _FIELD_SEP + text).encode("utf-8")
    ).hexdigest()


def family_sha(entries: Mapping[str, str]) -> str:
    """One stable sha256 over a family map, sorted by id.

    The same map always serializes to the same bytes regardless of insertion
    order (stable serialization before hashing).
    """
    payload = "\n".join(
        f"{field_id}{_FIELD_SEP}{text}" for field_id, text in sorted(entries.items())
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclasses.dataclass(frozen=True)
class ContractIdentity:
    """Per-id sha256 identity of the AC family and the VC family."""

    acs: dict[str, str]
    vcs: dict[str, str]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.acs) | set(self.vcs)))


def extract_contract(spec_text: str, design_text: str) -> ContractIdentity:
    """Identity of the current AC/VC text, as ``{id: sha256}`` per family."""
    return ContractIdentity(
        acs={
            ac_id: canonical_sha(ac_id, text)
            for ac_id, text in parse_acs(spec_text).items()
        },
        vcs={
            vc_id: canonical_sha(vc_id, text)
            for vc_id, text in parse_vcs(design_text).items()
        },
    )


# --- Freeze sidecar -----------------------------------------------------------


def freeze_path(key_dir: pathlib.Path | str) -> pathlib.Path:
    """``<key>/evidence/contract-freeze.json`` for an injected key root."""
    return pathlib.Path(key_dir) / FREEZE_DIR_NAME / FREEZE_FILE_NAME


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def build_freeze(
    key: str,
    spec_text: str,
    design_text: str,
    *,
    frozen_at: str | None = None,
    generator: str = FREEZE_GENERATOR,
) -> dict[str, object]:
    """Pure freeze payload (design D-015 shape) for the current text."""
    identity = extract_contract(spec_text, design_text)
    return {
        "schema": FREEZE_SCHEMA,
        "key": key,
        "frozen_at": frozen_at if frozen_at is not None else _iso_now(),
        "spec": dict(sorted(identity.acs.items())),
        "design": dict(sorted(identity.vcs.items())),
        "generator": generator,
    }


def read_freeze(key_dir: pathlib.Path | str) -> dict[str, object] | None:
    """Read the freeze sidecar; ``None`` when absent or unusable.

    A missing file, an unreadable path, malformed JSON, an unknown schema, or a
    wrong ``spec``/``design`` value type all read back as ``None`` - the caller
    treats "no usable anchor" and "no anchor" identically (no exception).
    """
    try:
        raw = freeze_path(key_dir).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("schema") != FREEZE_SCHEMA:
        return None
    for family in ("spec", "design"):
        entries = data.get(family)
        if not isinstance(entries, dict):
            return None
        if not all(
            isinstance(name, str) and isinstance(digest, str)
            for name, digest in entries.items()
        ):
            return None
    return data


def write_freeze(
    key_dir: pathlib.Path | str, freeze: Mapping[str, object]
) -> pathlib.Path:
    """Atomically write the sidecar (UTF-8, LF, LF-safe tmp + replace)."""
    path = freeze_path(key_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        freeze, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)
    return path


def freeze_contract(
    key_dir: pathlib.Path | str,
    key: str,
    spec_text: str,
    design_text: str,
    *,
    frozen_at: str | None = None,
) -> pathlib.Path:
    """Build and persist the freeze sidecar; returns its path."""
    return write_freeze(
        key_dir, build_freeze(key, spec_text, design_text, frozen_at=frozen_at)
    )


# --- Change detection ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ContractDiff:
    """Per-id change sets of current text against a freeze sidecar."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]

    @property
    def changed_ids(self) -> tuple[str, ...]:
        """Every affected id (added + removed + changed), sorted."""
        return tuple(sorted(set(self.added) | set(self.removed) | set(self.changed)))

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def _freeze_family(freeze: Mapping[str, object], family: str) -> dict[str, str]:
    entries = freeze.get(family)
    if not isinstance(entries, dict):
        return {}
    return {
        str(name): str(digest)
        for name, digest in entries.items()
    }


def diff_contract(
    identity: ContractIdentity, freeze: Mapping[str, object]
) -> ContractDiff:
    """Compare the current identity with a freeze sidecar (pure)."""
    added: list[str] = []
    removed: list[str] = []
    changed: list[str] = []
    for family, current in (("spec", identity.acs), ("design", identity.vcs)):
        frozen = _freeze_family(freeze, family)
        current_ids = set(current)
        frozen_ids = set(frozen)
        added.extend(sorted(current_ids - frozen_ids))
        removed.extend(sorted(frozen_ids - current_ids))
        changed.extend(
            sorted(
                field_id
                for field_id in current_ids & frozen_ids
                if current[field_id] != frozen[field_id]
            )
        )
    return ContractDiff(
        added=tuple(sorted(added)),
        removed=tuple(sorted(removed)),
        changed=tuple(sorted(changed)),
    )


# --- Approval lookup ----------------------------------------------------------


def gate_authorizes_contract_change(gate: object) -> bool:
    """True when the gate carries ``contract-change`` in ``authorizes``.

    Reads only the machine field: an absent field, an empty array, or a
    non-list value is not an authorization (fail-closed).
    """
    actions = getattr(gate, "authorizes", None)
    if not isinstance(actions, (list, tuple)):
        return False
    return CONTRACT_CHANGE_ACTION in actions


def authorizing_gates(gate_list: Iterable[object], key: str) -> list[object]:
    """Every approval record for ``key``, in input order.

    ``status == "approved"`` and ``authorizes`` contains ``contract-change`` and
    ``gate.key == key``. ``kind`` is not bound (the E2 incident carrier was a
    ``stalled`` gate), and ``note`` / ``answered_by`` are never read.
    """
    return [
        gate
        for gate in gate_list
        if getattr(gate, "status", None) == "approved"
        and gate_authorizes_contract_change(gate)
        and getattr(gate, "key", None) == key
    ]


def find_authorizing_gate(gate_list: Iterable[object], key: str) -> object | None:
    """First approval record for ``key``, or ``None``."""
    for gate in authorizing_gates(gate_list, key):
        return gate
    return None


# --- Composed verdict ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ContractVerdict:
    """Outcome of the done-gate contract check.

    ``ok`` is the decision (fail-closed). ``no_anchor`` distinguishes the
    "no freeze sidecar" branch: the check cannot decide, so it must not refuse
    (zero disturbance for historical keys). ``carrier`` is the id of the gate
    that authorized a detected change, when one exists.
    """

    ok: bool
    no_anchor: bool
    changed_ids: tuple[str, ...]
    carrier: str | None
    reasons: tuple[str, ...]


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def evaluate(
    key_dir: pathlib.Path | str,
    gates_dir: pathlib.Path | str,
    *,
    key: str | None = None,
    spec_text: str | None = None,
    design_text: str | None = None,
) -> ContractVerdict:
    """Composed G3 verdict for one key (used by T-10 and T-11).

    Without a freeze sidecar: ``ok=True, no_anchor=True`` (nothing to compare).
    With a sidecar: current AC/VC identity vs frozen; unchanged text is
    ``ok=True``. A change is ``ok=True`` only when an approved gate carries
    ``authorizes: ["contract-change"]`` for this key; otherwise it is
    ``ok=False`` (fail-closed) with the changed ids and reason.
    """
    key_dir = pathlib.Path(key_dir)
    freeze = read_freeze(key_dir)
    if freeze is None:
        return ContractVerdict(
            ok=True,
            no_anchor=True,
            changed_ids=(),
            carrier=None,
            reasons=("no-freeze",),
        )
    # Prefer the caller's key; otherwise trust the key recorded in the freeze
    # before falling back to the directory name.
    frozen_key = freeze.get("key")
    resolved_key = (
        key
        if key is not None
        else frozen_key
        if isinstance(frozen_key, str) and frozen_key
        else key_dir.name
    )
    if spec_text is None:
        spec_text = _read_text(key_dir / SPEC_FILE_NAME)
    if design_text is None:
        design_text = _read_text(key_dir / DESIGN_FILE_NAME)
    diff = diff_contract(extract_contract(spec_text, design_text), freeze)
    if not diff.has_changes:
        return ContractVerdict(
            ok=True,
            no_anchor=False,
            changed_ids=(),
            carrier=None,
            reasons=(),
        )
    carrier = find_authorizing_gate(gates.enumerate(gates_dir), resolved_key)
    if carrier is None:
        return ContractVerdict(
            ok=False,
            no_anchor=False,
            changed_ids=diff.changed_ids,
            carrier=None,
            reasons=("contract-unauthorized",),
        )
    return ContractVerdict(
        ok=True,
        no_anchor=False,
        changed_ids=diff.changed_ids,
        carrier=getattr(carrier, "id", None),
        reasons=("authorized",),
    )


# --- Real T07/T10/T17/T18 supply (shared by H06/H07/H08) ---------------------
#
# H06/H07/H08 deliberately do not trust the PM request text (or a free-form
# ``authority_ref``). A strict writer may only run against a real project
# supply: the T17 gate file, the T10 lifecycle request/basis/note/consumed
# rows, the live PM claim in ``_index.parallel``, a T07 authority record from a
# controlled writer and the policy hard budget. :func:`verify_supply` reads
# those facts from the injected project root on every call; there is no
# default source, so a missing supply is a refusal.


@dataclasses.dataclass(frozen=True)
class TrustedSupply:
    """Real project artefacts a strict writer must be bound to.

    Every field is an identity/path, not an asserted fact: the verifier reads
    the gate, the index, the lifecycle ledger, the authority records and the
    policy itself. A caller can construct this dataclass, but it still cannot
    manufacture the on-disk records the verifier requires.
    """

    project_root: pathlib.Path | str
    key: str
    gate_id: str
    decision_ref: str
    matter_ref: str
    substantive_version: str
    authority_source: Mapping[str, object]
    trusted_writers: tuple[str, ...]
    usage: Mapping[str, int] = dataclasses.field(default_factory=dict)
    spend: Mapping[str, int] = dataclasses.field(default_factory=dict)


_DAMAGE_FIELDS = (
    "bad_json",
    "bad_utf8",
    "unknown_schema",
    "oversized_line",
    "incomplete_tail",
)


def _unreadable_lifecycle(project_root: pathlib.Path) -> list[str]:
    """Lifecycle rows for ``project_root`` or a fail-closed damage list."""

    try:
        store = decision_lifecycle.LifecycleStore.production(
            project_root, redact=decision_wire.SubstringRedactor(())
        )
        read = decision_lifecycle.read_lifecycle(store)
    except (OSError, ValueError, TypeError):
        return []
    if any(getattr(read.stats, name) for name in _DAMAGE_FIELDS):
        return []
    return [
        row
        for row in read.events
        if isinstance(row, Mapping)
        and row.get("scope") == "production"
        and row.get("project_id") == store.project_id
    ]


def _resolve_authority_for(
    authority_ref: object,
    supply: TrustedSupply,
    required_scope: Iterable[str],
) -> tuple[str, ...]:
    """Reuse T07's controlled-writer resolution; never trust the ref text."""

    if not isinstance(authority_ref, str) or not authority_ref.strip():
        return ("authority-ref-missing",)
    resolution = decision_policy._resolve_authority(
        authority_ref,
        supply.authority_source,
        tuple(required_scope),
        supply.trusted_writers,
    )
    return tuple(issue.code for issue in resolution.issues)


def _check_budget(supply: TrustedSupply, project_root: pathlib.Path) -> tuple[str, ...]:
    """Cumulative hard budget via the same T07 policy the gate consumer reads."""

    load = decision_policy.load_policy(project_root)
    if not load.usable or load.policy is None:
        return ("budget_policy_unusable",)
    limits = load.policy.hard_limits
    if not limits:
        return ("missing_hard_budget",)
    units = {limit.unit for limit in limits}
    if set(supply.spend) != units:
        return ("budget_units_mismatch",)
    reasons: list[str] = []
    for limit in limits:
        delta = supply.spend.get(limit.unit)
        used = supply.usage.get(limit.usage_source)
        if (
            type(delta) is not int
            or delta < 0
            or type(used) is not int
            or not 0 <= used <= limit.limit
        ):
            reasons.append("budget_usage_unknown")
            continue
        if delta and not decision_policy.check_spend(
            load, unit=limit.unit, amount=delta, usage={limit.unit: used}
        ).allowed:
            reasons.append("budget_exhausted")
    return tuple(dict.fromkeys(reasons))


def _verify_lifecycle(supply: TrustedSupply, rows: list[Mapping[str, object]],
                      gate: "gates.Gate", require_consumed: bool) -> tuple[str, ...]:
    """The formal T10 request/basis/note facts for this decision reference."""

    decision_ref = supply.decision_ref
    logical_id = decision_ref.partition(":")[2] or decision_ref.partition(":")[0]
    scoped = [
        row
        for row in rows
        if row.get("logical_id") == logical_id
        and row.get("key") == supply.key
        and row.get("decision_id") in (None, decision_ref)
    ]
    starts = [
        row
        for row in scoped
        if row.get("kind") == "record-start"
        and row.get("record_version") == decision_lifecycle.RECORD_VERSION
        and row.get("initiator_role") == "pm"
    ]
    if len(starts) != 1:
        return ("missing_pm_record",)
    requests = [row for row in scoped if row.get("kind") == "request"]
    requests = [row for row in requests if row.get("decision_id") == decision_ref]
    if len(requests) != 1:
        return ("missing_pm_request",)
    request = requests[0]
    reasons: list[str] = []
    if (
        request.get("business_decisions") != 1
        or request.get("available") is not True
        or request.get("choice") != gate.business
        or request.get("basis_source") != "pm-prepared"
        or not request.get("basis_text")
        or not request.get("basis_catalog_sha256")
        or not request.get("prepared_at")
    ):
        reasons.append("request_basis_mismatch")
    if request.get("basis_text") != gate.model_basis:
        reasons.append("request_basis_mismatch")
    notes = [
        row
        for row in scoped
        if row.get("kind") == "note"
        and row.get("note_source") == "pm-prepared"
        and row.get("prepared_at") == request.get("prepared_at")
    ]
    if len(notes) != 1 or notes[0].get("pm_note") != gate.pm_note:
        reasons.append("missing_pm_note")
    if require_consumed:
        consumed = [
            row
            for row in scoped
            if row.get("kind") == "lifecycle"
            and row.get("lifecycle") == "consumed"
            and row.get("decision_id") == decision_ref
            and row.get("answer") == gate.business
        ]
        if not consumed:
            reasons.append("missing_consumed")
    return tuple(dict.fromkeys(reasons))


def verify_supply(
    supply: "TrustedSupply | None",
    *,
    gate_kind: str | None,
    expected_gate_key: str | None,
    required_scope: Iterable[str],
    authority_ref: object,
    require_authorizes: Iterable[str] = (),
    require_files: Iterable[str] = (),
    note: str | None = None,
    target_key: str | None = None,
    require_consumed: bool = True,
    effect_reasons: tuple[str, ...] | None = None,
) -> tuple[tuple[str, ...], "gates.Gate | None"]:
    """Verify one strict writer against the real project supply (fail-closed)."""

    if not isinstance(supply, TrustedSupply):
        return ("missing_trusted_supply",), None
    project_root = pathlib.Path(supply.project_root)
    reasons: list[str] = []
    gate_path = (
        project_root
        / ".agenticdoc"
        / "_autopilot"
        / "gates"
        / (supply.gate_id + ".md")
    )
    try:
        gate = gates.parse(gate_path)
    except (OSError, ValueError):
        return ("unreadable_gate",), None
    if gate.id != supply.gate_id:
        reasons.append("gate_identity_mismatch")
    if gate_kind is not None and gate.kind != gate_kind:
        reasons.append("wrong_gate_kind")
    if gate.historical:
        reasons.append("historical_gate")
    if gate.transport != "answered":
        reasons.append("gate_not_answered")
    if gate.business != "approve":
        reasons.append("gate_not_approved")
    if effect_reasons is None:
        effect_reasons = _pm_effect_evidence(project_root, gate)
    reasons.extend(effect_reasons)
    if expected_gate_key is not None and gate.key != expected_gate_key:
        reasons.append("gate_key_mismatch")
    if gate.decision_ref != supply.decision_ref:
        reasons.append("gate_decision_mismatch")
    if not gate.matter_ref or gate.matter_ref != supply.matter_ref:
        reasons.append("gate_matter_mismatch")
    if not gate.substantive_version or gate.substantive_version != supply.substantive_version:
        reasons.append("gate_version_mismatch")
    if not gate.model_basis:
        reasons.append("missing_model_basis")
    if note is not None and gate.pm_note != note:
        reasons.append("gate_note_mismatch")
    if require_authorizes and not set(require_authorizes).issubset(set(gate.authorizes or ())):
        reasons.append("gate_missing_authorizes")
    if require_files and not set(require_files).issubset(set(gate.write_scope or ())):
        reasons.append("gate_write_scope")

    rows = state.read_index(project_root)
    claims = [row for row in rows if row.get("key") == supply.key]
    if len(claims) != 1:
        reasons.append("pm_claim_not_live")
    else:
        claim = str(claims[0].get("claim_id") or "")
        if (
            claims[0].get("status") != "active"
            or not claim
            or claim != gate.answered_by
            or state.claim_state(claim) != state.CLAIM_LIVE
        ):
            reasons.append("pm_claim_not_live")
    if target_key is not None and target_key != supply.key:
        target_rows = [row for row in rows if row.get("key") == target_key]
        for row in target_rows:
            claim = str(row.get("claim_id") or "")
            if (
                row.get("status") == "active"
                and claim
                and claim != gate.answered_by
                and state.claim_state(claim) == state.CLAIM_LIVE
            ):
                reasons.append("target_key_claim_held")

    reasons.extend(_resolve_authority_for(authority_ref, supply, required_scope))
    lifecycle_rows = _unreadable_lifecycle(project_root)
    if not lifecycle_rows:
        reasons.append("lifecycle_unreadable")
    else:
        reasons.extend(_verify_lifecycle(supply, lifecycle_rows, gate, require_consumed))
    reasons.extend(_check_budget(supply, project_root))
    return tuple(dict.fromkeys(reasons)), gate


# --- H06: goal-version adoption (AC-024 / AC-025) ----------------------------
#
# A changed goal.md is never an authorization by itself. The goal-change gate's
# four choices are judged here; only a valid ``approve`` bound to the real T17
# gate, T10 request/basis/note, live PM claim, T07 authority and hard budget may
# move the baseline. ``steer``, ``need_fix``, ``reject`` and any failed or
# unverifiable answer return an explicit non-adoption: the writer below then
# leaves the baseline bytes untouched.

GOAL_ADOPTION_CHOICES: tuple[str, ...] = ("approve", "steer", "need_fix", "reject")

_GOAL_REQUIRED_FIELDS: tuple[str, ...] = (
    "key",
    "previous_version",
    "current_version",
    "target_version",
    "necessity",
    "impact",
    "authority_ref",
    "reverification_plan",
)


#: Capability marker: only :func:`assess_goal_adoption` may issue an adopting
#: verdict; the baseline writer refuses a hand-constructed dataclass.
_ISSUED = object()


def _read_json_object(path: pathlib.Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dict(data) if isinstance(data, dict) else None


@dataclasses.dataclass(frozen=True)
class GoalAdoptionRequest:
    """The PM-prepared goal-change note consumed by the adoption judgement.

    These fields are business intent only. They do not prove that the goal
    changed, that the note is the one the PM recorded or that any authority
    exists; the strict entry reads those facts from :class:`TrustedSupply`.
    """

    key: str
    previous_version: str
    current_version: str
    target_version: str
    necessity: str
    impact: str
    authority_ref: str
    reverification_plan: str


@dataclasses.dataclass(frozen=True)
class GoalAdoptionVerdict:
    """Whether the goal baseline may move, and what must be re-verified.

    ``baseline_refresh`` is the only field the writer reads. A blocked or
    non-adopted verdict always has ``False`` there, so a file change, a
    non-approve choice or a failed answer cannot refresh the baseline.
    ``_issued`` is a module-private capability: the writer accepts only a
    verdict this module's strict assessment produced.
    """

    status: str
    adopt: bool
    baseline_refresh: bool
    version: str | None
    reasons: tuple[str, ...]
    previous_version: str | None = None
    reverification_required: tuple[str, ...] = ()
    reusable_bindings: tuple[str, ...] = ()
    _issued: object | None = dataclasses.field(default=None, repr=False, compare=False)


def _blocked_goal(status: str, reasons: Iterable[str],
                  unaffected: Iterable[str] = ()) -> GoalAdoptionVerdict:
    return GoalAdoptionVerdict(
        status=status,
        adopt=False,
        baseline_refresh=False,
        version=None,
        reasons=tuple(dict.fromkeys(reasons)),
        reusable_bindings=tuple(unaffected),
    )


def assess_goal_adoption(
    choice: str,
    request: GoalAdoptionRequest,
    *,
    changed: bool = False,
    supply: TrustedSupply | None = None,
    baseline_path: pathlib.Path | str | None = None,
    goal_before_text: str | None = None,
    goal_after_text: str | None = None,
    pm_note: str | None = None,
    affected_bindings: Iterable[str] = (),
    unaffected_bindings: Iterable[str] = (),
) -> GoalAdoptionVerdict:
    """Judge one goal-change answer against real artefacts (fail-closed).

    Without a supply, a baseline and both goal texts the request text alone can
    never adopt anything. The substantive diff is computed from the texts
    (formatting-only changes need no re-approval), and ``approve`` additionally
    needs the verified T17/T10/T07/T18 supply whose note names the new target
    version.
    """

    if goal_before_text is None or goal_after_text is None:
        return _blocked_goal("blocked", ("missing_goal_text",), unaffected_bindings)
    comparison = decision_validity.compare_dependency_values(
        "structured", goal_before_text, goal_after_text
    )
    substantive = comparison.status == "changed"
    if not substantive:
        return GoalAdoptionVerdict(
            status="no_change",
            adopt=False,
            baseline_refresh=False,
            version=None,
            reasons=("no_substantive_change",),
            reusable_bindings=tuple(unaffected_bindings),
        )
    if choice not in GOAL_ADOPTION_CHOICES:
        return _blocked_goal("blocked", ("unknown_goal_choice",), unaffected_bindings)
    if choice != "approve":
        return _blocked_goal(
            "not_adopted",
            (f"{choice}_does_not_adopt_goal",),
            unaffected_bindings,
        )
    if not isinstance(baseline_path, (str, pathlib.Path)):
        return _blocked_goal("blocked", ("missing_goal_baseline",), unaffected_bindings)
    baseline = _read_json_object(pathlib.Path(baseline_path))
    if baseline is None:
        return _blocked_goal("blocked", ("missing_goal_baseline",), unaffected_bindings)
    current_version = baseline.get("goal_version")

    reasons: list[str] = []
    missing = [
        field
        for field in _GOAL_REQUIRED_FIELDS
        if not isinstance(getattr(request, field), str)
        or not getattr(request, field).strip()
    ]
    if missing:
        reasons.append("incomplete_goal_adoption_note")
    if not isinstance(current_version, str) or not current_version:
        reasons.append("invalid_goal_baseline")
    elif request.previous_version != current_version:
        reasons.append("baseline_version_mismatch")
    if request.previous_version == request.current_version:
        reasons.append("no_version_change")
    if request.target_version != request.current_version:
        reasons.append("approval_version_mismatch")
    if not isinstance(pm_note, str) or not pm_note.strip():
        reasons.append("missing_pm_note")
    elif request.target_version not in pm_note:
        reasons.append("note_version_mismatch")
    if reasons:
        return _blocked_goal("blocked", reasons, unaffected_bindings)

    supply_reasons, gate = verify_supply(
        supply,
        gate_kind="goal-change",
        expected_gate_key=request.key,
        required_scope=(
            f"goal-adopt:{request.key}",
            f"goal-version:{request.target_version}",
        ),
        authority_ref=request.authority_ref,
        note=pm_note,
    )
    if supply is not None and gate is not None:
        before_sha = hashlib.sha256(goal_before_text.encode("utf-8")).hexdigest()
        after_sha = hashlib.sha256(goal_after_text.encode("utf-8")).hexdigest()
        gate_reasons = list(supply_reasons)
        if gate.goal_sha256_before != before_sha:
            gate_reasons.append("goal_before_sha_mismatch")
        if gate.goal_sha256_after != after_sha:
            gate_reasons.append("goal_after_sha_mismatch")
        supply_reasons = tuple(dict.fromkeys(gate_reasons))
    if supply_reasons:
        return _blocked_goal("blocked", supply_reasons, unaffected_bindings)
    return GoalAdoptionVerdict(
        status="adopted",
        adopt=True,
        baseline_refresh=True,
        version=request.target_version,
        reasons=(),
        previous_version=current_version,
        reverification_required=tuple(affected_bindings),
        reusable_bindings=tuple(unaffected_bindings),
        _issued=_ISSUED,
    )


def apply_goal_adoption(
    baseline_path: pathlib.Path | str, verdict: GoalAdoptionVerdict
) -> bool:
    """The only sanctioned goal-baseline writer (``{goal_version}`` JSON).

    Returns ``False`` without touching the file unless the verdict both adopts
    and refreshes the baseline. The current baseline version must still be the
    one the verdict judged (no stale approval replay). A malformed existing
    file raises instead of being replaced (history/state is never guessed).
    """

    path = pathlib.Path(baseline_path)
    if verdict._issued is not _ISSUED:
        return False
    if not (verdict.adopt and verdict.baseline_refresh and verdict.version):
        return False
    data: dict[str, object] = {}
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        try:
            loaded = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"goal baseline is not JSON: {path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"goal baseline is not an object: {path}")
        data = dict(loaded)
        if verdict.previous_version is None or data.get("goal_version") != verdict.previous_version:
            return False
    data["goal_version"] = verdict.version
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)
    return True


# --- H08: exact frozen-contract change (AC-028 / AC-029) ---------------------
#
# The gate's free-form note is not enough: the change request and the approval
# are two structured records over the *same* key, item set and before/after
# shas. Only then may the freeze sidecar move. The spec/design text itself is
# never rewritten, and every adoption is appended to an audit log.

_FREEZE_CHANGE_REQUIRED_FIELDS: tuple[str, ...] = (
    "key",
    "reason",
    "commitment_impact",
    "evidence_impact",
    "authority_ref",
    "reverification_plan",
)


def _identity_versions(identity: ContractIdentity) -> dict[str, str]:
    return {**identity.acs, **identity.vcs}


def _freeze_versions(freeze: Mapping[str, object]) -> dict[str, str]:
    return {
        **_freeze_family(freeze, "spec"),
        **_freeze_family(freeze, "design"),
    }


@dataclasses.dataclass(frozen=True)
class FreezeChangeRequest:
    """The PM-prepared frozen-entry change: exact items and versions."""

    key: str
    items: tuple[str, ...]
    before_versions: Mapping[str, str]
    after_versions: Mapping[str, str]
    reason: str
    commitment_impact: str
    evidence_impact: str
    authority_ref: str
    reverification_plan: str
    acceptance_reductions: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class FreezeChangeApproval:
    """The approving answer: only the exact requested items/versions.

    ``authority_ref`` is an identity to resolve, never a grant. The real record
    must exist in the verified :class:`TrustedSupply` authority source.
    """

    approval_ref: str
    key: str
    items: tuple[str, ...]
    before_versions: Mapping[str, str]
    after_versions: Mapping[str, str]
    reverification_plan: str
    authority_source: str
    authority_ref: str = ""
    acceptance_reductions: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class FreezeChangeVerdict:
    """Outcome of the structured change judgement."""

    status: str
    reasons: tuple[str, ...]
    approved_items: tuple[str, ...] = ()
    reverification_items: tuple[str, ...] = ()
    covers_only_requested_change: bool = False


def _freeze_note_problems(request: "FreezeChangeRequest", note: str | None) -> tuple[str, ...]:
    """The PM note must name the key, items, reason, impacts and re-check plan."""

    if not isinstance(note, str) or not note.strip():
        return ("missing_pm_note",)
    required = [
        request.key,
        request.reason,
        request.commitment_impact,
        request.evidence_impact,
        request.reverification_plan,
        *request.items,
    ]
    if any(value not in note for value in required):
        return ("incomplete_pm_note",)
    return ()


def assess_freeze_change(
    request: FreezeChangeRequest,
    approval: FreezeChangeApproval | None,
    *,
    supply: TrustedSupply | None = None,
    pm_note: str | None = None,
) -> FreezeChangeVerdict:
    """Judge a frozen AC/VC change against real artefacts (fail-closed)."""

    reasons: list[str] = []
    missing = [
        field
        for field in _FREEZE_CHANGE_REQUIRED_FIELDS
        if not isinstance(getattr(request, field), str)
        or not getattr(request, field).strip()
    ]
    if not tuple(request.items):
        missing.append("items")
    if missing:
        reasons.append("incomplete_change_request")
    if not tuple(request.items) or any(not item.strip() for item in request.items):
        reasons.append("invalid_change_items")
    if not isinstance(request.before_versions, Mapping) or not isinstance(
        request.after_versions, Mapping
    ):
        reasons.append("missing_version_binding")

    if approval is None:
        reasons.append("missing_approval")
        return FreezeChangeVerdict("blocked", tuple(reasons))

    if approval.key != request.key:
        reasons.append("reused_unrelated_change_approval")
    requested = set(request.items)
    approved = set(approval.items)
    if requested - approved:
        reasons.append("approval_scope_too_narrow")
    if approved - requested:
        reasons.append("approval_scope_expansion")

    version_mismatch = False
    for item in request.items:
        if (
            approval.before_versions.get(item) != request.before_versions.get(item)
            or approval.after_versions.get(item) != request.after_versions.get(item)
            or not request.before_versions.get(item)
            or not request.after_versions.get(item)
        ):
            version_mismatch = True
            break
    if version_mismatch:
        reasons.append("approval_version_mismatch")
    if not isinstance(approval.reverification_plan, str) or not (
        approval.reverification_plan.strip()
    ):
        reasons.append("missing_reverification_plan")
    if approval.authority_ref != request.authority_ref:
        reasons.append("approval_authority_mismatch")
    reasons.extend(_freeze_note_problems(request, pm_note))

    unauthorized = sorted(
        set(request.acceptance_reductions) - set(approval.acceptance_reductions)
    )
    if unauthorized:
        reasons.append("unauthorized_acceptance_reduction")

    supply_reasons, _gate = verify_supply(
        supply,
        gate_kind=None,
        expected_gate_key=request.key,
        required_scope=(
            f"contract-change:{request.key}",
            *(f"contract-item:{item}" for item in request.items),
        ),
        authority_ref=request.authority_ref,
        require_authorizes=("contract-change",),
        note=pm_note,
    )
    reasons.extend(supply_reasons)

    unique = tuple(dict.fromkeys(reasons))
    if unique:
        return FreezeChangeVerdict("blocked", unique)
    return FreezeChangeVerdict(
        "approved",
        (),
        approved_items=tuple(request.items),
        reverification_items=tuple(request.items),
        covers_only_requested_change=True,
    )


@contextlib.contextmanager
def contract_publication_lock(key_dir: pathlib.Path | str):
    """Serialize H08 adoption and current proof publication; never transport."""
    key_dir = pathlib.Path(key_dir).resolve()
    path = key_dir.parent.parent / ".mw" / f"contract-publication-{key_dir.name}.lock"
    mw_common.acquire_lock(path, retries=600, base_delay=0.01, deadline_s=30)
    try:
        yield
    finally:
        mw_common.release_lock(path)


def adoption_log_path(key_dir: pathlib.Path | str) -> pathlib.Path:
    """Append-only log of approved frozen-entry adoptions (never rewritten)."""

    return pathlib.Path(key_dir) / FREEZE_DIR_NAME / "contract-adoptions.jsonl"


def _append_adoption(key_dir: pathlib.Path, request: FreezeChangeRequest,
                     approval: FreezeChangeApproval) -> None:
    path = adoption_log_path(key_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": 1,
        "key": request.key,
        "adopted_at": _iso_now(),
        "approval_ref": approval.approval_ref,
        "items": list(request.items),
        "before_versions": dict(request.before_versions),
        "after_versions": dict(request.after_versions),
        "reverification_plan": approval.reverification_plan,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def refreeze_approved_change(
    key_dir: pathlib.Path | str,
    request: FreezeChangeRequest,
    approval: FreezeChangeApproval | None,
    *,
    supply: TrustedSupply | None = None,
    pm_note: str | None = None,
    spec_text: str | None = None,
    design_text: str | None = None,
) -> tuple[FreezeChangeVerdict, pathlib.Path | None]:
    """Move the freeze anchor only for the exact approved change.

    Preconditions (all fail-closed): a usable existing anchor, no drifted item
    outside ``request.items``, every requested item has changed, the request's
    before/after shas match the anchor/current text, and the approval is bound
    to the real T17 gate/T10 lifecycle/T07 authority/hard budget. The contract
    text files are never touched and the adoption log is append-only.
    """

    key_dir = pathlib.Path(key_dir)
    freeze = read_freeze(key_dir)
    if freeze is None:
        return FreezeChangeVerdict("blocked", ("no-freeze-anchor",)), None
    if spec_text is None:
        spec_text = _read_text(key_dir / SPEC_FILE_NAME)
    if design_text is None:
        design_text = _read_text(key_dir / DESIGN_FILE_NAME)
    identity = extract_contract(spec_text, design_text)
    current_versions = _identity_versions(identity)
    frozen_versions = _freeze_versions(freeze)
    diff = diff_contract(identity, freeze)
    expected = set(request.items)
    actual = set(diff.changed_ids)

    reasons: list[str] = []
    if actual - expected:
        reasons.append("unrequested_contract_drift")
    if expected - actual:
        reasons.append("requested_item_unchanged")
    for item in request.items:
        if request.before_versions.get(item) != frozen_versions.get(item):
            reasons.append("anchor_version_mismatch")
            break
    for item in request.items:
        if request.after_versions.get(item) != current_versions.get(item):
            reasons.append("current_version_mismatch")
            break
    if reasons:
        return FreezeChangeVerdict("blocked", tuple(reasons)), None

    verdict = assess_freeze_change(request, approval, supply=supply, pm_note=pm_note)
    if verdict.status != "approved" or approval is None:
        return verdict, None

    freeze_key = freeze.get("key")
    key = freeze_key if isinstance(freeze_key, str) and freeze_key else request.key
    updated = build_freeze(key, spec_text, design_text)
    path = write_freeze(key_dir, updated)
    _append_adoption(key_dir, request, approval)
    return verdict, path


def contract_reverification_binding(key_dir: pathlib.Path | str) -> dict[str, object]:
    """Read exact adopted item versions; malformed or drifted history refuses.

    This is a requirement binding, never proof that verification ran. The
    adoption content digest excludes presentation-only JSON formatting.
    """
    key_dir = pathlib.Path(key_dir)
    path = adoption_log_path(key_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"status": "unaffected", "versions": {}, "adoptions_sha256": None}
    except (OSError, UnicodeError):
        return {"status": "needs-rerun", "reason": "adoption-history-unreadable"}
    rows: list[dict[str, object]] = []
    versions: dict[str, str] = {}
    try:
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if (not isinstance(row, dict) or row.get("schema") != 1
                    or row.get("key") != key_dir.name
                    or not isinstance(row.get("items"), list) or not row["items"]
                    or not isinstance(row.get("after_versions"), dict)):
                raise ValueError("invalid adoption")
            for item in row["items"]:
                digest = row["after_versions"].get(item)
                if (not isinstance(item, str) or not isinstance(digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
                    raise ValueError("invalid adopted version")
                versions[item] = digest
            rows.append(row)
        current = _identity_versions(extract_contract(
            (key_dir / SPEC_FILE_NAME).read_text(encoding="utf-8"),
            (key_dir / DESIGN_FILE_NAME).read_text(encoding="utf-8")))
        freeze = read_freeze(key_dir)
        if freeze is None or any(
            current.get(item) != digest or _freeze_versions(freeze).get(item) != digest
            for item, digest in versions.items()
        ):
            raise ValueError("adopted version drift")
        canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
    except (OSError, UnicodeError, ValueError, TypeError):
        return {"status": "needs-rerun", "reason": "adoption-history-or-version-unproven"}
    return {"status": "pending" if versions else "unaffected",
            "versions": dict(sorted(versions.items())),
            "adoptions_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def pending_reverification(
    verdict: FreezeChangeVerdict, verified_items: Iterable[str]
) -> tuple[str, ...]:
    """Items still pending a real re-verification after the change."""

    done = set(verified_items)
    return tuple(item for item in verdict.reverification_items if item not in done)


# --- Normal-PM consume surface (T20-pm-source) -------------------------------
#
# The strict H06/H07/H08 layers above are only reachable when a caller already
# owns a ``TrustedSupply``. A normally claimed PM does not: it must not have to
# assemble an authority source, a usage number or a bearer. These functions are
# the controlled consumption entry for that caller.
#
# They read the *real* source on every call: the protected ``host.json`` via
# ``operator_authority.read_pm_authority``, the live project claim in
# ``_index.parallel``, the T10 request/basis/note/consumed rows, the T17 gate
# file and the original policy (including its pinned SHA-256). The caller
# supplies only the PM-prepared business material: the recorded
# ``dp-gate-approve`` reference/gate, the PM note and the concrete change plan.
#
# Two phases are deliberate. ``prepare_*`` judges and returns a sealed
# observation; ``apply_*`` re-reads the same source and re-runs the original
# strict assessment immediately before the original writer. A revoked record,
# a changed claim, a moved gate/version/note or an exhausted budget between the
# two calls therefore refuses the write; an old observation is never a bearer.
#
# None of these functions mints, signs or records a second approval. The
# returned ``receipt`` is evidence about the real decision/action, not a grant.

_PM_DECISION_PREFIX = "dp-gate-approve:"
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ROUND_USAGE_KINDS = frozenset({"task-card-rounds"})


@dataclasses.dataclass(frozen=True)
class PmDecisionBinding:
    """Verified identity of one recorded PM decision and its real source.

    The ``supply`` is the ordinary strict layer's object. ``authority`` is the
    read-only ``operator_authority.PmAuthority`` observation used to build it;
    it is re-read (never trusted as a cached grant) before a write.
    """

    project_root: pathlib.Path
    key: str
    gate_id: str
    decision_ref: str
    matter_ref: str
    substantive_version: str
    pm_note: str
    choice: str
    claim_id: str
    policy_sha256: str
    authority_ref: str
    gate_kind: str | None
    expected_gate_key: str
    required_scope: tuple[str, ...]
    require_authorizes: tuple[str, ...]
    require_files: tuple[str, ...]
    target_key: str | None
    supply: TrustedSupply
    authority: object


@dataclasses.dataclass(frozen=True)
class PmConsumption:
    """Outcome of one normal-PM consumption call.

    ``status`` is one of ``prepared``/``authorized`` (sealed, not yet written),
    ``applied`` (the original writer really changed the target), ``blocked``,
    ``not_adopted`` or ``no_change``. ``written`` is only true after a real
    write; ``action`` names that write. ``receipt`` carries the original
    decision identity and the action facts for the conductor/T26 caller.
    """

    family: str
    status: str
    reasons: tuple[str, ...]
    binding: PmDecisionBinding | None
    verdict: object | None
    action: str | None
    written: bool
    target: str | None
    receipt: Mapping[str, object]
    plan: Mapping[str, object] = dataclasses.field(default_factory=dict)


def _pm_blocked(
    family: str,
    status: str,
    reasons: Iterable[str],
    *,
    binding: PmDecisionBinding | None = None,
    verdict: object | None = None,
    plan: Mapping[str, object] | None = None,
    receipt: Mapping[str, object] | None = None,
) -> PmConsumption:
    return PmConsumption(
        family=family,
        status=status,
        reasons=tuple(dict.fromkeys(reasons)),
        binding=binding,
        verdict=verdict,
        action=None,
        written=False,
        target=None,
        receipt=dict(receipt or {}),
        plan=dict(plan or {}),
    )


def _pm_gate_path(project_root: pathlib.Path, gate_id: str) -> pathlib.Path:
    return project_root / ".agenticdoc" / "_autopilot" / "gates" / (gate_id + ".md")


_FAMILY_EFFECT_DIR = pathlib.Path(".agenticdoc") / "_autopilot" / "family-effects"

#: The gate's own persisted submission; the goal-change gate carries no
#: ``write_scope`` field, so its declared object is the ``baseline_path`` frozen
#: here when the gate was prepared (the same artifact the family consumer
#: re-reads before it writes).
_PREPARED_GATE_DIR = pathlib.Path(".agenticdoc") / "_autopilot" / "prepared-gates"


def family_effect_path(project_root: pathlib.Path | str, gate: object) -> pathlib.Path:
    """The product-written reservation/effect record for one family gate."""

    identity = getattr(gate, "decision_ref", None) or getattr(gate, "id", None) or ""
    digest = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:32]
    return pathlib.Path(project_root) / _FAMILY_EFFECT_DIR / f"{getattr(gate, 'kind', '')}-{digest}.json"


# --- H06 actually adopted goal version (AC-039 / AC-052) --------------------
#
# A changed project goal.md and a caller-supplied ``baseline_path`` are not
# proof of what a key adopted. The only trusted locator is the canonical family
# effect record the conductor writes after its protected goal-baseline writer
# ran, tied to the answered goal-change gate. A bound target is read only when
# it still resolves inside the project.

_ADOPTED_GOAL_MAX_BYTES = 256 * 1024


@dataclasses.dataclass(frozen=True)
class AdoptedGoalBinding:
    """The goal version one key actually adopted, or why it cannot be proven."""

    state: str  # absent | present | unproven
    version: str | None = None
    target: str | None = None  # project-relative POSIX path
    sha256: str | None = None
    decision_ref: str | None = None
    reason: str = ""


def _goal_semantic_sha(target: str, version: str) -> str:
    payload = json.dumps(
        {"target": target, "version": version},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_epoch(value: object) -> float | None:
    """One recorded ISO-8601 time as epoch seconds; ``None`` when unusable."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.timestamp()


def _goal_record_epoch(record: Mapping[str, object], gate: object | None) -> float | None:
    values: list[object] = [record.get("recorded_at"), record.get("reserved_at")]
    if gate is not None:
        values.append(getattr(gate, "created_at", None))
    for value in values:
        epoch = _parse_epoch(value)
        if epoch is not None:
            return epoch
    return None


def _normalised_target(root: pathlib.Path, value: object) -> str | None:
    """Case/format-normalised absolute text of a target; never touches disk."""

    if not isinstance(value, str) or not value.strip():
        return None
    path = pathlib.Path(value)
    if not path.is_absolute():
        path = root / path
    return os.path.normcase(os.path.abspath(str(path)))


def _same_target(root: pathlib.Path, left: object, right: object) -> bool:
    first = _normalised_target(root, left)
    second = _normalised_target(root, right)
    return first is not None and first == second


def _prepared_gate_baseline(root: pathlib.Path, gate: object) -> str | None:
    """The baseline path the original goal-change gate was prepared for.

    A goal-change gate carries no ``write_scope``: its declared object is the
    ``baseline_path`` frozen in the gate's own prepared submission, bound to the
    gate by the same gate id / matter / version / note identity the family
    consumer itself re-reads before it writes. This reuses that existing gate
    artifact (no new registry/ledger/grant); a missing or re-bound preparation
    is no proof at all.
    """

    gate_id = getattr(gate, "id", None)
    if not isinstance(gate_id, str) or gates.GATE_ID_RE.fullmatch(gate_id) is None:
        return None
    record = _read_json_object(root / _PREPARED_GATE_DIR / (gate_id + ".json"))
    if record is None:
        return None
    note = getattr(gate, "pm_note", None) or ""
    if (
        record.get("gate_id") != gate_id
        or record.get("family") != "goal-adoption"
        or record.get("matter_ref") != getattr(gate, "matter_ref", None)
        or record.get("substantive_version")
        != getattr(gate, "substantive_version", None)
        or record.get("pm_note_sha256")
        != hashlib.sha256(note.encode("utf-8")).hexdigest()
    ):
        return None
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        return None
    baseline = payload.get("baseline_path")
    return baseline if isinstance(baseline, str) and baseline.strip() else None


#: The three feedback facts that witness one family action end to end.
_FAMILY_EVIDENCE_STAGES = ("consumed", "executed", "settled")

#: The ``object_sha256`` *member* of a completion receipt as the producer writes
#: it. The managed store clips a ``result`` row at 512 bytes, so the row may be a
#: prefix of the receipt; the member itself stays complete inside that prefix.
_RESULT_OBJECT_MEMBER_RE = re.compile(
    r'"object_sha256"\s*:\s*"([0-9a-fA-F]{64})"'
)
_SHA256_TEXT_RE = re.compile(r"[0-9a-fA-F]{64}")


@dataclasses.dataclass(frozen=True)
class _FamilyAssociation:
    """The real producer identity one adopted-goal T10 chain must join on.

    Every value is read from an existing producer artefact: ``key`` from the PM
    effect/gate, ``logical_id`` from the ``dp-gate-approve:<logical_id>``
    decision reference, ``task_key`` from the decision's own ``record-start``
    fact (the same row the family consumer rebuilds its meta from) and
    ``claim_id`` from the completion receipt the original writer returned.
    """

    key: str
    task_key: str | None
    logical_id: str
    claim_id: str
    writer_action: str


@dataclasses.dataclass(frozen=True)
class _FamilyEvidence:
    """T10 rows that witness one family write, plus what is missing/contradictory."""

    consumed: tuple[Mapping[str, object], ...] = ()
    executed: tuple[Mapping[str, object], ...] = ()
    settled: tuple[Mapping[str, object], ...] = ()
    problems: tuple[str, ...] = ()


def _result_object_receipt(value: object) -> str | None:
    """The object digest a T10 ``executed.result`` *structurally* carries.

    The family producer stores the sorted completion receipt there, and the
    managed store clips free text at 512 bytes, so the row may be a prefix of
    that JSON. Both cases are handled positively: a complete JSON object is
    parsed, and a clipped prefix is accepted only when its ``object_sha256``
    member is itself complete. A digest that merely occurs somewhere in the text
    (a note, a path, an unrelated field) is never an object receipt.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        parsed = None
    if isinstance(parsed, Mapping):
        digest = parsed.get("object_sha256")
        if isinstance(digest, str) and _SHA256_TEXT_RE.fullmatch(digest) is not None:
            return digest
        return None
    if not value.lstrip().startswith("{"):
        return None
    match = _RESULT_OBJECT_MEMBER_RE.search(value)
    return match.group(1) if match is not None else None


def _family_row_actor(row: Mapping[str, object]) -> tuple[str | None, str | None]:
    actor = row.get("actor")
    if not isinstance(actor, Mapping):
        return (None, None)
    kind = actor.get("kind")
    actor_id = actor.get("id")
    return (
        kind if isinstance(kind, str) else None,
        actor_id if isinstance(actor_id, str) else None,
    )


def _family_execution_evidence(
    project_root: pathlib.Path,
    decision_ref: object,
    object_sha: object,
    *,
    association: "_FamilyAssociation | None" = None,
) -> _FamilyEvidence:
    """T10 rows that really witness one exact family write.

    Rows are always restricted to this project's production scope
    (:func:`_unreadable_lifecycle`) and to the same ``decision_id``. Without an
    ``association`` the filter is the historical one (same decision, digest
    text in ``result``); that shape is what :func:`_pm_effect_evidence` reuses.

    With an ``association`` (the adopted-goal chain) the rows must also belong
    to the same key, task and logical decision, must have been recorded by the
    exact executor the completion receipt names (never the current claim), must
    carry the digest as a structural ``object_sha256`` member, must tell one
    non-decreasing, duplicate-free story and the settlement must be a real
    success (``outcome == "ok"``). Anything else is a listed problem, never a
    silent pass.
    """

    rows = _unreadable_lifecycle(project_root)
    same_decision = [
        row
        for row in rows
        if row.get("kind") == "lifecycle"
        and row.get("lifecycle") in _FAMILY_EVIDENCE_STAGES
        and row.get("decision_id") == decision_ref
    ]
    if association is None:
        return _FamilyEvidence(
            executed=tuple(
                row
                for row in same_decision
                if row.get("lifecycle") == "executed"
                and str(object_sha) in str(row.get("result") or "")
            ),
            settled=tuple(
                row
                for row in same_decision
                if row.get("lifecycle") == "settled"
            ),
        )

    problems: list[str] = []
    by_stage: dict[str, tuple[Mapping[str, object], ...]] = {}
    for stage in _FAMILY_EVIDENCE_STAGES:
        stage_rows = [
            row for row in same_decision if row.get("lifecycle") == stage
        ]
        owned = [
            row
            for row in stage_rows
            if row.get("key") == association.key
            and row.get("task_key") == association.task_key
            and row.get("logical_id") == association.logical_id
        ]
        if stage_rows and not owned:
            problems.append(
                f"the {stage} lifecycle receipt belongs to a different key/task/logical decision"
            )
        elif owned:
            kind, actor_id = _family_row_actor(owned[0])
            if (kind, actor_id) != ("system", association.claim_id):
                problems.append(
                    f"the {stage} lifecycle receipt was recorded by a different executor"
                )
                owned = []
        by_stage[stage] = tuple(owned)

    consumed = by_stage["consumed"]
    writer_executed = tuple(
        row
        for row in by_stage["executed"]
        if row.get("reason") == association.writer_action
        and row.get("action") in decision_lifecycle.EXECUTED_ACTIONS
    )
    if by_stage["executed"] and not writer_executed:
        problems.append(
            "the executed lifecycle receipt is not the original writer action"
        )
    executed = tuple(
        row
        for row in writer_executed
        if isinstance(object_sha, str)
        and _result_object_receipt(row.get("result")) == object_sha
    )
    if writer_executed and not executed:
        problems.append(
            "the executed lifecycle receipt does not carry this object receipt"
        )
    settled = by_stage["settled"]
    successful = tuple(row for row in settled if row.get("outcome") == "ok")
    if settled and not successful:
        problems.append("the adoption settlement is not a successful outcome")

    for stage, stage_list in (
        ("consumed", consumed),
        ("executed", executed),
        ("settled", settled),
    ):
        if not stage_list:
            problems.append(
                f"the adoption write has no {stage} lifecycle receipt"
            )
        elif len(stage_list) > 1:
            problems.append(
                f"the adoption write has more than one {stage} lifecycle receipt"
            )

    chain = (
        ("consumed", consumed),
        ("executed", executed),
        ("settled", successful),
    )
    if all(len(stage_list) == 1 for _stage, stage_list in chain):
        epochs: list[float | None] = []
        for stage, stage_list in chain:
            epoch = _parse_epoch(stage_list[0].get("ts"))
            if epoch is None:
                problems.append(
                    f"the {stage} lifecycle receipt has no readable recording time"
                )
            epochs.append(epoch)
        readable = [value for value in epochs if value is not None]
        if len(readable) == len(epochs) and readable != sorted(readable):
            problems.append(
                "the adoption lifecycle receipts are not in recording order"
            )
    return _FamilyEvidence(
        consumed=consumed,
        executed=executed,
        settled=settled,
        problems=tuple(problems),
    )


def _goal_adoption_association(
    root: pathlib.Path,
    key: str,
    gate: object,
    receipt: Mapping[str, object],
    writer_action: object,
) -> "_FamilyAssociation | str":
    """The real producer identity the adopted-goal T10 chain must join on.

    ``task_key`` is not guessed and never backfilled from the current claim: it
    is read from the decision's own pre-transport ``record-start`` fact, the same
    row the family consumer rebuilds its meta from (one PM record for the logical
    id and key, or no proof at all).
    """

    decision_ref = getattr(gate, "decision_ref", None)
    if not isinstance(decision_ref, str) or not decision_ref:
        return "the adoption gate has no decision reference"
    logical_id = decision_ref.partition(":")[2]
    if not logical_id:
        return "the adoption decision reference has no logical id"
    claim_id = receipt.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id.strip():
        return "the adoption completion receipt names no executor"
    if not isinstance(writer_action, str) or not writer_action.strip():
        return "the adoption effect names no original writer action"
    task_keys = {
        row.get("task_key")
        for row in _unreadable_lifecycle(root)
        if row.get("kind") == "record-start"
        and row.get("logical_id") == logical_id
        and row.get("key") == key
        and row.get("initiator_role") == "pm"
    }
    if len(task_keys) != 1:
        return "the adoption decision has no single PM record-start"
    return _FamilyAssociation(
        key=key,
        task_key=next(iter(task_keys)),
        logical_id=logical_id,
        claim_id=claim_id.strip(),
        writer_action=writer_action.strip(),
    )


def _adopted_goal_candidate(
    root: pathlib.Path,
    key: str,
    record: Mapping[str, object],
    gate: object | None,
    receipt_key: str | None,
    gate_key: str | None,
    record_path: pathlib.Path | None,
) -> tuple[float | None, str, AdoptedGoalBinding] | None:
    """One goal-adoption effect record -> (time, state, binding).

    The locator is proven by the chain that produced it, never by its caller:
    the record must sit at its gate-derived canonical path, the answered
    goal-change gate must name the same decision/matter/version, and the
    completion receipt must agree with the executed/settled lifecycle rows on
    the same key, target and object digest. Only then are the target bytes
    read.
    """

    epoch = _goal_record_epoch(record, gate)

    def unproven(reason: str) -> tuple[float | None, str, AdoptedGoalBinding]:
        return (epoch, "unproven", AdoptedGoalBinding("unproven", reason=reason))

    if receipt_key and gate_key and receipt_key != gate_key:
        return unproven("the adoption receipt and gate name different keys")
    if gate is None:
        return unproven("the adoption gate is missing or unreadable")
    if (
        gate_key != key
        or getattr(gate, "id", None) != record.get("gate_id")
        or getattr(gate, "decision_ref", None) != record.get("decision_ref")
    ):
        return unproven("the adoption gate does not match its effect receipt")
    if getattr(gate, "kind", None) != "goal-change":
        return unproven("the adoption gate is not a goal-change gate")
    status = record.get("status")
    if status in ("in-progress", "unknown"):
        return unproven(
            f"the adoption effect is {status}, not a proven applied consumption"
        )
    if status != "applied":
        return None  # a refusal never moved the baseline
    if (
        getattr(gate, "business", None) != "approve"
        or getattr(gate, "effect", None) != "applied"
        or getattr(gate, "transport", None) != "answered"
    ):
        return unproven("the adoption gate is not an applied answered approve")
    if record_path is None or not _same_target(
        root, str(record_path), str(family_effect_path(root, gate))
    ):
        return unproven(
            "the adoption effect record is not stored at its gate-derived path"
        )
    receipt = record.get("receipt")
    if not isinstance(receipt, Mapping) or not receipt:
        return unproven("the applied adoption has no canonical completion receipt")
    if (
        receipt.get("action") != "goal-baseline-adoption"
        or receipt.get("family") != "pm-consume"
        or receipt.get("decision_ref") != record.get("decision_ref")
        or receipt.get("gate_id") != record.get("gate_id")
        or receipt.get("key") != key
        or receipt.get("matter_ref") != getattr(gate, "matter_ref", None)
        or receipt.get("substantive_version")
        != getattr(gate, "substantive_version", None)
        or receipt.get("pm_note") != getattr(gate, "pm_note", None)
        or receipt.get("choice") != "approve"
        or receipt.get("verdict_status") != "adopted"
    ):
        return unproven("the adoption completion receipt does not match its gate/effect")
    if record.get("action") != "goal-adoption":
        return unproven(
            "the adoption effect record is not the goal-adoption writer action"
        )
    target_raw = record.get("target")
    if not isinstance(target_raw, str) or not target_raw:
        return unproven("the applied adoption has no baseline target")
    if not _same_target(root, target_raw, receipt.get("target")):
        return unproven(
            "the adoption record target does not match its completion receipt"
        )
    permitted = _prepared_gate_baseline(root, gate)
    if permitted is None:
        return unproven("the goal-change gate has no usable prepared baseline target")
    if not _same_target(root, target_raw, permitted):
        return unproven(
            "the adopted goal baseline target is not the one the goal-change gate authorized"
        )
    write_scope = getattr(gate, "write_scope", None)
    if write_scope and not any(
        _same_target(root, target_raw, item) for item in write_scope
    ):
        return unproven("the adopted goal baseline target is outside the gate write scope")
    object_sha = record.get("object_sha256")
    if (
        not isinstance(object_sha, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", object_sha) is None
    ):
        return unproven("the adoption object receipt is missing")
    if receipt.get("object_sha256") != object_sha:
        return unproven(
            "the adoption record object receipt does not match its completion receipt"
        )
    association = _goal_adoption_association(
        root, key, gate, receipt, record.get("action")
    )
    if isinstance(association, str):
        return unproven(association)
    evidence = _family_execution_evidence(
        root,
        getattr(gate, "decision_ref", None),
        object_sha,
        association=association,
    )
    if evidence.problems:
        return unproven(evidence.problems[0])
    target = pathlib.Path(target_raw)
    if not target.is_absolute():
        target = root / target
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError):
        return unproven("the adopted goal baseline target is missing")
    root_resolved = root.resolve()
    try:
        relative = resolved.relative_to(root_resolved)
    except ValueError:
        return unproven("the adopted goal baseline target is outside the project")
    if not resolved.is_file():
        return unproven("the adopted goal baseline target is not a file")
    try:
        if resolved.stat().st_size > _ADOPTED_GOAL_MAX_BYTES:
            return unproven("the adopted goal baseline target is too large")
        raw_bytes = resolved.read_bytes()
        text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return unproven("the adopted goal baseline target is unreadable")
    try:
        data = json.loads(text)
    except ValueError:
        return unproven("the adopted goal baseline target is not valid JSON")
    if not isinstance(data, dict):
        return unproven("the adopted goal baseline target is not a JSON object")
    version = data.get("goal_version")
    if not isinstance(version, str) or not version.strip():
        return unproven("the adopted goal baseline has no goal_version")
    receipt_version = receipt.get("version")
    if not isinstance(receipt_version, str) or receipt_version != version:
        return unproven(
            "the adoption receipt version does not match the baseline goal_version"
        )
    target_text = relative.as_posix()
    return (
        epoch,
        "present",
        AdoptedGoalBinding(
            "present",
            version=version,
            target=target_text,
            sha256=_goal_semantic_sha(target_text, version),
            decision_ref=(
                str(record.get("decision_ref"))
                if isinstance(record.get("decision_ref"), str)
                else None
            ),
        ),
    )


def adopted_goal_binding(
    project_root: pathlib.Path | str, key: str
) -> AdoptedGoalBinding:
    """Locate the goal version ``key`` really adopted from the canonical receipt.

    Only ``.agenticdoc/_autopilot/family-effects/goal-change-*.json`` records are
    considered; each is attributable to a key only through its receipt ``key``
    or the answered gate it names. A newer unproven consumption makes the
    current basis unproven instead of falling back to an older default.
    """

    root = pathlib.Path(project_root)
    if not isinstance(key, str) or not key:
        return AdoptedGoalBinding("absent")
    effects = root / _FAMILY_EFFECT_DIR
    try:
        paths = sorted(effects.glob("goal-change-*.json"))
    except OSError:
        paths = []
    candidates: list[tuple[float | None, str, AdoptedGoalBinding]] = []
    seen_gates: set[str] = set()
    for path in paths:
        record = _read_json_object(path)
        if record is None or record.get("family") != "goal-adoption":
            continue
        gate_id = record.get("gate_id")
        gate_valid = (
            isinstance(gate_id, str)
            and gates.GATE_ID_RE.fullmatch(gate_id) is not None
        )
        gate = None
        if gate_valid:
            seen_gates.add(gate_id)
            try:
                gate = gates.parse(_pm_gate_path(root, gate_id))
            except (OSError, ValueError):
                gate = None
        receipt = record.get("receipt")
        receipt_key = receipt.get("key") if isinstance(receipt, Mapping) else None
        receipt_key = (
            receipt_key
            if isinstance(receipt_key, str) and receipt_key
            else None
        )
        gate_key = gate.key if gate is not None else None
        if receipt_key and gate_key and receipt_key != gate_key:
            if key in (receipt_key, gate_key):
                epoch = _goal_record_epoch(record, gate)
                candidates.append(
                    (
                        epoch,
                        "unproven",
                        AdoptedGoalBinding(
                            "unproven",
                            reason="the adoption receipt and gate name different keys",
                        ),
                    )
                )
            continue
        if not gate_valid:
            # A non-canonical gate id is never a path to traverse; only the
            # record's own completion receipt may attribute it to a key, and it
            # is never a present proof.
            if receipt_key == key:
                candidates.append(
                    (
                        _goal_record_epoch(record, None),
                        "unproven",
                        AdoptedGoalBinding(
                            "unproven",
                            reason="the adoption gate id is not a canonical gate id",
                        ),
                    )
                )
            continue
        attributed = receipt_key or gate_key
        if attributed != key:
            continue
        candidate = _adopted_goal_candidate(
            root, key, record, gate, receipt_key, gate_key, path
        )
        if candidate is not None:
            candidates.append(candidate)
    # The gate is part of the canonical locator too: an applied goal-change
    # gate whose effect record/receipt was lost or corrupted must make the
    # current adopted goal unproven instead of silently defaulting to absent.
    gates_path = _pm_gate_path(root, "placeholder").parent
    try:
        goal_gates = list(gates.enumerate(gates_path))
    except (OSError, ValueError):
        goal_gates = []
    for gate in goal_gates:
        if (
            gate.historical
            or gate.kind != "goal-change"
            or gate.key != key
            or gate.id in seen_gates
            or gate.transport != "answered"
            or gate.business != "approve"
            or gate.effect not in ("applied", "in-progress", "unknown")
        ):
            continue
        epoch = _goal_record_epoch({}, gate)
        candidates.append(
            (
                epoch,
                "unproven",
                AdoptedGoalBinding(
                    "unproven",
                    reason="the canonical effect record for the applied adoption is missing",
                ),
            )
        )
    present = [item for item in candidates if item[1] == "present"]
    unproven = [item for item in candidates if item[1] == "unproven"]
    if not present and not unproven:
        return AdoptedGoalBinding("absent")
    if unproven:
        if any(item[0] is None for item in unproven):
            first = next(item for item in unproven if item[0] is None)
            return first[2]
        newest_present = max((item[0] or 0.0) for item in present) if present else None
        newest_unproven = max(unproven, key=lambda item: item[0] or 0.0)
        if newest_present is None or (newest_unproven[0] or 0.0) >= newest_present:
            return newest_unproven[2]
    if present:
        latest = max(
            present,
            key=lambda item: (
                item[0] or 0.0,
                item[2].decision_ref or "",
                item[2].target or "",
            ),
        )
        return latest[2]
    return AdoptedGoalBinding("absent")


def _file_sha256(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _pm_effect_evidence(project_root: pathlib.Path, gate: object) -> tuple[str, ...]:
    """Prove a normal-PM writer is bound to a real reservation or effect.

    ``in-progress`` is a controlled reservation persisted by the family
    consumer before the original writer runs; it is never a grant by itself
    (the strict supply also re-reads the live claim, T10 rows, authority and
    budget). ``applied`` must correspond to the actual object bytes and the
    recorded executed/settled events, not merely to a gate marker.
    """

    effect = getattr(gate, "effect", None)
    if effect not in ("in-progress", "applied"):
        return ("gate_effect_not_applied",)
    record = _read_json_object(family_effect_path(project_root, gate))
    if record is None:
        return ("gate_reservation_missing",)
    if (
        record.get("decision_ref") != getattr(gate, "decision_ref", None)
        or record.get("gate_id") != getattr(gate, "id", None)
        or record.get("matter_ref") != getattr(gate, "matter_ref", None)
        or record.get("substantive_version") != getattr(gate, "substantive_version", None)
    ):
        return ("gate_reservation_mismatch",)
    target = record.get("target")
    if not isinstance(target, str) or not target:
        return ("gate_reservation_missing",)
    if effect == "in-progress":
        if record.get("status") != "in-progress":
            return ("gate_reservation_missing",)
        return ()
    if record.get("status") != "applied":
        return ("gate_effect_unproven",)
    object_sha = record.get("object_sha256")
    if (
        not isinstance(object_sha, str)
        or not object_sha
        or _file_sha256(pathlib.Path(target)) != object_sha
    ):
        return ("gate_effect_unproven",)
    evidence = _family_execution_evidence(
        project_root, getattr(gate, "decision_ref", None), object_sha
    )
    if len(evidence.executed) != 1 or not evidence.settled:
        return ("gate_execution_unproven",)
    return ()


def _pm_gate_reasons(
    gate: object,
    *,
    gate_id: str,
    gate_kind: str | None,
    expected_gate_key: str | None,
    decision_ref: str,
    note: str | None,
    expected_matter_ref: str | None,
    expected_version: str | None,
    require_authorizes: tuple[str, ...],
    require_files: tuple[str, ...],
    effect_reasons: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if getattr(gate, "id", None) != gate_id:
        reasons.append("gate_identity_mismatch")
    if gate_kind is not None and getattr(gate, "kind", None) != gate_kind:
        reasons.append("wrong_gate_kind")
    if getattr(gate, "historical", False):
        reasons.append("historical_gate")
    if getattr(gate, "transport", None) != "answered":
        reasons.append("gate_not_answered")
    if getattr(gate, "business", None) != "approve":
        reasons.append("gate_not_approved")
    if effect_reasons is None:
        if getattr(gate, "effect", None) != "applied":
            reasons.append("gate_effect_not_applied")
    else:
        reasons.extend(effect_reasons)
    if expected_gate_key is not None and getattr(gate, "key", None) != expected_gate_key:
        reasons.append("gate_key_mismatch")
    if getattr(gate, "decision_ref", None) != decision_ref:
        reasons.append("gate_decision_mismatch")
    if not decision_ref.startswith(_PM_DECISION_PREFIX):
        reasons.append("not_prepared_gate_decision")
    matter = getattr(gate, "matter_ref", None)
    if not isinstance(matter, str) or not matter.strip():
        reasons.append("gate_matter_missing")
    elif expected_matter_ref is not None and matter != expected_matter_ref:
        reasons.append("matter_mismatch")
    version = getattr(gate, "substantive_version", None)
    if not isinstance(version, str) or not version.strip():
        reasons.append("gate_version_missing")
    elif expected_version is not None and version != expected_version:
        reasons.append("version_mismatch")
    if not getattr(gate, "model_basis", None):
        reasons.append("missing_model_basis")
    if not isinstance(note, str) or not note.strip():
        reasons.append("missing_pm_note")
    elif getattr(gate, "pm_note", None) != note:
        reasons.append("gate_note_mismatch")
    authorizes = getattr(gate, "authorizes", None)
    if require_authorizes and not set(require_authorizes).issubset(
        set(authorizes or ())
    ):
        reasons.append("gate_missing_authorizes")
    write_scope = getattr(gate, "write_scope", None)
    if require_files and not set(require_files).issubset(set(write_scope or ())):
        reasons.append("gate_write_scope")
    return tuple(dict.fromkeys(reasons))


def _pm_round_usage(project_root: pathlib.Path, key: str) -> int | None:
    """Cumulative rounds of this key from the real task-card attempt labels.

    ``state.used_rounds`` is the production reader the conductor/H11 recovery
    use for the same meter (one distinct attempt per loop). It is scoped to the
    key's own ``workers`` tree, exactly like the existing H11 read. A missing
    workers tree is a verifiable zero; an unreadable one is ``None``.
    """
    workers = project_root / ".agenticdoc" / key / "workers"
    try:
        rounds = state.used_rounds([workers])
    except (OSError, ValueError, TypeError):
        return None
    total = 0
    for value in rounds.values():
        if type(value) is not int or value < 0:
            return None
        total += value
    # Every durable reexecution reservation consumes a round, including failed
    # and interrupted attempts. Original task labels alone cannot meter reruns.
    attempts = project_root / ".agenticdoc" / key / "evidence" / "contract-reverification"
    try:
        for folder in attempts.iterdir() if attempts.exists() else ():
            if not folder.is_dir():
                return None
            record = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
            if (not isinstance(record, dict) or record.get("schema") != 1
                    or type(record.get("started_ns")) is not int
                    or record["started_ns"] <= 0):
                return None
            total += 1
    except (OSError, ValueError, TypeError):
        return None
    return total


def _pm_usage_reading(
    authority: object, project_root: pathlib.Path, key: str
) -> tuple[dict[str, int], dict[str, int], tuple[str, ...]]:
    """Read the cumulative meters the protected source actually declares.

    The descriptor's ``kind``/``unit`` must match a real, verifiable cumulative
    source and the policy's limit unit; a config knob (``round_budget``) or a
    self-reported number is never substituted. One consumption spends one unit
    on every declared hard limit (the caller cannot inject a smaller amount).
    """
    load = decision_policy.load_policy(project_root)
    if not load.usable or load.policy is None:
        return {}, {}, ("budget_policy_unusable",)
    limits = load.policy.hard_limits
    if not limits:
        return {}, {}, ("missing_hard_budget",)
    sources = getattr(authority, "usage_sources", {}) or {}
    usage: dict[str, int] = {}
    spend: dict[str, int] = {}
    reasons: list[str] = []
    for limit in limits:
        descriptor = sources.get(limit.usage_source)
        if descriptor is None:
            reasons.append("budget_usage_unknown")
            continue
        if getattr(descriptor, "unit", None) != limit.unit or limit.unit != "round":
            reasons.append("budget_units_mismatch")
            continue
        kind = getattr(descriptor, "kind", None)
        if kind not in _ROUND_USAGE_KINDS:
            reasons.append("usage_source_unknown")
            continue
        used = _pm_round_usage(project_root, key)
        if used is None:
            reasons.append("usage_unverifiable")
            continue
        usage[limit.usage_source] = used
        spend[limit.unit] = 1
    return usage, spend, tuple(dict.fromkeys(reasons))


def prepare_pm_binding(
    project_root: pathlib.Path | str,
    key: str,
    *,
    gate_id: str,
    decision_ref: str,
    note: str | None,
    authority_ref: str,
    gate_kind: str | None,
    expected_gate_key: str | None,
    required_scope: Iterable[str] = (),
    require_authorizes: Iterable[str] = (),
    require_files: Iterable[str] = (),
    target_key: str | None = None,
    expected_matter_ref: str | None = None,
    expected_version: str | None = None,
) -> tuple[PmDecisionBinding | None, tuple[str, ...]]:
    """Bind one recorded PM decision to the real project source (fail-closed)."""

    root = pathlib.Path(project_root)
    if not isinstance(key, str) or not _KEY_RE.match(key):
        return None, ("invalid_key",)
    if not isinstance(gate_id, str) or not gate_id:
        return None, ("missing_gate",)
    if not isinstance(decision_ref, str) or not decision_ref:
        return None, ("missing_decision_ref",)
    try:
        gate = gates.parse(_pm_gate_path(root, gate_id))
    except (OSError, ValueError):
        return None, ("unreadable_gate",)
    effect_reasons = _pm_effect_evidence(root, gate)
    reasons = list(
        _pm_gate_reasons(
            gate,
            gate_id=gate_id,
            gate_kind=gate_kind,
            expected_gate_key=expected_gate_key,
            decision_ref=decision_ref,
            note=note,
            expected_matter_ref=expected_matter_ref,
            expected_version=expected_version,
            require_authorizes=tuple(require_authorizes),
            require_files=tuple(require_files),
            effect_reasons=effect_reasons,
        )
    )
    if reasons:
        return None, tuple(dict.fromkeys(reasons))
    if not isinstance(note, str):
        return None, ("missing_pm_note",)

    try:
        import operator_authority
    except ImportError:
        return None, ("authority-source-unavailable",)
    try:
        observed = operator_authority.read_pm_authority(root, key)
    except operator_authority.AuthorityError as exc:
        return None, (f"authority-source:{exc.reason}",)
    if not observed.policy_sha256:
        return None, ("missing_policy_hash",)

    usage, spend, budget_reasons = _pm_usage_reading(observed, root, key)
    if budget_reasons:
        return None, budget_reasons
    supply = TrustedSupply(
        project_root=root,
        key=key,
        gate_id=gate_id,
        decision_ref=decision_ref,
        matter_ref=str(getattr(gate, "matter_ref")),
        substantive_version=str(getattr(gate, "substantive_version")),
        authority_source=dict(observed.records),
        trusted_writers=tuple(observed.trusted_writers),
        usage=usage,
        spend=spend,
    )
    supply_reasons, _gate = verify_supply(
        supply,
        gate_kind=gate_kind,
        expected_gate_key=expected_gate_key,
        required_scope=tuple(required_scope),
        authority_ref=authority_ref,
        require_authorizes=tuple(require_authorizes),
        require_files=tuple(require_files),
        note=note,
        target_key=target_key,
        effect_reasons=effect_reasons,
    )
    if supply_reasons:
        return None, supply_reasons
    return (
        PmDecisionBinding(
            project_root=root,
            key=key,
            gate_id=gate_id,
            decision_ref=decision_ref,
            matter_ref=supply.matter_ref,
            substantive_version=supply.substantive_version,
            pm_note=note,
            choice=str(getattr(gate, "business")),
            claim_id=observed.claim_id,
            policy_sha256=observed.policy_sha256,
            authority_ref=authority_ref,
            gate_kind=gate_kind,
            expected_gate_key=str(expected_gate_key) if expected_gate_key else "",
            required_scope=tuple(required_scope),
            require_authorizes=tuple(require_authorizes),
            require_files=tuple(require_files),
            target_key=target_key,
            supply=supply,
            authority=observed,
        ),
        (),
    )


def revalidate_pm_binding(
    binding: "PmDecisionBinding | None",
) -> tuple[PmDecisionBinding | None, tuple[str, ...]]:
    """Re-read the source, the gate and the policy hash before a real write.

    Any change (revoked record, moved claim, new gate note/version/decision,
    unreadable lifecycle, policy digest drift) refuses. The returned binding is
    a fresh observation; the caller must assess/write against it, never the
    previous one.
    """

    if not isinstance(binding, PmDecisionBinding):
        return None, ("missing_binding",)
    try:
        import operator_authority
        fresh_authority = operator_authority.verify_pm_authority(binding.authority)
    except operator_authority.AuthorityError as exc:
        return None, (f"authority-source:{exc.reason}",)
    except ImportError:
        return None, ("authority-source-unavailable",)
    if not fresh_authority.policy_sha256:
        return None, ("missing_policy_hash",)
    if fresh_authority.policy_sha256 != binding.policy_sha256:
        return None, ("policy_version_changed",)

    root = binding.project_root
    try:
        gate = gates.parse(_pm_gate_path(root, binding.gate_id))
    except (OSError, ValueError):
        return None, ("unreadable_gate",)
    effect_reasons = _pm_effect_evidence(root, gate)
    gate_reasons = _pm_gate_reasons(
        gate,
        gate_id=binding.gate_id,
        gate_kind=binding.gate_kind,
        expected_gate_key=binding.expected_gate_key or None,
        decision_ref=binding.decision_ref,
        note=binding.pm_note,
        expected_matter_ref=binding.matter_ref,
        expected_version=binding.substantive_version,
        require_authorizes=binding.require_authorizes,
        require_files=binding.require_files,
        effect_reasons=effect_reasons,
    )
    if gate_reasons:
        return None, gate_reasons

    usage, spend, budget_reasons = _pm_usage_reading(fresh_authority, root, binding.key)
    if budget_reasons:
        return None, budget_reasons
    supply = TrustedSupply(
        project_root=root,
        key=binding.key,
        gate_id=binding.gate_id,
        decision_ref=binding.decision_ref,
        matter_ref=binding.matter_ref,
        substantive_version=binding.substantive_version,
        authority_source=dict(fresh_authority.records),
        trusted_writers=tuple(fresh_authority.trusted_writers),
        usage=usage,
        spend=spend,
    )
    supply_reasons, _gate = verify_supply(
        supply,
        gate_kind=binding.gate_kind,
        expected_gate_key=binding.expected_gate_key or None,
        required_scope=binding.required_scope,
        authority_ref=binding.authority_ref,
        require_authorizes=binding.require_authorizes,
        require_files=binding.require_files,
        note=binding.pm_note,
        target_key=binding.target_key,
        effect_reasons=effect_reasons,
    )
    if supply_reasons:
        return None, supply_reasons
    return (
        dataclasses.replace(
            binding,
            claim_id=fresh_authority.claim_id,
            policy_sha256=fresh_authority.policy_sha256,
            supply=supply,
            authority=fresh_authority,
        ),
        (),
    )


def _pm_receipt(
    binding: PmDecisionBinding,
    *,
    action: str | None,
    verdict: object | None,
    target: str | None,
    reasons: Iterable[str] = (),
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "family": "pm-consume",
        "key": binding.key,
        "decision_ref": binding.decision_ref,
        "gate_id": binding.gate_id,
        "matter_ref": binding.matter_ref,
        "substantive_version": binding.substantive_version,
        "choice": binding.choice,
        "pm_note": binding.pm_note,
        "claim_id": binding.claim_id,
        "policy_sha256": binding.policy_sha256,
        "action": action,
        "target": target,
    }
    if verdict is not None:
        receipt["verdict_status"] = getattr(verdict, "status", None)
        receipt["reasons"] = list(getattr(verdict, "reasons", ()))
        version = getattr(verdict, "version", None)
        if version is not None:
            receipt["version"] = version
        receipt["reverification_required"] = list(
            getattr(verdict, "reverification_required", ())
        )
        receipt["reusable_bindings"] = list(
            getattr(verdict, "reusable_bindings", ())
        )
        approved = getattr(verdict, "approved_items", None)
        if approved is not None:
            receipt["approved_items"] = list(approved)
        reverify = getattr(verdict, "reverification_items", None)
        if reverify is not None:
            receipt["reverification_items"] = list(reverify)
    extra = tuple(dict.fromkeys(reasons))
    if extra:
        receipt["blocked_reasons"] = list(extra)
    return receipt


# --- H06 normal-PM consumption ----------------------------------------------


def prepare_goal_adoption(
    project_root: pathlib.Path | str,
    key: str,
    *,
    choice: str,
    request: "GoalAdoptionRequest",
    baseline_path: pathlib.Path | str,
    before_text: str,
    after_text: str,
    gate_id: str,
    decision_ref: str,
    note: str | None,
    expected_matter_ref: str | None = None,
    expected_version: str | None = None,
    affected_bindings: Iterable[str] = (),
    unaffected_bindings: Iterable[str] = (),
) -> PmConsumption:
    """Bind one goal-change answer to the real source, without writing."""

    plan = {
        "choice": choice,
        "request": request,
        "baseline_path": pathlib.Path(baseline_path),
        "before_text": before_text,
        "after_text": after_text,
        "note": note,
        "affected_bindings": tuple(affected_bindings),
        "unaffected_bindings": tuple(unaffected_bindings),
        "family": "goal-adoption",
    }
    if choice not in GOAL_ADOPTION_CHOICES:
        return _pm_blocked(
            "goal-adoption", "blocked", ("unknown_goal_choice",), plan=plan
        )
    if choice != "approve":
        return _pm_blocked(
            "goal-adoption",
            "not_adopted",
            (f"{choice}_does_not_adopt_goal",),
            plan=plan,
        )
    binding, reasons = prepare_pm_binding(
        project_root,
        key,
        gate_id=gate_id,
        decision_ref=decision_ref,
        note=note,
        authority_ref=request.authority_ref,
        gate_kind="goal-change",
        expected_gate_key=request.key,
        required_scope=(
            f"goal-adopt:{request.key}",
            f"goal-version:{request.target_version}",
        ),
        target_key=None,
        expected_matter_ref=expected_matter_ref,
        expected_version=expected_version,
    )
    if reasons:
        return _pm_blocked("goal-adoption", "blocked", reasons, plan=plan)
    return PmConsumption(
        family="goal-adoption",
        status="prepared",
        reasons=(),
        binding=binding,
        verdict=None,
        action=None,
        written=False,
        target=None,
        receipt=_pm_receipt(
            binding,
            action=None,
            verdict=None,
            target=None,
        ),
        plan=plan,
    )


def apply_goal_consumption(consumption: PmConsumption) -> PmConsumption:
    """Re-read the source and run the original H06 judgement/writer."""

    if not isinstance(consumption, PmConsumption) or consumption.family != "goal-adoption":
        return _pm_blocked("goal-adoption", "blocked", ("wrong_consumption",))
    if consumption.binding is None:
        return consumption
    plan = consumption.plan
    request = plan["request"]
    fresh, reasons = revalidate_pm_binding(consumption.binding)
    if reasons:
        return _pm_blocked(
            "goal-adoption",
            "blocked",
            reasons,
            binding=consumption.binding,
            plan=plan,
            receipt=_pm_receipt(
                consumption.binding, action=None, verdict=None, target=None,
                reasons=reasons,
            ),
        )
    verdict = assess_goal_adoption(
        str(plan["choice"]),
        request,
        supply=fresh.supply,
        baseline_path=plan["baseline_path"],
        goal_before_text=str(plan["before_text"]),
        goal_after_text=str(plan["after_text"]),
        pm_note=str(plan["note"]),
        affected_bindings=plan["affected_bindings"],
        unaffected_bindings=plan["unaffected_bindings"],
    )
    written = False
    action: str | None = None
    if verdict.adopt and verdict.baseline_refresh:
        written = apply_goal_adoption(plan["baseline_path"], verdict)
        if written:
            action = "goal-baseline-adoption"
    reasons_out = tuple(verdict.reasons)
    if verdict.adopt and verdict.baseline_refresh and not written:
        reasons_out = tuple(dict.fromkeys((*reasons_out, "baseline_write_refused")))
    status = "applied" if written else (verdict.status or "blocked")
    return PmConsumption(
        family="goal-adoption",
        status=status,
        reasons=reasons_out,
        binding=fresh,
        verdict=verdict,
        action=action,
        written=written,
        target=str(plan["baseline_path"]) if written else None,
        receipt=_pm_receipt(
            fresh,
            action=action,
            verdict=verdict,
            target=str(plan["baseline_path"]) if written else None,
            reasons=() if written else reasons_out,
        ),
        plan=plan,
    )


def consume_goal_adoption(*args: object, **kwargs: object) -> PmConsumption:
    """One normal-PM call: bind, re-read and (only if valid) adopt."""

    return apply_goal_consumption(prepare_goal_adoption(*args, **kwargs))


# --- H08 normal-PM consumption ----------------------------------------------


def prepare_freeze_change(
    project_root: pathlib.Path | str,
    key_dir: pathlib.Path | str,
    *,
    request: "FreezeChangeRequest",
    approval: "FreezeChangeApproval | None",
    gate_id: str,
    decision_ref: str,
    note: str | None,
    expected_matter_ref: str | None = None,
    expected_version: str | None = None,
) -> PmConsumption:
    """Bind one exact frozen-entry change to the real source, without writing."""

    plan = {
        "request": request,
        "approval": approval,
        "key_dir": pathlib.Path(key_dir),
        "note": note,
        "family": "contract-refreeze",
    }
    binding, reasons = prepare_pm_binding(
        project_root,
        request.key,
        gate_id=gate_id,
        decision_ref=decision_ref,
        note=note,
        authority_ref=request.authority_ref,
        gate_kind=None,
        expected_gate_key=request.key,
        required_scope=(
            f"contract-change:{request.key}",
            *(f"contract-item:{item}" for item in request.items),
        ),
        require_authorizes=("contract-change",),
        expected_matter_ref=expected_matter_ref,
        expected_version=expected_version,
    )
    if reasons:
        return _pm_blocked("contract-refreeze", "blocked", reasons, plan=plan)
    return PmConsumption(
        family="contract-refreeze",
        status="prepared",
        reasons=(),
        binding=binding,
        verdict=None,
        action=None,
        written=False,
        target=None,
        receipt=_pm_receipt(binding, action=None, verdict=None, target=None),
        plan=plan,
    )


def apply_freeze_consumption(consumption: PmConsumption) -> PmConsumption:
    """Serialize H08 publication with current verification consumers."""
    if (not isinstance(consumption, PmConsumption)
            or consumption.family != "contract-refreeze"
            or consumption.binding is None):
        return _apply_freeze_consumption_locked(consumption)
    with contract_publication_lock(consumption.plan["key_dir"]):
        return _apply_freeze_consumption_locked(consumption)


def _apply_freeze_consumption_locked(consumption: PmConsumption) -> PmConsumption:
    """Re-read the source and run the original H08 judgement/writer."""

    if (
        not isinstance(consumption, PmConsumption)
        or consumption.family != "contract-refreeze"
    ):
        return _pm_blocked("contract-refreeze", "blocked", ("wrong_consumption",))
    if consumption.binding is None:
        return consumption
    plan = consumption.plan
    fresh, reasons = revalidate_pm_binding(consumption.binding)
    if reasons:
        return _pm_blocked(
            "contract-refreeze",
            "blocked",
            reasons,
            binding=consumption.binding,
            plan=plan,
            receipt=_pm_receipt(
                consumption.binding, action=None, verdict=None, target=None,
                reasons=reasons,
            ),
        )
    verdict, path = refreeze_approved_change(
        plan["key_dir"],
        plan["request"],
        plan["approval"],
        supply=fresh.supply,
        pm_note=str(plan["note"]),
    )
    written = path is not None
    action = "contract-refreeze" if written else None
    status = "applied" if written else (verdict.status or "blocked")
    return PmConsumption(
        family="contract-refreeze",
        status=status,
        reasons=tuple(verdict.reasons),
        binding=fresh,
        verdict=verdict,
        action=action,
        written=written,
        target=str(path) if written else None,
        receipt=_pm_receipt(
            fresh,
            action=action,
            verdict=verdict,
            target=str(path) if written else None,
            reasons=() if written else verdict.reasons,
        ),
        plan=plan,
    )


def consume_freeze_change(*args: object, **kwargs: object) -> PmConsumption:
    """One normal-PM call: bind, re-read and (only if exact) refreeze."""

    return apply_freeze_consumption(prepare_freeze_change(*args, **kwargs))
