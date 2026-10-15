# T-07 · 跨任务矩阵用例补齐 + 基线区分脚本（收口，必须晚于 A+B）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「Worker 执行过程中追踪 goal 一致性」）——五个切面各自修完后，必须有一处**跨切面**的可复跑判据把 AC 串起来，否则「五处都绿」只是局部断言。
- 本卡是收口卡，**前置条件 = 批次 A（T-01/T-03/T-06）与 B（T-02/T-04/T-05）全部 done 且 PM 复核通过**。开工前先读各卡的 `output.md` 与 `evidence/`，**不要重跑它们的实现**。
- 设计落点（`design.md` §10 验证计划）：
  - **AC-010(a)** 语料复跑：`evidence/scripts/recovery-contract-corpus-stats.py`（已落盘，可复跑）；基线 145/433 = 33.5%（整篇别名）与 35/433 = 8.1%（标题别名），快照 n 已漂到 437（整篇 34.8% / H2 8.5%）。
  - **AC-010(c)** 110（后测 111）例的处置**逐条**给出（被自动补齐救回 / 仍失败及原因），不得只报总数；分类见 `evidence/recovery-contract-flip-disposition-20261014.txt`（`mechanical-only` 8 例 / `substantive` 103 例）。
  - **AC-005 重放**：8 例 `mechanical-only` 取 3 例的**盘上现存文本**，断言 `exit=2 → exit=0`。
  - **AC-017 四段判据**：(a) 13/55/319/336 字符 here-string ⇒ 0 行 `[WRITE_FILE]`；(b) 两个 .NET API 各 1 行；(c) `allow=2 deny=0` 且 `Write-Output a <term> --glob x` 产 0 候选；(d) `unjudgeable` 由有效事件数派生 + 12 个既有用例不回归。
  - **基线区分**：先跑 `baseline-vitest.json` 覆盖的 24 个文件取 **5 红**（`agent-team-loop-worker-file-tool.test.ts:177/:285`、`agent-team-loop.test.ts:6381`、`mwds-t02-write-intent.test.ts:345`、`mwds-t23-cutover-recheck.test.ts:295`），再跑改动后同集合 ⇒ **只认「新增红 = 0」**。
- R8（**硬约束**）：HEAD 既存红 **5 个**与 settle 层 **3 处预期内改动**必须分开计量，不得把 HEAD 既存红算作本次引入。

## 写入允许面

- `packages/coding-agent/test/suite/mwoc-matrix-*.test.ts`（新建）
- `.agenticdoc/mw-worker-output-contract/evidence/`（新增矩阵结果与基线对照产物）

## 写入禁止面

其余一切路径。特别地：**不得改任何 `packages/*/src/**`**（实现已由批次 A/B 冻结；发现实现缺陷时**只在报告里登记并停手上报**，不要就地修）；`test/suite/output-recovery-contract.test.ts`、`test/suite/dispatch-recovery-terminal.test.ts`（T-05 的预期内改动文件）只读；`evidence/research/**` 与 `evidence/scripts/**` 只读（可执行，不可改）；`.agenticdoc/_pitfalls.md`、`.agenticdoc/_framework-reflect.md`、`achieved.md` 归 T-09 写面，**只读**。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **跨切面矩阵用例**（新建 `mwoc-matrix-*.test.ts`）：至少覆盖 AC-005（3 例重放）、AC-001（8 例矩阵的跨入口一致性：判定入口与候选集入口对同一文本给同一结论）、AC-017 四段。每条断言注出对应 AC 编号。
2. **候选集 × 判定的组合**：构造「只写 `report-<slug>.md`」「`report.md` + slug 并存」「只有 `output.md`」三形态，断言受判文件选择与判定结论一致（锁住 T-05 的两个入口同源）。
3. **基线对照脚本化**：把「24 文件基线 → 改动后同集合」的对照落成可复跑命令（脚本或文档化命令行），产物写 `evidence/`：HEAD 5 红逐条列出 + 改动后新增红 = 0 的结论。**新增红 ≠ 0 ⇒ 停手上报**。
4. **AC-010(a)/(c) 产物**：语料两数（改动前后 × 整篇/标题 = 4 个数）+ 命令；110/111 例逐条处置表（被补齐救回 / 仍失败及原因）落 `evidence/`。
5. **不重跑、不修改实现**：发现问题只登记（含 `file:line` 与最小复现），交回 PM。
6. `git diff --stat` 收尾只应含允许面文件。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：新测试条数与结果、24 文件基线与改动后的逐文件红绿对照、HEAD 5 红名单、新增红 = 0 的声明、语料 4 个数、110/111 例处置表摘要（总数 + 分类 + 落盘路径）。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-matrix-.test.ts   # 逐个新文件给参数
# 基线区分：24 个文件逐个给参数（见 evidence 里的基线清单）
npx tsgo --noEmit
git diff --stat
```

## 改动历史

- 2026-10-14 design 阶段 DR6：实跑 24 个 vitest 文件 / 558 用例，登记 HEAD 5 红与全绿基线；语料快照 n=437（整篇 34.8% / H2 8.5% / flip 111 = 8 + 103）；落 4 份可复跑产物。
- 依赖：批次 A（T-01/T-03/T-06）+ 批次 B（T-02/T-04/T-05）全部 done。
