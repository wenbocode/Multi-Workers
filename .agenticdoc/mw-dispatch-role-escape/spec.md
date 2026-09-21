# spec: mw-dispatch-role-escape

> key: mw-dispatch-role-escape
> 类型: 缺陷修复（派工契约）
> 输入: H:\git\E2Feature 实际派工审计（2026-09-20）+ 本仓代码核查

## §0 Goal Alignment

- **对齐**：本 key 修复「PM 派工绕过项目声明的模型策略」这一缺陷，直接服务于 project goal 的
  「PM Agent 管理多个 Worker Agent」与「文件驱动的去中心化协调」——`.mw/dispatch.yml` 是策略文件，
  若派工链路可以静默绕过它，goal 中「项目级目标对齐」的前提就不成立。
- **GC 继承**：遵守 goal 的 Key Constraints「不修改 pi 核心：所有功能通过 Extension API 实现」
  （改动落在 agent-team-loop 扩展 + mw Python 侧，不触碰 pi core）与「工具白名单按任务类型」
  （`type:` 同时是白名单与 role 的输入，本次只补齐可达性，不改白名单内容）。
- **冲突**：与 goal 无冲突。与既有设计约定有一处**有意偏离**：`mw-dispatch-models` 记录过
  「dispatch.yml 解析失败永不阻断派发」。本次对**语法可解析但模型 id 不合法**的 role 值采取
  拒绝派发（fail-closed），理由与逃生口见 §2.4。
- **预期收益**：判定方式为「一次真实派工的证据链」——(1) pi 任务可以声明 `type: review`，
  `dispatch.yml` 的 review 档首次真正可达；(2) 任何偏离 role 默认值的模型覆盖都会在 task.md 留下
  `model-reason:` 并在工具结果/通知中回显「role 默认 X → 覆盖为 Y」；(3) 非法模型 id
  （如 `timi/gpt-5.6.sol`）在派发时被拒绝而不是被 pi 静默当 custom model id 使用。
  量化口径：E2Feature 的 14 个 worker 任务中，`type:` 与 `model:` 的一致性可从 task.md 单文件判定，
  不再需要 PM 自述。

## 1. 问题

E2Feature 窗口审计（用户报告 + 本仓核查）暴露三段链路缺陷：

1. **role 不可达（根因）**：`dispatch_worker` 与 `/worker` 都用
   `cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding"` 推导 task.md 的 `type:`。
   pi 永远得到 `coding`，于是 `.mw/dispatch.yml` 的 `review`/`research` 档对 pi worker **不可达**，
   worker 工具白名单也永远是 coding 那套。PM 想按 review 档跑，只能手填 `model:` —— 逃逸因此产生。
2. **覆盖无痕**：`dispatch_worker` 的 `model` 参数直写 task.md `model:`（解析链最高优先级），
   不校验、不需要理由、不回显偏离；工具结果文本还把类型印成 `type: <cli>`（`cli` ≠ `type`）。
3. **值不校验**：`timi/gpt-5.6.sol` 这类不存在的 id 在 pi 侧被
   `core/model-resolver.ts#buildFallbackModel` 静默当作 custom model id 使用（只有 warning），
   请求照发；派发侧（TS/Python）都不做 id 校验。

**实际后果**（E2Feature）：14/14 worker 任务带 `model: gpt-5.6-sol`（含 `type: coding` 的实现类任务），
`.mw/dispatch.yml` 的 coding 档被完全架空；配置里 `review: timi/gpt-5.6.sol` 是错 id 却无人发现。

## 2. 范围与契约（用户裁定：方案 1 = 保留覆盖能力，但必须强制理由 + 显式回显）

### 2.1 类型可声明（补回丢失的路径）

- `dispatch_worker` 新增可选参数 `type ∈ {coding, review, research}`，写入 task.md 的 `type:`。
- `/worker` 新增 `--type <t>`（并可配 `--reason <text>`），语义与校验一致。
- 省略时保持既有推导（pi→coding、claude→review、codex→codex），历史行为字节级不变。
- 非法值 → 拒绝派发（不建目录、不写队列行），消息列出合法值。

### 2.2 覆盖必须留痕（方案 1 的核心）

- `dispatch_worker` 新增可选参数 `model_reason`；`/worker` 对应 `--reason`。
- 触发条件：`.mw/dispatch.yml` 对「本次解析出的 role」配置了默认值，且请求的 `model` 与之不同。
  此时缺 `model_reason` → 拒绝派发，消息点名 role 默认值。
- 接受后：task.md frontmatter 记 `model-reason: <单行>`；工具结果/通知回显
  「role 默认 X → 覆盖为 Y（reason）」。
- 若请求的 `model` 与 role 默认值**相同**：不写 `model:` 行（配置保持唯一事实来源），结果说明
  「模型来自 dispatch.yml <role>」。
- 无配置（`.mw/dispatch.yml` 不存在或无该 role）时 `model` 覆盖不强制理由；提供了 `model_reason`
  则照样记录。

### 2.3 值必须校验（pi 路由）

- 校验对象（两处，都在派发时）：
  (a) 显式 `model` 参数；
  (b) 未显式指定时，`.mw/dispatch.yml` 中该 role 的默认值。
- 规则：`prefix/model-id` 的 prefix 属于 pi provider 族（timi/claude/codex/deepseek/zai）时，
  必须能在 `ctx.modelRegistry` 中按 `(providerId, modelId)` 找到；裸 id 按任务的 provider
  （pi 任务为 timi）校验。
- 校验不通过 → 拒绝派发，消息给出该 route 的候选 hint（`/mw model set` 或 `pi --list-models`）。
- 不校验：`codex_cli/`、`claude_cli/` 前缀与 cli ≠ pi 的任务（各自 CLI 拥有自己的模型表）。

### 2.4 与「配置不阻断派发」原则的关系

`mw-dispatch-models` 确立的语义是：dispatch.yml **解析失败**（unreadable / 结构错 / 未知 role）
永不阻断派发，doctor 只出建议。本 key 不改这条。新增的拒绝仅针对**可解析但模型 id 不存在**的
role 值，属语义错误而非便利性配置；逃生口：显式传 `model`（此时 role 默认值不参与解析，2.3(b) 不触发，
2.2 要求同时给出 `model_reason`）。

### 2.5 Launcher 侧证据

- Python `_resolve_entry_model` 增加 role 默认值对比：task.md 显式 `model:` 且与配置 role 默认值不同
  时，launcher 追加 `[launcher] <task_key>: model-override task=<X> config:<role>=<Y>`（写 launcher.log）。
- 派发行为不变：显式值仍然获胜（链路顺序不动）。

## 3. 验收标准（AC）

- **AC-001**：`dispatch_worker` 接受 `type ∈ {coding, review, research}`，task.md 写入该值；
  省略时 pi→`coding`、claude→`review`、codex→`codex`（与改动前一致）。
- **AC-002**：`type` 取非法值 → 工具返回拒绝消息且列出合法值；`.agenticdoc/<key>/workers/<task>/`
  与 `_workers.parallel` 均无新增行。
- **AC-003**：`/worker <cli> --type <t> ...` 与 `dispatch_worker` 同集合、同校验、同写入语义；
  notify 回显真实 type。
- **AC-004**：当 dispatch.yml 为解析出的 role 配置了默认值且请求 `model` 与之不同时，缺
  `model_reason` → 拒绝派发，消息包含该 role 默认值；不产生半成品 task.md 或队列行。
- **AC-005**：请求 `model` 等于配置的 role 默认值时，task.md **不含** `model:` 行，结果文本说明
  模型来自 dispatch.yml 的该 role。
- **AC-006**：接受覆盖时 task.md frontmatter 含单行 `model-reason: <text>`；含换行的 reason
  被规范化为单行（或拒绝），不得破坏 frontmatter 结构。
- **AC-007**：pi 任务的模型值校验：`timi/gpt-5.6.sol`（registry 中不存在）→ 拒绝并给出修正提示；
  `timi/gpt-5.6-sol`、裸 `gpt-5.6-sol`（provider timi）→ 通过；未知 prefix → 拒绝；
  `codex_cli/*` 与 cli ≠ pi 的任务跳过校验。
- **AC-008**：一次成功派工的结果/通知包含：解析出的 `type` 与 role、配置 role 默认值（或 `unset`）、
  覆盖时的「role 默认 X → 覆盖为 Y」。
- **AC-009**：手工写入的 task.md `model:` 与配置 role 默认值不同时，launcher.log 出现
  `model-override task=<X> config:<role>=<Y>`；worker 仍按显式值启动（行为不变）。
- **AC-010**：回归——不传新参数时，task.md frontmatter 与改动前逐字节相同；既有
  dispatch_worker / `/worker` / launcher 模型链测试全部通过。
- **AC-011**：文档同步——`packages/coding-agent/CHANGELOG.md` 与
  `packages/multi-workers/{README.md,CHANGELOG.md}` 记录 `type`、`model_reason`、pid/role 校验规则与
  2.4 的 fail-closed 例外。

## 4. 非目标

- 不改模型解析链顺序（task.md `model:` 仍最高优先级）。
- 不改 `dispatch.yml` 的 schema、role 集合、prefix 映射。
- 不删除 `model` 覆盖能力（用户明确选方案 1）。
- 不改 worker 工具白名单内容、不动 pi core。
- 不做「派工前自动改写 dispatch.yml」这类隐式修复。

## 5. 需规避坑点

- **P-001（PowerShell UTF-8 往返损坏）**：本 key 全部 `.agenticdoc/` 与源码文本写入走 write/edit 工具
  或 Python 显式 `encoding="utf-8"`；禁止 PS `Get-Content`/`Set-Content`/`WriteAllText` 往返。
- **P-002（会话内改共享凭证文件）**：本次不触碰 `~/.pi/agent/*`；不新增任何写 auth.json/models.json 的路径。
- **新增坑点（本 key 观察，待归档）**：`model:` / `type:` 是 launcher 与 worker 两侧共用的 task.md 契约，
  任何新键（`model-reason:`）必须不与既有正则冲突——`_read_task_md_fields` 用 `^model:`、
  worker `parseTaskMd` 用 `type:` 前缀匹配，`model-reason:` 两者都不匹配（设计 D-003 已锁定该口径）。

## 6. 可复用资产

- `shared/dispatch-models.ts`：`parseModelValue` / `PREFIX_TO_PROVIDER_ID` / `readMainModelConfig`
  的「严格手写解析 dispatch.yml，保持 bundle 无 yaml 依赖」模式——本 key 复用为 `readRoleModel(cwd, role)`。
- `extension ctx.modelRegistry.find(provider, id)`：已在 `applyMainModelConfig` 用于校验 `main` role，
  本次复用为派发期 id 校验，无需引入模型表读取代码。
- `mw_common.py` 的 `TASK_TYPE_TO_ROLE` + `resolve_dispatch_model` 链：TS 侧只做「解析 + 校验 + 留痕」，
  role→模型的实际解析仍由 Python 单点负责，避免双侧各写一份解析逻辑。
- 测试基建：`test/extensions/agent-team-loop.test.ts` 的 `fakeCmdPi()` / `writePhaseDocs()` /
  `fakeCmdCtx()`；Python 侧 `test_dispatch_models.py` 的 `_entry` / `_project` hermetic fixture。
