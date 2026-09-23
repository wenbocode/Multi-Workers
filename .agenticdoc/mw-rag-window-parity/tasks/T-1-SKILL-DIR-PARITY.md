# Task T-1: TS `skill.dir` 跨语言 parity

## 元信息
- Stage: 1
- 依赖: 无（可与 T-2 并行）
- 风险: 中（触及已锁定的跨语言 fingerprint 合约）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-301, AC-302]
- vc_refs: [VC-301, VC-302, VC-303, VC-304, VC-305]

## 背景（实测）

- Python `mw_common._rag_finalize_skill`（`mw_common.py:551-559`）接受 `skill.dir` 缺省或 `null`，语义 = 控制工作区根。
- TS `rag/config.ts:260-270` `parseSkill` 用 `requireString(raw.dir, …)` → 缺省/`null` 直接 `invalid-shape` 失败；
  `RagSkillEntry.dir`（`rag/config.ts:92-96`）类型为 `string`，无法表达 `null`。
- TS `rag/tools.ts:735` `cliCall` 里 `path.resolve(runtime.controlRoot, skill.dir)`：`dir` 为 `null` 会抛 `TypeError`。
- **关键约束**：TS `rag/config.ts:616-700` 的 `ragFingerprint` 与 Python `mw_common.rag_fingerprint` 必须**逐字节相等**，
  payload 里含 `skill.dir` 原值。所以**不得**把 `dir` 归一化成 `"."`（会破坏 fingerprint → `config tear (rag)` 误报）。

## 交付物

1. `packages/coding-agent/src/extensions/agent-team-loop/rag/config.ts`
   - `dir` 用 `optionalString`（缺省/`null` → `null`）；`RagSkillEntry.dir: string | null`；`dir: ""` 仍非法（保持 `invalid-shape`）。
   - **不要**改 `ragFingerprint` 的 payload 字段与顺序。
2. `packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts`
   - 新增并导出纯函数 `resolveCliDir(controlRoot: string, dir: string | null): string`（`null` → `controlRoot`，否则 `path.resolve`）；
   - `cliCall` 改用它（不 spawn CLI 也能单测）。
3. 测试
   - 新增 `packages/coding-agent/test/suite/rag-window.test.ts`（本任务只写它的 parity 部分；T-2/T-3 会往同一文件追加，追加时保持既有测试不动）：
     VC-301（缺省 `dir` → `dir === null` 且无错）、VC-302（`dir: null`）、VC-303（`dir: ""` → `invalid-shape`，错误文本含 `skill.dir`）、
     VC-304（`resolveCliDir` 两个断言：`null → root`、`"skills/x" → path.resolve(root,"skills/x")`）。
     写临时 fixture 请放在 `os.tmpdir()` 下，**不要**改 `test/fixtures/rag/*`。
   - 扩展 `packages/coding-agent/test/suite/rag-parity.test.ts`：VC-305 —— 同一份 servers 配置在 `dir` **缺省 / null / 显式** 三种变体下，
     TS `ragFingerprint` 与 Python `mw_common.rag_fingerprint`（subprocess 实跑取串，`encoding` 显式 utf-8）逐字节相等。
     沿用该文件既有的「跑 Python 取串」写法；不得改动既有断言与 golden 字节。

## 约束

- 只改上列文件；不改 `mw_common.py`/`mw.py`、`core/**`、任何 fixture/golden、`test_autopilot_l0.py`、`dist/**`。
- TS 只用可擦除语法（无 enum/namespace/参数属性）；无 `any`；无 inline `import()`。
- `[VERIFY]` 行必须用 `process.stdout.write("…\n")`（vitest `silent: "passed-only"` 会吞 `console.log`），
  且每行至少一个字段取自实测（例如实测解析出的 `dir`、实测两串是否相等 + 前 12 位）。
- 不 commit；不重建 `dist/extensions/agent-team-loop.js`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-parity.test.ts test/suite/rag-config.test.ts test/suite/rag-tools.test.ts
cd H:/git/Multi-Workers && npm run check
git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py   # 必须为空
```

## 报告要求

最终消息给出：改动文件、测试计数、`[VERIFY]` 行原文、fingerprint 三变体实测值（TS 串 = Python 串）、任何偏离与未覆盖项。
