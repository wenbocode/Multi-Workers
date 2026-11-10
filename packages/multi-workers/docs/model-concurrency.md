# 模型请求并发限制

在 pi 的 PM 窗口配置，同一操作系统用户下的所有项目、PM 和 pi workers 共享限额。限制的是同时进行的 LLM 请求数；本地工具执行不占名额，不改变 worker 数量设置。

```text
/mw concurrency set codex/gpt-5.6-sol 2
/mw concurrency show
/mw concurrency clear codex/gpt-5.6-sol
```

平台对所有模型合计限流时使用 `provider/*`：

```text
/mw concurrency set timi/* 4
/mw concurrency set timi/glm-5.3 2
```

上例表示 timi 所有模型合计最多 4 个请求，同时 glm-5.3 最多 2 个。两种限制同时生效，模型设置不会覆盖平台总上限。`clear timi/glm-5.3` 只清除该模型规则，`timi/*` 继续有效。未设置的模型/平台默认不限；不支持用 0 暂停。

支持 pi provider ID 及常用路由别名：`codex`、`openai-codex`、`openai-codex-local` 统一为 codex；`anthropic` 等价于 claude；`zai-coding-cn` 等价于 zai。模型 ID 保持大小写和完整名称。不同账号若使用同一个 provider 名称，也会共用限额。

`show` 和 `/autopilot monitor on` 返回已配置规则及当前有请求的每个模型的 `limit`、`active`、`waiting`。模型上限显示精确规则和 provider 总上限中的较小值；`provider/*` 行是汇总，不能与模型行相加。有请求但无规则的模型显示 `unlimited`；无规则且无请求的模型不逐项列出。

超过限额的请求在本机文件队列等待，每 200 毫秒检查一次，符合相同规则的请求按入队顺序准入。窗口状态显示 `Waiting for LLM slot`；可用 pi 的取消操作结束等待。等待最长 120 秒，超时明确报错，不向模型发送请求；获得名额后由原 provider 管理请求超时。成功、错误、取消后的流终态均释放名额，死亡 pi 进程的占用在下次事务时回收。

monitor 显示等待时间、模型、PID、项目/任务路径，并在当前项目 worker 行标记 `LLM queued`。PM 模型调用 `list_tasks` 时也会得到该标记，可区分正在推理和等待名额；UI 本身不会主动唤醒 PM 或注入消息。关联使用完整任务路径，跨项目同名 worker 不会混淆。旧进程缺少归属字段时只能显示 PID，更新重开后才有任务关联。状态损坏显示 `unavailable`，不会伪装成零排队。

修改立即被后续准入读取，无需 mw restart。降低限额不强制中断已有请求；等待活跃请求降到新上限以下才放行。清除规则也不删除正在记录的请求，之后重新设置限制仍能看到在途占用。

## 更新与范围

本功能位于 agent-team-loop 扩展，需构建安装后重开所有参与限流的 pi 窗口，旧 workers 等当前任务结束后重新启动。源码有未提交改动时，确认构建范围后可运行：

```powershell
python packages/multi-workers/mw.py build --install --allow-dirty
```

首次启用应等现有模型请求结束再设置：新规则无法追溯未加载限流入口的请求。已加载本版扩展的窗口会在后续模型调用前发现配置。设置不自动切换任何角色的模型，也不修改认证文件。

只覆盖经过 pi ModelRuntime provider 的 `stream` / `streamSimple` 调用（包括本地 Codex 转发）。独立 `codex_cli` / `claude_cli` workers、Python 决策专用 API、其他客户端、不同 OS 用户和其他机器不计入。异步服务端后台任务、直接绕过 ModelRuntime 的第三方 API 调用也不属于本机流计数；本功能不是平台账号配额查询。

Codex 本地代理另有默认并发 2 的服务容量，多模型共享该代理时可设置：

```text
/mw concurrency set codex/* 2
```

本命令不会提升代理服务本身的容量；`/mw proxy check --deep` 的独立诊断请求不经过 pi provider 限流，应在空闲时执行。

## 存储与故障

配置和在途计数保存在 `~/.mw/concurrency/state.json`，记录项目和 worker 任务路径，不含提示词或凭据。`MW_CONCURRENCY_DIR` 可覆盖目录用于隔离环境；需要共享限额的进程必须使用同一目录。与 `PI_CODING_AGENT_DIR` 无关。

写入用短文件锁和临时文件原子替换。状态损坏或事务锁持续占用会报错并拒绝发送新请求。不会仅按文件年龄删除锁或活跃占用，避免误放行；若管理进程崩溃遗留 `state.lock`，先关闭相关 pi 进程、核实锁内 PID 已退出，再删除这一个锁文件后重开。PID 被复用时可能保守保留旧占用，需停用相关进程后检查状态。不要在请求中删除 state.json。
