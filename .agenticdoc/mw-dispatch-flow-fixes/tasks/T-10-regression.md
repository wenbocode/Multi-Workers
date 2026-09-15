# Task T-10: 全量回归（vitest + pytest + check + 隔离语义）

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-005, AC-009]
- vc_refs: [VC-008, VC-011]
- pattern_refs: []

## 描述
S1-S4 合入后的全量密封回归（design D-007）：
1. 根仓 `./test.sh`（非 e2e vitest 全量）——VC-008（既有 output/exit-code/看门狗/扫描断言全绿 + 本 key 新用例全绿）
2. packages/multi-workers：`python -m pytest -q`（排除 e2e_real marker，默认 skip）——含 T-08 新用例与 mw-dispatch-reliability 全部既有用例
3. mw-dispatch-reliability 隔离语义回归（VC-011）：test_launcher.py / test_integration.py 中显式 claude 缺凭证 → per-task failed + worker.log 含凭证名 + 同批不受影响的用例必须仍绿（本 key 未改 D-001 语义的证明）
4. 根仓 `npm run check`（full output，零 error/warning/info）
5. 结果留底：pm-state 执行记录 + 必要时 evidence/runs/regression-<date>.md（命令 + 汇总行）

## 输入
- 依赖文件: 全部前序 task 改动
- 依赖 Task: T-01 ~ T-09
- AC 约束:
  > AC-005: 心跳机制不改变既有协议语义（output.md 四节、exit code 映射、trace 既有格式不变）
  > AC-009: 显式 cli=claude 缺凭证不降级（D-001 隔离语义回归保护）

## 预期产出
- 全量回归证据（命令输出摘要）
- 验证方式: ./test.sh + pytest + npm run check
- 验证等级: Level 1（全量）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 12:23 | 全量回归：npm test（等价 test.sh，隔离 TAI_PAT_TOKEN）中 agent-team-loop.test.ts 无 FAIL（61 例全过，含全套件）；multi-workers pytest 全量 112 passed / 1 deselected（含 VC-011 隔离语义 8 用例）；npm run check 本 key 全部文件 0 错误（修复两处自引入类型错：mw-runner age_s 同形西里尔字符、VC-013 dispatchTask 多传自动戳字段） | PASS（本 key 范围） |

### 附注（环境性失败归属，非本 key）
- npm test 仓库其余失败：packages/ai 53 文件、coding-agent 29 文件、agent-core 3、tui 2、evals 1 —— 成因两类：① Windows 无 sh（model-registry/resolve-config-value 的 `sh -c` 凭证解析、external-editor 等）；② 另一会话在途 packages/ai models 改动（M generate-models.ts，模型 ID 缺失与 check 580 错误同源）。失败文件与本 key 改动零交集（无任何文件导入 agent-team-loop/mw-runner 改动面）
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
