# Research: 视觉输入链路端到端 + `vision` 角色候选独立复核（RQ-4）

## TL;DR
1. 链路端到端可用：`read` 产出 `{type:"image",data,mimeType}` → toolResult 消息 → `transformMessages`（仅非视觉模型降级）→ provider 转换；timi/zai 走**直连**，mw proxy 不参与，图片无 mw 侧改写点。
2. 限制面：单图 2000x2000 / 4.5MB(base64) / jpeg q80，可逐级降采样；**无单请求图片数量上限**；`processImage` 失败 = 静默降级为文本行（不抛错）。
3. 复核：基线 timi 11 个 images=yes、`glm-4.6v` 128K/thinking=yes、`glm-5.3-flash` 1M/thinking=yes **全部与运行时一致，无出入**。
4. 推荐：首选 `timi/gpt-5.6-sol`（核实通过）；备选 `zai/glm-5.3-flash` + `zai/glm-4.6v`；**反驳**把 `timi/deepseek-v4-flash-vision-exp` 列为主备选。

## 决策问题
- Q1 图片内容块从 `read` 到 provider 的完整路径（`file:line`）；timi 直连时是否原样透传、mw proxy 是否参与；`anthropic-messages` 与 `openai-responses` 对 `ImageContent` 的处理位置。
- Q2 限制面：`autoResizeImages`、mime 白名单、单请求图片数量/大小上限、`processImage` 失败降级；worker `-p`（headless）是否与交互模式共用同一 `read` 路径。
- Q3 `vision` 角色默认值（首选 1 + 备选 2）独立推荐，核实或反驳 PM 倾向，尤其 `glm-4.6v` 的 ctx/thinking 与 `deepseek-v4-flash-vision-exp` 的 `-exp` 稳定性。

## 调研方法与出处
- 静态阅读（全文）：`core/tools/read.ts`、`utils/{image-process,image-resize-core,image-convert,mime,tool-result-images}.ts`、`agent/agent-loop.ts`、`core/agent-session.ts`、`ai/src/api/{transform-messages,anthropic-messages,openai-responses,openai-responses-shared,openai-completions,timi-responses}.ts`、`ai/src/providers/timi.ts`、`ai/src/types.ts`、`modes/print-mode.ts`、`cli/list-models.ts`、`core/{model-runtime,model-registry}.ts`、`multi-workers/{launcher.py,providers.json}`。
- 本地命令（无 LLM 调用、未打印凭证值）：`node packages/coding-agent/dist/cli.js --list-models timi|zai`；`node -e` 读 `~/.pi/agent/models-store.json` 与 `packages/ai/src/providers/data/*.json`；`node --input-type=module -e` 用 dist `processImage` 处理本地 1x1 PNG。
- 未发起任何真实模型请求；未读取 `auth.json` 的值（仅沿用 PM 已核实的顶层 key 集合）。

## 发现
### F1 图片路径（`file:line`）
- `read` 视觉分支：`read.ts:243` 嗅探 mime → `read.ts:249-250` 读二进制 + `processImage` → `read.ts:257-261` 装配 `[{type:"text"}, {type:"image",data,mimeType}]`；非视觉模型另加提示行（`read.ts:87-91` 生成，`:253`/`:258` 拼接）。
- 消息装配：`agent/agent-loop.ts:773` `createToolResultMessage`，`:401-403` 压入 messages；`agent-session.ts:516-528` 对工具结果图片跑 `normalizeToolResultImages`（扩展注入的图片也走这里）。
- provider 前统一降级：`transform-messages.ts:64` `transformMessages` → `:33-38` `downgradeUnsupportedImages`（`model.input` 不含 image 时把图片块替换为占位文本）。
- `anthropic-messages`：`:947` 调 `transformMessages`；tool_result 图片 `:1081-1108`（`convertContentBlocks` `:117-169`，media_type 白名单 `:125`/`:150`）；user 图片 `:1145-1153`。
- `openai-responses`：`openai-responses-shared.ts:170` 调 `transformMessages`；tool_result 图片 `:84-101`（`:87` 二次守卫 `model.input.includes("image")`）；user 图片 `:198-202`。timi 的该 API 经 `timi-responses.ts:78` 包装，`normalizePayload` 仅删 `store`、不动图片。
- 第三族（zai 用）：`openai-completions.ts:1090-1094`（user）、`:1230`/`:1252-1260`（tool_result）。
- timi 直连：`providers.json:44-47` 无 `port` → `launcher.py:235-249` 只注入 `TIMI_API_KEY`（`TIMI_BASE_URL` 仅当 serve env 已存在时透传）→ `providers/timi.ts:8-22` baseUrl = `http://api.timiai.woa.com/ai_api_manage/llmproxy`。**mw proxy 端口 7001/7003/7004 与图片链路无关，图片 base64 原样透传。**

### F2 限制面与失败降级
- `autoResizeImages` 默认 true（`read.ts:207`），值来自设置 `imageAutoResize`（`agent-session.ts:2558,2569`；`settings-manager.ts:1149`）。
- mime 白名单（嗅探）：jpeg/png/gif/webp/bmp（`mime.ts:6-25`；动画 PNG 返回 null → 会被当文本读）。`processImage` 原生接受 png/jpeg/gif/webp（`image-process.ts:29-43`），bmp 等先转 PNG（`:45-60`，依赖 Photon `image-convert.ts:4-9`）。
- 单图上限：maxWidth/maxHeight 2000、maxBytes 4.5MB(base64)、jpeg q80（`image-resize-core.ts:12-26`）；逐级缩到 1x1 仍超限则返回 null（`:143-160`）。**全仓无单请求图片数量上限、无图片计数守卫。**
- `read.ts:249` 先把整个文件读入内存，无原始文件大小前置上限。
- 失败降级：`processImage` ok:false → `read` 只落文本 `Read image file [mime]\n<message>`，不抛错（`read.ts:250-254`；两条 message 见 `image-process.ts:80-94`）。
- 本地实测：dist `processImage(1x1 PNG)` → `ok:true`（Photon 后端在本机可用，无降级）。

### F3 headless 与交互共用同一 read 路径
- worker 用 `-p` 启动：`launcher.py:476`（timi）、`:486`（zai-coding-cn 等直连 provider）。
- print 模式复用同一 runtime/session/tool 集：`main.ts:796-800` 建 runtime → `:918-919` `runPrintMode(runtime, …)`；`print-mode.ts:31-39` 直接用 `runtimeHost.session`。
- read 工具所有模式由同一工厂创建：`agent-session.ts:2569` → `core/tools/index.ts:99`/`:120` → `read.ts:203`/`:349`。差异仅在初始消息（`--file`/粘贴图片），工具内 `read` 逐行相同。

### F4 候选模型复核
- timi（运行时 `--list-models timi`）：11 个 images=yes，全部 200K —— 与基线一致。`gpt-5.6-sol` 200K/64K/thinking=yes/images=yes；`deepseek-v4-flash-vision-exp` 200K/64K/thinking=**no**/images=yes。
- zai（`--list-models zai`）：`glm-4.6v` 128K/32.8K/thinking=yes/images=yes；`glm-5.3-flash` 1M/131.1K/thinking=yes/images=yes —— 与基线一致。
- **新增事实（基线未写）**：`packages/ai/src/providers/data/zai-coding-cn.json` 只有 7 个模型且**不含 `glm-4.6v`**；4.6v 仅存在于 `~/.pi/agent/models-store.json` 的 `zai-coding-cn.models`（动态刷新，checkedAt 2026-09-26T08:25Z，`input:["text","image"]`，128000/32768）。`--list-models` 与派发门禁同源（`model-registry.ts:56` `find` → `model-runtime.ts:392` → 同一合并目录），故 PM 进程可判定它；但动态目录冷/刷新失败时 `find` 返回 undefined → 门禁 fail-open。
- timi 在 `models-store.json` 的 `models` 为空 → timi 全部走内建静态目录（目录稳定性优于 zai 动态侧）。

## 结论 → 决策映射
- 链路可用性：F1/F3 → spec §2.4 集成依赖成立；配成 images=yes 模型即可，无需任何 mw/pi 路由改动（满足 GC-5）。F2 → 支持 §1.3 场景 C 与 AC-011 的必要性（非视觉时是静默降级而非报错）。
- `vision` 默认值（核实/反驳 PM 倾向）：
  - **首选 `timi/gpt-5.6-sol`（核实通过）**：images=yes + thinking=yes + 200K/64K，内建静态目录 + timi 直连分支成熟，是唯一同时具备"视觉 + 推理 + 大上下文 + 目录稳定"的选项。
  - **备选 1 `zai/glm-5.3-flash`（替换 PM 的快模型位）**：1M ctx + thinking=yes + images=yes + 内建静态目录；"多图 + 长上下文"场景优于 `-exp` 模型，稳定性显著更好。
  - **备选 2 `zai/glm-4.6v`（核对 PM 备选，附警告）**：确为专用 VLM，能力面与基线一致；但 ctx 仅 128K、max-out 32.8K（读多张 mockup + 代码时最紧），且只存在于动态目录（F4）。建议定位为"专用/小上下文备选"，不要做无提示的自动回退。
  - **反驳 `timi/deepseek-v4-flash-vision-exp` 进入主备选**：`-exp` = 实验性、无稳定性承诺、thinking=no；一旦被移除，注册表无此模型 → 按 AC-008 fail-open 语义门禁不再拦，退化回静默降级。若用户坚持使用，只应作为知情下的临时值，并配一条"该模型仍在 `--list-models` 中 images=yes"的巡检断言。
- VC 候选（可机器判定，均无网络/无 LLM 调用）：
  1. `.mw/dispatch.yml models.vision=<v>` 且 `<v>` 出现在 `--list-models` 输出时，该行 `images` 列 **必须** == `yes`。
  2. 对 `<v>` 的 `--list-models` 行，`context`/`thinking` 必须与 `~/.pi/agent/models-store.json` 或内建目录中 `<v>` 的 `contextWindow`/`reasoning` 一致。
  3. 每个备选值也要满足断言 1（备选写成默认值后不得退化为 images=no）。
  4. 门禁判定用的 `ModelRegistry.find(provider, id)` 对 `<v>` 必须返回非 undefined（即走拒绝/放行分支而非 fail-open 分支）——单测内断言，不发请求。
- 数据缺口（未确认 + 确认方式，均不含真实调用）：
  - timi/zai 网关是否接受 `image/gif`、`image/webp` 内联块，以及是否有服务端单请求图片数量上限：未确认；确认方式 = 网关文档或用户知情下的一次真实小图调用（不在本卡范围）。
  - worker 首启时动态目录是否必定先完成 zai 刷新（决定 `glm-4.6v` 能否被门禁判定）：未确认；确认方式 = 干净 HOME + `ZAI_CODING_CN_API_KEY` 下先跑 `--list-models zai` 再跑门禁单测。
  - `models-store.json` 由哪个 pi 版本/时机写入（本机 store 的 `inputLimits` 字段在本仓库源码中不存在）：未确认；确认方式 = 对比 `--list-models zai` 前后 store `checkedAt` 变化。
  - 动画 PNG / 超大原图（超过可用内存）的降级行为未实测；确认方式 = 本地构造文件跑 dist `processImage`。

[VERIFY] `node packages/coding-agent/dist/cli.js --list-models timi` 输出中 images=yes 的行数为 11，且 `gpt-5.6-sol` 行 thinking=yes、context=200K
[VERIFY] `--list-models zai` 中 `glm-4.6v` 为 128K/thinking=yes/images=yes，`glm-5.3-flash` 为 1M/thinking=yes/images=yes
[VERIFY] `packages/ai/src/providers/data/zai-coding-cn.json` 不含 `glm-4.6v`；该模型只出现在 `~/.pi/agent/models-store.json` 的 `zai-coding-cn.models`
[VERIFY] `packages/multi-workers/providers.json` 的 timi 与 zai-coding-cn 条目无 `port` 键；`launcher.py:235-249` 的 timi 分支不设置任何 `*_BASE_URL`