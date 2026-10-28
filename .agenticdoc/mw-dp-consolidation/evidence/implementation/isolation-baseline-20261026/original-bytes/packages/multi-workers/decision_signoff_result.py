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
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

__all__ = [
    "CONCLUSIONS",
    "DP_ID",
    "MACHINE_LINE_NAMES",
    "RESULT_DIR_PARTS",
    "RESULT_VERSION",
    "SIGNOFF_RELATIVE_PATH",
    "SignoffResult",
    "SignoffResultError",
    "SignoffValidation",
    "assert_safe_target",
    "build_result",
    "canonical_sha256",
    "digest_material",
    "evidence_sha256",
    "is_valid_signoff",
    "parse_machine_lines",
    "read_result",
    "result_path",
    "signoff_path",
    "snapshot_digest",
    "validate_signoff",
    "write_result",
    "write_signoff_text",
]

#: Record schema of the retry face (the decision record version is 2; the sign
#: result record keeps the same generation so a reader never mixes v1/v2 rows).
RESULT_VERSION = 2
#: The only registered dp this record belongs to.
DP_ID = "dp25-signoff-conclusion"
#: The dp25 native answers (design sec 2 dp25).
CONCLUSIONS = ("finalize", "continue", "user-confirm")
#: Where the minimal result record of one logical decision is kept.
RESULT_DIR_PARTS = ("evidence", "review", "decide-results")
#: The only sign-off location the done gate / readers agree on.
SIGNOFF_RELATIVE_PATH = pathlib.Path("evidence") / "review" / "sign-final.md"
#: Machine-line names this module reads. The file is Markdown with these exact
#: column-0 ``name: value`` lines; ``decide_signoff.render`` writes them.
MACHINE_LINE_NAMES = (
    "record_version",
    "dp",
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
)

_LOGICAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+@-]{0,127}$")
#: The result record is a file named after the logical id: keep the name legal on
#: every platform (``:``/``+``/``@`` are legal ledger tokens but not file names).
_RESULT_FILE_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MACHINE_LINE_RE = re.compile(
    r"^(record_version|dp|logical_id|decision_id|material_sha256|evidence_sha256"
    r"|rows_sha256|snapshot_sha256|initiator_role|retry_of|transport|model"
    r"|confidence_source):\s*(.*?)\s*$",
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
) -> str:
    """The single snapshot id of one sign-off (material + evidence + archive).

    ``rows_sha256`` is the archive snapshot the file describes, so an archive
    append after the model call also invalidates the old conclusion.
    """
    return canonical_sha256(
        {
            "key": key,
            "dp": dp,
            "material_sha256": material_sha256,
            "evidence_sha256": evidence_sha256,
            "rows_sha256": rows_sha256,
        }
    )


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
    key_dir: pathlib.Path | str, target: pathlib.Path, text: str
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
        os.replace(tmp, path)
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_version": self.record_version,
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
            "transport": self.transport,
            "model": self.model,
            "confidence_source": self.confidence_source,
            "ts": self.ts,
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
) -> SignoffResult:
    """Build the minimal record of one already-decided dp25 selection.

    ``facts`` is the archive fact object (``decide_signoff.collect``) whose
    ``sha256`` the sign-off file describes; only that stable hash is read here.
    """
    logical_id = _check_logical_id(logical_id)
    if conclusion not in CONCLUSIONS:
        raise SignoffResultError(
            f"conclusion is not valid: expected one of {CONCLUSIONS}"
        )
    if not isinstance(decision_id, str) or not decision_id.startswith(DP_ID + ":"):
        raise SignoffResultError("decision_id is not valid: expected the dp25 form")
    if any(part in decision_id for part in ("/", "\\", "..", "\x00")):
        raise SignoffResultError("decision_id is not valid: no separators or traversal")
    if not isinstance(key, str) or not key:
        raise SignoffResultError("key is not valid: expected a non-empty key")
    rows_sha256 = getattr(facts, "sha256", None)
    rows_sha256 = _check_hash("rows_sha256", rows_sha256)
    digest, evidence = digest_material(material)
    snapshot = snapshot_digest(
        key=key,
        dp=DP_ID,
        material_sha256=digest,
        evidence_sha256=evidence,
        rows_sha256=rows_sha256,
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
        raise SignoffResultError("result record dp is not the dp25 sign-off point")
    conclusion = raw["conclusion"]
    if conclusion not in CONCLUSIONS:
        raise SignoffResultError("result record conclusion is not in the closed set")
    material = raw.get("material")
    if not isinstance(material, Mapping):
        raise SignoffResultError("result record material is not a mapping")
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
    conclusion: str | None = None
    dp: str | None = None
    file_sha256: str | None = None
    record_version: int | None = None
    decision_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "path": self.path,
            "logical_id": self.logical_id,
            "snapshot_sha256": self.snapshot_sha256,
            "material_sha256": self.material_sha256,
            "conclusion": self.conclusion,
            "dp": self.dp,
            "file_sha256": self.file_sha256,
            "record_version": self.record_version,
            "decision_id": self.decision_id,
        }


def _invalid(reason: str, **fields: Any) -> SignoffValidation:
    return SignoffValidation(valid=False, reason=reason, **fields)


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
    * ``record_version=2``, ``dp=dp25-signoff-conclusion`` and a conclusion in
      the dp25 closed set are required, together with ``logical_id``,
      ``material_sha256``, ``evidence_sha256``, ``rows_sha256`` and
      ``snapshot_sha256``;
    * ``snapshot_sha256`` must equal the digest recomputed from the file's own
      material/evidence/archive lines;
    * an optional expected ``logical_id``/``snapshot`` must match exactly;
    * if a minimal result record exists for that logical id, it must be readable
      and carry the same logical id + snapshot (a record alone is never valid).

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
    if "logical_id" not in lines:
        return _invalid("legacy sign-off file has no logical_id", path=str(path), file_sha256=file_hash)
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
    fields: dict[str, Any] = {
        "path": str(path),
        "logical_id": logical_id,
        "snapshot_sha256": snapshot or None,
        "material_sha256": material or None,
        "conclusion": conclusion,
        "dp": dp,
        "file_sha256": file_hash,
        "record_version": int(version) if version and version.isdigit() else None,
        "decision_id": lines.get("decision_id"),
    }
    if not logical_id or _LOGICAL_ID_RE.match(logical_id) is None:
        return _invalid("logical_id is missing or malformed", **fields)
    decision_id = lines.get("decision_id") or ""
    if not decision_id.startswith(DP_ID + ":"):
        return _invalid("decision_id is missing or does not name the dp25 point", **fields)
    if version != str(RESULT_VERSION):
        return _invalid("record_version is not 2", **fields)
    if dp != DP_ID:
        return _invalid("dp is not the dp25 sign-off point", **fields)
    if conclusion not in CONCLUSIONS:
        return _invalid("conclusion is not in the dp25 closed set", **fields)
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


def write_signoff_text(
    key_dir: pathlib.Path | str, text: str | Sequence[str]
) -> pathlib.Path:
    """Write the sign-off file atomically (temp + fsync + replace) under the key."""
    body = text if isinstance(text, str) else "\n".join(text) + "\n"
    return _atomic_write_text(key_dir, signoff_path(key_dir), body)
