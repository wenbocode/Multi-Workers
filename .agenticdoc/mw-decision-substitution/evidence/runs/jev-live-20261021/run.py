"""Live jev case capture (PM-run, network required).

Regenerates the evidence in this directory: the exact bytes sent to jev, the exact
bytes jev returned, the decoded answers, and the gate verdict. Two cases:

  A. `mw decide ask` semantics  -> legacy client path, human questions
     (noul / choice / score), no registry dp, no authorization.
  B. `mw decide run --dp dp3-worker-clarify` semantics -> structured path with a
     registry dp, dynamic candidates rendered from state, authorization + archive.

Run from the repo root:

    python .agenticdoc/mw-decision-substitution/evidence/runs/jev-live-20261021/run.py
"""

import hashlib
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "packages" / "multi-workers"))
sys.stdout.reconfigure(encoding="utf-8")

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_points as dpts  # noqa: E402

PROJECT = HERE / "project"
URL = "http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions"
MODEL = "jev-latest"


def payload_for(state, questions, labels=None):
    rendered = {}
    for qid, spec in questions.items():
        qtype = spec.get("type")
        item = {"type": qtype, "instructions": db._question_instructions(qid, spec)}
        if qtype == "choice":
            item["criteria"] = db._choice_criteria(spec, (labels or {}).get(qid))
        elif qtype == "score":
            item["criteria"] = db._score_criteria(spec)
        elif qtype == "noul" and isinstance(spec.get("criteria"), dict):
            item["criteria"] = dict(spec["criteria"])
        rendered[qid] = item
    return {"model": MODEL, "state": db._state_payload(state), "questions": rendered}


def post(payload, name):
    key = db.resolve_timi_api_key()
    started = time.time()
    resp = db._http_post(URL, {"Authorization": key, "Content-Type": "application/json"}, payload, 60.0)
    latency = int(round((time.time() - started) * 1000))
    (HERE / f"request-{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (HERE / f"response-{name}.json").write_text(
        json.dumps({"status": resp.status, "latency_ms": latency, "body": json.loads(resp.body)}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return resp, latency


def case_a():
    state = {
        "message": "求助！我的提现已经失败3天了。",
        "context": "用户从帮助中心提交工单，未提供订单号。",
    }
    questions = {
        "urgent": {"type": "noul", "instructions": "这段话是否传达了紧急性？",
                   "criteria": {"true": "用户明确表示业务受阻或要求立即处理",
                                "false": "只是普通咨询或抱怨"}},
        "dept": {"type": "choice", "instructions": "这条工单应该由哪个团队接手？",
                 "criteria": {"billing": "支付、开票、退款相关", "technical": "缺陷、故障、集成相关",
                              "sales": "定价、升级、新账号相关"}},
        "frustration": {"type": "score", "instructions": "用户此刻的情绪强度是第几档？",
                        "criteria": ["平静", "不满", "非常愤怒"]},
    }
    payload = payload_for(state, questions)
    resp, latency = post(payload, "a")
    body = json.loads(resp.body)
    print(f"[A] status={resp.status} latency={latency}ms id={body.get('id')}")
    print(f"[A] model={body.get('model')} usage={body.get('usage')}")
    for qid, ans in body.get("answers", {}).items():
        print(f"[A] answers.{qid} = {json.dumps(ans, ensure_ascii=False)}")
    return payload, body


def case_b():
    research = PROJECT / "evidence" / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "spec-timi-decisions-api-20261021.md").write_text(
        "调查结论：jev 的决策入口是 POST /v1/decisions，凭据用裸 timi key，body 只有 model/state/questions。\n",
        encoding="utf-8",
        newline="\n",
    )
    (research / "spec-worker-heartbeat-20261021.md").write_text(
        "调查结论：worker 心跳每 30 秒写一次 attempt 计数。\n", encoding="utf-8", newline="\n"
    )
    (research / "spec-budget-guard-20261021.md").write_text(
        "调查结论：预算守卫在 80% 时降级模型。\n", encoding="utf-8", newline="\n"
    )
    (PROJECT / ".mw").mkdir(parents=True, exist_ok=True)
    (PROJECT / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True, "transport": "timi-decisions", "model": MODEL}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    state = {
        "v": 1,
        "dp": "dp3-worker-clarify",
        "key": "jev-live-case",
        "phase": "EXECUTE",
        "task_type": "research",
        "risk": "low",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "jev 决策入口的契约调研证据应该写到哪个文件？",
        "questions_version": "q-fcbd3847",
        "ambiguity": {
            "kind": "scope",
            "question": "jev 决策入口 /v1/decisions 的传输契约调研证据应该写到 evidence/research/ 下的哪个文件？",
        },
        "local_candidates": [
            {"id": "c1", "label": "evidence/research/spec-worker-heartbeat-20261021.md"},
            {"id": "c2", "label": "evidence/research/spec-timi-decisions-api-20261021.md"},
            {"id": "c3", "label": "evidence/research/spec-budget-guard-20261021.md"},
        ],
    }
    questions = dpts.questions_map("dp3-worker-clarify")
    labels = db._dynamic_labels(questions, state)
    payload = payload_for(state, questions, labels)
    resp, latency = post(payload, "b")
    body = json.loads(resp.body)
    print(f"[B] status={resp.status} latency={latency}ms id={body.get('id')}")
    print(f"[B] model={body.get('model')} usage={body.get('usage')}")
    for qid, ans in body.get("answers", {}).items():
        print(f"[B] answers.{qid} = {json.dumps(ans, ensure_ascii=False)}")

    cfg, err = decision.DecisionConfig.from_project(PROJECT)
    client = decision.DecisionClient(cfg, project_root=PROJECT)
    outcome = dpts.decide_for("dp3-worker-clarify", dpts.Trigger.from_mapping(state), PROJECT,
                              client=client, intent="answer", archive=False)
    print(f"[B] decide_for status={outcome.status} escalated={outcome.escalated_reason}")
    print(f"[B] decide_for detail={outcome.detail}")
    print(f"[B] decide_for answer={json.dumps(outcome.answer, ensure_ascii=False)}")
    (HERE / "outcome-b.json").write_text(
        json.dumps({"status": outcome.status, "escalated_reason": outcome.escalated_reason,
                    "answer": outcome.answer, "response": outcome.response},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    return payload, body


def main():
    a_req, a_resp = case_a()
    b_req, b_resp = case_b()
    digest = hashlib.sha256(
        json.dumps([a_req, a_resp, b_req, b_resp], ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    print(f"[meta] case digest={digest}")


if __name__ == "__main__":
    main()
