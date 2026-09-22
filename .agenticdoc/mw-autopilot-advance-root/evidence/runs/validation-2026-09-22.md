# Validation runs: mw-autopilot-advance-root (T6)

> 日期：2026-09-22
> 关联：AC-001..008

## 1. 目标行为（修复前后对照，实跑）

### 1.1 framework root 定位（AC-001 / AC-002）

cwd = `H:\git\E2Feature`（framework 装在 mw 仓库外）：

修复前：

```
detect_root.py --json -> {"PLATFORM_DIR": "...Multi-Workers\\.agents\\skills\\agentic-task",
                          "PROJECT_ROOT": "...Multi-Workers", "method": "agenticdoc:platform_dir"}
find_root()           -> H:\git\Multi-Workers\.agenticdoc
```

修复后（d7004d0）：

```
$ python <framework>/scripts/detect_root.py --json   (cwd=E2Feature)
{"PLATFORM_DIR": "...Multi-Workers\\.agents\\skills\\agentic-task",
 "PROJECT_ROOT": "H:\\git\\E2Feature",
 "AGENTICDOC_ROOT": "H:\\git\\E2Feature\\.agenticdoc",
 "method": "agenticdoc:cwd"}

$ find_root()  ->  H:\git\E2Feature\.agenticdoc
```

### 1.2 mw conductor 路径（AC-003）

```
$ python -c "from autopilot import advance as adv; adv.locate_platform_dir('H:/git/E2Feature')"
platform_dir  = H:\git\Multi-Workers\.agents\skills\agentic-task
advance_script= H:\git\Multi-Workers\.agents\skills\agentic-task\scripts\advance_phase.py
```

一致（marker clone 最新 d7004d0 被采纳）；若候选不一致则 fail-loud（见 §3 单测）。

### 1.3 端到端（AC-005）

`packages/multi-workers/test_autopilot_advance_e2e.py`：临时项目 + marker 指向项目外
framework，调 `advance(key, "design", project)`：

- exit 0，`project/.agenticdoc/<key>/pm-state.md` 出现 `- Phase: DESIGN`
- framework 仓库 `H:\git\Multi-Workers\.agenticdoc\<key>` 未创建（修复前正是这里被 mkdir）

## 2. 测试汇总

| 套件 | 命令（包根） | 结果 |
|------|------------|------|
| mw Python 全量（非 e2e_real） | `python -m pytest -q` | **726 passed, 9 deselected** |
| mw autopilot config + e2e | `python -m pytest test_autopilot_config.py test_autopilot_advance_e2e.py -q` | **30 passed** |
| mw conductor | `python -m pytest test_autopilot_conductor.py -q` | **28 passed** |
| framework scripts | `python -X utf8 test_detect_root.py` | **8 tests OK**（含 3 个新 cwd 优先用例） |
| framework scripts | `test_advance_phase.py` / `test_update_index.py` / `test_migrate_patterns.py` / `test_audit_phase.py` | 各 exit 0 |
| framework scripts | `test_install.py` / `test_sync_framework.py` | exit 0 |
| pi 扩展 | `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts` | **168 passed** |
| 仓库静态检查 | `npm run check` | **exit 0**（0 error / 0 warning / 0 info；输出见 `check-output.txt`） |

## 3. 新增回归用例

- `test_detect_root.py::PreferCwdProjectTests`（3）：cwd 项目胜出 / 一致时保留原 method / 无 cwd 命中时不变。
- `test_advance_phase.py::FindRootCwdFirstTest`（1）：cwd 优先于脚本位置。
- `test_autopilot_config.py`（3）：不一致 marker 候选被跳过并回退到一致候选；全不一致 fail-loud 且消息可读；detect_root + advance 两个子进程 argv 均含 `-X utf8`。
- `test_autopilot_advance_e2e.py`（1）：真实 framework + 项目外安装的端到端。

## 4. 发布/同步（AC-007）

```
framework clone: H:\git\Multi-Workers\.agents\skills\agentic-task  HEAD d7004d0 (pushed origin/master)
E2Feature marker commit=d7004d0；.agents clone HEAD d7004d0；.claude/scripts 同步
三副本 advance_phase.py sha256 = 9427ABE2ECC0366B31A861241E38644A2F0E828E376488336B6DBD0D511BC63F
mw 本仓 .claude/scripts 同步；H:\git\Multi-Workers\.agentic-framework commit=d7004d0
```

副作用清理：删除修复前误建的 `H:\git\Multi-Workers\.agenticdoc\feature-params-service\`、
`feature-viewer-mvp\`（两目录均为空）。

## 5. 真实 conductor 现场验证（E2Feature，非 hermetic）

E2Feature autopilot timeline（`2026-09-22` UTC）：

```
08:31:32  advance feature-params-service design->plan exit=1   <- 修复前每个 tick
08:31:49  advance feature-params-service design->plan exit=1
08:31:53  advance feature-params-service design->plan exit=0   <- 首次成功（framework clone 的 find_root 已改）
08:31:57  dispatch ...plan-writer-a1 type=phase-writer
08:36:34  dispatch ...tasks-writer-a1 type=phase-writer        <- plan->tasks 也已推进
```

`_index.parallel`: feature-params-service DESIGN -> TASKS。conductor 仍在同一 mw 服务
（PID 112400，未重启）下运行 —— 证明 framework 侧修复（F2）单独即可解除阻塞；
mw 侧改动（一致性守卫 + `-X utf8`）需要 `/mw restart` 才对运行中的服务生效。

