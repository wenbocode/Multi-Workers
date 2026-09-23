# Spec: mw-worker-progress-persist

> Key: mw-worker-progress-persist
> 创建时间: 2026-09-23
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建 Agent Team 协作框架…文件驱动的去中心化协调：_workers.parallel、_index.parallel、goal.md」中的**worker 证据落盘层**（每 worker 目录的 trace.log / output.md / progress.md）。触发事实：2026-09-23 `chroma-review-evidence-r1`（OverCode，`type: review`）与 `chroma-review-lifecycle-r1` 在 30/40/50 分钟检查点反复回复「会话工具面恒为 read/find/grep/ls，无法创建/追加 progress.md，请编排方代为追加」——框架要求的检查点自评通道对只读角色**物理不存在**，PM 只能事后从 session jsonl 手工代记。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器（协调通过文件系统）——本 key 不新增常驻服务状态，只改 worker 侧落盘行为与扩展代码。
  - GC-2: 不修改 pi 核心——全部用 Extension API（`pi.on("tool_call")` 拦截 / `registerTool` / `before_agent_start`）实现。
  - GC-3: Worker 进程级隔离 + 工具白名单按任务类型——本 key 不得给只读角色（review/research/verifier/reviewer）任何**任意路径**写能力；写入面必须限制在 worker 自身目录内的白名单文件名，且框架自有文件不可被 worker 工具覆写。
  - GC-4: 超时看门狗三段式（activity idle / 墙钟 / 30 分钟检查点）语义不变——本 key 只补充检查点的落盘与 steer 表达，不改判据数值。
- 冲突：无硬冲突。goal 的 Key Constraints 原文把 review 白名单写作 `read/find/grep/ls`；本 key 若要为只读角色增加「仅 worker 目录内落盘」的通道，是对该约束的**收窄式补充**（写入面远小于 coding 的任意 `write`），已在 §1.4 明示；若评审认为该补充不可接受，退回 §1.4 的「仅机器代记」最小面（AC-001~004 成立，AC-005~006 作废）。
- 预期收益：
  - 只读角色任务结束后 `progress.md` 真实存在且含机器检查点行（判定：任务目录存在该文件，`grep -c "CKPT"` ≥ 1）。
  - 只读角色不再被 steer 要求执行它没有的工具（判定：只读角色收到的 steer 文本不含「追加到 …progress.md」的写入指令，见 AC-004）。
  - 只读角色获得 worker 目录内的落盘通道（判定：trace.log 出现对应 `[TOOL]` 行且目标文件位于 worker 目录，见 AC-005/AC-006）。

## §1 功能概述

### 1.1 目标

修复「人工/机器检查点要求 worker 落盘 progress.md，而只读角色没有写工具」这一框架自相矛盾，使 worker 进度证据在只读角色任务中同样落盘，并让检查点 steer 文本按角色能力分化；同时为只读角色提供一条**受限于自身 worker 目录**的落盘通道（用于 progress.md 自评与报告文件），不破坏「被审代码只读」这一硬语义。

### 1.2 技术栈 / 语言

- TypeScript 扩展源码：`packages/coding-agent/src/extensions/agent-team-loop/**`（worker 模式主文件 `worker/worker-mode.ts`、`worker/output-writer.ts`、`shared/dispatch-models.ts`），bundle 产物 `packages/multi-workers/dist/extensions/agent-team-loop.js`（`mw build --install` 重建后对新 spawn 的 worker 生效）。
- Python 侧 parity：`packages/multi-workers/autopilot/dispatch.py` 的 `REGISTRY`（类型→工具元组），由 `packages/multi-workers/test_autopilot_l0.py::_parse_ts_allowlists` 解析 TS 源并锁定一致性。
- 测试：`packages/multi-workers/test_*.py`（pytest）、`packages/coding-agent/test/**`（vitest，含 `test/suite/` faux provider）。

### 1.3 核心用户场景

1. 场景 A（PM 派只读审查任务）：worker 到 30 分钟检查点，扩展代码把机器检查点行写入 `<key>/workers/<task_key>/progress.md`；PM 打开即有进度证据，无需代记。
2. 场景 B（worker 自评落盘）：只读 worker 收到 steer 后用窄工具把自己的 `CKPT <n>m converging=yes|no eta≈<X>m <理由>` 追加进 `progress.md`。
3. 场景 C（长报告落盘）：只读 worker 把报告写入 worker 目录内的报告文件（`report*.md`），结论不再只存在于最后一条消息（P-007 缓解）。
4. 场景 D（越界尝试）：worker 试图写 `../x.md`、`a/b.md`、`C:\abs\x.md`、`trace.log`、`task.md`、`output.md` → 被拒并记 trace。
5. 场景 E（coding 角色回归）：coding worker 行为与现状一致，不产生重复的 progress 行。

### 1.4 范围说明（不做什么）

- 不给 review/research/verifier/reviewer 开放任意路径的 `write`/`edit`；「被审源码只读」语义不变，P-007 采用的「长报告改派 coding 类型」实践不废除（本 key 提供的是通道，不是派发策略变更）。
- 不引入中心化调度器或服务端状态（GC-1）；不改 pi 核心（GC-2）。
- 不改超时/看门狗判据数值与升级路径（GC-4）；不改 `_workers.parallel` / `_index.parallel` 格式。
- 不保证 provider 流中断概率下降（P-007 主业是流中断与长消息单点故障，本 key 只保证结论有落盘位置）。
- 不做 `progress.md` 的机器消费/自动归档（PM 代记流程保留；本 key 只让文件存在且格式稳定）。

## §2 业务约束

### 2.1 平台 / 环境

Windows（主开发机）与 Linux/macOS 均须正确；路径判定不得依赖 POSIX 词法（P-004）。

### 2.2 性能指标

无新增常驻开销要求；检查点落盘为同步小文件追加（与既有 `trace.log` 追加同量级）。

### 2.3 安全约束

- 写入目标限定 `<key>/workers/<task_key>/` 目录内的白名单文件名；路径分隔符、`..`、绝对路径、UNC、大小写变体一律拒绝（fail-closed）。
- 框架自有文件（`task.md`、`trace.log`、`worker.log`、`output.md`）**不可**被 worker 工具写入或覆写（否则可伪造机器证据）。
- 拒绝事件必须留痕（trace 行），供 PM 与审计核对。

### 2.4 集成依赖

- 与 `TOOL_ALLOWLISTS`（TS）/`REGISTRY`（Python）的 parity 锁同步（新增工具或改白名单必须两侧同时改）。
- 与 `applyRagTools` 的 allowlist 重算机制兼容（`before_agent_start` 每次重算完整集合，保持幂等，D-002）。
- 与 read-scope / protected-config 拦截器共存（同一 `tool_call` 事件上的多处理器顺序与 block 语义）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-23，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在只读角色（review/research/verifier/reviewer）worker 到达检查点时刻（含测试中缩短的锚点）时，`<key>/workers/<task_key>/progress.md` 存在且含 ≥1 行以固定机器前缀开头的检查点行（形如 `CKPT <n>m [machine] reads=<r> writes=<w> risk=<low\|mid\|high>`）。 |
| AC-002 | 同一 worker 连续到达 K 个检查点后，`progress.md` 机器行数恰好为 K，且此前已存在的内容（worker 自评行或 PM 代记内容）逐字节保留（append-only，不被覆盖）。 |
| AC-003 | coding/phase-writer/repair 等**有**写工具角色的 worker 到达检查点时，扩展不写机器行到 `progress.md`（`grep -c "[machine]"` = 0），其 steer 文本与现状逐字一致。 |
| AC-004 | 检查点 steer 文本按角色分化：无写工具角色收到的文本不含 `progress.md` 写入指令（不匹配 `追加到.*progress\.md`），且含明确的替代动作（窄工具名或「在回复中给出 CKPT 行」）；有写工具角色的文本与现状逐字一致。 |
| AC-005 | worker 通过窄工具写入 `progress.md`（append 模式）或报告文件（write 模式，文件名匹配白名单）时，目标文件位于 `<key>/workers/<task_key>/`，文件内容等于传入内容（append 为追加），且 `trace.log` 出现对应 `[TOOL]` 行。 |
| AC-006 | worker 通过窄工具请求以下目标时全部被拒（返回 block + reason），worker 目录内不产生新文件，且 `trace.log` 记录拒绝行：`../x.md`、`a/b.md`、`..\\x.md`、`C:\\abs\\x.md`、`\\\\unc\\share\\x.md`、`trace.log`、`task.md`、`output.md`、`worker.log`、空字符串、仅扩展名（`.md`）、超长名（>255 字节）。 |
| AC-007 | 角色工具集由单一来源决定：对每个已登记 type，`activeToolsForType(type)` 等于 `toolsForType(type)`，且仅在 `toolsForType(type)` 不含 `write` 时额外含窄工具名；`TOOL_ALLOWLISTS` 表本身与改造前逐项相等。 |
| AC-008 | TS `TOOL_ALLOWLISTS` 与 Python `REGISTRY` 的对应条目逐项相等（`test_autopilot_l0.py` / `test_autopilot_dispatch.py` / `test_rag_research.py` parity 用例全绿），且 `_parse_ts_allowlists` 仍能解析 `worker-mode.ts`。 |
| AC-009 | `npm run check` exit 0；新增用例（TS vitest + Python pytest）全绿；既有 suite 不新增失败（Windows 基线 89 项环境失败除外）。 |
| AC-010 | 变更记录与文档同步：`packages/coding-agent/CHANGELOG.md` 与 `packages/multi-workers/CHANGELOG.md` 的 `[Unreleased]` 各有对应条目；`packages/multi-workers` 中描述 progress.md / 检查点的文档与实现一致（符号名 grep 零悬空）。 |
| AC-011 | 真实派发冒烟：以 `type: review` 短预算任务（timi 路由）实跑一次，观察三点——(a) 任务目录 `progress.md` 含机器行或工具落盘行；(b) 收尾回复中不出现「无法写入 progress.md / 请编排方代为追加」一类文本；(c) `worker.log` 显示 `done exit=0`。 |

## §4 风险与未决项

- 风险 R-1：写入守卫在 Windows 路径语义下失效 → 只读角色可写被审代码（P-004 同族）。缓解：窄工具 + basename 白名单 + 任何含分隔符/盘符/UNC/`..` 的输入直接拒绝 + AC-006 反例矩阵。
- 风险 R-2：机器行与 worker 自评行格式混淆，PM/审计误判。缓解：机器行固定前缀 `[machine]`，AC-002/AC-003 锁格式与归属。
- 风险 R-3：给只读角色新增工具后，与 `applyRagTools` 的重算集合不一致 → worker 缺工具或拿到多余工具。缓解：沿用单一重算函数 + AC-007 现状一致性断言。
- 待确认（用户决策点，见评审问题）：
  - Q1：写入通道采用**窄工具**（专用 `progress`/`report` 工具，basename 白名单）还是 `write`/`edit` + 路径守卫（后者写入面更大、伪造风险更高）？[AI 推荐：窄工具]
  - Q2：白名单文件名集合 = `progress.md` + `report.md` / `report-*.md`？（是否放宽到任意 `*.md`，还是收紧到仅 `progress.md`）
  - Q3：机器检查点行是否对所有角色统一写（含 coding，可能与其自评行并存）还是仅限无写工具角色？[AI 推荐：仅限无写工具角色]

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- 扩展工具注册 + allowlist 重算范式：`rag/tools.ts` 的 `registerRagTools` / `applyRagTools`（`before_agent_start` 每次重算完整集合、幂等，D-002）——窄工具的注册与分发直接复用该形状。
- `tool_call` 拦截范式：`worker/worker-mode.ts` 的 read-scope 段（约 708 行）返回 `{ block: true, reason }` 并落 trace 拒绝行——写入守卫接同一事件。
- trace 写入器：`worker/output-writer.ts` 的 `appendCheckpoint` / `appendTool` / `appendToolError` / `appendTrace`——机器行与拒绝行复用同一写入层，不新造日志格式。
- 角色/类型到工具的单一映射：`worker/worker-mode.ts::toolsForType`（L89）——判定「角色是否有写工具」的唯一入口（不要在各调用点自行推断）。
- parity 测试 helper：`packages/multi-workers/test_autopilot_l0.py::_parse_ts_allowlists`（L215），被 `test_rag_research.py` / `test_autopilot_dispatch.py` 复用——白名单变更的回归锁现成。
- 已确立的 PM 侧约定：`progress.md` 由 PM 在 worker 结束后代记（OverCode `chroma-review-lifecycle-r1/progress.md` 先例）——本 key 不推翻该约定，只让机器/worker 侧也能落盘。

### 需规避坑点

- P-007（review 角色唯一交付通道是最后一条消息，长报告=单点故障）：本 key 直接对应其根因「无落盘通道」；落实时必须保留「被审代码只读」与缩小输出面的既有规避手段，不得把窄工具当成任意落盘能力。
- P-004（POSIX 词法分析在 Windows 路径上丢反斜杠 → 路径检查静默漏拦）：写入守卫必须覆盖反斜杠/盘符/UNC 反例，且用测试矩阵证明不是「绿但漏拦」（P-005 同族：只有读者没有写者的空契约）。
- P-005（跨语言契约只有读者没有写者）：白名单两侧 parity 必须同时有生产者与消费者，禁止只改一侧。
- P-003（`open(p,"w")` 先截断后求值 → 写/改文件静默清零）：append 语义实现不得先截断；机器行追加走既有 append 工具函数。
- P-010（用 Python 文本模式给源码打补丁翻转换行）：本 key 的源码改动只用 TS 侧编辑工具，不用 Python 脚本改 `.ts`。
- P-002（会话内修改跨窗口共享配置文件）：不碰 `~/.pi/agent` 下的共享配置；本 key 只改仓库源码。
