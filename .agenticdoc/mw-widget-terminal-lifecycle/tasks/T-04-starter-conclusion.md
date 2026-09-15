# Task T-04: starter prompt 首行结论指令

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker-wtl-t04-starter
- ac_refs: [AC-009]
- vc_refs: [VC-009]
- pattern_refs: []

## 描述
`packages/multi-workers/launcher.py` `_starter_prompt` 追加一句（ASCII，跨 CLI 唯一注入点）：

```
Your final reply MUST open with a one-line conclusion: status plus key
result or blocker.
```

- 追加在现有 starter 文案末尾（"…report results when done." 之后），单段不分节
- 不改 `_build_command`/`_build_env`/argv 传递逻辑（starter 仍是唯一经 argv 的文本，保持短）

**测试**（`packages/multi-workers/test_launcher.py` 追加）：
- `_starter_prompt(...)` 返回值包含 `one-line conclusion`（L0 断言）
- `_build_command` 的 pi/claude/codex 三分支末参数均以该 starter 结尾（既有断言风格）
- 输出 `[VERIFY] VC-009: starter_directive=present` 埋点行

## 输入
- 依赖文件: `launcher.py`（`_starter_prompt`、`_build_command`）
- 依赖 Task: 无
- AC 约束:
  > AC-009: …新完成任务由 worker 侧在 output.md 写入 TL;DR（首行结论、无 markdown 标记、≤100 字符）…（本 Task 做源头引导半：让模型最终回复首行即结论，headline 归一化在 T-03 兜底）
- 设计约束:
  > D-005: 行为引导放 starter（跨 CLI 唯一注入点），归一化兜底放 writeOutput
  > 调研 design-terminal-summary-quality 发现 2: deadline steer 只在预算尾段触发，正常完成不经过——不能替代 starter

## 预期产出
- `packages/multi-workers/launcher.py`（_starter_prompt 一句追加）
- `packages/multi-workers/test_launcher.py`（追加断言）
- 验证方式: `python -m pytest test_launcher.py -q` 全绿 + 埋点；全量零回归
- 验证等级: Level 1

## 约束（worker 派发适用）
- 只碰 launcher.py 的 `_starter_prompt` 与 test_launcher.py 对应新增断言；禁改 `_poll_once`/`_spawn`/`_build_env`（T-02/T-08 在飞或后续）
- [VERIFY] 埋点
- 完成后更新本文件执行记录

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T07:22:54Z | launcher.py `_starter_prompt` 追加首行结论指令；test_launcher.py 追加 `_emit_verify` + TestStarterConclusionDirective（5 用例：starter 含 `one-line conclusion`、pi/claude/codex 三分支末参 == starter 且含指令、VC-009 埋点） | `python -m pytest test_launcher.py -q` 52 passed（0.21s），输出 `[VERIFY] VC-009: starter_directive=present`；全量 `python -m pytest -q` 317 passed, 1 deselected（e2e_real），零回归。只改 `_starter_prompt` 与 test_launcher.py，未碰 `_poll_once`/`_spawn`/`_build_env`/mw_common.py，未 commit |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
