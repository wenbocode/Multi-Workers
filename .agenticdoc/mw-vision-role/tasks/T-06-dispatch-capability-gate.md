# T-06 派发期能力门禁接线（拒绝 / 放行 / fail-open）

- key: mw-vision-role · 波 1 · 独占写面：`.../agent-team-loop/pm/ui-bridge.ts`（门禁段 + 两入口）、新建 `test/extensions/agent-team-loop-vision-gate.test.ts`
- ac_refs: AC-006, AC-008 · vc_refs: VC-006, VC-008
- 依赖: T-04, T-05（同文件串行于 T-05） · 预估: 60-90min

## 前置

`ui-bridge.ts` 是五段串行热点。本卡**只碰**：`planDispatchFrontmatter` 内 `:1050-1054` 一带（`validateModelValue` 之后、写盘之前）+ 两入口传参（tool `:1239-1255` 与 `/worker` `:1625-1642`）。**不得**改 frontmatter 行组装（T-05）、自动路由（T-07）、文案（T-13）、doctor 渲染（T-12）。

## 目标

`images` 需求 + 解析出的模型判定为 `"no"` ⇒ 在 `fs.mkdirSync`（`:1252`）之前返回 `{ok:false}`，任务目录不创建、`_workers.parallel` 不新增行。

## 契约（逐字遵守）

- 判定源：`modelImageCapability(registry, cli, provider, effective)`（T-04），`effective = requested || configured`
- 拒绝条件**仅** `capability === "no" && imagesRequested === true`
- `imagesRequested` = 显式 `images:"yes"` **或** `detectImageNeed(cwd, description) === true`；显式 `images:"no"` 最高优先（短路为 false）
- 拒绝消息必须**同时含**：`images`、`mw model set vision`、`images: no`（豁免写法）；建议形态：
  `Task declares images (or references an image file) but model '<value>' cannot take image input. Use 'mw model set vision <provider/model>' to configure a vision role, or declare 'images: no' if the task does not need the image.`
- `"unknown"` ⇒ **放行**（AC-008）
- 两个入口都传 `images` + `description`（tool 从 params 取，`/worker` 从参数取）

## 步骤

1. 在 `planDispatchFrontmatter` 内 `validateModelValue` 之后插入能力分支（返回 `{ok:false, message}`）。
2. 两入口接线并确保拒绝分支**不**到达 `fs.mkdirSync`/写 `_workers.parallel`。
3. 新建 `test/extensions/agent-team-loop-vision-gate.test.ts`：
   - 扩 `fakeRegistry`（`agent-team-loop.test.ts:5041`）支持 `input`（否则能力恒 unknown ⇒ **假绿**）
   - 用例：`input:["text"]` + `images:"yes"` ⇒ 拒绝 + 目录不存在 + `_workers.parallel` 行数不变（零副作用）
   - 用例：`input:["text","image"]` + `images:"yes"` ⇒ `ok:true` + 队列 +1 + task.md 含 `^images: yes$` + 顺序 `type < phase < images < model`
   - 三条 fail-open：registry `undefined`、`cli:"codex"`、`model:"codex_cli/gpt-5"` ⇒ 均 `ok:true` + 队列 +1
   - `images:"no"` + 描述含存在的 png ⇒ 放行（豁免最高优先）
4. `[VERIFY]` 用 `process.stdout.write`。

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-vision-gate.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts   # 既有用例不得新增失败
npx biome check --error-on-warnings src/extensions/agent-team-loop test/extensions/agent-team-loop-vision-gate.test.ts
```

## 证据格式

`[VERIFY] VC-006: refused=true queue_delta=0 dir_exists=false` · `[VERIFY] VC-008: failopen_ok=true queue_delta=1`

## 非空洞对照

把拒绝条件改成 `capability !== "yes"` ⇒ VC-008 三条 fail-open 全红；把拒绝点挪到写盘之后 ⇒ VC-006 的 `dir_exists=false` 红。

## 交付

`ui-bridge.ts` 门禁段 + 新测试文件 + 原始输出。
