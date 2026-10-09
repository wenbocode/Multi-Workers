# Research: task.md `images:` 头契约（写侧/读侧/auto-detect/零字节不变量）

TL;DR
- `images:` 头当前**不存在**；两条写侧路径与 5 个读侧点全部是逐行前缀扫描，新增一行头成本低但读侧改动面 ≥3 处（worker / Python state / launcher）。
- P-005 在本仓是**既成事实**：`timeout:`、`rag_chat_budget:`、`rag_time_budget_s:` 只有读者没有写者；`model-reason:` 反过来只有写者没有读者。spec 风险 1 不是假想。
- 建议 `images:` 条件渲染、紧贴 `phase:` 之后 `model:` 之前，TS/Python 同序；auto-detect 只在 TS 派发面做（有 registry），Python 只渲染显式参数。
- 零字节不变量有现成双范式：Python git-HEAD 冻结渲染器 + TS 整文件 golden。二者都已在仓内存在，直接复用。

## 决策问题
1. 现有 task.md 头逐字段的写者/读者是谁？哪些是空转缺口？
2. 两条写侧的代码位置、头部顺序，以及新增一行会打到哪些 golden/逐字节测试？
3. auto-detect 放哪层、需要什么输入、误报面、`images: no` 优先级？
4. 如何断言"未声明时产物逐字节相同"？
5. 可机器判定的 VC（含零字节 + 真实派发路径产生）？
6. 未确认点与确认方式？

## 调研方法与出处
- 全量读源码：`ui-bridge.ts`、`worker-mode.ts`、`dispatch-models.ts`、`autopilot/dispatch.py`、`autopilot/state.py`、`launcher.py`、`mw.py`、`task-dispatcher.ts`、`pm-orchestrator.ts`。
- 全量读测试：`test_rag_phase.py`、`test_autopilot_readcap_injection.py`、`test_autopilot_dispatch.py`、`test_autopilot_conductor_exec.py`、`agent-team-loop.test.ts`、`agent-team-loop-checkpoint-wiring.test.ts`、`rag-required.test.ts`。
- 锚点为 2026-09-26 工作区实际 `file:line`；只读，未改任何其他文件。

## 发现

### F1 头部关键字现状表（写者 → 读者）
| 头 | 写侧 | 读侧 |
|---|---|---|
| `type:` | TS `ui-bridge.ts:1040-1043` / `:1083-1088`；Py `dispatch.py:296-297` | worker `worker-mode.ts:268`；Py `launcher.py:159`；Py `state.py:205`；Py `mw.py:1790`；TS `task-dispatcher.ts:117` |
| `phase:` | TS `ui-bridge.ts:1042` / `:1085`；Py `dispatch.py:299-300` | worker `worker-mode.ts:271`；Py `mw.py:1793`；TS `task-dispatcher.ts:118` |
| `model:` | TS `ui-bridge.ts:1087`；Py `dispatch.py:301-302` | Py `launcher.py:160`（唯一读点） |
| `model-reason:` | TS `ui-bridge.ts:1088` | **无读者**（仅 TS 测试断言） |
| `origin:` | Py `dispatch.py:304`（固定 `conductor`） | worker `worker-mode.ts:279`；Py `state.py:203`；TS `pm-orchestrator.ts:361/365` |
| `loop:` | Py `dispatch.py:305` | Py `state.py:196` / `:245`（`used_rounds`） |
| `attempt:` | Py `dispatch.py:306` | Py `state.py:197-205` / `:249` |
| `timeout:` | **无写者** | worker `worker-mode.ts:275` |
| `read_scope:` | Py `dispatch.py:308-310` | worker `worker-mode.ts:286-296` |
| `deny_globs:` | Py `dispatch.py:315-317` | worker `worker-mode.ts:300-312` |
| `l2_read_file_cap:` | Py `dispatch.py:311-312` | worker `worker-mode.ts:314` |
| `l2_read_byte_cap:` | Py `dispatch.py:313-314` | worker `worker-mode.ts:318` |
| `rag_chat_budget:` | **无写者** | worker `worker-mode.ts:322`；TS `task-dispatcher.ts:119` |
| `rag_time_budget_s:` | **无写者** | worker `worker-mode.ts:326`；TS `task-dispatcher.ts:120` |

- 空转字段（只有读者没有写者）：`timeout:`、`rag_chat_budget:`、`rag_time_budget_s:`（全仓 grep 除测试 fixture 外无生产者）→ 直接对应 P-005（`.agenticdoc/_pitfalls.md:45`）。
- 反向空转：`model-reason:` 只有写者没有读者（P-013 家族）。
- 读侧是 3 套互不共享的扫描器：worker `parseTaskMd`（`worker-mode.ts:246`）、Py `parse_task_labels`（`state.py:151`）、Py `_read_task_md_fields`（`launcher.py:143`）；另有 2 个正则读点（`mw.py:1786`、`task-dispatcher.ts:115`）。

### F2 写侧与受影响的 golden/逐字节测试
- TS：frontmatter 由 `planDispatchFrontmatter` 组装（`ui-bridge.ts:1024`）；落盘两处共用同一 `modelPlan.frontmatter`——dispatch_worker `ui-bridge.ts:1255`、`/worker` `ui-bridge.ts:1642`，内容 `${frontmatter}\n${description}\n`。改一处即两侧生效。
- Python：唯一渲染器 `render_task_md`（`dispatch.py:253`），唯一 conductor 调用点 `dispatch()`（`dispatch.py:515`）。
- 头部顺序：TS = `type:[, phase:][, model:][, model-reason:]`（`ui-bridge.ts:1040-1043`/`:1083-1088`）；Python = `type:[, phase:][, model:], origin:, loop:, attempt:[, read_scope:][, l2 caps][, deny_globs:]`（`dispatch.py:296-317`）。
- 会被新头打到的精确串/逐字节测试（新头必须条件渲染，否则这些会同时变红）：
  - `packages/coding-agent/test/extensions/agent-team-loop.test.ts:5331`（VC-010，整文件 `toBe("type: coding\n\nwork\n")`）；同文件 `:5127`/`:5134`（`startsWith("type: review\n")`）。
  - `packages/coding-agent/test/extensions/agent-team-loop-checkpoint-wiring.test.ts:470`（整文件 `toBe("type: review\n\nreview\n")`）。
  - `packages/coding-agent/test/suite/rag-required.test.ts:179`/`:189`/`:198`（frontmatter 精确串）。
  - `packages/multi-workers/test_rag_phase.py:36-62`（GOLDEN 整块 + `phase=""` 逐字节）。
  - `packages/multi-workers/test_autopilot_readcap_injection.py:634`/`:655`（对照 git-HEAD 冻结渲染器逐字节）、`:298-300`（cap 行位置）。
  - `packages/multi-workers/test_autopilot_dispatch.py:75`/`:98`（字段存在 / 缺省省略）。
  - `packages/multi-workers/test_autopilot_conductor_exec.py:939-960`（任务 body 逐字节）。

### F3 auto-detect 提案（位置/输入/误报/优先级）
- 建议层：**只在 TS 派发面做**（共享一个 `detectImageNeed(cwd, description)` 纯函数）。理由：能力判据必须有 registry，`dispatch_worker` 的 `_context?.modelRegistry` 已传入 `planDispatchFrontmatter`（`ui-bridge.ts:1247`）；Python conductor 无 registry（AC-008 fail-open + AC-011 worker 兜底已覆盖）。落点：`ui-bridge.ts:1239` 之前（拒绝要先于 `mkdirSync` `ui-bridge.ts:1253`）。
- 输入：任务描述全文（dispatch_worker 解构于 `ui-bridge.ts:1159`；`/worker` `ui-bridge.ts:1581`）+ `projectDir`（`ui-bridge.ts:1109`，即 `path.dirname(agenticdocRoot)`）。
- 判定：抓 `<path>\.(png|jpe?g|webp|gif|bmp)` token，`fs.existsSync(path.resolve(cwd, token))` 为真才命中；扩展名集与 `packages/coding-agent/src/core/tools/read.ts:212` 声明的支持集同源。注意 `read` 实际按**内容签名**判 MIME（`utils/mime.ts:6-22`），扩展名只是派发面廉价启发式。
- 误报面：`生成的 png`、`*.png` 通配、URL/图片链接、代码/文档散文里的路径、不存在的路径、backtick 示例。缓解：不存在即不算（覆盖"生成的 png"）；token 含 `* ? [ ]` 跳过（覆盖通配）；含 `://` 跳过（URL）；大小写不敏感。
- 优先级（高→低）：显式 `images: no`（豁免）> 显式 `images: yes`（强制门禁）> auto-detect 命中（等价 yes）> 都无（不写行、零 I/O）。拒绝消息给出 `images: no` 豁免写法（spec 风险 3）。

### F4 零字节不变量
- 可复用断言位置：
  - Python 最强范式：`test_autopilot_readcap_injection.py:171-195` 的 `_head_module()` 从 `git show HEAD:packages/multi-workers/autopilot/dispatch.py` 加载改造前渲染器；`:634`/`:655` 逐字节对照；`:885` `test_baseline_left_end_bound` 用 sha256 把冻结副本钉到 HEAD blob。→ 新增 `images` 参数后，省略/空值时 `render_task_md` 输出必须与 `_head_module().render_task_md(同参)` 逐字节相等。
  - TS：`rag-required.test.ts:179` 的 `expect(omitted.frontmatter).toBe("type: coding\n")`（frontmatter 级 golden）；`agent-team-loop.test.ts:5334`（整文件级 golden）。另注意 `task-dispatcher.ts:281` 仅在 `out !== original` 时写盘，故未声明时 profile/RAG 注入也必须直通不写。
- 推荐：仿 `test_rag_phase.py:50-62` 的三等式 `omitted == explicit_empty == GOLDEN`；`images` 的 `undefined`/`""`/未传三种调用产生同一字节。不要只写 `not.toContain("images:")`（P-016 空断言）。

### F5 VC 候选（机器可判定）
1. **未声明零字节**：`render_task_md(images=None/"")` == `_head_module()` 同参输出 == `test_rag_phase.py` GOLDEN；TS `planDispatchFrontmatter({无 images})` == `"type: coding\n"`；真实 dispatch_worker（无图片描述）task.md == `"type: coding\n\nwork\n"`。
2. **声明且真实路径产生**：dispatch_worker tool `execute`（非 fixture 手写）传 `images: yes`（或描述引用存在的 png）+ 视觉模型 → task.md 含 `^images: yes$` 且 `_workers.parallel` 新增 1 行。
3. **门禁拒绝**：模型 `input` 不含 `image` + 声明 → 消息含 `images` 与 `mw model set vision`，`_workers.parallel` 行数不变，任务目录不存在。
4. **`images: no` 豁免**：描述引用存在的 png + `images: no` + 纯文本模型 → ok，队列 +1 行。
5. **fail-open**：`codex_cli/...` 或 registry `undefined` + 声明 → ok + 队列 +1 行（与 `validateModelValue` 同契约）。
6. **worker 兜底**：`images: yes` + 运行模型无视觉 → `worker.log` 含 `[IMAGE-CAP]` + 模型 id + 非零退出；未声明任务不受影响。
7. **顺序不变量**：`type < phase < images < model` 在 TS 与 Python 两侧断言一致（防双侧漂移）。

### F6 数据缺口
- auto-detect 命中是否写 `images: yes`（影响 AC-009 归因与 AC-011 触发面）：未定 → 需 spec 落定。
- `images:` 精确排序位（`phase:` 后 vs `model:` 后）：未定 → 需与两侧顺序一起 freeze。
- Python conductor 是否需独立能力门禁：本调研判"不需要"（无 registry；AC-008 + AC-011 覆盖），需 spec 确认。
- `model-reason:` 无读者：属独立问题，本 key 仅记录不改。
- 扩展名启发式 vs `read` 内容签名判定：伪造扩展名会漏/误报，需在 spec 注明。

## 结论 → 决策映射
- F1 → 支持并升级 spec 风险 1：本 key 必须交付写侧（`ui-bridge.ts:1040-1088` + `dispatch.py:296-317`）+ 读侧（`worker-mode.ts:268-328`、`state.py:151`、`launcher.py:143`、`mw.py:1786`、`task-dispatcher.ts:115`）双侧；端到端用例必须走真实 `dispatch_worker`。
- F2 → design 须把 `images:` 定为条件渲染；新增一行会命中上列 7 个 golden 文件，plan 要点名。
- F3 → 待确认 2 的实现建议：TS 单侧 auto-detect + 显式 `images: yes|no`；`images: no` 最高优先；扩展名集与 `read.ts:212` 同源。
- F4 → AC-009 用 git-HEAD 冻结渲染器（Python）+ 整文件 golden（TS）双锚，禁用空断言。
- F5 → AC-006/007/008/009/011 的 VC 已可机器判定；VC-1/2 覆盖"零字节"与"真实派发路径产生"两条硬要求。
- F6 → spec §4 待确认 2/3 各加一条落定；风险 3 的豁免串写入拒绝消息。

[VERIFY] 14 个头中 `timeout:`/`rag_chat_budget:`/`rag_time_budget_s:` 无写者（读侧 worker-mode.ts:275/322/326），`model-reason:` 无读者（写侧 ui-bridge.ts:1088）——P-005 空转在本仓是既成事实
[VERIFY] TS 落盘两处 ui-bridge.ts:1255 / :1642 共用 planDispatchFrontmatter(:1024)；Python 渲染器 dispatch.py:253，conductor 调用 :515
[VERIFY] 逐字节 golden 复用点：test_rag_phase.py:36、test_autopilot_readcap_injection.py:171/634/655/885、agent-team-loop.test.ts:5334、rag-required.test.ts:179
[VERIFY] auto-detect 建议仅 TS 派发面（projectDir=ui-bridge.ts:1109，registry=:1247），扩展名集与 read.ts:212 同源；`images: no` 优先级最高
