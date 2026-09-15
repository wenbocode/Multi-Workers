# Task T-01: 基线冻结（手动套件对照锚点）

## 基本信息
- Stage: 0
- 代码状态: 代码完成（5 个测试侧基线修复，用户批准 B 方案）
- 验证状态: 验证通过（四套件全绿，基线已冻结）
- 负责 Agent: PM 窗口（WENBOZHOU-PC4:8420，用户指令直执）
- ac_refs: [AC-012]
- vc_refs: [VC-014]
- pattern_refs: []

## 描述
在任何实现改动落盘**之前**，固化现有手动工作流测试套件的基线结果，作为 AC-012「未启用零回归」的对照锚点（evidence-requirement 落盘约定：套件清单 + 期望通过数在实现期首 commit 固化）。

步骤：
1. 盘点 `packages/multi-workers/` 下全部 `test_*.py` 与 `smoke_test.sh`
2. 按 mw-dispatch-reliability key 的 L0/L1/L2 测试矩阵执行全部套件（原样运行，不修改任何被测代码）
3. 将套件清单、执行命令、期望通过数、原样输出固化到 `.agenticdoc/goal-autopilot/evidence/baseline/baseline-manual-suites.md`
4. 本 task 的产物必须在首个实现 commit（T-02 起）之前完成并单独 commit（或与 T-02 同 PR 但文件先落盘）

注意：
- 本 task 为只读验证 + 证据落盘，不改任何产品代码
- 若现有套件存在已知失败（非全绿），如实记录失败项与原因，作为基线事实（AC-012 对照口径 = 与基线一致，非绝对全绿；但预期应为全绿，异常需上报 PM）
- Windows 环境运行，注意 Python 调用方式与既有矩阵文档一致

## 输入
- 依赖文件: `packages/multi-workers/test_*.py`、`packages/multi-workers/smoke_test.sh`、mw-dispatch-reliability key 的测试矩阵文档（`.agenticdoc/mw-dispatch-reliability/` 下 research/evidence）
- 依赖 Task: 无（首个 task）
- AC 约束:
  > AC-012: 在 autopilot 未启用的项目上，conductor 进程不存在（`mw status` 不显示），现有手动工作流测试套件（packages/multi-workers/ 下 test_*.py 与 smoke_test.sh，按 mw-dispatch-reliability key 的 L0/L1/L2 矩阵执行）结果与引入前一致（全绿），`.agenticdoc` 下无 conductor 写入的新文件

## 预期产出
- `.agenticdoc/goal-autopilot/evidence/baseline/baseline-manual-suites.md`（套件清单 + 执行命令 + 期望通过数 + 原样输出）
- 验证方式: 基线文件存在且含全部套件的通过数记录；后续 T-16/T-18 对照此文件判定零回归
- 验证等级: Level 0（证据固化）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 00:43 | 首跑四套件 | L1 121 passed+1 deselected；TS vitest 90 passed；e2e_real 1 FAIL；smoke 5 PASS/4 FAIL |
| 2 | 2026-09-10 00:50-01:10 | 受控实验归因 5 个失败（探针 serve / tee 管道捕获 / tasklist 对照 / 诊断副本现场保留） | 全部定位为测试侧缺陷，产品行为验证正确；上报用户 |
| 3 | 2026-09-10 01:15 | 用户批准 B 方案 → 修复 5 项（e2e keyed 布局 / T3 pipefail 语义+timeout / T5 cygpath / T6 tasklist 回退 / VC-028 全局安装断言） | smoke 9/9 PASS；e2e_real 1 passed（17.1s 真实链路）；L1 回归 121 passed；TS 90 passed（未受影响） |
| 4 | 2026-09-10 01:20 | 基线冻结 evidence/baseline/baseline-manual-suites.md（套件清单+期望通过数+原样输出+修复记录+AC-012 对照口径） | 基线基点 commit 357296d89；待与测试修复同批 commit |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E-001 | 测试陈旧 | test_e2e_real.py:_make_task | invalid worker-task location: e2e-ok\task.md - tasks must live under .agenticdoc/{key}/workers/... | 已修复（_scratch/workers/ 布局） |
| E-002 | 测试逻辑 | smoke_test.sh:T3 | set -o pipefail 使 `serve \| grep -q` 在拒绝 exit 1 时整体判假 | 已修复（输出/退出码分捕 + timeout 10） |
| E-003 | 跨平台路径 | smoke_test.sh:T5 | 队列行 POSIX 路径 Windows Python 解析不到 → stale 归档 | 已修复（cygpath -w） |
| E-004 | 环境探测 | smoke_test.sh:T6 | Git Bash kill -0 对 DETACHED_PROCESS 误报死亡 | 已修复（tasklist //FI 回退） |
| E-005 | 测试陈旧 | smoke_test.sh:T1 | 断言项目本地 bundle，实际全局安装生效（AC-036） | 已修复（按 init 输出断言实际安装路径） |

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
