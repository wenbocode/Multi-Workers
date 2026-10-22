# jev 手动测试清单（2026-10-21）

所有命令在 `H:\git\Multi-Workers` 下跑。当前构建：`version=0.83.0`（`--allow-dirty`），bundle 14:25 已装。
唯一传输：`POST http://api.timiai.woa.com/ai_api_manage/llmproxy/v1/decisions`，model `jev-latest`，
`Authorization: <裸 timi key>`；没有 fallback，出错就报错。

## 0. 先重启 mw serve（当前 serve 是 10-20 的旧代码）

TUI 里敲 `/mw restart`。或终端：

```
python packages/multi-workers/mw.py stop --project . ; python packages/multi-workers/mw.py start --project .
```

（`mw decide *` 不经过 serve，但派 worker 走 serve，旧代码里的决策接线是旧的。）

## 1. 裸问答：看 jev 自己怎么答

```
python packages/multi-workers/mw.py decide ask --project . --state "线上 billing 服务 5xx 从 0.2% 升到 4.1%，已持续 12 分钟，告警已触发。" --noul urgent="这条告警需要立即人工介入吗？" --choice dept="billing:账单域,infra:基础设施" --json
```

看什么：`model` 必须是 `jev-latest`；`answers.urgent.prob` / `answers.urgent.confidence`；
`answers.dept.choice` + 各选项 `prob`；`latency_ms`（约 1 秒）；`usage`。

请求/响应的原始形状（上次真跑）：

```
request : {"model":"jev-latest","state":"...","questions":{"urgent":{"type":"noul","instructions":"..."},"dept":{"type":"choice","instructions":"...","criteria":{"billing":"...","infra":"..."}}}}
response: {"model":"jev-latest","answers":{"urgent":{"prob":0.87,...},"dept":{"choice":"billing","prob":{...}}},"usage":{...}}
```

## 2. 真决策点往返（dp3，带本地候选）

```
python packages/multi-workers/mw.py decide run --project . --dp dp3-worker-clarify --request-file .agenticdoc/mw-decision-substitution/evidence/runs/jev-live-20261021/request-b.json --json
```

看什么：三题 `candidate` / `answerable` / `answer_kind` 的 prob；聚合置信（各题取 min）；大概率
`escalated_reason=low-confidence`（聚合 < 0.7）→ 这正是"模型不作主、交人"的设计边界。

## 3. 档案行有没有落

```
python -c "import json,pathlib;[print(json.loads(l)['seq'],json.loads(l)['dp'],json.loads(l)['transport'],json.loads(l)['model'],json.loads(l).get('confidence_source'),json.loads(l).get('escalated_reason')) for l in pathlib.Path('.agenticdoc/_autopilot/decisions.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()][-4:]"
```

## 4. TUI 入口（本次 build 新增）

先 `/reload`（或重启窗口），然后：

```
/mw decide
```

应显示：`counted_rows=1`、`engines: timi-decisions/jev-latest/api=1`、三条 `verdict`、`rows_sha256` 前 12 位、`p0-open`。
再签收（唯一会写文件的一步）：

```
/mw decide sign continue --reason "jev 真决策跑通，dp3 N=1"
```

弹确认框 → 确认 → 写 `.agenticdoc/mw-decision-substitution/evidence/review/sign-final.md`（含 `signed_via: tui`）。
取消则是 `cancelled, nothing written`。verdict 不通过时**不弹框**、直接报错。

终端等价（人在窗口外跑，不需要 build）：

```
python packages/multi-workers/mw.py decide sign --project .agenticdoc/mw-decision-substitution --conclusion continue --reason "..."
```

## 5. worker 侧真采纳（端到端，最接近"jev 在做决策"）

本仓 `dp1/dispatch-type`、`dp2/checkpoint-split`、`dp3/worker-clarify` 都是 `enabled=true mode=auto`。
随便派一个任务，worker 日志/`trace.log` 里按顺序看：

1. `[triage]` 行 —— dp1 判类型（engine 三元组必须 `timi-decisions/jev-latest/api`）；
2. `decision:` 头行 —— 每个决策点的注册表版本 + 是否 enabled；
3. `[DECIDE] … dp=dp3-worker-clarify sub=3a acted=1` —— 3a 子决策真的跑了；
4. `[mw dp3-answer] …` steer —— 采纳的答案（文本来自本地文件命中行 + `(rel:line)`，**不是模型自由文本**）；
5. `.agenticdoc/<key>/workers/<task>/trace.log` 的 goal mtime 记录。

`acted=0` 且 `escalated_reason` 非空 = 模型没把握、按设计上抛给人，不算失败。

## 关掉

无需关任何东西；想关决策替换：`python packages/multi-workers/mw.py decide set --project . enabled=false`。
