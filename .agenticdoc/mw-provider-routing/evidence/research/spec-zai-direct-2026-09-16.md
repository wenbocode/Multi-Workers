# Research: zai 直连路由接入 + 直连泛化（spec）

## 决策问题

- §1 范围：本 key 同时落地的具体 provider 是哪个、走哪条接入路径
- §2 约束：端点/鉴权/凭证链/派发语义
- §4 风险：明文 key、pi 侧改动面

## 调研方法与出处

- 用户输入：`H:\git\Multi-Workers\docs\zai_guider.md`（ZAI 智谱 BigModel key + curl 示例，模型 glm-5.3）
- pi 原生支持事实：`packages/ai/src/providers/data/zai.json`、`packages/ai/src/providers/data/zai-coding-cn.json`、`packages/ai/src/providers/zai-coding-cn.ts:11`
- mw 接线事实：`packages/multi-workers/launcher.py`（`_build_env` AC-008 timi 直连特判、`_stripped_env` 隔离）、`packages/multi-workers/mw_common.py`（`route_precheck`/`resolve_credential` 泛型凭证链）、`packages/multi-workers/providers.json`（timi 直连路由先例：无 port 字段）
- 实验（2026-09-16，真实 key 双端点探针，max_tokens=8）：
  - `POST https://open.bigmodel.cn/api/paas/v4/chat/completions` → 200，model 回显 glm-5.3
  - `POST https://open.bigmodel.cn/api/coding/paas/v4/chat/completions` → 200，model 回显 glm-5.3
  - （content 为空系 8 token 预算被 thinking 消耗，非失败）

## 发现

1. **provider 选型**：用户 key 属智谱 BigModel CN。pi 已原生支持两个 zai provider：
   `zai`（baseUrl `https://api.z.ai/api/coding/paas/v4`，env `ZAI_API_KEY`）与
   `zai-coding-cn`（baseUrl `https://open.bigmodel.cn/api/coding/paas/v4`，env
   `ZAI_CODING_CN_API_KEY`）。key 与 CN 域名匹配 → 选 **zai-coding-cn**。
2. **模型可用**：两个 provider 目录均含 glm-4.7 / glm-5-turbo / glm-5.2 / glm-5.2-highspeed
   / **glm-5.3** / glm-5.3-flash / glm-5.3-highspeed（openai-completions API，
   thinkingFormat "zai"，maxTokens 131072）。零 pi 侧改动需求。
3. **端点验证**：该 key 对 general（`/api/paas/v4`）与 coding（`/api/coding/paas/v4`）
   端点均有效（双 200）。pi 的 zai-coding-cn 走 coding 端点 → key 直接可用。
4. **mw 侧泛化点**：`_build_env` 目前仅 `cli == "pi" and provider == "timi"` 走直连
   （注入 `TIMI_API_KEY` + `PI_WORKER_TASK`，不设 base_url）；泛化为「路由无 `port`
   字段 = 直连」后，zai-coding-cn 只需 providers.json 加凭证链（env
   `ZAI_CODING_CN_API_KEY` → auth.json field `zai-coding-cn.key`）+ 无 port 路由条目。
   `route_precheck`/`doctor`/`_stripped_env` 均已按 providers.json 泛型，无需改动。
5. **proxy 不受影响**：serve 的 `proxy_routes` 只统计含 port 的 available 路由——
   新增无 port 路由不改变 proxy 行为（mw-proxy-on-demand 已交付语义）。

## 结论 → 决策映射

- §1 范围：落地 provider = zai-coding-cn（glm-5.3 系列），接入路径 = 纯 mw 接线
  （providers.json + `_build_env` 直连泛化），pi 侧零改动
- §2 约束：env `ZAI_CODING_CN_API_KEY` + auth.json `zai-coding-cn.key` 双源；
  凭证隔离沿用 `_stripped_env`；无默认模型、不进回退链（用户裁定）；timi 保持默认路由
- §4 风险：`docs/zai_guider.md` 含明文 API key 且未被 git 跟踪——必须保持不入库，
  key 落地后建议从文档脱敏并迁入 auth.json（窗口外操作，P-002）
