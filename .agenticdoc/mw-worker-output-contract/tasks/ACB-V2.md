# ACB-V2 · AC-010(b) 审查类探针 2（TS 侧 S2 注入审查）

- Key: mw-worker-output-contract
- type: review

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「phase 门禁」「复用 built-in extension 机制」）。
- 本任务是 T-08 部署后的 **AC-010(b) 审查类验证探针**：验证新 bundle 下受判产物能拿到「标题判定 + 机械段自动补齐」，从而 `exit=0`。
- 审计目标：`pm/ui-bridge.ts:1888`（`export function renderCardSeedSections` 定义附近）

## 写入允许面

- `.agenticdoc/mw-worker-output-contract/evidence/acb-v2-audit.md`（唯一证据文件）

## 写入禁止面

其余一切路径。禁止修改代码、禁止无参全量 vitest/pytest。

## 要求

1. 审计 `renderCardSeedSections`：确认 (a) 契约清单注入条件是 `sections.type !== undefined`（不再是 writeless-only）；(b) 去重守卫 `!parts.includes(RECOVERY_CONTRACT_HEADING)`；(c) `recoveryContractSection` 对契约外 type 返回 `""`。逐条给 `PASS/FAIL`。
2. 产物落 `evidence/acb-v2-audit.md`（唯一证据文件）。
3. 不要修改代码。

## 交付格式

`report.md` 五段齐全：`结论` / `证据` / `残留与未验证` / `上下文来源` / `未覆盖面声明`。不要写 `## Questions` 段。

[VERIFY] ACB-V2 探针交付：exit=0。
