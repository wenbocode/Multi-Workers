# T-09b 守卫接线 + 框架镜像同步 + 过期断言修正

- key: mw-decision-substitution · type: coding
- 依据：T-09 阻塞项 1/2/3（PM 已核实三条均为写面/路径错误，不是设计分歧）

## 上下文

T-09 已交付四块实现并各自绿，但有三处**没有真正生效**：

1. **写守卫模块放错位置且未注册**：T-09 在 `agent-team-loop/xkey-gate-guard.ts` 新建了 9.5KB 模块，而真实守卫模块是 `agent-team-loop/shared/xkey-gate-guard.ts`（13.1KB，已存在）。新文件既不在正确位置、也没有任何 `index.ts` import → **零调用**。实测：
   ```
   .agents/skills/agentic-task/install.py::sync_script_mirrors
     src = ROOT/"scripts"      ← canonical
     mirrors = core/scripts, claude/scripts
   ```
2. **`advance_phase.py` 改到了镜像不是 canonical**：T-09 改的是 `.agents/skills/agentic-task/core/scripts/advance_phase.py`（含 `sign-final` 门禁），canonical `.agents/skills/agentic-task/scripts/advance_phase.py` **不含** `sign-final`。下一次 `sync_script_mirrors()` 会把镜像覆盖回去 → 门禁静默消失。
3. **3 条旧断言被本卡语义取代**，仍在树里红着（T-09 自报）。

## 要求

1. **守卫归位**：把 `agent-team-loop/xkey-gate-guard.ts` 的决策签收守卫逻辑并入 `agent-team-loop/shared/xkey-gate-guard.ts`（复用其既有的路径匹配/trace/bash 判定机制，命名不与既有 `registerXkeyGateGuard` 冲突），**删除** `agent-team-loop/xkey-gate-guard.ts`，并在 `agent-team-loop/index.ts` 注册（`registerXkeyGateGuard(pi)` 之后同级调用）。`decision-signoff.test.ts` 的 import 改到新路径。
2. **canonical 先行**：把 T-09 在 `core/scripts/advance_phase.py` 的改动（`GATES["done"]` 两条 `sign-final.md` 规则 + `find_mw_cli`/`maybe_write_decision_review` + 推进后调用）**原样移植到 `scripts/advance_phase.py`**，再运行 `sync_script_mirrors()` 让 `core/scripts/` 与 `claude/scripts/` 逐字节一致（然后 `install.py` 若支持再同步 `.claude/scripts/`）。验收：三个副本 sha256 相同。
3. **过期断言**：
   - `packages/multi-workers/test_decide_dp_cli.py::test_dp_apply_accepts_a_valid_signoff_skeleton_without_writing`：改为验证新的写回语义（`conclusion: continue` 真写表 + 落 `authority-change` 行），不再断言"不写盘"。
   - `.agents/skills/agentic-task/scripts/test_advance_phase.py` 的 `MemoryExtTest::test_vc030_done_gate_requires_achieved` 与 `DoneSummaryContractTest::test_summary_written_to_project_log`：fixture 补 `evidence/review/sign-final.md`（内容含 `conclusion: continue`）。改 canonical 后同步镜像测试文件。
4. 不改动任何 dp 语义、阈值、报告口径。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/xkey-gate-guard.ts`（删除）
- `packages/coding-agent/test/suite/decision-signoff.test.ts`
- `packages/multi-workers/test_decide_dp_cli.py`
- `.agents/skills/agentic-task/scripts/advance_phase.py`
- `.agents/skills/agentic-task/scripts/test_advance_phase.py`
- `.agents/skills/agentic-task/core/scripts/advance_phase.py`
- `.agents/skills/agentic-task/core/scripts/test_advance_phase.py`
- `.agents/skills/agentic-task/claude/scripts/advance_phase.py`
- `.agents/skills/agentic-task/claude/scripts/test_advance_phase.py`
- `.claude/scripts/advance_phase.py`
- `.claude/scripts/test_advance_phase.py`

## 写入禁止面

- 其它任何文件；禁止 `git add/commit/checkout/stash/clean`；禁止 `npm run build`、`npm run check`
- 禁止改 `pm-orchestrator.ts` / `worker-mode.ts`（其它卡已交付并锁死）

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run \
  test/suite/decision-signoff.test.ts test/suite/xkey-gate-guard-coverage.test.ts
cd packages/multi-workers && python -m pytest test_decide_report.py test_decide_dp_cli.py -q
python -m pytest .agents/skills/agentic-task/scripts/test_advance_phase.py -q
python -c "import hashlib,pathlib;print([hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()[:12] for p in ['.agents/skills/agentic-task/scripts/advance_phase.py','.agents/skills/agentic-task/core/scripts/advance_phase.py','.agents/skills/agentic-task/claude/scripts/advance_phase.py']])"
```

期望：全绿；三个 sha 前缀完全相同；`grep sign-final` 在 canonical 命中的行数 ≥ 2。

## 种子

- goal 锚点：`.agenticdoc/goal.md`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:85`（既有路径匹配机制）
- `packages/coding-agent/src/extensions/agent-team-loop/xkey-gate-guard.ts:1`（T-09 放错位置的模块，本卡并入后删除）
- `.agents/skills/agentic-task/install.py:sync_script_mirrors`（canonical=scripts/，镜像=core/、claude/）

## 交付格式

- 四段：结论 / 证据（含三副本 sha、grep 计数、三套测试尾行）/ 残留与未验证 / 改动清单。
- 必须给出"注册后守卫真的拦写"的证据（`tool_call` 分发用例 + trace 行），不接受只跑纯函数匹配器。
- 契约冲突停手写残留。

## 改动历史

- 2026-10-20 创建（T-09 阻塞项三项）
