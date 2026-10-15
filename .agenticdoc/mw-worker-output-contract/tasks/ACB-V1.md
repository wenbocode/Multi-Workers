# ACB-V1 · AC-010(b) 审查类探针 1（T-13 自检回合实现审查）

- Key: mw-worker-output-contract
- type: review

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」）。
- 本任务是 T-08 部署后的 **AC-010(b) 审查类验证探针**：验证新 bundle 下受判产物（审查报告）能拿到「标题判定 + 机械段自动补齐」，从而 `exit=0`。
- 审计目标：`worker/worker-mode.ts:2584`（`function settleOrSelfCheck` 定义附近）

## 写入允许面

- `.agenticdoc/mw-worker-output-contract/evidence/acb-v1-audit.md`（唯一证据文件）

## 写入禁止面

其余一切路径。禁止修改代码、禁止无参全量 vitest/pytest。

## 要求

1. 审计 `settleOrSelfCheck`：确认 (a) 自检回合条件包含 `hasDeliverableEvidence(taskDir, lastAssistantText).delivered`（writeless）或 `true`（write 角色）；(b) `selfCheckSent` 每进程一次；(c) 未交付走 `finishSuccess`（no-product 裁决）。逐条给 `PASS/FAIL`。
2. 产物落 `evidence/acb-v1-audit.md`（唯一证据文件，含逐条结论）。
3. 不要修改代码。

## 交付格式

`report.md` 五段齐全：`结论` / `证据`（逐条 PASS/FAIL 原始断言）/ `残留与未验证` / `上下文来源` / `未覆盖面声明`。不要写 `## Questions` 段。

[VERIFY] ACB-V1 探针交付：exit=0。
