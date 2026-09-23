# KDR: mw-implementation-gate

## R（需求）
- 技术栈: TypeScript（pi 扩展）+ Markdown（框架 SKILL.md）
- 边界: 只做机械门禁（守卫 + 触发词）；AGENTS.md 仓级规则已先行落地（用户批准的 #3，独立交付）；turn hook 提醒有天然挂点才做
- 关键约束: 不改 pi 核心（GC-1，Extension API 实现）；_index.parallel 只读判定（P-002）；守卫不可静默绕过（mini 须留审计）
- 背景: 本会话两轮野生实施实证（ue-toolchain key 补登记含完整偏差留底）

## A（架构）
- 待 W1（pi Extension API 拦截点）+ W2（P-002 守卫先例）调研结论定形态：硬拦截 / 事后审计
- 代码路径白名单 + active key claim 判定（读 _index.parallel，claim_id=host:pid）
- mini fast path 声明机制 + 审计记录（追加写）

## I（实施）
- [先行落地] AGENTS.md「AgenticTask Workflow」节（#3，用户批准 "做" 时立即生效，不属本 key AC）
- [进行中] W1/W2 research 派发 → design → plan → tasks → 实现
