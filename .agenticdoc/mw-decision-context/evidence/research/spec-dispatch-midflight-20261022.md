# dp1/dp2 决策上下文：现状与最简候选（只读调研）

> key mw-decision-context；时点 2026-10-22，静态只读 + 手算样例。未调模型、未读凭证、未改代码。
> 标记：**事实**=源码可核；**推断**=由事实推出、未运行验证；**建议**=候选，未被用户确认。其他 key 正在改测试/docs，本文只保证此刻源码，不争写。

## 1 dp1 真实决策问题与选项（事实）

- 注册 `packages/multi-workers/decision_points.py:546-573`（P2；executor 未接线 :573，`mw decide run` 固定 `intent="answer"` `packages/multi-workers/mw.py:1003`，所以 dp1 从不真执行）。
- 两问：`triage_type` = 这任务该派哪类 worker（coding|research|review）；`triage_risk` = 做错代价多大（low|mid|high）。题干/选项说明 :548-570。
- 模型侧提问 = `instructions` + `labels` 渲染成 `criteria`（`decision_backends.py:630-700, :810-846`），不含 schema 说明、不含 state 字段含义。
- `questions_version` 由问题集哈希派生（`decision_points.py:374`；实测 `q-09d3aad3`，锁定于 `test_decision_points.py:343`）。

## 2 dp1 producer 真实材料（事实）

- 唯一生产入口 `pm/ui-bridge.ts:1835` → `buildDp1DispatchState`（:528-600），输入只有 {key, phase, taskType, requestedType, description, writeFace, allowForeignWrite}。
- `task_summary` = description 首个非空行、绝对路径打码、≤600B（ui-bridge.ts:404-419）。
- `context.task_excerpt` = 卡片 `## 上下文` + `## 要求` 两节拼接，无这两节退回整卡正文；≤1200 字符再受 2000B 余量二次截断（:509-522, :442-444, :571-576）。
- `scope.write_scope` = 写面中"路径形状"条目的目录，逐级上粗化到每项 ≤32B、≤12 项（:343-362）；`scope.file_extensions` = 扩展名 ≤6 项（:365-390）。
- `risk` = allowForeignWrite?high : 无写角色?low : mid；`risk_source` 恒 `pm-label`（:427-430）——risk 是 PM 自己的标注，不是机器证据。
- `task_type` 与 `requested_type` 恒为同一个 dispatched type（:1840-1841）；`authority_tier` 恒 `P2`。`history`/`scope.images_required` 声明为可选（decision_points.py:2116）但无生产 producer（仅校验器认识，triage-client.ts:534）。
- **事实**（未覆盖的形状）：写面只有目录、无扩展名时 `file_extensions=[]`，而 TS 校验要求非空数组（triage-client.ts:502, :574-600）→ input-incomplete → 回退 legacy 字符串状态（ui-bridge.ts:600-615）。本任务卡的写面正是这种形状。**推断**（未统计）生产里这类回退不算少。

## 3 最终 HTTP：模型真正收到什么（事实）

- 请求体只有三个键 `{model, state, questions}`（`decision_backends.py:844-859`）；`state` 原样透传（:623-627），无字段白名单/二次裁剪；`questions` 由 registry 派生（:810）。
- 结构化路径在 Python 侧的门：身份键 + `trigger.data`（decision_points.py:443-459）、必填（:1258-1272, :2570）、类型/枚举/闭键集（:2306-2456，`allow_context=True` :4821）、2000B 两阶段裁剪（:145, :2629）。
- 结论：模型看到 = dp1 的 13 个必填 + 2 可选 + `context.task_excerpt`；Python 没有替模型丢任何审计字段（state 整体发送）。
- 只有关联/审计价值、对"派什么类型/多大风险"几乎无判断价值：`schema_version`、`decision_point`、`questions_version`、`authority_tier`(恒 P2)、`phase`、`key`(决策 id 后缀)。有来源价值：`risk_source`(pm-label)。
- 现状样例（**构造**自本节代码，非模型调用；本任务同形）：去掉 context 后 canonical state = 462B（手算 json），2000B 内留给 `task_excerpt` 的余量 = 1522B（中文≈500 字，1200 字符上限并不 binding）。

```json
{"schema_version":2,"decision_point":"dp1-dispatch-type","key":"mw-decision-context","phase":"EXECUTE",
 "task_type":"research","requested_type":"research","risk":"mid","risk_source":"pm-label","authority_tier":"P2",
 "task_summary":"只读核dp1/dp2真实职责/producer/最终HTTP上下文调研","questions_version":"q-09d3aad3",
 "scope":{"write_scope":[".agenticdoc/mw-decision-context/workers/dc-rq1-dispatch-midflight",
                         ".agenticdoc/mw-decision-context/evidence"],"file_extensions":["md"]},
 "context":{"task_excerpt":"<## 上下文 + ## 要求 两节，最多约 1522B>"}}
```

- legacy 回退样例（同一任务）：`requested_type: research\ncli: <cli>\nowner_phase: EXECUTE\n\ntask:<整份任务正文，≤16000B>`（triage-client.ts:776-804, :68），并自带 `DP1_QUESTIONS`（:93）。legacy 请求不经 `decide_for`，无授权行、无 state_digest（`mw.py:918-940` 说明 + :994-1000 分支）。

## 4 缺口：真实材料里哪些其实没进请求（判断，锚点已给）

| 材料 | 现状 | 影响 |
| --- | --- | --- |
| 任务原文 | 结构化只给首行 600B + 卡片两节 ≤1522B；legacy 反而给全文 ≤16KB | 两条路径材料量相反；切在验收/禁止面/唯一证据文件处时模型看不到硬约束（**推断**） |
| 文件写面 | 只目录 + 扩展名；不含"不得写"、read_scope、claims，目录还向上粗化 | 模型无法判断越界，只能复述 pm-label 的 mid |
| 进展原文（dp2） | 只有计数 + artifact_status(path/exists/bytes)，无 progress.md/report.md 正文、无 [CHECKPOINT] 行原文 | "narrow 还是 split"缺内容证据 |
| 同类历史 | dp1 `history` 未生产 | 没有"上次同类任务怎么派"的先例 |

## 5 dp1 候选最简 context（**建议**，未确认；本 key 不实施）

- 保留：任务原文（首段或整卡头部 ≤2KB，必须含验收标准/写入禁止面/唯一证据文件）、`scope.write_scope` + 新增 `scope.denied_paths`、`risk_source`、`context.task_excerpt`。
- 删/合并（待确认）：`schema_version`、`decision_point`（与 `--dp` 冗余）、`authority_tier`（dp 常量）、`requested_type`（与 task_type 恒等）、`phase`；`key` 只留本地关联。
- 结构性建议（待确认）：`task_type` 目前把 PM 已选类型直接告诉模型，而问题恰恰问"该派哪类"，**推断**会把模型推向复述；候选是改喂"是否要写代码/跑命令"的原文证据，或不喂 type。
- 预估最小请求：state ≈ 5 字段 + excerpt ≤2KB + 两个 choice 问题（题干/labels 不变）。

## 6 dp2 现状（事实）+ 候选（建议）

- 单问 `checkpoint_action` = narrow/split/direct-exec/escalate（decision_points.py:576-597）；生产 `pm/pm-orchestrator.ts:2336 decideDp2Checkpoint`。
- 材料：task.md 头 phase/type/timeout（:2262-2280）、worker.log [CHECKPOINT] 解析出的计数与 risk（`shared/heartbeat.ts` CheckpointInfo）、`progress.trend` ≤32 点、`artifact_status` ≤24 行（:2176-2181）。
- `context.change_summary` 完全由上面的计数拼成（:2168-2174），与 `progress.*` 重复，无新增信息（事实）。
- 缺：progress.md/report.md 原文、`CheckpointInfo.progressDone`（有字段但 dp2 state 无对应键）、[CHECKPOINT] 行原文。
- 候选最简（**建议**）：`elapsed_minutes/budget_minutes/phases_done/phases_total`、`artifact_present`、`risk`(machine)、`context.change_summary` 换成真实"上次落盘后改了什么"或 report/progress 尾段 ≤800B；`writes/uniq_targets/repeat_top/trend`、artifact_status 的 bytes 可视 thrash 判据决定去留。

## 7 待用户确认

1. dp1 是否保留"策略性字段"（task_type/requested_type/risk/risk_source），还是只给证据 + 两问？
2. 任务原文给"两节摘要"还是"整卡头部 ≤2KB"，且必须含验收标准/写入禁止面/唯一证据文件？
3. 审计键（schema_version/decision_point/authority_tier/phase/key）留在 `state` 全发，还是仅本地留档？
4. 目录型写面导致的 legacy 回退（全文 16KB、绕过 decide_for/授权行）是否为已知可接受行为，还是应当修 `file_extensions` 的空数组语义？
