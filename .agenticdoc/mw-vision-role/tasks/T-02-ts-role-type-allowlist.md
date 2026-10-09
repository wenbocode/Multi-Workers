# T-02 TS 侧注册（类型/角色映射 + 工具白名单）

- key: mw-vision-role · 波 0 · 独占写面：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`（表段）、`.../worker/worker-mode.ts`（`TOOL_ALLOWLISTS` 段）
- ac_refs: AC-004, AC-005 · vc_refs: VC-004, VC-005
- 依赖: 无 · 预估: 30-45min

## 前置（R1 纪律）

`worker-mode.ts` 工作区**有他人未提交改动**（165+/13-，行号已漂移）。开工前先 `git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` 记录现值；`TOOL_ALLOWLISTS` 现值在 `:52-83` 附近，**以文件实际内容为准**，只在自己的段内追加，不得 reformat 他人改动。

## 契约（逐字遵守）

- `shared/dispatch-models.ts:58-71 DISPATCH_ROLE_BY_TYPE` 新增 `"vision": "vision"`（末尾追加，不重排）
- `shared/dispatch-models.ts:74 DISPATCHABLE_TYPES` 追加**末尾** → `["coding","review","research","rag-research","vision"]`
- `worker/worker-mode.ts TOOL_ALLOWLISTS` 新增 `vision: ["read","write","edit","bash","find","grep","ls"]`（与 `coding` **同序逐元素**）
- `roleForTaskType`（`:77-79`）无需改（未知→coding 的兜底保留）

## 步骤

1. 两处表追加（只加不改）。
2. 自检脚本（临时文件放 `/tmp`，用完删）：
   ```ts
   // 断言 roleForTaskType("vision")==="vision" 且 DISPATCHABLE_TYPES.at(-1)==="vision"
   ```
   用 `node ../../node_modules/vitest/dist/cli.js --run <临时测试>` 或直接在 T-03 的正式断言里覆盖（推荐后者）。
3. 自检 Python 侧白名单是否同序：`python -c "from autopilot.dispatch import REGISTRY; print(REGISTRY['vision']['tools'])"`

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts   # 现有用例不得新增失败
npx biome check --error-on-warnings src/extensions/agent-team-loop   # 无 --write
```

## 证据格式

`[VERIFY] VC-005: allowlist_vision=read,write,edit,bash,find,grep,ls parity=true`（parity 由 T-03 的正式断言给出，本卡给出 TS 侧值）

## 非空洞对照

把 `vision` 的 allowlist 改成 `["read"]` ⇒ VC-005 变红；把 `vision` 插到 `DISPATCHABLE_TYPES` 中间 ⇒ 现有 `agent-team-loop.test.ts:5143-5145` 子串断言变红（这正是要暴露的）。

## 交付

仅源码两处 + 原始输出。
