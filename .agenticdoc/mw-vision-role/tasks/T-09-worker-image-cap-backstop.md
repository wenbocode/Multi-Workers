# T-09 worker 侧兜底 `[IMAGE-CAP]`

- key: mw-vision-role · 波 2 · 独占写面：`.../agent-team-loop/worker/worker-mode.ts`（`TaskMeta`/解析/`session_start` 段）、新建 `test/extensions/agent-team-loop-image-cap.test.ts`
- ac_refs: AC-011 · vc_refs: VC-011
- 依赖: T-02（同文件串行于 `TOOL_ALLOWLISTS` 段） · 预估: 60-90min

## 前置（R1 纪律）

`worker-mode.ts` 工作区有他人未提交改动（+165/-13）。**以工作区现值为锚**：`TaskMeta` 约 `:234-266`、`parseTaskMd` 约 `:268-330`、`origin:` 解析约 `:301-303`、`dispatchRefusal` 约 `:464`、拒绝三件套范式约 `:693-704`、`session_start` 回调约 `:738`。开工前再 `git diff --stat` 一次确认未变动；只在自己的段内插入。

## 目标

声明了 `images: yes` 但**运行模型**看不了图时，worker 不执行任务主体，走既有失败通道并在 `worker.log` 留机读行。

## 契约（逐字遵守）

- `TaskMeta` 新增 `images?: boolean`；`parseTaskMd` 在 `origin:` 之后同型插入：
  `if (trimmed.startsWith("images:")) images = trimmed.slice("images:".length).trim() === "yes"`
  （未声明 = `undefined`，零分支）
- 检查挂 `session_start`（**唯一**能读到 `ctx.model` 的事件上下文；`pi.on("session_start", (_e, ctx) => ...)`）
- 触发条件：`meta.images === true && ctx.model && Array.isArray(ctx.model.input) && !ctx.model.input.includes("image")`
- 动作（复用 `dispatchRefusal` 三件套 `:693-704` 完全同构）：
  1. `writeWorkerLogLine(line)` → `worker.log`（`fs.writeSync(1, ...)`，launcher 重定向）
  2. `appendError(taskKey, agenticdocRoot, line)` → trace.log
  3. `writeOutput({ taskKey, agenticdocRoot, exitCode: 1, summary: "Task refused (image capability).", exitReason: line })` → output.md
  4. `process.exit(1)`
- 机读行字面量：`[IMAGE-CAP] model=<id> provider=<p> task=<key> declared=images:yes`
- `ctx.model` 为 `undefined` ⇒ fail-open（写一条 trace 说明，不阻塞）
- 未声明 `images:` 的任务**不受任何影响**

## 步骤

1. `TaskMeta` + 解析（两处小改）。
2. `session_start` 内插入检查（在既有 `appendModel` 之后）。
3. 新建 `test/extensions/agent-team-loop-image-cap.test.ts`：激活 worker（`workerModeActivate(fakePi)`），捕获注册的 `session_start` handler，用 `ctx.model={id,input:["text"]}` 触发，`vi.spyOn(process,"exit")`，断言：`worker.log` 含 `[IMAGE-CAP]` + 模型 id、`output.md` 存在、`exit(1)` 被调用；对照：未声明 `images:` 的任务不触发。
4. `[VERIFY]` 用 `process.stdout.write`。

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-image-cap.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-checkpoint-wiring.test.ts   # 白名单快照回归
npx biome check --error-on-warnings src/extensions/agent-team-loop
```

## 证据格式

`[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true`

## 非空洞对照

把检查挂到 `session_start` 之外（拿不到 `ctx.model`）⇒ 必产出"恒不触发"的假绿，VC-011 红；把 `ctx.model` undefined 当"不支持" ⇒ fail-open 用例红。

## 交付

`worker-mode.ts` 三处 + 新测试文件 + 原始输出。真进程退出码由 T-14 人工核销（R13）。
