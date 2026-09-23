# Research: 设计事实底稿（design）

## 决策问题

支撑 design.md 的 D-101~D-109：写通道形态与可写文件名（D-101/102/103）、机器行归属与格式（D-104/105）、挂载点与 parity 影响面（D-106）、写入语义与计数口径（D-107/108）、拒绝留痕（D-109）。

## 调研方法与出处

- 源码逐段 `read`（非片段）：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`、`worker/output-writer.ts`、`rag/tools.ts`（注册范式段）、`packages/coding-agent/src/core/extensions/types.ts`（接口签名）。
- `rg -n` 定界：`TOOL_ALLOWLISTS`/`toolsForType`/`registerTool`/`setActiveTools`/`--tools`/`entry.tools`/`tools_snapshot`。
- Python：`packages/multi-workers/autopilot/dispatch.py`、`test_autopilot_l0.py`、`test_autopilot_dispatch.py`、`test_rag_research.py`。
- 事故与历史：`.agenticdoc/_pitfalls.md` P-003/P-004/P-005/P-007；上一轮 key 的 research note（`spec-progress-persist-baseline-2026-09-23.md`）。

## 发现

1. **单一集合计算点**：`rag/tools.ts:400-407` `applyRagTools` 是唯一设置 active tool 集合的地方（`pi.setActiveTools([...new Set([...toolsForType(type), ...ragToolNamesForType(rt, type)])])`，`:406`），`rt === null` 时退化为 `pi.setActiveTools(toolsForType(type))`（`:402`）。注册范式见 `rag/tools.ts:246-265`（`name/label/description/promptGuidelines/parameters: Type.Object({...})/execute(_toolCallId, params, signal, onUpdate)`）；`setActiveTools(toolNames: string[])` 签名见 `core/extensions/types.ts:1337`。
2. **parity 锁的解析对象是字面量表**：`test_autopilot_l0.py:215-239` 用正则 `const TOOL_ALLOWLISTS[^=]*=\s*\{(.*?)\n\};`（`:218`）解析 TS 源码中的对象字面量，再与 `dispatch.py:69` `REGISTRY` 比对；`test_autopilot_l0.py:292` 还断言 `toolsForType` 实现文本含 `TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback`。→ **在 `TOOL_ALLOWLISTS` 条目里加工具名会立即破坏 parity**；把新工具放在表外的 `activeToolsForType` 则不动锁。
3. **Python 侧无运行时消费者**：`dispatch.py:141`（`return entry.tools if entry else ()`）与 `:145-146`（`tools_snapshot`，注释明示供 L0 parity 测试）之外，`entry.tools` 无用途；`rg` 跨 `mw.py`/`launcher.py`/`mw_common.py`/`autopilot/dispatch.py` 对 `--tools` 与 `tools_for_type` 零命中 → launcher 不向 pi 传工具白名单，白名单完全由扩展在 TS 侧施加。→ D-106 的「零 Python 改动」成立。
4. **注册时机可行**：`workerModeActivate`（`worker-mode.ts:555`）先由 `PI_WORKER_TASK` 解析出 `meta.type`/`taskPath`，`workerTaskDir = path.dirname(taskPath)`（`:667` 附近注释区）与 RAG 注册（`:669`）都在 meta 就绪之后；因此「无写工具角色才注册窄工具」可以在同一位置做到结构性 gating（与 RAG「disabled 就不注册」同源）。
5. **append-only 写入器可复用**：`output-writer.ts` 的 `outputDir(taskKey, agenticdocRoot)`（`:11-18`，含 taskKey 穿越守卫）+ `appendLifecycleLine`（`:66-70`）+ 各 `append*` 均用 `fs.appendFileSync`；`writeOutput`（`:44-...`）在文件已有 agent 内容时走 D-117「保留原文并追加 harness 段」的合并路径 → 机器行若复用 `writeOutput` 会引入合并语义，故须单独 `appendProgressLine`（D-107）。
6. **`[TOOL]`/`[TOOL_ERR]` 已覆盖工具成败**：`worker-mode.ts:770-784`（`tool_execution_start` → `appendTool`）与 `:786-790`（`tool_execution_end` → `event.isError` 时 `appendToolError`）→ 窄工具的合法/非法调用无需新 trace 行类型（D-109）。
7. **写计数与读计数集合是显式常量**：`worker-mode.ts:138-140`（`READ_TOOLS`/`WRITE_TOOLS`）与 `:776-781` 的计数分支 → 决定窄工具是否计入 writes 只需决定是否加入 `WRITE_TOOLS`（D-108：不加）。
8. **风险先例**：`_pitfalls.md` P-004（POSIX 词法在 Windows 路径上丢反斜杠 → 路径检查静默漏拦）、P-003（`open(p,"w")` 先截断后求值）、P-007（review 无落盘通道，8/12 任务交不出结论）。

## 结论 → 决策映射

- 发现 1+4 → D-106：新增 `activeToolsForType` 作为唯一集合入口，注册点与 RAG 同区，结构性 gating。
- 发现 2+3 → D-101/D-106：走表外窄工具而非改白名单；本 key 无 Python 行为改动，AC-008 退化为「parity 无漂移」的回归断言。
- 发现 5 → D-107：`appendProgressLine` 独立追加语义，禁 `writeOutput`/`open(w)`。
- 发现 6 → D-109：拒绝留痕复用既有 trace 行类型，不改 `shared/heartbeat.ts` 的解析正则。
- 发现 7 → D-108：窄工具写入不计入 writes，保住「零产出」信号。
- 发现 8 → D-101/D-102：把「可写文件名」作为唯一输入（不做路径解析），从构造上消除 P-004 类漏拦；内容走 append（P-003）。
