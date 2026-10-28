# Research: Initial requirement facts (spec)

## 决策问题
本 key 范围来源及 unknown sub 报错初步定位；作为并行研究前的已有事实，不冒充完成调研。

## 调研方法与出处
- 用户 2026-10-22 当前会话：新建 key，决策看板和真实 Jev DP 测试页签。
- `.agenticdoc/goal.md:1` 已完整阅读：文件协调、扩展集成、凭证隔离。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4474-4533` 已读取完整 parseDecideArgs 函数：窗口 usage 仅 show/sign，sub 不为 sign 时返回 unknown sub。
- 命令 `python packages/multi-workers/mw.py --help` 返回 decide 顶级命令；Python 与窗口支持是否一致交 RQ-1 确认。
- `python .agents/skills/agentic-task/scripts/audit_phase.py mw-signoff-per-key` 返回 6 项历史文档违规；旧 key 是 mini-spec 快速路径，本次只记录不修改其他 key。

## 发现
窗口源码明确不支持 dp 子命令，报错字符串匹配用户反馈。这一事实独立于 serve 代码是否过期；是否还存在已安装扩展版本差异待 RQ-1。
决策档案和真实请求证据覆盖率尚未确认；看板技术方案尚未决定。

## 结论 → 决策映射
- spec §1 收录窗口命令差异问题、看板与真实测试三个用户场景。
- spec §4 保留 UI/测试副作用/人工来源/历史补全问题，等待用户与 RQ-1..3。
- 此记录不是零调研声明：只记录已读取的事实，后续研究各写独立证据。
