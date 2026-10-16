# Quality Gate Report: mw-model-error-perception (T-07 closure)

- 日期：2026-10-15
- 任务：`.agenticdoc/mw-model-error-perception/workers/t07-closure/task.md`（card `tasks/T-07-closure.md`，sha256 `98c437ec…`）
- 依赖交付：T-01/T-01b（worker 侧）、T-02/T-03/T-03b（Python 侧）、T-04（PM 告警）、T-05（TS 测试，13/13）、T-06（Python 测试，70/70）
- 平台：Windows（Git Bash 5.2.37 / MSYS、Node v24、Python 3.14.3、locale cp936）

## 1. 门禁命令与结果

| 命令 | 结果 | 摘要 |
|------|------|------|
| `npm run check` | 退出 1（`biome` 阶段） | `biome check --write --error-on-warnings .`：`Found 3 warnings / Found 2 infos / Skipped 5 suggested fixes / No fixes applied`，全部落在 `test/suite/mwoc-*.test.ts`（基线 ①）。后续子步骤单独执行全绿 |
| `npm run check:pinned-deps` | 退出 0 | 无输出 |
| `npm run check:ts-imports` | 退出 0 | 无输出 |
| `npm run check:shrinkwrap` | 退出 0 | `npm-shrinkwrap.json is up to date.` |
| `npm run check:install-lock:coding-agent` | 退出 0 | `install-lock is up to date.` |
| `npx tsgo --noEmit` | 退出 0 | 0 输出（全仓类型干净，含本 key 改动） |
| `npm run check:browser-smoke` | 退出 0 | 无输出 |
| `./test.sh`（Git Bash，隔离 HOME/TMP/env） | 退出 1 | 见 §2；documented 基线包内无新增失败 |
| `python -m pytest packages/multi-workers -q --deselect "…test_bom_historical_books_read_through_both_callsites"` | 退出 1 | `7 failed / 2325 passed / 10 deselected / 2 warnings / 470.26s`，逐条见 §3 |
| `node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-model-error-perception.test.ts` | 退出 0 | `Test Files 1 passed (1) / Tests 13 passed (13)` |
| `… --run test/suite/worker-model-error-perception.test.ts test/suite/worker-idle-heartbeat.test.ts test/extensions/agent-team-loop-checkpoint-wiring.test.ts` | 退出 0 | `3 passed (3) / Tests 28 passed (28)` |

### 1.1 `npm run check` biome 基线告警（逐条，全部 `test/suite/mwoc-*`，写面外）

| 文件:行 | 规则 | 级别 |
|---------|------|------|
| `packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts:120:6` | `lint/style/useTemplate` | warning |
| `packages/coding-agent/test/suite/mwoc-w2-contract-judgment.test.ts:130:6` | `lint/style/useTemplate` | warning |
| `packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts:45:2` | `lint/correctness/noUnusedImports` | info |
| `packages/coding-agent/test/suite/mwoc-matrix-t07.test.ts:606:4` | `lint/complexity/useOptionalChain` | info |
| `packages/coding-agent/test/suite/mwoc-w3-ledger-extractor.test.ts:216:3` | `lint/complexity/useOptionalChain` | info |

全部为 biome `--unsafe` 范畴（安全修复不动），文件位于 `test/**` 禁改面，属任务卡基线 ①（HEAD/他窗），豁免。本 key 写面文件（`packages/coding-agent/CHANGELOG.md`、`packages/multi-workers/README.md`、`evidence/quality-gate-report-*.md`）不在告警面内。

## 2. `./test.sh` 结果与 Windows 基线对照

运行方式：`D:\Program Files\Git\bin\bash.exe -lc "./test.sh"`（脚本自带 `env -i` 隔离 + 临时 HOME，未激活 e2e）。原始日志：`workers/t07-closure/testsh-20261015.log`。

| 包 | 结果 | 失败根因（全部环境/他 key） |
|----|------|------------------------------|
| `@earendil-works/pi-agent-core` | 2 failed / 217 passed | MSYS `/tmp` 与 Windows `C:\…\Temp` 路径拼写不一致（`nodejs-env.test.ts`、`tools.test.ts`） |
| `@earendil-works/pi-ai` | 1 failed / 837 passed | `timi-models.test.ts` 期望表落后于 `MODELS.timi` 目录（他 key `mw-timi-models-add` 增模型未同步期望） |
| `@earendil-works/pi-client` | 6 files passed | - |
| `@earendil-works/pi-coding-agent` | **76 failed / 3561 passed** / 6 skipped | 与 AGENTS.md 文档基线 76 逐字相符；唯一 agent-team-loop 相关失败 = T-17/B-1 anchor integrity（基线 ②，详见 §2.2） |
| `@earendil-works/pi-evals` | 1 failed / 22 passed | Windows 反斜杠路径分隔符（`sessions\…` vs `sessions/…`） |
| `@earendil-works/pi-protocol` | 3 files passed | - |
| `@earendil-works/pi-server` | 30 failed / 19 passed | Windows 无 Unix domain socket 支持：`listen EACCES`（`test/conformance.test.ts` Unix transport） |
| `@earendil-works/pi-tui` | 2 failed | home 前缀路径缩短在 Windows 未命中（`terminal-image.test.ts`） |
| `@earendil-works/pi-session-backend-sqlite-node` | 7 files passed / 68 passed | - |

### 2.1 基线对照结论

- AGENTS.md 文档基线：`packages/agent` + `packages/coding-agent` = 13 + 76 = **89 环境失败**。
- 本次：`pi-agent-core` = **2**（少于基线 13），`pi-coding-agent` = **76**（与基线完全一致）⇒ documented 基线包内 **新增失败 = 0**。
- 其余包（ai 1 / evals 1 / server 30 / tui 2）不在 AGENTS.md 基线口径内，且均与写入面无关（本 key 改动只落在 `packages/coding-agent/src/extensions/agent-team-loop/**`、`packages/coding-agent/test/**` 新增文件、`packages/multi-workers/*.py`；ai/evals/server/tui 不依赖这些模块），根因逐条已定性为 Windows/MSYS 环境或他 key 目录漂移，判为环境基线噪声。

### 2.2 coding-agent 失败分类（76 条，聚合）

- `test/extensions/agent-team-loop.test.ts`（1）：`T-17/B-1 anchor integrity`，`[ANCHORS] refs_total=79 resolved=10 unresolved=2 out_of_range=0 content_mismatch=67 unanchored_refs=69`；`unresolved = .agenticdoc/mw-guard-form-hardening/design.md worker/worker-mode.ts:747`（×2）。全文 67 条 content_mismatch 指向 `pm/ui-bridge.ts`、`worker/worker-mode.ts`（≤1571 行区段）、`shared/index-store.ts`、`shared/deliverable-evidence.ts` 等他窗未提交改动的行号位移；本 key 的 `worker-mode.ts` 改动全部落在 line 2400 之后，未落在任何 anchored 行区间（与 t01 报告一致：本 key 新增 mismatch = 0）。属基线 ②。
- `test/extensions/agent-team-loop-worker-file-tool.test.ts`（2）：`progress.md`/`report-*.md` 沙箱内多出 `trace.log` 的目录枚举断言，属他 key（mw-worker-progress-persist）既有失败。
- 其余 73 条分布在 Windows shell/path/watch/config/timeout 语义相关用例（`agent-session-runtime`、`tools`、`config`、`extensions-runner`、`model-registry`、`rag-*` 等），与 AGENTS.md 的 76 基线条数一致。

## 3. `python -m pytest packages/multi-workers` 失败逐条（7 条，全部基线噪声）

| # | 用例 | 判定 | 依据 |
|---|------|------|------|
| 1 | `test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites` | 基线 ③ | BOM 历史语料 `.agenticdoc/mw-dispatch-reliability/workers/mw-dr-glm53/task.md` 在 HEAD tree 中不存在（`git ls-files`=0）；断言在任何 launcher 代码执行前触发 |
| 2 | `test_task_type_parity.py::test_bom_historical_books` | 基线 ③（同一语料） | 同上；**卡片验收命令只 deselect 了 #1，未覆盖 #2**，两条都需 deselect |
| 3 | `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | 既有基线 | 冻结基线副本 vs `git show HEAD:autopilot/dispatch.py` sha256 不等；`autopilot/**` 本 key 零改动；已在 `mw-dispatch-settle-gates`、`mw-gate-verdict-hardening`、`mw-done-closure-repair`、`xkey-repair-mechanism`、`mw-autopilot-gate-alarm-liveness` 等 ≥5 份历史 QG 报告登记 |
| 4 | `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | 既有基线 | `assert 3 in [2]`：依赖外部实仓 fixture `H:/git/E2Feature` 的 round/report 一致性，外部项目已漂移；`autopilot/conductor.py` 本 key 零改动；历史 QG 报告已登记 |
| 5 | `test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge` | 既有基线 | `subprocess.run(text=True)` 无 `encoding=`，本机 locale=GBK 解码 node 的 UTF-8 中文输出抛 `UnicodeDecodeError`，`proc.stdout` 变 `None`。已由 2026-10-14 证据 `_scratch/evidence/locale-subprocess-io-20261014.md` 登记为跨 key 未修缺陷，归属 `mw-dispatch-settle-gates`（DONE） |
| 6 | `test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge` | 既有基线 | 同 #5（同一编码缺陷、同一证据文件） |
| 7 | `test_mwgal_t13_drift_identity.py::test_process_start_ms_probe` | 时长型环境噪声 | 断言「pytest 进程年龄 `< 300s`」；整轮 suite 跑 470s，该用例执行时进程已 >300s。单跑该用例：`1 passed in 0.10s`（新进程）。`mw.process_start_ms` 本 key 零改动 |

**新增失败 = 0**：以上 7 条均与本 key 写入面（worker-mode.ts / output-writer.ts / pm-orchestrator.ts / launcher.py / mw.py / mw_common.py）无因果关系；本 key 新增的两个 Python 套件（`test_mep_fallback_config.py` 41 用例、`test_mep_launcher_redispatch.py` 29 用例）在同一轮全绿。

### 3.1 建议的验收命令修正

原文 `--deselect ".../test_bom_historical_books_read_through_both_callsites"` 不足以覆盖基线 ③ 的两条同源用例，建议补第二条：

```
python -m pytest packages/multi-workers -q \
  --deselect "packages/multi-workers/test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites" \
  --deselect "packages/multi-workers/test_task_type_parity.py::test_bom_historical_books"
```

## 4. 基线噪声豁免清单（本 key 不得为凑全绿而改）

1. `test/suite/mwoc-*.test.ts` biome 3 warning + 2 info（§1.1，写面外，`--unsafe` 范畴）。
2. `test/extensions/agent-team-loop.test.ts` T-17/B-1 anchor integrity（§2.2；`.agenticdoc/mw-guard-form-hardening` 行号位移 + 该 key 不在 **EXPECTED** 表）。
3. pytest BOM 语料两条（§3 #1/#2）。
4. agent / coding-agent Windows 已知 89 环境失败基线（本次实测 78，无新增；§2）。
5. Windows/MSYS 相关跨包噪声：agent-core 路径拼写（2）、ai timi 目录漂移（1）、evals 反斜杠（1）、server unix socket EACCES（30）、tui home 路径（2）。
6. pytest：readcap 冻结基线（#3）、verdict-freshness 外部 fixture（#4）、mwds_t27/t29 GBK 解码（#5/#6）、process_start_ms 进程年龄（#7）。

## 5. 运行时生效说明（本 key 不执行 build）

本 key 的 TS 改动位于扩展源码，生产窗口运行的是已构建 bundle：

1. `npm run build`（根）或 `mw build --install`——重建 `packages/coding-agent/dist/**` 与全局扩展 bundle。**未由 T-07 执行**（AGENTS.md：未请求不构建；PM 统一安排）。
2. `/mw restart`——重启各项目窗口的 `serve`/launcher 进程，使 Python 侧（`launcher.py` 的 exit-3 拦截与备用链）对新 worker 生效。worker 角色下次 spawn 即生效；`main` 角色在窗口下次启动时生效。
3. 生效判据：新 worker 的 `worker-mode.js` 含 `[MODEL_ERR]`/`model_exhausted`；`.mw/dispatch.yml` 配置的 `fallback_models` 在 `mw doctor` 的 `dispatch` 段可见；exit 3 时 launcher.log/trace.log 出现 `[MODEL_RETRY]`/`[MODEL_FALLBACK]`。
4. 旧 bundle 窗口在重启前保持旧行为（不感知模型错误）。

## 6. 交付说明与发现的问题（仅报告，不修）

### 6.1 写入面（guard）与卡片不一致——阻塞 `packages/multi-workers/CHANGELOG.md` 与 `docs/**`

- 运行时 `write_face:` head（task.md 第 6 行）= `packages/coding-agent/CHANGELOG.md, packages/multi-workers/README.md, .agenticdoc/…/evidence/quality-gate-report-*.md`。
- 卡片 `tasks/T-07-closure.md` 的 `## 写入允许面`（第 22-24 行）与本任务卡正文实际声明了更多：`packages/multi-workers/CHANGELOG.md`、`docs/**`（mw 相关节）。
- 根因（读渲染结果推断）：卡片渲染器对每个 bullet 只取**第一个**反引号路径——第 22 行两个路径只落了第一个、第 23 行两个只落了第一个、第 24 行单路径正常。属 envelope producer（`agent-team-loop-pm@0.83.0`）侧 bug。
- 后果：`write`/`edit`/`bash` 对 `packages/multi-workers/CHANGELOG.md` 与 `docs/**` 被硬拦截（`[rule=write-scope]`）。本 worker 不绕过 guard，故这两项未落盘。
- 建议：PM 修复卡片渲染（每个 bullet 解析全部路径），或按 §6.2 的成稿文本直接补写 multi-workers CHANGELOG；`docs/**` 经查无 worker watchdog 节需同步（`docs/autopilot-observability-guide.md`/`dual-toolchain-practice-guide.md`/`rag-config-guide.md` 均无该节），故无实际内容缺失。

### 6.2 `packages/multi-workers/CHANGELOG.md` 待补条目（成稿，PM 直接采用）

```markdown
### Added

- Added the worker model-fallback chain (mw-model-error-perception): `.mw/dispatch.yml` gains a top-level `fallback_models:` block keyed by task type (`coding`/`phase-writer`/`repair`/`roadmap-writer`/`review`/`verifier`/`reviewer`/`research`/`rag-research`/`vision`), each a 1..4 entry list of `prefix/model` values (format-validated, list-deduplicated, `*_cli` transport prefixes rejected, read fail-soft); `mw doctor` reports a format error as an issue and a missing route / unavailable credential as a suggestion. A worker that exhausts its model exits 3 (`run.json model_exhausted: true`); the launcher then retries the SAME model up to `PI_WORKER_MODEL_ERR_MAX` (default 2, `0` = straight to the chain) before advancing the configured chain in order, using `--model` with `PI_WORKER_FALLBACK_INDEX`/`PI_WORKER_TRIED_MODELS` (the worker re-seeds from task.md + disk products; no global `setModel`, no `~/.pi` write). Every step is file-driven and restart-safe: same-model attempts are derived from the task's `[MODEL_RETRY]` trace lines and chain progress from `[MODEL_FALLBACK]` lines, an unusable candidate is skipped with `[MODEL_FALLBACK-SKIP]`, and an exhausted chain reaps as `failed`. Two hermetic suites (`test_mep_fallback_config.py`, `test_mep_launcher_redispatch.py`) add 70 cases.

### Changed

- Changed `mw model set`/`mw model clear` to rewrite `.mw/dispatch.yml` as a read-modify-write (mw-model-error-perception): `_model_write` now lifts every top-level key other than `models` off the existing file (`_dispatch_extra_keys`) before writing, so the new top-level `fallback_models` block (and any future key) is preserved instead of being silently dropped by the models-only rewrite.
```

### 6.3 实现层观察（t06 报告，未修）

- `_fallback_candidate_available` 判定候选不可用时，`_try_model_redispatch` 仍以 `index+1` 作为 `[MODEL_FALLBACK] attempt=` 与 `fallback_index`：被跳过的配置槽位计入 attempt，与 design §4「attempt=已消费的备用模型数」字面略有偏差；终止语义正确（跳过槽位被永久消费），仅 trace/INDEX 语义为「配置槽位序」。低危，建议 PM 判定是否后续 key 收口。

### 6.4 运行时硬崩盲区（spec §4 已声明越界）

- 硬崩（无 `agent_end`）不触发模型错误管线，由 OS exit + launcher `_exit_to_status` 兜底；print-mode phased 冻结缺陷（TRQ-2）不在本 key 修复范围。

## 7. 最终判定

- 除 §1/§2/§3 逐条列出的既有基线噪声外，本 key 门禁口径全绿；documented 基线包新增失败 = 0；本 key 新增测试（TS 13 + Python 70）全绿。
- 交付物：`packages/coding-agent/CHANGELOG.md` [Unreleased]（Added + Changed）、`packages/multi-workers/README.md`（新增「模型故障降级」节 + 4 条 env 契约）、本报告。
- 受阻交付物：`packages/multi-workers/CHANGELOG.md`（§6.1，envelope write_face 渲染 bug，成稿见 §6.2）；`docs/**`（无 watchdog 节需同步，无内容缺失）。
