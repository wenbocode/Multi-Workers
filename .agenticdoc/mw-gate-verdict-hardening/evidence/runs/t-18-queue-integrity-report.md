# T-18 回执：G5-C launcher 有界 + acked 参与 + Python 队列写面槽位保留 + doctor 形状判据

- key: `mw-gate-verdict-hardening` · 日期: 2026-10-10 · 基线 HEAD: `776b82d7f`
- 执行方式：**PM 直执**（D-014 硬门禁批次内）
- 覆盖 AC：**AC-021**（② launcher 有界 / ③ acked 参与，`[REVISED]`）、**AC-023**（写面范围扩到全部 Python 写者 + doctor 三条无状态判据，`[REVISED]`）
- 对应 IN-3 放大器：**F1**（无上限 spawn，峰值 66 并发）、**F3**（`_workers.acked` 零引用）、**F4**（写侧整表重写把丢行固化为删除）、**F5**（无队列形状告警）

---

## 1. 变更清单（6 个生产/测试面 + 3 个配置面）

| 文件 | 变更 | 关联 |
|---|---|---|
| `packages/multi-workers/launcher.py` | `_poll_once` 的 `limit` 在 `max_workers is None` 时取 `mw_common.launcher_max_workers(project_dir)`；派发前 acked 收敛（非终态行 ⇒ `run.json` 终态或 `done`，且不 spawn）；`run()` 同时解析并打印上限；`--max-workers` 帮助文本声明“never unbounded” | AC-021②③ |
| `packages/multi-workers/mw_common.py` | 新增 `parse_workers_queue()`（`rows`/`unparsable`/`version`）、`parse_worker_line()`、`read_workers_file_lines()`、`_scan_worker_lines()`、`upsert_worker_row()`、`read_acked()`、`read_run_status()`、`launcher_max_workers()`、`_queue_alarm_delta()`；`_write_workers_file()` 改为**行列表**入参；`update_status()`/`archive_stale_entries()` 改逐行保留；`_doctor_queue()` 扩字段；`_doctor_issues()` 加 3 条判据；`format_doctor_text()` 零扰动追加 | AC-023、AC-021② |
| `packages/multi-workers/autopilot/dispatch.py` | 队列写入改用 `mw_common.upsert_worker_row()`（第三个整表重写写者，R17 范围变更） | AC-023 |
| `packages/multi-workers/autopilot/config.py` | `DEFAULT_CONFIG` 14 → **17** 键（`launcher_max_workers`/`dispatch_max_per_scan`/`queue_alarm_delta`）+ `_INT_RANGES` + docstring | AC-021① |
| `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` | 同上 6 处镜像（interface / DEFAULT_CONFIG / INT_RANGES / `intOf` 联合 / `readConfig.merged` / `saveConfig.ordered`） | 跨语言一致 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | 新增 `readDispatchMaxPerScan()`，`dispatchNewTasks` 的配额来源 = `opts.maxPerScan` > 项目 config > 默认 3 | AC-021① |
| `test/fixtures/autopilot-config-corpus.json` | 55 → **64** 例（+3 单键 accept、+6 范围 reject），sha256 双侧 deliberate re-freeze | T-14 前置 |

新增/扩展测试（**20 例**）：

- `packages/multi-workers/test_worker_queue_python_integrity.py`（**新，13 例**）：行/不可解析行计数、版本头、三个写者槽位保留、无匹配行不写盘、acked fail-safe、doctor 三条判据、健康队列文本零扰动。
- `packages/multi-workers/test_launcher.py`（+**7 例**）：`TestLauncherMaxWorkersBound`（默认 8 / config 覆盖 / 显式参数优先 / 越界回落）＋ `TestLauncherAckConvergence`（acked 收敛不 spawn / ack 垃圾内容仍 spawn）。
- `packages/coding-agent/test/suite/worker-dispatch-guard.test.ts`（+1 例）：配额从项目 config 读取 + 坏配置回落。
- 同步的计数/顺序锁：`test_autopilot_config.py`、`test_autopilot_effective_config.py`、`test_autopilot_gate_schema_v2.py`、`test_mw_autopilot_cli.py`、`autopilot-console.test.ts`、`autopilot-config-parity.test.ts`、`autopilot-config-sync.test.ts`、`test_autopilot_readcap_injection.py`（旁路 golden sha re-freeze）。

## 2. 关键设计点（为什么这样做）

1. **`None` 永不等于无界**：解析只做一次（`_poll_once` 内），因此**任何**调用路径（含直接调 `_poll_once(..., None)` 的测试）都有界；配置坏掉时回落到默认 8（有界回落），而不是放开。
2. **acked 是“无信息安全”的信号**：ack 只在终态行上发生，所以“acked ∧ 行非终态”只可能来自队列被重建（IN-3）。收敛方向选 fail-closed：宁可少跑一个 PM 已吸收的任务，也不重跑。
3. **写面逐行保留**：`_write_workers_file` 的入参从“行字典”改成“**原始行**”，从类型上消灭“读全表丢弃后重写”这条路径；三个写者都只重写自己那一行。
4. **行宽是区间**：7/8/9 列都必须可读（8 列行 = 无 `origin` 的历史行）。**开发中真实踩到过**把判据写成 `in (7, 9)`，被冒烟脚本抓到并固化为控制 E。
5. **doctor 无状态**：形状判据只看当前队列内容（`rows_total` / 非终态比例 / `unparsable` 计数），不建快照文件，只读面不写盘。
6. **阈值可配**：`queue_alarm_delta` 走 effective config（fail-soft 回落 50），因此同一判据在 `mw` 与 `conductor` 两种配置层下都可用。

## 3. `[VERIFY]` 实测

```
cd packages/multi-workers
python -X utf8 -m pytest test_worker_queue_python_integrity.py -q           → 13 passed
python -X utf8 -m pytest test_launcher.py -q -k "MaxWorkers or Ack"        → 7 passed
python -X utf8 -m pytest test_launcher.py test_doctor_autopilot.py test_serve_doctor.py \
    test_mw_autopilot_cli.py test_autopilot_dispatch.py test_autopilot_attribution.py \
    test_mw_serve_config_partial.py test_common.py test_worker_queue_python_integrity.py \
    test_autopilot_config.py test_autopilot_config_parity.py test_autopilot_effective_config.py \
    test_autopilot_gate_schema_v2.py -q -p no:randomly                     → 386 passed
python -X utf8 -m pytest -q -p no:randomly                                 → 2 failed / 1407 passed / 10 deselected
                                                                             （2 红 = 开工前基线既有红）

cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run <23 个导入 status-model/pm-orchestrator/worker-store/ui-bridge 的测试>
                                                                           → 393 passed | 1 skipped（exit 0）
npm run check                                                              → 通过（全量输出）
```

**基线对照**（`evidence/runs/verify-baseline.md`）：开工前 Python `2 failed / 655 passed`，两条既有红为
`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`（frozen-sha drift）与
`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`（语料相关）。
本次全量跑的二红与之**完全一致**；期间新增的第三条红
（`test_existing_regression_files_untouched`）由 `_GOLDEN_REGRESSION_SHA256` deliberate re-freeze 消解，不属于回归。

## 4. 非空洞对照（`evidence/scripts/t18-controls.ps1`）

| 控制 | 变异 | 指名用例 | 结果 |
|---|---|---|---|
| A | `limit = max_workers or 10**9`（`None` 重新等于无界）| `TestLauncherMaxWorkersBound::test_default_max_workers_is_eight_not_unbounded` | 1 failed |
| B | `queue-burst-shape` 条件 → `if False:` | `test_doctor_burst_shape_flags_the_in3_fingerprint` | 1 failed |
| C | ack 解析失败写成 `acked[raw] = ""` | `TestLauncherAckConvergence::test_acked_parse_failure_does_not_skip` | 1 failed |
| D | `update_status` 改回「parse 全表 → 整表重写」| `test_update_status_preserves_unparsable_rows` | 1 failed |
| E | 行宽判据改成 `in (7, 9)` | `test_parse_workers_queue_counts_rows_and_unparsable_slots` | 1 failed |
| F | `queue-rows-unparsable` 条件 → `if False:` | `test_doctor_flags_unparsable_rows` | 1 failed |

脚本跑完自动还原，校验 `restored: True`。

## 5. 只读面实测（真实项目，未写盘）

命令：`python -X utf8 packages/multi-workers/mw.py doctor --project H:\git\Multi-Workers --json`（`fix=False`）

| 观测 | 值 |
|---|---|
| 执行前后 `_workers.parallel` | sha256 前缀 `2DB87B49AC9A`，50,444 B，mtime 未变，文件数未变 ⇒ **只读面不写盘** |
| `queue.rows_total` | 252 |
| `queue.non_terminal_count` | 0 |
| `queue.unparsable_count` / `version` | 0 / 1（无版本头的历史文件 ⇒ 无回填）|
| `queue.alarm_delta` | 50（来自 effective config）|
| `queue.run_ledger_conflict` | 0（T-20 的 `run.json` 尚未存在）|
| `summary.issues` | `[]`（**正确**：当前 252 行全部终态 ⇒ 非终态占比 0 ⇒ 不产 `queue-burst-shape`，无假阳性）|
| 文本行 | `queue: 0 non-terminal task(s), 0 stale, 1 archived`（无 `unparsable` 后缀 ⇒ 零扰动）|

⇒ 形状判据的“有/无”两侧分别由**真实项目**（252 行全终态 ⇒ 静默）与**测试夹具**（252 行全 pending ⇒ issue）覆盖；这也验证了判据不是“行数大就报”，而是 IN-3 的“大 + 几乎全非终态”组合指纹。

## 6. 已知残余与边界（诚实记录）

1. **`dispatch_max_per_scan` 的 TS 侧只读项目 config 层**（`readConfig` 不含 machine layer；machine layer 是 Python-only，既有设计）。Python 侧（doctor/launcher）走 effective config 含机器层。
2. **`run-ledger-conflict` 尚未被真实触发**：需要 T-20 的 `run.json` 产物；判据与字段已就位，T-20 落地后自动生效（无回填、无新增写路径）。
3. **acked 收敛把状态写成 `done`**（除非 `run.json` 给出更精确的终态）：ack 记录只存时间戳，失败/需澄清的历史状态无法恢复；选 `done` 是 IN-3 方向上的 fail-closed 取舍。
4. **launcher 上限对已在跑的进程不生效**：`limit` 只影响新 spawn；若上一轮已超发，需要等进程退出自然收敛（事故收尾用的就是这个性质）。
5. **`autopilot/dispatch.py` 属范围外文件（R17）**：只改队列写入那一段（`git diff` 1 处、-8/+8 行），未触碰 `loop:`/`attempt:` 标签与其余逻辑。
6. **旁路 golden sha 已移动**：`test_autopilot_readcap_injection.py::_GOLDEN_REGRESSION_SHA256["test_autopilot_config.py"]` 从 `5a728d0d…` → `c7c16802…`（原因是配置键锁 14 → 17），与该文件既有注释里 2026-09-26 的先例同性质，已双语记录。
7. **控制 E 是“真实 bug 的固化”**：`in (7, 9)` 的写法在开发第 1 小时就被冒烟脚本抓到（8 列历史行会被判不可读 ⇒ 可能再次触发 fail-closed 误判），因此它不是假设性变异，而是本次真实发生过的缺陷。
