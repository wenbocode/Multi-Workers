# 质量门报告: mw-dynamic-concurrency

- Key: mw-dynamic-concurrency
- 报告时间: 2026-10-14
- 判定范围: `spec.md` 的 AC-001..AC-013（13 条）+ `design.md` 的 VC-101..VC-109（9 条），共 **22 个问句**
- 证据基线: `evidence-requirement.md`（`ac_fingerprint = 95d6a253ba12`）、`evidence/baseline/`（3 份）、`evidence/runs/`（按 worker `[VERIFY]`/`[FLOW]` 机械抽取）、`evidence/M-0{2,3,4,5,6}*.md`、以及 PM 自己的原始运行输出
- 复核者: PM（本 key 窗口）；所有计数均为 PM 亲跑，非 worker 转述（P-025）

## §0 过程偏差披露（先自陈，避免把偏差读成结论）

1. **`./test.sh` 不可达**：本机 `bash` 落到 WSL 且未安装发行版 ⇒ 秒退 exit 1（P-032 复发）。plan §2 的 B4 门禁①改为按 AGENTS.md 回落路径执行：**包根显式文件套件 + 全量 `python -m pytest -q`**。TS 侧只跑了**定向**套件（44 / 26 / 4 / 36 passed + `npx tsgo --noEmit` exit 0），**未跑全量 TS**。
2. **`npm run check` 的越面副作用**：该命令是全仓 `biome check --write`，本轮 `Fixed 10 files`，落点含另一 session 在写的 `worker-mode.ts` / `write-face.ts` / `pm-orchestrator.ts`（仅格式化，exit 0 无残留，未回退）。已升 P-017 [高危] 复发。
3. **一次幻影红**：PM 与 worker 的全量 pytest 重叠跑，多出 `test_rag_init`（单跑 12 passed）等幻影红；已立 P-036，失败**集**为准。
4. **`ac_fingerprint` 的计算口径**：按门禁算法（sorted unique AC ids → sha1 → 前 12 位）= `95d6a253ba12`。
5. **AC-008 / AC-010 无对应 VC**（design.md 未定义），如实披露并改用测试级载体，不伪造 100% AC→VC 覆盖。

## §1 问题清单

| 编号 | 问句 | 证据来源（PM 亲跑） | 证据载体 | 期望节点/值 | 判定 |
|------|------|--------------------|---------|------------|------|
| Q-AC-001 | key 层实起 = `min(配置上界, |前沿|)`？ | M-02 §6 探针 + `test_mdc_concurrency.py`（10 passed） | `[VERIFY] cap=4,|F|=3→3` / `cap=1→1` / `cap=2,|F|=5→2` / `|F|=0→0` | 逐组恒等 | ✅ 充分 |
| Q-AC-002 | per-key 实起 = `min(per-key 上界, |任务前沿|)` 且不与在飞写面重叠？ | M-02 附录 A/B、`test_mdc_concurrency.py` VC-102、`test_mdc_e2e.py` VC-105 | 实起 5 = `min(5,6)`；`C(5,2)=10` 次判定**同文件多写者对 = 0**；逐行复跑真实 `_write_face_verdict` 5/5 不拒 | 0 重叠对 | ✅ 充分（空窗见 Q-AC-002b，⚠️） |
| Q-AC-002b | 跨 tick 顶配空窗是否可接受？（本 key 暴露的边界） | `test_mdc_e2e.py::test_ac002_topup_window_quantified` | `topup_ticks=2` / `free_slots=3` / `idle_slot_ticks=6` / `next_batch=2` / `extra_idle_ticks=0` | 量化 + 判定 | ⚠️ 已量化·已判定可接受·**未修**（记债务 D-MDC-3） |
| Q-AC-003 | 依赖/写面数据缺失或不可解析时该层回退串行 + 审计，不默认放大？ | M-02 附录 A、`test_mdc_concurrency.py` VC-104 | V-problem 串行回退；写面重叠被拒时 `stalled_events=0` 且 key 仍 `running` | 实起 ≤1 + 审计行 | ✅ 充分 |
| Q-AC-004 | `max_parallel_keys` 为 key 层上界；新增 per-key 上界键；既有 materialized config 不变非法？ | `test_autopilot_config.py` + `test_autopilot_config_parity.py` + `test_autopilot_effective_config.py`（合计 65 passed）、语料 73→77 | `config.py:91/92` 默认 8/4、`:127/128` 值域 `(1, None)`；语料 `range-max-parallel-low` 由 reject→accept + `range-max-parallel-below-floor` 仍 reject（非空控制） | 两侧一致且旧 config 合法 | ✅ 充分 |
| Q-AC-005 | 面板同快照显示"配置上界"与"本 tick effective"且可复算一致？ | `test/suite/autopilot-concurrency-panel.test.ts`（4 passed）、`autopilot-monitor.test.ts`（26 passed） | `monitor.ts:968` `slotsCap` / `:991` `slotsUsed: busyKeys.size` / `:994-995` `slotsEffective=min(cap,frontier)`；渲染行逐字断言 | 两量同快照可复算 | ✅ 充分 |
| Q-AC-006 | 上界改为 1 时两层均串行且无需重启 serve？ | M-02 探针 + `test_mdc_concurrency.py` VC-103 | key 层 `mpk=2→2 / 1→1`、per-key `cap=1→1`；配置热读 `conductor.py:3432-3447`（同进程改配置后下一 tick 生效） | 实起 ≤1，无重启 | ✅ 充分 |
| Q-AC-007 | TS `status-model.ts` 与 Py `config.py` 对新增/变更键逐字段一致？ | `autopilot-config-parity` + `autopilot-config-sync` + 面板套件（36 passed）、语料具名用例 | `config.py:91/92` = `status-model.ts:141/142` = 8/4；`:127/128` = `:202/203` = `(1,None)`/`[1,null]`；`range-max-parallel-low` 两侧同判 accept | 逐字段一致 | ✅ 充分 |
| Q-AC-008 | 任务级依赖载体 = 新增独立解析器 + 卡头 `deps:` 规则，不复用 `card_audit._header_value`？ | `test_task_graph.py`（71 passed）；spec 记录的实测 | 旧解析器 5/5 真实卡返回空串（`card_audit.py:160-162` 在 H1 处 break）；新解析器命中 | 新解析器可用 | ⚠️ 测试级载体（**design 无 VC**，记债务 D-MDC-1） |
| Q-AC-009 | 悬空/自依赖/环/跨 key 被检测 → 整 key 串行 + 事件；id→stem join 用"数字核心"？ | `test_task_graph.py`（71 passed，含四类问题用例） | 146 个真实 dep token：stem 精确 0 / `_plan_task_file_stems` 0 / 数字核心唯一 125 | 检测 + 串行 | ✅ 充分 |
| Q-AC-010 | key 层依赖语义校验在 tick 内执行且不改 fail-closed？ | M-02 §5 D 原始事件 + PM 代码审计 | `_emit_roadmap_validation` 观察式（无 suppress/authorize）；事件 `1 then 1`（去重生效） | 观察式、行为不变 | ⚠️ 测试级载体（**design 无 VC**，记债务 D-MDC-1） |
| Q-AC-011 | 派发判定与队列写入同临界区；同 `task_key` 不可能被两进程各 append？ | M-04 探针（PM 原位置亲跑 5 连×双入口）+ `test/test_write_face_dispatch.py`（30 passed）+ `test_mdc_e2e.py` VC-106 | 双入口均 `grants=1 refusals=1 rows=1 dispatch_events=1`；双真实进程 + 文件 barrier，锁未 mock；`test_rag_launcher.py` 旧断言由 PM 机械重修（合法作废路径） | 1 行 / 1 事件 | ✅ 充分 |
| Q-AC-012 | 在飞口径单源（一处导出谓词服务派发闸/面板等）？ | M-02 diff 审计 + M-03 复核 + 面板套件 | `_is_in_flight` 语义未改（M-02 diff 无该块）；`workerBelongsToKey`（TS `worker-store.ts:65-70`）与 `row_belongs_to`（`mw_common.py:2026-2034`）同形；`slotsUsed` 与 conductor key 层同口径 | 单源 | ✅ 充分 |
| Q-AC-013 | `advance.advance()` 不成为并发瓶颈，或给出等价实测量化？ | M-02 §6/附录 A、PM 复跑、`test_mdc_e2e.py` VC-109 | `advance` 事件 `data={"ms":n}`；`window_share` **0.9864 / 0.9906 / 0.9933**（三轮独立）、相对空 tick **70 / 74.67 / 184.33 / 257×** | 量化成立 | ✅ 充分（绝对墙钟受负载影响，见 ⚠️ D-MDC-2） |
| Q-VC-101 | 前沿恒等，≥3 组构造语料复算逐 tick 可重现？ | `test_mdc_concurrency.py` VC-101（4 条） | 逐组断言实起 = `min(上界,|F|)` | 恒等 | ✅ 充分 |
| Q-VC-102 | 链式依赖（前沿恒 1）时上界再大实起 = 1？ | `test_mdc_concurrency.py` VC-102 | `|F|=1→1` | 不放大 | ✅ 充分 |
| Q-VC-103 | 上界 = 1 时两层 ≤1 且无需重启 serve？ | `test_mdc_concurrency.py` VC-103 | `cap=1→1` + 热读 | 成立 | ✅ 充分 |
| Q-VC-104 | fail-closed：不可解析/悬空/环/未声明写面 → 实起 1 + 审计行？ | `test_mdc_concurrency.py` VC-104（4 条） | 串行 + 审计；重叠被拒不 `mark_stalled` | 成立 | ✅ 充分 |
| Q-VC-105 | N≥4 并行时同文件多写者对 = 0？ | `test_mdc_e2e.py::test_vc105_*`（PM 亲跑 5 passed） | 实起 5；`overlap_judgements=10`（`C(5,2)` 字面断言）；`collision_pairs=0`；`gate_none=5/5` | 0 对 | ✅ 充分 |
| Q-VC-106 | 注入并发下同 `task_key` 只 1 行？ | `test_mdc_e2e.py::test_vc106_*` 两条 | 双入口 `grants=1 refusals=1 rows=1 dispatch_events=1` + `duplicate-dispatch:` + `stalled_events=0` | 1 行 | ✅ 充分 |
| Q-VC-107 | 面板三量与 conductor 同快照复算一致？ | `autopilot-concurrency-panel.test.ts`（4 passed） | `eff === min(cap,|F|)` 双向；`slotsUsed` = key 计数（pending 1 / manual 0 / terminal 0 / mixed 2）；四个边界用例 | 一致 | ✅ 充分 |
| Q-VC-108 | 新增键默认值/取值域/校验两侧逐字段一致且语料冻结值更新？ | 定向 TS 36 passed + 语料具名用例 | 冻结值表逐字段对照；`requireCase` fail-closed（缺具名用例即抛，不静默跳过） | 一致 | ✅ 充分 |
| Q-VC-109 | `window_share` 实测 + N≥4 stall 量化？ | `test_mdc_e2e.py::test_vc109_*` + M-02/PM 两轮 | `[199,540,210]`/idle 3ms/`0.990605`/`70.00x`（PM）；`0.993323`/`184.33x`（M-06）；`0.995130`/`257x`（M-02） | 量化 | ✅ 充分（⚠️ D-MDC-2） |

## §2 汇总

- 问句总数 **22**；✅ 充分 **19**；⚠️ 不足 **3**（Q-AC-002b / Q-AC-008 / Q-AC-010，其中两条为同一 design 映射缺口）；❌ **0**。
- 阶段门禁：**无 ❌，⚠️ = 3 ≤ 3**，三条均已登记债务（D-MDC-1 / D-MDC-2 / D-MDC-3），故门禁**通过**。
- 失败集口径：全量 `python -m pytest -q` = `6 failed, 2222 passed, 10 deselected`，失败**集 == 基线 6 条**（新增失败 0，P-036 口径）。
- 定向 TS：`autopilot-config-parity` + `-sync` + `autopilot-console` 44 passed；`autopilot-monitor` 26 passed；`autopilot-concurrency-panel` 4 passed；`npx tsgo --noEmit` exit 0。`npm run check` exit 0（越面副作用见 §0.2）。

## §3 二次印证（独立复核，不复述 worker 结论）

1. **所有计数 PM 亲跑**：M-02 附录 A/B 探针（原位置重跑，含一次 PM 自造的假阴性并已定位为"探针被搬走后 `FRAMEWORK` 推导失效"）、M-04 双入口探针（5 连跑 ×2 入口）、M-05 TS/Py 套件、M-06 全部 5 条 + 原始 `[VERIFY]` 回放。
2. **代码逐点读证**（不靠 worker 自述）：`_timed_advance` / `_record_advance_result(ms=…)` / `_declared_write_face`（`dispatch_card` 是纯读者）/ `_emit_roadmap_validation`（观察式）/ `_stable_dependency_order`（环退化回计划序）/ identity 守卫（锁内、零副作用、单一 `_TERMINAL_STATUSES`、不再加锁）/ `_WRITE_FACE_WAIT_REFUSALS` 元组 + 注释。
3. **A/B 隔离法证伪两条红**：`test_autopilot_verdict_freshness` 用 `git show HEAD:...conductor.py` 换入隔离副本后**同形失败** ⇒ 与本 key 无因果；`test_rag_init` 单跑 12 passed ⇒ 幻影。
4. **测试改动是收紧而非放宽**：`test/test_write_face_dispatch.py` 两条对齐断言改为断言 `duplicate-dispatch:` 拒绝 + `task_md is None` + 恰好 1 行/1 事件（逐行读证）；竞态测试新增"恰好 1 grant / 1 refusal（非 `write-face-overlap`）/ 1 事件 / 1 行"。
5. **诚实性检查（禁项扫描）**：`test_mdc_concurrency.py` / `test_mdc_e2e.py` / `autopilot-concurrency-panel.test.ts` 对 `.skip(` / `.only(` / `.todo(` / `xit(` / `xdescribe(` / `pytest.mark.skip` / `xfail` **零命中**；期望值取自语料构造规模，未以被测公式自证。
6. **生产面零漂移**：M-06 的 mtime 全早于其启动时刻；本 key 的生产改动面 = `conductor.py` + `dispatch.py` + `config.py` + 新增 `task_graph.py`、`write_face.py`(WFG) + TS `status-model.ts`/`monitor.ts`（M-03）。

## §4 债务与遗留（不与遗留项混同）

- **D-MDC-1（映射缺口）**：AC-008 / AC-010 在 `design.md` 无 VC。改由测试级载体（`test_task_graph.py` 71 passed + 实测记录 + 观察式代码审计）承担。**未伪造 100% 覆盖**。
- **D-MDC-2（量测口径）**：`window_share` 的**绝对墙钟**受机器负载影响（208–554ms、70–257×），故只对 `exit==0` / `median≥idle` / `window_share>0.5` 做硬断言，判据取量级。
- **D-MDC-3（已量化未修）**：跨 tick 顶配（top-up）未开，AC-002 的边界已量化（`idle_slot_ticks=6`、边界额外空 tick 0）并判定可接受。
- 其余 10 条见 `achieved.md` §遗留（`dist/**` 重建、同步执行器决策、全量 TS 对照不可达、`npm run check` 越面副作用、基线 6 红、RF 重复激活、PM 回读推送缺口等）。
