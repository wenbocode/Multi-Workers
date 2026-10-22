import json
import pathlib
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
repo = pathlib.Path("H:/git/Multi-Workers")
outdir = repo / ".agenticdoc/mw-decision-substitution/evidence/runs/jev-cases-20261021"
outdir.mkdir(parents=True, exist_ok=True)
mw = repo / "packages/multi-workers/mw.py"

STATE = (
    "key=mw-decision-substitution（决策模型替换 jev）。阶段 EXECUTE，主体 T-01..T-10 全 done，"
    "FIX-A..Q 全落地；decide 相关九套件 397 passed；packages/ai 6 passed；tsgo rc=0。"
    "本仓决策配置：transport=timi-decisions、model=jev-latest、dp1/dp2/dp3 enabled=true mode=auto。"
    "权威档案 .agenticdoc/_autopilot/decisions.jsonl 共 25 行：seq1-24 是 refresh 授权行，"
    "seq25 是唯一一条真 jev 决策行（decision_id=dp3-worker-clarify:mw-decision-substitution、"
    "available=true、acted=false、escalated_reason=low-confidence、transport=timi-decisions、"
    "model=jev-latest、confidence_source=api、latency_ms=1055）。"
    "签收门禁（decide_signoff）要求：N>=1、hash 链闭合、每行 engine=timi-decisions/jev-latest/api。"
    "done 门禁当前 3 条 FAIL 全部指向缺失的 evidence/review/sign-final.md。"
    "构建：mw build --install --allow-dirty 已成功（version=0.83.0，bundle 14:25），"
    "但工作树仍有 9 个未提交的 tracked 改动（packages/coding-agent/src 下）。"
    "已知残留：worker 把 FIX-Q 的 signed_via 逻辑放在 mw.py 的两个 helper（原计划改 decide_signoff.py，"
    "被 write_face 头挡）；score 型问题在 24 个注册 dp 里没有任何一个使用；per-dp 配置只有 tier/enabled/mode/note。"
)

cases = {}

# Case A — noul: exactly the gate predicate the sign-off enforces.
a_noul = "仅凭 state 中给出的档案事实，现在是否已满足 continue 签收的三项硬条件（N>=1、链闭合、每行真 jev）？"
cases["A-noul"] = [
    "--state", STATE,
    "--noul", f"signoff_ready={a_noul}",
    "--noul-criteria",
    "signoff_ready=true:三项硬条件全部满足，N>=1 且 seq25 的 engine 三元组是 timi-decisions/jev-latest/api"
    ";false:仍有条件不满足（N=0、链断、或某行 engine 不是真 jev）",
]

# Case B — choice: the real fork the gate failure puts in front of the PM.
b_choice = (
    "done 门禁三条 FAIL 都指向缺失的 evidence/review/sign-final.md，下一步选哪条路？"
)
cases["B-choice"] = [
    "--state", STATE,
    "--choice",
    "gate_next=sign_now:让人类现在跑 /mw decide sign continue"
    ",narrow_scope:把 key 收窄成不需要签收的范围（删 decision-scope.md）"
    ",allow_empty:用 --allow-empty 留痕但判 revoke",
]

# Case C — score: real remaining-work band, low->high = more work left.
cases["C-score"] = [
    "--state", STATE,
    "--score",
    "remaining_work=已可收尾（只等签名）,只差证据或文档补齐,还差实现或测试",
]

results = {}
for name, extra in cases.items():
    proc = subprocess.run(
        [sys.executable, str(mw), "decide", "ask", "--project", str(repo), "--json", *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = (proc.stdout or "").strip()
    (outdir / f"{name}.json").write_text(raw + "\n", encoding="utf-8", newline="\n")
    if proc.stderr.strip():
        (outdir / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8", newline="\n")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = None
    results[name] = {"rc": proc.returncode, "payload": payload, "stderr": proc.stderr.strip()[:300]}

(repo / ".agenticdoc/mw-decision-substitution/evidence/runs/jev-cases-20261021/cases.json").write_text(
    json.dumps({"state": STATE, "results": results}, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)

for name, item in results.items():
    print("=" * 18, name, "rc=", item["rc"])
    p = item["payload"]
    if p is None:
        print("NO JSON:", item["stderr"])
        continue
    print("model:", p.get("model"), "latency_ms:", p.get("latency_ms"), "usage:", p.get("usage"))
    print(json.dumps(p.get("answers"), ensure_ascii=False))
