# T-07 auto-route（只换模型）与来源留证

- key: mw-vision-role · 波 2 · 独占写面：`.../agent-team-loop/pm/ui-bridge.ts`（auto-route 段 + 回显）、新建 `test/extensions/agent-team-loop-vision-autoroute.test.ts`
- ac_refs: AC-016, AC-017 · vc_refs: VC-016, VC-017
- 依赖: T-06（同文件串行） · 预估: 60-90min

## 目标

无显式 `model:` 的任务被判定需要图片、而该类型角色模型判定 `"no"` 且 `vision` 判定 `"yes"` 时，**只把模型换成 `vision` 角色值**，`type:` 行保持不变，并留下机读来源。

## 契约（逐字遵守）

- **不改 `type:` 行**（改 `type` 会改变工具白名单 ⇒ 只读任务被隐式提权；这是 D-004 的核心否决理由）
- `model:` 取 `dispatch.yml` 的 `vision` 值；`model-reason:` 追加 `auto-route: <src-role> -> vision`（复用既有 `:1088` 写侧）
- 回显（tool `:1272` / `/worker` `:1648`）显示生效模型与 `model-source: auto-route`（`modelPlan.echo` 需带上来源）
- 阻断：显式 `model:`（走门禁，不改写）；`vision` 未配置 ⇒ 走门禁拒绝；`vision` 判定非 `"yes"`（含 `"unknown"`）⇒ 走门禁拒绝
- 顺序：解析显式 type/model → auto-route → 能力门禁 → 回显（**auto-route 先于门禁**，否则门禁会先拒）
- 无图片需求 ⇒ 不触发（AC-009 零字节不受影响）

## 步骤

1. 读 `planDispatchFrontmatter` 现值（`:1024-1096`），在 `role/configured/requested` 计算（`:1036-1048`）之后、门禁之前插入判定：若 `!requested && imagesRequested && modelImageCapability(..., configured) === "no"`，取 `visionValue = readRoleModel(cwd, "vision")`，若其判定 `"yes"` ⇒ `effective = visionValue` + 记 `autoRouteSource`。
2. `model-reason` 组装（`:1083-1088`）追加来源；`ok` 载荷/echo 带上 `model-source: auto-route`。
3. 新测试文件（参数化，AC-017）：
   - 参数 `type ∈ {"vision","review"}`：两例均为「无显式 model + 描述引用存在的 png + 该角色模型 `input:["text"]` + `vision` 角色为 `input:["text","image"]`」⇒ 两例都 `ok:true`、task.md 的 `model:` == vision 值、`model-reason:` 含 `auto-route`，且 `type:` 行分别保持 `vision`/`review`
   - 显式 `model:` ⇒ 不改写（走门禁路径）
   - `vision` 未配置 / `vision` 模型 `input:["text"]` ⇒ 拒绝且消息含 `mw model set vision`
4. `[VERIFY]` 用 `process.stdout.write`。

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-autoroute.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-gate.test.ts   # T-06 不得回归
npx biome check --error-on-warnings src/extensions/agent-team-loop test/extensions/agent-team-loop-vision-autoroute.test.ts
```

## 证据格式

`[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true` · `[VERIFY] VC-017: types=vision,review routed=2`

## 非空洞对照

把 auto-route 改成同时改写 `type:` ⇒ 断言 `type_unchanged` 变红；把 `vision` 判定为 `"unknown"` 也路由 ⇒ 拒绝用例变红。

## 交付

`ui-bridge.ts` auto-route 段 + 新测试文件 + 原始输出。

## 卡缺陷更正（2026-09-26 实测，语义已回写 design.md §7 VC-017）

本卡验收 #1 对本卡要求的 `type=vision` 子项**逻辑不可满足**：`roleForTaskType("vision") == "vision"`（AC-004）⇒ `type: vision` 的源角色 == 目标角色，触发需同一值判 `"no"`、路由需其判 `"yes"`。强行自路由会写出假来源 `auto-route: vision -> vision`。

**正确断言**（与 VC-017 语义本身一致："均改到 `vision` 的模型 + `type:` 不变"）：
- `type=review`：路由触发（`model:` == vision 值，`model-reason` 含 `auto-route: review -> vision`）
- `type=vision`：不路由，但生效模型**本就是** vision 值（角色默认），`type:` 逐字不变，且**不写假 `model-reason`**
- 证据串：`[VERIFY] VC-017: types=vision,review type_unchanged=true effective_vision=2 auto_route_fired=1`（原卡写的 `routed=2` 已作废）
