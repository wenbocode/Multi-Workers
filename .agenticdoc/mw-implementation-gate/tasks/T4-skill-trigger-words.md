# T4: 框架 SKILL.md 触发词扩面

- 状态: done（worker t4-skill-trigger-words，2m）
- 范围: `.agents/skills/agentic-task/SKILL.md`（框架仓 clone）description 追加 non-trivial implementation 触发词；commit + push；`diff-installed.py` 对本仓报 clean。
- 规格: design.md D-9；AC-005。
- 验收: description 含 "non-trivial implementation"；clone HEAD=origin HEAD；diff-installed 无漂移。
- 结果: commit `e9360db`（master，fa97ed6..e9360db 已 push）；diff-installed exit 0（PM 复核：clone clean、仅 SKILL.md 单文件入栈）。AC-005 满足。
- 注意: 框架仓规则——改动后必须 commit+push（changed mirrors must be committed & pushed），install.py 不 pull 自身运行的 clone。
