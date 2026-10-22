# W-02 — guard 包：mw_console_guard/（sitecustomize + 补丁模块）

- key: mw-console-storm-hardening · type: coding · 波次 1
- ac_refs: AC-005, AC-006, AC-007 · vc_refs: VC-005, VC-006, VC-007(guard 侧)

## 上下文

goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」；spec §2.3（仅 env 激活、不改写显式 flag、零全局副作用）。机制依据 M4/M5/M6（design.md §1，evidence/research/design-guard-injection-mechanics-20261015.md）：sitecustomize 经 PYTHONPATH 在 python/pytest 链加载、patch Popen.__init__ 一处覆盖双入口、env 开关 + fail-open。锚点: `packages/multi-workers/mw_common.py:1572`（`_probe_spawn_kwargs` 既有 win32 console 隔离先例 + platform seam 测试模式）、`packages/multi-workers/launcher.py:2007`（CREATE_NO_WINDOW 先例）。

## 要求（契约 = design.md D-003，RQ-3 骨架为实现基线）

1. 新目录 `packages/multi-workers/mw_console_guard/`，两文件：
   - `sitecustomize.py`：≤3 行激活器（`import mw_console_guard`），带模块 docstring 说明注入方式（PYTHONPATH 前置本目录 + MW_CONSOLE_GUARD=1）。
   - `mw_console_guard.py`：以 `%TEMP%/mw-csg-rq3/guard/mw_console_guard.py` 的 58 行骨架（evidence 文件"骨架代码块"节有全文）为基线逐行落地，保留：`_patched` 模块级幂等标志、`os.name=="nt" and os.environ.get("MW_CONSOLE_GUARD")=="1"` 激活判据、`_apply()` OR `CREATE_NO_WINDOW`（显式 `CREATE_NEW_CONSOLE|DETACHED_PROCESS` 不动）、fail-open（异常 → 恢复原 Popen + 单行 stderr 告警）。
2. 硬化：patched 函数 docstring 明示"creationflags 位置传参不受保护"（design D-003 决策：不做签名镜像，理由 = 全仓无该调用形态）；`del os, sys` 命名空间清理保留。
3. 只 stdlib；文件写入一律 UTF-8 显式编码（P-001）。

## 写入允许面

- `packages/multi-workers/mw_console_guard/sitecustomize.py`（新建）
- `packages/multi-workers/mw_console_guard/mw_console_guard.py`（新建）

## 写入禁止面

- 其余一切（含 test_mw_console_guard.py——W-04 领地、console_run.py、mw.py、TS 侧）；禁止 git add/commit

## 验收命令

```bash
cd packages/multi-workers
python -c "import os,pathlib; d=pathlib.Path('mw_console_guard'); sys=p'dummy'" 2>$null
$env:PYTHONPATH="$PWD\mw_console_guard"; $env:MW_CONSOLE_GUARD="1"
python -c "import subprocess,inspect; orig=subprocess.Popen.__init; import sitecustomize; print('patched=', subprocess.Popen.__init is not orig)"
Remove-Item Env:MW_CONSOLE_GUARD
python -c "import subprocess,inspect; orig=subprocess.Popen.__init; import sitecustomize; print('noop=', subprocess.Popen.__init is orig)"
```

期望：第一处 `patched= True`，第二处 `noop= True`。

## 改动历史

- 2026-10-15 W-02 首派（波次 1）。

## 交付格式

- 两文件全文 + 验收命令原始输出（patched=True / noop=True 两行必须在场）+ 与骨架的逐行差异说明（如有）。
