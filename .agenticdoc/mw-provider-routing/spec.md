# Spec: mw-provider-routing

> Key: mw-provider-routing
> 创建时间: 2026-09-16
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: legacy-确立，三段有真内容）

- 对齐：本 spec 服务于 goal「PM Agent 管理多个 Worker Agent 并行开发同一个项目」中的**多 provider 并行调度能力**——worker 不再绑定单一 timi 路由，可按任务派发到 zai（GLM）等直连 provider。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器（文件驱动协调）——本 key 不触碰协调层
  - GC-2: 不修改 pi 核心——zai-coding-cn 为 pi **既有**原生 provider（`packages/ai/src/providers/zai-coding-cn.ts`），零 pi 侧改动
  - GC-3: Worker 进程级隔离——派发路径不变
  - GC-4: 凭证隔离（每个 Worker 只拿到它需要的 API key）——AC-003 直接落实
  - GC-5: 工具白名单按任务类型——不涉及
- 冲突：goal Context 写「LLM 代理基于 timi-proxy-cli，为不同 CLI 类型提供隔离的本地代理端口」。本 key（连同已交付的 `mw-proxy-on-demand`）将该定位**修订为可选件**（仅「外部 CLI + 协议翻译」场景）；主路径为直连。处理方式：goal.md 本身不动（低频变更文档），演进记录于本 spec §0 与 mw-proxy-on-demand 交付物；proxy 内化留在 README Backlog。
- 预期收益：PM 可显式派发 glm-5.3 worker（直连 `open.bigmodel.cn`），摆脱单一 timi 路由的单点依赖。判定方式：AC-005 真实冒烟通过 + 既有 timi 路由全量回归绿（AC-007）。

## §1 功能概述

### 1.1 目标

1. **直连泛化**：`launcher._build_env` 的 timi 直连特判（AC-008 分支）泛化为「providers.json 中无 `port` 字段的路由 = 直连」——注入该路由 `api_key_env` + `PI_WORKER_TASK`，不设任何 localhost base_url。
2. **落地 zai-coding-cn**：providers.json 增凭证链（env `ZAI_CODING_CN_API_KEY` → auth.json field `zai-coding-cn.key`）与无 port 路由条目；PM 可显式派发该路由的 pi worker（模型 glm-5.3 系列）。

### 1.2 技术栈 / 语言

Python（`packages/multi-workers`：providers.json / launcher.py / 测试）；既有 TS 扩展派发面（`/worker`、`dispatch_worker`）按需小改（形式由 design 决定）。

### 1.3 核心用户场景

1. **显式派发**：PM 在 pi 窗口以显式 zai-coding-cn 路由派发编码 worker（`--model glm-5.3`），worker 进程直连 `open.bigmodel.cn` 完成任务。
2. **凭证配置**：运维在新机器配 key——设 env `ZAI_CODING_CN_API_KEY` 或在 pi 窗口外写 auth.json 的 `zai-coding-cn` 条目。
3. **可观测**：`mw doctor` / serve 预检列出 `route zai-coding-cn: available/missing` 及来源。

### 1.4 范围说明（不做什么）

- 不包含：proxy 内化（留 Backlog）、外部 CLI（claude/deepseek CLI）路由、pi 侧新 provider 注册、默认路由切换（timi 保持默认）、模型目录扩充
- 不包含：`/worker` 派发面 UI 改动超出「能显式指定该路由」的最低需求

## §2 业务约束

### 2.1 平台 / 环境

Windows + Linux（launcher 泛化平台无关；端点 `https://open.bigmodel.cn/api/coding/paas/v4` 为 pi 目录既定）。

### 2.2 凭证

双源：env `ZAI_CODING_CN_API_KEY` 或 auth.json `zai-coding-cn.key`（写入必须在 pi 窗口外，P-002）。多 provider 并存沿用 `_stripped_env` 隔离语义（其他 provider 凭证全部剥离）。

### 2.3 派发语义（用户裁定）

- 新路由**无默认模型**：派发必须显式 `--model`
- **不进默认/回退链**：不指定 provider/model 时仍走 timi 默认
- 仅支持显式指定，不改回退逻辑
- **zai 家族固定 `zai-coding-cn`**：mw 路由层不引入裸 `zai` provider（国际端点），glm-* 模型在 mw 派发中一律解析到 zai-coding-cn 路由，消除裸模型 ID 重名歧义

### 2.4 集成依赖

pi 原生 zai-coding-cn provider（glm-4.7 / glm-5-turbo / glm-5.2 / glm-5.2-highspeed / glm-5.3 / glm-5.3-flash / glm-5.3-highspeed，openai-completions API，thinkingFormat "zai"）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-16T16:30:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 providers.json 含无 `port` 路由 R 且 R 凭证链解析成功的条件下，`_build_env`（pi worker，provider=R）返回的 env 满足：`env[R.api_key_env]` 等于解析到的凭证值、不含任何 `localhost` base_url 条目、含 `PI_WORKER_TASK` |
| AC-002 | 在路由 R 无 `port` 且其凭证链解析失败的条件下，`_build_env` 抛 `RuntimeError`，异常消息同时含路由名与 `describe_missing` 的缺失描述 |
| AC-003 | 在派发 provider=zai-coding-cn 的 pi worker 的条件下，worker env 不含 `ANTHROPIC_API_KEY`、`ANTHROPIC_AUTH_TOKEN`、`DEEPSEEK_API_KEY`、`TIMI_API_KEY`（除 `ZAI_CODING_CN_API_KEY` 与 worker 通用变量外无其他凭证） |
| AC-004 | 在 providers.json 含 zai-coding-cn 凭证链的条件下，`route_precheck` 输出的 routes 含 `zai-coding-cn` 条目：有凭证时 `available=true`，无凭证时 `available=false` 且 `missing` 为描述文本 |
| AC-005 | 在 zai-coding-cn 凭证存在且 PM 以显式 zai-coding-cn 路由派发 pi worker（模型 glm-5.3，预算 ≥1024 token）的条件下，worker 以 `pi --provider zai-coding-cn` 启动、对 `open.bigmodel.cn` 完成至少一次真实模型往返、任务以退出码 0 结束（e2e_real 标记，默认 deselect） |
| AC-006 | 在派发时不指定 provider 与 model 的条件下，worker 路由仍为 timi：env 含 `TIMI_API_KEY` 且不含 `ZAI_CODING_CN_API_KEY` |
| AC-007 | 在 multi-workers 全量 pytest 运行的条件下，0 failed（deselect 维持 8，passed 数随新增用例 ≥433 递增） |
| AC-008 | 在仅 zai-coding-cn（无 `port`）路由有凭证的条件下，`cmd_serve` 判定 proxy_routes 为空、不 spawn proxy 子进程（on-demand proxy 语义对无 port 路由保持） |

## §4 风险与未决项

- **风险**：`docs/zai_guider.md` 含明文 API key 且未被 git 跟踪——必须保持不入库；key 落地 auth.json 后建议将该文档脱敏。
- **已裁定（原待确认）**：TS 派发面（`/worker`、`dispatch_worker` 工具）的显式路由入口形式由 design 决定（新增 `--provider` 旗标 vs 模型前缀映射）；用户已裁定 zai 家族固定 `zai-coding-cn`，裸 `zai` 不引入，glm-* 重名歧义在 mw 层面消解。
- **风险**：glm-5.3 为 thinking 模型，小 `max_tokens` 会被思考预算耗尽（探针实证 8 token 全被吃）——AC-005 已设预算下限。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `launcher._build_env` 的 timi 直连分支（AC-008 特判）——泛化的直接基础
- `mw_common.route_precheck` / `resolve_credential` / `describe_missing`——已按 providers.json 泛型，零改动
- `_stripped_env` 凭证隔离——已覆盖任意声明的凭证链
- pi 原生 zai-coding-cn provider + glm-5.3 系列模型目录——零 pi 侧改动
- `test_serve_doctor.py` 的 hermetic `TEST_*` 凭证模式——新测试沿用，不依赖真机凭证
- `add-llm-provider` 技能——未来接私有网关时的完整流程（本 key 不需要）

### 需规避坑点

- P-001：`.agenticdoc/` 一切 UTF-8 文本写入用 write 工具或 Python `encoding="utf-8"`，禁 PowerShell 文本管道读-改-写
- P-002：auth.json 凭证写入必须在 pi 窗口外（`pi /login` 或普通终端）；测试一律不写真 `~/.pi/agent/auth.json`
- 测试凭证 hermetic 化：不依赖开发机真实 env / auth.json（既有教训见 `test_proxy_service.py` 对真实 providers.json 的依赖曾导致的队列错位风险）

> 调研留底：`evidence/research/spec-zai-direct-2026-09-16.md`（端点双验证、provider 选型、泛化点、pi 侧零改动论证）
