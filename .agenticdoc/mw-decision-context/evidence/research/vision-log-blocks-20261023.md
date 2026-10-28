# T14：两张截图的日志式区块识别

## 结论与边界

已通过 image read 实际查看两张 PNG，并全文读取 `packages/multi-workers/decision_dashboard.html` 与 `decision_dashboard.js`。截图对应的两个默认大块是 **`#pg-meta` 的 DP 元数据清单** 与 **`#pg-detail` 中 DAG 前的测试详情清单/摘要**，不是直接对应任务提示中的“本页测试操作反馈”或 `#pg-submit-out`。建议只精简默认展示，保留 DAG、所选节点详情、简短按钮/结果/错误反馈与只读轮询。本文为只读分析，未实施。

## 1. Monitor-DP-Test1.png：DP 配置/契约元数据清单

**截图事实**（`.agenticdoc/mw-decision-context/evidence/Vision/Monitor-DP-Test1.png`）：

- 该清单本身没有可见独立标题；顶部是上一段提示“questions 只影响本次 observe_only 观察请求…”，不是清单标题。
- 清单标签/值：`DP = dp1-dispatch-type`；`tier（P0 = 生产默认关闭）= P2`；“默认启用” `true`；“默认模式” `auto`；“当前启用（项目配置）” `true`；“当前模式” `auto`；“配置来源” `config`；`questions_version = q-ac4a6184`；`executor（本页从不执行）= unwired`；`wired = false`；“预算 max_state_bytes” `8192`；“传输（配置态，不探测）” `unknown · 未记录`；“观察提交契约” `observe_only=true（人工显式提交，仅观察）`。
- 底部文字：“配置层：OK · 配置告警：（无）”。这是配置诊断的 definition list，不是一次模型调用或操作日志。

**源码对应**：

- HTML `:115–117`：questions 边界提示之后的 `<div id="pg-meta" ...>`；`#pg-fields` 是另一个容器，不属于截图这份元数据清单。
- JS `renderSelectedDp()` `:1962–2002`：`:1972–1987` 构造上述 `rows` 并调用 `definitionList(rows)`；`:1994–1995` 输出配置层/告警。字段组合和文字逐项吻合。
- `renderDpOptions()`、`onDpChange()`、case 载入会调用该 renderer；`loadPlayground()` 读取 `/api/dps` 元数据。删除默认元数据清单不需要停止元数据读取。

**最小建议（不是截图事实）**：停止默认输出这份完整 `definitionList(rows)`，改为一句 DP/仅观察说明（DP 已有选择器），只在确有 P0、关闭或配置异常时保留必要警告。版本、executor/wired、预算与传输配置诊断可置于默认收起的“技术详情”，不改注册表、配置或发送契约。保留 `#pg-fields` 的业务输入契约、questions 编辑器和业务 state 编辑器。

## 2. Monitor-DP-Test2.png：本页测试详情中 DAG 前的技术清单/摘要

**截图事实**（`.agenticdoc/mw-decision-context/evidence/Vision/Monitor-DP-Test2.png`）：

- 可见主标题：“本页测试 DAG · 尚未发起测试 · 未调用模型（非后端决策记录）”。
- 技术字段依次是 `submission_id`、`dp`、`state`、`retry_of`、`decision_id`、`decision_ran`、`call_id`、`book_ref`、`state_digest`、`zero_call`、`http_attempts`、`capture_status`、`started_at`、`finished_at`、`answer_persisted`、`projection_status`、`projection_sha256`、`projection_redactions`。
- `dp = dp1-dispatch-type`、`zero_call = true`，其余字段均显示“未记录”。这不是已发生调用的证明。
- 下面三个可见标题/内容：“当次答案（来自该 submission 的持久化安全投影）” → “当次答案：未持久化（未记录）”；“拒绝/问题项” → “拒绝/问题项：无”；“采纳判定与动作预览” → “采纳判定/动作预览：未记录”。
- 截图未包含 DAG 图本体；标题中的 DAG 一词不表示应删除 DAG。

**源码对应**：

- HTML `:161`：`<div id="pg-detail" ...>`。
- JS `renderSubmissionDetail()` `:2127–2206`：`:2136–2138` 输出对应本地操作标题；`:2139–2158` 输出与截图相同的 18 项 definition list；`:2159–2171` 输出答案、问题项、采纳/动作预览。
- 默认加载路径 `loadPlayground()` `:2363–2368`：无记录且无已有详情时调用 `renderLocalTest("尚未发起测试", "未调用模型", null, null)`；`renderLocalTest()` `:1662–1666` 构造 `local_operation/local_status/observe_only/zero_call` 并进入 `renderSubmissionDetail()`。这解释了截图标题、`zero_call=true` 和大量未记录占位。
- 同一函数 `:2172–2202` 随后创建 `#pg-dag-graph` / `#pg-dag-node-detail`，调用 `submissionDagNodes()`、`renderDagGraph()`，并恢复选中节点；`:2202` 另追加 `renderAttempts(row)`。不可隐藏或删掉整个 `#pg-detail`，否则 DAG 与节点详情也会消失。

**最小建议（不是截图事实）**：移除 DAG 前默认展开的技术 definition list；初始“尚未发起测试”时不要展开全是未记录的答案/问题/预览占位。保留一句状态边界、真实结果的简短答案/采纳结论、非空问题/错误。技术字段及整份 attempts 可留给显式打开、默认收起的技术详情；保留后续 DAG 布局、节点点击/键盘详情、实际请求/返回节点渲染和选中节点恢复。

## 3. 引用位置差异与保留要求

- 任务提示 HTML `:145` 在当前源码是测试记录表的 `<caption>`；“本页测试操作反馈”实际在 `:136–138`，其 `#pg-operation-rows` 由 `operationFeedback()` `:1651–1660` 输出时间/操作/状态，最多 20 项。两截图均没有出现此标题或列表，不能把它当作第一图的事实。若另需减少累积操作日志，可停止默认呈现列表，但保留该函数首先更新的 `#playground-status`，以免丢失按钮反馈。
- 任务提示 JS `:1708` 在当前源码位于 `answerEntries()`；实际提交输出 renderer 是 `renderSubmitResult()` `:1770–1828` → `#pg-submit-out`（HTML `:135`）。它有 `accepted/duplicate/busy/observe_only/record_status` 等额外字段，截图 2 没有这些字段，且标题来自本地操作，故不能将截图 2 精确归到提交响应输出。
- 提交响应技术字段也可另行默认折叠，避免与详情重复；保留成功/失败/重复/busy 的真实状态区分与错误，不能以 HTTP 200 代替成功判定。此项为关联建议，不是第三个截图发现。
- 保留 `startSubmissionPoll()` `:1674–1702` 的每秒只读 GET `/api/test/history` 与 `/api/test/submissions/<id>`、终态停止、epoch 丢弃迟到响应、串行读与失败后只重读；保留 `sendSubmit()` 的显式提交边界，不新增自动提交/重试。

## 不确定与未覆盖

- PNG 是局部截屏：未见整页、DAG 本体、按钮区或实际运行错误；不能推出这些区域不存在。
- 当前仓库源码的文字与字段完全对应，但未核验截图时运行资产的 hash/版本，也未确认浏览器正在使用该份源码；引用行号可能随并发改动变化。
- 未打开真实浏览器、未做运行时/生产验收、未调用模型/决策服务、未验证 provider 或凭证、未起停共享服务、未 build/install/commit，未修改源码、配置或框架。唯一写入为本证据文件。
