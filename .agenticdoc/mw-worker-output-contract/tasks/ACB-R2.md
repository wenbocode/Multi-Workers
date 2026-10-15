# ACB-R2 · AC-010(b) 研究类探针 2（checkpoint 机器判据）

- Key: mw-worker-output-contract
- type: research

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「项目级目标对齐」）。
- 本任务是 T-08 部署后的 **AC-010(b) 研究类验证探针**：验证新 bundle 下受判产物能拿到「标题判定 + 机械段自动补齐」，从而 `exit=0`。
- 线索起点：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:101`（`formatMachineCheckpoint` 定义附近）。

## 写入允许面

- `.agenticdoc/mw-worker-output-contract/evidence/acb-r2-notes.md`（唯一证据文件）

## 写入禁止面

其余一切路径。禁止修改代码、禁止无参全量 vitest/pytest。

## 要求

1. 只读调查：定位 `worker/output-writer.ts` 里的 `formatMachineCheckpoint`，概括它产出的机器行包含哪几个字段（elapsed/reads/writes/risk 等），用 2-3 句中文说明。
2. 在 `evidence/acb-r2-notes.md` 记录结论（唯一证据文件，3-6 行）。
3. 不要修改任何代码。

## 交付格式

`report.md` 四段齐全：`结论` / `证据`（实际行号 + 一段示例机器行）/ `残留与未验证` / `上下文来源`。不要写 `## Questions` 段。

[VERIFY] ACB-R2 探针交付：exit=0。
