"""Read-only R3 probe: the two residuals through the real TS-text parser.

Every fixture here is synthetic parser input: it is NOT T04 output and proves no
generation, field parity, wiring or TS compilation. No product tree is written.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
PACKAGE = KEY / "implementation-worktree" / "packages" / "multi-workers"
FIXTURES = EVIDENCE / "fixture" / "r3"
FIXTURES.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PACKAGE))
contract = importlib.import_module("test_decide_registry_contract")
dpts = importlib.import_module("decision_points")
assert pathlib.Path(contract.__file__).resolve().parent == PACKAGE
assert pathlib.Path(dpts.__file__).resolve().parent == PACKAGE


def outcome(call) -> dict:
    try:
        value = call()
    except AssertionError as error:
        return {"outcome": "rejected", "detail": str(error)}
    return {"outcome": "accepted", "value": value}


def peers(name: str, *, peer: str, generated: str) -> None:
    (FIXTURES / f"{name}.triage.synthetic.ts").write_text(peer, encoding="utf-8")
    (FIXTURES / f"{name}.generated.synthetic.ts").write_text(generated, encoding="utf-8")


def activate(name: str) -> None:
    contract.TRIAGE_CLIENT = FIXTURES / f"{name}.triage.synthetic.ts"
    contract.GENERATED_TS = FIXTURES / f"{name}.generated.synthetic.ts"


rows = contract._ts_rows
peer = contract._synthetic_ts_peer
generated = contract._synthetic_generated_ts

probe: dict = {
    "synthetic_only": True,
    "product_generation": False,
    "imports": {
        "test_decide_registry_contract": str(pathlib.Path(contract.__file__).resolve()),
        "decision_points": str(pathlib.Path(dpts.__file__).resolve()),
    },
}

real_stage = contract._generated_ts_stage()
real_universal, real_by_dp = contract._ts_required_fields()
probe["real_peer"] = {
    "stage": real_stage,
    "universal": real_universal,
    "retired_rows": {
        key: value for key, value in real_by_dp.items() if dpts.is_retired_dp(key)
    },
    "active_rows": sorted(set(real_by_dp) & set(dpts.ACTIVE_DP_IDS)),
}

original_client = contract.TRIAGE_CLIENT
original_generated = contract.GENERATED_TS
try:
    active_only = {
        dp_id: list(dpts.REQUIRED_STATE_FIELDS[dp_id]) for dp_id in dpts.ACTIVE_DP_IDS
    }
    peers(
        "post-t04-active-only",
        peer=peer(rows(active_only), constants=""),
        generated=generated(dpts.ACTIVE_DP_IDS),
    )
    activate("post-t04-active-only")
    probe["post_t04_active_only_real_parser"] = outcome(contract._ts_required_fields)
    probe["post_t04_active_only_stage_test"] = outcome(
        contract.test_ts_required_rows_follow_the_registry_stage
    )

    peers(
        "post-t04-partial-legacy",
        peer=peer(rows({"dp4-failure-handling": ["failure.kind"]})),
        generated=generated(dpts.ACTIVE_DP_IDS),
    )
    activate("post-t04-partial-legacy")
    probe["post_t04_partial_legacy_stage_test"] = outcome(
        contract.test_ts_required_rows_follow_the_registry_stage
    )

    peers(
        "post-t04-full-legacy",
        peer=peer(rows(contract.LEGACY_TS_ROWS)),
        generated=generated(dpts.ACTIVE_DP_IDS),
    )
    activate("post-t04-full-legacy")
    probe["post_t04_full_legacy_stage_test"] = outcome(
        contract.test_ts_required_rows_follow_the_registry_stage
    )

    pre_t04_rows = dict(contract.LEGACY_TS_ROWS)
    pre_t04_rows["dp-w-type"] = list(dpts.REQUIRED_STATE_FIELDS["dp-w-type"])
    peers(
        "pre-t04-with-active-row",
        peer=peer(rows(pre_t04_rows)),
        generated=generated(tuple(dpts.RETIRED_DP_IDS)),
    )
    activate("pre-t04-with-active-row")
    probe["pre_t04_active_row_stage_test"] = outcome(
        contract.test_ts_required_rows_follow_the_registry_stage
    )

    new_name_rows = rows(
        {
            dp_id: list(dpts.REQUIRED_STATE_FIELDS[dp_id])
            for dp_id in dpts.ACTIVE_DP_IDS
            if dp_id != "dp-sign-key"
        }
    ) + "\t[SIGN_KEY_ID]: [" + ", ".join(
        json.dumps(field) for field in dpts.REQUIRED_STATE_FIELDS["dp-sign-key"]
    ) + "],\n"
    peers(
        "post-t04-new-name-constant",
        peer=peer(new_name_rows, constants='const SIGN_KEY_ID = "dp-sign-key";\n'),
        generated=generated(dpts.ACTIVE_DP_IDS),
    )
    activate("post-t04-new-name-constant")
    probe["no_dp1_id_new_name_constant_parser"] = outcome(contract._ts_required_fields)

    peers(
        "malformed-unknown-id",
        peer=peer(rows({"dp99-unknown": ["task_goal"]})),
        generated=generated(tuple(dpts.RETIRED_DP_IDS)),
    )
    activate("malformed-unknown-id")
    probe["parser_unknown_id_structurally_parsed"] = outcome(contract._ts_required_fields)
    probe["unknown_id_stage_test"] = outcome(
        contract.test_ts_required_rows_follow_the_registry_stage
    )

    malformed = {
        "empty-matrix": peer(""),
        "duplicate-key": peer(rows({"dp-w-type": ["a"]}) + rows({"dp-w-type": ["b"]})),
        "unquoted-key": peer('\tdp-w-type: ["task_goal"],\n'),
        "non-string-field": peer('\t"dp-w-type": ["task_goal", 42],\n'),
    }
    for label, text in malformed.items():
        peers(f"malformed-{label}", peer=text, generated=generated(dpts.ACTIVE_DP_IDS))
        activate(f"malformed-{label}")
        probe[f"malformed_{label.replace('-', '_')}"] = outcome(contract._ts_required_fields)
finally:
    contract.TRIAGE_CLIENT = original_client
    contract.GENERATED_TS = original_generated

assert contract._generated_ts_stage() == real_stage
(EVIDENCE / "probe-r3.json").write_text(
    json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(probe, ensure_ascii=False, indent=2))
