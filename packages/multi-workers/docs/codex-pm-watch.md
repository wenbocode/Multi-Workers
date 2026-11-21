# 当前 Codex 聊天值守多个 MW PM

用 `pm_channel.ts status` 在每个项目取得当前 key 的 claim 和 binding。下面的命令接受任意组这样的四个参数。加 `--status` 会打印一次实际状态后退出。

```powershell
node packages/multi-workers/pm_watch.ts $project1 $key1 $claim1 $binding1 $project2 $key2 $claim2 $binding2
```

保持此命令由当前 Codex 聊天运行。首次输出是接入快照，此后每五秒只读取本机心跳和必要的 worker 队列。工作中或等待所属 worker 时保持安静。连续空闲 45 秒且无在途 worker 才报一次 idle。断线、不可观测、换主或结束各有独立事件。收到 idle 后，聊天只读取最新结论和相关证据，区分达成目标、真实外部等待、明确停止以及可以继续的行动，再决定是否通过原绑定回复。相同状态不会每五秒重复报告。有明确用户停止时勿唤醒。

监听程序自身没有模型调用，不给 PM 发消息。停止命令结束监听。Codex 已结束的聊天不会被这个本地命令自行唤回。

本地 worker 队列仍为 running 时，监听会核对对应 run 的最后心跳和 PID。心跳过期 90 秒、原进程已退出，而且没有其他在途 worker 时，持续 45 秒后报告一次 worker-lost。此时由原 PM 回收 partial 和协调队列。

### 连续值守

在值守聊天的环境中运行 `node packages/multi-workers/pm_duty.ts --supervise <targets.json>`。配置包含当前 `thread` 和 `targets` 数组，每项固定 `project/key/claim/binding/session`。本机进程将停点事件排入该桌面聊天。Windows 下同一聊天只有一个监听能持有命名管道。监听异常退出时父进程会重启它。

每个项目在配置旁的 `evidence/continuous/<key>/` 保存状态及事件日志。聊天按事件 ID 查原 PM 回执、自决推进、确认后写 `<id>.handled.json`。持续的同一停点沿用该 ID，已处理的停点保持安静；投递失败退避重试，入队后 15 分钟仍无确认可提醒。检测到工作、在途 worker 或该事件的 started 回执后，下一停点会生成新 ID。原 claim 和 session 均匹配时可跟随 /reload 的新 binding。换主、未能观测、失联分别报告。

保持 Codex 桌面会话可用。需要停止整个值守时在 `evidence/continuous/` 写入 `STOP`，监听及父进程会正常退出。机器重启后的登录自启需单独配置。
