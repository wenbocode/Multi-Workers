# Task T-09: TS /mw doctor 命令（pi 内双入口）

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-007]
- vc_refs: [VC-008]
- pattern_refs: []

## 描述
在 `ui-bridge.ts::registerMwCommands` 增 `doctor` 子命令（design D-005）：
1. `/mw doctor` 与 `/mw doctor fix`：经 `mw-runner.ts` 新增的 `doctorMw(projectDir, fix)` → `spawnSync(PYTHON_EXE, [mwPy, "doctor", "--project=<dir>", "--json", ...fix])`（timeout 15s，findMwPy 复用现有解析）
2. 解析 JSON 后播报中文摘要：整体状态 + 各节一行结论（service/proxy/orphan/launcher/queue/credentials/bundle）+ fix 模式的修复清单与建议
3. 命令失败（mw.py 缺失 / 超时 / 非零退出）→ `ctx.ui.notify` 错误 + stderr 摘要
4. 与 CLI 同源数据：只经 `mw.py doctor --json`，不在 TS 侧重新实现任何诊断逻辑
5. 用例：mock spawnSync 断言命令行参数含 `doctor --json`（fix 变体含 `--fix`）

## 输入
- 依赖文件: ui-bridge.ts、mw-runner.ts、mw.py（T-07 cmd_doctor）
- 依赖 Task: T-07（doctor --json 接口）
- AC 约束:
  > AC-007: 在 pi PM 会话内执行 `/mw doctor` 的条件下，TUI 播报与 CLI 同源的诊断摘要（复用同一 doctor 数据来源，非两套实现）

## 预期产出
- ui-bridge.ts / mw-runner.ts 改造
- vitest 用例（mock spawnSync）
- 验证方式: VC-008
- 验证等级: Level 0（代码路径 + mock）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-28 20:10 | 执行完成（详见 evidence/runs/l2-summary.md） | PASS |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
