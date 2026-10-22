# D3 设计调研：dp3 三切（worker 澄清）+ dp2（checkpoint）执行面

- type: research
- 唯一证据文件: `.agenticdoc/mw-decision-substitution/evidence/research/design-dp3-dp2-execution-20261019.md`
- goal 锚点: `.agenticdoc/goal.md`（"Worker 执行过程中追踪 goal 一致性"）
- 超时: 30m

## 上下文（已冻结）

dp3 占全部 worker 运行的 17.4%（42/242），是最高频等人点；dp2 有 60 条 mid/high 信号。spec §4.1 把 dp3 切成 3a 事实可查 / 3b 意图需人 / 3c 已表态复用。`mode=auto` 才注入，`mode=suggest` 只落档。

关键锚点：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2681`（needs-clarification 终态）、`:3619`、`:3824`（`agent_settled`）、`packages/coding-agent/src/extensions/agent-team-loop/worker/launcher.py:593`、`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1498`（读 `## Questions` 后问人）、`:1658-1690`（checkpoint 发散升级）、`worker/worker-mode.ts:243-244`、`:3348`、`heartbeat.ts:96`、`worker/output-writer.ts:666-680`（`[CHECKPOINT]` 行）、`:505-528`（`## Questions` 段落）、`pm/triage-client.ts:132`（`readDecidePolicy`）、`:169`（spawn args）。

## 要求（逐条回答，每条带 path:line）

- **RQ-1 dp3 判定链插入点**：从 worker 判定"我需要澄清"到 exit 2 的完整调用链，指出**唯一**最合适的插入点（必须在写 `## Questions` 之前、exit 之前），并说明为什么不是其它候选点。给出插入前后的伪代码对比。
- **RQ-2 3a/3b/3c 判定规则**：可机器判定的分类信号是什么（问题文本特征 / 是否引用文件:行 / 是否可在仓库内检索到答案 / 是否命中"已表态"记录）。3c 的"已表态"来源优先级（task.md 卡 / goal.md / pm-state Decisions / 会话历史）与命中的判定阈值。无法判定时默认归 3b（上抛人）——证明这个默认是安全的。
- **RQ-3 答案注入形态**：`mode=auto` 时如何把答案交回 worker 继续执行（steer 消息 / 追加进 progress.md / 修改 task.md 头部 / 工具返回值回灌）。比较至少 3 种，给出推荐 + 理由 + 对 `needs-clarification` 计数的副作用（不能把"无人干预的 17.4%"变成"看起来 0%"）。
- **RQ-4 失败与降级**：jev 不可用 / 低置信 / 输入字段不足时的行为，如何保证"退回原来的问人路径"且不重复问、不丢失原问题。给出 `escalated_reason` 四值的具体触发条件。
- **RQ-5 dp2 checkpoint**：60 条 `[CHECKPOINT]` 行如何变成结构化输入（行格式 `output-writer.ts:666-680` 是文本，需要解析哪些字段）；`risk=mid|high` 的升级动作有哪些候选（拆 / 收窄 / 直执），哪个适合 `mode=auto`，哪个必须人。给出注入点（`pm-orchestrator.ts:1658-1690`）的精确改法与"不破坏现有 triggerTurn 语义"的验证办法。
- **RQ-6 不可破坏的现有不变量**：列出改动后必须仍然成立的 5 条不变量（例：worker 仍能正常以 needs-clarification 结束；PM 仍能读到 `## Questions` 原文；checkpoint 每任务最多升级一次；`mode=suggest` 零行为差异；goal mtime 记录不受影响），每条给可测的检查方法。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/design-dp3-dp2-execution-20261019.md`

## 写入禁止面

- 任何源码（`packages/**`）、配置（`.mw/**`）、其它 key 目录、其它 evidence 文件
- 禁止 `git add` / `git commit` / `git checkout` / `git stash`

## 交付格式

- 只写唯一证据文件；`## Q1..Q6` + `Q-answered: 6/6`；结论带 `path:line`；未确认写"未验证"。
- 不修改源码/配置；不做 git 操作。

## 验收命令

```
grep -c '^## Q' .agenticdoc/mw-decision-substitution/evidence/research/design-dp3-dp2-execution-20261019.md
```
期望 6。
