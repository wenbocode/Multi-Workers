# Research: worker 退出清理的入口/覆盖/测试观测选型（design）

## 决策问题

- D-001 清理入口：扩展如何拿到并终止 bash 工具遗留的子进程树
- D-002 覆盖策略：哪些退出位点需要显式清理、调用顺序如何定
- D-004 测试观测：单测如何在不起真实 taskkill 的前提下断言「杀树先于退出且覆盖全部 tracked pid」

## 调研方法与出处

- 代码走读（本仓库，2026-09-19）：
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:413,439,670,870`（4 个 `process.exit(1)` 位点）+ `:475-487`（'exit' 安全网在 refusal 块**之后**注册 → refusal/existsCheck 退出时 hook 尚未注册）
  - `packages/coding-agent/src/utils/shell.ts:239-279`（`trackedDetachedChildPids` 模块态 Set；`killTrackedDetachedChildren` 遍历 Set 逐 pid 调 `killProcessTree`；后者 Windows `taskkill /F /T /PID` detached spawn、POSIX `kill(-pid)`）
  - `packages/coding-agent/src/utils/shell.ts:1-5`（模块 import 均函数级使用，无 import 时副作用 → 扩展安全引入）
  - `packages/coding-agent/src/core/tools/bash.ts:108,142`（track 于 spawn 后、untrack 于 finally → 命令挂起期间 pid 恒在 Set 中）
- 测试惯例走查：`packages/coding-agent/test/first-time-setup-fork.test.ts:6-8`、`compaction-summary-reasoning.test.ts:15-17`（`vi.mock(path, async (importOriginal) => ({...actual, 替换单个导出}))` 是本仓库既定模式）；`test/extensions/agent-team-loop.test.ts:3868+`（watchdog 集成 harness：fakeWorkerPi + fake timers + `vi.spyOn(process, "exit")` + `fs.writeSync` 静音）

## 发现

1. tracked Set 是 `utils/shell.ts` 模块私有，唯一公开出口是 `killTrackedDetachedChildren()`；扩展与之同属一个编译产物（built-in extension），import 即同一模块实例 → **复用是读到 Set 的唯一途径**，自实现必然漏杀。
2. `killTrackedDetachedChildren` 逐 pid 调 `killProcessTree`（每 pid 恰一次）→ 把 mock 放在 `killProcessTree` 层、保留 `killTrackedDetachedChildren` 真实，即可在不 spawn 真实 taskkill 的前提下断言 per-pid 覆盖；Vitest 的 vi.mock + importOriginal 模式在本仓库已有先例。
3. 顺序断言可用 Vitest 的 `mock.invocationCallOrder`（跨 spy 全局单调递增）比较 kill 与 exit 的先后，无需计时。
4. 测试中 `process.exit` 被 spy（不真退）→ 'exit' 事件不会自然触发；'exit' hook 的单测只能**直接调用注册的 listener**（`process.listeners("exit")` 取新增项）。
5. taskkill 在 `killProcessTree` 内以 detached + stdio ignore spawn → 父进程随后 `process.exit(1)` 不影响其执行（Windows 子进程本就不随父死，本 key 正是利用该特性做善后）。
6. 早期退出位点（taskPath 不存在 :413、refusal :439）发生在 hook 注册与任何 agent turn 之前，tracked Set 必为空——清理调用是 no-op，但保留可让「worker-mode.ts 内 process.exit 必先杀树」成为可 grep 的机械不变量。

## 结论 → 决策映射

- D-001 选复用 `killTrackedDetachedChildren()`（否决自实现/自杀整树：前者 Set 不可达，后者 POSIX 组语义混乱且有自杀副作用）。
- D-002 选「全部 4 个 exit 位点显式清理 + 'exit' hook 兜底」，顺序 = 写盘 → 杀树 → exit（写盘同步先完成，杀树 fire-and-forget 不阻塞）。
- D-004 选 `vi.mock` 只替换 `killTrackedDetachedChildren`（跨模块导出 mock 必拦截）+ `invocationCallOrder` 顺序断言 + listeners 直调测 hook；真实杀树另设不 mock 的 live 测试文件（2 个独立 tracked 进程 + 孙进程树 + 轮询存活），per-pid 全覆盖与真实树终止由 live 证据承担。

### 补充发现（执行期 2026-09-19）：ESM 闭包使 killProcessTree 层 mock 不可行

- 验证方式：设计 D-004 原方案为 mock `killProcessTree` 以保留 `killTrackedDetachedChildren` 真实遍历；实施前复核 ESM 语义：`vi.mock` 工厂替换的是模块**导出表**，而 `killTrackedDetachedChildren` 函数体内对同模块 `killProcessTree` 的引用是**模块内闭包绑定**，不经过导出表 → mock 观测不到内部 per-pid 调用（标准 ESM 语义，非 Vitest 缺陷）。
- 结论：D-004 改为 mock `killTrackedDetachedChildren` 本身（worker-mode 的跨模块 import 必然拦截）；per-pid 全覆盖改由 live 测试（真实进程探活）以更强证据承担。同步修订 design.md VC-001~004 量化口径与 spec AC-001~003 量化行。
