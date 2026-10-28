"""Ad-hoc measurement: how many config reads does one `run --book` command do?"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, r"H:\git\Multi-Workers\packages\multi-workers")

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

CRED_ENV = ("TIMI_API_KEY", "TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "TIMI_API_TOKEN")
for name in CRED_ENV:
    import os

    os.environ.pop(name, None)

tmp = pathlib.Path(tempfile.mkdtemp(prefix="t05g-measure-"))
decision_backends._auth_json_path = lambda: tmp / "no-auth.json"

SECRET_A = "snap-cfg-a-0123456789abcdef"
SECRET_B = "snap-cfg-b-0123456789abcde"

root = tmp / "repo"
(root / ".git").mkdir(parents=True)
(root / "notes.txt").write_text("line1\nline2\n", encoding="utf-8", newline="\n")
(root / ".mw").mkdir(parents=True)
(root / ".mw" / "decide.json").write_text(
    json.dumps({"enabled": True, "api_key": SECRET_A}) + "\n", encoding="utf-8", newline="\n"
)
(root / ".mw" / "decide-points.json").write_text(
    json.dumps(
        {
            "version": 1,
            "points": {
                p.id: {"tier": p.tier, "enabled": True, "mode": "auto"} for p in dpts.DP_REGISTRY
            },
        }
    )
    + "\n",
    encoding="utf-8",
    newline="\n",
)
dpts.clear_points_config_cache()

dp = "dp3-worker-clarify"
state = {
    "schema_version": 2,
    "decision_point": dp,
    "questions_version": dpts.get_decision_point(dp).questions_version,
    "key": "k-measure",
    "phase": "EXECUTE",
    "task_type": "coding",
    "risk": "mid",
    "risk_source": "pm-label",
    "authority_tier": "P2",
    "task_summary": "measure the config read count",
    "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
    "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
}
evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp]}
book = {
    "schema_version": books.BOOK_SCHEMA_VERSION,
    "decision_point": dp,
    "state": state,
    "notes": {"evidence": evidence},
}
book_path = root / "book.json"
book_path.write_text(json.dumps(book, indent=2) + "\n", encoding="utf-8", newline="\n")

original = decision.DecisionConfig.from_project
reads: list = []


def spy(project_root=None, *args, **kwargs):
    cfg = original(project_root, *args, **kwargs)[0]
    reads.append({"call": len(reads) + 1, "authorization": decision_backends._cfg_get(cfg, "api_key"),
                  "id": id(cfg)})
    return cfg, None


decision.DecisionConfig.from_project = spy

gate_cfgs: list = []
original_redactor = decision.known_secret_redactor


def gate_spy(cfg=None, **kwargs):
    gate_cfgs.append({"id": id(cfg), "authorization": decision_backends._cfg_get(cfg, "api_key")})
    return original_redactor(cfg, **kwargs)


decision.known_secret_redactor = gate_spy

fake = decision.FakeBackend(
    [
        decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers={
                "answer_kind": {"value": "fact", "confidence": 0.9},
                "answerable": {"value": 0.9},
                "candidate": {"value": "c1", "confidence": 0.9},
            },
            latency_ms=2,
            detail="",
        )
    ]
)
decision.DEFAULT_BACKEND_FACTORY = lambda cfg: fake

args = argparse.Namespace(
    subcommand="decide",
    decide_action="run",
    project=str(root),
    json=True,
    request_file=None,
    dp=None,
    book=str(book_path),
)
rc = mw.cmd_decide(args)
sent = fake.calls[0]["cfg"] if fake.calls else None
print(
    json.dumps(
        {
            "rc": rc,
            "config_reads": len(reads),
            "reads": reads,
            "gate_sets": gate_cfgs,
            "sent_cfg_id": id(sent) if sent is not None else None,
            "sent_authorization_is_snapshot_a": (
                sent is not None and decision_backends._cfg_get(sent, "api_key") == SECRET_A
            ),
            "gate_cfg_is_sent_cfg": bool(gate_cfgs) and sent is not None and gate_cfgs[0]["id"] == id(sent),
            "secret_b_in_output": SECRET_B in "",
        },
        indent=2,
    )
)
