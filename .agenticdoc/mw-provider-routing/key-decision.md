# KDR: mw-provider-routing

## R（需求）

- 技术栈: Python（mw/launcher/providers.json）+ 既有 TS 扩展派发面小改
- 边界: 不做 proxy 内化（Backlog）、不做外部 CLI 路由、不做 pi 侧 provider 注册、不动默认路由（timi 保持默认）
- 关键约束: 直连优先（无 port 路由 = 直连）；凭证 env+auth.json 双源、`_stripped_env` 隔离语义不变；新路由无默认模型、仅显式派发；zai-coding-cn 走 pi 既有原生 provider（零 pi 改动）

用户裁定（2026-09-16）：

1. 同时落地一个具体 provider（zai，OpenAI 兼容，见 docs/zai_guider.md + research note）
2. 按推荐：无默认模型、必须显式 `--model`；timi 保持默认路由
3. 仅支持显式 provider/model，不动回退链
4. zai 家族固定 `zai-coding-cn`：不引入裸 `zai`（国际端点），glm-* 模型在 mw 派发中一律解析到 zai-coding-cn 路由；AC 已于 2026-09-16 锁定

## A（架构）

- D001 zai 接入方式: 选 C 第 5 个硬编码分支（用户裁定先落地 C），否 A pi_providers 泛化（回归面大拆后续 key）/ B 无 port 启发式（deepseek 双重身份）
- D002 zai 路由: 选 zai-coding-cn + prefix zai，否裸 zai（用户裁定消歧）
- D003 派发入口: 选零改动复用 prefix，否新增 --provider 旗标（入口已完备）
- D004 无 port 语义: 选确认现状即用，泛化推后续 key（与 D001 风险裁定一致）← system-design 追加

## I（实施）← PM 执行中追加
