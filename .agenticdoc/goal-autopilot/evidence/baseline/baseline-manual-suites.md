# Baseline: 手动工作流测试套件冻结（AC-012 对照锚点）

> Key: goal-autopilot · Task: T-01 · 冻结时间: 2026-09-10
> 基线修复基点 commit: `f6cea320c`（5 个测试侧修复的固化 commit；父提交 357296d89 为修复前状态）
> 用途: AC-012「未启用项目零回归」的唯一对照口径——autopilot 实现引入后，下列套件结果必须与本文件记录**完全一致**。

## 1. 套件清单与期望结果

| # | 层级 | 套件 | 执行命令（packages/multi-workers 下） | 期望结果 |
|---|------|------|--------------------------------------|---------|
| 1 | L1 | Python 单测（默认排除 e2e_real） | `python -m pytest` | **121 passed, 1 deselected** |
| 2 | L2 | 真实链路 e2e（真实 pi + timi LLM） | `python -m pytest test_e2e_real.py -m e2e_real` | **1 passed** |
| 3 | L2 | smoke E2E（Git Bash） | `bash smoke_test.sh`（`"D:\Program Files\Git\bin\bash.exe"`，下同） | **PASS: 9 FAIL: 0**（exit 0） |
| 4 | L1 | TS 单测（agent-team-loop 扩展） | packages/coding-agent 下 `node ..\..\node_modules\vitest\dist\cli.js --run test\extensions\agent-team-loop.test.ts` | **90 passed** |

环境事实（对照时需一致）：
- Windows（Python 3.14.3 / pytest 9.0.2 / Git Bash `D:\Program Files\Git\bin\bash.exe`）
- `mw setup` 全局扩展安装生效（`~/.pi/agent/extensions/agent-team-loop.js` 存在 → mw init 走全局安装分支）
- timi 凭证可用（`~/.pi/agent/auth.json`，套件 2 需要）

## 2. 原样输出（冻结时刻）

### 2.1 L1 Python 单测

```
$ python -m pytest
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.2, pluggy-1.6.0
rootdir: H:\git\Multi-Workers\packages\multi-workers
configfile: pytest.ini
plugins: anyio-4.12.1, Faker-40.13.0, respx-0.23.1
collected 122 items / 1 deselected / 121 selected

test_common.py .....................................                     [ 30%]
test_init_source.py .....                                                [ 34%]
test_integration.py ........                                             [ 41%]
test_launcher.py ...............................................         [ 80%]
test_proxy_service.py .........                                          [ 87%]
test_serve_doctor.py ...............                                     [100%]

===================== 121 passed, 1 deselected in 30.22s ======================
```

### 2.2 L2 e2e_real（真实 timi）

```
$ python -m pytest test_e2e_real.py -m e2e_real -v
test_e2e_real.py::TestRealTimiDispatch::test_say_exactly_ok_full_chain PASSED [100%]
============================= 1 passed in 17.08s ==============================
```

### 2.3 L2 smoke_test.sh

```
$ bash smoke_test.sh
=== T1: mw init ===
[mw init] Using global extension install: C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js
[mw init] framework installed from H:\git\Multi-Workers\.agents\skills\agentic-task
[mw init] Project initialized: C:\Users\wenbozhou\AppData\Local\Temp\test project
PASS: VC-028: .agenticdoc/_index.md exists
PASS: VC-028: Extension bundle installed (global)
=== T2: mw serve start ===
[mw start] background PID: 86140
PASS: VC-045: PID file exists after start
=== T3: duplicate serve rejected ===
PASS: VC-045: duplicate serve rejected
=== T4: proxy ports LISTENING ===
PASS: VC-021: port 17001 LISTENING
PASS: VC-021: port 17003 LISTENING
=== T5: pending task detection ===
PASS: AC-001: pending task detected within 1s
=== T6: mw serve survives pi exit ===
PASS: VC-046: mw serve still running after test (pi not running)
=== T7: mw stop ===
[mw stop] stopped PID 86140
PASS: VC-045: PID file cleaned up after stop

==============================
PASS: 9  FAIL: 0
PASS: smoke_test
```

### 2.4 L1 TS vitest

```
$ node ..\..\node_modules\vitest\dist\cli.js --run test\extensions\agent-team-loop.test.ts
 Test Files  1 passed (1)
      Tests  90 passed (90)
```

## 3. 基线修复记录（用户批准的 B 方案，2026-09-10）

冻结前首跑发现 5 个失败，逐一受控实验定位，**全部为测试侧缺陷（产品行为验证正确），经用户批准后修复，修复后全绿冻结**：

| # | 失败项 | 根因 | 修复 |
|---|--------|------|------|
| 1 | e2e_real FAIL（invalid worker-task location） | `_make_task` 在 `.agenticdoc/{key}` 根级建任务；launcher 自 mw-dispatch-reliability §7（2026-08-28 21:15 keyed 布局）起拒绝根级 task.md，那次迁移晚于其最后一次 e2e 运行 | task_dir 改 `.agenticdoc/_scratch/workers/{key}`（两处路径） |
| 2 | smoke T3「duplicate serve not rejected」 | `set -o pipefail` + 拒绝路径 exit 1 → `cmd \| grep -q` 管道整体判假（tee 实证消息正常输出，产品拒绝逻辑正确） | 输出与退出码分开捕获，双条件断言；加 `timeout 10` 防重复检查失效时挂死 |
| 3 | smoke T5「task NOT detected」 | 队列行 task_path 为 POSIX 路径；MSYS 只转换 argv 不转换文件内容，Windows Python 按当前盘符解析 → task.md 判缺失 → stale 归档（launcher.log 实证） | `cygpath -w` 转换队列行内路径 |
| 4 | smoke T6「serve not running」 | Git Bash `kill -0` 对 DETACHED_PROCESS 误报死亡（tasklist 与 Python OpenProcess 均确认存活） | `_pid_alive` 助手：kill -0 失败回退 `tasklist //FI` |
| 5 | smoke VC-028「bundle installed」 | mw init 现走全局扩展安装（mw-stale-builtin-fix，AC-036 global wins），测试仍断言项目本地 `.pi/extensions/` | 按 init 实际输出断言全局或本地路径存在 |

诊断证据（当场实验，未留档文件，结论记录于此）：
- 受控复现：mw start → 3s 后 PID 存活（tasklist）→ duplicate serve 输出 `[mw serve] already running (PID X)` 且 exit 1（消息与退出码均正确）
- 诊断副本 tee 捕获 T3 管道原始输出含拒绝消息（grep 已匹配，pipefail 吞掉结果）
- 原版 smoke 两次复现 5/4，修复后 9/9；e2e_real 修复后 17.1s 真实链路通过

## 4. 对照口径（AC-012）

autopilot 任一实现 task 完成后（尤其 T-16/T-18）：
1. 在未启用 autopilot 的状态下重跑第 1 节全部命令
2. 逐项比对通过数：121+1deselected / 1 passed / 9 PASS 0 FAIL / 90 passed
3. 任何偏差 = AC-012 FAIL，进入修复回路
4. 若套件自身因非 autopilot 原因演进（如新增测试），以「同一 commit 范围内的既有测试无回归」为准，并在 evidence 中注明演进项
