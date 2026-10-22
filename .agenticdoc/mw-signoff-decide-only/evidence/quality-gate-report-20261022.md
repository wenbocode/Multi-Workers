# 质量门报告 — mw-signoff-decide-only

- date: 2026-10-22
- phase: VERIFY
- 结论：**PASS**（目标套件全绿；仓库级 `npm run check` 仅被他人未提交的 3 个 `mwoc-*` 文件拦下，与本次改动无关）

## 1. 验收标准逐条

| AC | 结果 | 证据 |
| --- | --- | --- |
| AC-001 无决策行 → 门禁通过、不要求文件 | PASS | 临时项目 `_decision_signoff_problems()` → `[]`；无 `sign-final.md` |
| AC-002 有决策行 + 缺文件 → 失败且可定位 | PASS | → `['MISSING: evidence/review/sign-final.md …（该 key 的档案里有 kind=decide 行，必须有）']` |
| AC-002b 有 `decision-scope.md` 但无决策行 → 通过 | PASS | 同上夹具加 marker 文件 → `[]`；`_key_has_decide_rows()` = False |
| AC-003 `--dry-run --json` 零写入 + `verdicts` | PASS | 真实仓库实跑：`exit 0`，键 `['conclusion','facts','ok','path','problems','verdicts']`，`verdicts={'continue':False,'narrow':True,'revoke':True}`，`path=None`，`_autopilot/decisions.jsonl` 46 → 46 行，`sign-final.md` 未创建 |
| AC-004 jev 可用 → 结论来自 dp25、`signed_via: auto-decide` | PASS | 实跑 `mw decide sign --key mw-signoff-decide-only`：`conclusion: narrow`、`counted_rows: 0`、`signed_via: auto-decide`，档案追加 `authority-change by=signoff:narrow`；stdout 含 `confidence=1.0 source=api` |
| AC-005 jev 不可用 → exit 0、不写文件 | PASS | 单测（fake backend 不可用）断言 exit 0 + 无文件 + `sign-off not required`；实现路径 `mw.py` `conclusion is None` 分支 |
| AC-006 删参数、词表单值 | PASS | `mw decide sign --conclusion continue` → `exit 2 unrecognized arguments`；`--human-confirmed` 同；`SIGNED_VIA_VALUES == ('auto-decide',)` |
| AC-007 窗口 headless 可用、无确认框、argv 无 `--human-confirmed` | PASS | `decide-command.test.ts` 34/34；`headless-sign calls=2 notifies=0`；写面 argv `["sign","--key","k","--json"]`，preview `["sign","--key","k","--dry-run","--json"]` |
| AC-008 `write_signoff` 无 agent-session 拒绝 | PASS | `test_write_signoff_works_inside_an_agent_session`；实跑在 `PI_CODING_AGENT=1` 下写入成功 |
| AC-009 文档去人化 | PASS | `rg "decision-scope.md 时" docs/` 无输出；`--human-confirmed` 仅剩「已删除」说明 |
| AC-010 受影响套件全绿 | PASS（见 §2） | 176 + 34 + 28 全绿 |

## 2. 命令与输出

```text
# Python（目标四文件）
$ python -m pytest test_decide_signoff.py test_decide_sign_auto.py test_decide_cli.py test_decision_history.py -q
176 passed in 14.99s

# 框架门禁（canonical）
$ python -m unittest test_advance_phase    # .agents/skills/agentic-task/scripts
Ran 28 tests
OK

# TS（三个文件）
$ node ../../node_modules/vitest/dist/cli.js --run test/suite/decide-command.test.ts \
    test/suite/decision-signoff.test.ts test/suite/decision-dashboard-command.test.ts
Test Files  3 passed (3)
     Tests  34 passed (34)

# 本次改动文件的 lint / 类型
$ npx biome check <ui-bridge.ts mw-runner.ts 三个测试文件>
Checked 5 files in 66ms. No fixes applied.
$ npx tsgo --noEmit
exit=0
```

仓库级：

```text
$ python -m pytest -q        # packages/multi-workers
10 failed, 4049 passed, 1 skipped, 10 deselected in 659.57s

# 失败全在本次写面之外：
#  test_autopilot_readcap_injection (2) / test_autopilot_verdict_freshness (1)  ← 他人未提交的 readcap 改动
#  test_dispatch_decide_prepare (1)   ← autopilot/dispatch.py 由其它窗口改动中（git status 显示 M）
#  test_launcher / test_task_type_parity / test_mwds_t10 / t27 / t29 / test_mwgal_t13 (6) ← 环境/一致性基线

$ npm run check
Found 3 warnings.  Found 2 infos.       # 全部位于 test/suite/mwoc-{matrix-t07,w2-contract-judgment,w3-ledger-extractor}.test.ts
                                        # （他人未提交的 mwoc 工作；tsgo 阶段未被触发）
```

## 3. 门禁行为矩阵（临时项目，实跑 `_decision_signoff_problems`）

| 场景 | 结果 |
| --- | --- |
| 无档案、无文件 | `[]` |
| 有 `decision-scope.md`、无档案 | `[]` |
| 有 decide 行、无文件 | `MISSING …` |
| 只有**别人 key** 的 decide 行 | `[]` |
| 只有 dp25 行（raw 判据） | `MISSING …`（符合设计取舍） |
| 坏 JSON / 仅 `authority-change` / 坏 UTF-8 | 跳过 / 跳过 / fail-loud（由 T-02 的 13 项矩阵覆盖） |
| 真实仓库 4 个 key | `mw-signoff-decide-only`、`mw-decision-substitution`、`mw-usage-monitor`、`claim-driven-review` 均 `[]` |

## 4. 本次顺带修复

| 文件 | 修复 |
| --- | --- |
| `packages/multi-workers/decision_history.py:2147` | 读面改用自身四值词表校验，历史 `cli`/`tui` 签收不再触发 `unknown signed_via` 告警 |
| `packages/multi-workers/decide_signoff.py`（docstring + 签收文件表头） | 删除「仅当 key 目录存在 `decision-scope.md` 时生效」的过期描述 |
| `.agents/skills/agentic-task/scripts/advance_phase.py:750` | `mw decide report` 子进程固定 `encoding="utf-8", errors="replace"` + `(result.stdout or "")` 保护：中文输出在 cp936 环境下曾让 `maybe_write_decision_review` 抛 `UnicodeDecodeError` 并跳过 `decision-review-*.md` |

## 5. 残留风险 / 未覆盖

1. `trigger.key` 默认空串（`decision_points.py:229`）→ 无 key 的 decide 行对所有 key 不可见（今天 0 实例）。
2. 真实 jev 的 `--dry-run` 只证明"不调用"，未验证"调用后结论与 dry-run verdict 一致"（同一判据函数，风险低）。
3. 窗口的 `--json` 载荷消费用 `path != null` 判定已签收（T-01 同时提供 `signed_via` 字段，双保险未加断言）。
4. 仓库级 `npm run check`/全量 pytest 的红点来自并行窗口的未提交改动，未在本 key 内修。
