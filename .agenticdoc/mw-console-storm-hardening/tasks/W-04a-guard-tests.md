# W-04a — guard 单测：test_mw_console_guard.py

- key: mw-console-storm-hardening · type: coding · 波次 1.5（W-02 完成后即可，与 W-01/W-03 并行）
- ac_refs: AC-005, AC-006, AC-007 · vc_refs: VC-005, VC-006, VC-007
- 依赖: W-02（csg-w02-guard-package，已终态）· 预计: 30-45min

## 上下文

goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」；spec.md AC-005/006/007；design.md D-003/D-004。被测对象 = `packages/multi-workers/mw_console_guard/`（W-02 已落地：sitecustomize.py 激活器 + mw_console_guard.py 65 行补丁模块）。测试判据沿用 RQ-3 语义电池（evidence/research/design-guard-injection-mechanics-20261015.md Q2/Q3：popen_init_name 判据、观测入参断言、fail-open 注入异常）。锚点: `packages/multi-workers/mw_console_guard/mw_console_guard.py:32`（patched 定义）、`packages/multi-workers/mw_common.py:1572`（platform seam 测试模式先例）。

## 要求

新建 `packages/multi-workers/test_mw_console_guard.py`（pytest，本包风格：`print(..., flush=True)` + `-s` 友好），断言组：

1. **激活语义**（VC-005）：MW_CONSOLE_GUARD=1 下 `creationflags=0` 被 OR `CREATE_NO_WINDOW`（观测入参：wrap 后以捕获 Popen 或 monkeypatch 验证实际传入值）；显式 `CREATE_NEW_CONSOLE` 原样；显式 `DETACHED_PROCESS` 原样；kwargs（stdout/stderr/cwd/env）透传。
2. **未激活零副作用**（VC-006）：不设 env 时 `Popen.__init__.__name__ == "__init__"`（sitecustomize 经 subprocess 加载或直接 import mw_console_guard 验证 no-op）。
3. **幂等**：重复 `_activate()` 同对象不重 wrap。
4. **fail-open**：注入异常 `_apply`（monkeypatch 或 exec fresh module）→ Popen 保持原 `__init__` + stderr 单行告警 + `_patched` 未置位。
5. **platform seam**（VC-007）：posix 分支 no-op（monkeypatch `os.name` 或经 `hasattr(subprocess,"CREATE_NO_WINDOW")` 分支注入）。
6. 每个用例用子进程（`sys.executable -c`，env 注入用 `[Environment]::SetEnvironmentVariable` 等价或 subprocess env 参数）或 fresh module exec 隔离，禁止污染测试进程全局 subprocess 状态。
7. 文件头注明 ac_refs；断言失败消息含量化值（flags 数值）。

## 写入允许面

- `packages/multi-workers/test_mw_console_guard.py`（新建）

## 写入禁止面

- 其余一切（mw_console_guard/ 只读、console_run.py/mw.py/TS 侧不碰）；禁止 git add/commit；禁止跑全量套件

## 验收命令

```bash
cd packages/multi-workers
node ../../node_modules/vitest/dist/cli.js --version >$null 2>&1   # noop，保持输出卫生
python -m pytest test_mw_console_guard.py -q -s 2>&1 | Select-Object -Last 8
```

期望：全绿（通过计数 ≥ 断言组数）。

## 改动历史

- 2026-10-15 W-04a 首派（从 W-04 拆出：guard 半依赖 W-02 已满足；runner 半留 W-04b 待 W-01）。

## 交付格式

- 测试文件全文 + pytest 原始输出 tail（≤8 行）+ 断言组与 AC 对照清单。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
