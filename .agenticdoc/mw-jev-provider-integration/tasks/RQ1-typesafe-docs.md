# RQ-1 — typesafe.ai 文档调研:jev 模型的 API 契约与 coding-agents 接入

- key: mw-jev-provider-integration · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（.agenticdoc/goal.md）Provider 路由架构（mw-provider-routing DONE：直连路由泛化 + 可选代理）。本 key 目标：jev 模型跑通能用 + 决策面友好。仓内现状：`packages/ai/src/providers/data/timi.json:1` 已有 `jev-latest`（api=anthropic-messages，baseUrl=timi 代理 llmproxy，reasoning=true，text-only，200K ctx）；历史 mini-spec（.agenticdoc/mw-timi-models-add/mini-spec.md）记录：anthropic /v1/messages 实测 **429 rate limit**、openai /responses 报 **Unmapped LLM provider**（jev 在 timi 代理上未映射 responses 协议）。

## 审计目标（调研问题）

资料源（用 bash curl 拉取，禁长输出回灌：HTML 转 text 后落盘再 tail）：
1. https://docs.typesafe.ai/introduction — 平台定位、鉴权方式（API key 形态/头）、base URL
2. https://docs.typesafe.ai/introduction/quickstart — 首个请求的端点与最小参数、响应形状
3. https://docs.typesafe.ai/introduction/coding-agents — coding-agent 接入指引（协议兼容性：anthropic-messages / openai-chat / openai-responses？专用端点？）
4. https://docs.typesafe.ai/concepts/use-case-map — 能力/模型族映射（jev-latest 对应哪个 use-case 桶）

要回答的问题：
- Q1 端点契约：chat/completions 走哪个协议族？与 packages/ai 现有 api 类型（anthropic-messages / openai-responses / openai-chat-completions）哪个对齐？
- Q2 鉴权：header 形态（Authorization Bearer / x-api-key / 自定义）、是否需要团队/项目维度凭据
- Q3 模型族与 id：jev-latest 之外还有哪些模型 id？各自 reasoning/input/contextWindow 参数
- Q4 限流与配额：429 的官方说法（RPM/TPM/并发）与建议重试语义
- Q5 reasoning/thinking 参数的官方拼写与透传方式
- Q6 流式支持（SSE 事件形状是否与标准协议一致）
- Q7 coding-agents 页面对接 pi 类 agent 的具体建议（env、base_url、model 字符串格式）

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-typesafe-api-20261016.md`（新建，全文中文；原始 HTML 不落仓，转 text 摘录关键段 + 每条结论附来源 URL 锚点）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-typesafe-api-20261016.md`

## 写入禁止面

- 一切源码/配置；禁止 git add/commit；禁止把 HTML 原文整页粘进证据文件（只留关键摘录）

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\spec-typesafe-api-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6','Q7'] if q in t))"
```

## 交付格式

- 证据文件 + 七问逐条结论（每条：结论一句 + 官方原文摘录 ≤3 行 + URL）+ 「对 packages/ai 的接线建议」一节（对齐哪个 api 类型、缺什么）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
