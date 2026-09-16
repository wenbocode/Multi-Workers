# Mini-Spec: mw-bootstrap-fresh-install-tolerance

- Date: 2026-09-16
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop
- 来源：接手上个中断会话的未提交改动（mw.py / test_mw_bootstrap.py / 根 README 小节 /
  新建 packages/multi-workers/README.md 均为半成品），补齐一致性并闭环。

## Problem

全新机器上 `mw bootstrap` 第 1 步凭据预检失败即中止——但全新安装时
`~/.pi/agent/auth.json` 本来就不存在（凭据要在安装完成后才配），导致
一条命令引导新机器的承诺失效。用户必须手动跑步骤 2-6 再回来。

## Change

- `mw.py` `cmd_bootstrap`：`precheck["all_missing"]` 不再 fail-fast——
  警告（含配置指引：`TIMI_API_KEY` 或写 `~/.pi/agent/auth.json`）后继续，
  跳过步骤 7（服务启动），doctor 判决容忍该预期 issue；有凭据路径照常
  打印可用路由。步骤 1 的 docstring 同步。
- `test_mw_bootstrap.py`：`test_no_credentials_warns_proceeds_and_skips_service_start`
  重写为新契约（rc=0、步骤 2-6 执行、步骤 7 skip、doctor 容忍）。
- `packages/multi-workers/README.md`（新）：包级完整文档（架构图、8 步表、
  CLI、双工作区、pi 窗口命令、环境变量、测试）。重写为干净 UTF-8——
  上个会话经 PowerShell 管道写入已损坏（P-001 同类），且第 1 步描述与
  新行为矛盾，一并修正。
- 根 `README.md`：新增 Multi-Workers 小节（指路包 README）。
- CHANGELOG：`mw bootstrap` 条目改为新行为描述（fail-fast → 警告+跳过步骤 7）。

## Files

- packages/multi-workers/mw.py
- packages/multi-workers/test_mw_bootstrap.py
- packages/multi-workers/README.md（重写，修复 mojibake + 行为描述）
- README.md
- packages/multi-workers/CHANGELOG.md

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 无凭据时 bootstrap 不中止：步骤 2-6 执行、步骤 7 skip、rc=0、警告含 auth.json 指引 | pytest 20/20 |
| AC-002 | 有凭据路径不受影响（打印可用路由、照常 start） | 既有用例回归 |
| AC-003 | 包 README 无 mojibake、第 1 步描述与新行为一致 | read 工具目检 |
| AC-004 | CHANGELOG 与实现一致 | 目检 |
| AC-005 | 包级全量测试无回归 | pytest 430 passed |

## Result

- AC-001/002：`test_mw_bootstrap.py` 20/20 通过（含重写后的新契约用例）。
- AC-003：README 重写为干净 UTF-8（write 工具），第 1 步描述改为
  「警告后继续、跳过步骤 7、`--fast` 补启」，步骤 7 行同步；测试计数
  422+ → 430+。
- AC-004：CHANGELOG bootstrap 条目的 fail-fast 句已替换为警告+跳过描述。
- AC-005：`python -m pytest packages/multi-workers -q` → 430 passed, 8 deselected。
- 状态：完成（含接手时已就绪的代码改动；本会话补齐 README/CHANGELOG/记录）。
