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
      "triggerRatio": 0.8
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
/mw context clear maxTokens --project --type coding
/mw context clear compaction.enabled --project
/mw context clear type --global --type coding
```

变更必须恰好指定 `--global` 或 `--project`；不写 `--type` 就操作该作用域的 defaults。`clear <字段>` 只移除选定覆盖，恢复下层继承；`clear type` 移除选定类型的整条覆盖，保留其他类型。全局文件缺失时执行 clear 会先显式保存初始文档再清除指定项，因此类型删除可以持久生效。worker 仅允许 show，不能通过任务回答调高预算。

show 给出实际类型、控制根、配置/模型/有效窗口、inputBudget、自动压缩状态和逐字段来源，并以 summaryGeneration 汇总摘要恢复策略。MW 负责 maxTokens、compaction.enabled 和 compaction.triggerRatio；摘要准备、保留近期历史、保存和重建使用 pi 原生流程。MW 在原生摘要的 provider 边界单独关闭 thinking，并为输出额度设置下述下限和有限恢复。旧文件中的 targetRatio、keepRecentTokens、maxSummaryTokens、timeoutMs 显示为旧生成字段，不影响当前触发和生成；设置这些旧字段会拒绝，clear 仍可用于清理历史覆盖。不会自动修改用户现有配置文件。

配置采用 version=1，拒绝未知字段、非法 JSON、非对象 types、布尔/字符串数值、非正安全整数。触发比例必须满足 `0 < triggerRatio < 1`，旧 targetRatio 不再限制 triggerRatio。读取接受一个前置 UTF8 BOM；写入为无 BOM UTF8，使用同目录独占锁和临时文件原子替换。锁冲突不会偷锁，损坏或不可读文件不会回退到旧的宽松快照。

每次业务/摘要请求前重新读取策略。修改影响后续请求，不取消已经发出的请求；摘要结束后在业务发送前再次读取并复核。合法数值也可能不适合当前模型或输出预算，此时请求仍会被拒绝。

## 预算与估算

上限是单次请求窗口预算，包含输入和输出预留，不是任务累计 token 配额。模型能力记录保持原值。

```text
E = min(模型 contextWindow, 最终 maxTokens)
R = max(16384, 本次明确输出上限；未指定时使用模型 maxTokens)
S = max(4096, ceil(E × 0.02))
B = E - R - S
Trigger = floor(B × triggerRatio)
```

E/R/S/B 与估算值均可诊断。输出预留或固定 system/tools/任务锚点无法容纳时直接停止，不降低输出预算、不自动扩大窗口。

文本基值为 `ceil(UTF8 字节数/3)`，另加 1024 协议余量；计算覆盖 systemPrompt、工具定义、消息、工具参数和结果，以及实际送入请求的 thinking/签名。图片优先读取已有尺寸，无法识别时每张估算 4096（image-fallback）；base64 传输长度不作为普通文本 token。

真实 usage 的 input+cacheRead+cacheWrite 用于单调上调同一 provider/model/包装版本的校准系数；缓存读取仍占窗口。换模型或包装不会继承不匹配的系数，原生 compact 后重置校准。

本地 Codex 计入与实际请求同源的完整 JSON 包装，并另预留 16384 CLI 附加提示估算。**本地 CLI 不接受调用方 maxTokens 作为解码硬上限**：这里是外层保守预算，不能保证 CLI 内部精确窗口或输出截断。不同 provider 的 tokenizer 无法由此精确预知，服务端 overflow 防护继续保留。

## 自动压缩、恢复与失败

达到 Trigger 且自动压缩开启时，MW 请求 pi 在首请求前或完整工具批次结束后的安全边界执行原生 compact。压缩使用与手动 `/compact` 相同的原生准备、提示词、生成、持久化和活动上下文恢复，不再要求 MW 六字段 JSON，也不再生成新的 MW checkpoint。

原任务的执行循环等待原生 compact 完成，再使用重建后的上下文继续。不会另开 worker、重发用户任务或回放已完成工具；工具批次全部结束后才切换上下文。print/RPC 的原始请求也等待这一过程及最终结案，不依赖后台续行消息或固定延迟。

摘要请求仍经过 MW 当前预算、认证和并发限制。摘要关闭业务 thinking 的继承，初始输出上限为 min(模型最大输出, max(pi 原生摘要额度, 16384))。返回 length 或 stop 但正文为空（含纯 thinking）时，最多重新生成一次：要求简洁、完整保留继续任务所需状态，输出上限为 min(模型最大输出, 初始额度乘2)。每次请求独立取得并发槽并重新检查当前预算/认证；不自动提高窗口上限。不能从标题或标点证明 length 正文完整，因此不接受截断摘要。非空正文且 stop 后才交给原生保存；重生不会回放任务工具。预算/认证拒绝、父取消和其他错误不进入这条重生循环，其他瞬时上游错误沿用原生重试。

恢复成功以 mw-native-summary-result 保存安全尝试信息（次数、实际额度、thinking、状态、正文长度和已知用量）；恢复耗尽以 SUMMARY_TRUNCATED 或 SUMMARY_INVALID 结案，并在 summaryAttempts 中保留同类数字，不保存摘要正文。成功恢复的多次用量合并到原生 compaction usage，不额外写第二份 token 统计。每条工具结果前2000字符的原生摘要输入策略本次未改。

压缩完成后重新检查进展和实际业务预算；恢复耗尽、取消、无进展或仍超预算时停止，不无限重复压缩。完整原始记录保留在会话中，resume 按原生 compaction 边界恢复。

`compaction.enabled=false` 关闭 MW 自动压缩：Trigger 到 B 内仍可发送，超过 B 则停止。手动 compact 仍可用，同样受预算检查。MW 显式请求原生压缩不要求打开 pi 自己的自动压缩开关；不会为此写入全局 settings。原生 compact/tree 通过事件 signal 身份识别，避免递归或重复计量。

策略拒绝携带 `mw_context_policy` 诊断、稳定 code、配置来源与预算数字，并标记 `noProviderRequest=true`、`outerRetryEligible=false`。worker 在 MODEL_ERR 分支前落盘部分交付和 needs-clarification，exit2；不触发同模型重试、备用模型链、phase 推进或恢复自检。原生摘要内部即使把错误转为普通 Error，扩展也把本 run 的 typed 诊断传给结案路径并保存在 run.json 的 context_policy_details。

MW 新增失败诊断只保留固定分类（quota、rate_limit、auth、context、network、unknown）及有可靠证据的 HTTP 状态/白名单错误类型；不复制上游原始错误正文、URL、headers 或 stack。未知原因保持 unknown，历史已丢失的错误无法补回。`noProviderRequest=true` 表示未发送后续业务请求，摘要调用本身仍按实际状态计量。

父取消保持底层 `stopReason=aborted`。沿用现有跨语言状态集合，run.json 使用 failed/exit1 并写 `aborted:true` 与明确取消原因；不会伪装成功或策略 exit2。已改文件、report.md、output.md、trace.log 和原会话保留供接续。

## 认证变化边界

原生摘要与续行业务是独立调用，各自取得并发槽后重新解析当前认证，保留公开 API 可以区分的显式 key/header/env 覆盖。同一次请求排队期间，若 options 的 key 与入口解析值相同，而当前 key 已变化，公开 API 无法区分这是显式覆盖还是核心注入：以结构化 `AUTH_CHANGED` 停止，供调用方用新认证重新进入。认证比较不再跨越摘要和业务两次独立调用。

## 用量统计与排查

新压缩沿原生 compaction/tree usage 统计，不额外写一份 MW 摘要用量。`/mw stats` / `python mw.py stats --json --no-open` 继续读取历史 `mw-context-compaction-usage`，以保留既有统计记录。checkpoint 摘要正文不是统计来源，运行台账不复制 token。

失败原生摘要返回的已知 usage 可以随安全失败诊断保留四个数值；原生统计来源目前只有成功的 compaction 条目，这些失败数值不会自动计入 stats。未知用量不伪造为已知 0，也不把成功摘要重复写为 MW 用量记录。

历史 MW 用量记录按 attemptId 在整个会话内先去重，再按原 attemptStartedAt 过滤时间窗；已知 usage 优先于 unknown/null，更正不会把同一请求移入另一个时间窗或重复计费。历史记录中已经发送但未知的 usage 保留 unknown；只在并发槽中等待、`providerRequestStarted=false` 的取消尝试不计实际 calls/token。策略自身没有发送业务请求的 assistant 诊断不算实际 calls。当前原生 compact/tree 成功只读取各自原生 usage 条目，不添加托管副本；失败统计边界如上一段所述。

停止后先看 `/mw context show --json`、worker 的 Exit Reason / Questions、run.json 的 context_policy_code/context_policy_details 与会话诊断。核对实际类型、控制根、输出预留、固定锚点、摘要结果和配置读取错误，再决定手工 compact、调整显式配置或拆分剩余任务。用户修改策略后下一个请求重新评估；系统不会替用户自动扩大预算。
