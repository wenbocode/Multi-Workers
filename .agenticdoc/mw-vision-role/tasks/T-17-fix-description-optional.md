# T-17 修复：`planDispatchFrontmatter` 的 `description` 改为可选（解除 VC-012 阻塞）

- key: mw-vision-role · 波 4.5 · 独占写面：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- ac_refs: AC-012（另涉 AC-007/AC-009 行为不变） · vc_refs: VC-012
- 依赖: T-05/T-06（引入该必填参数）· 预估: 20-30min

## 缺陷（T-14 报出，PM 已独立复现）

`npx tsgo --noEmit`（仓库根）rc=2，**4 条 TS2741 全在同一文件**：

```
packages/coding-agent/test/suite/rag-required.test.ts(177,43) error TS2741: Property 'description' is missing ... but required in type '{ ...; description: string; ... }'
packages/coding-agent/test/suite/rag-required.test.ts(182,41) ... 187,41 ... 191,43  (同一条)
```

根因：T-05/T-06 在 `ui-bridge.ts:1031-1049` 把 `description` 声明为**必填**：

```ts
	/** Task body, scanned for an image-file reference when `images` is
	 * undeclared (T-06 auto-detection). */
	description: string;
```

而 `test/suite/rag-required.test.ts`（**另一个 key 的既有语料**：VC-020 / `phase:` 头部锁定断言，`git status` 显示对 HEAD **零改动**）以 `planDispatchFrontmatter(base)` 形式调用、不含该字段。该文件在 HEAD 上本就无此字段 ⇒ **本 key 引入的破坏**，非基线噪声（T-09/T-12 曾把它误判为"他人/HEAD 既有"，属误判）。

## 契约（改法，已定）

- `description?: string`（可选），与同对象里 `phase?: string` 一致；实现处取 `input.description ?? ""`。
- 不改任何运行语义：显式 `images:` 仍最高优先（D-013）；未声明时仍走 `detectImageNeed(cwd, 描述)`；描述缺省 ⇒ 待扫描文本为空 ⇒ **不得产生任何 `images:` 行、不得有文件系统扫描**（AC-009 零字节）。
- **不要**改 `test/suite/rag-required.test.ts`（他人 key 的语料，动了会污染并行会话的验证面）；也不得放宽/删任何既有断言来"修"类型错误。

## 非空洞对照（必做，各贴输出）

1. 把 `input.description ?? ""` 还原成 `input.description` ⇒ `npx tsgo --noEmit` 必须重新报同一文件 4 条 TS2741（证明 `?? ""` 承重）。
2. 把 `description?:` 改回 `description:`（必填）⇒ 同样 4 条 TS2741 回来（证明"可选化"是修复本体）。
3. 行为不变对照：造一个 `images` 未声明 + 描述含图片路径 的用例，确认**仍**自动写入 `images: yes`（若 `?? ""` 写错位置把描述吞掉，此例必红）。

## 硬约束

- 只改 `ui-bridge.ts` 上述声明与取值处；**不得**碰 auto-route（T-07）、门禁（T-06）、doctor 渲染（T-12）、四处 PM 文本（T-13）。
- 不 commit、不 `git add`；不跑全量 vitest；**不跑** `npm run build`；`npx biome check` 不加 `--write`；erasable TS、无 inline import。
- **禁止用 PowerShell `Get-Content/Set-Content` 改源码**（GBK 会毁 UTF-8，用 `edit` 工具）。

## 验收（真实执行，贴原始输出）

```bash
cd H:/git/Multi-Workers
npx tsgo --noEmit                       # 期望：无任何输出、rc=0
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-required.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-vision-gate.test.ts test/extensions/agent-team-loop-vision-autoroute.test.ts test/extensions/agent-team-loop-image-cap.test.ts
npx biome check --error-on-warnings src/extensions/agent-team-loop/pm/ui-bridge.ts
```

## 证据格式

`[VERIFY] VC-012: tsgo_errors=0 tsgo_rc=0 suites_green=true`

## 交付

改动 diff（只含 `ui-bridge.ts`）+ 四条命令原始输出 + 三条对照结果 + `[VERIFY]` 行。注意：`tsgo` 全仓运行可能耗时数分钟，耐心等它跑完并把**完整**尾段（含退出码）贴进 output。
