# T-17b — 基础设施写入不得归因到 worker（C-36 第 4 类）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-013（C-36 第 4 类：系统自身写入误归因）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/tasks/T-17-ledger-role-aware.md`（C-36a/b/c/d 已修）；
      T-12 终态实证（见下）、`workers/mwgal-t17-ledger-role-aware/report.md` 的"已知残留"条

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（worker 产物自带可信状态；账本不得把系统行为算成 worker 越界）。
- 已核实锚点（自行复核）：
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts:12`（`diffLedger` 调和 `declared ? recorded`，`extra` = 声明了但没记录）、`:19`（trace 零 `[WRITE_FILE]` 的迁移语义）、`:45`（`malformed` warn-only）、`:64/:68`（`WRITE_FILE_EVENT` 与格式化）、`:72`（best-effort 追加）。
  - `.../worker/output-writer.ts:52/:130/:133/:153/:185`（报告声明 vs trace 记录的判定链）。
- **实证（PM 已做决定性检验）**：worker `mwgal-t12-stage-close-auto` 的终态被扣"未记录写入：**`_workers.parallel`**"。三项检验：① `trace.log` 里 `_workers.parallel` 命中 **0 次**；② 队列文件 mtime = **19:23:30 本地**，落在该 worker 运行窗（**19:07–19:20 本地**）**之后**；③ 文件真实存在。⇒ 这是**调度器/launcher 自己写的全局队列**，与 worker 无关。
- 语义要点：`_workers.parallel`、`_index.parallel`、`run.json`、`trace.log`、`serve.meta`、timeline/ledger 等**基础设施文件由框架写**，其 mtime 天然落在 worker 运行窗内 ⇒ **mtime 窗口无法区分归属**，必须用**所有权白名单**判定。

## 要求

1. **基础设施所有权白名单**：列出由框架自身写入的路径/文件名集合（至少：`_workers.parallel`、`_index.parallel`、各 worker 的 `run.json`、`trace.log`、`output.md`、`report.md`、`serve.meta`、timeline/ledger 文件），这类路径**不得**进入 coding 角色的 `extra`（"声明了但没记录"）判定。
2. **不得静默丢弃**：被判为基础设施写入的项要以**可见但非 falsifying** 的方式留痕（warn 通道，形态与 T-17 已落的 `malformed` 一致，例如 `## Ledger Infra` 段 + 既有 `[FLOW]` 追踪行），报告里要能看见"这些是框架写的"。
3. **不得放宽真实越界（P-03）**：coding 角色对**非基础设施**路径的越界写入仍必须报红（回归语料：`packages/coding-agent/src/out-of-scope.ts` 仍出现在 `extra`）。
4. **不得回退 T-17 成果**：C-36a（writeless 角色窄清单）与 C-36b（`<key>/evidence/**` 交付物通道 + 新鲜度）语义保持；无 `role` 时行为与 T-17 之后一致。
5. **回归语料（必须内建）**：
   - `_workers.parallel` 出现在候选集 ⇒ **零 findings**（直接对应 T-12 实例）；
   - `run.json`/`trace.log`/`serve.meta` 出现在候选集 ⇒ 零 findings 且进 infra 通道；
   - 非基础设施越界路径 ⇒ 仍报红；
   - T-17 的 writeless 语料（`l3-verdict.txt`/`auto-decisions.jsonl`/幽灵名）⇒ 仍零 findings（防回退）。
6. 报告须给出"白名单条目 → 由谁写 → 证据"的对照表（每条给出代码位置或运行期观察）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
- 新增：`packages/coding-agent/test/suite/mwgal-t17b-ledger-infra-writes.test.ts`
- 既有 TS 测试中因本卡行为必须更新的期望（逐条说明；不得改弱断言）

## 写入禁止面

- `packages/multi-workers/**`（T-15 正在改 `conductor.py`/`mw.py`）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/**`、`pm/**`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t17b-ledger-infra-writes.test.ts test/suite/mwgal-t17-ledger-role-aware.test.ts test/suite/mwds-t02-write-intent.test.ts`

## 改动历史

（填写：白名单的判定方式与来源、infra 通道的可见落点、与 C-36a/b 的交互、被否决的替代方案（如"按 mtime 窗口判定"为何不成立）。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
