# T-15 / T-17 / T-19 回执（PM 直执，隔离先行批次）

- key: `mw-gate-verdict-hardening` · 日期: 2026-10-10 · 基线 HEAD: `776b82d7f`
- 执行方式：**PM 直执**（D-014 硬门禁：隔离落地前不派 worker；隔离三卡正是本批）
- 覆盖 AC：**AC-023（T-15）**、**AC-020/AC-021（T-17）**、**AC-019（T-19）**；AC-022 的挂点已留（`runState` 注入位），真实 `run.json` 落在 T-20

---

## 1. 改动面（4 文件 + 1 新测试）

| 文件 | 改动 |
|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` | +98/−19：`parseWorkerLine` 返回 `{ok}/{ok:false,reason}`；新增 `readQueue()` → `{rows, unparsable[], version}`、`parseQueueHeader()`、`WorkerQueue`/`UnparsableWorkerLine` 类型；`upsert` 改为**槽位回插**（不可解析行原文保留）；新队列写 `# mw-queue:v2` 头，已有文件不补头 |
| `.../pm/pm-orchestrator.ts` | +89/−3：`DispatchScanOptions` 增 `scope`/`watchedKey`/`maxPerScan`/`runState`/`onAlarm`；`DEFAULT_DISPATCH_MAX_PER_SCAN = 3`；扫描前 `readQueue()`，`unparsable > 0 ⇒ 告警 + return`；空队列 + 候选有产物证据 ⇒ 告警 + return；PM 作用域过滤；单轮配额；`agent_settled` 传 `scope:"pm", watchedKey: watch.key` |
| `.../test/suite/worker-store.test.ts` | +116：T-15 用例（9 列 IN-3 形状、不可解析计数与保留、槽位回插、版本头三态、两种失败原因） |
| `.../test/suite/worker-dispatch-guard.test.ts` | **新增**：T-17/T-19 用例 7 条（作用域双向、空格队列、unparsable、空队列+证据、配额、runState 终态跳过） |
| `.../test/extensions/agent-team-loop.test.ts` | 1 个既有用例适配新队列头（`writes 9-column rows`） |

---

## 2. `[VERIFY]` 实测

```
# T-15
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts
→ Test Files 1 passed (1) / Tests 11 passed (11) / 185ms

# T-17 + T-19
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts
→ Test Files 1 passed (1) / Tests 7 passed (7) / 703ms

# 回归（8 个相关文件，含 6 个既有 extension 套件）
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts \
  test/suite/worker-dispatch-guard.test.ts test/extensions/agent-team-loop.test.ts \
  test/extensions/agent-team-loop-profile-injection.test.ts \
  test/extensions/agent-team-loop-pm-state-sync.test.ts \
  test/extensions/agent-team-loop-baseline.test.ts \
  test/extensions/agent-team-loop-ack.test.ts \
  test/extensions/agent-team-loop-watch-aggregate.test.ts
→ Test Files 8 passed (8) / Tests 230 passed (230) / 4.33s

# 全量检查
npm run check  → 通过（biome 自动格式化 1 个文件后复跑仍绿；pinned-deps / ts-imports / shrinkwrap / install-lock / tsgo --noEmit / browser-smoke 全通过）

# 所有导入 worker-store.ts / pm-orchestrator.ts 的测试文件（13 个，覆盖面最广）
node ../../node_modules/vitest/dist/cli.js --run <13 files>
→ Test Files 13 passed (13) / Tests 303 passed | 1 skipped (304) / 4.42s
```

**环境限制（如实记录）**：`./test.sh` 需 bash，而本机 `bash.exe` 指向未安装发行版的 WSL（`wsl --list` 报无分发）⇒ 无法按 AGENTS 口径跑全量非 e2e；改用**逐文件/逐套件**口径：与本次改动有导入关系的 13 个测试文件全绿（含 `autopilot-console.test.ts` 的精确 `toEqual` 用例），Python 侧本批未改。

Python 侧本批未改（T-18 负责），基线见 `verify-baseline.md`（2 既有红，与本批无关）。

---

## 3. 非空洞对照（摘掉判据 ⇒ 指名用例转红）

机器可复现脚本：`evidence/scripts/t15-controls.ps1`、`evidence/scripts/t17-controls.ps1`（字节安全 UTF-8 读写；每次跑完从备份还原）

### T-15（`worker-store.test.ts`，共 11 用例）

| 控制 | 变异 | 结果 |
|---|---|---|
| A | `WORKER_COLS_MAX = 9 → 8`（回到事故前解析器） | **5 failed / 6 passed** |
| B | `upsert` 改回"按已解析行整表重写"（IN-3 的删除） | **1 failed / 10 passed** |
| C | 版本头识别失效（正则改为永不匹配） | **1 failed / 10 passed** |

### T-17 / T-19（`worker-dispatch-guard.test.ts`，共 7 用例）

| 控制 | 变异 | 结果 |
|---|---|---|
| A | 删掉 PM 作用域过滤 | **2 failed / 5 passed** |
| B | 删掉单轮配额 | **1 failed / 6 passed** |
| C | `unparsable > 0` 不再中止扫描 | **1 failed / 6 passed** |
| D | 删掉"空队列 + 产物证据"守卫 | **1 failed / 6 passed** |

全部控制后文件还原校验通过（控制脚本最后打印 `restored: True`，并复核守卫原文仍在）。

---

## 4. AC ↔ 用例映射

| AC | 用例 | 判据落点 |
|---|---|---|
| AC-019① | `scope pm queues only the watched key + _scratch and never rewrites another key's history` | `pm-orchestrator.ts` 作用域过滤（`scope === "pm"`）|
| AC-019② | `scope cli (the mw command surface) still dispatches across keys` | 默认 `scope = "cli"` ⇒ 全局保持 |
| AC-019（补充） | `scope pm without a watched key still picks up _scratch` | fail-safe：无 watch 也不全扫 |
| AC-020 | `an unreadable queue row aborts the whole scan and is preserved`；`an empty queue plus product evidence refuses the scan; a fresh project dispatches`（双向） | `queue.unparsable > 0` / `queueIsEmpty && hasProductEvidence` |
| AC-021 | `queues at most the per-scan quota and reports the refusal` | `queued >= maxPerScan`（默认 3）|
| AC-022（部分） | `skips a task whose own product is already terminal` | `opts.runState?.(taskKey) === "terminal"`（真实读取由 T-20 接）|
| AC-023 | `reads every 9-column IN-3-shaped row…`；`counts an unreadable line, then re-writes one row without touching it`；`replaces a row in place and leaves the rest of the file byte-identical`；`reads a declared header and never adds one to an existing header-less file`；`reports the two failure reasons separately` | `readQueue` / 槽位回插 / 版本头 / `reason` |

---

## 5. 已知边界（诚实记录）

1. **空队列守卫的作用点**：按 owner 逐个判定（首个"候选含产物证据"的 owner 触发中止）。若在它之前的某个 owner 没有产物证据（真·新任务）且已被派发，则那部分派发已发生——这是"新项目正常派发"所必需的取舍，已在代码注释中写明。
2. **AC-023 只覆盖 TS 写者**：Python 侧 `mw_common.update_status()` 仍是"parse 全表 → 整表重写"，**同样会静默删除不可解析行**（实测代码路径，见 `mw_common.py:1704-1727`）。该半边的修复属 **T-18**，不得视为已完成。
3. **`unparsable > 0` 时零派发**为 fail-closed：若某项目长期存在一行坏数据且无人修复，派发会持续被抑制——这是设计选择（宁可少派），doctor 侧（T-18）负责让它可见。
4. AC-022 的**真实**终态来源（`run.json`）尚未落地 ⇒ 目前 `runState` 缺省为 `"unknown"`（行为与改造前一致），T-20 接入。

---

## 6. 遗留卡（本批未做）

`T-18`（Python 写者保留 + launcher 有界 + acked 参与 + doctor 形状判据）、`T-20`（`run-store.ts` + worker 自写 `run.json`）、`T-21`（IN-3 样本回放与映射表）、`T-14`（计数锁）、以及 G1~G4 的 `T-01…T-13`、`T-16`。

---

## 7. 同日后继补充（2026-10-10 16:50）

1. **告警载体补齐（本报告 §5 边界 #1 的收尾）**：新增 `recordDispatchAlarm()` 把告警写进 `auto-decisions.jsonl` 的 `phase:"dispatch-alarm"` 行（形状对齐 Python 单写者：一行一 JSON + 1-based `seq`）+ `deliverPmAlert` 推送，**每 session 每 kind 一次**；并补了一条真跑 `pmActivate` + `agent_settled` 的**接线用例**（断言 ledger 行内容精确相等）。⇒ T-17/T-19 的非空洞对照从 4 组扩到 **5 组**（新增 E：摘掉 ledger 写入 ⇒ 接线用例红），见 `evidence/scripts/t17-controls.ps1`。
2. **AC-024（用户新要求）**：跨 key 只读（读全局 / 写限定），新增 **T-22**；AC-019② 反向用例就地修订（原写的 `mw dispatch --key` 子命令**不存在**）。见 `evidence/runs/t-22-crosskey-readonly-report.md`。
3. 本报告 §2 的 `230 passed` 为当日 15:36 的回归快照；**当前快照 = 18 个相关测试文件 / 368 passed + 1 skipped**。
