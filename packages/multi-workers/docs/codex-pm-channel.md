# 从当前 Codex 桌面聊天联系 MW PM

在 Multi-Workers 项目中打开的交互式 pi PM 会从项目扩展加载接收端。已有窗口空闲时执行一次 `/reload`。接收端按本进程的真实 claim 在权威索引中查找唯一活动 key。当前接收范围是本 checkout 的项目窗口。

从 Codex 桌面聊天运行以下命令。Node 24 可直接运行源码，发送时使用该聊天的 `CODEX_THREAD_ID`。两个进程使用同一 OS 用户和项目。消息和回执保存在用户目录的 `.mw-pm-channel` 下。同账号程序属于同一信任边界，聊天 ID 用于追踪；扩大写面和追加总预算等决定由获授权的 Codex 聊天作出，MW 继续执行其业务门禁。

```powershell
$key = 'mw-pm-dp-continuity'
$cli = 'packages/multi-workers/pm_channel.ts'
$pm = node $cli status --project . --key $key | ConvertFrom-Json
if (-not $pm.connected) { throw '原 PM 接收端未上线或心跳已过期' }
$messageId = [guid]::NewGuid().ToString()
node $cli send --project . --key $key --binding $pm.binding --id $messageId --file .agenticdoc/mw-pm-dp-continuity/user-direction-t06-ac015.md
node $cli receipt --project . --key $key --binding $pm.binding --id $messageId
```

`status` 返回权威阶段、claim、最近的会话心跳和 idle/working。`send` 使用刚观察到的 binding。一个 binding 对应一次窗口会话加载和认领。网络或调用中断后，用相同 binding、ID 和原文查回执或重试。重载、窗口易主或重启后先查询旧回执和会话证据，再决定是否重新发送。

| 回执 | 可确认的事实 |
|---|---|
| queued | 请求已落盘。接收端在 PM 空闲且没有已排队消息时读取。 |
| received | 原 PM 扩展已接收请求并为此次投递保留 ID。 |
| started | 对应消息进入模型上下文，且观察到了随后返回的首条有效助手回复或工具调用请求。回执带会话、时间和文本节选或工具名。 |
| failed / unconfirmed / rejected | 模型报错、中止、该轮没有可关联回复，或请求无效或已过期。查具体运行后再决定后续。 |

进程在收件后异常退出时可能只留下 received。回执与执行结果分开；核实代码修改、工具成功及 AC 完成时应读取任务的实际交付证据。尚未投递的旧 binding 消息不会随新窗口重放。断开的接收端不会消费已排队消息。
