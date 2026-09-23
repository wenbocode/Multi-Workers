# Achieved: mw-worker-visibility-gate

> 日期: 2026-09-23 | Phase: DONE
> 触发源：另一台机器（PC3）窗口的真实事故 —— key `h0h1-decision-baseline` 在 SPEC 相位被派发门禁拦住，4 个 worker 落到 `_scratch`，`list_tasks` 看得见面板看不见；同 key 的 `Claim-Id` 与 `_index.parallel` Claim 列不一致而 audit 不报。

## 系统行为变化

### 1. 派发门禁按 owner key 的相位分层（`shared/phase-docs.ts`）

- 变化前：`dispatchDocGaps(root, key)` 一次性要求 spec + design 两侧共六项（`spec.md`≥500B、`spec-*` 调研笔记、§0 预期收益、≥1 条 `AC-NNN`、`design.md`≥500B、`design-*` 调研笔记）——**新 key 在 SPEC 相位永远过不了**，关键调研被逼到 `_scratch`，证据落在真 key、task/queue 落在临时 key，追溯链断开；更矛盾的是它要求的 `design-*` 笔记正是被拦下的 worker 要产出的东西。
- 变化后：门禁读 owner key 的相位（`pm-state.md` `- Phase:`，与 task.md 的 `phase:` 头同源）并只要求该相位蕴含的部分——**SPEC（含 `init`/`—`/空/未知）只校验 spec 侧四项**；**DESIGN 起**才追加 design 侧两项。三处调用点全部接线（`dispatch_worker` 工具、`/worker` 命令、`pm-orchestrator.ts` 后台扫描），共用一次相位读取。
- 不变项：缺项文案与 `DOC_GATE_HINT` 逐字不变；无旁路/豁免参数；`_scratch` 短路不变；**不按任务类型限制**（`type: coding` 在 SPEC 相位照旧放行，保住 P-007 口径）。
- 影响面：任何在 SPEC/DESIGN 相位派 worker 的项目；SPEC 相位的 key 现在可承载调研 worker，`_scratch` 不再是新 key 调研的必经逃生门。

### 2. 底栏面板新增跨 key 聚合提示行（`pm/ui-bridge.ts` + `pm/pm-orchestrator.ts`）

- 变化前：面板用 `ownerKeyOf(e) === key` 单维筛选且签名拿不到 `dispatchedTaskKeys` → 本窗口派到 `_scratch`/他键的任务"工具看得见、面板看不见"（`list_tasks` 与面板口径分叉），跨 key 的发散/失败完全静默。
- 变化后：`renderWatchLines(..., extraTaskKeys?)` 在末尾追加**恰好一行** `  ~ N elsewhere: <owner>(<counts>; risk=high:K)`：owner 按（行数 desc, 名 asc）排序、状态按固定顺序只列非零、跨 key **running** 且 `[CHECKPOINT] risk=high` 的行计入 `risk=high:K`、整行 ≤110 字符截断。三处面板调用点传入 `watch.dispatchedTaskKeys`。
- 不变项（AC-007，双向验证）：不传参数时**输出与改造前逐行相同**（用 `git show HEAD:` 提取改造前面板模块同夹具逐行比对）；面板仍只列 watched key 的自身行（避免把他键产出误读成本 key 的）。
- 影响面：所有 PM 窗口；跨 key（含 `_scratch`）派发的任务现在至少有一行可见摘要 + 高风险标记。

### 3. claim 身份两处同值 + 缺行补写（`shared/pm-state-claim.ts` + 两处调用点）

- 变化前：`- Claim-Id:` 有两个写入者且 pid 语义不同（框架 `update_index.py claim` 用短命 python 进程 pid；TS `switch_key`/`IndexStore.claim` 用 pi 窗口 pid 且只改索引行）→ 同一 claim 在两处不同值；且本仓四个 key 的 pm-state **根本没有**该行（TS 路径只写索引行、`advance_phase` 新建模板不带它），镜像长期缺失而无任何消费者报错。
- 变化后：TS claim/takeover（`takeOverKey` 与 `restoreWatch` 会话恢复 re-claim）成功后调用 `syncPmStateClaimId` 把索引行的同一 `host:pid` 写入 `<key>/pm-state.md`：有 `- Claim-Id:` 行则单行原地替换，缺该行但有 `- Key:` 行则在其后**插行**（与框架 `update_index.py` 同构）；探测主导换行（CRLF 优先）并有守卫拒绝换行计数变化；原子写（`.tmp`+rename）；文件缺失或两行都缺时 fail-closed 且不写，claim 本身仍成功（索引行权威），工具文本/通知给出**一条** warning。
- 不变项：未复用 `StateManager.write()`（它会整体重写成旧 3 段模板）；7 段模板、`- Updated:` 行、其余字节逐字节不变（字节级：headings 7→7、updated 1→1、CRLF 27→27 / 插入分支 26→27 且 LF-only 保持 0）。
- 影响面：任何 claim/takeover（`switch_key`、`/pm-key new|switch`、会话恢复）。规则与坑点已登记 `_pitfalls.md` **P-011**（索引行权威 / 两处同值 / liveness 只在索引行判定）。

## 证据

- `evidence/research/spec-dispatch-gate-visibility-baseline-2026-09-23.md`（基线：门禁/面板/claim 三处 file:line）
- `evidence/research/design-gate-panel-claim-interfaces-2026-09-23.md`（接口约束 F1~F4 + F3b：四个 key 的 pm-state 均无 Claim-Id 行）
- `evidence/verify-independent-2026-09-23.md`（T-5 独立验证：13/13 VC，12 PASS + 1 PASS-with-note，0 FAIL；M-1/M-2/M-3 三变异红 + sha256 逐字节复原；回归 204/204 + `npm run check` EXIT=0；git 起止逐行相同）
- `evidence/quality-gate-report-2026-09-23.md`（质检门禁：31 充分 / 1 有条件 / 0 无证据，结论 ✅ 通过）
- `quality-report.md`（交付面 + AC 勾销 + 偏差登记）
- 四个 worker 的 `workers/*/output.md` 与 `trace.log`（含 `[VERIFY]`/`[MEASURE]`/`[CHECKPOINT]` 原始行）

## 偏差

1. `phaseDocGaps(status, tier?)` 的 tier 缺省 `design`（设计原写必填）——为保住既有 9 处单参调用不破 `tsgo --noEmit`；生产路径恒显式传 tier。
2. 门禁调用点由 2 处修正为 3 处（design 新增 D-110，勘察遗漏 `pm-orchestrator.ts:429` 后台扫描）；既有 `agent-team-loop.test.ts:1516` 的 gaps 断言随之 5→3（该用例其余语义原样保留）。
3. AC-011 语义修订（design D-111）：缺 `- Claim-Id:` 行时插行而非"不写 + warning"，依据是本仓四个 key 的 pm-state 均无该行。
4. VC-009 夹具写 trace.log `[CHECKPOINT] risk=` 行（`readTaskProgress` 的真实解析源），而非 `progress.md` 的 `[machine]` 展示行。
5. 新用例全部落在 `test/extensions/`（4 个新文件），未新建 `test/suite/` 文件（包内单一 vitest 配置，功能等价）。
6. 未 `mw build --install`（全局 bundle 仍为旧版）；`dist/**` 未重建。

## 遗留

| ID | 内容 | 去向 |
|----|------|------|
| R-1 | 框架仓库（`.agents/skills/agentic-task`）：claim 桩只有 Key/Claim-Id/Phase 三行——`advance_phase.py:313-341` 有**显式**升级路径把它补成 7 段模板（保留 Claim-Id），**非缺陷**（此前记录有误，已核实）；索引 Phase 列的 `—`（python claim）/`SPEC`（TS `IndexStore.claim`）与 pm-state 桩的 `init` 是"尚未开始"的三种写法，audit 以 pending 短路（`SPEC` 刻意不 pending，因为真的 SPEC 必须查门禁）——**已用测试钉住** | ✅ 已闭合 2026-09-23（框架仓库 `d0834ae`，VC-030 + AG-008 + 两处文档说明，三个镜像同步，已推送 origin/master） |
| R-2 | 新 key 首次 claim 时 pm-state 尚未存在 → 仍回一条 `pm-state.md missing` warning（镜像未建立，非分叉） | 接受不处理（`advance_phase` 建文件后，下次 claim/takeover 会插行收敛） |
| R-3 | `phaseDocGaps` 的 tier 缺省 `design`：未来新增调用点若忘记传相位，会静默退回"六项全查"（比 spec 层更严，可能复现本 key 修的问题） | 记入 `_pitfalls.md` 建议项；既有单参调用清零后把 tier 改为必填 |
| R-4 | `test/extensions-runner.test.ts` 4 个 hook 超时（Windows 环境基线，该文件零引用本 key 模块） | 归入既有环境基线，不处理 |
| R-5 | 跨 key 的 **risk 升级投递**仍只覆盖 watched key（面板已可见 risk 标记） | 用户决策项（spec §4 未决 Q-1 / 质检 Q-X-006） |
| R-6 | 全局 bundle 未重建（`mw build --install`） | 由用户决定何时构建（构建纪律） |
