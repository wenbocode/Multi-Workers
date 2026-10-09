# T-23: `KEY_STATUSES` 跨语言机器锁（QG Q-VC-011 / Q-AC-010 的欠债）

- 波次: **5**（收口波）· 依赖: T-08（把 `pending-review` 加进两侧枚举的那张卡）、T-02（parity 测试范式）
- 写面（独占）: **新建** `packages/coding-agent/test/suite/autopilot-status-parity.test.ts`；仅当 TS 侧无法安全取真值时，才允许**另**新建 `packages/multi-workers/test_autopilot_status_parity.py`。**不得修改任何既有文件**
- AC: AC-010 · VC: VC-011
- **来源**：独立 quality-gate worker 的 Q-VC-011 / Q-AC-010（`evidence/quality-gate-report-20260926-194528.md`），判定 ⚠️ 不足

## 问题（实证）

本 key 新增了 key 状态 `pending-review`（T-08），**同时改了 Python 与 TS 两侧**：

- `packages/multi-workers/autopilot/roadmap.py:69` `KEY_STATUSES: tuple[str, ...] = (...)`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:344` `export const KEY_STATUSES = [...] as const`

但**两侧之间没有任何机器锁**：`EVENT_TYPES`（`test/suite/autopilot-event-parity.test.ts`）、配置语料（`test_autopilot_config_parity.py`）、`GATE_FRONTMATTER_FIELDS`（T-09/T-11）都有跨语言锁，**唯独 enum 没有**。QG 实测：全仓（`packages/coding-agent/test` + `packages/multi-workers`）无任何断言两侧 `KEY_STATUSES` 相等的测试。

附带疑点：**T-08 回执里声称存在 "machine-checked subset proof"**，QG 在全仓**定位不到**对应测试/断言。本卡必须核实这条声称（见交付物 4）。

## 交付物

1. **新测试文件**，以**真子进程 dump** 取 Python 真值（照 `autopilot-event-parity.test.ts` 的范式：`spawnSync(resolveRagPython(), ["-X","utf8","-c", <dump>, MULTI_WORKERS_DIR])`）：
   - dump `autopilot.roadmap.KEY_STATUSES`（**保序**）与 `autopilot.conductor._DEP_SATISFIED`（排序）。
   - **fail-closed**：解释器缺失 / 子进程失败 / 任一侧常量缺失 ⇒ 硬失败。**禁止** `skipIf` / `if (!x) return;` 这类空心化写法。
   - **禁止**把 Python 侧常量手抄成字面量副本（那就不是锁了）。
2. 断言（逐条，缺一不可）：
   - **(a) 逐值同序相等**：Python `KEY_STATUSES` 与 TS `KEY_STATUSES` 必须是 **identity（含顺序）**，不是集合相等。
   - **(b) Python 内部一致性**：`_DEP_SATISFIED ⊆ set(KEY_STATUSES)`；`"pending-review" not in _DEP_SATISFIED`；`"closed-legacy" in _DEP_SATISFIED`。后两条锁住 T-08/T-07 的语义选择（`closed-legacy` 会像 done 一样解锁依赖、`pending-review` 不解锁不派发），防回归。
   - **(c) 镜像确实被消费（非死常量）**：对 TS 侧 `status-model.ts:556` 的校验路径做一次行为断言 —— 合法值被接受、闭集外的值被拒。仅"两个常量一样"不足以证明镜像有用。
3. **反向对照（非空洞证明，≥3 条）**：逐条临时破坏 ⇒ 必须红，恢复 ⇒ 必须绿。例如：只改一侧枚举增删一项 / 把顺序对调 / 把 `pending-review` 塞进 `_DEP_SATISFIED`。逐条贴原始输出。
4. **核实 T-08 的 "machine-checked subset proof" 声称**：定位它指向的具体文件与断言；给出定位命令与结果。**若不存在**，明确判定为**假声明**（附 grep 证据 + 该声称在回执中的原文行号），不要替它补一个再宣布"已存在"。
5. 回执给 `[VERIFY]` 行，至少含：`equal=true count=5`、`ordered=true`、`dep_satisfied=2`、`pending_review_not_dep=true`，且这些值**全部实测**（不得硬编码字面量 —— 见 P-023）。

## 契约（不得重定义）

- **只允许新增上述测试文件**；不得改生产代码、不得改既有测试、不得改语料/锁。
- 若发现两侧**真不一致**（例如顺序或值不同）⇒ **停下并在回执里报告差异**，**不许**自行改序/改值/放宽断言让它变绿。PM 会裁定修哪一侧。
- 断言强度不得低于上述 (a)(b)(c)；不得用集合相等代替保序相等。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-status-parity.test.ts`
- 并贴出该测试打印的 `[VERIFY]` 行。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t23-status-parity-lock/report.md`（含：新增文件、逐条断言、≥3 反向对照的前后原始输出、T-08 声称的核实结论、残留风险）。
