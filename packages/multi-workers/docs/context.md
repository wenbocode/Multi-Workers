# MW 上下文预算与自动压缩

加载当前版本 `agent-team-loop` 扩展的 pi PM 和 worker 在每次模型请求前检查预算，包括一个任务内的连续工具轮。本期源码变更需要按项目既有更新流程安装扩展并重新加载窗口后才会生效；修改源码不会改变已经运行的旧 bundle。本次开发不自动安装或重启服务。

原生 `codex_cli` / `claude_cli` 执行器没有加载此 pi 扩展，不在强制覆盖面内。pi 的本地 Codex 转发 provider 接入同一预算层，但 CLI 内部解码限制另见下文。

## 配置位置与初始值

全局文件为 `~/.mw/context.json`，项目文件为 `<控制工作区>/.mw/context.json`。dual/partition worker 从实际 `PI_WORKER_TASK` 反推控制工作区，不读取目标 cwd 中的同名配置。类型取 task.md 头部首个 `type:`，缺失为 `default`；PM 为 `pm`。`phase-writer`、`verifier` 和自定义类型都按精确类型名查找，不映射到 coding/review 角色桶。

全局文件缺失时只在内存使用以下初始文档，不自动写 HOME。k=1000 tokens；512k 为 512000，256k 为 256000。

```json
{
  "version": 1,
  "defaults": {
    "maxTokens": 512000,
    "compaction": {
      "enabled": true,
      "triggerRatio": 0.8,
      "targetRatio": 0.5,
      "keepRecentTokens": 20000,
      "maxSummaryTokens": 4096,
      "timeoutMs": 120000
    }
  },
  "types": {
    "coding": { "maxTokens": 256000 },
    "research": { "maxTokens": 256000 },
    "review": { "maxTokens": 512000 }
  }
}
```

已存在的全局文件中，`types` 是完整显式表，省略 `types` 等同空表。清除 coding 后会继承当前全局 defaults，重新读取或重启不会补回 256000。全局 defaults 缺少的字段使用内置 defaults。项目文件只包含显式覆盖；项目 `types: {}` 不会删除全局仍存在的类型。

每个字段分别按以下顺序选择值，并保留来源路径、作用域、defaults/type 层与初始默认标志：

```text
项目 types[实际类型] > 项目 defaults > 全局 types[实际类型] > 全局 defaults
```

例如全局 coding 的 maxTokens=256000、项目 defaults 的 maxTokens=300000 时，该项目 coding 使用 300000；项目没有声明的 compaction 字段仍逐字段继承。

## 查询、设置与清除

在 pi 的 PM 窗口执行：

```text
/mw context show
/mw context show --type coding --json
/mw context set maxTokens 400000 --global
/mw context set maxTokens 200000 --project --type coding
/mw context set compaction.enabled false --project
/mw context set compaction.triggerRatio 0.75 --project
/mw context set compaction.targetRatio 0.45 --project
/mw context set compaction.keepRecentTokens 15000 --project
/mw context set compaction.maxSummaryTokens 4096 --project
/mw context set compaction.timeoutMs 120000 --project
/mw context clear maxTokens --project --type coding
/mw context clear compaction.enabled --project
/mw context clear type --global --type coding
```

变更必须恰好指定 `--global` 或 `--project`；不写 `--type` 就操作该作用域的 defaults。`clear <字段>` 只移除选定覆盖，恢复下层继承；`clear type` 移除选定类型的整条覆盖，保留其他类型。全局文件缺失时执行 clear 会先显式保存初始文档再清除指定项，因此类型删除可以持久生效。worker 仅允许 show，不能通过任务回答调高预算。

show 给出实际类型、控制根、配置/模型/有效窗口、inputBudget、自动压缩状态和逐字段来源；`--json` 还包含全部 compaction 值及预算分量。已有无 UI/RPC 通路同样可以查询，不需要新增 Python 配置写入入口。

配置采用 version=1，拒绝未知字段、非法 JSON、非对象 types、布尔/字符串数值、非正安全整数。比例必须满足 `0 < targetRatio < triggerRatio < 1`。读取接受一个前置 UTF8 BOM；写入为无 BOM UTF8，使用同目录独占锁和临时文件原子替换。锁冲突不会偷锁，损坏或不可读文件不会回退到旧的宽松快照。

每次业务/摘要请求前重新读取策略。修改影响后续请求，不取消已经发出的请求；摘要结束后在业务发送前再次读取并复核。合法数值也可能不适合当前模型或输出预算，此时请求仍会被拒绝。

## 预算与估算

上限是单次请求窗口预算，包含输入和输出预留，不是任务累计 token 配额。模型能力记录保持原值。

```text
E = min(模型 contextWindow, 最终 maxTokens)
R = max(16384, 本次明确输出上限；未指定时使用模型 maxTokens)
S = max(4096, ceil(E × 0.02))
B = E - R - S
Trigger = floor(B × triggerRatio)
Target = floor(B × targetRatio)
```

E/R/S/B 与估算值均可诊断。输出预留或固定 system/tools/任务锚点无法容纳时直接停止，不降低输出预算、不自动扩大窗口。

文本基值为 `ceil(UTF8 字节数/3)`，另加 1024 协议余量；计算覆盖 systemPrompt、工具定义、消息、工具参数和结果，以及实际送入请求的 thinking/签名。图片优先读取已有尺寸，无法识别时每张估算 4096（image-fallback）；base64 传输长度不作为普通文本 token。

真实 usage 的 input+cacheRead+cacheWrite 用于单调上调同一 provider/model/包装版本的校准系数；缓存读取仍占窗口。换模型或包装不会继承不匹配的系数，原生 compact 后重置校准。

本地 Codex 计入与实际请求同源的完整 JSON 包装，并另预留 16384 CLI 附加提示估算。**本地 CLI 不接受调用方 maxTokens 作为解码硬上限**：这里是外层保守预算，不能保证 CLI 内部精确窗口或输出截断。若返回输出超过摘要规划，仍按实际 usage 计量并拒绝应用摘要。不同 provider 的 tokenizer 无法由此精确预知，服务端 overflow 防护继续保留。

## 自动压缩、恢复与失败

达到 Trigger 且自动压缩开启时，在完整工具批次结束后的下一次请求边界尝试一次摘要。保留首个任务 user 消息和当前 system/tools，按完整 toolCall/toolResult 批次划分历史，尽量保留最近 keepRecentTokens；过大的完整已结束批次可以整体纳入摘要。未完成的工具批次不能从中间切开。

摘要使用同模型、当前认证、独立并发槽且不开放工具，最多等待 timeoutMs，并服从父取消。摘要请求本身也受预算检查，不能容纳时直接报告。摘要包含非空的 goal/constraints/decisions/changes/verification/remaining 六字段；工具文字不会被解析为新工具调用。只有摘要有效、after<before 且 after<=Target，持久化 checkpoint 成功后才继续业务请求。本次事件不反复摘要，不重启 worker、不重执行工具。

checkpoint 只投影发送历史；完整原始会话与工具结果仍保留。resume/fork/模型切换时验证整个覆盖前缀的语义指纹；分支或原生 compact/tree 改变前缀后不会复用失效摘要。模型切小或配置变严时重新计算窗口。此机制不解决进程内原始历史的内存增长。

`compaction.enabled=false` 只关闭自动摘要：Trigger 到 B 内仍可发送，超过 B 则停止，提示手动处理。原生 threshold 自动 compact 由托管触发器统一接管；关闭自动摘要时也取消原生 overflow 自动摘要。手动 compact 仍可用，但同样受预算检查。原生 compact/tree 通过事件 signal 身份识别，避免递归托管摘要或重复计量。

策略拒绝携带 `mw_context_policy` 诊断、稳定 code、配置来源与预算数字，并标记 `noProviderRequest=true`、`outerRetryEligible=false`。worker 在 MODEL_ERR 分支前落盘部分交付和 needs-clarification，exit2；不触发同模型重试、备用模型链、phase 推进或恢复自检。原生摘要内部即使把错误转为普通 Error，扩展也把本 run 的 typed 诊断传给结案路径并保存在 run.json 的 context_policy_details。

受管摘要失败还会关联与用量记录相同的 attemptId、attemptStartedAt、provider/model。`SUMMARY_TRUNCATED` 表示摘要输出被截断，`SUMMARY_ABORTED` 表示父请求未取消时摘要独立中止，超时仍为 `SUMMARY_TIMEOUT`，其他请求失败为 `SUMMARY_FAILED`。安全原因只保留固定分类（quota、rate_limit、auth、context、network、unknown）及有可靠证据的 HTTP 状态/白名单错误类型；不会记录上游原始错误正文、URL、headers 或 stack。未知原因保持 unknown，历史已丢失的错误无法补回。`noProviderRequest=true` 表示未发送后续业务请求，摘要调用本身仍按实际状态计量。

父取消保持底层 `stopReason=aborted`。沿用现有跨语言状态集合，run.json 使用 failed/exit1 并写 `aborted:true` 与明确取消原因；不会伪装成功或策略 exit2。已改文件、report.md、output.md、trace.log 和原会话保留供接续。

## 认证变化边界

每次真实调用在取得并发槽后重新解析当前认证，保留公开 API 可以区分的显式 key/header/env 覆盖。若调用 options 的 key 与入口解析出的 key 相同，而摘要期间当前 key 已变化，公开 API 无法区分这是显式覆盖还是核心注入：业务请求以结构化 `AUTH_CHANGED` 策略终态停止，供调用方用新认证重新进入。不会在该歧义下悄悄替换用户的显式 key。

## 用量统计与排查

`/mw stats` / `python mw.py stats --json --no-open` 从会话读取每次 `mw-context-compaction-usage`：仅元数据、provider/model、attemptId、attemptStartedAt、providerRequestStarted、状态和四个 usage 分量。checkpoint 摘要正文不是统计来源，运行台账不复制 token。

同 attemptId 在整个会话内先去重，再按原 attemptStartedAt 过滤时间窗；已知 usage 优先于 unknown/null，更正不会把同一请求移入另一个时间窗或重复计费。已经发送但未知的 usage 保留 unknown；只在并发槽中等待、`providerRequestStarted=false` 的取消尝试留作证据，不计实际 calls/token。策略自身没有发送业务请求的 assistant 诊断不算实际 calls；已经发送的摘要仍照实计量，失败且有 usage 也不漏算。原生 compact/tree 成功只读取各自原生 usage 条目，不再添加托管副本。

停止后先看 `/mw context show --json`、worker 的 Exit Reason / Questions、run.json 的 context_policy_code/context_policy_details 与会话诊断。核对实际类型、控制根、输出预留、固定锚点、摘要结果和配置读取错误，再决定手工 compact、调整显式配置或拆分剩余任务。用户修改策略后下一个请求重新评估；系统不会替用户自动扩大预算。
