# T-04 · 检查点 `landed` 信号：判据为主 + 与账本同源的落盘事实（W4）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 超时看门狗：activity watchdog + 墙钟兜底 + 30 分钟收敛检查点」）——检查点判据是「真挂死 vs 在推进」的唯一机器判据。
- 现状（**已确证，不要重复发现**）：
  - `READ_TOOLS`/`WRITE_TOOLS` 只含 `{read,grep,find,ls,glob}`/`{write,edit}`（`worker/worker-mode.ts:260-262`）⇒ `worker_file`/`bash` 不计 ⇒ writeless 角色 `writes=0` **恒真**（**入参缺陷**）。
  - `computeRisk` 三支（`worker/worker-mode.ts:283-286`）；`checkpointAnchorMs = min(30m, max(1s, budget/2))`（`worker/worker-mode.ts:250-252`）。
  - 现场：`wjg-w12` 形态 —— `[WRITE_FILE]`=4、`worker_file` 调用 4 次、37,149 B 产物已落盘，但检查点仍判 `mid`（唯一有可重放检查点的实例）。
- 设计落点（`design.md` §6，逐字照办）：
  - `writes` / `uniq_targets` 语义**不变**（保住既有断言）；新增 `landed` / `lastLandingAgeMs` / `artifactPresent` / `progressDone`，来源 = `parseWriteFileEvents`（同一 `formatWriteFileEvent` 语法，按归一化路径去重，**不叠加** `[TOOL] worker_file` 计数）。
  - `computeRisk` 单函数扩展：`s.landed === undefined` 时 write 角色**逐字节不变**；writeless 分支 = 产物在盘 `low`；零落盘且过锚点 `high`；落盘陈旧且无产物按 `repeatTop>=4` / phases 停滞 `mid`，否则 `low`；新鲜窗 `max(60s, anchor/3)`。
  - `[CHECKPOINT]` 行**尾部追加**可选字段 `land=/last_land=/artifact=/done=`（仅 writeless），`CHECKPOINT_LINE_RE`（`shared/heartbeat.ts:84`）用可选非捕获组扩展 ⇒ 旧行/新行都能解析，**不新增 trace 行**。
- 不变量 I3（**硬约束**）：idle（`worker/worker-mode.ts:2589-2646`）、墙钟（`:2650-2654`）、deadline steer（`:2577-2587`）**都不吃 `risk`**。S5 改检查点判据时必须与三段式超时共存，不另起机制。
- AC-009：`wjg-w12` 形态判 `risk≠mid`；「无任何落盘事件且无完成记录」判 `risk=mid` 及以上；两场景各 1 例。**根因须同时处理**：`worker_file`/`bash` 不进 `writes`（修入参或改判据二者至少一处），且必须验证 idle/墙钟两段行为不变（3 例：正常活跃、真挂死、预算尾段）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅**检查点段）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/heartbeat.ts`
- `packages/coding-agent/test/suite/mwoc-w4-checkpoint-invariants.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`worker/worker-mode.ts` 的**抽取器/记账段**（归 T-02，已完成）与 **settle 段**（归 T-05，未开始）**一律只读**——本卡只改检查点段（`computeRisk` 与其调用点）；`worker/output-*.ts`、`pm/**`、`packages/multi-workers/**`、其它 test/suite 文件只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **新增字段取自账本**：`landed` / `lastLandingAgeMs` / `artifactPresent` / `progressDone` 的来源必须是 `parseWriteFileEvents`（同源、同归一化），**不得**叠加 `[TOOL] worker_file` 计数（否则与 T-02 的账本语义分叉）。
2. **`writes` / `uniq_targets` 语义逐字不变**；`landed === undefined` 时 write 角色的 `computeRisk` 结果**逐字节不变**（用既有 checkpoint 套件 22/22 证明）。
3. **`computeRisk` 单函数扩展**：分支与阈值按 `design.md` §6 实现；writeless 的 `low`/`mid`/`high` 三档必须有测试各 ≥1 例。
4. **`[CHECKPOINT]` 行尾部追加**：`land=`/`last_land=`/`artifact=`/`done=` 全部为**可选非捕获组**；旧行（无新字段）与新行都能被 `CHECKPOINT_LINE_RE` 解析；**不新增 trace 行**；既有解析该行的消费者不回归。
5. **I3 三例不回归**：正常活跃、真挂死（idle 10m 判死）、预算尾段（deadline steer）——各 1 例，证明 idle / 墙钟 / steer 不吃 `risk`。
6. **AC-009 两场景**：`wjg-w12` 形态（`[WRITE_FILE]`=4 + 37,149 B 产物在盘）判 `risk≠mid`；零落盘且无完成记录判 `risk=mid` 及以上。
7. **入参缺陷二者取一并说明理由**：修 `writes` 入参（把 `worker_file`/`bash` 计入）**或**改判据（走新的 `landed`）——`design.md` 取后者（前者会连带改计数语义与 parity 锁）。若你判断必须动入参，先停手上报。
8. 开工前若发现 `worker-mode.ts` 正被第三方编辑，停下并在「残留与未验证」报告。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：新测试条数与结果、既有 checkpoint 套件 22/22 原始输出、`wjg-w12` 重放的 `[CHECKPOINT]` 原始行（改前/改后）、I3 三例原始输出、`CHECKPOINT_LINE_RE` 新旧行各 1 例解析输出。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w4-checkpoint-invariants.test.ts
node ../../node_modules/vitest/dist/cli.js --run <既有 change-ledger / checkpoint / watchdog 相关套件，逐文件参数>
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

（HEAD 基线：`change-ledger` + `checkpoint` **22/22 全绿**、`mwds-t03` 63/63、`t04+t05+t06+t12` 50/50。列名单报基线。）

## 改动历史

- 2026-10-14 spec 阶段 RQ-4：确认 `READ_TOOLS`/`WRITE_TOOLS` 入参缺陷、`computeRisk` 三支、`checkpointAnchorMs` 公式、`wjg-w12` 为唯一可重放检查点；新增 AC-009 根因要求。
- design 阶段 DR4：给出「与账本同源的落盘信号 + `computeRisk` 扩展 + `[CHECKPOINT]` 尾字段」的落点与 I3 不变量证据。
- 依赖：T-02（账本抽取器）已落地 —— `landed` 复用的 `parseWriteFileEvents` 语义以 T-02 的产出为准。
