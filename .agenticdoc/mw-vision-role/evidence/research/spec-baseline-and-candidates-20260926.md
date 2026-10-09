# Research: 现状基线与候选模型（spec）

## 决策问题

回答 spec 的 §1.1（为什么需要视觉角色）、§2.1（可用 provider）、§4 待确认 4（`vision` 角色的候选模型值）。本文由 PM 亲手核实，作为本 key 的**基线证据**；RQ-1..RQ-4 由独立 worker 补深度（plumbing / 门禁挂点 / `images:` 头契约 / 视觉链路端到端）。

## 调研方法与出处

- `.mw/dispatch.yml`（本机实际文件，2026-09-26 读取）
- `.mw/window-model`、`~/.pi/agent/settings.json`（只读，无凭证值）
- `python -c` 读 `~/.pi/agent/auth.json` 的**顶层 key 集合**（未打印任何 key 值）
- `node packages/coding-agent/dist/cli.js --list-models`（本机运行，输出 `provider/model/context/max-out/thinking/images` 六列）
- `packages/ai/src/providers/data/timi.json` + 全 provider 数据文件的 `input` 字段扫描
- `packages/ai/src/image-models.generated.ts`、全仓 grep `generateImages|IMAGE_MODELS`
- 源码：`packages/coding-agent/src/core/tools/read.ts`、`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`、`packages/multi-workers/mw_common.py`、`packages/multi-workers/providers.json`

## 发现

### F1 当前 4 个派发角色全是纯文本模型（无视觉）

`.mw/dispatch.yml`：

| role | 值 |
|---|---|
| main | `timi/deepseek-v4.1-flash` |
| coding | `timi/deepseek-v4.1-flash` |
| research | `timi/deepseek-v4.1-flash` |
| review | `timi/glm-5.3` |

`--list-models` 原始输出中这两行的 `images` 列均为 `no`。

### F2 非视觉模型下 read 图片 = 静默降级为一行提示

`packages/coding-agent/src/core/tools/read.ts:87-91` 的 `getNonVisionImageNote` 返回 `"[Current model does not support images. The image will be omitted from this request.]"`；调用点 `read.ts:246`（视觉分支 `read.ts:243-252`，`mimeType` 命中即读二进制 + `processImage`）。即 worker 不会报错，只会拿到这行文本 → UI 设计任务 0 视觉信息。

### F3 有凭证的 provider 只有 timi 与 zai-coding-cn

`~/.pi/agent/auth.json` 顶层 key 集合 = `['timi', 'zai-coding-cn']`；`--list-models` 也只列出 `timi`、`zai-coding-cn` 两个 provider 的表（该命令按凭证过滤）。因此 spec 文档里写的 `claude/*`（pi provider `anthropic`）当前**不可用**——本 key 不处理该缺口。

### F4 现成可用的视觉输入模型（运行时证据，非文档推断）

`timi`（images=yes，全部 200K ctx）：

| 模型 | thinking |
|---|---|
| `timi/claude-haiku-4.5` / `timi/claude-opus-4.6` / `timi/claude-opus-4.8` / `timi/claude-sonnet-4.6` / `timi/claude-sonnet-5` | no |
| `timi/deepseek-v4-flash-vision-exp` | no |
| `timi/gpt-5.5-r3` | yes |
| `timi/gpt-5.6-luna` / `timi/gpt-5.6-sol` / `timi/gpt-5.6-terra` / `timi/gpt-6-astra` | yes |

`zai-coding-cn`（images=yes）：`zai/glm-4.6v`（128K，thinking yes）、`zai/glm-5.3-flash`（1M，thinking yes）。

timi 侧非视觉对照：`deepseek-v4.1-flash`、`glm-5.3`、`glm-5.3-flash`、`kimi-k3`、`hy3`、`hy4-preview` 均 images=no。

### F5 图片生成方向确实是空白（本 key 排除）

`packages/ai/src/image-models.generated.ts` 存在 `IMAGE_MODELS`，但全部属 provider `openrouter`（本机无该凭证）；全仓 grep `generateImages|IMAGE_MODELS|image-models` 在 `packages/coding-agent/src` 下**零命中**——coding-agent 没有暴露任何 image-gen 工具。

### F6 传递链路对视觉模型是直连透传（待 RQ-4 深挖）

`providers.json` 中 `timi` 条目只有 `api_key_env`/`credential`、**无 `port`** → 按 mw 的路由语义是直连（`mw_common` 注释：「无 `port` = 直连」），即图片内容不走 mw proxy。timi 的模型分属 `anthropic-messages`（18 个）与 `openai-responses`（5 个）两个 api 组，两个 API 模块都需要正确处理 `ImageContent`（RQ-4 核实）。

### F7 主窗口（PM）不会因 `mw model set main` 自动变视觉

`.mw/window-model` = `timi/deepseek-v4.1-flash`；`~/.pi/agent/settings.json` 有 `"defaultModel": "deepseek-v4.1-flash"`，而 `shared/dispatch-models.ts` 的 `applyMainModelConfig` 在 `settingsDefaultModel()` 非空时**直接 return**。→ 即使配 `vision`/`main`，PM 窗口粘贴图片仍会被丢弃，除非用户清掉 settings.json 的 defaultModel 或显式 `--model`。本 key 不改这个语义（spec §1.4）。

### F8 门禁的判据数据在 TS 侧现成（待 RQ-2 核实挂点）

`--list-models` 的 `images` 列来自 `packages/coding-agent/src/cli/list-models.ts:71`（`m.input.includes("image")`）；registry 的 `Model.input: InputModality[]`（`packages/ai/src/types.ts`）。派发期已有同族校验 `validateModelValue`（`shared/dispatch-models.ts`，fail-open：无 registry / CLI 前缀 / 空值一律 ok）——能力门禁应沿用同一契约。

## 结论 → 决策映射

- F1+F2+F3 → spec §1.1 现状描述与 §1.3 场景 C 成立：需要新角色 + 门禁，而不是"配一下就完事"。
- F4 → §4 待确认 4 的候选集来自本机实际可用 provider；推荐 `timi/gpt-5.6-sol`（images=yes + thinking=yes + 200K）、备选 `zai/glm-4.6v`（专用 VLM）、`timi/deepseek-v4-flash-vision-exp`（快）。**具体值由用户 `mw model set vision <value>` 决定**，本 key 不硬编码。
- F5 → §1.4 范围排除图片生成。
- F6 → §2.4 集成依赖；端到端可行性由 RQ-4 独立复核。
- F7 → §1.4 明确排除（不为视觉角色自动切 PM 窗口模型）。
- F8 → AC-006/007/008 的 fail-open 契约有既有范式可循；挂点由 RQ-2 决定。

## 数据缺口

- 图片块在 `anthropic-messages` / `openai-responses` 两个 api 模块里的具体处理与数量/大小限制：未确认 → RQ-4。
- 派发面的 registry 可达性与拒绝路径的确切落点：未确认 → RQ-2。
- `zai/glm-4.6v` 的非 thinking 视觉质量：本机不做真实调用，不在本 key 的判据内（用户侧试用决定）。

[VERIFY] `.mw/dispatch.yml` 当前 4 个角色的值分别为 timi/deepseek-v4.1-flash ×3 + timi/glm-5.3
[VERIFY] `node packages/coding-agent/dist/cli.js --list-models` 中 timi 的 images=yes 模型共 11 个（含 deepseek-v4-flash-vision-exp）
[VERIFY] `~/.pi/agent/auth.json` 顶层 key 集合为 ['timi', 'zai-coding-cn']（无 anthropic/openrouter）
[VERIFY] non-vision 降级提示行来自 packages/coding-agent/src/core/tools/read.ts:87-91
