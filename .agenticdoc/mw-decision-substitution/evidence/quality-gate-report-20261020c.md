## 结论

PASS-WITH-FINDINGS（只读、代码级复审）：MAJOR-1 关闭；MAJOR-2 部分关闭（字段集合/错误透传已对齐，但 dp1/dp2/dp3 工具答案仍不可达）；MINOR-5 关闭。

## 证据

以下路径均相对仓库根目录 `H:/git/Multi-Workers`；行号为本次读取的源码位置。测试引用是对用例源码的检查，不是本轮执行结果。

### 1. MAJOR-1：关闭（三项独立判定）

**1a 授权表读取：关闭。**

- 对 `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts` 全文件 grep `decide-points|readFile|load_points|readDecisionAuthorization|ASK_DECISION_DP_TIERS`，唯一命中为 `:34` 的注释：说明 Python 权威读取 `.mw/decide-points.json`。没有工具侧文件读取或授权推导代码。
- 对 `packages/**/*.ts` grep `readDecisionAuthorization|ASK_DECISION_DP_TIERS`：`No matches found`，旧函数、tier 表及其调用点均无残留。工具仍保留注册 id 枚举，未将其用于推导授权。
- 反面用例：`packages/coding-agent/test/suite/decision-tool.test.ts:234-296` 将同一子进程答案分别用于无表、表中 off/suggest、坏 JSON 三种目录，均断言相同 `auto/acted=false/child id`；`:492-518` 断言本地 dp12 off 不阻止 runner 调用，由 Python 的 disabled 答案决定结果。这些用例与源码无读表分支一致；本轮未执行。

**1b decision_id / mode / acted 仅来自子进程：关闭。**

- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:643-654` 直接取 `response.decision_id`、`response.mode`、`response.acted`，只做结构校验后放入成功 payload；未拼接 trigger、未补默认 mode、未补默认 acted。
- 缺/错任一键的代码级反例：给出 `available=true` 且 answers 合法，但删 `decision_id`、删 `mode` 或删 `acted`，`:646-647` 各自导致 `unavailable=bad-response`；不会本地补键。此处 fail 是结构化拒答，不是必须抛异常。
- `packages/coding-agent/test/suite/decision-tool.test.ts:323-336` 已覆盖 child id/mode 为 null 时拒答；尚未分别动态验证每个缺键，尤其没有独立的缺 acted 回归用例。
- Python 来源核对：`packages/multi-workers/mw.py:872-900` 的 `_decide_run_payload` 产生这三键及 `escalated_reason`；工具不是授权事实的第二生产者。

**1c 由 mode 推 acted：关闭。**

- 全文件 grep literal `acted` 共 15 处：`:12,31,37,41,42,186,576,641,642,645,646,654,801,816,842`。除注释、接口和提示文本外，只有 `const acted = response.acted`、布尔校验、payload 透传及 trace 展示；不存在赋值为 `mode === "auto"` 或其他 mode→acted 表达式。
- 反面证据：`:643-654` 对 `mode=auto, acted=false` 不改写；`packages/coding-agent/test/suite/decision-tool.test.ts:249-272` 的完整 expected payload 正是这一组合，`:649-665` 的 trace 断言也保留 `auto/false`。这能反驳“auto 自动代表已执行”，符合 D-036 / D-041。

### 2. MAJOR-2：部分关闭（两项契约修复通过，原始可达性缺口仍在）

**2a 必填字段集合：已对齐。不是仅相信注释或文本锁。**

直接抄录 `packages/multi-workers/decision_points.py:624-672` 的实际 `REQUIRED_STATE_FIELDS`：

- dp1-dispatch-type（13 项）：`v, dp, key, phase, task_type, requested_type, risk, risk_source, authority_tier, task_summary, questions_version, scope.write_scope, scope.ext`。
- dp2-checkpoint-split（14 项）：`v, dp, key, phase, task_type, risk, risk_source, authority_tier, questions_version, progress.elapsed_min, progress.budget_min, progress.phases_done, progress.phases_total, progress.artifact_present`。
- dp3-worker-clarify（12 项）：`v, dp, key, phase, task_type, risk, risk_source, authority_tier, task_summary, questions_version, ambiguity.kind, ambiguity.question`。

逐项与实际 TS 构造比较：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts:344-354` 的通用集合 U = `{v, dp, key, phase, task_type, risk, risk_source, authority_tier, questions_version}`（9 项）；它的每一项均存在于 Python 三组集合。
- 同文件 `:363-364`：dp1 附加 `{requested_type, task_summary, scope.write_scope, scope.ext}`（4 项）。U∪附加 = 上述 Python dp1 全部 13 项，无遗漏、无多项。
- 同文件 `:365-371`：dp2 附加 `{progress.elapsed_min, progress.budget_min, progress.phases_done, progress.phases_total, progress.artifact_present}`（5 项）。U∪附加 = Python dp2 全部 14 项，无遗漏、无多项。
- 同文件 `:372`：dp3 附加 `{task_summary, ambiguity.kind, ambiguity.question}`（3 项）。U∪附加 = Python dp3 全部 12 项，无遗漏、无多项。
- 同文件 `:538-548` 真正遍历该 union；`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:279-299` 调用此 validator 并滤掉 `questions_version`，不是缺少这一要求：`packages/multi-workers/decision_points.py:278-289` 的 builder 在 step 5 前从注册表补它。`:296-299` 只对 dp1/2/3 做前置必填检查，其余 21 点不被 triage-client 的额外 dp 表误门控；Python mapping 也仅含这三个键。
- 反面样本：给工具 owner key 和非空 note，实际 `buildDecisionState`（`decision-tool.ts:264-274`）只有 `{v,dp,key,task_key,task_summary}`；Python builder 仅再补 `questions_version`。因此 Python / TS 的缺字段集均为：
  - dp1：`phase, task_type, risk, risk_source, authority_tier, requested_type, scope.write_scope, scope.ext`（8 项）；
  - dp2：`phase, task_type, risk, risk_source, authority_tier, progress.elapsed_min, progress.budget_min, progress.phases_done, progress.phases_total, progress.artifact_present`（10 项）；
  - dp3：`phase, task_type, risk, risk_source, authority_tier, ambiguity.kind, ambiguity.question`（7 项）。
  `packages/coding-agent/test/suite/decision-tool.test.ts:364-429` 逐项断言这三组 `missing_fields` 且 runner calls=0，即使 stub 准备了 available=true 也不可绕过前置拒发。不提供 note 时，dp1/dp3 还缺 task_summary；不提供 owner key 时三者还缺 key。
- 限定：这是“必填路径集合”一致，不是两个 validator 的全部行为一致。Python `:698-707` 检查 missing/None/blank；TS `triage-client.ts:440-554` 另有类型、枚举、长度、可选字段及跨字段校验。例如一个其余字段齐全但 phase 为 17 个 ASCII 字符的 state，Python `_missing_required` 不报 phase，TS 会报 phase。当前工具根本不能提交这样的完整 state，不构成本轮额外关闭条件；不能把注释中的“exactly missing list”推广为任意 state 的完全等价性。

**2b available=false 的 escalated_reason / legacy reason：关闭。**

- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:620-629` 从 `response.reason` 取 legacy 值，仅按冻结八值集规范化；独立取非空字符串 `response.escalated_reason`，不转换、不枚举映射。`:558-566` 将前者放 `unavailable`，后者放独立 `escalated_reason`，两键并存；注册 execute `:850-852` 也独立展示 trace。
- 反面样本：child `{available:false, reason:"bad-response", escalated_reason:"input-incomplete"}` 应得到 `{available:false, unavailable:"bad-response", action:"blocked-ask-human", escalated_reason:"input-incomplete"}`，不是把 legacy 键覆盖成 input-incomplete。`packages/coding-agent/test/suite/decision-tool.test.ts:451-488` 覆盖此差异及全部七值透传，`:668-682` 覆盖 trace。
- 权威语义：`packages/multi-workers/mw.py:850-869` 将 input-incomplete 映射为 legacy bad-response、input-oversize 映射为 budget-exhausted；`:893-899` 同时保留原始 escalated_reason。工具按此契约消费。缺/空/non-string escalated_reason 不伪造；不在 legacy 集合的 reason 仍规范化 upstream-error。

**为什么只部分关闭：** 第一轮原始 MAJOR-2（`evidence/quality-gate-report-20261020.md:49-53`）不仅是误导原因，还明确指出 dp1/2/3 工具答案生产不可达。FIX-A 要求 4 允许拿不到字段时返回结构化缺字段，当前实现满足这一安全替代；但替代并未恢复答案能力。`decision-tool.ts:247-274,533-545,742-773,811-814` 的 state 来源/接口/schema 均无 phase/risk/progress/ambiguity 的输入通道，note 只是字符串，不被解析成结构化字段；`:590-592` 对三点恒零 spawn 返回 input-incomplete。删除旧误导性成功 stub 并改测缺字段是真正修复测试契约，不是完整消除原始可达性缺陷。不能用“测试已钉住拒发”证明“工具已能回答这三点”。

### 3. MINOR-5：关闭（原因对齐，不是加宽词表）

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4433` 定义 2000B 预算；`:4888-4892` 在 3a state 超限时直接 `escalate("input-oversize", "3a", ...)`，在 `:4894-4902` runner 调用之前返回。不是 input-incomplete，也不是截断后强发。
- trace 连线核对：同文件 `:3784-3789` 将 escalation 的 `decision.reason` 传入 `formatDp3TraceLine`；`:4993-5016` 仅把本地 intent 映成 `-`，input-oversize 不受映射，实际格式为 `escalated_reason=input-oversize`，并保留 `acted=false`、人工 NC 计数。
- 反面用例：`packages/coding-agent/test/suite/dp3-answer.test.ts:626-643` 用 `EXECUTE + 2100 个 x` 的 phase 推高 canonical state，驱动真实 worker settle 链，断言 runner calls=0、只有一条 trace、`sub=3a acted=false`、`escalated_reason=input-oversize`、`nc_raw=1 nc_human=1`。若原因改回 input-incomplete 或调用 runner，相关断言即失配；本轮未执行。
- Python 实际七值（`packages/multi-workers/decision_points.py:101-111`）为 `{disabled, unavailable, input-incomplete, input-oversize, low-confidence, over-authority, p0}`。input-oversize 原本就在其中。
- `worker-mode.ts:4441-4452` 的本地 union 加此值后仍是上述七值的子集；`packages/multi-workers/decide_archive.py:52-65` 核心集合完全同样七值，`:66` 的 input-invalid 仅旧行读侧兼容；`mw.py:855` 将其映射到八值 legacy 集合的 budget-exhausted。没有新增第八个 escalation 值，也没有改宽 legacy reason。
- FIX-D 要求 3 中“input-oversize 不是 Python ESCALATED_REASONS 成员”是错误前提，应由 PM 修正该卡的说明；当前 worker 实现是对齐 D-028/D-030，不应删 Python 成员或凭此拆类型。这里只指出文档事实，不越界修改。

### 4. 契约问题：是否与 AC-012“工具对 worker 可用”冲突？

**判定：不构成现行 spec 的 AC-012 违反，也不违反狭义的工具可见/可调用契约；但不能据此宣称 dp1/dp2/dp3 工具答案能力已交付。**

- 编号先校正：`spec.md:235` 的 AC-012 是 dp refresh（补行/保值/orphaned/幂等），不是工具可用性。本卡引用发生编号/内容漂移，不应把三点恒拒答记到 AC-012。
- 可调用证据：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:82-90` 在 worker 激活后注册工具；`pm/decision-tool.ts:880-884` 每轮追加 active tools；`decision-tool.test.ts:685-695` 检查追加且不重复。工具可见、可执行，并非因角色 allowlist 被隐藏。
- 拒发证据与理由：`spec.md:161-163` 明确要求必需字段缺失时 TS 拒发并上抛；FIX-A 要求 4 明确允许缺字段报告。因此“缺输入 → input-incomplete”本身是失效安全正确行为（AC-005），可用不等于无条件 available=true。
- 但是三点不是偶发缺输入，而是 schema 没有提供它们必填 state 的任何方法（上节代码级反例）。若“对 worker 可用”指“可用该工具对 dp1/2/3 获得有效决策答案”，当前实现不满足；这是原 MAJOR-2 的功能残留，故部分关闭。另有 dp1/2/3 框架专用调用点不等于这个 LLM 工具通道已可答，也不在本卡重评这些专用链路。

## 残留与未验证

1. MAJOR-2 功能残留：dp1/dp2/dp3 工具答案仍恒不可达。最小后续方向是给工具提供可信的 dp 专属 state 来源（从调用上下文取得或受校验的结构化入参），继续复用现有必填契约；不得以默认 risk/phase 或从 mode 推 acted 伪装闭环。这需要另卡改工具输入面，而不是放宽 Python 必填集合。
2. 同 owner key / 同 dp 的不同 trigger 仍可能复用 decision_id：工具 `decision-tool.ts:535,586,828-831` 不将 trigger 放入 state；Python `decision_points.py:152-160` fallback 到 task_key/key。当前已不伪造 id，属于已知身份粒度残留，不据此重开 MAJOR-1，也未复跑 duplicate-replay。
3. 本轮没有执行 vitest、Python、tsgo、npm check 或构建；当前实际可用工具仅 read/find/grep/ls/worker_file，无 bash/命令执行通道。没有新的 Tests N passed 或运行时 rc 证据；所有用例引用均限源码核验。任务允许只读取证，未把旧 worker 成功报告当成本轮运行结果。
4. 缺权威键分别 fail 的结论有代码级分支证据；缺 acted 单独回归、任意 state 的 TS/Python validator 运行时 parity 尚未验证。字段集合的人工逐项核对不等于执行 Python 集合 dump；现有 `decision-tool.test.ts:710-721` 只锁 dp id 键集合，不能独立证明字段 parity。
5. 任务卡中 AC-012 名称及 FIX-D 的词表前提需 PM 校正。只写本报告；未修改卡片、源码、测试、spec、design 或状态文件。

## 上下文来源

- 本角色任务：`workers/ds-qg-review-2c/task.md`；派发卡：`tasks/QG-review-2C.md`（均隶属 `.agenticdoc/mw-decision-substitution/`）。报告骨架在取证前已写入本路径。
- 原发现：`evidence/quality-gate-report-20261020.md:43-53,77`；修复范围：`tasks/FIX-A-ask-decision-authority.md`、`tasks/FIX-D-dp1-disagree-oversize.md`。
- 目标/状态：`.agenticdoc/goal.md`（扩展接线、进程隔离、文件驱动协调）；`.agenticdoc/_index.parallel` 的 active key mw-decision-substitution / EXECUTE；本 key `pm-state.md`，仅用于恢复状态，不代替源码证据。
- 契约：本 key `spec.md:148-163,223-238`；`design.md:179-189`（D-028 / D-030 / D-035 / D-036 / D-041）。现行 spec AC-012 名称以正文为准。
- 直接实现及反面用例：上文逐项引用的 decision-tool.ts、triage-client.ts 局部 validator、worker-mode.ts 局部 3a/trace 段、index.ts 注册段、decision_points.py、mw.py payload/映射段、decide_archive.py 七值段；仅 decision-tool.test.ts / dp3-answer.test.ts 的相关 describe 段。
- 工作流参考：agentic-task SKILL.md 与 workflow-quality-gate.md、verification-before-completion SKILL.md。未执行无工具支持的框架检测/相位审计命令，未变更相位。
- 上下文纪律：读取调用均显式 offset/limit 且单次不超过 200 行；worker-mode.ts 仅 grep 定位后的局部读取；未整读 ui-bridge.ts、pm-orchestrator.ts 或长测试文件。session usage / PI_* 环境无法用当前工具独立查询，不宣称实测 token 数。

## 未覆盖面声明

- 不评估 MAJOR-3 / MAJOR-4 / MINOR-1（并行 ds-qg-review-2d 负责）；不重做首轮全量审计。
- 不复核 AC-001..015 全矩阵；AC-012 仅校正编号并回答工具契约问题。
- 不评估真实启用端到端（任务已声明本仓无 decide-points.json 真实 run）；不以 stub 当真实外部服务证据。
- 不评估 mw build --install 后 L5 派发、bundle 更新或安装产物。
- 不评估本仓既有 Windows 环境类失败基线；未运行全量 pytest / test.sh / npm run check，未执行 git 写操作。
