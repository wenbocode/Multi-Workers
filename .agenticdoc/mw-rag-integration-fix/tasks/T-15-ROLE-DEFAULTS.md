# Task T-15: role/phase 默认真正接线到运行时（F-1）

## 元信息
- Stage: 1
- 依赖: 无（与 T-16 并行；T-16 只改 Python `mw.py`/`mw_common.py`，与本任务零文件重叠）
- 风险等级: 中
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-101, AC-102, AC-107]
- vc_refs: [VC-101, VC-102, VC-103, VC-109, VC-110]
- pattern_refs: []

- **`[VERIFY]` 行必须用 `process.stdout.write("[VERIFY] ...\n")`**：本仓 vitest `silent: "passed-only"` 会吞掉绿灯用例里的 `console.log`（坑点 P-006）。

## 背景（为什么做）

复核确认 AC-006 在运行时**从未生效**：`rewriteDefaults`（`rag/adapter.ts:247`）与 `resolveForRole`/`resolveForPhase`
（`rag/config.ts:584/596`）只有测试调用；`callRag`（`rag/tools.ts:426`）只透传 agent 显式参数，`ragToolCalls`
（`adapter.ts:311`）只在显式 `multi_rounds`/`auto_rewrite` 为真时改走 `rag_search_multi_rounds`。
即：调研角色不显式传开关时，**实际发出的仍是 `rag_search`**，注入块里那句 `[mw] Rewrite: true` 是空头支票。

设计：`design.md` D-101/D-102/D-103/D-104、VC-101/VC-102/VC-103/VC-110。

## 必须实现（按顺序）

### 1) 单一解析源：`renderRagBlock` 改用既有解析函数

现在 TS 侧 `rag/block.ts:60-83` 自带一份内联解析（`roleSpec?.server ?? phaseSpec?.server ?? config.defaultServer`；
`rewrite` 只看 `RESEARCH_ROLES`），而 Python 侧 `mw_common.py:903` 用 `_rag_resolve_defaults(config, role, phase)`
（role > phase > default，且 `rewrite` 考虑研究**阶段**）。两边**已经**是两份实现——这正是 D-104 要消除的。

- 让 `renderRagBlock` 调用 `resolveForRole` / `resolveForPhase` / `rewriteDefaults`：
  `server = roleSpecResolved.server ?? phaseResolved.server ?? config.defaultServer`，
  `source` 同理，`rewrite = rewriteDefaults(role, phase, capabilityRewriteOf(server))`。
  取 `role = roleForTaskType(type)`（见第 2 点），`phase = meta.phase ?? ""`。
- **硬要求**：golden 字节不得变（`packages/multi-workers/test/fixtures/rag-block.golden.md`，347 B，
  sha256 `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`）。若你的改动会让它变，
  **停下来在报告里说明**，不要自行重生成 golden（golden 是跨语言锁，重生成要 Python 侧同步）。

### 2) 角色回落统一为一份规则

`shared/dispatch-models.ts:78` 的 `roleForTaskType` = `DISPATCH_ROLE_BY_TYPE[type] ?? "coding"`。目前三处不一致：

| 位置 | 现状 | 目标 |
|---|---|---|
| `rag/block.ts:66` | `DISPATCH_ROLE_BY_TYPE[type] ?? type` | 改用 `roleForTaskType(type)` |
| `shared/dispatch-models.ts:78` | `?? "coding"` | 基准（不变） |
| Python `mw_common.py:901` / `mw.py:1866` | `?? task_type` | 由 **T-16** 对齐（本任务不动 Python） |

### 3) `RagRuntime` 接 role/phase，`callRag` 应用默认

- `rag/tools.ts`：`RagRuntimeHooks` 增可选 `role?: string; phase?: string`；`RagRuntime` 增 `role: string; phase: string`
  （缺省 `""`）；`registerRagTools` 把它们落到 runtime。
- `rag/tools.ts:426` `callRag` 内、构造 `args`（`:515-517`）之前：
  - `const roleRes = runtime.role !== "" ? resolveForRole(runtime.config, runtime.role) : null;`
  - `const phaseRes = runtime.phase !== "" ? resolveForPhase(runtime.config, runtime.phase) : null;`
  - server：`requested ?? roleRes?.server ?? phaseRes?.server ?? runtime.config.defaultServer`
  - source：显式 `params.source` > `roleRes?.source` > `phaseRes?.source` > `null`
  - rewrite：**仅对 `rag_search`**，且 agent 未显式给 `multi_rounds`/`auto_rewrite` 时，
    按 `rewriteDefaults(runtime.role, runtime.phase, entry.capabilities.rewrite)` 判定；为 `true` 时向 `args` 注入
    `multi_rounds: true`（`ragToolCalls` 会剥离开关并映射到 `rag_search_multi_rounds`）。显式值优先，不覆盖。
  - **未注册/为空的 role、phase → 完全不介入**（D-103）：不改 server 选择、不注入任何参数，行为与修复前逐字节/逐请求一致。
- 不要新增第二套判定函数（P-005 的教训）；只用 `resolveForRole`/`resolveForPhase`/`rewriteDefaults`。

### 4) 接线点（call site）

- `worker/worker-mode.ts:669`：`registerRagTools(pi, controlRoot, { breaker: new Breaker(), workerTaskDir, role: roleForTaskType(meta.type), phase: meta.phase ?? "" })`
  （`meta` 已在 `:567` 解析，`meta.phase` 就是 task.md 的 `phase:` 头；未知/缺失 → `""`）。
- `pm/pm-orchestrator.ts:635`：PM 会话没有 role/phase 概念 → 传 `""`（或省略），保证 PM 路径零变化。

### 5) 证据（fixture 级，不是直调纯函数）

新增 `packages/coding-agent/test/suite/rag-role-defaults.test.ts`，复用 `test/suite/rag-fixture.ts` 的假传输层
（`handler` 记录每次 `calls[].name` 与请求 url）：

- **VC-101**：配置 `roles.design`（server A，A 的 `capabilities.rewrite: true`）→ 以 `role: "design"` 起 runtime，
  agent 不传 `multi_rounds` → 断言 fixture 观测到的 wire 名 = `rag_search_multi_rounds`；以 `role: "coding"` →
  `rag_search`。
- **VC-102**：`roles.design.server: B`（未显式传 server）→ 请求打到 B 的 url；显式 `server: "A"` 时打到 A（显式优先）。
- **VC-110**：不传 role/phase（PM 路径）→ 不注入开关（wire 名 = `rag_search`）、server 仍取 `default_server`、
  不产生任何新文件写入。
- **VC-103 / AC-102**：把 `[VERIFY] VC-008` 行从 `test/suite/rag-adapter.test.ts:259` **移到这里**（只留一个发射点），
  字段必须取自 fixture 观测值，例如
  `[VERIFY] VC-008: role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1`。
  旧文件里对 `rewriteDefaults` 的纯函数断言**保留**（它仍是合法单测），但删掉它的 `[VERIFY] VC-008` 打印。
- **VC-109**：行内至少一个字段随被测数据变化——报告里用反例说明（例如把 `roles.design` 的 rewrite 相关配置反转，
  行内 `rewrite_tool` 随之变化且测试变红，验证后**还原**，`git status` 自查无 ` M`）。

## 验收

1. `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-role-defaults.test.ts test/suite/rag-adapter.test.ts test/suite/rag-tools.test.ts test/suite/rag-parity.test.ts` 全绿。
2. 十套 `test/suite/rag-*.test.ts` 全绿（`97 passed | 1 skipped` 为基线，新增用例允许计数增加）。
3. **golden 不变**：`sha256(test/fixtures/rag-block.golden.md)` 仍为 `00f85e64…`，`rag-parity` 的
   `golden_byte_match=true`、`fingerprint_match=true` 仍打出。
4. `test/suite/rag-phase.test.ts` / `rag-required.test.ts`（phase 轴）不受影响。
5. 仓根 `npm run check` exit 0（无 error/warning/info）。
6. 既有测试文件除本任务声明的两处（`rag-adapter.test.ts` 的 `[VERIFY] VC-008` 位置、必要时 `rag-parity.test.ts`）外零修改。

## 禁止

- 不改 Python 侧（`mw.py`、`mw_common.py`、`launcher.py`）——归 T-16/T-17。
- 不重生成 golden / 不改 `test/fixtures/**` 的既有 golden 与指纹。
- 不改其他会话的文件（`index.ts`、`implementation-gate.ts`、`docs/`）、不改文本层守护测试、不 commit。
- 不以「函数存在 + 单测绿」当完成判据（本任务的全部意义就是消灭这种假交付）。
