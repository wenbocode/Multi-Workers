# 2026-11-22 跨项目 DP 阻塞回执

已按原因合并为 13 类。可按项目、DP、原因和文件诊断交叉筛选，或在案例页查看 10 例四段对照与任务差额。[交互图表](DP阻塞复盘_动态演示.html) · [v0.5 对照和修复状态](v05-blocked-comparison.md)

15:01:25（北京时间）完成快照。检查 23 个本机目录，在 6 个项目读到 193 条回执。193 个事件 ID 均不同，文件读取和解析错误为 0。统计单位是阻塞事件，同一业务事项可以多次阻塞。

目录集合涵盖 Codex 登记的 10 个本机项目、`E:/MWWS`、`E:/gitlite`、`E:/git` 下发现的项目、Multi-Workers 登记工作树及 Pi 会话中发现的额外项目。仅采集项目根的 `.agenticdoc/_autopilot/dp-blocked/*.json`。测试/历史快照中嵌套目录及没有写过回执的尝试不在统计范围。完整目录和读取状态见[汇总与扫描范围](summary.json)。

| 项目 | 回执 | 材料不完整 | 最近一条（北京时间） | 最近阻塞 |
| --- | ---: | ---: | --- | --- |
| Gaze | 47 | 8 | 11-22 14:39:32 | dp-w-type · disabled |
| UEPerformanceFlow | 45 | 43 | 11-22 06:08:54 | dp-w-type · 文件证据准备失败 |
| RenderPerformance | 33 | 30 | 11-22 12:38:07 | dp-w-type · 文件证据准备失败 |
| Bearing | 31 | 31 | 11-22 14:33:59 | dp-pm-steer · 准备材料无法证明无凭据 |
| SceneProfiler | 24 | 13 | 11-20 19:59:11 | dp-w-type · 上游域名解析失败 |
| Multi-Workers | 13 | 12 | 11-22 02:58:42 | dp-pm-steer · 文件证据准备失败 |
| 合计 | **193** | **137** | | |

[回执全集 JSONL](receipts.jsonl) 每行含项目、原路径、原文件 SHA-256 和完整回执。可按 `receipt.event_id`、`key`、`logical_id`、DP、阶段或原因查找。每条记录保持原归属和时间。

采集后逐条复读源文件，193 条记录的 SHA-256 和内容均与索引一致，各目录的读取计数与汇总一致。

| 原因 | 回执数 | 从现有证据能确定的事 |
| --- | ---: | --- |
| input-incomplete | 137 | 98 条写明文件证据准备失败且未发送。其余包括凭据检查、前置输入检查、接回凭据绑定及身份检查。 |
| disabled / unconfigured | 39 / 11 | 模式或配置状态。Gaze 占 38 条 disabled，SceneProfiler 占 9 条 unconfigured。 |
| upstream-error | 3 | 区分上游通路问题与材料校验。 |
| budget-exhausted | 2 | 核原额度和超限诊断。 |
| failed | 1 | 签收回执。 |

67 条事件带结构化证据诊断，均标为 `transport: not-sent`。诊断有多条时按问题计数，其中未解析文件 111 项、无效引用 46 项、行范围越界 6 项、读取拒绝 4 项、额度超限 2 项、不可读 1 项。**111 是问题数，67 是事件数。** 按 DP 计，w-type 115、steer 51、QG 23、gate 2、sign 1、w-check 1。UEPerformanceFlow 的原 `ueperf-platform` key 留有 4 条 QG `input-incomplete` 回执。

这些实录补充了当前 key 的验收输入。T02/T03 优先核未来输出误当来源、无效字段或范围、读取与额度拒绝。T06/T07 区分材料未发送、配置状态、上游错误与业务接回。T08 从不同项目取代表性回执做脱敏离线回归，并明确拒绝所处阶段。现有回执能证明记录下来的阻塞，对最终单选、回包和 PM 执行仍需关联相应的 wire 和 handoff 证据。

本轮复测现有 Python 配对、来源、授权和新鲜度测试 101 通过、2 跳过，TS 预览与材料诊断 31 通过。TS 首次加载遇到 Windows 临时目录改名权限错误，改用工作区临时目录后通过。这些是现有能力的隔离回归，项目历史恢复仍需运行证据。图表 8 页通过桌面、390px 窄屏、筛选及事件跳转检查，见 [HTML 检查](DP阻塞复盘_动态演示.html.qa.json)和 [筛选检查](explorer-check.json)。
