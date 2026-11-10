# DeepSeek 官方 API

本项目已准备 `.mw/deepseek.json`，启用 `deepseek-flash`、`deepseek-v4-pro`，直连 `https://api.deepseek.com`。模型与接口依据 [官方首次调用文档](https://api-docs.deepseek.com/zh-cn/)。PM 与 pi workers 共用原生 DeepSeek provider，不通过 Codex 本地转发。

不同项目可共用用户级 `~/.mw/deepseek.json`（Windows 本机为 `C:\Users\wenbozhou\.mw\deepseek.json`）。配置内容与样例 `packages/multi-workers/config/deepseek.json` 相同，不必在每个项目复制。

读取顺序：控制项目 `.mw/deepseek.json` 优先，其不存在时读取 `~/.mw/deepseek.json`；两者均缺失时保持原生 provider。项目配置整份覆盖全局配置，不合并字段。选中的配置损坏或不可读时会报出具体路径，不会静默切换到另一份配置。已有项目文件会继续覆盖全局；希望该项目也沿用全局时，移走项目文件即可。

双根 worker 从 `PI_WORKER_TASK` 定位控制目录，局部配置不放在 game root。配置变更在 pi 扩展重新加载/新窗口及新启动 worker 时生效。所有使用该全局默认的 pi 进程需加载更新后的 agent-team-loop 扩展。

## 填写密钥

pi DeepSeek 是官方直连，默认配置的 `providers.deepseek.proxy_autostart=false`，填写官方 key 不会启动旧的 timi 协议代理。旧端口路由仍保留；只有明确需要 legacy bridge 时才设置 `proxy_autostart=true`，或启动时指定 `--deepseek-port`。该旧代理需要 `timi_proxy_cli`，与官方 DeepSeek provider 无关。

推荐在 pi 执行 `/login`，选择 DeepSeek 并填写 key。pi 将其保存到自己的认证存储；launcher 的 `providers.json` 已配置 `DEEPSEEK_API_KEY` 优先、`~/.pi/agent/auth.json` 的 `deepseek.key` 回退。无须把 key 填入项目 JSON。

也可以从设置了 `DEEPSEEK_API_KEY` 的终端启动 pi 和 mw。环境变量仅影响之后启动的进程；已有 mw 未继承该变量时，等待在途 worker 完成后从该环境重启 mw。如果使用 pi 登录文件方式，launcher 后续派发时读取，不依赖新环境。

`PI_CODING_AGENT_DIR` 使用自定义路径时，pi 的存储位置可能不同；launcher 当前默认文件回退仍为 `~/.pi/agent/auth.json`。这种情况优先让 pi 和 mw 都继承 `DEEPSEEK_API_KEY`，或在自定义 `--providers` 文件中调整凭证路径。

## 更新与选择模型

源码更新需先按项目构建安装流程更新安装，重开 pi。本次涉及 `mw_common.py` 与 providers 配置，已有 mw 应在在途任务结束后重启以加载新版本。未构建的源码不会更新已安装 bundle。

在 pi 中：

```text
/login
/model deepseek/deepseek-flash
/mw model set coding deepseek/deepseek-flash
/mw model set review deepseek/deepseek-v4-pro
/mw model set research deepseek/deepseek-flash
/mw model set main deepseek/deepseek-flash
/mw concurrency set deepseek/* 4
/mw concurrency show
```

这些是按需执行的选择步骤；配置文件本身不切换现有角色。`main` 是后续窗口默认，当前 PM 用 `/model` 明确选择。并发数 4 只是本机起始设置，不表示平台上限；同用户所有项目合计，PM 和 worker 共用名额。

## 模型行为

- Flash 支持 text/image；Pro 为 text-only，按 [官方模型表](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 配置。
- 复用 pi 原生 OpenAI chat-completions 适配，支持流、工具和缓存统计。使用 [DeepSeek 思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/) 时，工具后续请求会回传 `reasoning_content`。
- thinking 档位：minimal/low→low，medium/high/xhigh→high，max→max。off 经原生适配器关闭思考。
- 上下文/输出预算及 cost 基于 pi 内置模板；cost 是既有估算，不代表最新峰谷人民币账单。实际费用以 DeepSeek 控制台为准。
- 缺 key 时会明确报认证不可用；配置损坏或未知模型时明确拒绝，不静默切换 provider。`.mw/deepseek.json` 不支持 key 字段。

## 观察与验证

`/session`、底部 `R`/`CH` 与 `/mw stats --since 1h --model deepseek` 可查看 usage；并发等待通过 `/autopilot monitor on` 和 `list_tasks` 观察。

无 key 定向验证：

```powershell
# packages/multi-workers
python -m pytest -q test_deepseek_provider.py test_dispatch_models.py test_common.py
# packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-deepseek-provider.test.ts test/extensions/agent-team-loop-concurrency.test.ts
```

以上使用临时凭证与模拟响应，不能证明账户权限。提供 key 后再做一次真实文本及工具往返验证。
