# Research: dp3/dp25 真实上下文（RQ2，只读）

## 唯一证据来源（时点：HEAD 54f194d + 工作树未提交改动，2026-10-22）
- `.agenticdoc/mw-decision-context/spec.md:1`、`tasks/RQ2-clarify-signoff.md:1`、`goal.md:1`
- `packages/multi-workers/decision_points.py`（注册表/required/optional/消息契约）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（dp3 唯一 producer）
- `packages/multi-workers/decide_signoff.py`（dp25 唯一 producer + verdict）
- `packages/multi-workers/decision_backends.py`（最终 HTTP body）
- 旁证：`shared/decide-registry.generated.ts:741-777`、`pm/triage-client.ts:380`、`mw.py:3432`、`shared/xkey-gate-guard.ts:300-380`
- 未做：真实模型调用、HTTP 抓包、凭证读取、代码修改、build/install

## 真实事实

### dp3-worker-clarify（P2，唯一 state producer = worker-mode.ts）
1. 注册问题 3 条：`answer_kind`(fact|intent|reuse) `decision_points.py:601-617`；`answerable`(noul) `:614-621`；`candidate`(dynamic→local_candidates) `:622-627`。
2. 最终请求体只有 `{model, state, questions}`：`decision_backends.py:844-859`，questions 由 `questions_map` 渲染 `decision_points.py:4845`，state 经 `_fit_state` 2000B 截断 `:4859`、发送 `:4929`。
3. state 里问题原文出现 3 次（同一字符串、3 个上限）：`task_summary` 600B `worker-mode.ts:5575`、`ambiguity.question` 300B `:5592`、`context.change_summary` 600B `:5601`。
4. `answer_kind` 与 `answerable` 是同一判断的两种问法（"材料里有没有答案"）；且调用方在发起前已排除 `intent`（`DP3_INTENT_RE` `:5303`，3b 直接返回 `:5714-5720`）、已排除本地 reuse≥阈值（`:5681-5691` 零 spawn 返回）。到达模型时 `intent`/`reuse` 基本不可选 → 该问信息量≈0。
5. 真正起作用的只有 `candidate`：从本地构造的 ≤5 条候选中选 1 条（`buildDp3Candidates` `:5476-5513`，上限 `:5016`），答案文本与 `path:line` 取自本地文件（`resolveDp3CandidateAnswer` `:5539-5558`）。模型不写 prose、不写引用。
6. 模型可见的候选材料只有：候选 label（仓库相对路径）`:5593` + 每个候选文件首条命中行前 200 字符 `:5606-5612`。没有文件正文、没有 diff。
7. `harnessDetail`（失败/超时详情）声明 `:5324`、传入 `:4195`、形参 `:4156`，但 `buildDp3State`/`decideDp3WorkerClarify` 全文未读 → 死输入，错误材料从未发送；而 `DP3_LOCATOR_RE` `:5307-5310` 明确放行 `报错|为什么|why` 类问题。
8. `c1` 恒为约定证据文件 `evidence/{research|runs}/<taskKey>-<YYYYMMDD>.md` `:5476-5481`；该文件尚未写出时模型若选 c1，本地解析失败并降级 `unavailable` `:5545-5547`（必然不可读候选占 1/5）。
9. 预算：客户端 canonical state ≤2000B `:5019`/`:5727`；未实测本任务样例字节数（未验证）。

### dp25-signoff-conclusion（P2，default_mode=auto，唯一 producer = decide_signoff.py）
10. state 构造 `signoff_state` `decide_signoff.py:340-380`，唯一调用点 `auto_conclusion:414`；required 5 字段 `decision_points.py:1458-1464`，optional 3 字段 `:2126-2130`。
11. 模型输入全是计数/布尔：`rows_total/rows_available/chain_ok/p0_open/rows_escalated/escalated_reasons/engine_violations`（`:361-377`）。缺 per-dp 覆盖、缺 `n_acted`（已算 `:323` 但未进 state）、缺每行 `dp` 集合、escalated 只有枚举无内容。
12. 结论判据已由本地 `verdict` 实现：链断对**所有**结论都报错 `:465-470`；`continue` 另加 N>=1 `:473-484` 与每行 jev 三元组 `:485-491`。注册表 instructions `decision_points.py:876-882` 逐条复述同一规则 → 模型只在复述 producer 已算过的判断；且模型答完后 `verdict` 还会再判一次，模型意见不改变结果。
13. 矛盾：label 说 `revoke` 用于 chain_ok=false / 非 jev 行 `decision_points.py:886`、`:880-881`；但 `verdict` 在 chain_ok=false 时对 revoke 也返回 problems `:465-470`（非 continue 分支 `:470-471` 只跳过 N/engine 检查）。故 revoke 只在链完好时合法 —— 正是其声明的理由不成立的场景。
14. `p0_open` 是 `mw decide dp apply` 的机器行（render `p0-open` `:565`，注释 `:529-531`），不属于结论判据，却作为 required 字段进入模型输入（本地元信息混入判断材料）。
15. 2000B 截断顺序：先丢 dp25 的 optional 三字段（`OPTIONAL_STATE_PATHS` `decision_points.py:2136`/`:2661`）——即唯一有区分力的 `engine_violations/escalated_reasons`；计数型 required 保留。
16. 写权限仍在 `mw decide sign`，executor 只 echo `decision_points.py:890-892`；`SIGNED_VIA_VALUES=("auto-decide",)` `decide_signoff.py:102`（mw-signoff-decide-only T-01 已落在工作树的改动）。
17. 源时点差异：`git diff -U0` 显示 `decide_signoff.py` 仅改动 5/21/27/57/99/130/523/535/669/675/684 行附近（docstring、词表、render 默认值、write_signoff 参数），`collect:286`/`signoff_state:340`/`verdict:449` 未被该 key 触碰；`decision_points.py` 工作树另有 +2625 行未提交新增（state 字段描述/校验扩展），dp3/dp25 注册块在 HEAD 亦存在，仅行号漂移。

## 最小候选（建议，未确认；不改 spec 相位）
- dp3（保留固定字段约束的前提下，只填判断材料）：
  `state = {task_summary: 问题原文 1 份, local_candidates: [{id,label}], context: {candidate_snippets: [{text(命中行), source(path:line)}], error_excerpt?: 来自 harnessDetail}}`
  问题集只留 `answerable`(noul) + `candidate`(choice/dynamic)，`answer_kind` 合并或删除；删 `ambiguity.question`/`context.change_summary` 与 `task_summary` 的三重复写。
- dp25：
  `state = {rows_total, rows_available, acted_rows, chain_ok, engine_violations, escalated_reasons, dp_coverage: [{dp, rows, available, escalated}]}`
  `p0_open` 移出模型输入（留在本地 render/apply 机器行）；把"覆盖哪些 dp 是否足以背书该 key 收尾"作为模型唯一非冗余判断，链/N/engine 三条继续由本地 `verdict` 硬门。
- 缺材料时的行为建议（待确认）：dp3 无命中片段 → 不发（本地 3b）；dp25 无 `dp_coverage` → 不允许 `continue`。

## 待确认（用户裁决，未写进 spec）
1. `answer_kind` 是否可并入 `answerable`（现状双问同判）。
2. dp3 是否应把 `harnessDetail`/错误摘录真正发送（现状死输入），以及上限。
3. dp25 是否把 revoke 语义改为"链断只能是本地事故，不由模型选"，并修 label 矛盾。
4. dp25 是否以 `dp_coverage` 取代计数摘要作为主要判断材料；`p0_open` 是否移出。
5. 字段增删需同步改动 `REQUIRED_STATE_FIELDS` 闭合集与 `triage-client.ts:380` 前置清单——属实现，本轮不做。
