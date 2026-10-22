# D5 设计调研：结果关联 + phase 报告 + 签收门禁 + `dp apply` 护栏

- type: research
- 唯一证据文件: `.agenticdoc/mw-decision-substitution/evidence/research/design-association-report-signoff-20261019.md`
- goal 锚点: `.agenticdoc/goal.md`（"项目级目标对齐（goal.md）"、"PM 模式（编排）"）
- 超时: 30m

## 上下文（已冻结）

spec §6.2 结果关联：`decision:` 头行注入 task.md → PM 回收终态时追加 `settle` 行，6 种终态映射。spec §7.1/§7.2：phase 末自动报告 + done 强制签收（复用现成 gate 规则），签收文件含 `conclusion:` / `promote:` / `demote:`，PM 不得写签收文件，`dp apply` 在 agent 会话内拒绝。

关键锚点：`pm/ui-bridge.ts:1376-1379`（task.md 头行组装）、`shared/run-store.ts:29-56`（run.json 字段与终态）、`:113-115`（output.md run marker）、`pm/pm-orchestrator.ts:525-532`（model-error kind）、`:538-542`（kind 白名单）、`:645-664`（recordDispatchAlarm）、`:666-687`（WRITE_SCOPE 过滤器）、`.agents/skills/agentic-task/core/scripts/advance_phase.py:69-95`（GATES）、`:191-289`（check_gate）、`:220-227`（content_match）、`:345-351`（Phase 行读取）。

## 要求（逐条回答，每条带 path:line）

- **RQ-1 头行注入**：`decision:` 行加在 task.md 头部的精确位置与格式（单行、可被现成解析器忽略）；注入时机（frontmatter 生成之后还是之内）；头部解析器（`run-store.ts:168-172` 之类）会不会因此报错——证明过程。
- **RQ-2 settle 触发点**：PM 回收 worker 终态的现有代码路径，指出**唯一**最合适的 settle 追加点；6 种终态映射的判定依据（`run.json.status` / `exit` / output.md 段落）；`lost` 与 `needs-clarification` 的 pending 保持规则；重复 settle 的幂等（同一 decision_id 只认最后一条 settle，还是拒绝第二条）。
- **RQ-3 报告生成**：报告骨架的各节数据来源（全来自 `fold` 结果？）；生成时机的准确判据（"phase 已推进且上一 phase 无报告"，锚点 `advance_phase.py:345-351`）；写入路径白名单；`N<5` 的判定与"数据不足"文本；`suggest:` 行的机器可读格式。
- **RQ-4 签收文件格式与解析**：`sign-*.md` 的完整格式（`conclusion:` / `promote:` / `demote:` / P0 已开清单 / 正文）；多行的解析容错（缺 conclusion、拼错 dp id、P0 漏列）；`dp apply <file>` 的处理顺序（先全量校验再原子写，还是逐条写）。
- **RQ-5 门禁规则**：`GATES["done"]` 追加两条规则的具体 Python 代码（沿用 `glob_has_files` + `content_match`）；现有 done 门禁已有哪些规则（列出）、新规则会不会与既有 `PASS` 规则冲突；门禁失败时的人读提示怎么写。
- **RQ-6 `dp apply` 护栏**：如何检测"当前在 agent 会话内"（可用环境变量：`PI_WORKER_TASK` / PM 会话标记 / 其它——需要在代码里确认已存在的变量名与设置点）；检测到后行为（exit 2 + 提示）；PM 写禁止面如何接（`pm-orchestrator.ts:666-687` 的过滤器是否覆盖 `evidence/review/**`）；给出两层防护分别能挡什么、不能挡什么（含绕过方式）。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/design-association-report-signoff-20261019.md`

## 写入禁止面

- 任何源码（`packages/**`）、配置（`.mw/**`）、其它 key 目录、其它 evidence 文件
- 禁止 `git add` / `git commit` / `git checkout` / `git stash`

## 交付格式

- 只写唯一证据文件；`## Q1..Q6` + `Q-answered: 6/6`；结论带 `path:line`；未确认写"未验证"。
- 不修改源码/配置；不做 git 操作。

## 验收命令

```
grep -c '^## Q' .agenticdoc/mw-decision-substitution/evidence/research/design-association-report-signoff-20261019.md
```
期望 6。
