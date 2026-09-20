# Task T-02-TS-UNION: worker 侧 parent root union

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM（本窗口）或 worker
- ac_refs: [AC-002, AC-003, AC-004]
- vc_refs: [VC-002, VC-003, VC-004, VC-005, VC-006]
- pattern_refs: []

## 描述

### 源码

1. `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts` 新增两个导出纯函数（模块头注释注明 mw-partition-parent-extended AC-002；无 pi 依赖、无写盘）：

```ts
/** Partition extended-workspace union (mw-partition-parent-extended
 * AC-002/D-004): the Parent root line of a task.md v2 profile block.
 * Gated on the profile mode line (same line shape as the launcher tear
 * check `^\[mw\] mode: partition[ \t]*$`); the `Parent root` prefix
 * matches BOTH the old and the annotated label, so tasks dispatched
 * before the label change keep their union. null when not applicable. */
export function parentRootFromTaskContent(content: string): string | null;

/** Append parentRoot to the scope entries (AC-002/D-003). No-op when
 * config is undefined (no read_scope/deny_globs), scope is null
 * (deny-only) or empty (fail-closed all-block form) — never widen a
 * containment that was not declared non-empty. */
export function applyParentRootUnion(
	config: ReadScopeConfig | undefined,
	parentRoot: string | null,
): ReadScopeConfig | undefined;
```

实现要点：模式行正则 MULTILINE 全文锚定（不设行窗口）；`Parent root` 前缀行取首个命中、`:` 后路径 trim；union 返回新对象（scope 数组拷贝追加），不 mutate 入参。

2. `worker/worker-mode.ts` wiring（:449 区 `readScopeConfigFromMeta(meta)` 处，~3 行 + 注释）：

```ts
const readScopeConfig = applyParentRootUnion(
	readScopeConfigFromMeta(meta),
	parentRootFromTaskContent(fs.readFileSync(taskPath, "utf8")),
);
```

（taskPath 在作用域内；task.md 小文件 startup 一次性重读。）

### 测试（`packages/coding-agent/test/suite/autopilot-read-scope.test.ts` 新 describe，既有 describe 零修改）

- 纯函数矩阵（VC-002）：`[mw] mode: partition` + `Parent root: P`（旧标签）→ P；`Parent root (extended workspace, writable): P`（新标签）→ P；无模式行 / 无 Parent root 行 / mode: dual → null。
- union 矩阵（VC-003）：scope=["src/"] + P → ["src/", P]；config=undefined / scope=null / scope=[] → 原样返回（=== 同引用或深度相等）。
- wiring（VC-004）：`startScopedWorker` 变体——task.md body 追加 v2 profile 块（marker + `[mw] mode: partition` + `Parent root: <tmp parent 目录绝对路径>`）+ frontmatter `read_scope: [子目录]`；断言 parent 内 read 不 block、scope 外路径 block（rule=scope）。
- deny 优先（VC-005）：同 wiring + deny_globs `**/DerivedDataCache/**` → parent 下该目录路径 read block，reason 含 rule=deny-glob。
- 写零拦截（VC-006）：同 wiring，对 parent 路径 write/edit/bash toolCall 返回 undefined（不 block）且 trace/output 无 rejection；既有 "non-read tools untouched" 用例保持。

测试内标签建议同时断言双形态（旧 + 新），Stage 3 标签变更后无需回改本测试。

### 注意

- Node strip-only 可擦除语法（AGENTS.md）；无 inline import。
- 测试运行：coding-agent 包根 `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-read-scope.test.ts`。

## 完成判定

- autopilot-read-scope.test.ts 全绿（新 describe + 既有全部）
- 输出 `[VERIFY] VC-002..VC-006` 对应断言行
