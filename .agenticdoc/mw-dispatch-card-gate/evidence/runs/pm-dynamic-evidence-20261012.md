# PM 侧动态证据（QG 未覆盖面的补偿）

- Key: `mw-dispatch-card-gate`｜采集者: PM（本地）/ 采集时刻: 2026-10-12T13:35Z（21:35 本地）
- 动机：本次 QG（`mwd-t11b-adversarial-qg`）为 `review` 角色（只读、**无 bash**，见 `tasks/T-07-terminal-escape-hatch-and-type-source.md` 的 PM 裁定与两处固定测试）⇒ 它**无法执行**任何测试。为补上它将声明的"未覆盖面（无动态验证）"，由 PM 执行并归档原始输出。
- 说明：以下输出为 PM 在交付工作树上直接运行、按其自报格式摘录的关键行；完整 stdout 未另存（命令可原样重放）。

## 1. TS 定向（5 个本 key 新增/受影响的测试文件）

命令（在 `packages/coding-agent` 下）：

```
node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-card-envelope.test.ts test/suite/dispatch-card-injection.test.ts test/suite/output-recovery-contract.test.ts test/suite/dispatch-recovery-terminal.test.ts test/suite/change-ledger.test.ts
```

输出：

```
 Test Files  5 passed (5)
      Tests  79 passed (79)
   Duration  3.92s
```

`TS_EXIT=0`

## 2. Python 定向（4 个本 key 新增/受影响的测试文件）

命令（仓库根）：

```
python -X utf8 -m pytest packages/multi-workers/test_mwds_t29_producer_signal.py packages/multi-workers/test_mwds_t27_service_envelope.py packages/multi-workers/test_mwds_t27_card_audit.py packages/multi-workers/test_launcher.py -q
```

输出：

```
148 passed in 1.90s
```

`PY_EXIT=0`

## 3. 卡追溯与一致性 CLI（真实语料，非夹具）

命令（仓库根）：

```
python -X utf8 packages/multi-workers/autopilot/card_audit.py --root .agenticdoc --key mw-dispatch-card-gate
```

输出（末行）：

```
summary: cards=10 dispatched=0 missing=0 unlisted=14 -> OK
```

`CA_EXIT=0`

读法：`cards=10` = 本 key 现有 10 张卡；`missing=0` = 没有被引用却缺失的卡（缺卡会硬红）；`unlisted=14` = 14 个已派发 `task.md` 没有 `card_path:` 头 —— **符合预期**：cutover 尚未执行，派发仍由旧 bundle 完成（未携带卡身份行）；按 T-06/`card_audit.py` 语义这些计入 `unlisted_dispatches`，仅 `--strict` 判失败。cutover 后该数应随新派发下降。

## 4. 全量 Python 基线（PM 于 13:20Z 前后实测）

```
python -X utf8 -m pytest packages/multi-workers -q
2 failed, 1666 passed, 10 deselected, 190 warnings in 203.54s
FAILED test_autopilot_readcap_injection.py::test_baseline_left_end_bound
FAILED test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below
```

两条均为**既有基线**（`autopilot/dispatch.py` 冻结副本/外部 `H:\git\E2Feature` 依赖类）；`git status` 证实 `autopilot/dispatch.py` 在 T-10 之前未被任何会话改动，故非本 key 引入。

## 5. QG worker 运行态快照（采集时刻）

```
run_id            mwd-t11b-adversarial-qg@2026-10-12T13:05:54.066Z
status            running
pid               136376
last_heartbeat_at 2026-10-12T13:35:24.450Z
artifacts         []
elapsed           ~29.5 min
```

对照：全局队列行 `.agenticdoc/_workers.parallel` 同时刻仍写 `pending`（行时间戳 `2026-10-12T13:09:38.269Z`）⇒ **行状态与运行态不一致**（本 key 已登记为独立事故，见 `achieved.md` 遗留与事故文档）。故 monitor 的 "pending" 属谎报，非真实调度阻塞。

## 6. 未覆盖 / 未采集项（诚实标注）

- 未跑 `npm run check`（仓内并发会话正在改 `test/extensions/**`，`biome check --write .` 会改写他人文件 ⇒ worker 与我均以只读等价检查替代；本 key 的 TS 改动已由定向套件与既有守卫套件覆盖）。
- 未跑 `./test.sh` 全仓；未跑 e2e。
- 未做 cutover（属 T-08）⇒ 运行期一正一负证据、`[WRITE_FILE]` 事件生效、`card_path:` 落盘均待 cutover 后复测。
- 未采集完整 stdout 原文（仅关键行）；命令可重放。
