# T-03 RQ-3: sitecustomize console-guard 注入机制实证

- key: mw-console-storm-hardening · 第 1 批 · type: research
- type: research
- 唯一证据文件: `.agenticdoc/mw-console-storm-hardening/evidence/research/design-guard-injection-mechanics-20261015.md`（其余仅 `%TEMP%` 下自建实验目录）
- 写入允许面: `.agenticdoc/mw-console-storm-hardening/evidence/research/design-guard-injection-mechanics-20261015.md` + `%TEMP%/mw-csg-rq3/` 实验目录；写入禁止面: 仓库其余一切（源码/测试/配置/注册表）
- 上下文: goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」+ spec §2.3（仅 env 激活、不改写显式 flag）
- 锚点: `packages/multi-workers/mw_common.py:1572`（`_probe_spawn_kwargs` 既有 win32 console 隔离先例与 platform seam）、`packages/multi-workers/launcher.py:2007`（worker spawn CREATE_NO_WINDOW 先例）、事故报告 §7.1（最小复现脚本）

## 写入允许面

- `.agenticdoc/mw-console-storm-hardening/evidence/research/design-guard-injection-mechanics-20261015.md`
- `%TEMP%/mw-csg-rq3/`（自建实验目录，仓库外）

## 写入禁止面

- 仓库其余一切（源码/测试/配置/注册表）
- ac_refs: AC-005, AC-006, AC-007 · deps: 无（与 T-01/T-02 并行）
- 预计: 30-45min

## 目标

为 L2 guard（spec §1.1，用户已定 sitecustomize + PYTHONPATH 方案）实证注入机制的四个设计输入。约束锚点：spec §2.3（仅 env 激活、不改写显式 flag）、AC-005/006/007。

## 四个必须回答的问题

1. **Q1（加载时机）**：PYTHONPATH 前置一个含 `sitecustomize.py` 的目录，CPython 启动（含 `python -X utf8 -m pytest`）是否加载它？`python -S` 会跳过（记录即可）；pytest 自身是否以任何方式绕过 sitecustomize？virtualenv/conda 环境下 PYTHONPATH 的 sitecustomize 与环境自带的 sitecustomize 谁胜出（同名冲突行为）？
2. **Q2（最小补丁点）**：patch `subprocess.Popen.__init__`（`run()` 内部走 Popen → 一处覆盖两入口）是否成立？实测：patch 后 `subprocess.run([...])` 与 `subprocess.Popen([...])` 均被拦截；`creationflags=0` 被补 OR `CREATE_NO_WINDOW`；`creationflags=CREATE_NEW_CONSOLE` 原样保留；`**kwargs` 未传 creationflags 时补上后不影响 `stdout/stderr/env/cwd` 透传。
3. **Q3（激活开关）**：guard 模块 import 时检查 `os.environ.get("MW_CONSOLE_GUARD") == "1"` 决定是否激活——未激活时 import 零副作用（AC-006）；激活但 patch 过程抛异常时 fail-open（捕获后恢复原 Popen，打印 stderr 一行告警，不崩宿主）。实测三条路径。
4. **Q4（端到端弹窗对照）**：在 `%TEMP%` 实验目录搭事故 §7.1 最小复现（DETACHED 父 → 子进程循环 10 个 `cmd /c exit`，flags=0）：(a) 不激活 guard → 弹窗数 ≈10；(b) runner 语义注入（PYTHONPATH 前置 + `MW_CONSOLE_GUARD=1`）→ 弹窗数 = 0。窗口观测用 ctypes EnumWindows（250ms 轮询，owner PID 归属终端进程），方法同事故 §7.2。

## 硬契约

- 实验脚本全部在 `%TEMP%/mw-csg-rq3/`（自建）；仓库内唯一写面 = 上述 evidence 文件；只用 stdlib；不改注册表；实验完 evidence 里列 `%TEMP%` 清单。
- guard 草图必须是**可直接搬进 design 的成品骨架**（≤60 行）：模块结构 + patch 函数 + 激活判据 + fail-open，含幂等性（重复 import / 双重 patch 自检，如 module-level `_patched` 标志）。
- 临时脚本用 write 工具或 Python 写盘（UTF-8 显式编码），禁 PowerShell 管线（P-001）。
- 本机默认终端即 WT，实验结果即为 AC-005 verify 的方法预演。

## 步骤

1. Q1：三个变体各跑一遍——`python -c "import sys; print('sc' if ...)"` 探针脚本（sitecustomize 里写标记文件证明被加载）；`-X utf8 -m pytest` 一个 1 用例迷你套件验证加载链；如有 venv 在 PATH 上，用 `python -m venv` 临时环境测同名冲突（无 venv 则跳过并如实记录）。
2. Q2：写 guard 草图 → 在探针进程里分别调 `run`/`Popen`/`CREATE_NEW_CONSOLE`/带 `cwd,env,stdout` 的调用，把实际收到的 creationflags 打到 stdout 断言。
3. Q3：三路径实测（未激活零改写 / 激活生效 / 注入异常 fail-open：临时把 `kernel32` 替换抛错或 monkeypatch 一个必炸点验证恢复）。
4. Q4：搭复现并跑 (a)/(b) 对照，各 2 轮。
5. 输出结论表 Q1-Q4 → design 决策映射（runner 注入的 env 精确写法、guard 模块名、放置目录）。

## 验收命令

```bash
grep -c "VERIFY" .agenticdoc/mw-console-storm-hardening/evidence/research/design-guard-injection-mechanics-20261015.md
```

## 证据格式（写进 evidence 文件末尾）

```
[VERIFY] RQ3-Q1: pytest_loads=yes|no venv_conflict=<observed|skipped>
[VERIFY] RQ3-Q2: run_patched=yes popen_patched=yes new_console_untouched=yes kwargs_intact=yes
[VERIFY] RQ3-Q3: inactive_noop=yes fail_open=yes|no
[VERIFY] RQ3-Q4: off_windows=<n> on_windows=0 rounds=2
```

## 非空判定

Q1 若 pytest 链上 sitecustomize 未被加载（或被 venv 覆盖）→ 立即上报为 **BLOCKER 级发现**（动摇方案前提），evidence 里给出备选机制（如 `usercustomize` / `sitecustomize` 之外的 `.pth` 钩子 / conftest 兜底）与实测依据，不得含糊。

## 交付

唯一 evidence 文件（探针原始输出 tail + 对照轮窗口计数 + guard 骨架代码块 + 结论表 + [VERIFY] 行）。
