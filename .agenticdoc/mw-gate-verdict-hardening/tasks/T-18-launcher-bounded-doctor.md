# T-18: G5-C launcher 有界 + acked 参与 + doctor 形状告警

- 波次: **3** · 依赖: **T-11**（同写 `mw_common.py` / `mw.py`，必串行；另见 D-009 他人未提交改动）
- 写面（独占）: `packages/multi-workers/launcher.py`、`packages/multi-workers/mw_common.py`
- 只读参考: `packages/coding-agent/src/extensions/agent-team-loop/shared/ack-store.ts:9,20`（`_workers.acked` 的唯一写者，格式 `taskKey | ackedAtIso`）
- AC: **AC-021 / AC-023** · VC: **VC-030 / VC-031 / VC-039 / VC-040 / VC-041**
- 基线: `10446aefb`

## 问题（IN-3 放大器 F1/F3/F5）

- `launcher.py:822` 只 spawn `status == "pending"` 的行；`:837` `if max_workers and len(running_procs) >= max_workers:` ⇒ **`max_workers = None` 时该分支永不生效**（默认 `:847`；`mw.py:328-329`/`:424-425` 只在真值时透传 `--max-workers`）⇒ **无上限**（事故峰值 66 并发 node worker）。
- `_workers.acked`（261 行）**在 launcher 侧零引用** ⇒ "已 acked 的终态任务"对重派毫无作用。
- `mw doctor` 没有"队列形状"判据 ⇒ 252 行 / 100% 非终态这种形态**无人告警**（F5）。

## 交付

1. `launcher.py`：`max_workers` 默认从 `None` → `launcher_max_workers`（默认 8）；优先级不变（CLI > task.md 头 > config > 默认）。
2. spawn 前：`if task_key in acked and isTerminalRunState(task_key): 收敛该行为终态 + 跳过`（读 `.agenticdoc/_workers.acked`，格式 `taskKey | iso`；解析失败按"无信息"处理，**不得**当成已 acked）。
3. `mw_common._doctor_issues`（插在 `:2887` 之前）新增三条**无状态**判据（不建快照文件，保持只读面不写盘）：
   - `rows_total > cfg.queue_alarm_delta`（默认 50）**且** 非终态占比 > 0.9 ⇒ issue `queue-burst-shape`；
   - 解析失败行数 > 0 ⇒ issue `queue-rows-unparsable`；
   - `run.json` 终态 ∧ 台账非终态 ⇒ issue `run-ledger-conflict`（T-20 落地后接入）。
4. 配置键（与 T-02 同族，写入 `DEFAULT_CONFIG` / `_INT_RANGES`）：`launcher_max_workers`（1..64，默认 8）、`queue_alarm_delta`（10..10000，默认 50）。

## 契约（冻结）

- doctor 判据**不得**需要历史快照、**不得**创建文件（只读面）。
- `_workers.acked` 解析必须 fail-safe：读不到/格式坏 ⇒ 视为"无 ack 信息"（继续按台账判），不得因此**跳过**全部任务。
- 默认并发上限必须是**有限值**；0/负数非法（配置校验拒绝）。
- 历史队列（252 行样本）在只读面上必须**只产 issue、不改文件**。

## 实施记录（2026-10-10，PM 直执）

实际落地与卡的差异（均有证据）：

1. **第三个 Python 写者**：除 `update_status` 之外，`archive_stale_entries` 与 **`autopilot/dispatch.py:621-633`** 也在「parse 全表 → 整表重写」（后者是真正的派发写入口）。两者均改为槽位保留（新增 `mw_common.upsert_worker_row`），否则同一缺陷还留两份拷贝（R17）。
2. **解析层**：新增 `parse_workers_queue()`（`rows`/`unparsable`/`version`）、`parse_worker_line()`、`WORKER_COLS_MIN/MAX = 7/9`、`QUEUE_HEADER_RE`；`parse_workers_file()` 变为它的薄封装（既有调用点零改动）。开发中真实踩到“把 7..9 写成 `in (7,9)` ⇒ 8 列行不可读” ⇒ 已固化为控制 E。
3. **配置键三个**（不是两个）：`launcher_max_workers`(1..64, 8)、`dispatch_max_per_scan`(1..64, 3)、`queue_alarm_delta`(10..10000, 50)；第三个（配额）本属 T-17 卡片，但本次才落进配置 schema，同时 TS 侧 `readDispatchMaxPerScan()` 改为读项目 config（`opts.maxPerScan` > config > 默认 3）。
4. **冻结语料**：55 → **64** 例（+3 单键 accept + 6 范围 reject），sha256 双侧 re-freeze；`_GOLDEN_REGRESSION_SHA256`（另一 key 的旁路锁）也 deliberate re-freeze。
5. `read_acked` / `read_run_status` 落在 `mw_common.py`；`_TERMINAL_STATUSES` 之外另立 `RUN_TERMINAL_STATUSES`（含 `lost`，D-022）。

## [VERIFY]

```
cd packages/multi-workers
python -X utf8 -m pytest test_worker_queue_python_integrity.py -q          # 13 passed
python -X utf8 -m pytest test_launcher.py -q -k "MaxWorkers or Ack"       # 7 passed
python -X utf8 -m pytest test_doctor_autopilot.py test_serve_doctor.py -q  # 全绿
python -X utf8 -m pytest test_autopilot_config.py test_autopilot_config_parity.py \
    test_autopilot_effective_config.py test_autopilot_gate_schema_v2.py -q # 全绿
python -X utf8 -m pytest -q                                                # 2 failed / 1407 passed（2 红=开工前基线既有红）
cd ../coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-dispatch-guard.test.ts \
    test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts \
    test/suite/autopilot-console.test.ts                                    # 68 passed
npm run check                                                              # 通过（全量输出）
```

只读面实测（`mw.py doctor --project H:\git\Multi-Workers --json`，只读、不写盘）：队列段落产出新增机器字段 `rows_total`/`unparsable_count`/`version`/`alarm_delta`/`non_terminal_count`/`run_ledger_conflict`；实测输出见 `evidence/runs/t-18-queue-integrity-report.md` §5。

## 非空洞对照（`evidence/scripts/t18-controls.ps1`，六组均转红 + 还原校验 True）

| 控制 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| A | `limit = max_workers or 10**9`（`None` 重新等于无界）| `test_default_max_workers_is_eight_not_unbounded` | 1 failed |
| B | `queue-burst-shape` 判据条件改为 `if False:` | `test_doctor_burst_shape_flags_the_in3_fingerprint` | 1 failed |
| C | ack 解析失败写成 `acked[key] = ""`（当成已 acked）| `test_acked_parse_failure_does_not_skip` | 1 failed |
| D | `update_status` 改回「parse 全表 → 整表重写」（丢 `unparsable` 行）| `test_update_status_preserves_unparsable_rows` | 1 failed |
| E | 行宽判据改成 `in (7, 9)`（8 列行不可读；开发中真实踩到的 bug）| `test_parse_workers_queue_counts_rows_and_unparsable_slots` | 1 failed |
| F | `queue-rows-unparsable` 判据条件改为 `if False:` | `test_doctor_flags_unparsable_rows` | 1 failed |

## 回执

写入 `evidence/runs/t-18-queue-integrity-report.md`（PM 直执，不建不存在的 `workers/` 目录）。
