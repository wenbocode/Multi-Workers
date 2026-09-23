# Task T-1: 机器检查点行写入器

## 元信息
- Stage: 1
- 依赖: 无（可与 T-2 并行；与 T-2 文件面不相交）
- 风险: 低
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-001, AC-002]
- vc_refs: [VC-001（写入器半侧）, VC-002（append-only 半侧）]

## 背景（实测）

- `worker/output-writer.ts:11-18` `outputDir(taskKey, agenticdocRoot)` 已含 taskKey 穿越守卫（`resolved.startsWith(root + path.sep)`）。
- 既有写入器模式：`appendLifecycleLine`（`:66-70`）与各 `append*`（`appendCheckpoint` 等）均为 `fs.mkdirSync` + `fs.appendFileSync`。
- `writeOutput`（`:44` 起）在 `output.md` 已有内容时走 D-117「保留原文 + 追加 harness 段」的合并路径 → **不可**用于本次机器行（会引入合并语义）。
- `P-003`：`open(p,"w")` 先截断后求值 → 机器行必须是纯追加。

## 交付物

1. `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`
   - 新增 `export interface MachineCheckpointOpts { elapsedMs: number; reads: number; writes: number; phases: string; repeatTop: number; risk: "low" | "mid" | "high"; }`
   - 新增 `export function formatMachineCheckpoint(opts: MachineCheckpointOpts): string`，输出**恰好一行**（无尾随换行），格式见 design D-105：
     `CKPT <n>m [machine] ts=<ISO-8601> reads=<n> writes=<n> phases=<d>/<t> repeat_top=<k> risk=<low|mid|high>`
     （`<n>m` = `Math.round(elapsedMs / 60000)`；`ts` 用 `new Date().toISOString()`）
   - 新增 `export function appendProgressLine(taskKey: string, agenticdocRoot: string, line: string): void`：`outputDir` 守卫 + `mkdirSync(dir,{recursive:true})` + `appendFileSync(path.join(dir,"progress.md"), `${line}\n`, "utf8")`。**纯追加，不得读取/截断既有内容。**
2. 测试：新增 `packages/coding-agent/test/extensions/agent-team-loop-worker-progress.test.ts`
   - 新建场景：目录不存在时自动创建，文件内容 == `formatMachineCheckpoint(...)` + `\n`；
   - append-only：先写入 sentinel 行（模拟 PM 代记/worker 自评），再 append 两行，断言三行按序共存且 sentinel 未被改写；
   - 格式断言：输出匹配 `^CKPT \d+m \[machine\] ts=\S+ reads=\d+ writes=\d+ phases=(\d+/\d+|-) repeat_top=\d+ risk=(low|mid|high)$`，且 `phases`/`risk` 各变体齐全；
   - 守卫回归：包含 `..` 的 taskKey 抛错（沿用既有 `outputDir` 行为）。
   - `[VERIFY]` 行必须用 `process.stdout.write("…\n")`（vitest `silent: "passed-only"` 会吞 `console.log`），每行至少一个字段取自实测。
   - 临时目录用 `os.tmpdir()`，不得污染仓库。

## 约束

- 只改 `worker/output-writer.ts` 与该新测试文件；不改 `worker-mode.ts`（T-3 负责）、不改 `dist/**`、不改 Python。
- TS 只用可擦除语法（无 enum/namespace/参数属性）；无 `any`；无 inline `import()`。
- 不 commit；不运行 `mw build`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-progress.test.ts
cd H:/git/Multi-Workers && npm run check
git status --short
```

## 报告要求

最终消息给出：改动文件、用例计数、`[VERIFY]` 行原文、机器行样例、以及任何偏离 design 的实现细节。
