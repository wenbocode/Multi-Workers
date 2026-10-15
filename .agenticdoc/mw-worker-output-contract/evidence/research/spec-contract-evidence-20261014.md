# Research: worker 输出面三契约的现状与实例证据（spec）

## 决策问题

支撑 spec 的哪些决策：
- §1.4 范围取舍（本 key 收哪几条台账条目、哪些分流）
- §1.6 修法选择（为什么是「改判定 + 增通道 + 修账本」，而不是「改提示」或「给角色加 write」）
- §3 AC 的期望值与反向对照片（每条 AC 的「当前实现必然失败」用例从哪来）

## 调研方法与出处

- **直接读取被审对象**（均为已落盘的 worker 工件，非二手转述）：
  - 另一窗口 key `mw-write-face-guard` 的 5 个 worker：`workers/<task>/run.json`（`status`/`exit`/`run_id`）、`output.md`（首行 `<!-- mw-run: … status=… -->` 与标题列表）、`report.md`、`trace.log`（`[TOOL]`/`[WRITE_FILE]`/`[WRITE_SCOPE]`/`[CHECKPOINT]` 行）、`worker.log`；`evidence/research/*.md` 的字节数与 mtime；`tasks/*.md` 的 `## 交付格式`。
  - 本仓 key `mw-worktree-junction-guard` 的 `wjg-qg-evidence-closure` / `wjg-w12-negative-space-audit` / `wjg-w15-delta-adversarial` 同类工件。
- **源码坐标核对**（读源码，不猜）：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts`（`RECOVERY_SECTIONS` / `RECOVERY_TYPE_SECTIONS.review` / `RECOVERY_SECTION_ALIASES` / `containsAlias`）、`worker/worker-mode.ts`（`:723`、`:1604`、`:1624`、`:2199` 写面；`:2368-2388` 事件记录；`:2745` `exitCode`；`:2776` questions）、`worker/worker-file-tool.ts`（`:42` `WORKER_FILE_NAME_RE`、`:63` 拒绝文案、`:82` 事件）、`shared/change-ledger.ts`（`:116`/`:123`/`:135`）、`.mw/dispatch.yml`（仅 5 行，只声明 role→model）。
- **计数与字节校验**：伪 `failed` 块整目录递归计数（Python，非 `Select-String`）；产物与提升副本的 sha256 比对；`[CHECKPOINT]` 行计数。
- 时间：2026-10-14，`mw-write-face-guard` 的两个 run 批次（`17:10:27Z` 与 `23:45:43Z`）。

## 发现

### F1 输出段契约：单批 3/5 命中，补录成为事实标准

| worker | `status` / `exit` | `output.md` 标题 | 回读缺失段 | 实质产物 |
|---|---|---|---|---|
| `wfg-rq2-enforcement` | `needs-clarification` / 2 | 澄清模板四段（2,658 B） | `残留与未验证, 上下文来源` | `evidence/research/spec-write-face-enforcement-20261014.md` 32,053 B |
| `wfg-rq3-safety` | `needs-clarification` / 2 | 澄清模板四段（3,745 B） | `残留与未验证, 上下文来源` | `…spec-write-face-safety-20261014.md` 44,793 B |
| `wfg-rq-d2-runtime-guard` | `needs-clarification` / 2 | 澄清模板四段（2,907 B） | `上下文来源` | `…design-runtime-guard-20261014.md` 30,724 B |
| `wfg-rq-d1-glob-intersection` | `done` / 0 | 交付模板 | — | 经 PM 提升（`design-glob-intersection-20261014.md`） |
| `wfg-rq1-write-face-sources` | `done` / 0 | 交付模板 | — | `…spec-write-face-sources-20261014.md` 50,544 B |

该窗口 PM 的兜底与本仓同源：三个任务目录的 `report.md` 标题为 `# wfg-rq2-enforcement — report（PM 补录，收口 recovery-incomplete）`，正文补 `## 残留与未验证` / `## 上下文来源`。五张卡的 `## 交付格式` 都非空 ⇒ **卡面告知不足以修复本项（第 5 次确认）**。

### F2 写面分层：`evidence/**` 被允许，卡住的是通道

- 壳层/default 写面 = `taskDir + <key>/evidence/**`，由任务 `write_scope:` 头收窄（`worker-mode.ts:723`、`:1604`、`:1624`、`:2199`）。
- `worker_file` 只认 basename `progress.md | report.md | report-<slug>.md` 且强制任务目录（`worker-file-tool.ts:42`、`:63`）。
- research/review 角色**没有** `write` 工具：`[TOOL_ERR] … write Tool write not found` 在 `wfg-rq-d1`、`wfg-rq2`、`wfg-rq3` 各出现 1 次。
- 结果：`wfg-rq1/rq2/rq3/rq-d2` 用壳层（PowerShell here-string + `python -`）直写 `evidence/**` 成功；`wfg-rq-d1` 退回任务目录 → PM 原样提升（两处 41,612 B、sha `8E4B5A418D99512B` 相同）。

### F3 变更账本双向失真

- 误报（`wfg-rq2`、`wfg-rq3`）：`[WRITE_FILE]` 落的是命令正文片段（`path=` + 反引号 + `:1175`、`…:1184`；`, .agenticdoc/_aut + opilot)`），各 2 行；其前一行 `[WRITE_SCOPE] … pattern=redirect target=` 已判 `allow-unknown`（target 为空）。
- 漏报（`wfg-rq1`）：真实写了 50,544 B，`[WRITE_FILE]` **0** 行。
- 机制位置：`worker-mode.ts:2368-2388`（两个来源均无形状校验）+ `change-ledger.ts:116/123`（行格式）/`:135`（读取正则正确）。

### F4 检查点判据未复现，但账本问题连带影响其修法

- `mw-write-face-guard` 5 条 trace **全 0** 条 `[CHECKPOINT]`（run 时长 7~8 分钟，未到 30 分钟阈值）⇒ FW-007 在该 key 未复现。
- 反向对照（本仓）：`wjg-w12-negative-space-audit` 的 `[CHECKPOINT] … writes=0 uniq_targets=0 repeat_top=16 risk=mid`，而 37,149 B 产物已在 `17:32:12` 落盘。

### F5 伪 failed 风暴不普遍

- `mw-write-face-guard` 整 key 目录递归计数 `exited without writing output` = **0**；本仓同形态曾 20 / 6 / 17 块 ⇒ 触发条件与「回读被渲染的时刻」相关，不是 worker 侧必然产物（该条按台账分流到 `mw-dispatch-reliability`）。


### F6 终态回读推送的范围缺口（用户 2026-10-14 指定并入；来源 = 既有报告 + 探针）

- 来源报告：`.agenticdoc/_scratch/evidence/readback-push-scope-gap-20261014.md`（14,191 B，sha256 `A55ACD7DF8EB70D9…`），已字节纯净并入本 key `evidence/readback-push-scope-gap-20261014.md`；探针 `readback-push-scope-repro-20261014.mts`（5,197 B）同法并入。
- 机制：`pm/pm-orchestrator.ts:1436` 的 `notified.add(entry.taskKey)` 早于 `:1440` 的 owner 门禁 `continue` ⇒ 非 watch key 的终态行被记账为「已投递」。
- 证据强度：合成探针（真实 `startWorkerPollLoop`，`P3` 缺陷 + `P4` 同 key 对照通过）为**决定性**；本会话自然实验 11/11 吻合（11 个终态 → 7 条回读）。
- 与 P1~P5 的关系：同为「PM 吸收 worker 结果的入口面」，但错在投递而非内容判定 ⇒ 单独一条 S6 + 独立 AC（011/012/013）。
## 结论 → 决策映射

| 结论 | 支撑的 spec 决策 |
|---|---|
| F1（3/5 + 补录重造 + 卡面告知无效） | §1.5 P1；S1（判定改结构）+ S3（机械段自动补齐）；AC-001/002/003/004/005 的期望值与语料 |
| F2（`evidence/**` 已在允许面、`worker_file` 是瓶颈、角色无 `write`） | §1.4 排除「给角色加 write」（GC-5）；S4（放宽通道路径域）；AC-006/007 |
| F3（误报 + 漏报共存，机制在事件记录处） | §1.5 P4；S5（形状校验 + `unjudgeable`）；AC-008；并决定 FW-007 的修法须后置（§1.7 第 4 条） |
| F4（writeless 判据失真） | §1.5 P5；S5 的判据部分；AC-009 |
| F6（回读推送记账早于 owner 门禁；探针决定性 + 11/11 自然实验） | §1.4 纳入声明；§1.5 P6；S6；AC-011/012/013；并决定该条的验收以探针转仓库用例为闸门（P3 必须翻转） |
| F5（伪 failed 不普遍） | §1.4 范围排除 FW-003（分流 `mw-dispatch-reliability`） |
| 6 次实例的缺失段分布（3 次唯一缺机械段、2 次缺实质段） | S1+S3 处理机械段、S2 处理实质段；AC-004 与 AC-005 的分工 |

## 未覆盖 / 待 design 阶段调研

- 历史语料统计（FW-001 提到的 99.4% / 87.2%）的实现入口与复跑方式未知 ⇒ AC-010 的可行性待定。
- `output.md` / `evidence/**` / trace 事件的全部消费者清单（PR 侧 declaration gap、PM 校验、widget 渲染）未穷举 ⇒ 落在 design 阶段的并行调研。
- 壳层写目标抽取器的实现位置与完整匹配规则未读 ⇒ 同上（AC-008 的夹具已知，规则待定）。
