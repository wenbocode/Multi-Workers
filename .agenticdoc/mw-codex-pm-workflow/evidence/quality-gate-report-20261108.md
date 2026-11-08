# Codex PM 开发与验收质量报告

任务卡 T-01 约定的验收命令通过，4 项测试全部通过。隔离项目使用真实 AgenticTask 脚本、pi PM 的 `dispatch_worker`、MW 共享队列和 launcher。launcher 启动确定性的离线 worker 子进程，worker 按卡写入计数器实现和交付报告。

| 契约 | 结果 | 可复核证据 |
| --- | --- | --- |
| AC-001 / VC-001 | PASS | 两个进程同时派同一张卡，仅一个新 worker 入队，另一个复用回执。越界路径、不完整卡、失效或被占用的 claim 和 Autopilot 管理的 key 均被拒绝。见 [pytest.log](pytest.log)。 |
| AC-002 / VC-002 | PASS | 新进程在派工后、worker 退出后和独立验收后分别按 key 恢复。队列完成时尚未验收，验收后可查询全部尝试和产物。见 [reconnected-status.json](reconnected-status.json)。 |
| AC-003 / VC-003 | PASS | 对计数器注入错误后，原验收命令触发断言并返回 1。恢复 worker 实现后，同一命令返回 0。验收命令变更、目标工作区变更和失败 worker 都被拒绝。清空报告使既有通过结论失效。见 [失败回执](counter-failed.json)、[失败输出](counter-failed.log)、[通过回执](counter-passed.json)、[通过输出](counter-passed.log)。 |
| AC-004 / VC-004 | PASS | 隔离项目从 SPEC 开始执行真实阶段脚本，到 DONE 后重放所有门禁。见 [sample-audit.log](sample-audit.log)、[操作指南](../../../packages/multi-workers/docs/codex-pm.md)。 |

## 仓库检查

- 任务卡原命令 `python -m pytest -q packages/multi-workers/test_codex_pm.py` 的结果见 [card-acceptance.log](card-acceptance.log)。逐项结果见 [pytest.xml](pytest.xml)。
- 根 `npm run check` 返回 1。Biome 在扫描既有的 `.agenticdoc/mw-dp-consolidation/implementation-worktree/biome.json` 时因重复根配置终止，见 [root-check.log](root-check.log)。单独运行 packages 范围的 Biome 也报告了既有 coding-agent 测试的诊断。
- 根脚本的其余六项单独通过，涵盖依赖版本、TypeScript 导入、shrinkwrap、安装锁、TypeScript 类型和浏览器冒烟检查。Python 编译及 Node 入口语法检查也通过。

## 验证范围

本轮覆盖本地开发、派发、恢复和验收。线上模型提供方的认证、网络和模型实际执行开发卡的效果未在本轮验证。
