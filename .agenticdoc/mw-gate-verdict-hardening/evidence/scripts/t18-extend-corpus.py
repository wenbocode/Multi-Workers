"""Extend the frozen autopilot-config parity corpus with the three G5/G6 keys
(mw-gate-verdict-hardening T-18) and re-freeze it deliberately.

Adds single-key accept cases (the P6 coverage map requires every DEFAULT_CONFIG
key to appear in at least one accepted single-key payload) plus the 1..64 /
10..10000 range rejects that lock the "0/negative is rejected" contract.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = REPO / "packages" / "multi-workers" / "test" / "fixtures" / "autopilot-config-corpus.json"

NEW_CASES = [
    {
        "id": "partial-key-launcher_max_workers",
        "categories": ["D2"],
        "payload_text": json.dumps({"launcher_max_workers": 8}),
        "expected": {"verdict": "accept", "error_fields": []},
    },
    {
        "id": "partial-key-dispatch_max_per_scan",
        "categories": ["D2"],
        "payload_text": json.dumps({"dispatch_max_per_scan": 3}),
        "expected": {"verdict": "accept", "error_fields": []},
    },
    {
        "id": "partial-key-queue_alarm_delta",
        "categories": ["D2"],
        "payload_text": json.dumps({"queue_alarm_delta": 50}),
        "expected": {"verdict": "accept", "error_fields": []},
    },
    {
        "id": "range-launcher-max-workers-low",
        "categories": ["D5"],
        "payload_text": json.dumps({"launcher_max_workers": 0}),
        "expected": {"verdict": "reject", "error_fields": ["launcher_max_workers"]},
    },
    {
        "id": "range-launcher-max-workers-high",
        "categories": ["D5"],
        "payload_text": json.dumps({"launcher_max_workers": 65}),
        "expected": {"verdict": "reject", "error_fields": ["launcher_max_workers"]},
    },
    {
        "id": "range-dispatch-max-per-scan-low",
        "categories": ["D5"],
        "payload_text": json.dumps({"dispatch_max_per_scan": 0}),
        "expected": {"verdict": "reject", "error_fields": ["dispatch_max_per_scan"]},
    },
    {
        "id": "range-dispatch-max-per-scan-high",
        "categories": ["D5"],
        "payload_text": json.dumps({"dispatch_max_per_scan": 65}),
        "expected": {"verdict": "reject", "error_fields": ["dispatch_max_per_scan"]},
    },
    {
        "id": "range-queue-alarm-delta-low",
        "categories": ["D5"],
        "payload_text": json.dumps({"queue_alarm_delta": 9}),
        "expected": {"verdict": "reject", "error_fields": ["queue_alarm_delta"]},
    },
    {
        "id": "range-queue-alarm-delta-high",
        "categories": ["D5"],
        "payload_text": json.dumps({"queue_alarm_delta": 10001}),
        "expected": {"verdict": "reject", "error_fields": ["queue_alarm_delta"]},
    },
]


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    existing = {case["id"] for case in data["cases"]}
    added = 0
    for case in NEW_CASES:
        if case["id"] in existing:
            continue
        data["cases"].append(case)
        added += 1
    FIXTURE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    print(f"added={added} count={len(data['cases'])} sha256={digest}")


if __name__ == "__main__":
    main()
