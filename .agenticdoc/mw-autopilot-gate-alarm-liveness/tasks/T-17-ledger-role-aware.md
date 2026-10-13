# T-17 — 回收契约按角色分流（writeless 角色不再"量错对象"）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-013（C-36a/b/c）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md` AC-013、§0.1 ①；`design.md` §2 D10；`plan.md` §2 批次

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（worker 产物必须自带可信状态；假信号与漏信号都会污染 PM 判断）。
- 已核实锚点（自行复核）：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:5`（每次成功 `write`/`edit` 追加一行 `[WRITE_FILE]`）、`:12`（`diffLedger` 调和 `declared ? recorded`；`extra` = 声明了但没记录）、`:19`（**trace 里 ZERO 个 `[WRITE_FILE]` 的迁移语义**）、`:45`（含全角标点等"不可解析"路径 presently 是 `malformed`、**warn-only、从不参与判定**）、`:64`（`WRITE_FILE_EVENT = "[WRITE_FILE]"`）、`:68`（`formatWriteFileEvent`）、`:72`（best-effort 追加）。
  - `.../worker/output-writer.ts:52`（报告声明了文件但 trace 零写入事件的处理）、`:130`（"有 `[WRITE_FILE]` 事件 + 非空声明"= *unjudgeable*）、`:133`（`readTerminalGaps`）、`:153`（unjudgeable 时用 `ledger.declared`）、`:185`（报告声明过但 trace 从未记录的文件）。
- **本卡要修的三类实测缺陷**（本 key 自曝，PM 已用决定性检验判定为假阳性）：
  - **C-36a 过判**：writeless 角色（`research`/`review`）的报告天然充满**被读取**的路径名 ⇒ 被当作写入意向。实证：`mwgal-t08-drq4-auto-approve` 的"未记录写入"清单是 `l3-verdict.txt, auto-decisions.jsonl, gates.pending` —— 三者都是它普查时**读过**的路径并集，其中 `gates.pending` **磁盘上根本不存在**（幽灵名）。
  - **C-36b 漏判**：交付物写在 taskDir 之外时对账本**完全不可见**。实证：本 key 的 4 份 RQ + 4 份 DRQ 证据文件都真实存在（其中 DRQ 三份 38,778 / 32,706 / 74,196 B），而它们的 `trace.log` 里 `evidence/research` 出现 **0 次**；对应 Exit Reason 全是 `writes=none`（累计 **8 例**）。
  - **C-36c 路径污染**：账本把**未展开的 shell 变量**当路径记录（如 `path=$dir`、`path=$src`、`path=$env:TEMPxxx`），既污染证据又无法与声明匹配。
- **PM 的判定方法学（本卡须固化为回归语料）**：复核"未记录写入"看三件事 —— ① 目标文件 **mtime 是否落在 worker 运行窗内**；② `trace.log` 是否有对应事件；③ 文件名**是否真实存在**。T-08 三项全否 ⇒ 假阳性。

## 要求

1. **角色分流（C-36a）**：writeless 角色（任务 `type:` 为 `research`/`review`）只把**任务声明的唯一交付物**当写入意向；报告中出现的其他路径一律按**读取引用**处理，不得进入 `declared` 集合。要求给出：角色从哪里读（`task.md` 的 `type:` 字段）、如何在账本侧拿到它、以及若角色不可判定时的 fail-safe 方向（**不得**因为拿不到角色就退回"过判"）。
2. **覆盖 taskDir 之外的交付物（C-36b）**：writeless 角色的交付物写入必须能被对账（当前 `evidence/research` 在 trace 里 0 次可见）。要求：至少让"声明的唯一交付物"即使写在 taskDir 之外也进入对账（记录 + 可判定），并保证"真实越界写入仍为红"（不得用放宽来换取通过）。
3. **路径卫生（C-36c）**：未展开变量（`$`/`${...}`/`%VAR%` 形态）与不可解析路径一律归 `malformed`，且**不得**参与 `declared`/`recorded` 任一集合的判定；`malformed` 的计数与样例必须**可见**（warn 通道），但不得导致 fail。
4. **不得放宽判据（P-03）**：真实"声明了但没记录"的写入仍必须报红（含 coding 角色）；本卡不得改变既有 `declared`/`recorded`/`extra` 的核心语义，只做角色分流 + 覆盖 + 卫生。
5. **回归语料（必须内建）**：
   - 假阳性语料：research 报告正文提到 `l3-verdict.txt` / `auto-decisions.jsonl` / 一个**不存在**的路径名 ⇒ **零 findings**（直接对应 T-08 实例）；
   - 真阳性语料：coding 角色真实越界写入 ⇒ 仍报红；
   - 变量语料：`path=$dir`、`path=$env:TEMPfoo.py` ⇒ 归 `malformed`、不构成写入证据；
   - taskDir 外交付物语料：writeless 交付物写在 taskDir 之外 ⇒ 可对账（不再 `writes=none` 式不可见）。
6. 报告须逐条给出：旧行为 vs 新行为的对照，以及对既有测试期望的必要更新（仅允许因新语义而必须改的期望，逐条说明理由）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- 新增：`packages/coding-agent/test/suite/mwgal-t17-ledger-role-aware.test.ts`
- 既有 TS 测试中与账本/交付物对账直接相关的用例（仅改因新语义必须改的期望/夹具，须逐条在报告说明）

## 写入禁止面

- `packages/multi-workers/**`（T-12 正在改 `conductor.py`；`card_audit.py` 不在本卡面内）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/**`、`pm/**`（属 T-10/T-10b/T-14）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t17-ledger-role-aware.test.ts test/suite/worker-write-intent.test.ts test/suite/worker-dispatch-guard.test.ts`

（若上列既有测试文件名不存在，改用实际存在的同类测试并在报告中注明。）

## 改动历史

（填写：角色如何取、`declared` 语义演化、taskDir 外覆盖的落点、`malformed` 的判定与可见性；说明被否决的替代方案。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
