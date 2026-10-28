# Achieved: mw-dynamic-concurrency

- Key: mw-dynamic-concurrency
- Completed: 2026-10-14
- Depends on: mw-write-face-guard（DONE 2026-10-14 15:04，写面判定先行的前置已满足，D-018）
- 范围：把 autopilot 的 key 层"静态上限 2"改成**依赖前沿驱动、按前沿动态最大化**，per-key 层同样由依赖前沿导出并落在配置上界内；写面判定先行；派发层 identity 去重。

## 系统行为变化

### 1. per-key 并发由依赖前沿动态决定

单 key 实起 worker 数 = `min(max_workers_per_key, |可并行任务前沿|)`（`autopilot/conductor.py` 的 per-key 上界 + `autopilot/task_graph.py` 的前沿）。原先没有任务级依赖图：同 key 的任务按"计划出现序 + 写面串行化"逐个起，per-key 上限是写死的 2。现在是解析任务卡头 `deps:` 得到依赖图，取出"依赖全部终态"的可并行前沿，再按配置上界截断。

### 2. 任务级依赖的载体与解析

新增独立解析器（`autopilot/task_graph.py`）：任务卡头一行 `deps:`（`-`/空 = 无依赖；逗号分隔任务 id，语法与 roadmap `depends_on` 同构）。**不复用** `card_audit._header_value`（实测 5/5 真实卡返回空串，因其 `_HEADER_RE` 在卡首 H1 处即 break）。id → 卡文件 stem 的 join 用"数字核心"规则（实测 146 个真实 dep token：stem 精确命中 0、既有 `_plan_task_file_stems` 命中 0、数字核心唯一命中 125）。

### 3. 依赖图校验与 fail-closed 回退

悬空 id / 自依赖 / 环 / 跨 key 引用被检测；任一问题、或任务卡不可读 ⇒ **该层整层回退串行**（实起 ≤ 1）并写审计事件。审计复用既有 `config` 事件通道 + 报警通道（**无新事件名**，事件词表冻结），并按 `(tasks dir, key)` + 问题签名去重，同一问题只播报一次，修复后复现才再次播报（避免 4s tick 洪泛）。

### 4. key 层依赖语义校验进入 tick

`_emit_roadmap_validation` 在 tick 内执行原本只有 CLI/doctor 做的 roadmap 校验（悬空/环/前向 stage）。**观察式**：不抑制也不授权任何派发，key 层 fail-closed 行为不变；同样按 `(path, problem)` 去重。

### 5. 派发层 identity 级去重（同 `task_key` 零副作用拒绝）

`autopilot/dispatch.py::dispatch` 在**已持有的 `workers.lock` 临界区内**（写面判定之后、`mkdir` 之前）判"同一 `task_key` 是否已有非终态行"：有则拒绝且**零副作用**（不建 taskDir、不写 task.md、不写队列行、不发第二个 `dispatch` 事件），reason 前缀 `duplicate-dispatch:`。终态旧行仍走 upsert 重派（重试路径不被封）。该拒绝被纳入"等待下一 tick"类（`_WRITE_FACE_WAIT_REFUSALS` 新增 `duplicate-dispatch`），故 `execute_loop` **不会** `mark_stalled`。这一条同时是 P-034 / RF-1..RF-4「同一 task_key 被重复激活」的**根修候选**：`upsert_worker_row` 按 `task_key` 无条件替换（不区分旧行是否在飞）正是其机制面。

### 6. advance 墙钟可观测（无新事件名）

`_timed_advance` 给 `advance.advance()` 计时，`_record_advance_result(..., ms=...)` 把毫秒放进既有 `advance` 事件的**可选 `data={"ms": n}`**（detail 句子是冻结线格式，未动）。由此得到 `window_share = Σadvance_ms / Σtick_ms`。

### 7. 配置语义与呈现

`max_parallel_keys`（默认 8，`[1, null]`）是 key 层上界；新增 per-key 上界 `max_workers_per_key`（默认 4，`[1, null]`），两侧（Python `autopilot/config.py` / TS `autopilot/status-model.ts`）默认值、取值域、校验行为逐字段一致。既有 materialized config 不因新增键变非法。autopilot monitor 同时显示配置上界与本 tick effective 并发：`cap` / `eff = min(cap, |前沿|)` / `frontier`，`slotsUsed` 为**key 计数**（与 conductor 的 key 层口径同一快照可复算一致）。

### 8. 反证与量化（B4）

- N≥4 并发安全：真实 `conductor.tick` 实起 5，从真实队列取在飞行、复用生产判定本体复算 `C(5,2)=10` 次**同文件多写者对 = 0**；逐行复跑真实 `_write_face_verdict` 5/5 不拒。
- 注入并发：双真实进程与 conductor stale-snapshot 入口均"1 grant / 1 refusal / 1 行 / 1 个 `dispatch` 事件"，`stalled_events=0`。
- 性能：`window_share` 实测 0.9864–0.9933、相对空 tick **70–184×**（三轮独立：M-02、PM、M-06）。
- 顶配空窗：批内 N 全终态后才补派；实测空窗 = straggler 剩余 runtime（tick 回合 2、`idle_slot_ticks=6`），批次边界的额外空 tick = 0。

## 遗留

1. **`dist/**` 已重建（2026-10-14 事后，用户驱动）**：`python mw.py build --install --allow-dirty` exit 0，重建了 `packages/multi-workers/dist/extensions/agent-team-loop.js`（sha256 `1D5184B8…6065F`）、全局 `~/.pi/agent/extensions/agent-team-loop.js`（同 sha）与 `packages/coding-agent/dist`；产物已确认含 `frontierSize`/`max_workers_per_key`/`WRITE_FACE`/`parseWriteFace`（建前全为 ABSENT）。建后 `test_rag_launcher` + `test_rag_init` 的红消失；**需重启 pi 窗口**才加载。详见 `.agenticdoc/_scratch/evidence/mdc-postbuild-status-20261014.md`。原遗留描述（运行时能力只在 `src` 生效、`mwds-t23` req-4 sha 红）保留为历史记录：`test/suite/mwds-t23-cutover-recheck.test.ts:46` 的 `EXPECTED_BUNDLE_SHA = 975D4066…` 与任何新构建都不同，其刷新属那个 key 的面；`test_mwds_t27`/`t29` 两条红经复跑定性为**测试侧 locale 解码缺陷**（`subprocess.run(..., text=True)` 缺 `encoding="utf-8"`，子进程打印中文时按 GBK 解码失败使 `proc.stdout` 变 `None`），与 dist 无关。
2. **跨 tick 顶配（top-up）未开**：任一在飞行仍使整 key 跳过 `_advance_key`（AC-002 边界）。已量化（见上）并判定"当前 tick 语义下可接受"（等长 runtime 批 makespan 不变，唯一损失是 straggler 期间 ≤cap-1 槽位空闲，有界）；**未改** `orchestrate`/`execute_loop` 的跳过逻辑。
3. **`advance.advance()` 仍是同步子进程**（120s 超时）。D-107 把执行器决策推给"一周现场量化"；本 key 已给出等价量化证据（AC-013）。若生产出现同 tick ≥4 次 advance 撞车再上独立执行器。
4. **全量 TS 对照未完成**：`./test.sh` 在本机**不可达**（`bash` 落到 WSL，本机未安装发行版，exit 1；见 P-032 复发记录）。已按 AGENTS.md 回落路径执行：包根**显式文件**套件（Py 2228 条全量 + TS 定向 44/26/4/36 + `npx tsgo --noEmit` exit 0）全绿，全量 pytest 仅"基线 6 红"。**不把定向绿说成全量绿**。
5. **`npm run check` 的越面副作用（自陈）**：该命令是全仓 `biome check --write`，本轮 `Fixed 10 files`，落点含别的 session 在写的 `worker/worker-mode.ts`、`shared/write-face.ts`、`pm/pm-orchestrator.ts`（仅格式化，exit 0 无残留，**未回退**以免破坏他人在飞工作）。已升为 P-017 [高危] 复发。
6. **AC→VC 映射缺口**：AC-008、AC-010 在 `design.md` 里没有对应 VC（`evidence-requirement.md` 如实披露，改由测试级载体承担：`test_task_graph.py` 71 passed + spec 记录的 5/5 旧解析器空串实测；M-02 §5 D 的原始事件 + 观察式代码审计）。
7. **M-04 守卫的未覆盖面**：identity 守卫只给 `_WRITE_FACE_WAIT_REFUSALS` 加了等待类条目，其余 dispatch 调用点（L3/repair/roadmap/phase-writer）未逐个接入"等待"分支；`parse_workers_file` 会丢弃不可解析行，故不可解析行无法参与 identity 判定（与既有写面闸同口径）。
8. **基线 6 条外部红**（非本 key，逐条归因已记）：`test_autopilot_readcap_injection`（外部 E2Feature 冻结副本，`MW_READCAP_BASELINE_DIR`）、`test_autopilot_verdict_freshness`（A/B 隔离证伪与本 key 无因果）、`test_launcher`/`test_task_type_parity`（另一 key `mw-dispatch-reliability` 的任务书缺失）、`test_mwds_t27`/`t29`（见遗留 1）。
9. **RF-1..RF-4 重复激活**：机制已定位（`upsert_worker_row` 无条件替换）、M-04 是根修候选，但**起这 12 个副本进程的组件仍未定论**（需现场捕获器）。证据 `.agenticdoc/_scratch/evidence/wfg-i03-duplicate-activation-20261014.md`（含追加实例 2）；需独立 key。
10. **PM 回读推送范围缺口**：`pm/pm-orchestrator.ts` 的 `notified.add` 早于 owner gate，终态结果可能不发推送。需独立 key（建议 `mw-readback-delivery-scope`），证据与复现已备。
