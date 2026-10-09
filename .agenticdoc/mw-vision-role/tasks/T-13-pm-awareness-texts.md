# T-13 PM 知情面四处文本（否则"能派但不提示"）

- key: mw-vision-role · 波 2 · 独占写面：`.../agent-team-loop/pm/ui-bridge.ts`（文案段）、`.../agent-team-loop/pm/pm-orchestrator.ts`、`packages/multi-workers/test_autopilot_l0.py`
- ac_refs: AC-014 · vc_refs: VC-014
- 依赖: T-06（`ui-bridge.ts` 串行） · 预估: 45-60min

## 背景（RQ-5 实证）

PM 的 LLM 可见面里**唯一**枚举任务类型的是 `dispatch_worker` 的 `type` 参数描述（`ui-bridge.ts:1146`），其现状是硬编码 `'coding' | 'review' | 'research'`（**连已有的 `rag-research` 都没列**）；系统提示 `PARALLEL_PROTOCOL`（`pm-orchestrator.ts:650-658`）只点名 `type: research`。只改 `DISPATCHABLE_TYPES` = "能派但不提示"，PM 不会主动用。`README.md`/`UPDATE.md`/skill 文档**不被扩展注入**，对 PM 零影响（不构成 AC）。

## 契约（逐字遵守）

四处文本都要含 `type: vision` 语义与角色名 `vision`：

| # | 位置 | 改法 |
|---|---|---|
| 1 | `ui-bridge.ts:1146` `type` 参数描述 | 类型清单补齐为 `'coding' \| 'review' \| 'research' \| 'rag-research' \| 'vision'`，并加一句图片语义（如 `Use 'vision' for tasks that must read image files (screenshots/mockups).`） |
| 2 | `ui-bridge.ts:1554` `/worker` USAGE | `--type coding\|review\|research\|rag-research\|vision` |
| 3 | `ui-bridge.ts:1993` `/mw model set` USAGE | 角色清单加 `vision`（且与 `mw_common.DISPATCH_ROLES` 一致） |
| 4 | `pm-orchestrator.ts:650-658 PARALLEL_PROTOCOL` | 补一条规则：**引用图片/截图/mockup 的任务用 `type: vision`**（沿用该数组既有条目的行文风格） |

## 步骤

1. 四处文案（只改文本，不改逻辑）。
2. `test_autopilot_l0.py` 新增 L0 断言（范式 `:215` 的解析）：
   - 从 `ui-bridge.ts` 的 `type` 参数描述里**解析出类型 token 集合**，断言其等于 `DISPATCHABLE_TYPES ∪ {"codex"}`（锁住"描述与白名单不再漂移"）
   - 断言 `/worker` USAGE 文本含 `vision`、`/mw model set` USAGE 的角色集合 == `mw_common.DISPATCH_ROLES`
   - 断言 `PARALLEL_PROTOCOL` 冻结文本含 `type: vision` 与 `type: research`

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_autopilot_l0.py -q -s
cd ../../packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
npx biome check --error-on-warnings src/extensions/agent-team-loop
```

## 证据格式

`[VERIFY] VC-014: surfaces=4 token_set_ok=true`

## 非空洞对照

只改 3 处漏掉 `PARALLEL_PROTOCOL` ⇒ VC-014 红；把描述里的 token 集合写漏 `rag-research` ⇒ token 集合断言红（这正是现状的缺陷）。

## 交付

3 处源码文件 + 1 个测试文件 + 原始输出。
