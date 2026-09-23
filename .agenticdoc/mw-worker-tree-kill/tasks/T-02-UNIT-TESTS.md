# Task T-02-UNIT-TESTS: mocked killProcessTree 单测（AC-001~005）

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: 本窗口 PM 自执
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005]
- pattern_refs: []

## 描述

新建 `packages/coding-agent/test/extensions/agent-team-loop-worker-tree-kill.test.ts`：

- `vi.mock("../../../src/utils/shell.ts", async (importOriginal) => ({ ...actual, killTrackedDetachedChildren: vi.fn() }))`——只替换 `killTrackedDetachedChildren`（worker-mode 跨模块导入 → 必拦截；ESM 闭包使 killProcessTree 层 mock 不可观测，见 design 调研）。
- harness 复刻 `agent-team-loop.test.ts:3868+` 模式：fakeWorkerPi（on/sendUserMessage 记录）、fake timers、`vi.spyOn(process, "exit")`、`fs.writeSync` 静音、mkdtemp 任务目录、PI_WORKER_IDLE_MS=60000。
- 用例：
  1. AC-001/VC-001：无活动推进 60s → killTrackedDetachedChildren 恰一次，invocationCallOrder < exit(1) 的 order；trace.log [TIMEOUT]/[END] 与 output.md 已写入
  2. AC-002/VC-002：task.md `timeout: 2`（wall 分支）→ 同上断言（detail 行含 budget exceeded）
  3. AC-003/VC-003：vi.mock phase-runner 的 writePhaseFile 注错 → emit agent_settled 两次 → catch 路径杀树先于 exit(1)
  4. AC-004/VC-004：激活后 `process.listeners("exit")` 取新增 listener 直接调用 → killTrackedDetachedChildren 被调（模拟硬崩溃，不 emit 全局 exit 事件）
  5. AC-005/VC-005：正常 settle（agent_end + agent_settled）→ kill 零调用、exit 零调用、trace [END] exit=0、output 含 "Agent settled"
- 运行：`node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-tree-kill.test.ts`（包根执行）全绿；原 `agent-team-loop.test.ts` 套件同命令不回归。

## 验收
- 新文件 5 用例全绿 + 原套件全绿，运行输出留 evidence/runs/
