# plan — mw-write-face-guard

> 输入：`spec.md`（AC-001..AC-014 已锁）、`design.md`（决策 D-001..D-009）、
> `evidence/research/{spec-write-face-sources,spec-write-face-enforcement,spec-write-face-safety,design-glob-intersection,design-runtime-guard}-20261014.md`
> 行号一律以 symbol 名为准（前序 key 的教训：行号会漂移）；实现前先 grep 函数名。
> 本 key 是 `mw-dynamic-concurrency` 的硬前置：**判定面（A 声明 + B 派发闸 + C 运行期闸）未落地前不得放开 per-key 并发**。

## 0. 批次与依赖（落地顺序）

落地顺序由依赖决定，不由批次大小决定：**B0（算子 + 语料）→ B1（派发层闸，双通道同版本）→ B2（运行期闸 + 审计/doctor）→ B3（端到端对拍 + 迁移）→ B4（PM 收口）**。

| 批次 | 任务 | 语言 / 写面 | 依赖 | 覆盖 AC |
|---|---|---|---|---|
| **B0** | W-01 算子在 Python 落地 ‖ W-02 算子在 TS 落地（**语料由 PM 先冻结**） | Py 1 条 / TS 1 条，文件集两两不相交 | — | AC-007/009 |
| **B1** | W-03 conductor 派发闸 ‖ W-04 PM 派发闸 + 卡渲染 | Py `dispatch.py` / TS `ui-bridge.ts`+`task-dispatcher.ts` | B0 的两个模块 | AC-001/002/003/008/011/014 |
| **B2** | W-05 运行期写面闸（IP-1b）→ W-06 审计行 + doctor 计数 | TS `worker-mode.ts` / Py `doctor` 段 | W-05 依赖 B0；W-06 依赖 B1 的 refusal 事件形状 | AC-004/006/010/012/013 |
| **B3** | W-07 端到端双通道对拍 + 反证夹具 ‖ W-08 存量卡迁移脚本（可后置） | TS suite + Py pytest / 一次性脚本 | W-03+W-04+W-05 | AC-005/007/012 |
| **B4** | PM 收口：`npm run check` + `./test.sh` + `achieved.md` + QG | — | B0..B3 全绿 | 全部 |

**为什么 B1 必须整体先于 B2**：AC-012 已证伪"C 能替代 B"——运行期闸只能拦下**已经跑起来**的 worker 的越界写，拦不住"两个 worker 同时被派发到同一文件"这个事实；B 是唯一的"派发前拒绝"面。反之 B 也不能替代 C（声明为假时只能靠 C 兜底）。两层必须都在。

## 1. 写面唯一性（并行边界）

| 文件 | 唯一写者 | 说明 |
|---|---|---|
| `packages/multi-workers/autopilot/write_face.py`（新建） | W-01 | `parse_write_face` / `overlap`；**不得** import `fnmatch` 做匹配（D-006） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts`（新建） | W-02 | `parseWriteFace` / `writeFacesOverlap`；基准语义 = minimatch |
| `packages/multi-workers/test/fixtures/write-face-corpus.json`（新建，冻结） | **PM（先写）** | 双语言共享语料；冻结后 B0 的两个 worker 只读。改语料 = 改契约，须回到 PM。**冻结指纹（2026-10-14，第二次冻结）：`sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`，`bytes=19996`，`counts={parse:23, overlap:59}`（overlap 逐 kind：overlap 34 / none 13 / reject 8 / serial_only 1 / unsupported 3）**；第一次冻结为 `sha256=fb710b904cd4bbcb03ffa4f432ebc3b60c0234771b4c5f06c0d3a36a0186b09f`，两次差异与理由见 `evidence/PM-parity-differential-20261014.md`（D-111/D-112）｜ |
| `packages/multi-workers/test_write_face.py`（新建） | W-01 | 语料 + 边界向量本侧全过 + 冻结计数 |
| `packages/coding-agent/test/suite/write-face.test.ts`（新建） | W-02 | 读同一份 JSON 语料（沿用 `autopilot-config-corpus.json` 的 parity 形状） |
| `packages/multi-workers/autopilot/dispatch.py` | W-03 | **只此一条**：判定 + `task.md` 创建移进锁内；refusal 零副作用 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | W-04 | 只动 `mergeCardHeader`（渲染 `write_face:`）；跨 key 热文件 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts` | W-04 | 派发前判定挂点 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | W-05 | 跨 key 热文件，全程唯一写者；只加 IP-1b 分支，不动 `research` 行为 |
| `packages/coding-agent/test/suite/write-face-runtime.test.ts`（新建） | W-05 | 越界 block 矩阵 + AC-013 假阻回归 |
| `packages/multi-workers/mw_common.py` | W-06 | doctor 段；**其它 session 正在追加此文件**，落地前先 `git diff` 复核，冲突则让 PM 转手 |
| `packages/multi-workers/test/write-face-e2e.test.py`（新建） | W-07 | 双通道同输入同判定 + 反证夹具 |

## 2. 任务清单

### W-01 · 交集算子（Python，B0）
- **写面**：上表 W-01 两行。**禁止**修改 `autopilot/xkey.py:1084` 那处 `fnmatch` 用法（另一个语义面，不在本 key 范围）。
- **交付**：`parse_write_face(text)` **三态**返回（RQ-D1 §3.3）：缺头 → `UNKNOWN`（未声明，走 D-003 serial-only）；有头但空 → 解析拒绝 `write-face-empty`；非空 → `tuple[str, ...]`。`overlap(a, b) -> str | None` 返回**冲突样例路径**或 `None`。归一实现按 D-006：单一 `/`、拒绝前导/内嵌 `!`、拒绝 `..`（`write-face-escape`）、拒绝 entry 内 `,`、`a/**` 含 `a`、段内 `**` 按 `*`、win32 大小写不敏感（显式 `caseInsensitive` 参数）、`dot:true`、base = 仓根；**判定里 deny 不参与**（`A.deny` 遮盖 `A∩B` 仍判重叠）。判定全离线（glob 编译 → 交集 → ε-NFA 乘积），**不枚举文件系统**。另需 `Unsupported` 分支覆盖 §3.2 的保守回退清单（extglob 取反/`+()`/`*()`/`?()`/非法 class/嵌套 brace 超限/跨 base 绝对路径）——任一侧命中即判**重叠**，不判无交集。
- **验收**：`cd packages/multi-workers; python -m pytest test_write_face.py -q`。
- **证据**：`evidence/W-01-write-face-operator-py.md`；含语料全过计数、`a/**` vs `a`、中段 `**`、段内 `**`、`dot:true`、win32 大小写（两种模式都锁）六组边界，以及 §3.2 保守回退清单的逐条命中样例，以及"deny 遮盖不改结论"的单调性对照。

### W-02 · 交集算子（TS，B0）
- **写面**：上表 W-02 两行。
- **交付**：与 W-01 逐字同语义（同一份语料同一期望值）；复用 `minimatch`（`worker/read-scope.ts` 已在用，10.2.5），**不新引依赖**。
- **验收**：`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face.test.ts`。
- **证据**：`evidence/W-02-write-face-operator-ts.md`；含与 W-01 的同语料结果对照表（两列，必须逐行相等）。

### W-03 · conductor 派发闸（Python，B1）
- **写面**：`autopilot/dispatch.py`（唯一写者）。
- **交付**：在 `dispatch()` **已持的那一次** `acquire_lock`（`dispatch.py:1156`）内完成"读队列 → 读在飞 worker 的 `write_face` → 判重叠 → 建 `task.md` → upsert"；`task.md` 创建从 `:1132` 移到锁内（AC-014）。拒绝时返回稳定 code `write-face-overlap` + `overlap-with:<task_key>` + 冲突样例路径，**零副作用**（不建 taskDir/task.md/队列行）。未声明（D-003）→ `write-face-undeclared` 审计行 + **serial-only**（存在同 key 在飞则不派发，不拒绝也不写行）。在飞集合在判定时由 `_workers.parallel` 重算（不加队列列，AC-008）。
- **验收**：`cd packages/multi-workers; python -m pytest -q`（新增 + 既有不回归）；含零副作用目录快照 diff。
- **证据**：`evidence/W-03-dispatch-refusal.md`；含锁内临界区的 before/after 行号与双进程对拍输出。

### W-04 · PM 派发闸 + 卡渲染（TS，B1）
- **写面**：`pm/ui-bridge.ts`（`mergeCardHeader`）、`pm/task-dispatcher.ts`。
- **交付**：① `mergeCardHeader` 把卡 envelope 的「写入允许面」渲染成 task.md 头 `write_face:`（与 W-03 的读取格式逐字一致）；② `dispatchTask` 在 `WorkerStore.upsert` 的锁内 RMW 上做同一判定，拒绝时返回同一 code/字段形状。**判定必须与 W-03 同输入同输出**（AC-007）。
- **验收**：`node ... vitest --run test/suite/write-face.test.ts test/suite/agent-team-loop.test.ts`（后者的行号/表头冻结断言是回归锚点）。
- **证据**：`evidence/W-04-pm-refusal.md`；含卡头渲染 before/after 原文、refusal 形状与 W-03 的逐字段对照。

### W-05 · 运行期写面闸（TS，B2，跨 key 热文件）
- **写面**：`worker/worker-mode.ts`（唯一写者）。
- **交付**：按 D-007 的 **IP-1b**：在 `workerModeActivate` 闭包内新增 `write`/`edit` 分支，bash 分支条件由 `isShellRole && isWritelessRole` 放宽到 `isShellRole`，复用 `extractBashWriteCandidates`/`checkBashWriteScopeTarget`（meta 已缓存，零额外 I/O）；**自建写面 lexer**，不复用 `implementation-gate` 的 target lexer；`worker_file` basename 白名单不变；**默认面/deny 面角色类别化**（不能把 `packages/**` 绝对 deny 套到 coding）；`research` 行为逐字保持（用现有测试证明字节级不变）。
- **验收**：`node ... vitest --run test/suite/write-face-runtime.test.ts` + 现有 `research` 相关 suite 无回归。
- **证据**：`evidence/W-05-runtime-guard.md`；含 11 条 AC-013 反例向量（`Write-Output a <term> --glob x` 家族）逐条判定，以及 `research` 无回归的测试名单。

### W-06 · 审计行 + doctor 计数（Python，B2）
- **写面**：`mw_common.py`（doctor 段）。
- **交付**：`.agenticdoc/_autopilot/timeline.jsonl` 写 refusal / undeclared 事件；`mw doctor` 输出写面重叠拒绝计数 + 最近样例（无重叠显示 0，不能静默）。
- **验收**：`python -m pytest -q`，含 `capsys` 断言（干净仓库零行/rc 不变）。
- **证据**：`evidence/W-06-doctor.md`；含两类事件样例行。

### W-07 · 端到端双通道对拍 + 反证（B3）
- **写面**：`test/suite/…` + `test_write_face_e2e.py`（新建）。
- **交付**：① 同语料过两条通道，比较 code/`overlap-with`/样例逐字段相等；② AC-005 反证：同一时刻同 key 同文件多写者 = 0（在飞快照 + 写面字段重算）；③ AC-013 假阻双向对照。
- **验收**：两侧测试全过。
- **证据**：`evidence/W-07-e2e-parity.md`。

### W-08 · 存量卡迁移脚本（B3，可后置）
- **交付**：一次性脚本，把卡 envelope 的「写入允许面/禁止面」渲染进 419 份存量任务书的 `write_face:`；不是运行期依赖（D-003 已保证不迁移也不中断）。
- **验收**：干跑模式输出 diff 计数；抽样复核。
- **证据**：`evidence/W-08-migration.md`。

## 3. 串行点（必须排队，不得并行）

1. **`worker-mode.ts`**：跨 key 热文件（其它 key 也在改同一文件，含 `[WRITE_SCOPE]` 相邻段）——派 W-05 前先看 `_index.parallel` 是否有 live key 正在改它。
2. **`ui-bridge.ts`**：同样跨 key 热文件（`mw-widget-order-stability` 刚改过 `setWatchWidget` 一带）——W-04 需独占。
3. **语料 JSON**：单一写者（PM），冻结后任何改动回到 PM。
4. **`mw_common.py`**：其它 session 正在追加（本窗口已实测到 +281 行）——W-06 落地前复核 diff。
5. **B1 双通道同版本**：W-03/W-04 同批发布；只落一侧会导致两通道判定分叉（AC-007）。

## 4. 每批 DoD 与全局门禁

| 批次 | DoD |
|---|---|
| B0 | 两侧语料全过且逐行相等；`npm run check` 全绿；`python -m pytest -q` 不回归 |
| B1 | AC-001/002/003/014 测试通过（含零副作用快照）；`npm run check` 全绿 |
| B2 | AC-004/010/012/013 通过；`research` 无回归；doctor 计数非静默 |
| B3 | AC-005/007 端到端成立；反证夹具（C 不能替代 B）双向成立 |
| B4 | `npm run check` + `./test.sh`（非 e2e）全绿；`achieved.md`（含「# 系统行为变化」「# 遗留」）；`/quality-gate` 出报告 PASS |

**每张卡必带**（dispatch 门禁）：`type:` + 上下文/要求/交付格式 + ①写入允许面/禁止面 ②验收命令原文 ③改动历史（`file:line` before→after）④唯一证据文件路径 ⑤目标对齐（`goal.md` 锚点 + 至少一条 `path:line`）。

## 5. 风险与回退

| 风险 | 处置 |
|---|---|
| 存量 419 份无写面 ⇒ 串行回退拖慢吞吐 | D-003 已定 serial-only + 只审计不拒绝；W-08 迁移可后置；吞吐代价在 MDC 的 cap 内已被算入（key 层 cap 是上界，不是必须打满） |
| 两语言语义漂移 | 单一冻结语料 + 逐行相等断言（P-021）；Python 侧禁 `fnmatch` |
| 运行期误拦合法写（AC-013 同类） | 角色类别化的默认面/deny 面 + W-05 的 11 条反例向量 + 双向对照 |
| 判定把 deny 当扣减项 ⇒ 拿安全网放宽并发（RQ-D1 §3.2 否掉的方向） | D-006 已定“判定里 deny 不参与、运行期 deny 优先”；W-01 证据里必须带单调性对照 |
| 热文件撞车（worker-mode.ts / ui-bridge.ts / mw_common.py） | §3 串行点；派发前查 `_index.parallel` |
| 声明为假（卡上写 A、实际写 B） | C 层兜底 + `[WRITE_SCOPE]` 审计；不假装 A 够用（AC-012） |

## 6. 与下游 key 的接口（mw-dynamic-concurrency 的输入）

- MDC 的 per-key 并发放开**只读**本 key 的两个产物：task.md 头 `write_face:`（或"未声明"标记）与 `overlap(...)` 判定结果。语义冻结在 `design.md` D-001/D-006，MDC 不得自行解释或复制实现。
- 本 key 达到 DONE 是 MDC 进入 EXECUTE 的硬前置；MDC 的 PLAN/TASKS 可并行推进（只写文档不写实现）。


## 7. 执行记录（2026-10-14 第三轮：语料 v3 + 两张修正卡）

- **语料 v3 冻结**：`packages/multi-workers/test/fixtures/write-face-corpus.json` 现为 `sha256=b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62`、`bytes=19996`、`counts={parse:23, overlap:59}`（kind 直方图 overlap 34 / none 13 / reject 8 / serial_only 1 / unsupported 3）。新增行 **V58**（`[huge, "src/x.ts"]` × 同，`huge="x/"*300+"x"`，601 字符）锁的是 D-111 overlap 期"状态机回退只延迟那一对、不中止整轮"。补丁脚本（可复核、含 `--check`）：`_scratch/evidence/wf-corpus-v58-20261014.py`（另有两次 trailing-comma 修复脚本 `wf-corpus-v58-repair-20261014.py` / `-repair2-`）。
- **V58 两侧实测**（`_scratch/evidence/wf-v58-probe-20261014.py` + `wf-v58-ts-out.json`）：TS `Conflict sample="src/x.ts"`（109 passed，已把 TS 测试计数同步到 23/59）；Python 现状 `Unsupported(glob-product-state-limit)` ⇒ 修复前基线 `python -m pytest test_write_face.py -q` = **2 failed, 127 passed**。
- **W-03 收尾**：任务真身（pid 95260）34 分钟后正常 `done`，交付完整（`test/test_write_face_dispatch.py` 25 passed、`evidence/W-03-dispatch-refusal.md` 19,849 B 存在）。**但该任务被重复激活 12 次**，把 12 块假 `failed` 写进 `output.md`，一度误导 PM。完整取证与 RF-1..RF-4 待修项见 `_scratch/evidence/wfg-i03-duplicate-activation-20261014.md` + `_pitfalls.md` P-034；**属框架级缺陷，不在本 key 的处理面**（需要独立 key：激活期唯一性闸 / run.json 写前置条件 / 产物归属校验 / 重复激活告警）。
- **第三轮两张卡（并行、写面不相交）**：
  - `T-W-I06-operator-py-defer`（W-06）：`autopilot/write_face.py` + `test_write_face.py`——按对延迟 + 冲突优先 + 与 TS `writeFacesOverlap` 同族；验收 `129 passed`。
  - `T-W-I07-render-comma-safe`（W-07）：`autopilot/dispatch.py` + `test/test_write_face_dispatch.py`——D-113 含逗号条目回退块列表载体，锁 `parse(render(E)) == E`（含 16 条语料的往返锁 + 真实 dispatch 端到端）；验收 ≥28 passed。
- 两张卡都过了 spawn 阶段自检（`inspect_envelope` + `type_extras_missing` 均空 + 种子 `goal.md` 与 `name.ext:NNN` 齐备，见 `_scratch/evidence/precheck-cards-20261014.py`）。

### 7.1 W-06 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核（不采信自述）**：`python -m pytest test_write_face.py -q` = **130 passed**（修复前基线 2 failed / 127 passed）；`wf-v58-probe-20261014.py` 输出 V58 = `Conflict(sample="src/x.ts", rule="src/x.ts", other="src/x.ts")`、V59 = `Unsupported(unsupported-syntax)`、V60 = `Unsupported(glob-product-state-limit)`，与 TS 侧逐条同族。
- **修复形状经 PM 读码确认**（`autopilot/write_face.py:943-977`）：单槽 `deferred`（首个遇到者胜）+ `ga.unsupported or gb.unsupported` 与 `_ConservativeUnknown` 共用该槽 + 冲突对立即 `return Conflict` + 循环耗尽后才 `return deferred`。与 `shared/write-face.ts:844` 的 `writeFacesOverlap` 逐条对应，注释里也写明了对应关系。
- **卡面 129 vs 实测 130 的解释（PM 采信）**：`129 collected` 是开工基线（127 passed + 2 failed），要求 7 强制新增 1 条独立回归测试 ⇒ 修复后 `130 collected` 全绿。卡面数字未计入新增测试，不是测试泄漏。
- **指纹口径修正（W-06 发现，PM 确认并记此）**：本仓 Windows 磁盘上的语料是 **CRLF**（130 行 ⇒ 磁盘 20126 B），而本文件各处记的 `sha256` / `bytes` 均按**LF 归一化后的内容**计（`19996 B`）。两者等价：两侧读者解析的都是同一份 JSON 内容，LF 归一化 sha 恒为 `b39f8925…`。后续引用该指纹时必须带这个口径说明。
- **遗留（本 key 只记录，不单独开卡）**：`globs_overlap`（`write_face.py:858`）仍是旧形状——`except _ConservativeUnknown` 仍包住整轮 `for ga_globs/for gb_globs/...`，混合"不可判定对 + 可证冲突对"时会提前 `return Unsupported`。**可达性实测**：唯一调用点是 `test_write_face.py:318` 的 `_go()`，恒以 1×1 列表调用；其 docstring 自述为 "direct boundary testing" 变体（每元素单个 glob）⇒ 当前**不可达**，且不在任何生产路径（`dispatch.py` 只调 `overlap()`）。触发条件与义务：一旦有卡以**多元素列表**调用它，必须同族化（按对延迟）。

### 7.2 W-07 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核（不采信自述）**：`python -m pytest test/test_write_face_dispatch.py -q` = **29 passed**（基线 25，卡面 ≥28）；我自己的往返探针 5 例全恒等——`['a/{b,c}/**']` → `'write_face:\n  - a/{b,c}/**'`、`['packages/x/**','a/{b,c}/**']` → 两行块列表、`['src/[a-','src/ok.ts']` → 单行、`['packages/x/**','packages/y/z.py']` 与 `['dir/']` → **单行逐字节不变**。
- **跨读者风险由 PM 单独核过（卡面未要求）**：`write_face` 的读者只有 `autopilot/dispatch.py`（写+读在飞 task.md）与算子本体；`mw_common.py` 不读它；TS 侧只有 `shared/write-face.ts`（**没有** task.md 的 `write_face` 读者 ⇒ 证实 B1 的 PM 侧确实未开工）。多行块列表在 task.md 头里是**既有形态**：同一头里的 `read_scope:` / `deny_globs:` 早已用 `  - item` 块列表（`dispatch.py:881-889`）⇒ 无读者被破坏。
- **指纹口径的报回项已解决（非缺陷）**：W-07 实测磁盘 `sha256=4acc365d…`、`20126 B` 与卡面 `b39f8925…`、`19996 B` 不符，原因就是 §7.1 记的 CRLF 口径：卡面指纹按 **LF 归一化内容**计，磁盘是 CRLF（130 行）。W-07 未硬编码指纹（只用行数 + 逐行恒等），故不受影响；**后续写卡一律带"LF 归一化"字样**，避免重复报回。
- **warn 段来源（W-07 回读出现 `路径形态（warn，不影响判定）`）**：生产者为 `worker/output-writer.ts` 的 `gaps.malformedFiles` 形态检查（C-36c，warn-only），检查对象是 worker 自报的文件清单；本次因报告里嵌入了写面条目串（含 `,` / 换行 / `{}`）而被列入。**不是** worker 缺陷，也**不是**台账按逗号切分。已记录为 `_pitfalls.md` P-035，并把"报告里嵌入写面条目"的处理义务指向输出契约族（另一窗口的 `mw-worker-output-contract` 正在做 ledger/契约族研究）。

### 7.3 W-08 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/write-face-pm-gate.test.ts` = **19 passed**；`test/suite/write-face.test.ts` = **109 passed**；`npx tsgo --noEmit` 由 worker 报 0 错误（未复跑）。B1 两半（conductor `dispatch.py` + PM `pm/{ui-bridge,task-dispatcher}.ts`）现已同形。
- **PM 修掉了本 key 弄红的一条既有冻结断言**（W-08 报回的两处卡面缺陷，我认）：卡面把验收路径写成不存在的 `test/suite/agent-team-loop.test.ts`，而真正会因新增头行变红的是 `test/suite/dispatch-card-injection.test.ts`（byte-exact 头断言）。PM 自跑确认 `1 failed / 17 passed`（`+ write_face: 仅本任务目录。`），按 `write_face:` 头行把**期望值**同步为 `writeFaceLine` 常量 + prologue 数组一项（不动断言逻辑），复跑 **18 passed**。该文件不是任何活跃 worker 的写面（`git status` 干净、mtime 10-13 00:53）。
- **PM 读码对照出的两处真实分歧（测试未覆盖，非 W-08 越界）**：
  1. **拒绝分支 `reason` 丢算子 detail**。Python `_write_face_verdict`（`dispatch.py:1169`）：`reason = f"{parsed.code}: {parsed.detail}"`，而 `Refused.detail` 带 `entry '<raw>'` / `present-but-empty write_face head`（`write_face.py:654/668/674/685`）。TS 侧 `writeFaceVerdict`（`pm/task-dispatcher.ts` rejected 分支）只回 `code`，`detail` 退化为 `${taskKey}: ${code}` ⇒ 两通道对同一非法输入给出**不同的 reason 串**（`code` 相同）。根因：TS 算子 `WriteFaceParseResult` 的 `rejected` 变体只有 `code`（`shared/write-face.ts:134/514`），不带 raw entry。
  2. **PM 通道对任何拒绝都不留持久审计记录**（见 design 未决项）：Python 有 `_write_face_audit` → `.autopilot/timeline.jsonl`（事件 `write-face-rejected`/`-overlap`/`-undeclared`，`dispatch.py:1089/1164/1183/1230`）；TS 侧只有 timeline 的**读**入口（`autopilot/status-model.ts` 的路径/解析），W-08 把 PM 的审计出口定成 `DispatchOutcome` 返回值，但 `pm/pm-orchestrator.ts` 仍忽略该返回值（W-08 残留 2）⇒ **AC-003「拒绝/降级须写审计行」今日只在 conductor 通道成立**。
- **队列单写者偏离已裁定**：W-08 因写入面限制在 `task-dispatcher.ts` 内复制了 `WorkerStore.upsert` 的字节镜像（`upsertQueueRowLocked`，`task-dispatcher.ts:521`），并用结构化视图读 `WorkerStore` 私有 `filePath`/`lockPath`。裁定见 D-114；跟进卡 `wfg-i09-queue-single-writer` 已派。
- **计数偏乐观（未修，待 orchestrator 释放）**：`pm-orchestrator.ts` 的 `dispatchNewTasks` / `dispatchOrphanCandidates` 忽略 `DispatchOutcome`，被拒仍 `queued += 1`（下一轮扫描自愈，但计数误导）。该文件属另一 key 的读回投递话题范围，暂不派卡。
- **W-08 自报的既有红项**（T-17 anchor、worker-file-tool `trace.log`、mwds-t02 语料、mwds-t23 bundle sha）未由 PM 复跑，按"与写面路径无关"接受，不据此判分。

### 7.4 W-09 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/worker-store.test.ts` + `test/suite/write-face-pm-gate.test.ts` = **38 passed**（19 + 19）；相邻 `write-face` / `dispatch-card-injection` / `mwds-t21-write-intent-soundness` = **140 passed**；`rg 'join(" | ")|upsertQueueRowLocked|serializeWorkerEntry' pm/task-dispatcher.ts` **无命中** ⇒ 第二份行拼接实现确已删净。
- **PM 补做了一项测试抓不到的核对（base 语义）**：`dispatchTask` 现在是 `writeFaceBase(path.dirname(store.queuePath))`，而 `store.queuePath` = `worker-store.ts:152` 的 `path.join(agenticdocRoot, "_workers.parallel")` ⇒ `writeFaceBase` = `resolve(agenticdocRoot, "..")` = **仓库根**，与 Python `write_face_base(project_root) = str(project_root)`（`dispatch.py:1016`，调用点 `:1452` 传 `project_root`）**同根**。这条必须用代码锚点核对：base 若错成 `.agenticdoc`，条目仍是原样字符串、往返/条目对照测试全都照样绿，但 `write-face-escape` / `write-face-outside-base` 的判定会与 conductor 分叉。
- **临界区形状保持**：`task-dispatcher.ts` 仍是 `acquireLock(store.lockFilePath)` → `writeFaceVerdict` → `injectWorkspaceProfile` → `store.upsertWithinLock(full)`，与 D-005/AC-014 一致；`WorkerStore.upsert`（`:208`）改为取锁 + 调 `upsertWithinLock`（`:225`，不取锁，docstring 写前置条件），D-114 落地。
- **残留（已记，未开卡）**：`upsertWithinLock` 是 public 方法，误用（非持锁调用）只靠 docstring + 测试约束；`pm-orchestrator.ts` 仍忽略 `DispatchOutcome`（被拒仍 `queued += 1`），与 §7.3 同题，等该文件写权释放。
- **B2 已派**：`wfg-i10-runtime-guard`（T-W-I10，D-007 IP-1b 运行期写面闸）。派发前实测 `worker/worker-mode.ts` 无活跃写者（`git status` 干净、mtime 2026-10-12 22:02），满足 plan §3 串行点 1 的前置检查。

### 7.5 W-10 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/write-face-runtime.test.ts` = **9 passed**；`mwds-t12-regression` + `dispatch-card-envelope` + `mwds-t21-write-intent-soundness` = **57 passed**（11 + 33 + 13，无回归）；`mwds-t03` = **4 failed / 59 passed**，4 条红经我逐条核对**全部是旧口径断言**（3× `VC-024: <coding|repair|vision> registers no write-scope guard`、1× `the summary is written once at recordEnd and only for the writeless guard role`）——D-007 明确反转该口径，属**预期内**，已裁定由 `wfg-i11-carrier-convergence` 重写（D-115 第 7 条）。
- **PM 自核「记账面未动」**：`git diff -U0 worker-mode.ts | rg 'tool_execution_start|tool_execution_end|READ_TOOLS|WRITE_TOOLS|pendingBashWrites|appendWriteFileEvent|appendToolError'` 只命中一行**新增注释** ⇒ 断言成立。
- **PM 自核的关键设计缺口（R1，本次最重要的发现）**：B1 渲染 `write_face:`（PM 侧 `ui-bridge.ts:2092` 渲染、`:2273` 调用），而 B2 运行期货仍只读 `meta.writeScope`（`worker-mode.ts:434-441` 被本卡列为"复用/不改"）⇒ **真实 writable 卡的声明面在运行期失效**（落默认面 = 工作树根，越出 `write_face:` 不会被拦）。PM 裁定 D-115（载体收敛）并派 `wfg-i11-carrier-convergence` 收口。
- **R3（writable 无 bash 角色零闸门）**：`roadmap-writer` 无 bash ⇒ `isShellRole` 为假 ⇒ 不装闸。已并入 D-115 第 6 条（安装条件改 `hasWriteTools || isShellRole`）与本卡。
- **R4/R5/R6 接受**：P1「miss 优先于误拦」的有意漏面（`-` 头重定向目标、here-string 宽松闭合、`allow-unknown` 放行）已由新测试锁定；`mwds-t02` 1 条 red 是别 key 的 task book 引起的语料漂移（`wjg-qg-evidence-closure` 指向 `mw-worktree-junction-guard` 的证据文件）；`worker-file-tool` 2 条为既有 `trace.log` 基线。
- **R7/R8 未验证（记录）**：`dist/**` 未重建（现场仍跑旧逻辑）；无真实 provider 端到端（判定经 handler 直调 + 纯函数复算）。

### 7.6 W-11 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`write-face-runtime.test.ts` + `mwds-t03-bash-write-scope.test.ts` = **81 passed**（18 + 63；`mwds-t03` 由 `4 failed / 59 passed` 变 **0 failed / 63 passed**，旧口径断言是**重写加严**而非删除）；回归 `dispatch-card-envelope` + `mwds-t12-regression` + `mwds-t21-write-intent-soundness` = **57 passed**。
- **D-115 落地形状**：`parseTaskMd` 经 `shared/write-face.ts::parseWriteFace` 解析权威 `write_face:`（含 D-113 块列表）；`[WRITE_FACE]` 审计行只在**两载体同时存在**时产生（单载体 0 行，避免噪声）；安装条件 `hasWriteTools || isShellRole`（`roadmap-writer` 由零闸门变有 `write`/`edit` 闸、不装 bash 子判定）；writeless 逐字不变。
- **PM 独自查出并直接修掉的两条本 key 造成的红**（W-11 只报了一条同类，另一条它标为"既有红"但**实为 W-10 引入的旧口径断言**）：`test/suite/autopilot-read-scope.test.ts` 的 `expect(interceptorCount()).toBe(1)` 两处（`:752`/`:809`，`type: coding` + `read_scope`）——coding 现在同时注册读面与写面两个 `tool_call` 处理器，故为 2。按行号精确改（另一处 `:466` 是 research 型任务、仍应为 1；`:648` 为 0，均未动）并加注释说明第二个处理器的来源，复跑 **28 passed**。同一文件未被其它会话占用（`git status` 干净）。
- **PM 误拦探针（本卡最关键的风险自测，卡面未要求）**：临时 vitest 驱动（用完已删）以 `write_face: packages/coding-agent/src/**` 声明面直调 `checkBashWriteScopeTarget`（verbatim=true）：
  - 面内文件 `src/a.ts`、`src/sub/a.ts` → **allow**；**面内目录目标 `src/gen`（`rm -rf`/`find -delete` 家族）→ allow**；面根 `src` → allow。
  - 面外一层 `packages/coding-agent`、面外文件 `outside.ts`、`..` 逃逸 → 拦 `rule=write-scope detail=outside-declared-write-face`；仓外绝对路径 → 拦 `rule=scope`；glob 目标 `packages/coding-agent/*.ts` → fail-closed 拦。
  - 结论：**没有面内合法写被误拦**（尤其目录目标），方向正确；本 key 的"声明面真的拦得住"现在对 writable 角色成立。
- **残留（记，未开卡）**：
  1. 包含判定是**重叠**语义（单个具体目标时等于成员判定，正确）；glob 型目标只要求"有交集"而非"子集"，理论上可 fail-open，但生产路径上 glob 目标走 `allow-unknown`（只审计不拦），暴露面被限住——未来卡可显式裁定 subset vs overlap。
  2. `write_face:` 存在但被拒（present-but-refused）时运行期 fail-closed（非沙箱目标全拦），未单独加测试（派发层本会先拒该卡，运行期是兜底）。
  3. junction/cwd 与 base 的 realpath 归一未做（保持最小改动）；`mw-worktree-junction-guard` key 覆盖该族。
  4. `dist/**` 未重建（现场仍跑旧逻辑），B4/发布前需重建两侧。
- **本 key 造成的测试红已全部清零的账**：`mwds-t03` 4 条（W-11 重写）、`dispatch-card-injection` 1 条（PM 直接修）、`autopilot-read-scope` 2 条（PM 直接修）。其余红均为无关既有基线：`worker-file-tool` 2 条（`trace.log` 污染）、`mwds-t02` 1 条（别 key task book 语料漂移）、`mwds-t23` 1 条（别 session 的 dist bundle sha）、`test/extensions/agent-team-loop.test.ts` 1 条（T-17 anchor 指 `mw-guard-form-hardening`）。

### 7.7 W-13 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑复核**：`test/suite/write-face-pm-gate.test.ts` = **22 passed**（基线 19，只加 3 条，既有 19 条未改未放）。
- **PM 读码核对消费点**（卡面要求的实质）：`pm/pm-orchestrator.ts:981`（修复路径）与 `:1325`（常规路径）都是 `if (outcome.ok) { queued += 1 / result.queued.push } else { reportWriteFaceRefusal(...) }` —— 对**任意非 ok** 统一处理，**没有**硬编码 `code`；审计走既有 `recordDispatchAlarm` → `.agenticdoc/_autopilot/auto-decisions.jsonl`（`phase:"dispatch-alarm"`, `kind:"write-face-refusal"`, `detail="${taskKey}: ${reason}"`），best-effort 不破派发；`onRefusal → deliverPmAlert` 为生产接线（`:1761`）。⇒ **AC-003 在 PM 通道闭合**，且计数不诚实（被拒仍 `queued += 1`，会污染 `dispatch-quota`）同批修掉。
- **D-008 一致性**：PM 侧审计出口仍是"派发返回值"，本卡只是让调用方把它变成持久行——未新建 `.autopilot/timeline.jsonl` 写者（这是我先前 (b) 方案的修正，已写入 `design.md` 裁定）。
- **设计取舍（接受）**：`write-face-refusal` 是 per-task、**未做 session 去重**——长期被拒的任务每轮 `agent_settled` 扫描各落一行（conductor 侧 `_write_face_audit` 同为每次尝试一行）。若将来要求"同类同 task 每 session 一行"，需把去重集合并入 `DispatchScanOptions`（当前不做，避免越面）。
- **新发现的收口障碍（B4 必须处理）**：`test/suite/mwds-t23-cutover-recheck.test.ts` 的 requirement 4 断言 `packages/multi-workers/dist/extensions/agent-team-loop.js` 的 sha 等于卡面记录值，实测 `expected 975D4066…` vs `received 9544D8A4…`；该 bundle mtime `2026-10-14 08:38:48`（早于本会话）、开工前即 `git status = M`、且是**禁止面**（`packages/multi-workers/**` 只读）⇒ 与本 key 无关，但**它是本 key DONE 前的质量门障碍**：B4 必须重建两侧 `dist`（同步别人已改的 source）并重新同步该卡面记录的 sha，或明确由该文件归属方处理。
- **其余既有红（无关，报基线不修）**：`worker-file-tool` 2 条（`trace.log` 污染）、`mwds-t02` 1 条（别 key task book 语料漂移）；`dispatch-recovery-terminal` 全绿。

### 7.8 W-12 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑双侧复核**：TS `test/suite/write-face-e2e.test.ts` = **8 passed**；Python `test/test_write_face_e2e.py` = **7 passed**；`git status` 只多这两个 `??` 新文件（**未动生产代码**）；精确禁用项扫描（`.only(`/`.skip(`/`.todo(`/`pytest.mark.skip`/`xfail`）**零命中**（两个文件里 `only/skip/todo` 字样都出现在文档注释里）。
- **B3 三项结论（worker 自报，PM 采信其原始证据行 + 自跑复现）**：
  1. **双通道逐字段对照 0 不一致**：同一装置把语料 parse 23 + overlap 59 = 82 行喂给 conductor `_write_face_verdict` 与 PM `dispatchTask`，比 `ok`/`code`/`overlap-with:<task_key>`/`sample`/`serial-only` = **410 次对照全一致**，且两通道都与"按文档算法写的 projection"一致（同为 0）。**base 对齐坑已量化**：故意错对齐 → 4 处不一致（P12/P15/V55/V56 全是绝对路径项），显式对齐 → 0。这是对本 key 最核心主张（AC-007 两通道同判定）的收口证据。
  2. **AC-005 反证成立**：conductor 与 PM 实派后复算 **0 对**同 key 同文件多写者；人为绕过闸门直写队列行后复算 **1 对** ⇒ 这个 0 来自检测器拦阻而非空集（**检测器不自证**）。
  3. **AC-013 双向对照成立**：真写族（`..` 逃逸 / 仓外绝对 / 非法否定项 / 目录目标越界）两通道全拒；假写族（`Write-Output a <term> --glob x` 家族 11 条 + 只读 3 条）两通道 14/14 放行；运行期 `write`/`edit` 与 `bash` 两条真实注册路径上真写 4/4 拦、假写 0/14 拦。
- **仍未闭合的一处（PM 早前读码发现，本卡未覆盖）**：**拒绝分支的 `reason` 串两通道仍不等**——Python `_write_face_verdict:1169` 回 `f"{parsed.code}: {parsed.detail}"`（detail 形如 `entry '<raw>'` / `present-but-empty write_face head`，`write_face.py:654/668/674/685`），TS 侧 `writeFaceVerdict` 只回 `code`（TS 算子 `WriteFaceParseResult` 的 `rejected` 变体不带 raw entry，`shared/write-face.ts:134/514`）。W-12 的 5 个对照字段**不含 `reason`**，故未被这次对照发现；该串会经 W-13 的 `writeFaceRefusalDetail` 进入 PM 审计行 ⇒ 同一非法输入在两通道留下不同的审计 detail。**PM 判定**：这是 AC-007 的最严读法下的缺口，且已在 W-13 的审计面上可见，故**不留给"遗留"**，派 `wfg-i14-reject-reason-parity`（T-W-I14）收口后再进质量门。
- **B4 决定（PM）**：
  1. **存量卡迁移不做**：D-003（未声明不中断）+ D-115（writable 无 `write_face:` 时回落 `write_scope:`；有 `write_face:` 时以它为准）已保证不迁移也不中断，迁移脚本属可后置改动 ⇒ **不派卡**，在 `achieved.md` 的遗留里点明"若将来要清空 legacy 载体再迁"。
  2. **`dist/**` 未重建是开放的收口障碍**：本 key 的运行期能力只在 `src` 生效（W-12 §残留 3 明确测试经 type-stripping 直接 import `src`）；仓库 `AGENTS.md` 禁止我自行 `npm run build`（除非用户要求），且 `packages/multi-workers/dist/extensions/agent-team-loop.js` 已被**其它 session** 改动（mtime 08:38:48、本会话开工前即 `M`）并导致 `mwds-t23` req-4 的 sha 断言红。⇒ 交由用户在收口时决定重建时机（避免与其它 session 的 dist 写权相撞），本 key 记录为"落地上线前必做"。

### 7.9 W-14 终态吸收（PM 独立复核，2026-10-14）

- **PM 自跑五条验收（全部与 worker 自报逐字一致）**：`write-face.test.ts` **113 passed**（基线 109）、`write-face-pm-gate.test.ts` **25 passed**（基线 22）、`write-face-e2e.test.ts` + `mwds-t03` **71 passed**、`npx tsgo --noEmit` exit 0、Python `test_write_face_e2e.py`+`test_write_face.py`+`test/test_write_face_dispatch.py` **166 passed**。
- **PM 读码核对（不采信自述）**：`pm/task-dispatcher.ts:442` `reason: parsed.detail === undefined ? parsed.code : \`${parsed.code}: ${parsed.detail}\``、`:438` detail 尾缀；算子 `shared/write-face.ts:54` `WRITE_FACE_EMPTY_DETAIL`、`:151` `readonly detail?: string`、`:629/:633` 拒绝时回填；两侧字面格式对得上（Python `write_face.py:654/668/674/685` 的 `f"entry {raw!r}"` / `f"deny entry {raw!r}"` vs TS 的 `entry '<raw>'` / `deny entry '<raw>'`，TS 注释显式引用了这两个 Python 行号）。⇒ AC-007 在 `reason` 字段上收口（空头 / 非法条目 / 逃逸三例两侧逐字节相等，`detail` 亦逐字节相等）。
- **两处有界差异（worker 主动报告 + 我确认其已被测试显式锁定，不是掩盖）**：
  1. **repr 引号风格**：条目原文含单引号、不含双引号时 Python `{raw!r}` 改用双引号包裹（`entry "x'y/**"`），TS 保持单引号（`entry 'x'y/**'`）；除 wrapper 外两串全同；测试 `write-face-pm-gate.test.ts:726` 用 `rawOf()` 断言**去掉 wrapper 后相等**。
  2. **D-112 单行引号逗号切分**：`write_face: 'a,b'` 时 TS `splitSingleLine` 先剥 wrapper 再按 `,` 切（raw=`a,b`）、Python 语法盲切（raw=`'a`）；`code` 两侧相同（`write-face-invalid-entry`）而 reason 的 raw 片段不同。这是**冻结的 D-112 解析语义的既有差异**，改它会变更判定（属另一 key 面），故只记录并断言（`:752`）。
  ⇒ PM 判定：两处都**接受**（不派卡）：字符串级边界，判据 `kind`/`code` 一致，且已显式锁在测试里；模拟 Python `repr` 的引号选择只会把展示层复杂度带进冻结语料算子（卡面明确禁止"对齐用格式转换"）。
- **新残留（PM 记录，不修）**：PM 审计行的前缀分隔符与 conductor 不同——conductor `_write_face_audit` 是 `"<task_key>: <code> <detail>"`（空格），PM `writeFaceRefusalDetail`（`pm-orchestrator.ts`，W-14 的禁止面）是 `"<task_key>: <reason>"` ⇒ `<task_key>: <code>: <detail>`。`reason` 本体已逐字节相等，且两条审计落在**不同文件/不同 schema**（timeline 事件 vs ledger 行），故接受为有界差异。
- **`it.skipIf(!pythonAvailable)` 的口径（PM 记录，接受）**：3 条跨通道对照是条件跳过（W-08 起既有惯例，该文件共 4 处这种守卫）；本机 Python 可用 ⇒ 25 passed **0 skipped**（实测）。PM 用**读码**独立佐证同一结论（两侧构造点字面一致），故 AC-007 的收口不依赖该守卫的运行时值。
- **未修**：`dist/**` 仍未重建（见 §7.8 B4 决定 2 与 `achieved.md` 遗留 1）。

### 7.10 PM 质量门前置扫描发现 AC-006 是真缺口 → 派 W-15（2026-10-14）

- **AC-014 复核通过**（PM 读码）：`autopilot/dispatch.py` 取锁 `:1435` → `task_dir.mkdir` `:1461` / `task_md.write_text` `:1462` → `upsert_worker_row` `:1478`，**全在锁内**；文件头注释 `:18-27` 明确记着"旧顺序在锁外写 task.md 会留下 check-then-act 孤儿"。⇒ AC-014 满足。
- **AC-006 是未实现的 AC（PM 实测）**：`mw_common.doctor_report`（`mw_common.py:4039-4091`）的 section 清单（service/proxy/queue/gates/dispatch/activation/worktree_links/conductor/rag/serve_code…）**没有写面容**；`_doctor_autopilot` 只读 timeline 的尾部水位；TS 侧唯一读 ledger 的 `readGateReminders`（`autopilot/status-model.ts:1212`）只接受 `phase === "remind"`（`:1232`）⇒ W-13 落的 `phase:"dispatch-alarm"`, `kind:"write-face-refusal"` 行**没有任何只读面消费**。反差点：`pm-orchestrator.ts:571` 的注释本来就写着这些行"对 humans、`mw doctor` 与后续消费者可见"——**设计意图在、实现没跟上**，这正是质量门要抓的那类缺口。
- **PM 已给出精确实现口径（读码核实，替 worker 消掉猜测空间）**：
  - conductor 事件名恰为 `write-face-rejected` / `write-face-overlap` / `write-face-undeclared`（`dispatch.py` 的 `WRITE_FACE_AUDIT_*`）；`_write_face_audit`（`:1089`）只传 `ev` + 自由文本 `detail`，**没有结构化字段**；三种 detail 形态：rejected = `"<task_key>: <code> <operator detail>"`、undeclared = `"<task_key>: write_face undeclared; <N> same-owner worker(s) in flight"`、overlap = `"<task_key>: overlap with <other_key> at <sample> (<rule> vs <other>)"`（**不是** `overlap-with:` 形态）。
  - PM ledger 行形状恰为 `{seq, phase:"dispatch-alarm", kind, count, detail}`（`pm-orchestrator.ts:586`），**无 `task_key` 字段**；`kind=="write-face-refusal"` 的 `detail` = `"<task_key>: <reason>"`（`reason` 内含冒号，禁 `split(":")`）；另有 `kind=="write-scope-risk"` 行，**不是拒绝**，不得混入计数。
  - 读时间线必须用 `autopilot/timeline.py:422` `query_events`（已处理 `.1/.2` 轮转）；section 只能在 `mw.py` 里按 `_doctor_rag`（`mw.py:2364`）式样加——**`mw_common.py` 是别的 session 的活动写面，本卡只读**。
- **卡**: `tasks/T-W-I15-doctor-refusal-surface.md`（写面 `packages/multi-workers/mw.py` + 新建 `packages/multi-workers/test/test_write_face_doctor.py`；七项要求含"纯只读零副作用"、"0 不报错不 unhealthy"、轮转覆盖、坏行容错、"解析不出附加字段仍计数"）。

### 7.11 W-15 终态吸收（AC-006 收口，PM 独立复核，2026-10-14）

- **PM 自跑复核（全部与 worker 自报一致）**：`test/test_write_face_doctor.py` **15 passed**；既有 `test_write_face.py`+`test/test_write_face_dispatch.py`+`test/test_write_face_e2e.py` **166 passed**；相邻 doctor 面 7 个套件 **155 passed**（87s，我复跑）；`python mw.py doctor --project H:/git/Multi-Workers --json` 的 `write_face` 段 = `{"total":0,"by_code":{},"by_source":{"conductor":0,"pm":0},"recent":[]}`，`summary.issues` 里**只有**预先存在的 `STALE CODE`（活动 serve PID 151032 落后工作树代码），`write_face` 不入 issues。
- **PM 读码核对只读纪律**：新增 5 个函数（`_write_face_detail_parts` / `_parse_write_face_event` / `_parse_write_face_ledger_row` / `_doctor_write_face` / `_format_write_face_doctor_line`）逐个体检**零** `write_text`/`open(...,"w")`/`acquire_lock`/`summary[...]`/`issues.append`/`mkdir` 命中；挂载点只有 `mw.py:621`（`report["write_face"] = ...`）与 `:641`（非 `--json` 打印）。⇒ AC-006 的"只读面 + 0 不报错 + 不进 issues"三项成立。
- **本仓库 `mw doctor` 退出码 = 1 的口径**：唯一 issue 是 `STALE CODE`（另一 session 的活动 serve 落后于工作树），与写面无关；worker 用"干净项目 + live pid + 3 条拒绝"证明同一 CLI 路径在 N=3 时仍 **exit 0 / healthy / 不入 issues**。⇒ PM 判定：**不影响 AC-006 判定**（AC-006 要的是"显示 0 而非报错"，本仓库的 1 来自别的既有 issue；写面段自身恒不产 issue）。
- **新残留（PM 记录，接受）**：① `mw doctor --json` 的 `write_face` 段**目前无 TS 侧消费者**（`/mw doctor` 只透传 JSON），要接线进 UI 属另一面；② `recent` 的跨源定序口径——conductor 事件有秒级 `ts`，PM ledger 行**没有 `ts`**，PM 行按"最旧"参与并集（仅在时间戳事件不足 5 条时占窗）；③ 读不出的 `code` 归 `unknown` 桶但**仍计数**。
