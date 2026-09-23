# Spec: mw-autopilot-stall-feedback（autopilot 停滞自愈 + 底部监控反馈）

> Key: mw-autopilot-stall-feedback
> 创建时间: 2026-09-22
> 状态: locked
> 来源: E2Feature autopilot 停滞现场诊断（2026-09-22 21:28，本窗口）

> 修订记录（2026-09-22 23:50，spec 门禁通过前）：① 停滞升级从「新增 `advance-stuck` 门禁 kind」改为**复用既有 `stalled` 门禁**（避免 kind 双侧登记兼容风险），AC-004 随之改为「approve → 复位 + 一轮额度恢复」。② 新增 AC-012（L3 worker 崩溃 ≠ verdict=below）。③ 新增 AC-013（stalled approve 的额度恢复必须可派生、无私有状态）。AC-001/002/003/005..011 编号与语义不变。
>
> 修订记录 2（2026-09-23 00:30，L3 复核反馈，独立 worker `mw-stall-feedback-l3-review-a2`）：① AC-004/AC-013 的「恰好一轮」改为精确语义——一次 approve 对**四个受管回路各放宽一轮**，其消费由各回路单调递增的 `used` 计数保证（不可重复受益；新增 `test_one_credit_is_spent_by_one_round_per_loop` 固化）。② 新增 AC-014（面板派生必须与 conductor 的连击规则同口径，仅同 edge 成功清除）。AC 编号与其余语义不变。

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（已确立，非 draft）

- 对齐：goal 核心交付「mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行」+「一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」。autopilot conductor 是无人值守推进的唯一执行路径；本 key 修的是该路径**停滞时既不收敛也不上报**的缺陷：conductor 对非瞬时 advance 失败每 4s 无界重试，且反馈只落在 `timeline.jsonl` 的一行自由文本里，PM 只能靠人工翻日志才发现。
- 现场证据（E2Feature，2026-09-22）：`feature-params-service` 的 `pm-state.md` Phase 行被 worker 写成 `EXECUTE（T-014 结案完成，待 PM 侧 \`advance_phase … done\`）`，`advance_phase.py` 解析整串 → `unknown phase` → exit 1；conductor 从 10:53:06Z 起每 4s 重试一次，**2242 次 / 2h35m**（诊断时刻）仍无任何门禁或状态提示，K2 的 deps 挡住 K3..K6，整条 Stage 1 静默停摆。同日同型故障另有 spec→design（14 次）与 design→plan（**3891 次 / 4h25m**，advance-root bug，已由 `d106bcfb2` 修）两次，累计约 7h 空转。
- 继承约束（GC 编号）：
  - GC-1 不引入中心化调度器：新增状态一律从文件家族派生（`timeline.jsonl` / `_index.parallel` / `_workers.parallel` / `_autopilot/config.json` / `gates/`），不新增常驻服务、不新增跨进程私有状态。
  - GC-2 不修改 pi 核心：改动限于 `packages/multi-workers/autopilot/**`（Python）与 agent-team-loop 扩展既有文件（TypeScript）。
  - GC-3 phase 变更仍只经 `advance_phase.py`；本 key 唯一一次 pm-state 状态修复（T1）只把非法值规范化为其**原有语义值** `EXECUTE`，不改变相位、不跳过门禁。
  - GC-4 与并发窗口隔离：`mw-rag-integration-fix`（另一 session，EXECUTE）持有未提交改动（`pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`worker/worker-mode.ts`、`rag/*`、`mw.py`、`mw_common.py`、`autopilot/dispatch.py`、`launcher.py`、`dist/`、CHANGELOG）；本 key 不修改这些文件，`dist/` 重建与扩展加载验证排到该 key 提交之后。
- 预期收益：停滞从「无限静默重试」变为「有限重试 + 机器判据分类 + 门禁升级 + 底部可见」。判定方式：以本 key 复现样例（Phase 行含括注的 pm-state）为输入，conductor 在阈值（默认 5）次同签名失败后停止重试、建 `advance-stuck` 门禁并在底部 widget 显示 STUCK 行；修复 pm-state 后 approve 该门禁即刻恢复推进（或直接成功后自动清零）。

## §1 功能概述

### 1.1 目标

三件事，一条闭环：

1. **现场止损**：修好 E2Feature `feature-params-service` 的 Phase 行，让现场 autopilot 恢复推进，并留下恢复证据（tick → advance exit=0 → L3 dispatch 出现）。
2. **停滞自愈（逃生舱）**：conductor 对 advance 失败做**分类**（`interface-drift` / `gate-blocked` / `timeout-env` / `other`），按「同 key + 同 edge」连续失败计数（分类只用于上报与门禁问句）；达阈值即 `mark_stalled`（复用既有四件套：key-status + `stalled` 门禁 + achieved 草稿 + pattern 文件），key 随即被既有 skip 规则冻结，不再无界重试。approve 该门禁 → key-status 复位 `running` + 该 key 恢复**一轮**额度（额度由「该 key 的已批准 stalled 门禁数」派生，无私有状态）→ 回路继续；reject → 走既有 closed-legacy 语义。
3. **VERIFY 裁决失真**：L3 worker 崩溃（exit≠0 / 无 output.md）原先被 `_parse_l3_output` 静默当作 `below`，直接烧掉一轮预算并触发 repair；改为区分 `no-verdict`（worker 失败，附失败状态）与 `below`（reviewer 真裁决），no-verdict 走「重派 L3」而非 repair，停滞原因也带真实失败原因。
4. **底部反馈**：agent-team-loop 的 autopilot 监控面板增加停滞段——tick 新鲜度（seq + age）、槽位用量（in-flight/max）、每 key phase/status/in-flight、advance 连击分类与最近错误、pending 门禁、STUCK 高亮与恢复提示；autopilot enabled 的项目在 PM 窗口**自动呈现**（不再要求先敲 `/autopilot monitor on`）。

### 1.2 技术栈 / 语言

Python 3（`packages/multi-workers/autopilot/**`，pytest）；TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/autopilot/**`，vitest + `npm run check`）。

### 1.3 核心用户场景

1. PM 窗口开着 autopilot，底部面板持续显示 `tick: seq N (3s ago)`、`slots: 0/2`、`key feature-params-service EXECUTE · advance STUCK 2242x interface-drift 2h35m -> /autopilot gate gate-0002 approve|reject`——不需要翻 timeline 就能看到停滞。
2. conductor 在 K2 上第 5 次同签名失败后：冻结该 edge、建 `advance-stuck` 门禁、timeline 记 `advance-stalled`；此后每 tick 只更新状态，不再无界调用子进程。
3. PM 修好 pm-state 后 approve 门禁 → 下一个 tick 恢复 advance（exit=0）→ 连击清零、门禁闭合、面板 STUCK 行消失。
4. 若确实是死局（如上游 key 永久不可达），reject 门禁 → 该 key 按既有语义标 stalled，其 dependents 立即在本 tick 解除依赖阻塞判断（沿用 `_apply_stalled_rejections`）。

### 1.4 范围说明（不做什么）

- 不改 tick 周期（4s）、`round_budget`、L1/L2/L3 循环语义、dispatch 语义。
- 不改 framework 侧 `advance_phase.py` 的接口解析（放宽「Phase 行带括注」的容错是**另一条**根治路径，属跨仓 AgenticTask 改动；本 key 只在 mw 侧做防呆 + 反馈。是否要做由用户另批，记 §4 未决 U-2）。
- 不改 `pm/ui-bridge.ts` 的 watch widget 结构（并发窗口脏文件）；autopilot 反馈落在既有 monitor 面板。若用户要求「并与 watch widget 同屏」，作为 follow-up 在该窗口提交后再评估。
- 不做 `dist/` 重建与扩展加载验证（GC-4；排到并发 key 提交后执行，未执行前不得声称扩展已生效）。
- 不新增 dashboard/HTML/TUI 页面；不做历史持久化统计（只读当前状态）。

## §2 业务约束

### 2.1 平台 / 环境

Windows + cp936 控制台；两处消费同一文件家族：Python conductor（mw serve 子进程）与 pi 扩展（PM 窗口）。并发窗口约束见 GC-4。

### 2.2 性能指标

- 连击判定：每 tick 从 `timeline.jsonl` 尾部窗口（最近 200 行）派生，不新增子进程调用；冻结生效后单 tick 不再 spawn `advance_phase.py`（省掉现状每 4s 一次的 python 启动）。
- 面板渲染：沿用既有 4s 轮询与 110 列截断；新增读取只做尾部扫描 + 既有读取器复用，单帧读取不随 timeline 体积线性放大（4.14MB/21k 行现场必须仍是 O(尾部窗口)）。

### 2.3 安全约束

- 停滞判据不得误伤正常推进：必须同时满足「同 key + 同 edge + 同失败分类连续 ≥ 阈值」且「该 key 无 in-flight worker 行」；任何其它事件的插入都打断连击。
- 冻结是**可恢复**的，不是终止：冻结期间不写任何 phase/roadmap/key-status（除 reject → stalled 的显式语义）。
- 门禁与状态派生都必须幂等（重启 conductor 后不重复建门禁、不丢冻结）。
- 额度恢复只能来自文件派生（已批准的 stalled 门禁数），不得引入内存计数或新状态文件；每次恢复恰好一轮，恢复后再次达上限即再次升级（人工驱动，不会静默空转）。
- 只读面：面板侧零写入（沿用 monitor.ts 的 PURE READ-ONLY 约定）。

### 2.4 集成依赖

- `timeline.jsonl` 事件字段（`ev` / `key` / `detail` / `ts` / `seq`）——本 key 会新增 `advance` 事件的分类载荷与 `advance-stalled` / `advance-resume` 事件；需与 TS 侧 `status-model.ts` 的 `EVENT_TYPES` 镜像同步。
- 门禁协议**不变**：本 key 复用既有 `stalled` kind，不新增 kind、不改 `gates.py` 前端 schema、TS 侧无需镜像新 kind（`mark_stalled` 已写四件套）。
- `_autopilot/config.json` 新增阈值键 `advance_stall_ticks`（默认 5，范围 1..50）——`config.validate_config` 对未知键 fail-closed，故必须双侧同批次登记（Python `DEFAULT_CONFIG`/`_INT_RANGES` + TS 读取器）；旧 config.json 缺该键时取默认（向后兼容）。
- monitor 面板 + `console.ts` 的 `/autopilot monitor` 命令 + 自动启动点（`registerAutopilotCommands`）。

## §3 验收标准（AC）

> AC Locked at 2026-09-22（编号永不回改）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 现场止损：E2Feature `feature-params-service/pm-state.md` 的 Phase 行规范化为 `EXECUTE`（其余字节不动、CRLF 保留）；此后 ≤2 tick 内 timeline 出现 `execute->verify exit=0`，`_index.parallel` 该 key phase 变 `VERIFY`，且出现 `l3-a1`/`l3` 相关 dispatch 事件。证据落 `evidence/e2e-recovery-20260922.md`。 |
| AC-002 | advance 失败分类：`advance.py` 返回值被解析为分类枚举（`interface-drift` / `gate-blocked` / `timeout-env` / `other`），分类写入 timeline `advance` 事件的可机读字段（`detail` 含 `class=`）与 `config`/`advance-stalled` 事件；原有人类可读错误文本保留。分类规则单测覆盖 4 类 + 未知 fallback。 |
| AC-003 | 连击判定与冻结：同一 (key, edge) 的连续失败数 ≥ 阈值（`advance_stall_ticks`，默认 5，读 `_autopilot/config.json`，缺失回退默认）→ 调 `mark_stalled`（reason 含 edge / 连续次数 / 分类分布 / 最近错误摘要，单行）；此后该 key 被既有 skip 规则冻结，不再调用 `advance_phase.py`；`mark_stalled` 幂等（已 stalled 不再重复建门禁/重复记事件）。 |
| AC-004 | 门禁升级与恢复（幂等 + 可恢复）：停滞走既有 `stalled` 门禁（四件套齐全，question 单行含 key / 主分类 / 连续次数 / 最近错误摘要）；approve → key-status `stalled`→`running` + 追加 timeline `gate-answered`（消费记录，同 `_consumed_gate_ids` 协议）+ `resume` 事件，且该 key 的四个受管回路（L2 / EXECUTE / L3 / repair）各获得**一轮**额外额度；reject → 既有 `_apply_stalled_rejections` → `closed-legacy`；重复 approve / 重启 conductor 不得重复恢复（幂等）。 |
| AC-005 | 不误伤：单测证明 (a) 单次失败不冻结；(b) 失败之间插入成功/其他事件（如 `dispatch`/`gate-created`）即打断连击；(c) 不同 edge 或不同分类的失败不合并计数；(d) 该 key 有 in-flight worker 时不计数、不冻结。 |
| AC-006 | 面板停滞段：`renderMonitorLines` 新增行包含 tick 新鲜度（`seq` + age，超时判 STALE）、槽位（in-flight/max）、每 key `phase`/`status`/in-flight、advance 连击（次数 + 分类 + 持续时长）与最近错误摘要、pending 门禁计数；冻结中的 key 以 `STUCK` 高亮并给出 `/autopilot gate <id> approve\|reject` 提示；所有行遵守 110 列截断，分节固定存在（高度不闪）。 |
| AC-007 | 面板数据源只读文件家族：新增派生函数（如 `deriveAutopilotPanel` / `deriveAdvanceStalls`）签名可注入 `nowMs`/路径，缺失或损坏文件降级为安全默认（不抛）；单测覆盖「无 config」「timeline 缺失」「gate 文件损坏」「行数超窗」四种降级，且断言无写 API 调用（沿用 monitor.ts 的只读约定）。 |
| AC-008 | 自动呈现：autopilot enabled（`_autopilot/config.json` 存在且 `enabled=true`）的项目在 PM 模式启动时自动显示该面板；`/autopilot monitor off` 关闭后本会话不再自动拉起；未启用 autopilot 的项目不自动显示（现状不变）。 |
| AC-009 | 回归：`packages/multi-workers` 的 `test_autopilot_*` 全绿（含既有 conductor/gates/timeline 用例无改动失败）；TS 侧新测试通过；`npm run check` 0 error / 0 warning / 0 info；`./test.sh` 相关包无新增失败（对照 Windows 已知基线）。 |
| AC-010 | 变更登记：`packages/multi-workers/CHANGELOG.md` 与 `packages/coding-agent/CHANGELOG.md` 的 `[Unreleased]` 各追加一条（`Fixed`/`Added`）；新增配置键与门禁 kind 记入 `packages/multi-workers/README.md`（或对应 docs）；`_pitfalls.md` 追加本次「无界重试 + 无反馈」教训条目。 |
| AC-012 | L3 裁决失真修正：`_verify_loop` 区分 `meets` / `below` / `no-verdict`；当该轮 L3 worker 行为终态失败（`failed` 等）或 output.md 缺失而 worker 已终态 → `no-verdict`：不派 repair、直接进入下一轮 L3（同 `l3:{key}` 预算），并记 timeline 事件（含 worker 状态与 task_key）；预算耗尽时 `mark_stalled` 的 reason 明确指出是 worker 失败而非 `below`。单测覆盖：崩溃轮不触发 repair、原因分类正确。 |
| AC-013 | 额度恢复的派生性与不可复用性：额外额度 = 该 key 已批准 `stalled` 门禁数（`_resume_credits`），对 L2 / EXECUTE / L3 / repair 四个预算点各放宽一轮；**一次批准只能买到一轮**——额度的消费由各回路单调递增的 `used` 计数（由 append-only 的 dispatch 行派生）保证，用掉即失效，不会在后续轮回里被反复受益；单测证明「恢复后用掉那一轮、再达上限即再次升级且 credits 不重新计入」（`test_one_credit_is_spent_by_one_round_per_loop`）以及「无批准门禁时行为与现状完全一致」。 |
| AC-014 | 面板与守卫同口径：`deriveAdvanceStalls` 的连击清除规则必须与 `conductor._advance_failure_streak` 一致——只有**同一 edge** 的成功才结束该连击（相邻边界的成功既不打断也不计入），避免面板显示「已恢复」而守卫仍在计数；面板与守卫的**唯一**允许差异是尾部事件（`stalled`/`gate-created` 之后仍保留该轮连击以便展示），且必须在代码注释中写明。单测覆盖跨 edge 成功不清除、同 edge 成功后更早的失败不复活。 |
| AC-011 | 并发边界留痕：本 key 结束时明确记录 `dist/` 重建与扩展自动呈现的**加载验证**是否已执行（依赖并发 key 提交）；未执行则记入未决并向用户报告，不得声称已验证生效。 |

## §4 风险与未决项

- R-1 阈值选择：4s × 5 = 20s 即冻结，对「慢门禁」类临时失败可能过早升级。缓解：默认 5 且可配（`advance_stall_ticks`）；升级是**提示而非终止**，approve 即恢复一轮；分类分布写入 reason 供人判断。
- R-2（已关闭，改设计）：不再新增 gate kind，`stalled` 复用既有 schema，无双侧登记兼容风险。
- R-3 冻结与人工修复的交互：冻结期间即使 pm-state 已被修好，也不自动重试——必须 approve 门禁（有意的：避免静默再次空转）。若用户希望「自动探测恢复」，作为 follow-up。
- R-5 恢复额度被滥用：approve 是人工动作且每次只加一轮，单调递增；若同一 key 被反复 approve 而每次都失败，会持续消耗人工注意力（这正是想要的反馈），但不会静默空转。
- R-4 并发窗口重叠：`dist/`、CHANGELOG、README 与 `mw-rag-integration-fix` 冲突面；本 key 结束时按 GC-4 收口（AC-011）。
- U-1（未决）：面板是否应与 watch widget 同屏（`ui-bridge.ts` 结构改动）——待并发窗口提交后由用户定。
- U-2（未决）：是否在 framework 侧放宽 `advance_phase.py` 的 Phase 行解析（把 `EXECUTE（…）` 视作 `execute` 并规范化写回），从根上消除 `interface-drift` 这一类——跨仓 AgenticTask 改动，需用户另批。
- U-3（已定案）：approve stalled 门禁 → 该 key 恢复一轮额度（AC-013）；不与 `budget-exhausted` 的 bonus 机制叠加（两者独立计数）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `mark_stalled` / `_apply_stalled_rejections`（既有 stalled 四件套与 reject→closed-legacy 语义，AC-004 的 reject 分支直接复用）。
- `_create_gate` / `gates.create` / `gates.GATE_KINDS`（门禁创建、锁定、幂等）。
- `timeline` 事件 schema 与 `timeline.py::query_events`、TS `status-model.ts::queryTimeline`（连击派生与面板数据源）。
- TS `autopilot/monitor.ts` 面板骨架（固定分节 + 110 列截断 + 只读约定 + 可注入 `nowMs`/`readState` 测试缝）与 `autopilot/console.ts` 的 `/autopilot monitor` 命令、`status-model.ts` 的读取器族。
- `test_autopilot_conductor*.py` 的 fake-framework harness；`mw-autopilot-advance-root` 的证据链与 `_arch_snapshot.md` 相关条目（同型故障先例）。
- 本窗口诊断脚本思路（timeline 尾部统计 / pm-state Phase 行字节审计）——T1 与 AC-002/003 的复现夹具。

### 需规避坑点

- P-001（PS 管道损坏无 BOM UTF-8）：`pm-state.md` 与所有 JSON/MD 改写用 Python `encoding="utf-8"` 或 write/edit，禁止 PS `Get-Content`/`Set-Content` 往返（本 key T1 直接命中该坑：现场文件含中文 + CRLF）。
- P-002（Phase 行机器接口）：任何写入 `- Phase:` 的内容必须是裸阶段名；解释性文字写 `- Next Action:`（E2Feature 现场根因）。
- P-003（`open(p,"w")` 先截断后求值）：状态文件先算后写；测试断言文件非空 + 内容锚点，不只信退出码。
- P-004（POSIX 词法在 Windows 路径丢反斜杠）：路径一致性比较用 `Path.resolve()` / `os.path.realpath`。
- 野生实施教训（mw-ue-toolchain）：先建 key 再动手；跨仓/跨包改动按 AC-011 留痕。
- 并发窗口教训（本次现场）：多 session 同 cwd 时先看 `git status` + `_index.parallel` claim，再决定可写文件集。
