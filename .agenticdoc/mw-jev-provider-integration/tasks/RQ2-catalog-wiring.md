# RQ-2 — 仓内目录与接线调研:jev 现状、模型可见性断点、provider 架构

- key: mw-jev-provider-integration · type: research · SPEC 相位调研
- timeout: 40

## 上下文

goal.md（.agenticdoc/goal.md）Provider 路由架构。已知锚点: `packages/ai/src/providers/data/timi.json:1`（jev-latest 唯一 jev 条目）、`packages/ai/scripts/generate-models.ts:403`（TIMI_BASE_URL/TIMI_ZERO_COST/TIMI_RESPONSES_COMPAT 常量）、`packages/ai/src/models.generated.ts`（**grep 'jev' 零命中——生成产物里没有 jev，模型可见性可能断在这里**）。历史证据: `.agenticdoc/mw-timi-models-add/mini-spec.md`（jev-latest 429/unmapped 实测）。

## 审计目标（调研问题）

- Q1 `models.generated.ts` 的生成链：generate-models.ts 如何消费 data/*.json（TIMI_MODELS 数组？还是读 timi.json？）；jev-latest 为什么没进生成产物——是 TIMI_MODELS 硬编码数组漏了，还是生成后未重跑？
- Q2 模型可见性链路：`/mw --list-models`、窗口模型列表、`/mw model` 各自从哪个数据源读（generated vs data json vs dispatch.yml）；jev-latest 当前在各层可见性逐层给结论
- Q3 provider 架构：packages/ai 的 provider 注册（anthropic-messages/openai-responses 等 api 类型）与 baseUrl 解析；timi 代理（proxy_multi.py/llmproxy）在其中的位置；「直连路由 vs 代理路由」判定代码在哪（mw-provider-routing 交付）
- Q4 jev-latest 的 429：timiai.woa.com llmproxy 对 anthropic-messages 协议的 jev 路由现状——仓内有没有重试/限流处理，错误反馈到哪一层
- Q5 timi.json 的维护规则：手编还是脚本生成？加新模型的标准动作（对应 mini-spec batch 2 的做法与遗留问题）
- Q6 typesafe.ai 若为独立平台（非 timi 代理后端），仓内加一个「新 provider」的标准面是什么（对照 docs/custom-provider.md 与 docs/models.md）

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-catalog-wiring-20261016.md`（新建，全文中文，每条结论附 文件:行号）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-catalog-wiring-20261016.md`

## 写入禁止面

- 一切源码/配置；禁止 git add/commit

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\spec-jev-catalog-wiring-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t))"
```

## 交付格式

- 证据文件 + 六问逐条结论（文件:行号 证据）+ 「jev 跑通的断点清单」一节（按层：目录→生成→路由→调用→反馈）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
