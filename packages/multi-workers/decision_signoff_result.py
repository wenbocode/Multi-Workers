"""Minimal dp25 sign-off result record and credential-free sign-off validator.

Card dc-t05-signoff-cli (design D005 / sec 4.4) splits the sign-off into three
facts:

* the **valid sign-off file** (``<key>/evidence/review/sign-final.md``) is the
  success authority: it lands through a safe temporary write + ``fsync`` +
  ``os.replace`` and carries the exact ``logical_id`` + snapshot it signs;
* the **minimal result record** (``<key>/evidence/review/decide-results/
  <logical_id>.json``) is only the retry face: it keeps the model conclusion and
  snapshot of one decision so a failed file write is retried with zero new model
  calls. It is never a substitute for the file;
* the **feedback** is the separate lifecycle ledger (see ``decision_lifecycle``),
  reported as ``feedback_status`` and never allowed to turn a real file write
  into a sign-off failure.

:func:`validate_signoff` is the read face T06 may use without a model, a
credential or a network: it parses the file's machine lines, requires the exact
logical id + snapshot, refuses a legacy file with no logical id, and checks the
whole parent chain for symbolic links before trusting any hash or id. A hash
match can never exempt an unsafe path.

Everything here is stdlib-only and writes only under the key directory passed by
the caller. The module never reads a credential or touches the network.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import decision_validity
import decision_file_evidence
from autopilot import contract_guard

__all__ = [
    "AUTHORITY_CHANGE_PRODUCT_TYPE",
    "BASIS_VERSION",
    "NativeBasis",
    "capture_native_basis",
    "native_basis_problems",
    "CONCLUSIONS",
    "DP_ID",
    "LEGACY_DP_IDS",
    "MACHINE_LINE_NAMES",
    "PRODUCT_TYPE",
    "RESULT_DIR_PARTS",
    "RESULT_VERSION",
    "SIGNING_CONCLUSIONS",
    "SIGNOFF_RELATIVE_PATH",
    "KeySignoffValidation",
    "SignoffResult",
    "SignoffResultError",
    "SignoffValidation",
    "assert_safe_target",
    "basis_usable_now",
    "build_result",
    "canonical_sha256",
    "digest_material",
    "evidence_sha256",
    "is_valid_signoff",
    "parse_machine_lines",
    "read_result",
    "result_path",
    "signoff_material_problems",
    "signoff_path",
    "snapshot_digest",
    "validate_key_signoff",
    "validate_signoff",
    "write_result",
    "write_signoff_text",
]

#: Record schema of the retry face (the decision record version is 2; the sign
#: result record keeps the same generation so a reader never mixes v1/v2 rows).
RESULT_VERSION = 2
#: The single active key-signoff decision point (the eight consolidated names;
#: the old ``dp25`` number is retired and only readable as history).
DP_ID = "dp-sign-key"
#: Retired ids that historical sign-off files carry. They are readable as
#: history but can never validate as a current successful sign-off.
LEGACY_DP_IDS = ("dp25-signoff-conclusion",)
#: The typed product discriminator of a key sign-off. ``authority-change`` is a
#: separate product type; a consumer of one must refuse the other.
PRODUCT_TYPE = "key-signoff"
AUTHORITY_CHANGE_PRODUCT_TYPE = "authority-change"
#: The dp-sign-key native answers (design sec 2 / spec 1.2).
CONCLUSIONS = ("finalize", "continue", "user-confirm")
#: Only this word satisfies a required key sign-off. ``continue`` and
#: ``user-confirm`` are legal menu words that write no sign-off file.
SIGNING_CONCLUSIONS = ("finalize",)
#: Schema of the native contract/goal basis bound into a sign-off snapshot.
BASIS_VERSION = 1
#: The project-level goal document advance_phase treats as the goal anchor.
GOAL_FILE_NAME = "goal.md"
#: Where the minimal result record of one logical decision is kept.
RESULT_DIR_PARTS = ("evidence", "review", "decide-results")
#: The only sign-off location the done gate / readers agree on.
SIGNOFF_RELATIVE_PATH = pathlib.Path("evidence") / "review" / "sign-final.md"
#: Machine-line names this module reads. The file is Markdown with these exact
#: column-0 ``name: value`` lines; ``decide_signoff.render`` writes them.
MACHINE_LINE_NAMES = (
    "product_type",
    "record_version",
    "dp",
    "basis_version",
    "basis_sha256",
    "logical_id",
    "decision_id",
    "material_sha256",
    "evidence_sha256",
    "rows_sha256",
    "snapshot_sha256",
    "initiator_role",
    "retry_of",
    "transport",
    "model",
    "confidence_source",
    "decision_source",
)

_LOGICAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+@-]{0,127}$")
#: The result record is a file named after the logical id: keep the name legal on
#: every platform (``:``/``+``/``@`` are legal ledger tokens but not file names).
_RESULT_FILE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MACHINE_LINE_RE = re.compile(
    r"^(product_type|record_version|dp|basis_version|basis_sha256|logical_id|decision_id|material_sha256"
    r"|evidence_sha256|rows_sha256|snapshot_sha256|initiator_role|retry_of|transport"
    r"|model|confidence_source|decision_source|review_task|review_source):\s*(.*?)\s*$",
    re.MULTILINE,
)
_MAX_RESULT_BYTES = 256 * 1024


class SignoffResultError(ValueError):
    """A result record or sign-off path violates the contract (fail closed).

    Messages name the field/rule only and never echo a caller value: the value
    may itself be a known secret.
    """


# ---------------------------------------------------------------------------
# Digests
# ---------------------------------------------------------------------------


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8", errors="replace")


def canonical_sha256(value: object) -> str:
    """``sha256(canonical JSON)`` - the one digest function of this module."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def digest_material(material: Mapping | object) -> tuple[str, str]:
    """``(material_sha256, evidence_sha256)`` of the exact business material.

    ``material`` must be the whole dp25 four-part mapping. The evidence digest
    covers only ``verification_evidence`` so a material change outside the
    evidence is still caught by the material digest, and an evidence change is
    visible on its own.
    """
    if not isinstance(material, Mapping):
        raise SignoffResultError("material is not a mapping")
    evidence = material.get("verification_evidence")
    if evidence is None:
        evidence = {}
    return canonical_sha256(dict(material)), canonical_sha256(evidence)


def material_sha256(material: Mapping | object) -> str:
    return digest_material(material)[0]


def evidence_sha256(material: Mapping | object) -> str:
    return digest_material(material)[1]


def snapshot_digest(
    *,
    key: str,
    dp: str = DP_ID,
    material_sha256: str,
    evidence_sha256: str,
    rows_sha256: str,
    basis_sha256: str | None = None,
) -> str:
    """The single snapshot id of one sign-off (material + evidence + archive).

    ``rows_sha256`` is the archive snapshot the file describes, so an archive
    append after the model call also invalidates the old conclusion. A current
    sign-off additionally binds its native contract/goal basis; old records
    without that proof keep the original digest and stay readable as history.
    """
    payload: dict[str, Any] = {
        "key": key,
        "dp": dp,
        "material_sha256": material_sha256,
        "evidence_sha256": evidence_sha256,
        "rows_sha256": rows_sha256,
    }
    if basis_sha256 is not None:
        payload["basis_sha256"] = basis_sha256
    return canonical_sha256(payload)


# ---------------------------------------------------------------------------
# Native contract/goal basis
# ---------------------------------------------------------------------------

_BASIS_STATES = ("present", "absent", "unreadable")
_BASIS_CONTRACT_SOURCES = ("spec", "design")
_BASIS_SOURCES = (*_BASIS_CONTRACT_SOURCES, "goal")
#: The adopted-goal family is either proven by the canonical effect receipt or
#: absent. ``unproven`` is capture-time only and is never persisted as proof.
_ADOPTED_GOAL_STATES = ("absent", "present")


@dataclass(frozen=True)
class NativeBasis:
    """The native contract/goal semantics one sign-off is bound to.

    The contract family is the per-AC/VC canonical identity from
    ``contract_guard.extract_contract`` (an unrelated file or a formatting-only
    edit never enters it). The goal family is the formatting-normalised prose
    digest of the project ``goal.md``. Source presence/readability is recorded
    too, so a bound source that later disappears or becomes unreadable is a
    concrete failure instead of silently empty content.
    """

    contract_states: Mapping[str, str]
    contract_items: Mapping[str, str]
    goal_state: str
    goal_sha256: str | None
    version: int = BASIS_VERSION
    #: The actually adopted goal version baseline (canonical family-effect
    #: receipt). ``unbound`` marks a pre-H06 record: readable history, never a
    #: current proof.
    adopted_goal_state: str = "unbound"
    adopted_goal_version: str | None = None
    adopted_goal_target: str | None = None
    adopted_goal_sha256: str | None = None
    adopted_goal_reason: str = ""
    include_adopted_goal: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": self.version,
            "contract": {
                "spec": self.contract_states.get("spec", "absent"),
                "design": self.contract_states.get("design", "absent"),
                "items": dict(sorted(self.contract_items.items())),
            },
            "goal": {"state": self.goal_state, "sha256": self.goal_sha256},
        }
        if self.include_adopted_goal:
            payload["adopted_goal"] = {
                "state": self.adopted_goal_state,
                "version": self.adopted_goal_version,
                "target": self.adopted_goal_target,
                "sha256": self.adopted_goal_sha256,
            }
        return payload

    def digest(self) -> str:
        return canonical_sha256(self.as_dict())


def _read_basis_source(path: pathlib.Path) -> tuple[str, str]:
    """``(state, text)``; a missing file is absent, damaged data is unreadable."""
    try:
        return "present", path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "absent", ""
    except (OSError, UnicodeDecodeError):
        return "unreadable", ""


def _goal_digest(text: str) -> str:
    """Formatting-insensitive digest of the goal prose."""
    return decision_validity.semantic_version("prose", text).digest


def capture_native_basis(key_dir: pathlib.Path | str) -> NativeBasis:
    """Read the key's real contract sources and the project goal right now.

    ``key_dir`` is ``<project>/.agenticdoc/<key>``; the contract sources are the
    key's canonical ``spec.md``/``design.md`` and the project anchor is
    ``<project>/.agenticdoc/goal.md`` (the same file the phase gate reads).
    Nothing is guessed from mtimes, whole-project scans or the freeze sidecar.
    """
    root = pathlib.Path(key_dir)
    states: dict[str, str] = {}
    texts: dict[str, str] = {}
    for name, path in (
        ("spec", root / contract_guard.SPEC_FILE_NAME),
        ("design", root / contract_guard.DESIGN_FILE_NAME),
        ("goal", root.parent / GOAL_FILE_NAME),
    ):
        states[name], texts[name] = _read_basis_source(path)
    items: dict[str, str] = {}
    if states["spec"] == "present" or states["design"] == "present":
        identity = contract_guard.extract_contract(
            texts["spec"] if states["spec"] == "present" else "",
            texts["design"] if states["design"] == "present" else "",
        )
        items = {**identity.acs, **identity.vcs}
    goal_sha = _goal_digest(texts["goal"]) if states["goal"] == "present" else None
    # The adopted goal version is located only through the canonical family
    # effect receipt / gate, never from a caller-supplied path or a guessed
    # file name. A key outside the standard layout has no adopted baseline.
    if root.parent.name == ".agenticdoc":
        adopted = contract_guard.adopted_goal_binding(root.parent.parent, root.name)
    else:
        adopted = contract_guard.AdoptedGoalBinding("absent")
    return NativeBasis(
        contract_states={
            "spec": states["spec"],
            "design": states["design"],
        },
        contract_items=items,
        goal_state=states["goal"],
        goal_sha256=goal_sha,
        adopted_goal_state=adopted.state,
        adopted_goal_version=adopted.version,
        adopted_goal_target=adopted.target,
        adopted_goal_sha256=adopted.sha256,
        adopted_goal_reason=adopted.reason,
    )


def _native_basis_from_mapping(raw: Mapping[str, Any]) -> NativeBasis:
    """Parse a persisted basis; any malformed field fails closed."""
    if not isinstance(raw, Mapping):
        raise SignoffResultError("native_basis is not a mapping")
    version = raw.get("version")
    if isinstance(version, bool) or version != BASIS_VERSION:
        raise SignoffResultError("native_basis version is not supported")
    contract = raw.get("contract")
    goal = raw.get("goal")
    if not isinstance(contract, Mapping) or not isinstance(goal, Mapping):
        raise SignoffResultError("native_basis families are not mappings")
    states: dict[str, str] = {}
    for name in _BASIS_CONTRACT_SOURCES:
        value = contract.get(name)
        if value not in _BASIS_STATES:
            raise SignoffResultError(f"native_basis contract.{name} state is invalid")
        states[name] = str(value)
    items = contract.get("items")
    if not isinstance(items, Mapping) or any(
        not isinstance(name, str) or _SHA256_RE.match(str(digest)) is None
        for name, digest in items.items()
    ):
        raise SignoffResultError("native_basis contract.items is invalid")
    adopted_raw = raw.get("adopted_goal", None)
    adopted_present = "adopted_goal" in raw
    if not adopted_present:
        # Pre-H06 basis: keep the exact old digest so the record stays readable
        # as history; native_basis_problems refuses it as current proof.
        adopted_state = "unbound"
        adopted_version = None
        adopted_target = None
        adopted_sha = None
    else:
        if not isinstance(adopted_raw, Mapping):
            raise SignoffResultError("native_basis adopted_goal is not a mapping")
        adopted_state = adopted_raw.get("state")
        if adopted_state not in _ADOPTED_GOAL_STATES:
            raise SignoffResultError("native_basis adopted_goal.state is invalid")
        adopted_version = adopted_raw.get("version")
        adopted_target = adopted_raw.get("target")
        adopted_sha = adopted_raw.get("sha256")
        if adopted_state == "present":
            if not isinstance(adopted_version, str) or not adopted_version.strip():
                raise SignoffResultError("native_basis adopted_goal.version is invalid")
            if not isinstance(adopted_target, str) or not adopted_target:
                raise SignoffResultError("native_basis adopted_goal.target is invalid")
            target_path = pathlib.PurePosixPath(adopted_target)
            if target_path.is_absolute() or ".." in target_path.parts:
                raise SignoffResultError("native_basis adopted_goal.target escapes the project")
            if not isinstance(adopted_sha, str) or _SHA256_RE.match(adopted_sha) is None:
                raise SignoffResultError("native_basis adopted_goal.sha256 is invalid")
        elif (
            adopted_version is not None
            or adopted_target is not None
            or adopted_sha is not None
        ):
            raise SignoffResultError(
                "native_basis adopted_goal must be null when absent"
            )
    goal_state = goal.get("state")
    if goal_state not in _BASIS_STATES:
        raise SignoffResultError("native_basis goal.state is invalid")
    goal_sha = goal.get("sha256")
    if goal_state == "present":
        if not isinstance(goal_sha, str) or _SHA256_RE.match(goal_sha) is None:
            raise SignoffResultError("native_basis goal.sha256 is invalid")
    elif goal_sha is not None:
        raise SignoffResultError("native_basis goal.sha256 must be null when absent")
    if any(state == "unreadable" for state in states.values()) or goal_state == "unreadable":
        raise SignoffResultError("native_basis is bound to an unreadable source")
    return NativeBasis(
        contract_states=states,
        contract_items={str(name): str(digest) for name, digest in items.items()},
        goal_state=str(goal_state),
        goal_sha256=str(goal_sha) if isinstance(goal_sha, str) else None,
        adopted_goal_state=str(adopted_state),
        adopted_goal_version=(
            str(adopted_version) if isinstance(adopted_version, str) else None
        ),
        adopted_goal_target=(
            str(adopted_target) if isinstance(adopted_target, str) else None
        ),
        adopted_goal_sha256=(
            str(adopted_sha) if isinstance(adopted_sha, str) else None
        ),
        include_adopted_goal=adopted_present,
    )


def _basis_identity(raw: NativeBasis | Mapping[str, Any] | None) -> NativeBasis:
    if raw is None:
        raise SignoffResultError("native_basis is missing")
    if isinstance(raw, NativeBasis):
        return raw
    return _native_basis_from_mapping(raw)


def basis_usable_now(basis: NativeBasis) -> tuple[str, ...]:
    """Problems that make a freshly captured basis unfit to bind."""
    problems: list[str] = []
    for name in _BASIS_CONTRACT_SOURCES:
        if basis.contract_states.get(name) == "unreadable":
            problems.append(f"{name} source is unreadable")
    if basis.goal_state == "unreadable":
        problems.append("goal source is unreadable")
    if basis.adopted_goal_state == "unproven":
        detail = basis.adopted_goal_reason or "the canonical adoption receipt is not proven"
        problems.append(f"adopted goal basis is not proven: {detail}")
    return tuple(problems)


def native_basis_problems(
    bound: NativeBasis | Mapping[str, Any] | None, current: NativeBasis
) -> tuple[str, ...]:
    """Concrete substantive differences between a bound and the current basis.

    Formatting-only edits are already gone from both digests. Unreadable or
    missing bound sources are failures, never an empty-but-equal state.
    """
    try:
        before = _basis_identity(bound)
    except SignoffResultError as exc:
        return (f"bound basis is unusable: {exc}",)
    problems: list[str] = []
    if before.version != current.version:
        problems.append("native basis schema changed")
    if not before.include_adopted_goal:
        problems.append(
            "native basis has no adopted goal binding (pre-H06 history, not current proof)"
        )
    else:
        was_adopted = before.adopted_goal_state
        now_adopted = current.adopted_goal_state
        if now_adopted == "unproven":
            problems.append(
                "current adopted goal basis is not proven: "
                + (current.adopted_goal_reason or "the canonical receipt is unusable")
            )
        if was_adopted == "unproven":
            problems.append("bound adopted goal basis was not proven at signing")
        elif was_adopted == "present" and now_adopted == "absent":
            problems.append(
                "bound adopted goal baseline is missing"
                f" ({before.adopted_goal_version or '-'})"
            )
        elif was_adopted == "absent" and now_adopted == "present":
            problems.append(
                "adopted goal appeared after signing"
                f" ({current.adopted_goal_version or '-'})"
            )
        elif was_adopted == "present" and now_adopted == "present":
            if before.adopted_goal_version != current.adopted_goal_version:
                problems.append(
                    "adopted goal version changed: "
                    f"{before.adopted_goal_version or '-'} -> {current.adopted_goal_version or '-'}"
                )
            if before.adopted_goal_target != current.adopted_goal_target:
                problems.append(
                    "adopted goal baseline target changed: "
                    f"{before.adopted_goal_target or '-'} -> {current.adopted_goal_target or '-'}"
                )
            elif before.adopted_goal_sha256 != current.adopted_goal_sha256:
                problems.append("adopted goal baseline content changed")
    for name in _BASIS_CONTRACT_SOURCES:
        was = before.contract_states.get(name, "absent")
        now = current.contract_states.get(name, "absent")
        if now == "unreadable":
            problems.append(f"current {name} source is unreadable")
        if was == "unreadable":
            problems.append(f"bound {name} source was unreadable at signing")
        elif was == "present" and now == "absent":
            problems.append(f"bound {name} source is missing")
        elif was == "absent" and now == "present":
            problems.append(f"{name} source appeared after signing")
    added = sorted(set(current.contract_items) - set(before.contract_items))
    removed = sorted(set(before.contract_items) - set(current.contract_items))
    changed = sorted(
        field_id
        for field_id in set(before.contract_items) & set(current.contract_items)
        if before.contract_items[field_id] != current.contract_items[field_id]
    )
    for label, ids in (("added", added), ("removed", removed), ("changed", changed)):
        if ids:
            problems.append(f"contract {label}: {', '.join(ids)}")
    was_goal = before.goal_state
    now_goal = current.goal_state
    if now_goal == "unreadable":
        problems.append("current goal source is unreadable")
    if was_goal == "unreadable":
        problems.append("bound goal source was unreadable at signing")
    elif was_goal == "present" and now_goal == "absent":
        problems.append("bound goal source is missing")
    elif was_goal == "absent" and now_goal == "present":
        problems.append("goal source appeared after signing")
    elif (
        was_goal == "present"
        and now_goal == "present"
        and before.goal_sha256 != current.goal_sha256
    ):
        problems.append("goal source substantive content changed")
    return tuple(problems)


# ---------------------------------------------------------------------------
# Paths: key containment + no symbolic link on any component
# ---------------------------------------------------------------------------


def _key_root(key_dir: pathlib.Path | str) -> pathlib.Path:
    root = pathlib.Path(key_dir)
    if not root.is_absolute():
        root = root.absolute()
    try:
        if os.path.islink(root):
            raise SignoffResultError("key directory is a symbolic link; refusing")
    except OSError:
        raise SignoffResultError("key directory could not be inspected") from None
    return root


def _assert_safe_target(key_dir: pathlib.Path | str, target: pathlib.Path | str) -> pathlib.Path:
    """Refuse a target outside the key dir or behind any symbolic-link component.

    This is a lookup, not a race-free guarantee (design sec 9 does not claim a
    TOCTOU-free pure-lstat check), but it is the boundary that prevents a hash
    or a logical id from exempting an unsafe parent chain: every existing
    component from the key root down to the file is inspected.
    """
    root = _key_root(key_dir)
    path = pathlib.Path(target)
    if not path.is_absolute():
        path = path.absolute()
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise SignoffResultError("path escapes the key directory") from None
    if not relative.parts:
        raise SignoffResultError("path is the key directory itself")
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if os.path.islink(current):
                raise SignoffResultError(
                    "path component is a symbolic link; refusing to trust it"
                )
        except OSError:
            raise SignoffResultError("path component could not be inspected") from None
    # Resolve the parent and re-check containment (a junction/mount that lstat
    # cannot see on every platform still has to stay inside the key root).
    try:
        root_real = root.resolve()
        parent_real = path.parent.resolve()
    except OSError:
        raise SignoffResultError("path could not be resolved") from None
    if parent_real != root_real and root_real not in parent_real.parents:
        raise SignoffResultError("path resolves outside the key directory")
    return path


def assert_safe_target(
    key_dir: pathlib.Path | str, target: pathlib.Path | str
) -> pathlib.Path:
    """Public name of the parent-chain/symlink/containment check (T06 may reuse)."""
    return _assert_safe_target(key_dir, target)


def _safe_read_text(key_dir: pathlib.Path | str, target: pathlib.Path | str) -> str:
    path = _assert_safe_target(key_dir, target)
    if not path.is_file():
        raise SignoffResultError("file is missing")
    if path.stat().st_size > _MAX_RESULT_BYTES:
        raise SignoffResultError("file exceeds the bounded size")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise SignoffResultError("file could not be read as UTF-8") from None


def _fsync_dir(path: pathlib.Path) -> None:
    """Best-effort directory fsync (POSIX); Windows cannot open a directory."""
    flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write_text(
    key_dir: pathlib.Path | str, target: pathlib.Path, text: str, *, replace: bool = True
) -> pathlib.Path:
    """Safe temp write + file fsync + atomic replace under the key directory."""
    path = _assert_safe_target(key_dir, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Re-check after mkdir: a component created/swapped by someone else is not
    # trusted just because the pre-check passed.
    path = _assert_safe_target(key_dir, target)
    data = text.encode("utf-8")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    _fsync_dir(path.parent)
    return path


def result_path(key_dir: pathlib.Path | str, logical_id: str) -> pathlib.Path:
    logical_id = _check_logical_id(logical_id)
    if _RESULT_FILE_TOKEN_RE.match(logical_id) is None:
        raise SignoffResultError(
            "logical_id cannot be used as a cross-platform result file name"
        )
    return pathlib.Path(key_dir).joinpath(*RESULT_DIR_PARTS) / f"{logical_id}.json"


def signoff_path(key_dir: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(key_dir) / SIGNOFF_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------


def _check_logical_id(value: object) -> str:
    if not isinstance(value, str) or _LOGICAL_ID_RE.match(value) is None:
        raise SignoffResultError(
            "logical_id is not valid: expected one bounded ledger token"
        )
    return value


def _check_hash(field: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.match(value) is None:
        raise SignoffResultError(f"{field} is not valid: expected 64 lowercase hex characters")
    return value


@dataclass(frozen=True)
class SignoffResult:
    """One persisted dp25 selection + its exact material/evidence snapshot."""

    key: str
    logical_id: str
    dp: str
    decision_id: str
    conclusion: str
    material_sha256: str
    evidence_sha256: str
    rows_sha256: str
    snapshot_sha256: str
    #: Typed product discriminator: only ``key-signoff`` is this contract.
    product_type: str = PRODUCT_TYPE
    #: Native contract/goal identity this sign-off is bound to (new schema).
    native_basis: Mapping[str, Any] | None = None
    basis_sha256: str | None = None
    basis_version: int | None = None
    #: Redacted copy for audit only; never the comparison source.
    material: Mapping[str, Any] = field(default_factory=dict)
    task_key: str | None = None
    initiator_role: str = "unknown"
    retry_of: str | None = None
    transport: str | None = None
    model: str | None = None
    confidence_source: str | None = None
    record_version: int = RESULT_VERSION
    ts: str | None = None
    #: Actual prepared request/answer proof; absent on historical typed records.
    prepared_proof: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_version": self.record_version,
            "product_type": self.product_type,
            "dp": self.dp,
            "key": self.key,
            "logical_id": self.logical_id,
            "task_key": self.task_key,
            "initiator_role": self.initiator_role,
            "retry_of": self.retry_of,
            "decision_id": self.decision_id,
            "conclusion": self.conclusion,
            "material_sha256": self.material_sha256,
            "evidence_sha256": self.evidence_sha256,
            "rows_sha256": self.rows_sha256,
            "snapshot_sha256": self.snapshot_sha256,
            "native_basis": dict(self.native_basis) if self.native_basis is not None else None,
            "basis_sha256": self.basis_sha256,
            "basis_version": self.basis_version,
            "transport": self.transport,
            "model": self.model,
            "confidence_source": self.confidence_source,
            "ts": self.ts,
            "prepared_proof": dict(self.prepared_proof) if self.prepared_proof is not None else None,
            "material": dict(self.material),
        }


def build_result(
    key_dir: pathlib.Path | str,
    *,
    key: str,
    logical_id: str,
    decision_id: str,
    conclusion: str,
    material: Mapping[str, Any],
    facts: object,
    transport: str | None,
    model: str | None,
    confidence_source: str | None,
    task_key: str | None = None,
    initiator_role: str = "unknown",
    retry_of: str | None = None,
    ts: str | None = None,
    snapshot_material: Mapping[str, Any] | None = None,
    native_basis: NativeBasis | Mapping[str, Any] | None = None,
    prepared_proof: Mapping[str, Any] | None = None,
) -> SignoffResult:
    """Build the minimal record of one already-decided dp25 selection.

    ``facts`` is the archive fact object (``decide_signoff.collect``) whose
    ``sha256`` the sign-off file describes; only that stable hash is read here.

    ``native_basis`` is the contract/goal identity captured *before* the model
    request. When omitted it is captured now from the key's real sources, which
    keeps direct callers bound; the production sign path always passes the
    pre-request capture so a mid-response change cannot be bound silently.
    """
    logical_id = _check_logical_id(logical_id)
    if conclusion not in CONCLUSIONS:
        raise SignoffResultError(
            f"conclusion is not valid: expected one of {CONCLUSIONS}"
        )
    if not isinstance(decision_id, str) or not decision_id.startswith(DP_ID + ":"):
        raise SignoffResultError(
            "decision_id is not valid: expected the dp-sign-key form"
        )
    if any(part in decision_id for part in ("/", "\\", "..", "\x00")):
        raise SignoffResultError("decision_id is not valid: no separators or traversal")
    if not isinstance(key, str) or not key:
        raise SignoffResultError("key is not valid: expected a non-empty key")
    rows_sha256 = getattr(facts, "sha256", None)
    rows_sha256 = _check_hash("rows_sha256", rows_sha256)
    digest, evidence = digest_material(material)
    if native_basis is None:
        bound_basis = capture_native_basis(key_dir)
    else:
        bound_basis = _basis_identity(native_basis)
    if not bound_basis.include_adopted_goal:
        raise SignoffResultError(
            "the native basis has no adopted goal binding; history cannot be a current proof"
        )
    if bound_basis.adopted_goal_state == "unproven":
        raise SignoffResultError(
            "the adopted goal basis is not proven: "
            + (bound_basis.adopted_goal_reason or "the canonical receipt is unusable")
        )
    basis_dict = bound_basis.as_dict()
    basis_sha = bound_basis.digest()
    snapshot = snapshot_digest(
        key=key,
        dp=DP_ID,
        material_sha256=digest,
        evidence_sha256=evidence,
        rows_sha256=rows_sha256,
        basis_sha256=basis_sha,
    )
    return SignoffResult(
        key=key,
        logical_id=logical_id,
        dp=DP_ID,
        decision_id=decision_id,
        conclusion=conclusion,
        material_sha256=digest,
        evidence_sha256=evidence,
        rows_sha256=rows_sha256,
        snapshot_sha256=snapshot,
        product_type=PRODUCT_TYPE,
        native_basis=basis_dict,
        basis_sha256=basis_sha,
        basis_version=bound_basis.version,
        prepared_proof=dict(prepared_proof) if prepared_proof is not None else None,
        material={
            str(name): item
            for name, item in (snapshot_material if snapshot_material is not None else material).items()
        },
        task_key=task_key,
        initiator_role=initiator_role,
        retry_of=retry_of,
        transport=transport,
        model=model,
        confidence_source=confidence_source,
        ts=ts
        or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    )


def _redact_tree(value: object, redact: object, *, depth: int = 0) -> object:
    if depth > 16:
        raise SignoffResultError("material is nested too deeply")
    if isinstance(value, str):
        try:
            result = redact.redact(value)  # type: ignore[attr-defined]
            text = getattr(result, "text", None)
        except Exception:  # noqa: BLE001 - a broken redactor never proves text safe
            raise SignoffResultError("material could not be proven secret-free") from None
        if not isinstance(text, str):
            raise SignoffResultError("material could not be proven secret-free")
        return text
    if isinstance(value, Mapping):
        return {
            str(name): _redact_tree(item, redact, depth=depth + 1)
            for name, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_tree(item, redact, depth=depth + 1) for item in value]
    return value


def write_result(
    key_dir: pathlib.Path | str,
    result: SignoffResult,
    *,
    redact: object,
) -> pathlib.Path:
    """Publish the minimal record atomically; an existing different record is kept.

    The stored ``material`` is the redacted audit copy. The comparison source is
    ``material_sha256`` of the *sent* material, so redaction can never weaken the
    change check. A second, different record for the same ``logical_id`` is
    refused instead of overwriting the previous decision's snapshot.
    """
    if not isinstance(result, SignoffResult):
        raise SignoffResultError("result is not a SignoffResult")
    if redact is None:
        raise SignoffResultError("redact is required: a record needs a known set")
    path = result_path(key_dir, result.logical_id)
    material = _redact_tree(dict(result.material), redact)
    payload = result.as_dict()
    payload["material"] = material
    if result.prepared_proof is not None:
        payload["prepared_proof"] = _redact_tree(dict(result.prepared_proof), redact)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        existing = _safe_read_text(key_dir, path)
        if existing == text:
            return path
        raise SignoffResultError(
            "a different result record already exists for this logical_id"
        )
    return _atomic_write_text(key_dir, path, text)


def _result_from_mapping(raw: Mapping[str, Any]) -> SignoffResult:
    known = set(SignoffResult.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = [name for name in raw if name not in known]
    if unknown:
        raise SignoffResultError(f"result record carries {len(unknown)} unknown key(s)")
    version = raw.get("record_version")
    if isinstance(version, bool) or version != RESULT_VERSION:
        raise SignoffResultError("result record version is not supported")
    for required in (
        "key",
        "logical_id",
        "dp",
        "decision_id",
        "conclusion",
        "material_sha256",
        "evidence_sha256",
        "rows_sha256",
        "snapshot_sha256",
    ):
        if required not in raw:
            raise SignoffResultError(f"result record is missing {required}")
    if raw["dp"] != DP_ID:
        raise SignoffResultError(
            "result record dp is not the active key-signoff point"
        )
    product_type = raw.get("product_type")
    if product_type is None:
        # Pre-T22 v2 records carry no typed discriminator. They are read as
        # key-signoff history, never as an authority-change product.
        product_type = PRODUCT_TYPE
    if product_type != PRODUCT_TYPE:
        raise SignoffResultError(
            "result record product_type is not the key-signoff product"
        )
    conclusion = raw["conclusion"]
    if conclusion not in CONCLUSIONS:
        raise SignoffResultError("result record conclusion is not in the closed set")
    decision_id = str(raw["decision_id"])
    if not decision_id.startswith(DP_ID + ":"):
        raise SignoffResultError(
            "result record decision_id does not name the active key-signoff point"
        )
    material = raw.get("material")
    if not isinstance(material, Mapping):
        raise SignoffResultError("result record material is not a mapping")
    native_basis_raw = raw.get("native_basis")
    basis_sha = raw.get("basis_sha256")
    basis_version = raw.get("basis_version")
    if native_basis_raw is None:
        # Pre-native-basis records stay readable as history; they are never
        # current proof (validate_key_signoff requires a bound basis).
        if basis_sha is not None or basis_version is not None:
            raise SignoffResultError("result record carries a partial native basis")
        basis_payload = None
        basis_hash = None
        basis_schema = None
    else:
        if not isinstance(native_basis_raw, Mapping):
            raise SignoffResultError("result record native_basis is not a mapping")
        bound = _native_basis_from_mapping(native_basis_raw)
        basis_hash = _check_hash("basis_sha256", basis_sha)
        if isinstance(basis_version, bool) or basis_version != bound.version:
            raise SignoffResultError("result record basis_version does not match")
        if bound.digest() != basis_hash:
            raise SignoffResultError("result record native_basis digest does not match")
        basis_payload = bound.as_dict()
        basis_schema = bound.version
    return SignoffResult(
        key=str(raw["key"]),
        logical_id=_check_logical_id(raw["logical_id"]),
        dp=DP_ID,
        decision_id=str(raw["decision_id"]),
        conclusion=str(conclusion),
        material_sha256=_check_hash("material_sha256", raw["material_sha256"]),
        evidence_sha256=_check_hash("evidence_sha256", raw["evidence_sha256"]),
        rows_sha256=_check_hash("rows_sha256", raw["rows_sha256"]),
        snapshot_sha256=_check_hash("snapshot_sha256", raw["snapshot_sha256"]),
        product_type=PRODUCT_TYPE,
        native_basis=basis_payload,
        basis_sha256=basis_hash,
        basis_version=basis_schema,
        material={str(name): item for name, item in material.items()},
        task_key=raw.get("task_key") if isinstance(raw.get("task_key"), str) else None,
        initiator_role=str(raw.get("initiator_role") or "unknown"),
        retry_of=raw.get("retry_of") if isinstance(raw.get("retry_of"), str) else None,
        transport=raw.get("transport") if isinstance(raw.get("transport"), str) else None,
        model=raw.get("model") if isinstance(raw.get("model"), str) else None,
        confidence_source=(
            raw.get("confidence_source")
            if isinstance(raw.get("confidence_source"), str)
            else None
        ),
        ts=raw.get("ts") if isinstance(raw.get("ts"), str) else None,
        prepared_proof=(
            dict(raw["prepared_proof"])
            if isinstance(raw.get("prepared_proof"), Mapping) else None
        ),
    )


def read_result(
    key_dir: pathlib.Path | str, logical_id: str
) -> SignoffResult | None:
    """Read one exact ``logical_id`` record; ``None`` only when it is absent.

    A present-but-unreadable/unknown record raises: "cannot read" must never
    look like "no record", and the caller must refuse to guess instead of
    re-asking the model.
    """
    path = result_path(key_dir, logical_id)
    if not path.exists():
        return None
    text = _safe_read_text(key_dir, path)
    try:
        raw = json.loads(text)
    except ValueError:
        raise SignoffResultError("result record is not valid JSON") from None
    if not isinstance(raw, Mapping):
        raise SignoffResultError("result record is not a JSON object")
    return _result_from_mapping(raw)


# ---------------------------------------------------------------------------
# Valid sign-off file: parse + validate (credential-free T06 face)
# ---------------------------------------------------------------------------


def parse_machine_lines(text: str) -> dict[str, str]:
    """Column-0 ``name: value`` machine lines (first occurrence wins)."""
    found: dict[str, str] = {}
    for match in _MACHINE_LINE_RE.finditer(text):
        found.setdefault(match.group(1), match.group(2))
    return found


@dataclass(frozen=True)
class SignoffValidation:
    """Result of :func:`validate_signoff` (never raises on invalid content)."""

    valid: bool
    reason: str
    path: str | None = None
    logical_id: str | None = None
    snapshot_sha256: str | None = None
    material_sha256: str | None = None
    evidence_sha256: str | None = None
    conclusion: str | None = None
    dp: str | None = None
    product_type: str | None = None
    file_sha256: str | None = None
    record_version: int | None = None
    decision_id: str | None = None
    basis_version: int | None = None
    basis_sha256: str | None = None
    native_basis_verified: bool = False
    decision_source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "path": self.path,
            "logical_id": self.logical_id,
            "snapshot_sha256": self.snapshot_sha256,
            "material_sha256": self.material_sha256,
            "evidence_sha256": self.evidence_sha256,
            "conclusion": self.conclusion,
            "dp": self.dp,
            "product_type": self.product_type,
            "file_sha256": self.file_sha256,
            "record_version": self.record_version,
            "decision_id": self.decision_id,
            "basis_version": self.basis_version,
            "basis_sha256": self.basis_sha256,
            "native_basis_verified": self.native_basis_verified,
            "decision_source": self.decision_source,
        }


def _invalid(reason: str, **fields: Any) -> SignoffValidation:
    return SignoffValidation(valid=False, reason=reason, **fields)


def read_local_signoff_proof(
    key_dir: pathlib.Path, key: str, proof_id: object, nonce: object = None,
    *, prepared_snapshot: str | None = None, published_snapshot: str | None = None,
) -> dict | None:
    """Read an attestation only from the native pipe of this key's live PM."""
    if sys.platform != "win32" or not isinstance(proof_id, str) or not re.fullmatch(r"[a-f0-9]{32}", proof_id):
        return None
    if nonce is not None and (not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce)):
        return None
    snapshot = prepared_snapshot if prepared_snapshot is not None else published_snapshot
    if prepared_snapshot is not None and published_snapshot is not None:
        return None
    if snapshot is not None and (nonce is None or not _SHA256_RE.fullmatch(snapshot)):
        return None
    import _winapi
    from multiprocessing.connection import PipeConnection
    from autopilot import state
    from review_observation import _pipe_peer

    rows = [row for row in state.read_index(key_dir.parent.parent) if row.get("key") == key]
    if len(rows) != 1 or rows[0].get("status") != "active":
        return None
    claim = rows[0].get("claim_id") or ""
    if state.claim_state(claim) != state.CLAIM_LIVE:
        return None
    try:
        pid = int(claim.rsplit(":", 1)[1])
        if nonce is not None and pid != os.getppid():
            return None
        address = rf"\\.\pipe\mw-local-sign-{pid}-{proof_id}"
        handle = _winapi.CreateFile(
            address, _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
            0, _winapi.NULL, _winapi.OPEN_EXISTING, _winapi.FILE_FLAG_OVERLAPPED, _winapi.NULL,
        )
        with PipeConnection(handle) as conn:
            if _pipe_peer(conn.fileno(), server=True) != pid:
                return None
            if prepared_snapshot is not None:
                request = f"prepare:{nonce}:{prepared_snapshot}\n"
            elif published_snapshot is not None:
                request = f"publish:{nonce}:{published_snapshot}\n"
            else:
                request = f"write:{nonce}\n" if nonce is not None else "read\n"
            conn.send_bytes(request.encode("ascii"))
            data = bytearray()
            deadline = time.monotonic() + 2
            while len(data) < 65_536 and conn.poll(max(0, deadline - time.monotonic())):
                data.extend(conn.recv_bytes(65_536 - len(data)))
                if data.endswith(b"\n"):
                    proof = json.loads(data)
                    if isinstance(proof, dict) and proof.get("key") == key and proof.get("claim_id") == claim:
                        return proof
                    return None
                if time.monotonic() >= deadline:
                    break
    except (OSError, EOFError, ValueError, IndexError):
        return None
    return None


def capture_local_signoff(key_dir: pathlib.Path, key: str, proof_id: str, proof: dict) -> dict:
    """Bind the private current followup and QG to the native key snapshot."""
    import decide_signoff

    followup = proof.get("followup")
    material = proof.get("material")
    problems = signoff_material_problems(material)
    if problems:
        raise SignoffResultError("; ".join(problems))
    assert isinstance(material, dict)
    verification = material["verification_evidence"]
    if (
        not isinstance(followup, dict)
        or followup.get("verified_source") != "local"
        or followup.get("local_progress") != "verified"
        or not followup.get("qg_refs")
        or verification["unverified"]
        or material["unfinished_impact"]
        or verification["verified"] != followup["qg_refs"]
    ):
        raise SignoffResultError("current independent QG or verified followup is incomplete")
    basis = capture_native_basis(key_dir)
    if issues := basis_usable_now(basis):
        raise SignoffResultError("; ".join(issues))
    facts = decide_signoff.collect(key_dir, key)
    if not facts.chain_ok:
        raise SignoffResultError("decision archive chain is broken")
    closure_evidence = _local_closure_evidence(key_dir, followup)
    material_sha, evidence_sha = digest_material(material)
    record = {
        "record_version": 3,
        "product_type": PRODUCT_TYPE,
        "decision_source": "pm-evidence",
        "key": key,
        "logical_id": proof_id,
        "local_ref": followup["ref"],
        "review_run_id": followup["review_run_id"],
        "review_artifact_sha256": _check_hash("review_artifact_sha256", followup.get("review_artifact_sha256")),
        "conclusion": "finalize",
        "basis_version": basis.version,
        "basis_sha256": basis.digest(),
        "material_sha256": material_sha,
        "evidence_sha256": evidence_sha,
        "rows_sha256": facts.sha256,
        "counted_rows": len(facts.rows),
        "followup_sha256": canonical_sha256(followup),
        "closure_evidence_sha256": closure_evidence,
        "claim_id": proof["claim_id"],
    }
    record["snapshot_sha256"] = canonical_sha256(record)
    return record


def _local_closure_evidence(key_dir: pathlib.Path, followup: dict) -> str:
    """Bind the whole-key QG and achieved artifacts to the attested reviewer."""
    from autopilot import gates
    from autopilot.conductor import _md_section

    for gate in gates.enumerate(key_dir.parent / "_autopilot" / "gates"):
        if gate.key == key_dir.name and gate.status == "pending" and gate.authorizes:
            raise SignoffResultError("current key still has an external authorization gate")
    ref = followup.get("review_artifact_ref")
    if not isinstance(ref, str) or not re.fullmatch(r"workers/[\w.-]+/report\.md", ref):
        raise SignoffResultError("independent review artifact reference is invalid")
    artifact = _assert_safe_target(key_dir, key_dir / ref)
    report = _safe_read_text(key_dir, artifact)
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != followup.get("review_artifact_sha256"):
        raise SignoffResultError("independent review artifact changed")
    qg = _md_section(report, "## Quality Gate Report")
    achieved = _md_section(report, "## Achieved")
    if not qg or not achieved:
        raise SignoffResultError("the independent review did not verify whole-key closure")
    _require_complete_local_qg(key_dir, qg)
    actual_achieved = _safe_read_text(key_dir, key_dir / "achieved.md")
    if actual_achieved.rstrip() != achieved.rstrip():
        raise SignoffResultError("achieved.md does not match the independent closure review")
    for candidate in sorted((key_dir / "evidence").glob("quality-gate-report-*.md")):
        text = _safe_read_text(key_dir, candidate)
        if _md_section(text, "## Quality Gate Report") == qg:
            return canonical_sha256({"qg": text, "achieved": actual_achieved})
    raise SignoffResultError("the current reviewed quality-gate report is missing")


def _require_complete_local_qg(
    key_dir: pathlib.Path, report: str, scope: frozenset[str] | None = None, *, allow_nonpass: bool = False,
) -> list[dict]:
    """Check the outcome and evidence of every applicable frozen criterion."""
    spec = _safe_read_text(key_dir, key_dir / "spec.md")
    design = _safe_read_text(key_dir, key_dir / "design.md")
    goal = _safe_read_text(key_dir.parent, key_dir.parent / GOAL_FILE_NAME)
    contract = contract_guard.extract_contract(spec, design)
    flows = contract_guard.function_flow_identities(design)
    if not contract.acs or not contract.vcs or not flows or not goal.strip():
        raise SignoffResultError("the current spec, design or project goal is incomplete")
    frozen = contract_guard.read_freeze(key_dir)
    if (
        frozen is None
        or (scope is None and frozen.get("decision_signoff") != "required")
        or frozen.get("spec") != contract.acs
        or frozen.get("design") != contract.vcs
        or frozen.get("function_flows") != flows
    ):
        raise SignoffResultError("the current AC, VC or Function Flow differs from the frozen sign-off contract")
    expected = scope if scope is not None else set(contract.ids) | set(flows)
    if not expected or not expected <= set(contract.ids) | set(flows):
        raise SignoffResultError("the review scope does not name current contract criteria")
    results = {}
    statuses = {"PASS": "met"}
    if allow_nonpass:
        statuses.update({"FAIL": "unmet", "NOT-RUN": "not-run", "UNKNOWN": "unknown"})
    observed: dict[pathlib.Path, str] = {}
    project = key_dir.parent.parent
    for name, verdict, evidence in re.findall(
        r"(?m)^\|\s*((?:AC|VC|FLOW)-\d{3})\s*\|([^|\r\n]*)\|([^|\r\n]*)\|", report
    ):
        if scope is not None and name not in scope:
            continue
        status = statuses.get(verdict.strip())
        ref = re.fullmatch(r"([A-Za-z0-9._/-]+)@([a-f0-9]{64})", evidence.strip())
        if name not in expected or name in results or status is None or (status in {"met", "unmet"} and ref is None):
            raise SignoffResultError(f"independent closure review has an invalid outcome for {name}")
        results[name] = {"id": name, "status": status}
        if ref is None:
            if evidence.strip() not in {"", "-", "—"}:
                results[name]["review_note"] = evidence.strip()[:400]
            continue
        relative, digest = ref.groups()
        if relative.startswith("/") or any(part in ("", ".", "..") for part in relative.split("/")):
            raise SignoffResultError(f"invalid evidence path for {name}")
        file = _assert_safe_target(project, project / relative)
        if file not in observed:
            if not file.is_file() or file.stat().st_size > _MAX_RESULT_BYTES:
                raise SignoffResultError(f"current evidence is unavailable for {name}")
            observed[file] = hashlib.sha256(file.read_bytes()).hexdigest()
        if observed[file] != digest:
            raise SignoffResultError(f"evidence bytes changed for {name}")
        results[name]["evidence_sha256"] = digest
    missing = sorted(expected - results.keys())
    if missing:
        raise SignoffResultError("independent closure review is missing " + ", ".join(missing))
    return list(results.values())


def _terminal_review_artifact(
    key_dir: pathlib.Path, key: str, review_task: str, review_source: str,
) -> tuple[dict, str, str, str, str]:
    """Read a source pinned by an independent, successful terminal review."""
    import mw_common
    from autopilot.conductor import _l3_provenance_record

    if not isinstance(review_task, str) or not re.fullmatch(r"[\w-]+[\w.-]*", review_task):
        raise SignoffResultError("invalid independent review task")
    if not isinstance(review_source, str) or not re.fullmatch(r"(?:evidence|workers)/[\w./-]+\.md", review_source):
        raise SignoffResultError("invalid independent review source")
    if any(part in ("", ".", "..") for part in review_source.split("/")):
        raise SignoffResultError("invalid independent review source")
    task_dir = key_dir / "workers" / review_task
    envelope = task_dir / "task.md"
    envelope_text = _safe_read_text(key_dir, envelope)
    headers = dict(re.findall(
        r"(?m)^(type|origin|loop|card_path|card_sha256):[ \t]+([^\n]+)$",
        envelope_text.split("\n\n", 1)[0],
    ))
    conductor_review = (
        headers.get("type") == "reviewer"
        and headers.get("origin") == "conductor"
        and headers.get("loop") == f"l3:{key}"
    )
    card = headers.get("card_path", "")
    if not conductor_review:
        if headers.get("type") != "review" or not re.fullmatch(r"tasks/(?:[\w-]+/)*[\w.-]+\.md", card):
            raise SignoffResultError("independent review must have a dispatched review card")
        card_path = _assert_safe_target(key_dir, key_dir / card)
        if mw_common.sha256_eol_normalized(card_path) != headers.get("card_sha256"):
            raise SignoffResultError("independent review card changed")
    run_text = _safe_read_text(key_dir, task_dir / "run.json")
    run = json.loads(run_text)
    output_ref = (task_dir / "output.md").relative_to(key_dir).as_posix()
    report_path = task_dir / ("output.md" if review_source == output_ref else "report.md")
    report = _safe_read_text(key_dir, report_path)
    queue = mw_common.parse_workers_queue(key_dir.parent / "_workers.parallel")
    rows = [
        row for row in queue["rows"]
        if pathlib.Path(row["task_path"]) == envelope
    ]
    if (
        len(rows) != 1 or rows[0]["status"] != "done" or rows[0]["task_key"] != review_task
        or not isinstance(run, dict) or run.get("kind") != ("reviewer" if conductor_review else "review")
        or run.get("task_key") != review_task or run.get("owner_key") != key
        or run.get("status") != "done" or type(run.get("exit")) is not int or run["exit"] != 0
        or not isinstance(run.get("started_at"), str) or not run.get("ended_at")
        or run.get("run_id") != f"{review_task}@{run['started_at']}"
        or not isinstance(run.get("artifacts"), list) or report_path.name not in run["artifacts"]
    ):
        raise SignoffResultError("independent review has no successful recorded terminal run")
    if conductor_review:
        if rows[0].get("origin") != "conductor" or review_source != report_path.relative_to(key_dir).as_posix():
            raise SignoffResultError("conductor review must use its own terminal artifact")
        provenance = _l3_provenance_record(key_dir, review_task, report_path, "meets")
        if provenance["suspect"] or provenance["anchor_path"] is None:
            raise SignoffResultError("conductor review is missing current L3 trace provenance")
    if review_source != report_path.relative_to(key_dir).as_posix() and f"`{review_source}`" not in report:
        raise SignoffResultError("terminal reviewer did not reference the selected evidence")
    source = _safe_read_text(key_dir, key_dir / review_source)
    return run, run_text, envelope_text, report, source


def capture_reviewed_signoff(
    key_dir: pathlib.Path, key: str, review_task: str, review_source: str,
    *, scope: frozenset[str] | None = None,
) -> dict:
    """Recheck durable independent review and approval evidence from the control workspace."""
    import decide_signoff
    from autopilot.conductor import _md_section

    run, run_text, envelope_text, report, source = _terminal_review_artifact(key_dir, key, review_task, review_source)
    qg = _md_section(source, "## Quality Gate Report")
    if scope is not None:
        if not qg:
            raise SignoffResultError("independent review did not report the requested criteria")
        _require_complete_local_qg(key_dir, qg, scope)
        return {
            "review_task": review_task, "review_run_id": run["run_id"], "review_source": review_source,
            "evidence_sha256": canonical_sha256({
                "source": source, "run": run_text, "envelope": envelope_text,
                "freeze": contract_guard.read_freeze(key_dir), "scope": sorted(scope),
            }),
        }
    achieved = _md_section(source, "## Achieved")
    if not qg or not achieved:
        raise SignoffResultError("independent review is missing whole-key acceptance or achieved")
    _require_complete_local_qg(key_dir, qg)
    if achieved.rstrip() != _safe_read_text(key_dir, key_dir / "achieved.md").rstrip():
        raise SignoffResultError("achieved.md does not match the reviewed result")
    if not any(
        (_md_section(_safe_read_text(key_dir, candidate), "## Quality Gate Report") or "").rstrip() == qg.rstrip()
        for candidate in (key_dir / "evidence").glob("quality-gate-report-*.md")
    ):
        raise SignoffResultError("the current reviewed quality-gate report is missing")
    approvals = _reviewed_approvals(key_dir, key)
    basis = capture_native_basis(key_dir)
    if issues := basis_usable_now(basis):
        raise SignoffResultError("; ".join(issues))
    facts = decide_signoff.collect(key_dir, key)
    if not facts.chain_ok:
        raise SignoffResultError("decision archive chain is broken")
    record = {
        "record_version": 4, "product_type": PRODUCT_TYPE, "decision_source": "pm-evidence",
        "key": key, "conclusion": "finalize", "review_task": review_task,
        "review_run_id": run["run_id"], "review_source": review_source,
        "basis_version": basis.version, "basis_sha256": basis.digest(),
        "material_sha256": canonical_sha256({"achieved": achieved, "review": report}),
        "evidence_sha256": canonical_sha256({
            "source": source, "run": run_text, "envelope": envelope_text, "approvals": approvals,
        }),
        "rows_sha256": facts.sha256, "counted_rows": len(facts.rows),
    }
    record["logical_id"] = canonical_sha256(record)[:32]
    record["snapshot_sha256"] = canonical_sha256(record)
    return record


def _reviewed_approvals(key_dir: pathlib.Path, key: str, *, explicit_only: bool = False) -> dict[str, str]:
    from autopilot import gates

    approvals = {}
    for gate in gates.enumerate(key_dir.parent / "_autopilot" / "gates"):
        if gate.key != key:
            continue
        requires_approval = gate.authorizes or (
            not explicit_only and gate.kind in {"stage-confirm", "stage-close", "goal-change", "xkey-authorize"}
        )
        if not requires_approval:
            continue
        if gate.status != "approved" or (
            not explicit_only and (not gate.answered_by or not gate.answered_at)
        ):
            raise SignoffResultError(f"required approval is unresolved: {gate.id}")
        if gate.authorizes and (
            gate.answer_source == "conductor-auto" or (gate.answered_by or "").startswith("conductor-auto:")
        ):
            raise SignoffResultError(f"required human authorization is unresolved: {gate.id}")
        approvals[gate.id] = canonical_sha256(_safe_read_text(key_dir.parent, gate.path))
    return approvals


def local_signoff_text(record: Mapping) -> str:
    return "# Key sign-off\n\n" + "".join(f"{name}: {value}\n" for name, value in record.items())


def write_local_signoff_result(key_dir: pathlib.Path, record: Mapping) -> pathlib.Path:
    target = result_path(key_dir, record["logical_id"])
    return _atomic_write_text(key_dir, target, json.dumps(record, ensure_ascii=False) + "\n", replace=False)


def local_signoff_matches_disk(key_dir: pathlib.Path, record: Mapping, text: str | None = None) -> bool:
    stored = json.loads(_safe_read_text(key_dir, result_path(key_dir, record["logical_id"])))
    if text is None:
        text = _safe_read_text(key_dir, signoff_path(key_dir))
    return stored == record and text == local_signoff_text(record)


def reviewed_signoff_candidates(key_dir: pathlib.Path, *, unreadable: list[str] | None = None):
    """Find candidate terminal review artifacts and the evidence they explicitly cite."""
    workers = key_dir / "workers"
    for candidate in sorted([*workers.glob("*/report.md"), *workers.glob("*/output.md")]):
        try:
            report = _safe_read_text(key_dir, candidate)
        except (OSError, ValueError) as exc:
            if unreadable is not None:
                unreadable.append(str(exc))
            continue
        refs = [candidate.relative_to(key_dir).as_posix()]
        refs.extend(dict.fromkeys(re.findall(r"`(evidence/[\w./-]+\.md)`", report)))
        for source in refs:
            yield candidate.parent.name, source


def _latest_acted_qg(key_dir: pathlib.Path, key: str) -> dict | None:
    import decide_archive
    import decide_signoff

    if not decide_signoff.collect(key_dir, key).chain_ok:
        return None
    latest_qg = None
    for _, row in decide_archive.iter_rows(decide_signoff.archive_path(key_dir)):
        if row.get("dp") == "dp-QG" and row.get("key") == key and row.get("acted") is True:
            latest_qg = row
    return latest_qg


def _latest_terminal_quality_review(key_dir: pathlib.Path, key: str) -> tuple[str, list[str]] | None:
    from autopilot.conductor import _md_section

    candidates: dict[tuple[datetime.datetime, str], dict[str, str]] = {}
    for task, source in reviewed_signoff_candidates(key_dir):
        try:
            run, _, _, _, text = _terminal_review_artifact(key_dir, key, task, source)
            report = _md_section(text, "## Quality Gate Report")
            if not report:
                continue
            finished = datetime.datetime.fromisoformat(run["ended_at"])
            if finished.tzinfo is None:
                continue
            candidates.setdefault((finished, task), {})[source] = canonical_sha256(report.rstrip())
        except (OSError, ValueError, RuntimeError, TypeError, KeyError):
            continue
    if not candidates:
        return None
    newest = max(finished for finished, _ in candidates)
    current = [(task, sources) for (finished, task), sources in candidates.items() if finished == newest]
    if len(current) != 1:
        return None
    task, sources = current[0]
    if len(set(sources.values())) != 1:
        return None
    return task, list(sources)


def current_review_binding(key_dir: pathlib.Path, key: str) -> dict | None:
    """Read the latest terminal independent quality review for closure."""
    latest_qg = _latest_acted_qg(key_dir, key)
    current = _latest_terminal_quality_review(key_dir, key)
    if current is None:
        return None
    task, sources = current
    for source in sources:
        try:
            record = capture_reviewed_signoff(key_dir, key, task, source)
            if latest_qg is not None:
                # The archived verdict does not prove that it covers this
                # whole-key review. Only a complete review started afterwards
                # can supply a fresh closure basis for that history.
                review_start = datetime.datetime.fromisoformat(record["review_run_id"].split("@", 1)[1])
                last_qg_at = datetime.datetime.fromisoformat(latest_qg["ts"])
                if review_start <= last_qg_at:
                    continue
        except (OSError, ValueError, RuntimeError, TypeError, KeyError, IndexError):
            continue
        binding = {name: record[name] for name in (
            "review_task", "review_run_id", "review_source", "basis_sha256", "material_sha256", "evidence_sha256",
        )}
        return {**binding, "preceding_qg_id": latest_qg.get("decision_id") if latest_qg is not None else None}
    return None


def _published_quality_gate(
    key_dir: pathlib.Path, key: str, source: str, report: str,
) -> dict | None:
    from autopilot.conductor import _md_section, current_contract_done_problems

    published = []
    for candidate in sorted((key_dir / "evidence").glob("quality-gate-report-*.md")):
        document = _safe_read_text(key_dir, candidate)
        section = _md_section(document, "## Quality Gate Report")
        if not section or section.rstrip() != report.rstrip():
            continue
        ref = candidate.relative_to(key_dir).as_posix()
        linked = re.findall(r"(?m)^- source: ([^\r\n]+)$", document)
        expected = f".agenticdoc/{key}/{source}"
        if linked and linked != [expected]:
            continue
        if ref.startswith("evidence/quality-gate-report-contract-") and current_contract_done_problems(key_dir):
            continue
        published.append({"artifact": ref, "publication_sha256": canonical_sha256(document)})
    return published[0] if len(published) == 1 else None


def model_quality_gate(key_dir: pathlib.Path, key: str, binding: Mapping | None) -> dict:
    """Project the current formal QG that the sign-off writer can reverify."""
    from autopilot.conductor import _md_section, current_contract_done_problems

    unknown = {
        "status": "needs-review", "conclusion": None, "object": key,
        "meaning": "The host could not verify a current whole-delivery quality gate. Prepared claims alone cannot authorize finalize.",
    }
    latest = _latest_acted_qg(key_dir, key)
    answer = latest.get("answer") if latest is not None else None
    verdict = (answer.get("qg_verdict") or answer.get("q-verdict")) if isinstance(answer, Mapping) else None
    if isinstance(verdict, Mapping) and verdict.get("value") in ("pass", "fix", "reopen"):
        unknown["last_recorded_decision"] = {"conclusion": verdict["value"], "scope_version_verified": False}
    current = _latest_terminal_quality_review(key_dir, key)
    if current is None:
        return unknown
    task, sources = current
    for source in sources:
        try:
            run, run_text, envelope, _, text = _terminal_review_artifact(key_dir, key, task, source)
            report = _md_section(text, "## Quality Gate Report")
            if not report:
                continue
            criteria = _require_complete_local_qg(key_dir, report, allow_nonpass=True)
            open_items = [item["id"] for item in criteria if item["status"] != "met"]
            basis = capture_native_basis(key_dir)
            if basis_usable_now(basis):
                continue
            if not open_items and (
                binding is None or binding["review_source"] != source
                or current_review_binding(key_dir, key) != binding or current_contract_done_problems(key_dir)
            ):
                continue
            if latest is not None and datetime.datetime.fromisoformat(run["started_at"]) <= datetime.datetime.fromisoformat(latest["ts"]):
                continue
            published = _published_quality_gate(key_dir, key, source, report)
            if published is None:
                continue
            spec = _safe_read_text(key_dir, key_dir / "spec.md")
            design = _safe_read_text(key_dir, key_dir / "design.md")
            definitions = contract_guard.parse_acs(spec) | {
                name: details.split("\x1f", 1)[0] for name, details in contract_guard.parse_vcs(design).items()
            }
            for item in criteria:
                if item["id"] in definitions:
                    item["text"] = definitions[item["id"]]
            return {
                "status": "verified", "conclusion": "fix" if open_items else "pass", "object": key,
                "scope": {"kind": "whole-key", "criteria": criteria}, "open_criteria": open_items,
                "version": {"contract_sha256": basis.digest(), "quality_gate_sha256": canonical_sha256(report.rstrip()), **published},
                "independent_review": {"run_id": run["run_id"], "source": source,
                                       "evidence_sha256": canonical_sha256({"source": text, "run": run_text, "envelope": envelope})},
                "meaning": "Use these independently verified outcomes for the current delivery if prepared claims differ. AC means acceptance criterion, VC means verification criterion, and FLOW means function flow.",
            }
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            continue
    return unknown


def current_scoped_qg_binding(key_dir: pathlib.Path, key: str, scope: frozenset[str]) -> dict | None:
    """Bind a QG pass to the reviewed AC/VC scope, independently of key closure."""
    if not scope:
        return None
    for task, source in reviewed_signoff_candidates(key_dir):
        try:
            return capture_reviewed_signoff(key_dir, key, task, source, scope=scope)
        except (OSError, ValueError, RuntimeError):
            continue
    return None


def publish_reviewed_signoff(
    key_dir: pathlib.Path, key: str, review_task: str, review_source: str,
) -> tuple[str, dict]:
    """Validate and publish one immutable, retryable evidence snapshot."""
    from autopilot import state

    with contract_guard.contract_publication_lock(key_dir):
        rows = [row for row in state.read_index(key_dir.parent.parent) if row["key"] == key]
        if len(rows) != 1 or rows[0]["phase"].upper() not in {"VERIFY", "DONE"}:
            raise SignoffResultError("reviewed evidence sign-off requires an unambiguous VERIFY or DONE key")
        record = capture_reviewed_signoff(key_dir, key, review_task, review_source)
        target = signoff_path(key_dir)
        if target.exists():
            if not local_signoff_matches_disk(key_dir, record):
                raise SignoffResultError("existing sign-off differs from the current reviewed snapshot")
            return "existing", record
        if rows[0]["phase"].upper() != "VERIFY":
            raise SignoffResultError("a new sign-off can only be published during VERIFY")
        try:
            write_local_signoff_result(key_dir, record)
        except FileExistsError:
            stored = _safe_read_text(key_dir, result_path(key_dir, record["logical_id"]))
            if json.loads(stored) != record:
                raise SignoffResultError("existing sign-off result differs from the reviewed snapshot")
        if capture_reviewed_signoff(key_dir, key, review_task, review_source) != record:
            raise SignoffResultError("reviewed evidence changed before sign-off publication")
        write_signoff_text(key_dir, local_signoff_text(record), replace=False)
        return "written", record


def prepare_reviewed_done(key_dir: pathlib.Path, key: str) -> dict:
    """Default Done preflight shared by interactive and conductor PMs."""
    import decide_signoff
    import decision

    cfg, _ = decision.DecisionConfig.from_project(key_dir.parent.parent)
    _reviewed_approvals(key_dir, key, explicit_only=True)
    if cfg.signoff_error:
        raise SignoffResultError(cfg.signoff_error)
    if cfg.signoff == decision.SIGNOFF_DISABLE:
        return {"signoff_status": "disabled"}
    frozen = contract_guard.read_freeze(key_dir) or {}
    spec = key_dir / "spec.md"
    spec_text = _safe_read_text(key_dir, spec) if spec.is_file() else ""
    required = (
        frozen.get("decision_signoff") == "required"
        or re.search(r"(?im)^\s*(?:>\s*)?Decision signoff:\s*required\s*$", spec_text)
        or decide_signoff.collect(key_dir, key).rows
    )
    if not required:
        return {"signoff_status": "not-required"}
    if signoff_path(key_dir).exists():
        _reviewed_approvals(key_dir, key)
        validation = validate_signoff(key_dir, key)
        if not validation.valid or not validation.native_basis_verified:
            raise SignoffResultError(f"existing sign-off is not current: {validation.reason}")
        return {"signoff_status": "existing", "logical_id": validation.logical_id}
    failures = []
    for task, source in reviewed_signoff_candidates(key_dir, unreadable=failures):
        try:
            status, record = publish_reviewed_signoff(key_dir, key, task, source)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"{task}: {exc}")
            continue
        return {"signoff_status": status, "logical_id": record["logical_id"]}
    detail = "; ".join(dict.fromkeys(failures[-5:]))
    raise SignoffResultError(f"no current independent closure review{': ' + detail if detail else ''}")


def _validate_local_signoff(
    key_dir: pathlib.Path, key: str, text: str, lines: dict[str, str],
    expected_logical_id: str | None, expected_snapshot: str | None,
) -> SignoffValidation:
    path = str(signoff_path(key_dir))
    logical_id = lines.get("logical_id")
    durable = lines.get("record_version") == "4"
    try:
        if durable:
            current = capture_reviewed_signoff(key_dir, key, lines.get("review_task", ""), lines.get("review_source", ""))
            published = True
        else:
            proof = read_local_signoff_proof(key_dir, key, logical_id)
            if proof is None or logical_id is None:
                return _invalid("current PM evidence attestation is unavailable", path=path)
            current = capture_local_signoff(key_dir, key, logical_id, proof)
            published = proof.get("publication_sha256") == current["snapshot_sha256"]
        matches = local_signoff_matches_disk(key_dir, current, text)
    except (OSError, ValueError, RuntimeError) as exc:
        return _invalid(str(exc), path=path)
    if (
        not matches
        or not published
        or (expected_logical_id is not None and logical_id != expected_logical_id)
        or (expected_snapshot is not None and current["snapshot_sha256"] != expected_snapshot)
    ):
        return _invalid("PM evidence snapshot no longer matches the signed product", path=path)
    return SignoffValidation(
        valid=True, reason="", path=path, logical_id=logical_id, conclusion="finalize",
        snapshot_sha256=current["snapshot_sha256"], evidence_sha256=current["evidence_sha256"],
        material_sha256=current["material_sha256"], basis_version=current["basis_version"],
        basis_sha256=current["basis_sha256"], record_version=current["record_version"], product_type=PRODUCT_TYPE,
        file_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        native_basis_verified=True, decision_source="pm-evidence",
    )


def validate_signoff(
    key_dir: pathlib.Path | str,
    key: str | None = None,
    *,
    expected_logical_id: str | None = None,
    expected_snapshot: str | None = None,
) -> SignoffValidation:
    """Validate the sign-off file of one key without a model or a credential.

    Rules (all fail closed):

    * the file, and every existing component down from the key dir, must not be
      a symbolic link and must stay inside the key dir (a hash or id never
      exempts this);
    * ``record_version=2``, ``product_type=key-signoff`` and
      ``dp=dp-sign-key`` are required, together with ``logical_id``,
      ``material_sha256``, ``evidence_sha256``, ``rows_sha256`` and
      ``snapshot_sha256``;
    * the conclusion must be the only signing word (``finalize``);
      ``continue`` / ``user-confirm`` are legal menu words but never a
      successful sign-off, and the retired ``narrow`` / ``revoke`` labels (and
      legacy words such as ``approve``/``signed``) are refused;
    * a retired ``dp25-signoff-conclusion`` file (or any other dp) is history,
      never a current valid sign-off;
    * ``snapshot_sha256`` must equal the digest recomputed from the file's own
      material/evidence/archive lines (and its native basis when present);
    * an optional expected ``logical_id``/``snapshot`` must match exactly;
    * if a minimal result record exists for that logical id, it must be readable
      and carry the same logical id + snapshot (a record alone is never valid);
    * a native contract/goal basis written by the producer is re-read from the
      real sources now and must still be the same semantic identity. A record
      from before this schema stays internally valid history but
      ``native_basis_verified`` is false and it is never current proof.

    A legacy file with no ``logical_id`` is invalid (``legacy-no-logical-id``);
    readers keep their existing legacy display instead of inventing a link.
    """
    path = signoff_path(key_dir)
    if not path.exists():
        return _invalid("missing sign-off file", path=str(path))
    try:
        text = _safe_read_text(key_dir, path)
    except SignoffResultError as exc:
        return _invalid(str(exc), path=str(path))
    file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = parse_machine_lines(text)
    if lines.get("decision_source") == "pm-evidence":
        return _validate_local_signoff(
            pathlib.Path(key_dir), key or pathlib.Path(key_dir).name, text, lines,
            expected_logical_id, expected_snapshot,
        )
    if "logical_id" not in lines:
        return _invalid("legacy sign-off file has no logical_id", path=str(path), file_sha256=file_hash)
    product_type = lines.get("product_type")
    if product_type != PRODUCT_TYPE:
        return _invalid(
            "product_type is missing or is not the key-signoff product",
            path=str(path),
            file_sha256=file_hash,
        )
    logical_id = lines.get("logical_id") or None
    material = lines.get("material_sha256") or ""
    evidence = lines.get("evidence_sha256") or ""
    rows = lines.get("rows_sha256") or ""
    snapshot = lines.get("snapshot_sha256") or ""
    # `conclusion` and `key` are written by decide_signoff.render but are not
    # part of ``MACHINE_LINE_NAMES`` above (the legacy parser owns their names
    # too); read them explicitly from whole column-0 lines.
    conclusion_match = re.search(r"^conclusion:\s*(.*?)\s*$", text, re.MULTILINE)
    conclusion = conclusion_match.group(1) if conclusion_match else None
    key_match = re.search(r"^key:\s*(.*?)\s*$", text, re.MULTILINE)
    file_key = key_match.group(1) if key_match else ""
    if key is not None and file_key and file_key != key:
        return _invalid("key does not match the sign-off file", path=str(path))
    effective_key = key if key is not None else file_key
    dp = lines.get("dp")
    version = lines.get("record_version")
    basis = lines.get("basis_sha256")
    basis_version_line = lines.get("basis_version")
    fields: dict[str, Any] = {
        "path": str(path),
        "logical_id": logical_id,
        "snapshot_sha256": snapshot or None,
        "material_sha256": material or None,
        "evidence_sha256": evidence or None,
        "conclusion": conclusion,
        "dp": dp,
        "product_type": product_type,
        "file_sha256": file_hash,
        "record_version": int(version) if version and version.isdigit() else None,
        "decision_id": lines.get("decision_id"),
        "basis_sha256": basis or None,
        "basis_version": (
            int(basis_version_line)
            if basis_version_line and basis_version_line.isdigit()
            else None
        ),
    }
    if basis is not None or basis_version_line is not None:
        if basis is None or basis_version_line is None:
            return _invalid("native basis machine lines are incomplete", **fields)
        if basis_version_line != str(BASIS_VERSION):
            return _invalid("native basis version is not supported", **fields)
        if _SHA256_RE.match(basis) is None:
            return _invalid("basis_sha256 is missing or malformed", **fields)
    if not logical_id or _LOGICAL_ID_RE.match(logical_id) is None:
        return _invalid("logical_id is missing or malformed", **fields)
    decision_id = lines.get("decision_id") or ""
    if not decision_id.startswith(DP_ID + ":"):
        return _invalid("decision_id is missing or does not name the dp-sign-key point", **fields)
    if version != str(RESULT_VERSION):
        return _invalid("record_version is not 2", **fields)
    if dp in LEGACY_DP_IDS:
        return _invalid(
            "dp is a retired sign-off point; history is read-only", **fields
        )
    if dp != DP_ID:
        return _invalid("dp is not the current dp-sign-key point", **fields)
    if conclusion not in SIGNING_CONCLUSIONS:
        return _invalid(
            "conclusion is not finalize; continue/user-confirm do not sign off",
            **fields,
        )
    for name, value in (
        ("material_sha256", material),
        ("evidence_sha256", evidence),
        ("rows_sha256", rows),
        ("snapshot_sha256", snapshot),
    ):
        if _SHA256_RE.match(value) is None:
            return _invalid(f"{name} is missing or malformed", **fields)
    recomputed = snapshot_digest(
        key=effective_key,
        dp=DP_ID,
        material_sha256=material,
        evidence_sha256=evidence,
        rows_sha256=rows,
        basis_sha256=basis,
    )
    if recomputed != snapshot:
        return _invalid("snapshot does not match its material/evidence lines", **fields)
    if expected_logical_id is not None and expected_logical_id != logical_id:
        return _invalid("logical_id does not match the expected decision", **fields)
    if expected_snapshot is not None and expected_snapshot != snapshot:
        return _invalid("snapshot does not match the expected snapshot", **fields)
    try:
        record = read_result(key_dir, logical_id)
    except SignoffResultError as exc:
        return _invalid(f"result record is unusable: {exc}", **fields)
    if record is not None and (
        record.logical_id != logical_id
        or record.snapshot_sha256 != snapshot
        or record.material_sha256 != material
    ):
        return _invalid("result record does not match the sign-off file", **fields)
    if record is not None and record.prepared_proof is not None:
        review_binding = record.prepared_proof.get("review_binding")
        if review_binding is not None:
            qg_digest = record.prepared_proof.get("quality_gate_sha256")
            if qg_digest is not None:
                gate = model_quality_gate(key_dir, effective_key, review_binding)
                if gate["status"] != "verified" or gate["conclusion"] != "pass" or canonical_sha256(gate) != qg_digest:
                    return _invalid("the published quality gate or independent review changed since signing", **fields)
            elif current_review_binding(key_dir, effective_key) != review_binding:
                return _invalid("the independent quality review changed since signing", **fields)
        try:
            dependencies = decision_file_evidence.parse_file_evidence(record.prepared_proof)
            if dependencies is not None and decision_file_evidence.check_file_evidence(dependencies).changed:
                return _invalid(
                    "cited file evidence changed since the judgment; a new judgment is required",
                    **fields,
                )
        except decision_file_evidence.FileEvidenceError:
            return _invalid("prepared file evidence metadata is malformed", **fields)
    # Native basis: the file, the record and the sources now must agree. Old
    # internal-consistency-only files remain readable history, never proof.
    if basis is not None:
        if record is None:
            try:
                current = capture_native_basis(key_dir)
            except SignoffResultError as exc:
                return _invalid(f"native basis cannot be read: {exc}", **fields)
            if current.digest() != basis:
                return _invalid(
                    "native contract/goal basis changed since signing", **fields
                )
            fields["native_basis_verified"] = True
        else:
            if record.basis_sha256 != basis:
                return _invalid(
                    "result record does not carry the signed native basis", **fields
                )
            if record.native_basis is None:
                return _invalid(
                    "result record has no native basis for the signed snapshot",
                    **fields,
                )
            if canonical_sha256(dict(record.native_basis)) != basis:
                return _invalid("native basis digest does not match the signed snapshot", **fields)
            try:
                current = capture_native_basis(key_dir)
            except SignoffResultError as exc:
                return _invalid(f"native basis cannot be read: {exc}", **fields)
            problems = native_basis_problems(record.native_basis, current)
            if problems:
                return _invalid(
                    "native contract/goal basis changed: " + "; ".join(problems),
                    **fields,
                )
            fields["native_basis_verified"] = True
    elif record is not None and record.native_basis is not None:
        return _invalid(
            "sign-off file lacks the native basis line of its result record", **fields
        )
    return SignoffValidation(valid=True, reason="", **fields)


def is_valid_signoff(
    key_dir: pathlib.Path | str,
    key: str | None = None,
    *,
    expected_logical_id: str | None = None,
    expected_snapshot: str | None = None,
) -> bool:
    return validate_signoff(
        key_dir,
        key,
        expected_logical_id=expected_logical_id,
        expected_snapshot=expected_snapshot,
    ).valid


# ---------------------------------------------------------------------------
# Typed key-signoff validator (the public read face T25 may call)
# ---------------------------------------------------------------------------

_SIGN_TEXT_FIELDS = ("delivery_goal", "actual_completion")


def _array_problems(name: str, value: object) -> list[str]:
    if not isinstance(value, list):
        return [f"{name} must be a list ([] is a real empty, missing/null is not)"]
    problems: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            problems.append(f"{name}[{index}] must be a non-empty string")
    return problems


def signoff_material_problems(material: object) -> tuple[str, ...]:
    """Problems with the dp-sign-key four parts and three arrays (fail closed).

    ``[]`` is the only representation of a real empty array: a missing key, a
    ``None`` value or a non-list is invalid material, so a caller can never
    turn an unrecorded item into an empty list (or a null into a real "none").
    """
    if not isinstance(material, Mapping):
        return ("material must be the four-part mapping",)
    problems: list[str] = []
    for name in _SIGN_TEXT_FIELDS:
        value = material.get(name)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{name} must be a non-empty string")
    evidence = material.get("verification_evidence")
    if not isinstance(evidence, Mapping):
        problems.append("verification_evidence must be a mapping with two arrays")
    else:
        for name in ("verified", "unverified"):
            problems.extend(
                _array_problems(f"verification_evidence.{name}", evidence.get(name))
            )
    problems.extend(_array_problems("unfinished_impact", material.get("unfinished_impact")))
    return tuple(problems)


@dataclass(frozen=True)
class KeySignoffValidation:
    """Typed, read-only result of :func:`validate_key_signoff`.

    ``signs_key`` is the only success bit for a required key sign-off; it is
    true only for a current, active ``finalize`` whose material/evidence/record
    all match. ``closes_stage`` is always false and ``second_approval`` is
    always zero: a sign-off is never a stage close or a second approval.
    """

    product_type: str
    valid: bool
    reason: str
    key: str
    logical_id: str | None = None
    decision_id: str | None = None
    conclusion: str | None = None
    dp: str | None = None
    material_sha256: str | None = None
    evidence_sha256: str | None = None
    snapshot_sha256: str | None = None
    file_sha256: str | None = None
    record_version: int | None = None
    observed_ts: str | None = None
    basis_sha256: str | None = None
    native_basis_verified: bool = False
    signs_key: bool = False
    writes_signoff: bool = False
    closes_stage: bool = False
    second_approval: int = 0
    problems: tuple[str, ...] = ()
    decision_source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_type": self.product_type,
            "valid": self.valid,
            "reason": self.reason,
            "key": self.key,
            "logical_id": self.logical_id,
            "decision_id": self.decision_id,
            "conclusion": self.conclusion,
            "dp": self.dp,
            "material_sha256": self.material_sha256,
            "evidence_sha256": self.evidence_sha256,
            "snapshot_sha256": self.snapshot_sha256,
            "file_sha256": self.file_sha256,
            "record_version": self.record_version,
            "observed_ts": self.observed_ts,
            "basis_sha256": self.basis_sha256,
            "native_basis_verified": self.native_basis_verified,
            "signs_key": self.signs_key,
            "writes_signoff": self.writes_signoff,
            "closes_stage": self.closes_stage,
            "second_approval": self.second_approval,
            "problems": list(self.problems),
            "decision_source": self.decision_source,
        }


def _key_signoff_invalid(
    key: str, reason: str, **fields: Any
) -> KeySignoffValidation:
    return KeySignoffValidation(
        product_type=PRODUCT_TYPE,
        valid=False,
        reason=reason,
        key=key,
        signs_key=False,
        problems=(reason,),
        **fields,
    )


def validate_key_signoff(
    key_dir: pathlib.Path | str,
    key: str,
    expected_matter: Mapping | object,
    current_evidence: Mapping | str | object,
    *,
    expected_logical_id: str | None = None,
    expected_snapshot: str | None = None,
) -> KeySignoffValidation:
    """Validate a *current* key sign-off against the matter and evidence now.

    A file that is internally consistent is not enough (design D-007): the
    caller passes the approved four-part ``expected_matter`` and the
    ``current_evidence`` it is relying on, and both digests must still match
    the signed file. Only an active ``finalize`` with a matching typed result
    record can be the success condition; ``continue``/``user-confirm``, legacy
    words, a retired ``dp25`` file and an ``authority-change`` product are all
    refused. This function is read-only and never writes a sign-off, closure or
    approval.
    """
    if not isinstance(key, str) or not key:
        return _key_signoff_invalid("", "key is missing")
    validation = validate_signoff(
        key_dir,
        key,
        expected_logical_id=expected_logical_id,
        expected_snapshot=expected_snapshot,
    )
    common: dict[str, Any] = {
        "logical_id": validation.logical_id,
        "decision_id": validation.decision_id,
        "conclusion": validation.conclusion,
        "dp": validation.dp,
        "material_sha256": validation.material_sha256,
        "evidence_sha256": validation.evidence_sha256,
        "snapshot_sha256": validation.snapshot_sha256,
        "file_sha256": validation.file_sha256,
        "record_version": validation.record_version,
        "basis_sha256": validation.basis_sha256,
        "native_basis_verified": validation.native_basis_verified,
        "decision_source": validation.decision_source,
    }
    if not validation.valid:
        return _key_signoff_invalid(key, validation.reason, **common)
    if not validation.native_basis_verified:
        return _key_signoff_invalid(
            key,
            "sign-off has no current native contract/goal basis; it is history, not proof",
            **common,
        )
    if validation.conclusion != "finalize":
        return _key_signoff_invalid(
            key, "conclusion is not finalize; this is not a key sign-off", **common
        )
    problems = signoff_material_problems(expected_matter)
    if problems:
        return _key_signoff_invalid(
            key,
            "expected matter is not valid key-signoff material: " + "; ".join(problems),
            **common,
        )
    assert isinstance(expected_matter, Mapping)
    material_digest, evidence_digest = digest_material(expected_matter)
    if material_digest != validation.material_sha256:
        return _key_signoff_invalid(
            key, "material does not match the current approved matter", **common
        )
    if evidence_digest != validation.evidence_sha256:
        return _key_signoff_invalid(
            key, "evidence does not match the signed evidence snapshot", **common
        )
    if current_evidence is None:
        return _key_signoff_invalid(key, "current evidence is missing", **common)
    if isinstance(current_evidence, str):
        if _SHA256_RE.match(current_evidence) is None:
            return _key_signoff_invalid(key, "current evidence is not a sha256", **common)
        current_digest = current_evidence
    elif isinstance(current_evidence, Mapping):
        current_digest = canonical_sha256(dict(current_evidence))
    else:
        return _key_signoff_invalid(
            key, "current evidence is neither a mapping nor a sha256", **common
        )
    if current_digest != validation.evidence_sha256:
        return _key_signoff_invalid(
            key, "current evidence does not match the signed evidence", **common
        )
    if validation.decision_source == "pm-evidence":
        return KeySignoffValidation(
            product_type=PRODUCT_TYPE, valid=True, reason="", key=key,
            signs_key=True, writes_signoff=True, **common,
        )
    try:
        record = read_result(key_dir, validation.logical_id or "")
    except SignoffResultError as exc:
        return _key_signoff_invalid(
            key, f"result record is unusable: {exc}", **common
        )
    if record is None:
        return _key_signoff_invalid(key, "result record is missing", **common)
    if record.product_type != PRODUCT_TYPE:
        return _key_signoff_invalid(
            key, "result record is not the key-signoff product", **common
        )
    if record.conclusion != "finalize":
        return _key_signoff_invalid(
            key, "result record conclusion is not finalize", **common
        )
    if record.key != key:
        return _key_signoff_invalid(
            key, "result record belongs to a different key", **common
        )
    if (
        record.logical_id != validation.logical_id
        or record.snapshot_sha256 != validation.snapshot_sha256
        or record.material_sha256 != validation.material_sha256
        or record.evidence_sha256 != validation.evidence_sha256
    ):
        return _key_signoff_invalid(
            key, "result record does not match the sign-off file", **common
        )
    return KeySignoffValidation(
        product_type=PRODUCT_TYPE,
        valid=True,
        reason="",
        key=key,
        logical_id=record.logical_id,
        decision_id=record.decision_id,
        conclusion=record.conclusion,
        dp=record.dp,
        material_sha256=record.material_sha256,
        evidence_sha256=record.evidence_sha256,
        snapshot_sha256=record.snapshot_sha256,
        file_sha256=validation.file_sha256,
        record_version=record.record_version,
        observed_ts=record.ts,
        basis_sha256=validation.basis_sha256,
        native_basis_verified=validation.native_basis_verified,
        signs_key=True,
        writes_signoff=True,
        closes_stage=False,
        second_approval=0,
    )


def write_signoff_text(
    key_dir: pathlib.Path | str, text: str | Sequence[str], *, replace: bool = True
) -> pathlib.Path:
    """Write the sign-off file atomically (temp + fsync + replace) under the key."""
    body = text if isinstance(text, str) else "\n".join(text) + "\n"
    return _atomic_write_text(key_dir, signoff_path(key_dir), body, replace=replace)
