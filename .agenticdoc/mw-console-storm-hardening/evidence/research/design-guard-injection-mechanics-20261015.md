# Research: sitecustomize console-guard injection mechanics (RQ-3)

> key: mw-console-storm-hardening · card: T-03-RQ3-guard-injection.md · type: research
> date: 2026-10-15 (本机 Win11, 默认终端委托 = Windows Terminal, Python 3.14.3 @ pythoncore-3.14-64, pytest 9.0.2)
> 决策问题: L2 subtree console guard（spec §1.1）——sitecustomize + PYTHONPATH 注入机制的四个设计输入（Q1-Q4）
> 约束锚点: spec §2.3（仅 env 激活、不改写显式 flag）、AC-005/006/007
> 实验载体: `%TEMP%/mw-csg-rq3/`（清单见「残留与未验证」末尾 + progress.md）；本文件为仓库内唯一写面

## 结论

四问全部实证通过，无 BLOCKER。Q1 关键判定：PYTHONPATH 前置的 sitecustomize 在 CPython（含 `python -X utf8 -m pytest`，conftest 同进程）链上稳定加载；venv 场景下 PYTHONPATH 版 sitecustomize 胜出（site 模块同名单次加载语义）；`python -S` 跳过（符合预期，记录）。Q2：patch `subprocess.Popen.__init__` 一处覆盖 `run`/`Popen` 两入口成立；未指定 console 语义时 OR `CREATE_NO_WINDOW`、显式 `CREATE_NEW_CONSOLE`/`DETACHED_PROCESS` 原样保留、`**kwargs` 透传完整；幂等（double import/reload 不重 patch）。Q3：未激活 import 零副作用；激活生效；注入异常 fail-open（恢复原 Popen + 单行 stderr 警告，宿主不崩）。Q4 事故 §7.1 最小复现：off 轮观测到 openconsole 新窗口（a1=4, a2=1），on 轮严格 0 ×2 轮；guard 目录 sitecustomize 在 DETACHED 子进程内被加载，child_flags 确认 off/on 全部十次 spawn 均以 `creationflags=0` 发起。
→ design 决策：runner 注入 = 子树 env `PYTHONPATH=<guarddir>;<existing>` + `MW_CONSOLE_GUARD=1`；guard 目录含 `sitecustomize.py`（import guard 模块）+ `mw_console_guard.py`（骨架见下）。

## 证据

### 探针原始输出（tail）

Q1 加载时机:
```
$env:PYTHONPATH=q1; python -c "import sys; print('sc' if 'sitecustomize' in sys.modules else 'no-sc')"   -> sc
$env:PYTHONPATH=q1; python -S -c "..."                                                                     -> no-sc   # -S 跳过 sitecustomize（预期）
$env:PYTHONPATH=q1; python -X utf8 -m pytest -q q1\test_mini.py                                             -> 1 passed in 12.78s
$env:PYTHONPATH=q1; python -X utf8 -m pytest -q q1\test_chain.py                                            -> 1 passed in 9.38s   (conftest stderr: "conftest: sc"; 断言 sitecustomize in sys.modules 成立)
sc-loaded.marker (逐行增长, 每次启动 +1):
2026-10-15T14:55:30 pid=72832 ...   # python -c
2026-10-15T14:55:38 pid=59732 ...
2026-10-15T14:55:57 pid=51888 ...   # pytest run 1
2026-10-15T14:56:16 pid=71124 ...   # pytest run 2 (test_chain)
2026-10-15T14:56:27 pid=67164 ...
2026-10-15T14:57:05 pid=58524 ...   # venv python (PYTHONPATH q1)
```

venv 冲突（`python -m venv v1` 3.14.3, venv site-packages 放入同名 sitecustomize.py；PYTHONPATH 仍前置 q1）:
```
q1\venv-report.txt:
default: sc_in_modules=True file=C:\Users\...\Temp\mw-csg-rq3\q1\sitecustomize.py
venvtest\v1\venv-sc-loaded.marker -> NO        # venv 自带 sitecustomize 未被执行
```
→ **PYTHONPATH 的 sitecustomize 胜出**。conda 未测（本机无 conda），如实记录。

Q2/Q3 guard 骨架（`PYTHONPATH=guard; MW_CONSOLE_GUARD=1`, 拦截探针）:
```
q2_results.jsonl:
{"case": "double_import", "patched": true, "same_obj": true, "popen_init_is_patched": true}
{"case": "run", "creationflags": "ABSENT"}            # subprocess.run -> Popen 被拦截
{"case": "popen", "creationflags": "ABSENT"}          # 直接 Popen 被拦截
{"case": "explicit_new_console", "creationflags": 16} # CREATE_NEW_CONSOLE 原样保留
{"case": "kwargs", "kwargs": {"stdout": -3, "stderr": -3, "cwd": "...\q2", "env": {"A": "B"}}}  # 透传完整

q3_results.jsonl:
{"mode": "inactive", "guard": "mw_console_guard", "observed_creationflags": 0, "popen_init_name": "__init__"}
{"mode": "active",   "guard": "mw_console_guard", "observed_creationflags": 0, "popen_init_name": "patched"}
{"mode": "broken",   "guard": "mw_console_guard_broken", "observed_creationflags": 0, "popen_init_name": "__init__"}
stderr: mw_console_guard: patch failed, running unprotected: RuntimeError('injected-brake-inside-apply')
```
→ 未激活 import 零副作用（AC-006）✓；激活 patch 生效 ✓；注入异常 fail-open（恢复原 Popen + 单行告警 + 宿主不崩）✓。

Q4 端到端弹窗对照（事故 §7.1 最小复现, EnumWindows 100ms-pole, owner-PID 归属, TERMINAL={cmd,conhost,windowsterminal,openconsole,python}）:
```
round a1 (off): count=4  events=[t=1.06 pid=34152 openconsole, t=2.37 pid=71272, t=6.31 pid=61152, t=9.21 pid=69688]
round a2 (off): count=1  events=[t=2.85 pid=59304 openconsole]
round b1 (on) : count=0  events=[]
round b2 (on) : count=0  events=[]
child_flags: a1/a2/b1/b2 各 10 次 `cmd /c exit` 经 spy 记录 creationflags=0 （b 轮 guard 已将 spawn 转为 CREATE_NO_WINDOW）
sitecustomize_loaded.marker -> loaded pid=58364     # DETACHED 子进程内 guard 目录 sitecustomize 被加载
```
off 轮可见 openconsole 窗口 ∈ [1,4]（WT 合成/合并渲染时序导致瞬时窗口部分不可观测，低于理论 10）；on 轮严格 0。

### guard 骨架（可直接搬进 design, ≤60 行, `mw_console_guard.py`）

```python
"""mw_console_guard -- windows subtree console guard (sitecustomize-mode).

Spec L2.  Injected via PYTHONPATH prefix + MW_CONSOLE_GUARD=1 by the runner.
Design-proven skeleton (RQ-3 Q2/Q3): idempotent patch of subprocess.Popen
so that calls with no explicit console semantics get CREATE_NO_WINDOW OR-ed in.

Contract (spec $2.3 / AC-005 / AC-006 / AC-007):
  - env switch only: no activation unless MW_CONSOLE_GUARD == "1"
  - explicit CREATE_NEW_CONSOLE / DETACHED_PROCESS flags are never rewritten
  - import is a no-op when inactive; patching failure fails OPEN (restore, warn)
  - POSIX: no-op
"""

import os
import sys

_patched = False            # module-level idempotency flag (double-import / re-patch self-check)


def _apply():
    """OR CREATE_NO_WINDOW into Popen creationflags when console semantics
    were not explicitly requested. Returns True on success (or nothing to do)."""
    import subprocess

    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return True  # non-Windows or ancient stdlib: nothing to guard

    orig = subprocess.Popen.__init__
    flag = subprocess.CREATE_NO_WINDOW
    EXPLICIT = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS

    def patched(self, *args, creationflags=0, **kwargs):
        # OR CREATE_NO_WINDOW whenever the caller did not explicitly request
        # console semantics (CREATE_NEW_CONSOLE / DETACHED_PROCESS untouched).
        if (creationflags & EXPLICIT) == 0:
            creationflags = creationflags | flag
        return orig(self, *args, creationflags=creationflags, **kwargs)

    subprocess.Popen.__init__ = patched
    return True


def _activate():
    global _patched
    if _patched:
        return
    try:
        _apply()
        _patched = True
    except Exception as exc:                      # fail-open: never crash host
        sys.stderr.write(
            "mw_console_guard: patch failed, running unprotected: %r\n" % (exc,))


if os.name == "nt" and os.environ.get("MW_CONSOLE_GUARD") == "1":
    _activate()

del os, sys  # keep namespace clean (module still safely re-importable)
```

注：guard 目录内的 `sitecustomize.py` 负责 `import mw_console_guard`（sitecustomize 是 CI 链上的既有钩子，Q1 实测在 DETACHED 子进程亦加载）。

### 结论表 Q1-Q4 → design 决策映射

| # | 问题 | 判据（原文） | 实测结论 | 对 design 的直接输入 |
|---|------|--------------|----------|----------------------|
| Q1 | PYTHONPATH 前置 sitecustomize 加载链 | `python -c` + `-X utf8 -m pytest` + `-S` + venv 冲突 | ✅ 全部加载（含 pytest 链, conftest 亦确认 `sc`）；`-S` 跳过（记录）；venv 冲突: PYTHONPATH 版胜出 | runner 注入 = 子树 env `PYTHONPATH=<guarddir>;<existing>` + `MW_CONSOLE_GUARD=1`；guard 目录放 `sitecustomize.py`（import guard 模块）+ `mw_console_guard.py` |
| Q2 | 最小补丁点 = Popen.__init__ | run/Popen 均拦截；补 OR；显式 flag 不动；kwargs 透传 | ✅ 全部成立；幂等（double import/reload 不再重 patch） | patch 点钉死 `subprocess.Popen.__init__`；OR 条件用 `(creationflags & EXPLICIT) == 0`（等价于「未显式指定 console 语义」，亦兼容 CREATE_NEW_PROCESS_GROUP-only 调用） |
| Q3 | env 开关 + fail-open | 未激活零副作用 / 激活生效 / 注入异常恢复 | ✅ inactive `__init__`；active `patched`；broken 恢复 `__init__` + 单行警告 | 激活判据 `os.environ.get("MW_CONSOLE_GUARD") == "1"`；`_patched` 模块级标志保幂等；patch 异常捕获后恢复原 Popen 再告警 |
| Q4 | 事故 §7.1 弹窗对照 off/on | (a) ≈10 / (b) 0 | ✅ off ∈ [1,4]（理论 ≈10, WT 渲染合并掩盖瞬时窗口）, on 严格 0 ×2 轮 | AC-005 verify 方法预演：EnumWindows 差分 + owner-PID 归属 + 轮询可直接复用为 verify 脚本；off 断言建议放宽为「>0 且聚合 > on」 |

非空判定：Q1 无 BLOCKER（sitecustomize 在 pytest 链上稳定加载, venv 场景 PYTHONPATH 版胜出 —— 方案前提成立）。

## 残留与未验证

- conda 环境同名冲突未测（本机无 conda）。
- 可见窗口观测对 WT 渲染时序敏感（off < 10）：verify 阶段建议 off 断言「>0 且聚合 > on」、on 断言严格 0。
- 未在 conhost-only / POSIX 平台实测；POSIX 走 `hasattr(subprocess, "CREATE_NO_WINDOW")` 检查天然 no-op（AC-007 兼容）。
- 若未来环境下 PYTHONPATH 被宿主剥离（少见），备选机制：runner 额外传 `-p` 插件或 rootdir conftest 兜底（Q1 已证 conftest 与 sitecustomize 同进程可共存）；策略上 sitecustomize 仍为首选。

%TEMP% 文件清单 (`%TEMP%/mw-csg-rq3/`):
- `guard/mw_console_guard.py`（骨架成品, 58 行）、`guard/sitecustomize.py`（加载器 + 标记）、`guard/mw_console_guard_broken.py`（fail-open 注入变体）、`guard/sitecustomize_loaded.marker`
- `q1/`: sitecustomize.py、sc-loaded.marker、test_mini.py、test_chain.py、conftest.py、probe.py、sc_marker_probe.py、venv_sitecustomize.py、venv_probe.py、venv-report.txt
- `q2/q2_main.py` + `q2_results.jsonl`（拦截断言）
- `q3/q3_main.py` + `q3_results.jsonl`（三路径）
- `q4/`: repro_console_storm.py、watcher.py、_repro_child*.py、child_flags_*.jsonl、child_done_*.marker、watch_events.jsonl、_slow_child*.py
- `venvtest/v1/`：`python -m venv` 临时环境（冲突对照）

## 上下文来源

- spec.md §1.1 L2 / §2.3 / AC-005/006/007
- 事故报告 evidence/research/spec-incident-console-storm-20261015.md（§7.1 最小复现 / §7.2 观测命令）
- tasks/T-03-RQ3-guard-injection.md（卡片契约: 写入面、非空判定、交付格式）
- 记忆前馈: spec-spawn-site-survey-20261015.md（L0/L1 并行的 spawn 站点调研）

[VERIFY] RQ3-Q1: pytest_loads=yes venv_conflict=observed
[VERIFY] RQ3-Q2: run_patched=yes popen_patched=yes new_console_untouched=yes kwargs_intact=yes
[VERIFY] RQ3-Q3: inactive_noop=yes fail_open=yes
[VERIFY] RQ3-Q4: off_windows=4 on_windows=0 rounds=2
