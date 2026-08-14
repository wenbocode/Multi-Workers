# Task T-16: smoke_test.sh E2E 验证

## 基本信息
- Stage: 7
- 代码状态: 未开始
- 验证状态: 未验证
- 负责 Agent: TBD
- ac_refs: [AC-013, AC-021, AC-028, AC-030, AC-034, AC-035]
- vc_refs: [VC-021, VC-029, VC-037, VC-039, VC-045, VC-046]
- pattern_refs: []

## 描述
实现 `smoke_test.sh`：覆盖所有 L2 E2E VCs 的端到端验证脚本（Git Bash on Windows）。

**测试场景**：
1. `mw init` 初始化含空格路径的项目目录
2. `mw serve` 启动，验证 PID 文件存在（VC-045）
3. 第二个 `mw serve` 实例被拒绝（VC-045）
4. proxy 三端口 LISTENING（VC-021）
5. 写一条 `pending` 任务到 `_workers.parallel`，验证 ≤ 5s 内被检测（AC-001）
6. kill pi 进程，验证 mw serve 存活（VC-046）
7. `mw stop` 停止服务，PID 文件清理

每个断言失败时输出 `FAIL: <描述>` 并 exit 1；全部通过输出 `PASS: smoke_test` 并 exit 0。

## 输入
- 依赖文件: 全部 Stage 1~6 产出
- 依赖 Task: T-01~T-15 全部
- AC 约束:
  > AC-013: netstat 三端口 LISTENING
  > AC-034: PID 文件 + 防重复
  > AC-035: pi 退出不中止 mw serve

## 预期产出
- `smoke_test.sh`（Git Bash 脚本）
  - 自包含（含清理逻辑，测试前后 `mw stop` 确保不留残余进程）
  - 使用含空格路径 `/tmp/test project/` 作为测试目录（AC-015 覆盖）
- 验证方式: smoke_test.sh exit 0
- 验证等级: Level 2

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
