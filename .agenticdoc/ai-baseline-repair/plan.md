# Plan: ai-baseline-repair

> Key: ai-baseline-repair
> 模式: 轻量（5 任务 PM 直执，无 worker 派发）
> 任务拆分已在 design.md §3 定案，本 plan 补执行步骤与退出判据

## 执行顺序

T-01 → T-02 → T-03 →（T-05 可与其后任一并行）→ T-04（收口验证）

## T-01 src + 单点类型修（D-001/D-004/D-005）

1. cloudflare-ai-gateway.ts：镜像上游 `CloudflareAIGatewayApi` 别名 + `createProvider<CloudflareAIGatewayApi>` + 注释
2. timi-dispatch.test.ts:30：参数属性 → 显式字段 + 构造器赋值
3. openai-completions-tool-choice.test.ts:1410：compat union 窄化后取 `maxTokensField`，断言不变

退出：`npx tsgo --noEmit` 中这 3 处错误消失，其余错误数不变（26→23）

## T-02 model ID 映射全量执行（D-002，15 处）

1. 按 design 映射表执行 M1（上游镜像 5 处）/M2（点号 1 处）/M3（gateway 重定向 8 处 + describe 标题同步）
2. 跳过的上游 hunk（qwen-token-plan-individual ×6）在代码中不留痕，在 evidence 注记
3. 写 `tmp/verify-ids.py`：对每个新 ID 在 `data/*.json` 中断言存在（VC-005），跑完删除

退出：TS2345 全部消失（23→8，剩 cross-api）；脚本全绿

## T-03 cross-api 8 处（D-003）

1. fixture 补 `baseUrl` 等必填字段
2. `"end_turn"` → 按语境 `"stop"`/`"toolUse"`
3. `type === "stop"` → `type === "done"`，`.messages` → `.message`
4. 4 处 `as Record<string, unknown>` → 经 `as unknown` 或正当窄化

退出：tsgo 零错误（8→0）；diff 审阅注记无断言删除（VC-006）

## T-04 验证链 + 运行时失败 + 预防文档（D-006/D-008）

1. `npx tsgo --noEmit`（0 错）→ `npm run check`（exit 0）
2. packages/ai 套件（包内 vitest --run）；8 个预存运行时失败逐个：修复 / 证明同根自愈 / 升级用户决策（R-4）
3. agent-team-loop TS + Python 基线复跑（121/121 + 365）确认零回归
4. biome 触碰文件零告警
5. 预防约定落 `packages/ai/README.md`（存在则加节，不存在则建短文件）+ CHANGELOG 条目

退出：VC-001/002/003/008/009 全绿

## T-05 第二层归因（D-007）

1. `git worktree add ../mw-attr-main origin/main` + `../mw-attr-head HEAD`（独立目录，GC-A6）
2. 各自 `npm ci --ignore-scripts` + build + check + test（Linux 语义近似置信度注记）
3. 87 失败（agent 2 + coding-agent core 85）三分类 A/B/C + 计数 + 修/不修建议表
4. 报告落 `evidence/runs/attribution-2026-09-10.md`，含用户决策区；worktree 用后 `git worktree remove`

退出：VC-007；用户决策留痕（未决策前第二层不修）

## 风险控制

- R-1 近重复块：保守保留（不删）；注记于验收
- R-2 镜像判定：逐 hunk 注记于 evidence/research/design-forensics §2
- R-3 upstream remote：已添加为永久 git config（不改工作区文件）
- R-4 运行时失败超面：升级用户决策，不擅自扩
- 全程不动 pytest.ini / test_autopilot_* / __pycache__（goal-autopilot 会话资产）
