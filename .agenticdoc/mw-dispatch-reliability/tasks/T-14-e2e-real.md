# Task T-14: L2 E2E 真实链路 test_e2e_real.py

## 基本信息
- Stage: 6
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-013]
- vc_refs: [VC-014]
- pattern_refs: []

## 描述
新建 `packages/multi-workers/test_e2e_real.py`（pytest marker `e2e_real`，默认 deselect/skip）：
1. **skip 判定**：无 timi 凭证（env + config.toml file 源都不可解析）→ `pytest.skip("no timi credentials")`
2. **用例**（真实 LLM，token 成本极小）：
   - tmp project（或本仓库隔离目录）造 task：`type: coding` + prompt "Say exactly: ok"，`_workers.parallel` 写 pending 行（cli=pi, provider=timi）
   - 起 launcher（--poll-interval=1），轮询至终态（超时 120s）
   - 断言：status=done；`output.md` 含 `## Summary` 且 >50 字节；`trace.log` 含 `[FLOW]`
3. **环境不可用标注**：超时/上游 HTTP 失败 → 输出诊断（worker.log 尾部）并标注 "environment unavailable"（不静默 PASS；exit 非 0 但摘要注明需人工判读是否上游故障）
4. 运行方式：`python -m pytest test_e2e_real.py -m e2e_real`（pytest.ini 或 marker 注册避免 warning）
5. CI/常规回归不含该 marker（`-m "not e2e_real"` 默认行为确认）

## 输入
- 依赖文件: launcher.py（pi/timi 路由）、真实 pi CLI 在 PATH
- 依赖 Task: T-03, T-05
- AC 约束:
  > AC-013: 在 L2 E2E smoke 以真实 pi/timi 执行 prompt 为 "Say exactly: ok" 的任务的条件下，任务在 120s 内状态为 done，output.md 含 "## Summary" 节且文件 > 50 字节

## 预期产出
- test_e2e_real.py
- 验证方式: VC-014（实跑记录进 evidence/runs/）
- 验证等级: Level 2

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
