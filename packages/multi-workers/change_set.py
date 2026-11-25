"""Per-key write-journal aggregation and closure change-set records.

The change set is the key's own write events, never a repository comparison:

* pi PM windows append one JSON line per successful write/edit/bash target to
  ``.agenticdoc/<key>/write-journal.jsonl`` (shared/write-journal.ts);
* worker windows already record ``[WRITE_FILE]`` / ``[WRITE_UNRESOLVED]`` in
  ``workers/<task>/trace.log`` (shared/change-ledger.ts);
* when no pi tool layer observed the PM (Codex CLI/desktop apply_patch), the
  closure document declares the paths in its ``## 修改面`` section.

``finalize`` folds those three sources into ``change-set.json`` + ``change-set.md``
at done time. Everything under ``.agenticdoc/`` is process state and is excluded.
No git, no baseline snapshot, no patch generation and no agent-called recorder.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys

AGENTICDOC = ".agenticdoc"
JOURNAL_NAME = "write-journal.jsonl"
CHANGE_SET_JSON = "change-set.json"
CHANGE_SET_MD = "change-set.md"
DECLARED_SECTION = "修改面"
MACHINE_SOURCES = ("worker-trace", "pm-tool-result")
DECLARED_SOURCE = "pm-declared"
UNRESOLVED_SOURCE = "unresolved"

WRITE_FILE_RE = re.compile(r"^\[WRITE_FILE\][ \t]+path=(.+?)[ \t]*$")
WRITE_UNRESOLVED_RE = re.compile(r"^\[WRITE_UNRESOLVED\][ \t]+pattern=(\S+)[ \t]+target=(.*)$")
PATH_SHAPE_RE = re.compile(r"^(?:[A-Za-z]:)?/?(?:[\w.-]+/)*[\w.-]+/?$")
QUOTED_PATH_SHAPE_RE = re.compile(r'^(?:[A-Za-z]:)?/?[^<>:"|?*\x00-\x1f\x7f]+$')
KEY_SHAPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
NO_WRITE_MARKERS = ("无改动", "未改动", "无", "none", "n/a", "no changes", "no writes",
                    "无写入", "没有改动")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)
HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def resolve(project: str | Path, key: str) -> tuple[Path, Path]:
    root = Path(project).resolve(strict=True)
    if not KEY_SHAPE_RE.fullmatch(key) or key.startswith("."):
        raise ValueError(f"Invalid key: {key!r}")
    key_dir = root / AGENTICDOC / key
    if not key_dir.is_dir():
        raise ValueError(f"Key directory does not exist: {key_dir}")
    return root, key_dir


def normalize_path(raw: object, project: Path) -> str:
    """Repo-relative, forward-slashed path. An absolute path outside the
    workspace stays absolute (an honest record, not a silently dropped write)."""
    text = str(raw).strip().strip("`\"' \t").replace("\\", "/")
    text = re.sub(r"/{2,}", "/", text)
    text = re.sub(r"^\./", "", text).rstrip("/")
    if text == "":
        return ""
    absolute = text.startswith("/") or re.match(r"^[A-Za-z]:/", text) is not None
    if absolute:
        try:
            return Path(text).resolve().relative_to(project).as_posix()
        except (ValueError, OSError):
            return text
    return text


def is_excluded(rel: str) -> bool:
    """All of .agenticdoc/ is coordination state, never a produced code file."""
    return rel.split("/")[0].casefold() == AGENTICDOC


def section(text: str, heading: str) -> str | None:
    """Body of one H2 section. None means the section is absent (an empty
    section is a real, nonempty distinction for the caller)."""
    cleaned = HTML_COMMENT_RE.sub("", text)
    headings = list(HEADING_RE.finditer(cleaned))
    matches = [i for i, m in enumerate(headings) if m.group(1).strip() == heading]
    if not matches:
        return None
    position = matches[0]
    end = headings[position + 1].start() if position + 1 < len(headings) else len(cleaned)
    return cleaned[headings[position].end():end].strip()


def declared_paths(achieved_text: str) -> tuple[list[str], bool]:
    """Parse the explicit write list. Returns (paths, no-write-acknowledged).

    Only declaration positions count: backticked tokens, the first cell of a
    table row, or the first token of a list item / bare line. Prose references
    and fenced code (quoted diffs) cannot declare a file.
    """
    body = section(achieved_text, DECLARED_SECTION)
    if body is None:
        return [], False
    lines: list[str] = []
    fence: str | None = None
    for line in body.splitlines():
        opened = FENCE_RE.match(line)
        if fence is None:
            if opened is not None:
                fence = opened.group(1)[0]
                continue
            lines.append(line)
        elif opened is not None and opened.group(1)[0] == fence:
            fence = None
    cleaned = "\n".join(lines)
    out: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", stripped)
        if item.startswith("|"):
            item = item[1:].split("|", 1)[0].strip()
        leading_path = re.match(r"^`([^`]+)`", item)
        tokens = re.findall(r"`([^`]+)`", stripped)
        quoted = bool(tokens)
        if not tokens:
            words = item.split()
            tokens = [words[0]] if words else []
        for token in tokens:
            # Backticks already delimit the filename, including any punctuation.
            candidate = token if quoted else token.strip("\"'").rstrip(".,;:，；：")
            candidate = candidate.replace("\\", "/")
            path_shape = QUOTED_PATH_SHAPE_RE if quoted else PATH_SHAPE_RE
            if not path_shape.fullmatch(candidate):
                continue
            trimmed = candidate.rstrip("/")
            explicit_path = leading_path is not None and leading_path.group(1) == token
            if not explicit_path and "." not in trimmed.rsplit("/", 1)[-1] and "/" not in trimmed:
                continue
            out.append(trimmed)
    # A standalone no-write statement is an explicit record; the word 无 inside
    # prose ("无法解析") is not one.
    acknowledged = False
    for line in cleaned.splitlines():
        statement = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line.strip()).strip("。.，,；; ")
        if statement.casefold() in {marker.casefold() for marker in NO_WRITE_MARKERS}:
            acknowledged = True
            break
    return sorted(set(out)), acknowledged


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def read_journal(key_dir: Path) -> tuple[list[dict], int]:
    records: list[dict] = []
    malformed = 0
    for line in _read_lines(key_dir / JOURNAL_NAME):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(entry, dict):
            malformed += 1
            continue
        records.append(entry)
    return records, malformed


def read_worker_traces(key_dir: Path) -> tuple[list[dict], list[dict]]:
    recorded: list[dict] = []
    unresolved: list[dict] = []
    workers = key_dir / "workers"
    if not workers.is_dir():
        return recorded, unresolved
    for trace in sorted(workers.glob("*/trace.log")):
        worker = trace.parent.name
        for line in _read_lines(trace):
            matched = WRITE_FILE_RE.match(line)
            if matched is not None:
                recorded.append({"path": matched.group(1), "source": "worker-trace",
                                 "tool": "write", "worker": worker})
                continue
            unknown = WRITE_UNRESOLVED_RE.match(line)
            if unknown is not None:
                unresolved.append({"source": "worker-trace", "worker": worker,
                                   "pattern": unknown.group(1), "target": unknown.group(2)})
    return recorded, unresolved


def _sha256(project: Path, rel: str) -> tuple[bool, str | None]:
    candidate = Path(rel) if Path(rel).is_absolute() else project / rel
    try:
        if not candidate.is_file():
            return False, None
        return True, hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        return False, None


def _markdown(key: str, data: dict) -> str:
    lines = [
        f"# {key} · 修改面（写事件记录）",
        "",
        f"生成时间：{data['generated_at']}；工作区：`{data['workspace']}`",
        "",
        "记录来自宿主观察到的写事件与本 key 的结案声明，不是仓库对比；`.agenticdoc/` 全部排除。",
        "",
        "| 文件 | 来源 | 工具 | 卡 | 结案时 sha256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in data["files"]:
        digest = item["sha256"][:12] if item["sha256"] else "（文件不存在）"
        lines.append("| `{0}` | {1} | {2} | {3} | `{4}` |".format(
            item["path"], ", ".join(item["sources"]), ", ".join(item["tools"]),
            ", ".join(item["workers"]) or "—", digest))
    if not data["files"]:
        lines.append("| （无） | — | — | — | — |")
    coverage = data["coverage"]
    lines.extend([
        "",
        "## coverage",
        "",
        f"- 机器记录来源：{', '.join(coverage['machine_sources']) or '无'}",
        f"- 机器写事件数：{coverage['machine_record_count']}；无法解析路径的写：{coverage['unresolved_count']}",
        f"- 排除的 `.agenticdoc/` 写事件：{coverage['excluded_agenticdoc_count']}",
        f"- 机器记录里未被声明的路径：{', '.join(coverage['machine_paths_missing_from_declared']) or '无'}",
        f"- 声明中缺少机器记录的路径：{', '.join(coverage['declared_paths_missing_from_machine']) or '无'}",
        f"- 覆盖完整：{'是' if coverage['complete'] else '否'}；{coverage['note']}",
    ])
    if data["unresolved"]:
        lines.extend(["", "## 无法解析路径的写", ""])
        for entry in data["unresolved"]:
            lines.append(f"- {entry['source']} / {entry.get('worker') or '—'}: "
                         f"`{entry['pattern']}` → `{entry['target'][:160]}`")
    return "\n".join(lines) + "\n"


def finalize(project: str | Path, key: str, require_declared: bool = False) -> dict:
    """Fold all write records into the key's change-set artifacts.

    ``require_declared`` makes a missing/empty ``## 修改面`` a hard error; the
    codex-lite done gate validates that earlier and passes False here.
    """
    root, key_dir = resolve(project, key)
    achieved_file = key_dir / "achieved.md"
    achieved_text = achieved_file.read_text(encoding="utf-8") if achieved_file.is_file() else ""
    declared, acknowledged = declared_paths(achieved_text)
    if require_declared and (section(achieved_text, DECLARED_SECTION) is None
                             or (not declared and not acknowledged)):
        raise ValueError("achieved.md 需要非空的 `## 修改面` 段（列出实际写入的代码路径，或明确写“无改动”）")

    journal, malformed = read_journal(key_dir)
    traced, trace_unresolved = read_worker_traces(key_dir)
    machine: list[dict] = []
    unresolved: list[dict] = list(trace_unresolved)
    for entry in journal:
        if entry.get("source") == UNRESOLVED_SOURCE or not entry.get("path"):
            unresolved.append({"source": entry.get("source", "pm-tool-result"),
                               "worker": entry.get("worker"),
                               "pattern": entry.get("pattern", entry.get("tool", "unknown")),
                               "target": str(entry.get("target", ""))})
            continue
        machine.append({"path": entry.get("path"), "source": entry.get("source", "pm-tool-result"),
                        "tool": entry.get("tool", "unknown"), "worker": entry.get("worker"),
                        "ts": entry.get("ts")})
    machine.extend(traced)

    files: dict[str, dict] = {}

    def add(rel: str, source: str, tool: str, worker: object, ts: object) -> None:
        if is_excluded(rel):
            return
        item = files.setdefault(rel, {"path": rel, "sources": [], "tools": [], "workers": [],
                                     "first_write": None, "last_write": None})
        for field, value in (("sources", source), ("tools", tool)):
            if value and value not in item[field]:
                item[field].append(value)
        if worker and str(worker) not in item["workers"]:
            item["workers"].append(str(worker))
        if isinstance(ts, str):
            if item["first_write"] is None or ts < item["first_write"]:
                item["first_write"] = ts
            if item["last_write"] is None or ts > item["last_write"]:
                item["last_write"] = ts

    excluded_seen = 0
    for entry in machine:
        rel = normalize_path(entry.get("path", ""), root)
        if not rel:
            continue
        if is_excluded(rel):
            excluded_seen += 1
            continue
        add(rel, str(entry.get("source")), str(entry.get("tool")), entry.get("worker"), entry.get("ts"))
    declared_set: set[str] = set()
    for path in declared:
        rel = normalize_path(path, root)
        if not rel:
            continue
        if is_excluded(rel):
            excluded_seen += 1
            continue
        declared_set.add(rel)
        add(rel, DECLARED_SOURCE, "declared", None, None)

    ordered = sorted(files.values(), key=lambda item: item["path"])
    for item in ordered:
        item["sources"] = sorted(item["sources"])
        item["tools"] = sorted(item["tools"])
        item["workers"] = sorted(item["workers"])
        exists, digest = _sha256(root, item["path"])
        item["exists"] = exists
        item["sha256"] = digest

    machine_paths = {item["path"] for item in ordered
                     if any(source in MACHINE_SOURCES for source in item["sources"])}
    missing_from_declared = sorted(machine_paths - declared_set) if declared_set else []
    missing_from_machine = sorted(declared_set - machine_paths)
    sources_present = sorted({source for item in ordered for source in item["sources"]
                              if source in MACHINE_SOURCES})
    complete = (bool(sources_present) and not missing_from_declared and not missing_from_machine
                and not unresolved and malformed == 0)
    if not sources_present and declared_set:
        note = "仅 PM 结案声明；未列出的写入无法被发现，不能视为完整覆盖"
    elif not sources_present:
        note = "没有任何机器写记录或结案声明，不能视为完整覆盖"
    elif missing_from_declared:
        note = "机器记录存在未声明的路径，复核时以 change-set.json 为准"
    elif missing_from_machine:
        note = "部分声明路径缺少机器写记录，覆盖不完整"
    elif unresolved or malformed:
        note = "存在无法解析路径的写事件或格式异常的日志行，覆盖不完整"
    else:
        note = "机器写记录覆盖全部列出的路径"
    coverage = {
        "machine_sources": sources_present,
        "machine_record_count": len(machine),
        "declared_paths": sorted(declared_set),
        "declared_required": bool(require_declared),
        "declared_no_write_acknowledged": bool(acknowledged),
        "machine_paths_missing_from_declared": missing_from_declared,
        "declared_paths_missing_from_machine": missing_from_machine,
        "unresolved_count": len(unresolved),
        "malformed_journal_lines": malformed,
        "excluded_agenticdoc_count": excluded_seen,
        "complete": complete,
        "note": note,
    }
    data = {
        "key": key,
        "generated_at": _now(),
        "workspace": str(root),
        "method": "write-events",
        "excluded": [".agenticdoc/**"],
        "files": ordered,
        "unresolved": unresolved,
        "coverage": coverage,
    }
    _atomic_text(key_dir / CHANGE_SET_JSON, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _atomic_text(key_dir / CHANGE_SET_MD, _markdown(key, data))
    return {
        "key": key,
        "change_set": str(key_dir / CHANGE_SET_JSON),
        "markdown": str(key_dir / CHANGE_SET_MD),
        "files": [item["path"] for item in ordered],
        "coverage": coverage,
    }


def record(project: str | Path, key: str, tool: str, path: str, source: str = "pm-tool-result",
           worker: str | None = None, ts: str | None = None) -> dict:
    """Append one successful write event. Host-side entry point; a failed write
    must never call it. Returns the appended event for audit."""
    root, key_dir = resolve(project, key)
    rel = normalize_path(path, root)
    if not rel:
        raise ValueError("A write path is required")
    event = {"ts": ts or _now(), "key": key, "source": source, "tool": tool, "path": rel}
    if is_excluded(rel):
        return {"skipped": True, "reason": ".agenticdoc/ is excluded", "event": event}
    if worker:
        event["worker"] = worker
    journal = key_dir / JOURNAL_NAME
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return {"skipped": False, "event": event}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("record", "finalize"):
        command = sub.add_parser(action)
        command.add_argument("--project", type=Path, default=Path.cwd())
        command.add_argument("--key", required=True)
        if action == "record":
            command.add_argument("--tool", required=True)
            command.add_argument("--path", required=True)
            command.add_argument("--source", default="pm-tool-result")
            command.add_argument("--worker")
            command.add_argument("--ts")
        else:
            command.add_argument("--require-declared", action="store_true")
    args = parser.parse_args()
    if args.action == "record":
        result = record(args.project, args.key, args.tool, args.path, args.source, args.worker, args.ts)
    else:
        result = finalize(args.project, args.key, args.require_declared)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
