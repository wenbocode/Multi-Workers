# T-04 能力判定纯函数（TS 三态）

- key: mw-vision-role · 波 1 · 独占写面：`.../agent-team-loop/shared/dispatch-models.ts`（能力函数段，邻 `validateModelValue :166`）
- ac_refs: AC-008 · vc_refs: VC-008
- 依赖: T-02（同文件串行） · 预估: 45-60min

## 目标

新增两个**纯函数**，作为门禁与 auto-route 的唯一判据；语义与 `validateModelValue` 的 fail-open 契约逐条对齐。

## 契约（逐字遵守）

```ts
export type ImageCapability = "yes" | "no" | "unknown";

export function modelImageCapability(
  registry: ModelRegistry | undefined,
  cli: string,
  provider: string,
  value: string,
): ImageCapability;

export function detectImageNeed(cwd: string, description: string): boolean;
```

早退序**照抄** `validateModelValue`（`dispatch-models.ts:172-195`）：

| 条件 | 返回值 |
|---|---|
| `value` trim 后为空 | `"unknown"` |
| `registry === undefined` | `"unknown"` |
| `cli.toLowerCase() !== "pi"` | `"unknown"` |
| 无 modelId | `"unknown"` |
| 前缀 ∈ `CLI_EXECUTOR_PREFIXES`（`codex_cli`/`claude_cli`） | `"unknown"` |
| 前缀 ∉ `PREFIX_TO_PROVIDER_ID` | `"unknown"` |
| 无 provider | `"unknown"` |
| 该 provider 在 registry 无任何 id | `"unknown"` |
| `registry.find(provider, modelId)` 未命中 | `"unknown"` |
| 命中 | `input.includes("image") ? "yes" : "no"` |

`detectImageNeed`：从 description 提取 token，命中扩展名集（`.png/.jpg/.jpeg/.webp/.gif/.bmp`，口径同 `core/tools/read.ts:212`）且满足：无 `*?[]` 通配符、不含 `://`、`fs.existsSync(path.resolve(cwd, token))` 为真 ⇒ `true`；否则 `false`。

**铁律**：绝不把 `"unknown"` 当 `"no"`；本函数不抛异常。

## 步骤

1. 实现两函数（无副作用、无 I/O 除 `existsSync`）。
2. 单测（临时或并入 T-06 的卡片）：registry `undefined` / `cli:"codex"` / `value:"codex_cli/gpt-5"` / `value:"unknownprov/x"` / 空值 ⇒ 全 `"unknown"`；`input:["text"]` ⇒ `"no"`；`input:["text","image"]` ⇒ `"yes"`。
3. `detectImageNeed` 用例：存在的 `login.png` ⇒ true；`generated.png`（不存在）⇒ false；`https://x/y.png` ⇒ false；`*.png` ⇒ false。

## 验收命令

```bash
cd packages/coding-agent
npx biome check --error-on-warnings src/extensions/agent-team-loop/shared/dispatch-models.ts
npx tsgo --noEmit
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
```

## 证据格式

`[VERIFY] VC-008: unknown_branches=7 yes=1 no=1`（用 `process.stdout.write` 输出）

## 非空洞对照

把 `registry === undefined` 分支改成返回 `"no"` ⇒ AC-008 的三条 fail-open 用例全红。

## 交付

`dispatch-models.ts` 能力段 + 单测（正式断言可并入 T-06 卡片，但本卡必须自带一个可跑的临时验证并给出原始输出）。
