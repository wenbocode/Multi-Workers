"""Compact a complete-SDD PM handoff while retaining a byte-exact archive."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile

from autopilot.active_projection import key_name_refusal, normalize_key, strict_rows_from_bytes
from autopilot.index_parallel import index_lock_path, index_path
from mw_common import acquire_lock, release_lock


SUMMARY_LIMIT = 8 * 1024
STATE_LIMIT = 16 * 1024
SECTIONS = ("Notes", "Task Status", "Decisions", "Evidence Ledger")
FIELDS = re.compile(rb"^- (Key|Phase|Claim-Id|Updated|Completed|PM mode):[^\n]*(?:\n|$)")
PASS_ENTRY = re.compile(rb"^[ \t]*- PASS(?:\b|\xef\xbc\x9a)[^\n]*(?:\n|$)")


def child(directory: Path, name: str) -> Path:
    path = directory / name
    if path.resolve() != path or path.is_symlink():
        raise ValueError(f"Expected a local path under {directory}: {path}")
    return path


def atomic_write(path: Path, content: bytes, *, expected: bytes | None) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not None and path.read_bytes() != expected:
            raise ValueError(f"{path.name} changed during compaction; run preview again")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_summary(text: str) -> bytes:
    summary = text.strip().encode("utf-8")
    if len(summary) > SUMMARY_LIMIT:
        raise ValueError(f"Summary exceeds {SUMMARY_LIMIT} UTF-8 bytes")
    headings = list(re.finditer(rb"^## ([^\n]+)\n", summary, re.MULTILINE))
    if not headings or headings[0].start() or tuple(
        match[1].decode() for match in headings
    ) != SECTIONS:
        raise ValueError(f"Summary must contain these level-two headings in order: {', '.join(SECTIONS)}")
    for heading, end in zip(headings, [next_heading.start() for next_heading in headings[1:]] + [len(summary)]):
        if not summary[heading.end():end].strip():
            raise ValueError(f"Summary section {heading[1].decode()!r} is empty")
    if any(FIELDS.match(line) or PASS_ENTRY.match(line) for line in summary.split(b"\n")):
        raise ValueError("The summary cannot supply machine fields or PASS entries")
    return summary


def compact(project: Path, key: str, summary: bytes, apply_sha: str | None, window_claim: str | None = None) -> dict:
    refusal = key_name_refusal(key)
    if refusal or key != key.strip():
        raise ValueError(refusal[1] if refusal else "Specify the exact registered key")

    with ExitStack() as locks:
        if apply_sha is not None:
            lock_dir = child(project, ".mw")
            for lock in (child(lock_dir, f"key-{normalize_key(key)}.lock"),
                         child(lock_dir, index_lock_path(project).name)):
                acquire_lock(lock, deadline_s=2)
                locks.callback(release_lock, lock)
        agenticdoc = child(project, ".agenticdoc")
        authority = child(agenticdoc, index_path(project).name)
        rows = [row for row in strict_rows_from_bytes(authority.read_bytes())
                if normalize_key(row["key"]) == normalize_key(key)]
        if len(rows) != 1 or rows[0]["key"] != key:
            raise ValueError("Specify one exact, unambiguous key from _index.parallel")
        row = rows[0]
        idle = row["status"] == "idle" and row["claim_id"] in ("", "—", "-")
        if window_claim is not None:
            host, _, pid = window_claim.rpartition(":")
            if (apply_sha is None or row["status"] != "active" or row["claim_id"] != window_claim
                    or host.casefold() != socket.gethostname().casefold() or pid != str(os.getppid())):
                raise ValueError("Apply requires the current local pi parent process and its active claim")
        elif apply_sha is not None and not idle:
            raise ValueError("Apply requires an idle key with no claim in _index.parallel; pause the writers and release the key")

        key_dir = child(agenticdoc, key)
        state = child(key_dir, "pm-state.md")
        if apply_sha is not None:
            lock = child(key_dir, "pm-state.md.lock")
            acquire_lock(lock, deadline_s=2)
            locks.callback(release_lock, lock)
        original = state.read_bytes()
        original.decode("utf-8")
        source_sha = hashlib.sha256(original).hexdigest()
        if apply_sha is not None and apply_sha != source_sha:
            raise ValueError(f"pm-state.md changed since preview (current SHA-256 {source_sha}); run preview again")

        fields = {}
        pass_entries = []
        for fragment in original.splitlines(keepends=True):
            field = FIELDS.match(fragment)
            if field:
                if field[1] in fields:
                    raise ValueError(f"Duplicate machine field: {field[1].decode()}")
                fields[field[1]] = fragment
            elif PASS_ENTRY.match(fragment):
                pass_entries.append(fragment)
        phase = fields.get(b"Phase", b"").partition(b":")[2].strip().decode()
        if phase not in {"SPEC", "DESIGN", "PLAN", "TASKS", "EXECUTE", "VERIFY", "DONE"} or phase != row["phase"].upper():
            raise ValueError("Expected a complete-SDD phase matching _index.parallel")
        if b"Key" in fields and fields[b"Key"].partition(b":")[2].strip().decode() != key:
            raise ValueError("pm-state.md Key does not match _index.parallel")
        if window_claim is not None and fields.get(b"Claim-Id", b"").partition(b":")[2].strip().decode() != window_claim:
            raise ValueError("pm-state.md Claim-Id does not match the current pi claim")
        if phase == "DONE" and b"PASS" in original and not pass_entries:
            raise ValueError("DONE has no explicit PASS entry to preserve; identify the gate evidence before compacting")

        archive_rel = f"pm-state-history/{source_sha}.md.gz"
        title = f"# PM State: {key}\n\n## 1. Snapshot\n".encode()
        machine = b"".join(line if line.endswith(b"\n") else line + b"\n" for line in fields.values())
        evidence = b"".join(line if line.endswith(b"\n") else line + b"\n" for line in pass_entries)
        archive_link = f"\n## Archive\n\n[Previous PM state (gzip)]({archive_rel})\n".encode()
        candidate = title + machine + b"\n" + summary + b"\n\n" + evidence + archive_link
        if b"PASS" not in original and b"PASS" in candidate:
            raise ValueError("The summary would introduce a PASS marker read by the phase gate")
        if len(candidate) > STATE_LIMIT or len(candidate) >= len(original):
            raise ValueError("Compaction must reduce pm-state.md and fit within 16 KiB")

        if apply_sha is not None:
            history = child(key_dir, "pm-state-history")
            history.mkdir(exist_ok=True)
            archive = child(history, f"{source_sha}.md.gz")
            if archive.exists():
                if gzip.decompress(archive.read_bytes()) != original:
                    raise ValueError(f"Existing archive does not match its source SHA-256: {archive}")
            else:
                atomic_write(archive, gzip.compress(original, mtime=0), expected=None)
            atomic_write(state, candidate, expected=original)

        return {"key": key, "phase": phase, "status": row["status"], "claim_id": row["claim_id"],
                "can_apply": idle or window_claim is not None, "applied": apply_sha is not None, "source_sha256": source_sha,
                "before_bytes": len(original), "after_bytes": len(candidate), "archive": archive_rel}


def add_compact_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, type=Path, help="control workspace")
    parser.add_argument("--key", required=True, help="exact registered SDD key")
    parser.add_argument("--summary", required=True, type=Path, help="reviewed Markdown handoff")
    parser.add_argument("--apply", metavar="SOURCE_SHA256", help="apply the preview to an idle key")
    parser.add_argument("--window-claim-id", help=argparse.SUPPRESS)


def cmd_compact(args: argparse.Namespace) -> int:
    try:
        if args.window_claim_id is not None and args.summary == Path("-"):
            # The owning pi process sends the generated Markdown over stdin.
            raw = sys.stdin.buffer.read(SUMMARY_LIMIT + 1)
            if len(raw) > SUMMARY_LIMIT:
                raise ValueError(f"Summary exceeds {SUMMARY_LIMIT} UTF-8 bytes")
            text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        else:
            text = args.summary.read_text(encoding="utf-8-sig")
        result = compact(args.project.resolve(), args.key, validate_summary(text), args.apply, args.window_claim_id)
    except (EOFError, OSError, RuntimeError, ValueError) as error:
        print(f"pm-state: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compact",))
    add_compact_arguments(parser)
    raise SystemExit(cmd_compact(parser.parse_args()))
