# ACB-R1 · AC-010(b) 研究类探针 1（only-news-letter）

- Key: mw-worker-output-contract
- type: research

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」）。
- 本任务是 T-08 部署后的 **AC-010(b) 研究类验证探针**：验证新 bundle 下受判产物能拿到「标题判定 + 机械段自动补齐」，从而 `exit=0`。
- 线索起点：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:101`（`recoverySectionsFor`，契约段来源）。

## 写入允许面

- `.agenticdoc/mw-worker-output-contract/evidence/acb-r1-notes.md`（唯一证据文件）

## 写入禁止面

其余一切路径。禁止修改代码、禁止无参全量 vitest/pytest。

## 要求

1. 只读调查：阅读 `packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts` 中 `matchesWriteScopeEntry` 的实现（约第 292 行起），用 1-2 句中文概括它的判定规则（glob 语义、双基准、裸 basename）。
2. 在 `evidence/acb-r1-notes.md` 记录结论（该文件是唯一证据文件，写 3-6 行即可）。
3. 不要修改任何代码，不要触碰其他文件。

## 交付格式

`report.md` 四段齐全：`结论` / `证据`（含你实际读取的行号与 grep 输出）/ `残留与未验证` / `上下文来源`（引用你读过的文件）。结论一句话，证据给原始命令或行号，残留写「无」。不要写 `## Questions` 段。

[VERIFY] ACB-R1 探针交付：exit=0。
