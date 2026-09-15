# Task T-11: L1 集成测试框架 + 状态机/串行/并发

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-010, AC-011, AC-012]
- vc_refs: [VC-011, VC-012, VC-013]
- pattern_refs: []

## 描述
新建 `packages/multi-workers/test_integration.py`（design D-007），假 CLI 注入 + 真 launcher 进程：

1. **fixture**：
   - tmp project：`.agenticdoc/`、`.mw/`、注入版 providers.json（env 源指向测试专用变量名，如 TEST_ANTHROPIC_API_KEY，避免撞真实 env）
   - 假 CLI 目录：Windows 写 `pi.cmd`（`@echo off & echo ran >> "%FAKE_MARK%" & exit /b %FAKE_EXIT%`），POSIX 写 `pi` shell 脚本（`echo ran >> "$FAKE_MARK"; exit ${FAKE_EXIT:-0}` + chmod +x）；目录前插 PATH
   - 起 launcher 子进程 `python launcher.py --project=<tmp> --poll-interval=1`（stdout/stderr 捕获到文件），teardown terminate + 等待退出
   - 轮询断言 helper：读 `_workers.parallel` 至期望状态或超时（默认 30s）

2. **用例**：
   - VC-011：两个 pending（FAKE_EXIT=0 / FAKE_EXIT=1）→ 30s 内 done/failed + 两任务 worker.log 存在
   - VC-012：`--max-workers=1` + 两任务（FAKE_EXIT=0，第二个 FAKE_MARK 文件 mtime / 状态时间戳比较）→ 第二任务 running 晚于第一任务终态
   - VC-013：8 并发 WorkerStore 等价写入（Python 多线程直接写文件 or 起 8 个并发进程调用 upsert 逻辑）+ launcher 同时运行 → 最终行数 = 8 + 原有，无丢失

3. 隔离保证：全测试无真实 LLM 请求、无真实 pi/claude/codex 子进程（假 CLI 是唯一可执行入口；测试专用 env 变量名）

## 输入
- 依赖文件: launcher.py（T-03/T-04/T-05 改造后）、mw_common.py
- 依赖 Task: T-03, T-04, T-05
- AC 约束:
  > AC-010: 在 L1 集成测试以假 CLI 注入 PATH 并放入 exit 0 与 exit 1 两个 pending 任务的条件下，launcher 在 30s 内分别将其置为 done 与 failed，且两个任务目录下 worker.log 均生成
  > AC-011: 在 L1 集成测试以 `--max-workers=1` 放入 2 个 pending 任务的条件下，第二个任务的状态变为 running 的时间晚于第一个任务进入终态的时间
  > AC-012: 在 8 个并发 WorkerStore.upsert 与 launcher 状态写同时运行的条件下，最终 `_workers.parallel` 包含全部并发写入的行，无丢失行

## 预期产出
- test_integration.py（框架 + 3 用例组）
- 验证方式: VC-011/VC-012/VC-013
- 验证等级: Level 1

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
