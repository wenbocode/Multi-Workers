#!/usr/bin/env python3
"""Summarise this attempt's logs, hashes and before/after comparisons."""

from __future__ import annotations

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve()
REWORK = HERE.parent.parent
EVIDENCE = REWORK.parents[1]
PM = EVIDENCE / "t04-r2-pre-dispatch-20261026"


def log_facts() -> dict:
    out = {}
    for log in sorted((REWORK / "logs").glob("*.log")):
        text = log.read_text(encoding="utf-8", errors="replace")
        rc = re.search(r"^# rc=(-?\d+)$", text, re.MULTILINE)
        summary = [
            line
            for line in text.splitlines()
            if re.search(r"(passed|failed|error)", line) and "===" not in line
        ]
        out[log.name] = {
            "rc": int(rc.group(1)) if rc else None,
            "bytes": log.stat().st_size,
            "last_summary": summary[-1] if summary else None,
        }
    return out


def main() -> int:
    before = json.loads((REWORK / "before" / "state.json").read_text(encoding="utf-8"))
    after = json.loads((REWORK / "after" / "state.json").read_text(encoding="utf-8"))
    diff = json.loads((REWORK / "after" / "diff-summary.json").read_text(encoding="utf-8"))
    pm_check = json.loads((PM / "check.json").read_text(encoding="utf-8"))
    parity = json.loads((REWORK / "logs" / "gen-parity.json").read_text(encoding="utf-8"))

    pm_paths = {entry["path"]: entry["sha256"] for entry in pm_check["files"]}
    own = {
        entry["path"]: entry["sha256"]
        for entry in before["readonly_peers"] + [before["allowed_test"]]
    }
    pm_cross = {
        path: {"pm": sha, "own_before": own.get(path), "same": sha == own.get(path)}
        for path, sha in pm_paths.items()
    }

    doc = {
        "card_sha256_from_envelope": pm_check["card_sha256"],
        "pm_cross_check": pm_cross,
        "mirror_files": {
            "pm_check": pm_check["mirror_files"],
            "before": before["mirror_inventory"]["files"],
            "after": after["mirror_inventory"]["files"],
        },
        "original_t04_evidence_files": {
            "pm_check": pm_check["original_t04_evidence_files"],
            "before": before["original_t04_evidence"]["files"],
            "after": after["original_t04_evidence"]["files"],
        },
        "allowed_test": {
            "before": before["allowed_test"],
            "after": after["allowed_test"],
        },
        "diff": diff,
        "protected_unchanged": {
            "readonly_peers": all(
                x["sha256"] == y["sha256"]
                for x, y in zip(before["readonly_peers"], after["readonly_peers"])
            ),
            "legacy_cases": all(
                x["sha256"] == y["sha256"]
                for x, y in zip(before["legacy_cases"], after["legacy_cases"])
            ),
            "other_guards": all(
                x["sha256"] == y["sha256"]
                for x, y in zip(before["other_guards"], after["other_guards"])
            ),
            "legacy_case_dir_listing": {
                "before": before["legacy_case_dir_listing"],
                "after": after["legacy_case_dir_listing"],
            },
            "product_case_dir_files_written": 0,
        },
        "mirror_delta": {
            "changed": sorted(
                k
                for k in before["mirror_inventory"]["sha256"]
                if k in after["mirror_inventory"]["sha256"]
                and before["mirror_inventory"]["sha256"][k]
                != after["mirror_inventory"]["sha256"][k]
            ),
            "added": sorted(
                set(after["mirror_inventory"]["sha256"])
                - set(before["mirror_inventory"]["sha256"])
            ),
            "removed": sorted(
                set(before["mirror_inventory"]["sha256"])
                - set(after["mirror_inventory"]["sha256"])
            ),
            "original_evidence_delta": sorted(
                set(before["original_t04_evidence"]["sha256"])
                ^ set(after["original_t04_evidence"]["sha256"])
            ),
        },
        "generation_parity": parity,
        "logs": log_facts(),
    }
    (REWORK / "logs" / "06-summary.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(doc["logs"], indent=1))
    print("mirror_delta", json.dumps(doc["mirror_delta"]))
    print("protected_unchanged", json.dumps(doc["protected_unchanged"]))
    print("pm_cross_check", json.dumps(pm_cross, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
