# T-21: G5/G6 用例 + IN-3 样本回放

- 波次: **4** · 依赖: **T-15 / T-17 / T-19 / T-20**
- 写面（独占，**实施后**）: `packages/coding-agent/test/suite/worker-store.test.ts`、`packages/coding-agent/test/suite/worker-dispatch-guard.test.ts`、`packages/multi-workers/test_in3_queue_replay.py`（新；卡片原写 `test_worker_queue_integrity.py`，因与 T-18 的 `test_worker_queue_python_integrity.py` 几乎同名且后者被冻结证据引用而改名）、`packages/multi-workers/test/fixtures/in3-queue-9col-burst.txt`（新夹具）、`evidence/runs/verify-g5g6-tests.md`（新映射表）
- AC: **AC-014 / AC-019 ~ AC-024** · VC: **VC-024 ~ VC-046**（映射表逐条落地；VC-039~041 由 T-18、VC-042~045 由 T-20、VC-046 由 T-19/T-20 已先落地，本卡汇总核销）
- 基线: `10446aefb`

## 交付

1. **IN-3 样本回放（核心回归）**：把事故当日队列的**行格局**做成夹具（去敏：`task_key` 改名、路径改占位符，但**列数/分隔符/时间格式原样**）：
   - 9 列行 252 行样本 ⇒ 新解析器 `rows == 252`、`unparsable == 0`；
   - 同一夹具喂给"`WORKER_COLS_MAX = 8`"的旧解析器（用局部参数化模拟）⇒ **丢弃 252 行**（把事故机制钉成可执行回归）；
   - 混入 1 行 10 列 ⇒ `unparsable == 1`，且 `upsert` 回写后**行数不变**。
2. **派发面用例**（`worker-dispatch-guard.test.ts`）：
   - `unparsable > 0` ⇒ 零派发 + `phase:"dispatch-alarm"`；
   - 空队列 + 有终态证据 ⇒ 零派发 + 告警；空队列 + 无终态证据（真·新项目）⇒ 正常派发；
   - 候选 10 个 ⇒ 单轮新增 = `dispatch_max_per_scan`；
   - 隔离双向（VC-034 / VC-035）。
3. **运行身份用例**（VC-032 / VC-033）：`run.json` 终态拒派 + `supersedes` 放行 + 旧目录只读。
4. **Python 侧**（`test_worker_queue_integrity.py`）：`_workers.acked` 解析 fail-safe、launcher 默认上限、doctor 三条形状判据（含 252 行样本）。

## 契约（冻结）

- 夹具**不得**包含真实 key 名/路径（去敏），但**不得**改变列格局（否则失去回归意义）。
- 每个用例必须成对：正向 + **非空洞对照**（摘掉判据 ⇒ 红）。
- 用例不得依赖真实服务/真实 `_workers.parallel`（用临时目录）；不得触碰项目真实台账。

## 实施记录（2026-10-10，PM 直执，基线 `776b82d7f`）

1. **夹具**（`packages/multi-workers/test/fixtures/in3-queue-9col-burst.txt`）：从真实队列抽取 `dispatched_at` 落在事故 burst 秒的行 → **250 行 × 9 列 / 27 owner**，sha256 `6c4f4dfca3ed2e0dbb2a4a5f3b3ee0368622a8f48fb138ef6a1726b982005661`。生成器 = `evidence/scripts/t21-make-in3-fixture.py`（可复跑）。事故当次 252 行 / 28 owner：差量 = `mw-worktree-junction-guard` 的 2 行（`wjg-rq1/rq2`）在 `03:03:39.002Z`/`03:04:04.554Z` 被**原地 upsert** 重写了 `dispatched_at`（不再带 burst 指纹，行本身没丢）。第 9 列 `origin=manual` 为**重建值**（事故前 9 列、事故后存活 8 列，见 post-mortem §4.2）。
2. **命名偏离**：卡片写的 `test_worker_queue_integrity.py` 与 T-18 已落地的 `test_worker_queue_python_integrity.py` 几乎同名，且后者被冻结证据（T-18 卡/回执/控制脚本/design §11.7）引用 ⇒ 回放文件改名为 **`test_in3_queue_replay.py`**（按用途命名），不改写冻结证据。
3. **回放**：Python 7 函数 / 8 例；TS `worker-store.test.ts` 新增 `describe("IN-3 sample replay (T-21)")` 5 例（11 → 16）；`worker-dispatch-guard.test.ts` 新增 10 候选配额例（16 → 17，并把 ASCII 扫描序 `t-1, t-10, t-2` 钉住——与事故 §3.2 同形）。
4. **映射表**：`evidence/runs/verify-g5g6-tests.md`（VC-024 ~ VC-046 → 用例名 → 落地卡 + 四组数字 + 控制矩阵）。

## [VERIFY]

```
cd packages/multi-workers
python -X utf8 -m pytest test_in3_queue_replay.py -q -p no:randomly        # 8 passed
python -X utf8 -m pytest -q -p no:randomly                                 # 2 failed / 1431 passed（2 红 = 基线既有红）
cd ../coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-store.test.ts          # 16 passed
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts # 17 passed
node ../../node_modules/vitest/dist/cli.js --run <34 个相关文件>                            # 33 passed | 1 skipped；Tests 494 passed | 2 skipped
npm run check                                                                             # 通过（No fixes applied）
```

**四组数字**：9 列样本行数 **250**；旧解析器丢弃 **250/250**；`unparsable` **0**（注入 10 列行 ⇒ **1**，且原文在四个写者回写后仍在）；单轮配额截断 **10 候选 → 3 行**（默认 3；配置 1 ⇒ 1 行）。

## 非空洞对照（`evidence/scripts/t21-controls.ps1`，A~E 全红 + `restored: True`）

| 控制 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| A | TS `WORKER_COLS_MAX = 9 → 8` | `worker-store.test.ts` · reads every incident row | 1 failed |
| B | Python `WORKER_COLS_MAX = 9 → 8` | `test_in3_queue_replay.py::test_current_codec_reads_every_incident_row` | 1 failed |
| C | TS `upsert` 按解析结果过滤（丢不可读行）| `worker-store.test.ts` · counts a 10-column row and keeps its slot across an upsert | 1 failed |
| D | TS `WORKER_COLS_MIN = 7 → 9` | `worker-store.test.ts` · also reads the legacy 8-column writer output | 1 failed |
| E | Python `WORKER_COLS_MIN = 7 → 9` | `test_in3_queue_replay.py::test_current_codec_also_reads_the_legacy_column_shape` | 1 failed |

T-15/T-17/T-18/T-20/T-22 的判据对照由各自脚本覆盖（t15 3 组 / t17 5 组 / t18 6 组 / t20 7 组 / t22 4 组，共 **30 组变异全部转红**）——矩阵见 `verify-g5g6-tests.md` §3。

## 回执

`evidence/runs/t-21-integrity-report.md`（= `workers/t-21-integrity-tests/report.md`，哈希相同）+ 映射表 `evidence/runs/verify-g5g6-tests.md`。
