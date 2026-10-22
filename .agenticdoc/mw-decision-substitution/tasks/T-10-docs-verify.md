# T-10 文档 + CHANGELOG + 全量验证

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（全部（验收证据））+ design.md — + plan.md §1

## 上下文

- 文档基线：`packages/multi-workers/README.md`（决策服务小节）、`docs/jev-integration-flow-and-usage.md`（底座正式文档）。
- CHANGELOG 规则见 AGENTS.md（只写 `## [Unreleased]`，用 `### Added/Changed/Fixed`）。
- 度量基线：人工轮次/墙钟 93.3 min、中位 13.6 min（`spec-decision-metrics-20261016.md`）。

## 要求

1. 新建 `docs/decision-substitution.md`：dp 一览（24 项 + 档位 + 默认）、配置表用法（指令/手改/热生效）、`mode` 语义、决策档案字段与读法、报告与签收流程、失败与回退路径。
2. `packages/multi-workers/README.md` 增补「决策替换」小节并指向新文档；`packages/*/CHANGELOG.md` 写 `## [Unreleased] ### Added`（不写版本号章节）。
3. 跑全量：`./test.sh` + `npm run check`，把结果写入 `evidence/runs/verify-mw-decision-substitution-<date>.md`（含命令、输出摘要、失败数与基线对比）。
4. 用 pi 会话 JSONL 复核度量基线（人工轮次/墙钟），把方法与数字写进同一证据文件。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/multi-workers/README.md:1`
- 代码锚点: `.agenticdoc/goal.md:1`

## 写入允许面

- `docs/decision-substitution.md`（新建）
- `packages/multi-workers/README.md`
- `packages/multi-workers/CHANGELOG.md`
- `packages/coding-agent/CHANGELOG.md`
- `.agenticdoc/mw-decision-substitution/evidence/runs/verify-mw-decision-substitution-20261020.md`（新建）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令（PM 已实测调整：本机没有可用的 WSL，`./test.sh` 不可执行）

```bash
# 1) Python 全量
cd packages/multi-workers && python -m pytest -q
# 2) TS 全量（test/ 与 test/suite/，不含 e2e）
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite test/extensions/agent-team-loop.test.ts
# 3) 静态检查（**不要**跑 `npm run check`：它带 biome --write，会改写其它会话的在途文件）
npx tsgo --noEmit
npx biome check <本卡改动的文件…>
```

## 已实测基线（PM 2026-10-20 跑出，直接引用，不要重跑到超时）

**Python**（`packages/multi-workers`，`python -m pytest -q`）：

```
8 failed, 2729 passed, 10 deselected, 2 warnings in 496.72s
```

这 8 条是既有 Windows 环境基线（与 AGENTS.md 记录的基线同类），**不是本 key 引入**：
`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、
`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`、
`test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites`、
`test_mwds_t10_dispatch_run_state.py::test_missing_run_json_dispatches_byte_identically`、
`test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge`、
`test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge`、
`test_mwgal_t13_drift_identity.py::test_process_start_ms_probe`、
`test_task_type_parity.py::test_bom_historical_books`。
对比旧基线（8 failed / 2488 passed）：**失败数不变，通过数 +241**（本 key 新增用例）。

**TS**（`test/suite` + `test/extensions/agent-team-loop.test.ts`）：

```
Test Files  9 failed | 147 passed | 1 skipped (157)
     Tests  18 failed | 1838 passed | 3 skipped (1859)
```

18 条按类归因（写进证据文件时必须逐条归类，不得只说"环境噪声"）：
- Windows shell/path 类（bash↔powershell、find glob、fs.watch、no-builtin-tools、exclude-tools）：`5109-exclude-tools` ×2、`3302-find-path-glob` ×3、`2791-fswatch-error-crash`、`3592-no-builtin-tools`、`agent-session-runtime` ×7
- 其它会话在途改动：`rag-tools`（另一会话在 `worker-mode.ts` 加 `mw_run_detached`）、`mwds-t02-write-intent`（其它 key 卡片语料 false positive）
- 未重建 bundle：`mwds-t23-cutover-recheck`（bundle sha 期望，需 `mw build --install`，属用户放行后步骤）
- 既有锚点漂移：`agent-team-loop.test.ts > T-17/B-1 anchor integrity`

本 key 新增/改动套件全部绿（PM 已逐个复跑）：`decision-association` 35、`dp2-narrow` 30、`dp3-answer` 13、`triage-client-state` 31、`triage-dispatch` 21、`decision-tool` 17、`decision-signoff` + `xkey-gate-guard-coverage` 19。

## 改动历史

- 2026-10-20 创建
