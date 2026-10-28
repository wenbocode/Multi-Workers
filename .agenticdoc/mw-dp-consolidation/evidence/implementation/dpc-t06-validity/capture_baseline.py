"""T06 before-state capture (read-only).

Records, under this card's evidence dir:

* the dispatch card bytes/SHA256/EOL (``workers/dpc-t06-validity/task.md``);
* the approved isolated card bytes/SHA256/EOL (``tasks/isolated/T06-validity.md``)
  and that it matches the dispatch ``card_sha256``;
* the before state of the two product write-face targets (both are expected to
  be absent: the baseline snapshot says ``existed: false``);
* which DAG tasks claim either target path (single-writer check), with their
  current status;
* a full path->sha256 inventory of the isolated implementation worktree, so a
  later run can show exactly which files this card changed.

Usage: python capture_baseline.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY_ROOT = EVIDENCE.parents[2]
REPO = KEY_ROOT.parents[1]
WORKTREE = KEY_ROOT / "implementation-worktree"
PACKAGE = WORKTREE / "packages" / "multi-workers"
CARD = KEY_ROOT / "workers" / "dpc-t06-validity" / "task.md"
ISOLATED_CARD = KEY_ROOT / "tasks" / "isolated" / "T06-validity.md"
DAG = KEY_ROOT / "implementation-isolated-dag.json"
BASELINE = (
    KEY_ROOT / "evidence" / "implementation" / "isolation-baseline-20261026"
    / "approved-file-baselines.json"
)
TARGETS = (
    "packages/multi-workers/decision_validity.py",
    "packages/multi-workers/test_dp_consolidation_concurrency.py",
)


def describe(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "crlf": data.count(b"\r\n"),
        "bare_lf": data.count(b"\n") - data.count(b"\r\n"),
        "utf8_bom": data.startswith(b"\xef\xbb\xbf"),
    }


def inventory(root: pathlib.Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        entries[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def main() -> int:
    dag = json.loads(DAG.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_entries = {entry["source_path"]: entry for entry in baseline}
    card = describe(CARD)
    isolated = describe(ISOLATED_CARD)
    match = re.search(
        r"^card_sha256:\s*([0-9a-f]{64})\s*$",
        CARD.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    declared_card_sha = match.group(1) if match else None
    writers = {}
    for task in dag["tasks"]:
        claimed = [
            path
            for path in task.get("source_product_write_face") or []
            if path in TARGETS
        ]
        if claimed:
            writers[task["id"]] = {
                "task_key": task["task_key"],
                "status": task.get("status"),
                "claimed": claimed,
                "stage": task.get("stage"),
            }
    targets = {}
    for rel in TARGETS:
        mirror = WORKTREE / rel
        live = REPO / rel
        targets[rel] = {
            "mirror_exists": mirror.is_file(),
            "mirror_bytes": mirror.stat().st_size if mirror.is_file() else None,
            "mirror_sha256": (
                hashlib.sha256(mirror.read_bytes()).hexdigest()
                if mirror.is_file()
                else None
            ),
            "live_exists": live.is_file(),
            "baseline_existed": baseline_entries.get(rel, {}).get("existed"),
            "baseline_sha256": baseline_entries.get(rel, {}).get("sha256"),
        }
    payload = {
        "captured_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "card": card,
        "isolated_card": isolated,
        "envelope_declared_card_sha256": declared_card_sha,
        "envelope_card_sha256_matches_isolated_card": (
            declared_card_sha == isolated["sha256"]
        ),
        "targets": targets,
        "write_face_claimants": writers,
        "worktree_file_count": len(inventory(WORKTREE)),
        "worktree_inventory": inventory(WORKTREE),
    }
    (EVIDENCE / "baseline").mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "baseline" / "before.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        key: payload[key]
        for key in (
            "card",
            "isolated_card",
            "envelope_declared_card_sha256",
            "envelope_card_sha256_matches_isolated_card",
            "targets",
            "write_face_claimants",
            "worktree_file_count",
        )
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
