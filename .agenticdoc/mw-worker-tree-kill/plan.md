# Plan: mw-worker-tree-kill

> 依据：spec.md（AC-001~006）+ design.md（D-001~004）。串行三阶段，无并行机会（S2/S3 依赖 S1 的代码位点）。

## Stage 1 — 实现退出路径树杀（S1）

目标：worker-mode.ts 全部 `process.exit(1)` 位点与 'exit' 安全网 hook 调用 `killTrackedDetachedChildren()`，顺序 = 写盘 → 杀树 → exit。

- 顶层新增 `import { killTrackedDetachedChildren } from "../../../utils/shell.ts";`
- 位点 1（:413 existsCheck）、位点 2（:439 refusal）、位点 3（:670 timeoutExit）、位点 4（:870 settled-catch）：exit 前一行加调用
- 'exit' 安全网 hook（:475）：在 output 补写**之前**加调用
- 验证：`npm run check` 通过；grep 断言 worker-mode.ts 内每个 `process.exit(` 的前两行内存在 `killTrackedDetachedChildren()`（机械不变量）

产出：worker-mode.ts 变更 + grep 证据。

## Stage 2 — 单测（mocked killProcessTree，S2）

目标：`test/extensions/agent-team-loop-worker-tree-kill.test.ts` 覆盖 AC-001~005（VC-001~005）。

- `vi.mock("../../../src/utils/shell.ts", importOriginal)` 只替换 `killProcessTree`；`trackDetachedChildPid` 保持真实
- harness 复刻既有 fakeWorkerPi 模式（on/sendUserMessage）+ fake timers + process.exit spy + fs.writeSync 静音
- 用例：idle kill（AC-001）、wall kill（AC-002，timeout: 2 头）、settled-catch 注错（AC-003）、exit listener 直调（AC-004）、成功路径零调用（AC-005）
- 顺序断言统一用 `mock.invocationCallOrder`
- 验证：该文件单跑全绿；`test/extensions/agent-team-loop.test.ts` 原套件不回归

产出：新测试文件 + 两条测试运行证据。

## Stage 3 — live 验证 + 全量回归（S3）

目标：AC-006 机制级 live 证据 + 仓库级回归。

- `test/extensions/agent-team-loop-worker-tree-kill-live.test.ts`（不 mock）：真实 spawn 挂起孙进程树（pid 落盘）→ track → 触发 idle watchdog → 轮询探活 ≤60s 全灭
- `./test.sh`（或按 AGENTS.md 的定向 vitest 运行）非 e2e 回归
- `npm run check` 全量
- dist bundle 重建（mw 框架部署语义，mw-stale-builtin-fix 教训）+ 提示 `/mw restart`
- 验证：live 用例 PASS + 回归 new-failures=0

产出：live 测试文件 + 运行证据 + dist 重建记录。

## 里程碑

| Stage | 完成判据 | AC |
|-------|---------|-----|
| S1 | check 通过 + grep 不变量成立 | （实现基础） |
| S2 | 单测 5 用例绿 + 原套件不回归 | AC-001~005 |
| S3 | live 绿 + test.sh/check 全绿 + dist 重建 | AC-006 |
