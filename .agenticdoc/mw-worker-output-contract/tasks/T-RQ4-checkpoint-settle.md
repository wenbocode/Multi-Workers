# T-RQ4: 检查点判据与 settle 前自检的插入点（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（Key Constraints 的「Worker 超时看门狗：activity watchdog + 墙钟兜底 + **30 分钟收敛检查点**（`[CHECKPOINT]` 机器判据 + worker 自评）」）。
- 本 key 的 spec：`.agenticdoc/mw-worker-output-contract/spec.md` —— 相关条目 §1.5 P5、§1.6 S2/S3/S5、§3 AC-004/AC-005/AC-009、§1.7 第 1 与第 4 条。
- 已知起点坐标（**只是起点**）：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2745`（`exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2`）、同文件 `:2728`（`[WRITE_FILE]` 事件与 declaration gap）、`:2758`（`unjudgeable write(s)`）。
- 背景事实（已复核）：writeless 角色（review/research）的检查点行形如 `[CHECKPOINT] elapsed=1800s reads=111 writes=0 uniq_targets=0 repeat_top=16 risk=mid`，而 `writes`/`uniq_targets` 对这类角色**恒为 0**（写文件走 `worker_file`，不计入计数）⇒ 已完成并落盘的审计被判 `risk=mid`（`wjg-w12-negative-space-audit`，37,149 B 产物已在 `17:32:12` 落盘）；另一 key 的 5 条 trace 则 0 条 `[CHECKPOINT]`（run 只有 7~8 分钟）。输出段契约的判定发生在 settle **之后**，worker 收尾前无从自查（6 次实例）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、全量 `./test.sh`。

## 要求

1. **`[CHECKPOINT]` 的完整生成链**：触发条件（时间/事件）、计算 `elapsed`/`reads`/`writes`/`uniq_targets`/`repeat_top` 的代码位置与各自的数据来源、`risk` 的判定规则（`low`/`mid`/`high` 的确切条件）、以及 `triggerTurn` 升级 PM 的路径。逐条 `文件:行号` + 原文片段。
2. **writeless 角色的「已落盘」可用信号**：列出可机械取得的信号与其代码位置（trace 事件、产物文件存在性、`progress.md` 完成记录、`worker_file` 调用记录、`[WRITE_FILE]`/`unjudgeable` 行），并指出每条信号对 writeless 角色**是否真的可得**（逐条判定，不许概括）。
3. **settle 路径的顺序**：从 agent 收尾到 `output.md` 落盘、到契约判定、到 `exitCode` 的完整顺序（含 `evidence.delivered` 的语义与来源），并指出「自检 + 自动补齐」可以插入的**具体位置**（给 `file:line` 区段与插入点前后各 3~5 行原文）。这是本 RQ 的核心交付。
4. **机械段的可得事实**：框架在 settle 时手上有什么可用于生成 `## 上下文来源`（例如 `task.md` 里的 `card_path`/`card_sha256`、已读文件清单、写事件）；逐条给出字段名与读取位置。
5. **现有测试清单**：与检查点 / 收敛 / settle 出口 / `output.md` 生成相关的测试文件 + 用例名 + 断言要点（vitest 与 pytest 都查），并指出哪些用例会在判据改动后翻转。
6. **与看门狗三段式的耦合**：改动 `risk` 判据会不会影响 activity idle（10 分钟）与墙钟兜底（默认 60m）两段的触发；给出代码证据（不是判断）。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq4-checkpoint-settle-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。

## 交付格式

- `## 0. 结论先行`（≤6 条）→ `## 1…N` 逐问作答（第 3 问必须给可直接落 tasks 的插入点清单）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；未找到写「未找到（命令 + 输出）」；**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`；声明工具与方法边界。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
