# T-05 — AC-010：多段 `output.md` 回读取末个非占位块 + settle 幂等

- key: `mw-dispatch-settle-gates`｜AC: **AC-010**｜VC: **VC-043…VC-046**｜波次 **3**｜链 1（依赖 T-02 对 `ui-bridge.ts` 的编辑）
- 角色: coding
- **唯一允许改的路径**：① 新建 `packages/coding-agent/src/extensions/agent-team-loop/shared/output-sections.ts`；② `pm/ui-bridge.ts`（**仅** `readTerminalDetail` 的 4 处读点）；③ `worker/worker-mode.ts`（**仅** settle 入口幂等守卫）；④ 新建 `packages/coding-agent/test/suite/mwds-t05-output-sections.test.ts`；⑤ 自身目录 `report.md`
- 上游：`plan.md §4` 契约 **C7**；`design.md` DD-08；证据 `evidence/research/design-settle-read-20261010.md`（口径与回归断点）

## 现状（以符号名为准）
- `readOutputSection`（`ui-bridge.ts` 约 `:344`，`readOutputSummary` 约 `:339`）= **首匹配**契约，已被测试钉住 ⇒ **不得改**。
- `readTerminalDetail` 有 4 处读点（约 `:457` / `:460` / `:464` / `:470`）。
- 语料实测：30 个 worker 目录中 10 个含 >1 个 `## TL;DR`（最多 9 = `mwg-t11-*`）；3 个目录含占位符块；跨 run 追加是主因（`blocks == starts`），同进程双 settle 次之。

## 必须实现
1. **新模块 `shared/output-sections.ts`（C7）**：
   - `readOutputSections(text)`：按标题块切分（保留块序与标题行），返回 `{title, body, startLine}[]`；
   - `isPlaceholderSection(title, body)`：body 去空白后为空、或 ∈ 15 个占位符集、或 < 阈值字节（阈值取常量并注释依据，如 32 B）；
   - `readLastProductSection(text)`：从**末块**向前取首个非占位块；无 ⇒ `undefined`；
   - 占位符集（15 个，单一真相源，含现有 `See task output for details.`、`(none)`、`No changed files recorded.` 等既有形态）：从现有代码/测试提取，不得凭记忆臆造。
2. **只切 4 个读点**：`readTerminalDetail` 内改用 `readLastProductSection`；其余调用面（`/mw` 命令、整文件回读、`readOutputSummary`/`readOutputSection`）**零影响**。
3. **settle 幂等**：`worker-mode.ts` 的 settle 入口加 `if (taskDone) return;`（或用既有等价状态位），保证同一 run 二次 settle 不追加第二块。**不得**改追加语义（D-117 有意：worker 自写机器行不被销毁）。
4. 回读失败降到既有降级路径（不得抛错、不得新增写盘）。

## 反向用例（必须真跑）
- (a) fixture：首块占位 + 末块真报告（仿 `mwg-t11` 形态）⇒ 回读得到**真报告**；(b) 单块正常 ⇒ 行为不变；(c) 只有占位符块 ⇒ 返回 `undefined` 且走既有降级文案；(d) 9 段形态（`mwg-t11` 语料）⇒ 取到末个非占位块。
- (e) 幂等：同 run 二次 settle ⇒ 追加块数不增（断言字节相等）；(f) `/mw` 命令面与 `readOutputSummary` 首匹配语义不变（回归）。

## 对照协议（`plan.md §5`）
A 把 `readLastProductSection` 回退成首匹配 ⇒ (a)(d) 转红；B 反转占位判定（把占位当真实）⇒ (a) 转红；C 摘除 `taskDone` 守卫 ⇒ (e) 转红。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-043: placeholder_first_real_last=true picked_last=true
[VERIFY] VC-044: single_block_unchanged=true
[VERIFY] VC-045: double_settle_blocks=1 bytes_equal=true
[VERIFY] VC-046: mw_command_surface_unchanged=true first_match_contract_kept=true
```
命令：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t05-output-sections.test.ts`

## 禁止
不改 `readOutputSection`/`readOutputSummary` 契约；不改 `output-writer.ts`（T-06）；不改 `pm-orchestrator.ts`（T-04 已改，勿再动）；不改大测试文件 `test/extensions/agent-team-loop.test.ts`；不 build；不 commit；不跑全量套件 / `npm run check`。
