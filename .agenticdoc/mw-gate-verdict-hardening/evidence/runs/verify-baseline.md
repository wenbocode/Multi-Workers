# EXECUTE 基线（plan §5.1，2026-10-10 记）

- key: `mw-gate-verdict-hardening` · phase **EXECUTE**（`tasks -> execute`，2026-10-10）
- 代码基线：HEAD **`776b82d7f`**（`chore: ignore the local .tmp scratch dir`）；开工前工作树对我方写面**干净**
  - `git status --porcelain` 共 16 条，全部为 `??`（本 key 文档目录、`.tmp/`、他 key 新目录）；`M` = 0
  - 7 个写面文件逐个复核：`mw.py` / `mw_common.py` / `effective_config.py` / `worker-store.ts` / `pm-orchestrator.ts` / `launcher.py` / `worker-mode.ts` 全部 clean
  - 自 `10446aefb` 以来的改动只在 `conductor.py`(+9/−1)、`effective_config.py`、`mw.py`（他 key 已提交）⇒ **本 key 的 worker-store / pm-orchestrator / launcher 锚点未漂移**；`conductor.py` 锚点（T-01/T-07/T-10）需在开工时重锚

## 1. TS 基线（`packages/coding-agent`）

```
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts
→ Test Files 1 passed (1) / Tests 6 passed (6) / 178ms
```

## 2. Python 基线（`packages/multi-workers`）

```
python -X utf8 -m pytest -q <34 × test_autopilot_*.py> test_doctor_gates.py
→ 2 failed, 655 passed, 8 deselected, 64 warnings in 76.45s
```

**既有红（本 key 不修、不得当成回归）**：

| 测试 | 断言 | 性质 |
|---|---|---|
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | `assert frozen == git_blob` → `219ed809…` vs `6be60fe5…` | **冻结锚点漂移**（该文件内容 sha 与冻结常量不一致）——与 dispatch/queue 无关 |
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | `assert last_round in report_matches` → `3 in [2]`（"latest report is not from the last round"） | 依赖仓库真实 `.agenticdoc` 语料的 fixture；语料已变 ⇒ 既有红 |

⇒ 后续每波只与该基线比对；上表两条红不算本 key 引入。

## 3. 与 AC-014 的关系

本文件即 AC-014「`[VERIFY]` 数值来自实测」的基线锚：EXECUTE 期每条卡的回执必须给出**可复算**的命令与原始输出，并与本基线对照（红集合不扩大）。
