# Research: 门禁分层 / 面板聚合 / claim 同步的接口约束（design）

> 日期：2026-09-23
> Key: mw-worker-visibility-gate
> 方式：只读代码勘察（本仓），无外部网络调研

## 决策问题

支撑 design 的四个接口级决策：
- D-101/D-102：门禁分层改在 `phase-docs.ts` 还是调用点？相位从哪读、未知值如何归一？
- D-105/D-106：面板聚合行如何注入（签名怎么改才不动 12 处既有测试调用）？内容格式怎样满足 AC-006~AC-009？
- D-107/D-108：claim 同步写 pm-state 的落点（哪个函数）+ 写入策略（换行/原子/缺行）？
- D-103：要不要顺带按任务类型收紧 SPEC 相位派发？

## 调研方法与出处

全部为仓库内文件的直接阅读（文件:行号）与字节级抽样。

## 发现

### F1 门禁分层落点

- `dispatchDocGaps`（`shared/phase-docs.ts:127`）是唯一判定入口，`_scratch` 短路在 `:128`；缺项文案集中在 `phaseDocGaps`（`:96-110`），阈值常量 `MIN_PHASE_DOC_BYTES`（`:7`），提示文案 `DOC_GATE_HINT`（`:117`）。
- 调用点**三处**（T-1 执行期补充发现，见 design D-110）：`pm/ui-bridge.ts:1093`（`dispatch_worker` 工具）、`pm/ui-bridge.ts:1498`（另一入口）、`pm/pm-orchestrator.ts:429`（`dispatchNewTasks` 后台扫描）。若把分层写在调用点，三处必须各自实现 → 分叉风险；写在 `phase-docs.ts` 则三处只需多传一个参数。第三处的存在由 T-1 的既有测试回归暴露（`agent-team-loop.test.ts:1516` 断言 `gaps` 长度 5 → 实测 3）。
- 相位读取口现成：`dispatchPhase(agenticdocRoot, ownerKey)`（`ui-bridge.ts:902`，内部 `StateManager.read().phase`，`pm/state-manager.ts:31`），且两处调用点都已有 ownerKey。
- 归一化事实：`update_index.py claim` 新建 pm-state 时写 `- Phase: init`（框架仓库脚本），而 TS 侧 `Phase` 联合类型只有 `SPEC|DESIGN|PLAN|TASKS|EXECUTE|DONE`（`state-manager.ts:6`）→ 门禁必须把 `init`/`—`/空/未知一律按 SPEC 层处理，否则新 key 会在"design 层判定"下被要求 design 文档。

### F2 面板签名与既有调用面

- `renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key)`（`ui-bridge.ts:480-485`），本键行筛选在 `:495`；行宽上限 `WATCH_LINE_MAX=110`（`:249`）。
- 调用点：`pm-orchestrator.ts:312`、`:531`、`:645`；测试调用点 12 处（`test/extensions/agent-team-loop.test.ts:2162,2195,2222,2261,2530,2576,2597,2613,2623,2638,2653,2659,3902`）。
- **结论**：新增参数必须**可选**（`extraTaskKeys?: ReadonlySet<string>`），否则 12 处既有调用全要改，且容易把既有断言改坏；可选参数天然满足 AC-007（不传 = 与改造前逐行相同）。
- 检查点读取口现成：`readTaskProgress(taskDir)`（`ui-bridge.ts` 内已用于行详情），risk 取值 `low|mid|high`（同文件 `checkpoint.risk`）。
- 面板既有尾部约定：无本键行时输出 `  (no worker tasks)`（`:526` 附近），历史折叠行 `+N more` → 聚合行追加在末尾不破坏既有首行/尾行断言。

### F3 claim 同步落点与写入策略

- TS claim 调用点两处：`pm/ui-bridge.ts:238`（`takeOverKey`，被 `/pm-key` 与 `switch_key` 工具共用：`:676`、`:694`、`:1299`）与 `pm/pm-orchestrator.ts:298`（会话恢复时的 quiet re-claim，`demoteOthers:false, activate:false`）。两处都会把索引行 Claim 列写成 `self`。
- pm-state 现状：TS 侧只有 `StateManager.read()` 被生产代码使用（`ui-bridge.ts:904`）；`write()`（`state-manager.ts:56`）会整体重写成 **旧 3 段模板**（`## Section 1: Snapshot` + `## Notes`），与框架 7 段模板不兼容 → **同步绝不能走 `StateManager.write()`**，必须单行原地替换。
- 换行抽样（字节级）：本仓三个 key 的 `pm-state.md` 全部为 CRLF（`\r\n`），LF-only 计数为 0；框架脚本 `_update_pm_state_claim` 也按探测到的换行改写（`update_index.py` 读 `newline=""`）。→ 同步实现必须探测主导换行并原样写回，否则整文件换行翻转（P-010 同类）。
- 缺行情形：`update_index.py` 的 stub 只在新文件时创建（`Key`/`Claim-Id`/`Phase: init`）；`advance_phase.py` 升级模板时**保留** `- Claim-Id:`（`:317-319`）。因此"pm-state 存在但缺 `- Claim-Id:`"只在文件被手改损伤时出现 → AC-011 要求：不重建、不写，只回 warning（fail-closed 但不阻断索引）。

### F4 类型门禁的兼容性风险

- 历史口径 P-007（`_pitfalls.md`）：审查/调研任务以 `type: coding` 派发（"审查任务改派 coding 类型 + 只允许写一份报告文件"），且 `mw-worker-progress-persist` 之后 review 角色有了 `worker_file` 落盘通道。
- 现仓代码里 `resolveDispatchType` 在门禁之前执行（`ui-bridge.ts:1075` 附近 vs `:1093`），技术上可以按 type 收紧，但会与 P-007 的既有实践冲突，且本 key 的 AC-012 明确要求 coding 在 SPEC 相位不被拒。
- 结论：**不做类型门禁**（D-103），只做文档分层；spec §4 R-1 记录放宽后的缓解（spec 侧四项缺一即拒）。

### F3b pm-state 的 Claim-Id 在 TS 创建路径上是**缺失**而非不一致（T-1 执行期发现）

- 逐 key 实测（`re.search(r'^- Claim-Id:', pm-state, re.M)`）：`mw-worker-progress-persist`、`mw-task-scope-isolation`、`mw-rag-window-parity`、`mw-worker-visibility-gate` 四个 key 的 pm-state **全部为 None**，而它们的索引行都有 Claim 值。
- 原因：TS 路径 `switch_key` → `IndexStore.claim`（`shared/index-store.ts:91`）只写索引行；pm-state 由随后的 `advance_phase.py` 新建（7 段模板，**不带** Claim-Id）。只有框架侧 `update_index.py claim` 才会写该行（新文件时建 stub，已有文件时替换或 "Insert after '- Key:'"）。
- 后果：若不插行，D-c 的"两处必须同值"对最常见的 key 创建路径**无法达成** —— 每次 claim/takeover 只能得到一条 warning，镜像永远为空。
- 框架已有先例可循：`update_index.py._update_pm_state_claim` 缺行时的处理就是插在 `- Key:` 之后（`count=1`，保持换行）。
- 结论 → design D-111：同步函数在"有 `- Key:` 行但无 `- Claim-Id:` 行"时插行（其余字节不变），仅在两者都没有时 fail-closed。

## 结论 → 决策映射

| 结论 | 支撑的决策 |
|------|-----------|
| F1 | D-101（分层写在 `phaseDocGaps`/`dispatchDocGaps`，调用点只传相位）、D-102（归一化：SPEC 层 = SPEC/init/`—`/空/未知）、D-109（缺项文案与 hint 复用，不新增参数） |
| F2 | D-105（可选第六参数 `extraTaskKeys`）、D-106（聚合行格式与顺序）、D-107b（追加在末尾、宽带上限复用 `WATCH_LINE_MAX`） |
| F3 | D-107（单行原地替换 + 换行探测 + 原子写 + 不创建文件）、D-108（两处调用点在 claim 成功后同步；失败回 warning 不阻断） |
| F3b | D-111（缺 Claim-Id 行时在 `- Key:` 后插行；AC-011 已按 REVISED 修订） |
| F4 | D-103（不做类型门禁）、AC-012（回归项） |
