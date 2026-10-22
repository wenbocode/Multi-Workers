# W-04b — runner 集成测试 + 守卫断言：test_console_storm_guard.py

- key: mw-console-storm-hardening · type: coding · 波次 2（W-01 已终态）
- ac_refs: AC-001, AC-002, AC-003, AC-004, AC-007 · vc_refs: VC-001, VC-002, VC-003, VC-004, VC-007
- 依赖: W-01（csg-w01-python-core，已终态）· 预计: 45-60min

## 上下文

goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」；spec.md AC-001/002/003/004/007；design.md D-001/D-002/D-004。被测对象 = `packages/multi-workers/mw.py` 的 cmd_start（已改：`CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW`，serve-console.log 重定向）+ `packages/multi-workers/console_run.py`（cmd_run_detached / run_supervisor，W-01 已落地）。W-01 已实测的契约形态（可作断言蓝本）：4 行 stdout、marker schema `mw-run/1`（rc/timed_out/started_at_ms/ended_at_ms/wall_sec/pid/argv）、heartbeat `mw-heartbeat/1`、timeout rc=124 + taskkill /T、spawn 失败 rc=127 + spawn_failed、guard 注入（`MW_CONSOLE_GUARD=1` + PYTHONPATH 前置；`=0` 跳过；缺目录 stderr 单行告警）、run-dir `-N` 后缀、`_run_supervisor` 不出现在 help。锚点: `packages/multi-workers/mw.py:506`（cmd_start L0 改点）、`packages/multi-workers/console_run.py:1`（runner 模块）、`packages/multi-workers/test_common.py:740`（monkeypatch Popen 捕获 kwargs 的既有断言模式）。

## 要求

新建 `packages/multi-workers/test_console_storm_guard.py`（pytest，`print(..., flush=True)` 风格），断言组：

1. **VC-001**：monkeypatch `subprocess.Popen`（捕获 kwargs，test_common.py:740 先例）调 `cmd_start`（组装 argparse.Namespace）→ 断言 win32 kwargs["creationflags"] == CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW 且按位不含 DETACHED_PROCESS；断言 stdout/stderr 重定向目标为 `.mw/serve-console.log`（temp project dir 构造）。
2. **VC-002 守卫**：遍历 `packages/multi-workers/**` 非 test_*.py 的 .py 文件，**逐行剥离 `#` 注释后** grep `DETACHED_PROCESS` → 断言命中 = 0（注释允许——mw.py 有意保留 M2/M3 说明注释）；同时断言 `.agenticdoc/mw-console-storm-hardening/evidence/research/design-spawn-site-audit-20261015.md` 存在。
3. **VC-003 集成**：真实短命令跑 `cmd_run_detached` 全链（win32 下 `cmd /c exit`，posix 分支 seam 跳过）：断言 stdout 恰 4 行（pid/marker/heartbeat/log）、marker.json schema=mw-run/1 且 rc=0、cmd.txt 内容正确、run.log 存在。轮询 marker 出现（timeout ≤15s）。
4. **VC-004**：(a) `--heartbeat-s 0.5` + 长命令（`ping -n 3`）→ 轮询 heartbeat.json 至少 2 次不同 ts_ms；(b) timeout seam：`--timeout-min 0.05` + 长命令 → marker rc=124 + timed_out=true（复用 W-01 实测参数）。
5. **VC-007**：platform seam（monkeypatch sys.platform 或注入参数）断言 posix 分支传 start_new_session=True 且 kwargs 无 creationflags。
6. 子进程隔离：集成用例用 tmp_path 做 cwd/run_dir，不污染仓库；每用例结束回收（marker 出现即说明 supervisor 已退出，残留 ping 等由 timeout 自然消亡）。
7. 文件头注明 ac_refs；失败消息含实际 flags 数值/文件路径。

## 写入允许面

- `packages/multi-workers/test_console_storm_guard.py`（新建）

## 写入禁止面

- 其余一切（console_run.py/mw.py 只读、test_mw_console_guard.py 是 W-04a 领地、guard 包只读）；禁止 git add/commit；禁止跑全量套件

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_console_storm_guard.py -q -s 2>&1 | Select-Object -Last 10
```

期望：全绿（通过计数 ≥ 断言组数）。

## 改动历史

- 2026-10-15 W-04b 首派（W-04 的 runner 半；W-04a 已先行并行）。

## 交付格式

- 测试文件全文 + pytest 原始输出 tail（≤10 行）+ 断言组与 VC 对照清单 + grep 守卫的命中计数说明（剥注释前后对比）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行，长输出落临时文件只回读 tail。
