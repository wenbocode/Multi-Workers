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

Deliberately not used: the gate ``subject_sha256`` field (no production writer,
dead path) and ``git diff`` (fail-open: ``advance done`` runs before commit in
long keys). The identity anchor is the freeze sidecar only.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import pathlib
import re
from collections.abc import Iterable, Mapping

from autopilot import gates

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
