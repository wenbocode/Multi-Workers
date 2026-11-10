# 本机 Codex CLI 转发

让 pi PM 和 pi workers 的 `codex/<model>` 路由使用本机 Codex CLI 已登录的 ChatGPT 账号。默认关闭，不读取、复制或改写 Codex 认证文件。

链路：pi 的上下文 → 本地 HTTP 服务 → `codex exec` → 结构化文本/工具请求 → pi 执行工具 → 下一轮上下文。

## 前置条件

- `codex login status` 显示 `Logged in using ChatGPT`。需要时在普通终端运行 `codex login`。
- CLI 支持 `exec --ignore-user-config --ephemeral --output-schema`。本机 Codex 桌面版附带 CLI 已验证。
- Python 3.11+；pi 必须包含本次更新后的 agent-team-loop 扩展。已有安装使用项目原有构建/安装流程更新，再启动新窗口；仅改源码不会更新已有 dist 或常驻进程。
- 无需独立 `PI_CODING_AGENT_DIR`，也无需 pi `/login`：本地模型以 `openai-codex-local` 身份注册，避免旧 `openai-codex` OAuth 触发刷新；不读取或改写 Codex 认证文件，不修改 pi `auth.json`。

## 在 pi 内启用

先通过项目原有 `python packages/multi-workers/mw.py build --install` 更新安装并重开 pi。然后在项目的 PM 窗口执行：

```text
/mw proxy start
/mw proxy check
/model openai-codex-local/gpt-5.6-sol
/mw model set main codex/gpt-5.6-sol
/mw model set coding codex/gpt-5.6-sol
/mw model set review codex/gpt-5.6-sol
/mw model set research codex/gpt-5.6-sol
/mw start
/autopilot monitor on
```

`start` 校验本机 ChatGPT 登录，隐藏启动代理，幂等复用已运行实例，并把连接配置保存到控制工作区 `.mw/codex-local.json`。该文件包含本地共享口令，勿提交或分享。受管服务默认 7010 端口、180 秒调用期限、并发 2。多项目使用不同端口时，可先从终端执行 `python packages/multi-workers/codex_proxy.py start --project <目录> --port 7011`。

若已通过环境变量连接同版本手动服务，`start` 会先鉴权复用它并保存项目配置；不会启动第二个实例。旧版仅支持 `/health` 的服务需先更新重启。

PM 和 pi workers 在扩展激活时读取同一个项目配置；双工作区 worker 由 `PI_WORKER_TASK` 反推控制目录。无需让旧 launcher 继承新环境。已有 worker 需加载新版本扩展后才有此能力。配置优先于环境变量。

`/mw proxy start` 会把当前已选的 Codex 模型接到本地；当前使用其他 provider 时保留选择，请用上述 `/model` 命令选择 **Codex (local CLI)**。切换到原生 `openai-codex` 模型时，已配置项目也会在 `model_select` 重定向到本地。没有 pi OAuth 的窗口请直接选择本地身份。worker 和角色配置仍写 `codex/<model>`，无需使用内部 provider id；显式任务模型和已有角色默认值不会被 start 改写。`main` 配置受已有显式 CLI/settings 模型优先级约束，因此当前窗口建议显式 `/model`。

| 命令 | 行为 |
|---|---|
| `/mw proxy start` | 启动或复用代理，接通当前窗口；首次启动检查 CLI 登录 |
| `/mw proxy status` | 鉴权读取服务状态、活跃调用、最近成功和错误 |
| `/mw proxy models` | 从本机 Codex 缓存刷新模型目录，显示来源及回退原因，不调用模型 |
| `/mw proxy check` | 检查服务与 `codex login status`，不调用模型 |
| `/mw proxy check --deep` | 用当前所选 Codex 模型做一次真实推理，会消耗账号额度 |
| `/mw proxy stop` | 返回 draining，拒绝新请求，等待在途请求结束后退出 |

monitor 与窗口状态每 4 秒刷新，超过 12 秒未刷新标为 STALE。显示服务状态、并发数、请求等待时间、最近成功/错误；当前窗口的调用还显示心跳年龄和剩余期限。heartbeat 仅代表连接存活，**不代表模型已生成 token**。

每次 LLM 请求前做最长 3 秒的鉴权服务检查；请求中每秒接收心跳，10 秒无心跳即取消，默认 240 秒总期限不被心跳延长。选择 Codex 模型及 `turn_end` 时刷新轻量状态，不额外调用模型。错误交回原有 pi 错误流程，worker 保留原有错误退出/重试机制。代理不会自动重试或静默切换到其他账号/provider。

`stop` 保留项目配置，后续请求会明确报离线，`start` 可复用原口令恢复。若要完全退出本地路由，先 stop，移除 `.mw/codex-local.json` 和手工环境变量，再重启 pi 并选择所需 provider。不要在调用中删除配置。启动锁因管理进程异常退出遗留时，确认无 start 正在执行后再移除 `.mw/codex-local.lock`；不会自动强杀未知 PID。

## 模型目录与 GPT-6

本地 provider 优先读取 `CODEX_HOME/models_cache.json`（未设置时为 `~/.codex/models_cache.json`）中 `visibility=list` 的模型元数据，补充 pi 内置目录；隐藏条目不注册，损坏或缺失时回退内置目录。只取 id、名称、上下文等元数据，不取缓存指令或认证数据。适配器仍为 text-only；新增模型的 `maxTokens` 是保守本地预算，并非服务上限声明。

更新安装并重开 pi 后运行：

```text
/mw proxy models
/model openai-codex-local/gpt-6.1-sol
/mw model set coding codex/gpt-6.1-sol
/mw concurrency set codex/* 2
```

以 `/mw proxy models` 返回的完整 ID 为准，不能把 GPT-6 家族名直接写成 `gpt-6`。目录依赖当前本机 Codex 的缓存；CLI 与 pi 应使用相同 `CODEX_HOME`。缓存不会由本命令联网更新，目录存在也不等于模型权限已验证。新增缓存模型可再执行本命令刷新，worker 在启动时读取；角色模型仍用 `codex/<id>`，当前窗口选择用 `openai-codex-local/<id>`。

## 手动启动（可选）

未使用项目管理配置时，仍可在 PowerShell 启动独立服务。`MW_CODEX_LOCAL_TOKEN` 是本地共享口令，不是 OpenAI API key；此手动模式下服务、PM、mw launcher 必须继承同一组环境变量。

```powershell
$env:MW_CODEX_LOCAL_URL = 'http://127.0.0.1:7010'
$env:MW_CODEX_LOCAL_TOKEN = [guid]::NewGuid().ToString('N')

# 隐藏窗口启动本地服务，记录 PID 供关闭时使用。
$relayScript = Join-Path (Get-Location) 'packages/multi-workers/codex_local.py'
$relay = Start-Process python -ArgumentList @('"' + $relayScript + '"') -WindowStyle Hidden -PassThru
Invoke-RestMethod "$env:MW_CODEX_LOCAL_URL/health"
```

服务默认 `--port 7010 --timeout 180 --concurrency 2`。健康检查只表示服务已启动，不证明登录或模型权限。如果刚启动时连接被拒，稍后重试。排查启动错误可在具有相同环境的终端前台运行 `python packages/multi-workers/codex_local.py`。

选择当前 pi catalog 中、账号可调用的 Codex 模型。已实测 `gpt-5.6-sol` 的完整工具往返：

```powershell
python packages/multi-workers/mw.py model set --project . main codex/gpt-5.6-sol
python packages/multi-workers/mw.py model set --project . coding codex/gpt-5.6-sol
python packages/multi-workers/mw.py model set --project . review codex/gpt-5.6-sol
python packages/multi-workers/mw.py model set --project . research codex/gpt-5.6-sol

# mw 尚未运行时，从这个终端启动，使 launcher 继承上述环境。
python packages/multi-workers/mw.py start --project .
pi --provider openai-codex-local --model gpt-5.6-sol
```

手动环境模式下，若 mw 已在运行，先让在飞任务完成，再从上述环境重启；已有服务不会自动获取新环境。推荐使用 `/mw proxy start` 的项目配置方式。

`codex/` 是 pi provider 路由；`codex_cli/` 是让 worker 本身运行 Codex CLI，后者不会经过本服务。未配置的角色沿用原有 model 继承规则。其他 provider 以及显式任务模型不会自动切换。

跨项目限制 PM 和 pi workers 的请求并发可使用 `/mw concurrency set codex/* 2`，详见 [模型并发限制](model-concurrency.md)。该上限不改变代理自身容量。

## 手动模式关闭

完成在飞任务后，关闭本地代理并在后续 PM/mw 启动环境中撤销变量：

```powershell
Stop-Process -Id $relay.Id
Remove-Item Env:MW_CODEX_LOCAL_URL
Remove-Item Env:MW_CODEX_LOCAL_TOKEN
```

撤销后 `codex/` 恢复原生 pi Codex provider，需要其自己的登录配置。若之前修改了 `mw model set`，按所需 provider 重新设置对应角色。不要在请求执行中强杀服务，以免中断调用；调用方取消会由服务清理该请求子进程。

## 协议与边界

- `POST /complete`：bearer token + JSON `{model, context: {systemPrompt, messages, tools}, reasoning?}`。响应是 NDJSON：`heartbeat`、最终 `result`（text/toolCalls/usage）或 `error`。这是 pi 专用适配协议，不是 OpenAI Responses/Chat Completions API。
- 管理协议 v2：鉴权 `GET /status`、`GET /check`、`POST /stop`；公开 `/health` 仍仅表示存活。旧版服务需更新后重启。
- 每次请求启动独立 ephemeral CLI、回放完整历史。没有共享线程、没有原生 token streaming；文本完成后一次性返回，保活事件不代表模型生成了 token。
- 工具调用通过 `--output-schema` 转译，参数仍由 pi 的工具校验器检查。CLI 的 shell、apps、plugins、multi-agent、web search 被关闭，工作目录隔离，sandbox 为 read-only、审批为 never。pi 的工具权限、worker 白名单和写面检查继续生效。
- 仅支持文本（包括文本工具结果）；图片会报错。模型目录在本地模式下也标记 text-only。
- 请求上限 8 MiB，满载返回 429；错误 token/浏览器 Origin 返回 401；非法输入返回 400。服务仅绑定 `127.0.0.1`。客户端禁止重定向。
- 登录/模型失败显示 Codex 退出码，不回传可能包含认证信息的原始 stderr。先运行 `codex login status`，再独立确认所选模型可用。
- `CODEX_HOME` 原样继承；忽略个人 Codex config（认证仍由 CLI 自己使用），避免个人 MCP、代理设置或项目指令干扰转发。模型 id 原样传递。
- `reasoning` 会传给 CLI；温度、调用方 `maxTokens`、原生 prompt cache/session 参数没有逐项映射，不能把本服务当作完全等价的 provider API。
- usage 来自 CLI；cost 显示 0 表示本地转发不估算 API 美元费用，不代表 ChatGPT 配额不消耗。

## 验证

Python 定向测试 `python -m pytest -q test_codex_local.py test_codex_proxy.py`（在 `packages/multi-workers`）使用真实 loopback HTTP 和假的 CLI 子进程，不消耗模型额度。

TS 定向测试 `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-codex-local.test.ts test/extensions/agent-team-loop-codex-proxy.test.ts test/extensions/agent-team-loop-codex-proxy-http.test.ts`（在 `packages/coding-agent`）覆盖 PM/worker 路由、旧 OAuth 隔离、命令、monitor、真实 HTTP 与假 CLI 工具往返、心跳期限、取消和错误。
