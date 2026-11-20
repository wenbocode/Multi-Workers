"""Prepare file evidence that a decision model can actually read.

Only references submitted in business material are opened. Source text is a
snapshot, never an instruction to execute commands or recursively follow links.
When the complete request does not fit, an explicitly labelled, line-numbered
excerpt keeps every detected failure/negative/constraint and its neighbours.
This is mechanical excerpting, not a claim that a semantic summary is complete.
"""

from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

import decision
import decision_source_scope
import mw_common

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_REFERENCES = 64

_REFERENCE = re.compile(
    r"(?P<path>[^\r\n<>|\x00]+?\.[A-Za-z][A-Za-z0-9_.-]*)"
    r"(?::(?P<start>-?[0-9]+)(?:-(?P<end>-?[0-9]+))?)?\Z"
)
_DELIMITED = re.compile(r"`([^`\r\n]+)`|\[[^\]\r\n]*\]\(([^)\r\n]+)\)")
_INLINE_LINE_REFERENCE = re.compile(
    r"(?<![\w])((?:[A-Za-z]:[\\/]|\.{0,2}[\\/])?"
    r"[^\s`\[\]()<>;,]+\.[A-Za-z][A-Za-z0-9_.-]*:[0-9]+(?:-[0-9]+)?)(?![\w:-])"
)
_COMMAND = re.compile(
    r"^(?:python[0-9.]*|node|npm|npx|git|bash|sh|pwsh|powershell|cmd(?:\.exe)?|"
    r"cat|type|Get-Content|rg|pytest|echo|curl|wget|Get-ChildItem)\s",
    re.IGNORECASE,
)
_PROTECTED = re.compile(
    r"\b(?:fail(?:ed|ure|ures|ing)?|error(?:s)?|exception|traceback|unverified|"
    r"unproven|unknown|missing|block(?:ed|er|ers|ing)?|constraint(?:s)?|"
    r"must|required|shall|never|cannot|can't|not|no|false|pending|"
    r"incomplete|unresolved|unauthori[sz]ed|denied|reject(?:ed)?|"
    r"risk(?:s)?|limit(?:s|ation|ations)?|P[012])\b|"
    r"失败|错误|异常|未验证|未证|未知|缺少|缺失|阻断|约束|必须|不得|禁止|"
    r"不允许|不能|不支持|尚未|未完成|未解决|未覆盖|未执行|未运行|未批准|未测试|"
    r"无证据|没有|不成立|风险|限制|待验证|待修复|否定",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^\s*(?:#{1,6}\s|(?:Goal|Requirements?|Findings?|Limitations?|"
                      r"Evidence|Scope|Acceptance|Constraints?)\s*:)", re.IGNORECASE)


class SourceMaterialError(ValueError):
    """Field-addressable preparation refusal; messages never contain file text."""

    def __init__(self, issues: tuple[tuple[str, str], ...],
                 file_evidence: list[dict[str, object]] | None = None) -> None:
        self.issues = issues
        self.file_evidence = file_evidence or []
        super().__init__("; ".join(f"{field}: {issue}" for field, issue in issues))


class PreparedSourceState(dict):
    """JSON-native model state with local-only replay dependencies."""

    def __init__(self, state: Mapping) -> None:
        super().__init__(copy.deepcopy(dict(state)))
        self.file_evidence: list[dict[str, object]] = []


@dataclass(frozen=True)
class _Reference:
    field: str
    path: str
    start: int | None
    end: int | None


@dataclass(frozen=True)
class _Snapshot:
    raw: bytes
    lines: list[str]
    sha256: str


def _string_leaves(value: object, field: str = "material") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(field, value)]
    if isinstance(value, Mapping):
        return [leaf for key, child in value.items()
                for leaf in _string_leaves(child, f"{field}.{key}")]
    if isinstance(value, (list, tuple)):
        return [leaf for index, child in enumerate(value)
                for leaf in _string_leaves(child, f"{field}[{index}]")]
    return []


def _references(material: object, source_references: Mapping | None = None,
                preparation: object = None) -> list[_Reference]:
    found: list[_Reference] = []
    leaves = _string_leaves(material)
    if source_references is not None:
        leaves.extend(_string_leaves(source_references, "notes.evidence"))
    if isinstance(preparation, Mapping):
        catalog = preparation.get("basis_catalog")
        if isinstance(catalog, list):
            for index, entry in enumerate(catalog):
                if isinstance(entry, Mapping) and isinstance(entry.get("text"), str):
                    leaves.append((f"preparation.basis_catalog[{index}].text", entry["text"]))
    for field, value in leaves:
        text = value.strip()
        if text.startswith("cmd:") or _COMMAND.match(text) or "://" in text and not _DELIMITED.search(text):
            continue
        # Basis IDs/prose are not file names. Only explicit Markdown/backtick
        # citations or unambiguous file:line citations in basis text are read.
        basis_text = field.startswith("preparation.basis_catalog[")
        candidates = [] if basis_text else [text]
        delimited = list(_DELIMITED.finditer(text))
        candidates.extend(match.group(1) or match.group(2) for match in delimited)
        whole = _REFERENCE.fullmatch(text.strip('"\'`'))
        whole_absolute = whole is not None and (
            pathlib.PureWindowsPath(whole.group("path")).is_absolute() or whole.group("path").startswith("/")
        )
        if basis_text and whole is not None and whole.group("start") is not None:
            candidates.append(text)
        if not whole_absolute:
            candidates.extend(match.group(1) for match in _INLINE_LINE_REFERENCE.finditer(text)
                              if not any(start.start() <= match.start() < start.end() for start in delimited))
        seen: set[tuple[str, int | None, int | None]] = set()
        for candidate in candidates:
            candidate = candidate.strip().strip('"\'`')
            if "://" in candidate or _COMMAND.match(candidate):
                continue
            match = _REFERENCE.fullmatch(candidate)
            if match is None:
                continue
            raw_path = match.group("path")
            # Unquoted prose is not a filename. Windows/Unix absolute paths may
            # contain spaces; a delimited relative reference may contain them.
            if any(char.isspace() for char in raw_path) and candidate == text:
                if not (pathlib.PureWindowsPath(raw_path).is_absolute() or raw_path.startswith("/")):
                    continue
            if ":" in raw_path and not re.match(r"^[A-Za-z]:[\\/]", raw_path):
                continue
            start = int(match.group("start")) if match.group("start") is not None else None
            end = int(match.group("end")) if match.group("end") is not None else start
            # Planned deliverables/action descriptions can legitimately name a
            # file that does not exist yet. Explicit line citations still mean
            # existing source evidence and are checked.
            planned = field.startswith("material.task_deliverables") or bool(
                re.match(r"material\.handling_options\[[0-9]+\]\.(?:description|consequence)(?:\.|$)", field)
            )
            if planned and start is None:
                continue
            key = raw_path, start, end
            if key not in seen:
                found.append(_Reference(field, raw_path, start, end))
                seen.add(key)
    if len(found) > MAX_SOURCE_REFERENCES:
        raise SourceMaterialError((("evidence_sources", "too many file references; narrow the submitted citations"),))
    return found


def _path_key(path: pathlib.Path) -> str:
    return os.path.normcase(str(path)).replace("\\", "/")


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    path_key, root_key = _path_key(path), _path_key(root).rstrip("/")
    return path_key == root_key or path_key.startswith(root_key + "/")


def _scope(project_root: pathlib.Path) -> tuple[list[pathlib.Path], list[str]]:
    try:
        config = mw_common.load_target_config(project_root)
    except (OSError, ValueError, mw_common.TargetConfigError) as exc:
        raise SourceMaterialError((("evidence_sources", f"cannot resolve source read scope ({type(exc).__name__})"),)) from exc
    roots = [project_root.resolve()]
    for key in ("control_root", "game_root", "engine_root", "parent_root", "partition_root"):
        root = config.get(key)
        if isinstance(root, str) and root:
            roots.append(pathlib.Path(root).resolve())
    named = config.get("roots")
    if isinstance(named, Mapping):
        roots.extend(pathlib.Path(root).resolve() for root in named.values() if isinstance(root, str) and root)
    ignore = config.get("ignore")
    deny = ignore.get("deny_globs", []) if isinstance(ignore, Mapping) else []
    if any("{" in str(pattern) or re.search(r"[!+@?*]\(", str(pattern))
           or str(pattern).startswith("!") for pattern in deny):
        raise SourceMaterialError((("evidence_sources", "read-scope deny glob requires an unsupported pattern; source read refused"),))
    return roots, [str(pattern) for pattern in deny]


def _denied(path: pathlib.Path, roots: list[pathlib.Path], deny: list[str]) -> bool:
    names = [_path_key(path)]
    for root in roots:
        if _within(path, root):
            names.append(_path_key(path)[len(_path_key(root).rstrip("/")) + 1:])
    for raw_pattern in deny:
        pattern = os.path.normcase(raw_pattern).replace("\\", "/")
        for name in names:
            if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(name, pattern.removeprefix("**/")):
                return True
            if "/" not in pattern and any(fnmatch.fnmatchcase(part, pattern) for part in name.split("/")):
                return True
    return False


def _read_source(reference: _Reference, project_root: pathlib.Path,
                 roots: list[pathlib.Path], deny: list[str],
                 snapshots: dict[str, _Snapshot],
                 dependencies: dict[str, dict[str, object]],
                 worker_scope: decision_source_scope.WorkerSourceScope | None = None) -> tuple[dict[str, object], list[str]]:
    raw_path = pathlib.Path(reference.path.replace("\\", "/"))
    candidate = raw_path if raw_path.is_absolute() else project_root / raw_path
    if worker_scope is not None:
        try:
            worker_scope.check_path(candidate)
        except (decision_source_scope.WorkerSourceScopeError, OSError, RuntimeError) as exc:
            raise SourceMaterialError(((reference.field, str(exc) if isinstance(exc, decision_source_scope.WorkerSourceScopeError)
                                       else "Worker source scope cannot be resolved"),)) from exc
    try:
        lexical = pathlib.Path(os.path.abspath(candidate))
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        try:
            loose = candidate.resolve()
            safe = any(_within(loose, root) for root in roots)
            safe = safe and not _denied(lexical, roots, deny) and not _denied(loose, roots, deny)
        except (OSError, RuntimeError):
            safe = False
        if safe:
            dependencies[_path_key(lexical)] = {
                "path": str(lexical), "canonical_path": None, "sha256": None, "status": "missing",
            }
        raise SourceMaterialError(((reference.field, "referenced file is missing or cannot be resolved"),)) from exc
    if not any(_within(resolved, root) for root in roots):
        raise SourceMaterialError(((reference.field, "referenced file is outside the configured read roots"),))
    if _denied(lexical, roots, deny) or _denied(resolved, roots, deny):
        raise SourceMaterialError(((reference.field, "referenced file is excluded by the read-scope deny globs"),))
    dependency: dict[str, object] = {
        "path": str(lexical), "canonical_path": str(resolved), "sha256": None, "status": "unreadable",
    }
    dependencies[_path_key(lexical)] = dependency
    path_key = _path_key(resolved)
    snapshot = snapshots.get(path_key)
    if snapshot is None:
        try:
            before = resolved.stat()
            if not resolved.is_file():
                raise SourceMaterialError(((reference.field, "referenced path is not a regular file"),))
            if before.st_size > MAX_SOURCE_BYTES:
                dependency["status"] = "oversized"
                raise SourceMaterialError(((reference.field, "referenced file exceeds the read limit; cite an appropriately sized artifact"),))
            if worker_scope is not None:
                try:
                    worker_scope.charge(resolved, before.st_size)
                except decision_source_scope.WorkerSourceScopeError as exc:
                    raise SourceMaterialError(((reference.field, str(exc)),)) from exc
            before_signature = before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
            with resolved.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                opened_signature = opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns
                if before_signature != opened_signature or candidate.resolve() != resolved:
                    raise SourceMaterialError(((reference.field, "referenced file changed while reading; prepare a stable snapshot"),))
                raw = handle.read(MAX_SOURCE_BYTES + 1)
                descriptor = os.fstat(handle.fileno())
            after = resolved.stat()
            if len(raw) > MAX_SOURCE_BYTES:
                dependency["status"] = "oversized"
                raise SourceMaterialError(((reference.field, "referenced file exceeds the read limit"),))
            descriptor_signature = descriptor.st_dev, descriptor.st_ino, descriptor.st_size, descriptor.st_mtime_ns
            after_signature = after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            if before_signature != descriptor_signature or before_signature != after_signature or candidate.resolve() != resolved:
                raise SourceMaterialError(((reference.field, "referenced file changed while reading; prepare a stable snapshot"),))
            dependency["sha256"] = hashlib.sha256(raw).hexdigest()
            dependency.pop("status", None)
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise SourceMaterialError(((reference.field, "referenced file is unreadable or is not UTF-8 text"),)) from exc
        if "\x00" in text or any(ord(char) < 32 and char not in "\t\r\n" for char in text):
            raise SourceMaterialError(((reference.field, "referenced file contains binary/control data"),))
        lines = text.splitlines(keepends=True)
        if not lines or not text.strip():
            raise SourceMaterialError(((reference.field, "referenced file is empty"),))
        snapshot = _Snapshot(raw, lines, hashlib.sha256(raw).hexdigest())
        snapshots[path_key] = snapshot
        if sum(len(item.raw) for item in snapshots.values()) > MAX_TOTAL_SOURCE_BYTES:
            raise SourceMaterialError((("evidence_sources", "total cited files exceed the read limit; narrow the citations"),))
    raw, lines, sha = snapshot.raw, snapshot.lines, snapshot.sha256
    dependency["sha256"] = sha
    dependency.pop("status", None)
    start = reference.start if reference.start is not None else 1
    end = reference.end if reference.end is not None else len(lines)
    if start < 1 or end < start or end > len(lines):
        raise SourceMaterialError(((reference.field, "referenced line range is outside the file or reversed"),))
    selected = lines[start - 1:end]
    identity = json.dumps([_path_key(resolved), sha, start, end], ensure_ascii=False)
    source: dict[str, object] = {
        "source_id": "src-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
        "path": str(resolved),
        "sha256": sha,
        "source_bytes": len(raw),
        "source_lines": len(lines),
        "line_range": [start, end],
        "representation": "full" if start == 1 and end == len(lines) else "excerpt",
        "text": "".join(selected),
        "included_lines": [[start, end]],
        "omitted_lines": [],
        "references": [reference.field],
    }
    return source, selected


def _ranges(numbers: set[int]) -> list[list[int]]:
    ranges: list[list[int]] = []
    for number in sorted(numbers):
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1][1] = number
        else:
            ranges.append([number, number])
    return ranges


def _excerpt(source: dict[str, object], lines: list[str], kept: set[int]) -> dict[str, object]:
    start = source["line_range"][0]
    selected = {start + index for index in kept}
    omitted = set(range(start, start + len(lines))) - selected
    out = dict(source)
    out.update(
        representation="excerpt",
        included_lines=_ranges(selected),
        omitted_lines=_ranges(omitted),
        text="\n".join(f"{start + index}: {lines[index].rstrip(chr(10) + chr(13))}" for index in sorted(kept)),
        compression="Mechanical excerpt; omitted lines are not reviewed evidence. No semantic completeness is claimed.",
    )
    return out


def _fits(state: Mapping, questions: Mapping | None, max_state_bytes: int,
          max_total_tokens: int, max_state_plus_question_tokens: int) -> bool:
    encoded = decision._encode_state(state)
    state_tokens = decision._estimate_tokens(encoded.decode("utf-8"))
    question_tokens = [decision._estimate_tokens(json.dumps(spec, ensure_ascii=False, default=str))
                       for spec in (questions or {}).values()]
    return (not max_state_bytes or len(encoded) <= max_state_bytes) and (
        state_tokens + max(question_tokens, default=0) <= max_state_plus_question_tokens
        and state_tokens + sum(question_tokens) <= max_total_tokens
    )


def prepare_source_state(
    state: Mapping,
    project_root: pathlib.Path | str | None,
    *,
    max_state_bytes: int = 0,
    max_total_tokens: int = 65536,
    max_state_plus_question_tokens: int = 32768,
    questions: Mapping | None = None,
    source_references: Mapping | None = None,
) -> dict:
    """Hydrate precise file citations, deduplicate, and fit explicit excerpts.

    A no-reference request is deep-copied without reading workspace config.
    Caller-supplied ``evidence_sources`` is never trusted: this function owns
    that field and regenerates it from the submitted material on every call.
    Plain future output paths under task_deliverables and action descriptions
    are not evidence; explicit line citations in those fields still are.
    """
    prepared = PreparedSourceState(state)
    prepared.pop("evidence_sources", None)
    references = _references(prepared.get("material"), source_references, prepared.get("preparation"))
    if not references:
        return prepared
    if project_root is None:
        raise SourceMaterialError((("evidence_sources", "project root is required to read cited files"),))
    root = pathlib.Path(project_root).resolve()
    try:
        worker_scope = decision_source_scope.load_worker_source_scope(root)
    except decision_source_scope.WorkerSourceScopeError as exc:
        raise SourceMaterialError((("evidence_sources", str(exc)),)) from exc
    config_path = root / ".agenticdoc" / "target.yml"
    config_dependency: dict[str, object] = {
        "path": str(config_path), "canonical_path": None, "sha256": None, "status": "missing",
    }
    try:
        if config_path.exists():
            config_dependency["canonical_path"] = str(config_path.resolve())
            with config_path.open("rb") as handle:
                config_bytes = handle.read(MAX_SOURCE_BYTES + 1)
            if len(config_bytes) > MAX_SOURCE_BYTES:
                config_dependency["status"] = "oversized"
            else:
                config_dependency["sha256"] = hashlib.sha256(config_bytes).hexdigest()
                config_dependency.pop("status", None)
    except OSError:
        config_dependency["status"] = "unreadable"
    dependencies = {_path_key(config_path): config_dependency}
    if worker_scope is not None:
        dependency = worker_scope.dependency
        dependencies[_path_key(pathlib.Path(str(dependency["path"])))] = dependency
    prepared.file_evidence = list(dependencies.values())
    if config_dependency.get("status") == "oversized":
        raise SourceMaterialError((("evidence_sources", "source read-scope config exceeds the read limit"),),
                                  file_evidence=prepared.file_evidence)
    try:
        roots, deny = _scope(root)
    except SourceMaterialError as exc:
        exc.file_evidence = copy.deepcopy(list(dependencies.values()))
        raise
    sources: list[dict[str, object]] = []
    source_lines: list[list[str]] = []
    seen: dict[str, int] = {}
    snapshots: dict[str, _Snapshot] = {}
    for reference in references:
        try:
            source, lines = _read_source(reference, root, roots, deny, snapshots, dependencies, worker_scope)
        except SourceMaterialError as exc:
            exc.file_evidence = copy.deepcopy(list(dependencies.values()))
            raise
        source_id = str(source["source_id"])
        if source_id in seen:
            existing = sources[seen[source_id]]["references"]
            if reference.field not in existing:
                existing.append(reference.field)
            continue
        seen[source_id] = len(sources)
        sources.append(source)
        source_lines.append(lines)
    prepared.file_evidence = copy.deepcopy(list(dependencies.values()))
    prepared["evidence_sources"] = sources
    if _fits(prepared, questions, max_state_bytes, max_total_tokens, max_state_plus_question_tokens):
        return prepared

    # Every detected negative/constraint, section heading and its immediate
    # neighbours is protected. First and last lines give each source context.
    kept_by_source: list[set[int]] = []
    for lines in source_lines:
        anchors = {0, len(lines) - 1}
        anchors.update(index for index, line in enumerate(lines) if _PROTECTED.search(line) or _HEADING.search(line))
        kept_by_source.append({near for index in anchors for near in (index - 1, index, index + 1)
                               if 0 <= near < len(lines)})
    prepared["evidence_sources"] = [_excerpt(source, lines, kept)
                                     for source, lines, kept in zip(sources, source_lines, kept_by_source)]
    if not _fits(prepared, questions, max_state_bytes, max_total_tokens, max_state_plus_question_tokens):
        raise SourceMaterialError(((
            "evidence_sources",
            "compression-required: protected evidence and core material exceed the request budget; "
            "prepare narrower explicit line citations or an independently sourced summary artifact",
        ),), file_evidence=prepared.file_evidence)

    # Expand each source by the same fraction of its remaining lines. Binary
    # search bounds preparation time even for an 8 MiB, many-line log; the
    # protected minimum above guarantees that no source is dropped entirely.
    remaining = [sorted(set(range(len(lines))) - kept)
                 for lines, kept in zip(source_lines, kept_by_source)]
    maximum_remaining = max(map(len, remaining))
    low, high = 0, maximum_remaining
    best = prepared["evidence_sources"]
    while low <= high:
        amount = (low + high) // 2
        expanded = []
        for source, lines, kept, available in zip(sources, source_lines, kept_by_source, remaining):
            count = len(available) * amount // max(1, maximum_remaining)
            expanded.append(_excerpt(source, lines, kept | set(available[:count])))
        prepared["evidence_sources"] = expanded
        if _fits(prepared, questions, max_state_bytes, max_total_tokens, max_state_plus_question_tokens):
            best = expanded
            low = amount + 1
        else:
            high = amount - 1
    prepared["evidence_sources"] = best
    return prepared
