# T-01 开关解析：`shared/review-split.ts`（coding）

- Key: claim-driven-review-orchestration
- 里程碑：M1（只读规划器）
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（PM 管多 worker 并行、文件驱动协调）。
- 本卡只做**开关解析**这一个纯模块，不接派发链、不改任何现有文件。
- 设计依据 `.agenticdoc/claim-driven-review-orchestration/design.md` §2.2：开关名为 `MW_REVIEW_SPLIT`，
  优先级 **env > `.mw/review-split.json` > 默认 `off`**，返回值必须带**来源**（`env` / `config` / `default`），
  因为 `mw review-split status` 要回显"生效值 + 来源"。
- 参照既有形态：`shared/dispatch-card.ts:565` 的 `CLAIM_GATE_DEFAULT`（常量 + env，平价锁）。

## 要求

在新文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/review-split.ts` 中实现：

1. 常量：`REVIEW_SPLIT_MODES = ["off","plan","on"] as const`、`ReviewSplitMode` 类型、
   `REVIEW_SPLIT_DEFAULT: ReviewSplitMode = "off"`、`REVIEW_SPLIT_ENV = "MW_REVIEW_SPLIT"`、
   `REVIEW_SPLIT_CONFIG = ".mw/review-split.json"`。
2. `resolveReviewSplit(projectDir: string, env?: Record<string, string|undefined>): ReviewSplitState`，
   `ReviewSplitState = { mode: ReviewSplitMode; source: "env"|"config"|"default"; configPath: string; invalid?: string }`。
3. 规则（**永不抛异常**，P-048 宽容）：
   - env 存在且合法 → `{mode: env, source: "env"}`；
   - env 存在但非法（如 `"ON"`、`"true"`、空串）→ 视同未设置，继续看 config，并把原文放进 `invalid`
     以便上层记 `split:mode-invalid:<v>`；**大小写不敏感**（`"Plan"` 视为 `plan`）。
   - config 存在且 `{"v":1,"mode":<合法值>}` → `{mode, source: "config"}`；
   - config 缺失 / JSON 坏 / `mode` 非法 / `v` 不是 1 → 继续降级（坏文件时 `invalid` 记录原因）。
   - 都没有 → `{mode: "off", source: "default"}`。
4. **纯读**：只 `readFileSync`，不创建、不修改任何文件；目录不存在时视为无 config。
5. 导出 `reviewSplitConfigPath(projectDir)` 供 `mw review-split status` 打印。

## 交付格式

- 新增 `packages/coding-agent/src/extensions/agent-team-loop/shared/review-split.ts`
- 新增测试 `packages/coding-agent/test/suite/review-split-mode.test.ts`，覆盖 8 条：
  默认、env=on、env 非法降级、env 大小写、config=plan、env 覆盖 config、config JSON 坏、config mode 非法。
- 测试用 `os.tmpdir()` 建临时项目目录写 `.mw/review-split.json`，不要碰仓库里的真实 `.mw`。
- 报告 `report.md` 四段：`## 结论` `## 证据`（每条用例一行）`## 未覆盖面声明` `## 上下文来源`。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/review-split.ts`
- `packages/coding-agent/test/suite/review-split-mode.test.ts`

## 写入禁止面

- 其他任何 `packages/**` 文件（尤其 `shared/dispatch-card.ts`、`pm/**`、`worker/**`）
- `.agenticdoc/**`（除自己 taskDir）、`.mw/**`、`dist/**`

## 验收命令

从 `packages/coding-agent` 目录：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/review-split-mode.test.ts`
要求 8 条全绿；另在仓库根跑 `npx biome check` 限于本卡两个文件，0 诊断。

## 改动历史

| 日期 | 改动 | 依据 |
|---|---|---|
| 2026-10-22 | 初始卡（M1 拆分） | design.md §2.2、spec AC-S1 |
| 2026-10-22 | 吸收：卡内自相矛盾（把 ON 列为非法但同时要求大小写不敏感）→ 按宽容原则判 ON → on，单点改动 sMode()；8/8 绿、	sgo rc=0 | worker report |
