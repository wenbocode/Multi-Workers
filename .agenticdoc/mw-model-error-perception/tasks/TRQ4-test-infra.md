# TRQ-4: 模型错误仿真的测试基建盘点（research）

type: research

## 上下文

- 项目 goal：`.agenticdoc/goal.md`；约束：`packages/coding-agent/test/suite/` 用 harness.ts + faux provider，禁止真实 provider API（AGENTS.md）。
- 需求：为「模型持续 500/断连 → worker fail-fast + 证据落盘」写测试，须先盘点现有仿真手段。
- 已知锚点（须核验）：faux provider 的 `FauxResponseStep = AssistantMessage | FauxResponseFactory`（`packages/ai/src/faux.ts:114`）可直接注入 `stopReason: "error"` 的 assistant 消息；既有 watchdog 驱动测试见 `packages/coding-agent/test/suite/worker-idle-heartbeat.test.ts:1`。

## 要求

1. 盘点 mw-worker-timeout-convergence 留下的 watchdog/timeout 测试：在 `packages/coding-agent/test/` 下找出 idle/wall/checkpoint 相关测试文件与其驱动方式（如何起 worker-mode、如何注入 PI_WORKER_IDLE_MS、如何伪造事件流）。
2. 盘点 faux provider 能力：`packages/coding-agent/test/suite/harness.ts` 与其 provider 仿真能否注入「assistant stopReason=error / errorMessage=HTTP 500」「流中断」；若不能，指出最小扩展点（faux provider 在哪定义、事件如何编程）。
3. 盘点 packages/ai 层已有的错误重试单测（packages/ai/test/ 下 provider-retry/retry 相关），确认 ai 层行为已有覆盖、本 key 无需重复。
4. 结论→决策映射：新测试放哪个文件/目录、用什么注入手段模拟「连续 N 个 error turn」，以及哪些断言只能做纯函数级（如阈值解析、trace 行格式）。

## 写入允许面

- 仅允许写：`.agenticdoc/mw-model-error-perception/evidence/research/spec-test-infra-2026-10-15.md`

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-model-error-perception/evidence/research/spec-test-infra-2026-10-15.md`（只写此一个文件）
- 结构：现有测试清单（文件:行号 + 驱动方式）→ faux provider 能力判定 → 注入方案建议 → 结论→决策映射
