# 当前窗口的 compact 模型

在 pi 的 MW 窗口中，单独指定负责摘要压缩的模型：

```text
/mw context compact-model provider/model
/mw context compact-model
/mw context compact-model clear
```

第一条设置，第二条查询，第三条清除并恢复跟随任务模型。使用模型列表中的完整 provider/model，模型 ID 内可以含斜杠。`/mw context show` 和 `show --json` 也会显示模型与来源。

配置只在当前窗口的运行时内存中生效，不写入 key、项目或全局配置，不传给 worker。重启、重载或替换会话运行时后需要重新设置。任务或压缩运行期间也可设置、清除；变更从下一次压缩生效。每次压缩开始时固定本次模型，进行中的摘要及其重试保持原模型。

手动 `/compact`、MW 自动压缩和上下文溢出恢复都使用该模型。普通任务请求和分支摘要沿用原模型。目标 provider 使用自己的认证、端点、并发限制和模型容量；上下文过大时拒绝压缩，失败或取消不提交摘要。

当前压缩实现本身使用独立 session 和 `cacheRetention=none`。切换 compact 模型不会切换任务模型；压缩替换历史可能降低后续请求的缓存命中率。

HTTP 400 摘要错误显示固定分类：

| summary | 含义 |
| --- | --- |
| parameter | 参数或参数值不支持、无效或缺失 |
| model | 模型不存在、不支持或不可访问 |
| context | 上下文超过容量 |
| request_format | JSON、消息格式或工具调用关系不符合要求 |
| bad_request | 已知 HTTP 400，但缺少可识别的具体原因 |

例如 `MW_CONTEXT_POLICY:SUMMARY_FAILED (summary=parameter; http=400)`。分类只输出允许的枚举与状态，不输出上游错误原文。

源码改动需要按项目现有流程更新扩展 bundle 后重载窗口；仅修改源码不会更新已安装的 bundle。
