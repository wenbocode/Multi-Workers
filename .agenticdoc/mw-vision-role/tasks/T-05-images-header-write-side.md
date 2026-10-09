# T-05 `images:` 写侧与头部顺序（TS 派发面）

- key: mw-vision-role · 波 0 · 独占写面：`.../agent-team-loop/pm/ui-bridge.ts`（frontmatter 段：`planDispatchFrontmatter` `:1024-1096`）
- ac_refs: AC-007, AC-009 · vc_refs: VC-007, VC-009
- 依赖: 无 · 预估: 45-60min

## 目标

`planDispatchFrontmatter` 接收 `images` 入参并在头部**条件**渲染 `images: <yes|no>`，位置在 `phase:` 之后、`model:` 之前；未声明时输出**逐字节不变**。

## 契约（逐字遵守）

- 入参新增 `images?: "yes" | "no"`（`undefined` = 未声明）
- 渲染顺序：`type:` →（`phase:` 若存在）→ `images:` → `model:` →（`model-reason:`）
- `images === undefined` ⇒ 不产生该行（AC-009 零字节）
- 本卡**不做**能力门禁、**不做** auto-route（T-06/T-07）；入参缺省时行为与改造前完全一致

## 步骤

1. 读 `planDispatchFrontmatter` 全文（`:1024-1096`），定位 `:1040-1043` 的 `typeLines` 组装与 `:1083-1088` 的行数组。
2. 在 `phase` 行之后插入条件行（沿用同一行数组风格，不新开拼接路径）。
3. 两个入口（tool `:1239`、`/worker` `:1625`）暂不传值（默认 `undefined`），确保零字节。
4. 自测：
   - `planDispatchFrontmatter({...无 phase/model/images})` 输出 === `"type: coding\n"`
   - 传 `images:"yes"` + `phase` + `model` ⇒ 顺序为 `type:`、`phase:`、`images: yes`、`model:`

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
```
（本卡验收以**新增**的 inline 断言为准，可临时写在临时测试文件里；正式断言由 T-06 的卡片落进 `agent-team-loop.test.ts`。）

## 证据格式

`[VERIFY] VC-009: zero_byte=true`（无 `images` 入参时输出严格等于 `"type: coding\n"`）

## 非空洞对照

把条件行写成**无条件**渲染 ⇒ VC-009 变红（既有 golden `agent-team-loop.test.ts:5331/5334` 也会红）。

## 交付

`ui-bridge.ts` frontmatter 段改动 + 原始输出。**不得**同时改门禁/文案/doctor 渲染段（属 T-06/T-07/T-12/T-13）。
