# Task T-14: mw.py init 子命令

## 基本信息
- Stage: 6
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-020, AC-022, AC-036]
- vc_refs: [VC-028, VC-030, VC-031, VC-047]
- pattern_refs: []

## 描述
在 `mw.py` 中实现 `init` 子命令：

1. **前置检查**（AC-036）：检查 `dist/extensions/agent-team-loop.js` 是否存在（相对于 mw.py 所在目录）。不存在 → 输出明确错误信息 + exit 1，**不**创建任何目录。

2. **创建目录结构**（AC-020）：
   - `<project-dir>/.agenticdoc/`（含 `_index.md`、`_index.parallel` 占位文件）
   - `<project-dir>/.mw/`
   - `<project-dir>/.pi/extensions/`

3. **安装 Extension bundle**（AC-036）：将 `dist/extensions/agent-team-loop.js` 复制到 `<project-dir>/.pi/extensions/agent-team-loop.js`。

4. **同步 AgenticTask**（AC-022，可选 `--sync-agentictask <source-dir>`）：将 `<source-dir>` 内容同步到 `<project-dir>/.claude/`。只更新源中存在的文件，保留目标中独有的用户文件。

exit 0 表示成功。

## 输入
- 依赖文件: `dist/extensions/agent-team-loop.js`（T-15 构建）、`mw.py`（T-06 框架）
- 依赖 Task: T-06（mw.py 框架）；T-15（bundle，软依赖——init 检查 bundle 存在性，T-15 负责构建）
- AC 约束:
  > AC-020: init 后 .agenticdoc/_index.md 存在，.pi/extensions/agent-team-loop.js 存在，exit 0
  > AC-022: --sync-agentictask 后 .claude/scripts/update_index.py 存在；用户自定义文件不被删除
  > AC-036: bundle 不存在 → exit 1 + 明确错误信息，不创建不完整目录

## 预期产出
- `mw.py`（init 子命令完整实现）
  - `init(project_dir, sync_agentictask_source=None)`
  - `_check_bundle(mw_dir) -> bool`
  - `_sync_dir(src, dst)` — 只更新 src 中存在的文件
- 验证方式: VC-028（目录结构 + bundle）、VC-030/031（sync）、VC-047（bundle 缺失 exit 1）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
