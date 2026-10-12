# T-21 回执：G5/G6 用例汇总 + IN-3 样本回放

- key: `mw-gate-verdict-hardening` · 日期: 2026-10-10 · 基线 HEAD: `776b82d7f`
- 执行方式：**PM 直执**（D-014 硬门禁批次内）
- 覆盖：**AC-014 / AC-019 ~ AC-024**，VC-024 ~ VC-046（映射表：`evidence/runs/verify-g5g6-tests.md`）
- 回执契约：本文件同时是 `workers/t-21-integrity-tests/report.md` 的副本

---

## 1. 交付

| 交付 | 内容 |
|---|---|
| **IN-3 夹具** | `packages/multi-workers/test/fixtures/in3-queue-9col-burst.txt`（250 行 × 9 列，27 owner，`sha256 6c4f4dfca3ed2e0dbb2a4a5f3b3ee0368622a8f48fb138ef6a1726b982005661`，36,988 B）|
| **夹具生成器** | `evidence/scripts/t21-make-in3-fixture.py`（从真实队列 `.agenticdoc/_workers.parallel` 抽取 IN-3 burst 行 → 去敏 → 补回第 9 列；可复跑）|
| **Python 回放** | `packages/multi-workers/test_in3_queue_replay.py`（**新，7 函数 / 8 例**）|
| **TS 回放** | `test/suite/worker-store.test.ts` 新增 `describe("IN-3 sample replay (T-21)")`（**5 例**，该文件 11 → 16）|
| **配额扫描形状** | `test/suite/worker-dispatch-guard.test.ts` 新增 `refuses a 10-candidate scan after the quota`（**1 例**，该文件 16 → 17）|
| **映射表** | `evidence/runs/verify-g5g6-tests.md`（VC-024 ~ VC-046 → 用例名 → 落地卡；四组数字；控制矩阵）|
| **非空洞对照** | `evidence/scripts/t21-controls.ps1`（A~E，5 组，全部转红 + `restored: True`）|

**命名偏离（1 处，需知情）**：卡片把 Python 回放文件写成 `test_worker_queue_integrity.py`，但该名称与 T-18 已落地的 `test_worker_queue_python_integrity.py` 只差一个词，且后者已被**冻结证据**（T-18 卡、T-18 回执、`t18-controls.ps1`、design §11.7）引用。为不改写冻结证据，回放文件改用**按用途命名**的 `test_in3_queue_replay.py`。

## 2. 夹具出处与去敏（可复核）

| 项 | 值 |
|---|---|
| 源 | `<project>/.agenticdoc/_workers.parallel`（gitignored，本机）|
| 抽取规则 | `dispatched_at` 落在事故 burst 秒 `2026-10-10T02:50:05` 的行 |
| 行数 | **250**（事故当次 252 行 / **28** owner）|
| owner | **27**（与事故的 28 个 key 差 1 个：`mw-worktree-junction-guard`）|
| 差量解释 | 该 owner 的 2 行（`wjg-rq1-junction-semantics` / `wjg-rq2-guard-seams`）在事故窗口内 `03:03:39.002Z` / `03:04:04.554Z` 被**原地 upsert** 重写了 `dispatched_at`，因此不再带 burst 指纹（本机实测；行本身没丢）。⇒ 250 + 2 = 252，**无行丢失、无补造** |
| 去敏 | owner 目录段 → `pk01..pk27`（首次出现序＝原字母序）；`task_key` → `<owner>-t<NN>`；`task_path` → `H:/proj/.agenticdoc/<owner>/workers/<task>/task.md` |
| 保持原样 | 列数（9）、分隔符（` | `）、`dispatched_at`（`.220Z` TS 格式）、`updated_at`（`+00:00` Python 格式）、`status` 分布（242 done / 8 failed）、owner 分组与 ASCII 序 |
| **重建项（1 处）** | 第 9 列 `origin` = `manual`：事故前落盘的是 9 列（新 codec 恒写 `origin`），事故**重建后**存活的是旧 codec 的 8 列输出（post-mortem §4.2 步骤 1/3）。断言只依赖列数/行数/时间格式，补回的第 9 列不承担任何结论 |
| 泄漏检查 | 0 行含 `Multi-Workers`/`E2Feature`/`msc-`/`wip-`/`wjg-` 等真实标识 |

## 3. 回放内容与四组数字

| # | 用例 | 断言 |
|---|---|---|
| 1 | `test_fixture_is_the_incident_shape` / TS `keeps the incident shape` | 250 行、每行 9 域、burst 秒、`Z` + `+00:00`、27 owner、owner 分组为纯 ASCII 序、零泄漏 |
| 2 | `test_current_codec_reads_every_incident_row` / TS `reads every incident row` | `rows == 250`、`unparsable == []`、`version == 1`、**key 集合非空**（`dispatched = ∅` 这一 IN-3 前提已不可能）|
| 3 | `test_legacy_codec_drops_every_incident_row` / TS `the pre-fix codec drops every incident row` | 旧 codec（`WORKER_COLS = 8`）对 250 行的接受数 = **0** ⇒ 机制可执行复现 |
| 4 | `test_current_codec_also_reads_the_legacy_column_shape` / TS `also reads the legacy 8-column writer output` | 8 列（旧 codec 自己的输出）⇒ 250 行全收、`unparsable == []`；TS 归一 `origin=manual`，Python 保留 `""` |
| 5 | `test_ten_column_row_is_counted_and_survives_all_three_writers` / TS `counts a 10-column row and keeps its slot across an upsert` | 注入 10 列行 ⇒ `unparsable == 1`（`line=251, cols=10`）；三个 Python 写者（`update_status` / `archive_stale_entries` / `upsert_worker_row`）与 TS `upsert` 回写后**该行原文仍在**、总行数 251 → 252 |
| 6 | `test_doctor_reads_the_incident_shape_without_a_false_positive` | `rows_total == 250`、`unparsable_count == 0`、`non_terminal_count == 0`、`run_ledger_conflict == []`、无 `queue-*` issue ⇒ **零假阳性** |
| 7 | `test_fixture_rows_are_terminal_and_keep_their_burst_stamp`（参数化 2 例） | 行数守恒 + 状态落在 `RUN_TERMINAL_STATUSES` + burst 戳保持 |

`[VERIFY]` 要求回答的四组数字：

| 数字 | 值 |
|---|---|
| 9 列样本行数 | **250** |
| 旧解析器丢弃行数 | **250 / 250**（全丢）|
| `unparsable` 计数 | 夹具 **0**；注入 1 行 10 列 ⇒ **1** |
| 单轮配额截断数 | 10 候选 ⇒ **3** 行（+1 条 `dispatch-quota`）；配置 `dispatch_max_per_scan: 1` ⇒ **1** 行；5 候选 ⇒ **3** 行 |

配额用例顺带把事故的行序指纹钉住：10 个候选保留的是 `t-1, t-10, t-2`（ASCII 序），与事故 §3.2「`msc-rq10..rq14` 排在 `msc-rq2` 前」同形。

## 4. `[VERIFY]` 实测

```
cd packages/multi-workers
python -X utf8 -m pytest test_in3_queue_replay.py -q -p no:randomly        → 8 passed
python -X utf8 -m pytest -q -p no:randomly                                 → 2 failed / 1431 passed / 10 deselected
                                                                             （2 红 = 开工前基线既有红）

cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts
                                                                           → 16 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts
                                                                           → 17 passed
node ../../node_modules/vitest/dist/cli.js --run \
    test/suite/{worker-store,worker-dispatch-guard,run-store,worker-run-identity}.test.ts
                                                                           → 4 files, 54 passed
node ../../node_modules/vitest/dist/cli.js --run <34 个相关测试文件>        → 33 passed | 1 skipped
                                                                             Tests 494 passed | 2 skipped（exit 0）
npm run check                                                              → 通过（exit 0，No fixes applied）
```

## 5. 非空洞对照（`evidence/scripts/t21-controls.ps1`）

| 控制 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| A | TS `WORKER_COLS_MAX = 9 → 8` | `worker-store.test.ts` · reads every incident row | 1 failed |
| B | Python `WORKER_COLS_MAX = 9 → 8` | `test_in3_queue_replay.py::test_current_codec_reads_every_incident_row` | 1 failed |
| C | TS `upsert` 回写时按解析结果过滤（丢不可读行）| `worker-store.test.ts` · counts a 10-column row and keeps its slot across an upsert | 1 failed |
| D | TS `WORKER_COLS_MIN = 7 → 9` | `worker-store.test.ts` · also reads the legacy 8-column writer output | 1 failed |
| E | Python `WORKER_COLS_MIN = 7 → 9` | `test_in3_queue_replay.py::test_current_codec_also_reads_the_legacy_column_shape` | 1 failed |

其余卡片的对照由各自脚本覆盖（`t15`/`t17`/`t18`/`t20`/`t22-controls.ps1`，全部转红），矩阵见 `verify-g5g6-tests.md` §3。

## 6. 已知残余

1. **夹具是快照，会与线上漂移**：生成器按 burst 前缀抽取，重跑会得到当时的行集合（本机队列仍在动）。冻结值 = 上文 sha256；用例把行数写成 `FIXTURE_ROWS = 250` 常量并在注释里指向本文件。
2. **第 9 列 `origin` 是重建值**（§2）。若要更严格的"原样"，需要在下次事故时**当场**保存队列文件；目前 gitignore（`.agenticdoc/**/_workers*`）使队列无历史版本可回溯。
3. **`test_launcher.py` 的 `TestReconcileRunState` 依赖 launcher 进程语义**（`[END]`/`output.md`/静默窗口），本机通过；Windows 上 `_reconcile_orphans` 的 mtime 语义仍有历史基线噪声（89 例环境失败基线，与本卡无关）。
4. **配额测试用默认 3**：真实项目 `dispatch_max_per_scan` 未写进 `config.json` 时走默认值；若将来把默认调大，`FIXTURE`-无关的这两个用例的期望值会随之变化（常量引用 `DEFAULT_DISPATCH_MAX_PER_SCAN`，不是字面量 3）。
5. **AC-014 由本卡正文承接**（不是残余）：它是证据标准型 AC——每条机器判据要配非空洞对照、`[VERIFY]` 数值必须实测、"已校验"声称要带 `文件:行号`/测试名坐标。本卡的交付即为此：映射表 `verify-g5g6-tests.md`（VC → 用例名 → 落地卡）、控制矩阵（6 个脚本 30 组变异全红）、以及各卡回执里的 `test_xxx.py::用例名` 坐标。本卡自身也遵守该标准：§3/§4 的每组数字都能用上文命令复现。
