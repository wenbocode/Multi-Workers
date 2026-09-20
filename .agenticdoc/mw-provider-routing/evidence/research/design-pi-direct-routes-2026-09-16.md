# Research: pi 直连路由数据驱动化 + zai 接入（design）

## 决策问题

- §1 D-001：直连泛化的机制——「无 port=直连」启发式 vs 独立 pi_providers 段 vs 第 5 个硬编码分支
- §1 D-003：providers.json 中 timi/deepseek 的归属
- §1 D-004：zai 的派发入口形式

## 调研方法与出处

- `packages/multi-workers/launcher.py:192-260`（`_build_env` 四个硬编码直连分支：timi / openai-codex / anthropic+deepseek / codex CLI）
- `packages/multi-workers/launcher.py:368-408`（`_build_command`：timi 默认模型 glm-5.3；anthropic/openai-codex/deepseek 要求显式 model）
- `packages/multi-workers/mw_common.py:659-678`（`route_for`：未声明 port 时默认 7001——「无 port=直连」无法从返回值判定）
- `packages/multi-workers/mw_common.py:96`（`CLI_DEFAULT_PROVIDER = {"pi": "claude", ...}`）
- `packages/multi-workers/providers.json`（deepseek 键双重身份：pi 直连分支用 provider id "deepseek"，providers 段同名键带 port 7004 服务 CLI 代理路由）
- `packages/multi-workers/mw_common.py:113-124` + `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts:23-33`（prefix↔provider 双侧映射，文件头注释明确「keep both sides in sync」）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:325-341`（`pickWorkerRoute` 默认 `pi/timi`；`readModel` 直通 task.md `model:` 行）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:925,1219`（/worker 与 dispatch_worker 的 provider 列默认 timi，仅展示/传输用途）
- dispatch_worker 工具 schema（含 `model` 参数）——派发入口已支持任意模型值

## 发现

1. **直连已有四个硬编码分支**，每个新 provider 需同时改 `_build_env`（env 注入）、`_build_command`（flag 构造）两处硬编码 + prefix 双侧 map——这正是本 key 要消除的重复。
2. **「无 port=直连」启发式在 deepseek 上冲突**：providers.json 的 `deepseek`（port 7004）是 CLI 代理路由，而 pi+deepseek 是直连——同一键两种语义，启发式会把 pi+deepseek 错误送进 localhost:7004。
3. **route_for 的 port 默认值 7001** 使「路由是否声明 port」无法从返回值区分（declared-7001 vs default-7001）。
4. **派发链已完备**：task.md `model: zai/glm-5.3` → `_resolve_entry_model`（task.md model: 最高优先）→ `_effective_entry`（prefix 覆盖 provider）→ `_build_command`/`_build_env`。TS 侧 `/worker --model`、`dispatch_worker(model=)` 均已存在，**入口零改动**。
5. **direct provider「必须显式 model」已是现行语义**（`_build_command:386-392` 对 anthropic/openai-codex/deepseek 抛错），与用户裁定一致；timi 的 glm-5.3 默认是唯一例外。
6. **_stripped_env 现状**：剥离所有声明凭证 + providers 段 base_url_env；TIMI_BASE_URL 等直连 base_url 未经声明、会泄给非本路由 worker（无害但不整洁）。

## 结论 → 决策映射

- D-001 → 选**独立 `pi_providers` 段**（数据驱动，keyed by pi provider id）：消灭全部硬编码分支、天然解决 deepseek 双重身份（两段各自 keyed）、route_for/proxy 语义不变
- D-003 → timi/openai-codex/anthropic/deepseek 迁入 pi_providers（timi 带 `default_model: glm-5.3` 数据化）；providers 段收敛为纯 CLI 代理路由（claude/claude-cli/deepseek）
- D-004 → 派发入口零改动：复用 prefix 机制（`zai/glm-5.3`），prefix map 双侧加 `"zai" ↔ "zai-coding-cn"`
- 附带收敛：pi_providers 声明的 base_url_env 纳入 _stripped_env 剥离集（直连 base_url 不再泄给无关 worker）
