# 设计证据 — 自动反馈、精确关联与 dp25 直接签收（D-RQ2）

- Key: `mw-decision-context`；卡片 `tasks/D-RQ2-feedback-signoff.md`；对齐 spec AC-008–010/012–014/019–020。
- 方法：**只读静态源码扫描**（未运行、未改码、未起服务、未调模型、未读真实凭证）。行号为本次扫描位置，漂移按符号定位。
- 分级：`F*` = 当前静态事实；`R*` = 建议（未实现、未测试）；`P*` = 待决。
- 输入契约（四 DP 材料）归 RQ1，本文件只到"结果消费者 + 反馈写点"。

## 0 结论摘要

1. **关联键今天不存在**：`decision_id = <dp>:<trigger.resolved_id()>`（`decision_points.py:4617`，`resolved_id()` 见 `:250`），而 dp1/dp2/dp3 的 TS 生产者只发 `{state}`（无 `trigger_id`），state 里只有 `key`，`task_key` 为空 → 同一 key 内所有 dp1/dp2/dp3 决策**共享同一 decision_id**（`F1`–`F3`）。AC-010 的 task/角色精确关联、AC-012 的重试关联当前无载体。
2. **反馈链只有 reader，没有 writer**：`decision_wire.lifecycle_event`（`:1288`，字段 `lifecycle/target/supersedes/reason/answer/evidence/result`）与 `decide_archive.append_settle`（`:1074`）**生产调用点为 0**（全仓仅测试调用）；`decision_history` 已能折叠 `adopted/consumed/responded/steered/executed/signoff/settled`（`:1513`–`:1725`）。这正是 spec §4 "只有 reader 没有 writer" 的实例。
3. **推荐方案 A**：新增一个 Python 写入口（`mw decide lifecycle`），复用 schema v1 lifecycle 行 + 现有 reader/redactor，四个消费点各自调用；不新增 kind、不改 frozen archive 行、不改 `rows_sha256` 快照字段集。
4. **dp25 无需 PM 二批已经成立**（`mw.py:3945 _decide_sign` → 写文件 → 门禁通过，无人审）；**缺的是原子性与幂等**：先写文件再追加 `authority-change`（`mw.py:4086`→`:4101`），追加失败时文件已在、权威行缺失，且重复执行会再花一次模型调用、重写文件 `ts`、再追加一行（`F8`）。
5. **四状态**可由 append-only 折出，不需要新 schema：失败 / 处理中 / 处理完成 / 旧数据无状态（无任何 wire+lifecycle 证据）；dp25 的"处理完成"必须绑定 sign-final.md 实际校验通过（AC-014）。

## 1 当前事实：产物面 / 写者 / 读者 / 无写者行为

| 产物 | 路径 | 生产写者 | 读者 | 无写者时的实际行为 |
|---|---|---|---|---|
| decide 档案 | `.agenticdoc/_autopilot/decisions.jsonl` | `decision_points._archive_decision:3804` → `decide_archive.append_decide:953` | `decide_signoff.collect:286`、`decision_history.load_history`、门禁 `advance_phase._key_has_decide_rows:281` | 零行 = 无签收要求（门禁跳过） |
| authority-change 行 | 同上 | `mw.py:_decide_sign:4101`、`_dp_append_authority_change:1943` | `decision_history`（归档 authority 阶段） | 签收不再留权威行；`dp apply` 独立链路 |
| settle 行（结果相关） | 同上 | **无**（`append_settle:1074` 仅测试调用） | `decision_history`（`status`） | `status=pending`（`decision_history.py:33` 说明） |
| wire 事件（请求/返回/decision-end） | `.agenticdoc/_autopilot/decisions-wire.jsonl` | `decision_points._DecisionCapture._emit:3707`（`record_event`） | `decision_history.read_ledger_into:2464` | 无行 = 该决策无捕获证据（`capture_status` 只能由 outcome 报） |
| lifecycle 事件 | `.agenticdoc/_autopilot/decision-lifecycle.jsonl` | **无**（`lifecycle_event:1288` 仅测试调用） | `decision_history._build_stages:1545` → `_last_lifecycle:1505` | 各阶段 `StageFact(state="not-recorded")`（`:1542`） |
| 签收文件 | `<key>/evidence/review/sign-final.md` | `decide_signoff.write_signoff:664`（`mw.py:4086` 调用） | `advance_phase._decision_signoff_problems:309`、`decision_history._iter_signoff_keys:2168`、`mw.py:_dp_apply:3215` | 门禁 `MISSING` → `done` 阻断（若该 key 有 `kind=decide` 行且未 `signoff:disable`） |
| dp1 反馈 | `.agenticdoc/_autopilot/auto-decisions.jsonl` | `pm-orchestrator.recordDispatchAlarm:666`（行 `{seq,phase,kind,count,detail}`） | 人、`mw doctor` | 派发照常，无告警行 |
| dp1 关联头 | `<task>/task.md` 的 `decision:` 行 | `ui-bridge.mergeDecisionHeader:2309`（`acted` 且类型一致才写） | **无生产 reader**（注释称 settle 反查，未找到实现） | task.md 字节不变 |
| dp2 请求/回执 | `<task>/steer-dp2.md` + `<task>/trace.log` | `pm-orchestrator.writeDp2SteerRequest:2435`、`appendDp2ActedTrace:2476`；worker 消费 `worker-mode.consumeDp2NarrowSteer:3279` | 人、PM、worker 自身 | 不写 steer → PM 保留人工唤醒（`:2690` fallback） |
| dp3 回执 | `<task>/trace.log` | `worker-mode.attemptDp3Clarification:4162`、关联行 `:4235` | 人、PM 回读 | 走人工问路（3b） |

### 1.1 关键静态事实

- `F1` `decision_points.py:4617` `decision_id = f"{dp_point.id}:{trigger_obj.resolved_id()}"`；`:250` 回落顺序 `trigger_id → task_key → key → ts`。
- `F2` dp1：`ui-bridge.buildDp1DispatchState:529` 只写 `key`（无 `task_key`），`triage-client.triageDispatch:863` 发 `{state}`；单测夹具的 id 形状即 `<dp>:<key>`（`test/suite/triage-client-state.test.ts:582`）。
- `F3` dp2：`pm-orchestrator.decideDp2Checkpoint:2341` 发 `{state}`，`buildDp2CheckpointState` 明确"`task_key` 不是 dp2 字段，已移除"（`:2199`）。dp3：`worker-mode.decideDp3WorkerClarify:5652` 发 `{state}`，本地 id `<dp>:<taskKey>#nc<N>` 只在子进程返回前后用于 trace。dp25：`decide_signoff.auto_conclusion:381` 显式给 `trigger_id=<key>@<ts>`。
- `F4` `decide_archive._append_row:642`：幂等扫描**只对 `kind=="decide"` 且传了 `dedupe_decision_id`**（`:686`）；`append_authority_change:1115`、`append_settle:1074` 都不传 → 二者无去重。
- `F5` `decide_archive.append_decide:1010` `row["outcome"] = "pending"  # decide rows are never backfilled (Q4)`；`_NOT_APPLICABLE`（`:133`）把 settle/authority 字段在 decide 行置 None。→ **反馈/结果只能新增行，不能回填**。
- `F6` `decision_points._DecisionCapture._actor:3648` 仅在 `observation` 存在时返回 actor，生产决策恒 `None`；`origin="decide"`（`:4494`）不带角色。→ 发起角色无落点。
- `F7` dp1 反馈行无 `decision_id`：`recordDispatchAlarm:666` 行形状 5 键；`formatTriageLedgerDetail:969` 只写 `dp/triage_type/triage_risk/dispatched_type/disagreement/confidence_source`。
- `F8` `mw.py:_decide_sign`：`facts→auto_conclusion(:4019)→重读 facts→verdict→render→write_signoff(:4086)→append_authority_change(:4101)`；追加失败打印"sign file written … but the authority-change row failed"并 `return 2`（文件已落盘）。无"已签收"短路，重复执行会再调一次 dp25（`auto_conclusion` 每次新 `@ts` → 新 decide 行）。
- `F9` `decide_signoff.write_signoff:664`：`path.parent.mkdir(parents=True)` + `tmp.write_text` + `os.replace`，**不检查路径上是否有 symlink**；`decision_wire.append_event:1584` 用 `os.open(O_WRONLY|O_CREAT|O_APPEND)`，同样跟随 symlink（`_terminate_dangling_tail:1486` 亦是）。
- `F10` 读侧边界已有：`decision_history._inside(root_real, candidate)` 用于 sign-final.md（`:2168`）与 gates（`_read_gates:2201`）；`decision_wire.WireScope._refuse_production_paths:518` 对 test scope 同时校验给定路径与 realpath。
- `F11` 门禁：`advance_phase.py:309 _decision_signoff_problems` 控制流 = `disable?(:244) → _key_has_decide_rows?(:281) → 文件存在 → conclusion/counted_rows/rows_sha256 机器行 → collect 重算 sha → continue 时 verdict`；`GATES["done"]`（`:84`）另有 achieved/quality-gate/pm-state 规则，签收只是其中一条。
- `F12` dp3 的 PM→用户路径**无调用点**：`DP3_ID` 只出现在 `worker/worker-mode.ts`；`pm/` 下无 dp3 生产者（grep `DP3_ID|clarif`）。AC-005 的"两种路径"今天只有一种。
- `F13` `decision_history.STATUSES:156`（settle 词表 `pending/ok/rework/rollback/inconclusive/unknown`）已在主表使用（`decision_dashboard.js:333`）；新四状态不能复用它（AC-011 只允许 4 值，AC-015 要求原 status 留在日志详情）。

## 2 RQ-A 精确关联：decision / key / task / 发起角色

现状（`F1`–`F3`、`F6`）：`key` 有；`task_key` 对 dp1/dp2/dp3/dp25 全空；角色无。dp1/dp2/dp3 的 decision_id 退化为 `<dp>:<key>`，第二个检查点/派发/澄清会命中 `duplicate="existing"` 重放：**调用方拿到的是本次新答案，档案里留下的是第一次那行**（`_append_row:686` 返回旧行，`decide_for` 记 `note=duplicate-replay`）。这不是"精度不足"，是**档案失真**。

`R1` 不改 frozen 行结构（AC-002 只允许本地审计字段，且 `_ROW_FIELDS` 快照被 `rows_sha256` 覆盖，加字段会移动已签收文件的哈希）。三点落地：

| 关联 | 载体（建议） | 说明 |
|---|---|---|
| decision_id 唯一性 | 生产者显式传 `trigger_id` | dp2 用现成的 `<taskKey>#ckpt<N>`（`trend.total` 已算好，`pm-orchestrator.ts:2351`）；dp3 用 `<taskKey>#nc<N>`（`:5652`）；dp1 用 `<key>#d<seq>` 或 `@<ts>`；dp25 保持 `<key>@<ts>`。TS 侧只需在 envelope 顶层加 `trigger_id`（`{state, trigger_id}`）→ `mw.py:_decide_run:1011` 的 `Trigger.from_mapping` 已读 `payload["trigger_id"]`。 |
| task | 档案 `task_key` 列（已有、可空、`_validate_row:380` 允许 None） | dp1/dp2/dp3 的 state 里补 `task_key` **仅当该 dp 注册字段表接受**（dp2 明确不接受 → 改用 envelope 顶层 `task_key`，`Trigger.from_mapping(task_key=...)` 取 payload）。dp25 无 task 必须保持 NULL（AC-010 后半）。 |
| 发起角色 | `origin` 扩值 + `decision-end.actor` | `origin` 现为 `"decide"`（`:4494`）；建议 `decide:pm` / `decide:worker:<type>` / `decide:cli`，由 `mw decide run` 的 `--origin` 参数传入（TS 调用点各自传常量，Python 只校验枚举）。actor 走 `_actor()` 的既有通道，不为生产决策伪造 `human`。 |

`P1`（待决）：`task:` 头在不带 `PI_WORKER_TASK` 的 PM 决策里无来源，建议与 spec §1.5"PM 无 task 不强造"一致：留 NULL 并在 DAG 节点显示"未记录"，不反查最近 task。

## 3 RQ-B 四 DP 的真实结果消费者与反馈位置

| DP | 发起角色/调用点 | 真实结果消费者 | 今天写在哪 | 权限边界（不得扩大） |
|---|---|---|---|---|
| dp1 | PM（`ui-bridge.computeDispatchTriage:614`，`mw decide run` 子进程） | `triageDispatch:863` 解析 `triage_type/triage_risk` → `dispatchDecisionOf:291` → 只在 `mode=auto` 且类型一致时写 task.md `decision:` 头；不一致只告警 | `emitDispatchTriage:636` → `recordDispatchAlarm:666`（无 decision_id） | 只消费类型；**派发类型不由模型改写**（`buildDp1DispatchState:529` 固定 `requested_type`，`:542`）。反馈写入不得新增"改派"分支 |
| dp2 | PM（检查点 tick，`decideDp2Checkpoint:2341`） | 只允许 `narrow` 一个动作，且要 `mode=auto` + `min_confidence` + 存活探测（`:2426`、`:2690`） | `writeDp2SteerRequest:2435`（机器头带 `decision_id=`）+ `appendDp2ActedTrace:2476`；worker `consumeDp2NarrowSteer:3279` 写 `consumed=1 … marker=` | 只有 `narrow` 可执行；`split/direct/escalate` 一律回人工（`:2420`–`:2426`）。反馈写入不得执行任何动作 |
| dp3 | Worker（`attemptDp3Clarification:4162`）；PM→用户**无调用点**（`F12`） | `decideDp3WorkerClarify:5652` 的答案注入为 follow-up；每进程仅 1 次 auto（`dp3AutoAnswered:4149`） | `<task>/trace.log` 的 `[DECIDE]`/`[DECISION] dp3 acted=1 decision_id=`（`:4235`） | 只回执选择；不得写用户授权、不得执行工具调用 |
| dp25 | PM 窗口（`mw-runner` → `mw decide sign`） | `advance_phase._decision_signoff_problems:309`；`mw decide dp apply` 另读机器行 | sign-final.md 机器行 + `kind=authority-change` 行 | 可以收尾 → 直接写签收，**不得加 PM 二次批准**；继续完成/交用户确认 → 不写签收（AC-009） |

## 4 RQ-C 最小自动反馈事件协议

约束：接收 ≠ 行动 ≠ 结果；重试独立记录且关联前次；旧数据无 DAG；不造中心调度器、不加大 schema。

### 4.1 两方案

**方案 A（推荐）：复用 lifecycle 侧账本 + 单一 Python 写入口**
新增 `mw decide lifecycle --decision-id … --lifecycle consumed|executed|settled|signoff [--result <closed-vocab>] [--evidence <rel-path>] [--supersedes <decision_id>]`，内部 `decision_wire.production_scope(origin=…)` + `lifecycle_event:1288` + `append_event:1539`；TS 消费点用**已有的 `mw` 子进程通道**（与 `runDecideMw` 同形状）best-effort 调用。
- 优点：schema v1 与字段（`target`/`supersedes`/`result`/`evidence`）已在；`decision_history` 已折叠成 stage（`:1605`–`:1725`），DAG 10 节点无需再造；写侧 redact→clip→boundary-scrub 与 `WireScope` 隔离现成（`:447`、`:518`）；不触碰 frozen decide 行与 `rows_sha256`（`F5` 兼容）；零新增 kind，`LIFECYCLE_VOCAB:168` 不扩。
- 缺点：生产写者为 0，必须新增（并新增一个 CLI 子命令 → argparse/文档/测试面）；每次回执一次子进程（与 dp1 现有 `decide run` 同量级）；ledger 无 per-(decision,word) 去重（需在写入口做）；不在 `rows_sha256` 内，签收不覆盖反馈完整性。

**方案 B：写回 decide 档案（`kind=settle` + `kind=authority-change`）**
- 优点：单一权威链（`seq`/`prev_sha`/锁/`fsync`，`_append_row:642`）；`decision_history` 已读 settle 得 `status`；`decide_signoff.collect` 已在读档案，签收与反馈同源。
- 缺点：`append_settle` 字段只有 `outcome/settled_by/evidence_ref/note`，无法区分"已接收/已行动/已结果"三态而不借 `settled_by` 约定（隐性 schema）；`outcome` 词表是 settle 语义（`ok/rework/...`），把"接收"塞进去就污染 AC-015 的日志详情；写失败是 **fail-loud**（`DecisionArchiveError`）→ 可能打断派发/检查点业务路径；同样无去重；`_chain_ok` 覆盖全档案，新行会持续延长链（不破坏已签收 sha，但 `seq` 无界增长）。

**放弃的 C（记录在此以免回潮）**：继续写 `trace.log`/task.md 自由文本。无 schema、无 redaction 保证、dp1 侧无 decision_id 列（`F7`）→ 无法派生四状态，也无法 fail-closed。

### 4.2 事件草案（方案 A，字段全部为既有列）

| 词 | 何时写 | 必填 | 语义（不可合并） |
|---|---|---|---|
| `consumed` | 消费者**拿到并采纳**了答案（dp1 类型一致、dp2 注入 steer 成功、dp3 注入 follow-up、dp25 使用结论） | `decision_id`、`target=decision_id`、`actor`、`result`(closed: `adopted`/`injected`/`signing`) | = "接收签收"。**不代表动作已发生** |
| `executed` | 动作**真的执行完**（dp1 任务卡已写、dp2 steer 文件落盘、dp3 follow-up 已注入、dp25 签收文件已 replace） | 同上 + `evidence`(相对路径) | 与 `consumed` 分离；缺 `executed` 就显示"已接收未行动" |
| `settled` | 结果已知（dp2 worker 收窄后回读、dp3 后续轮次收敛、dp25 门禁通过） | `result`(closed vocab) | 只由真实回读产生，不由 PM 声明产生 |
| `signoff` | 签收文件写入成功 | `target`=key、`result`=`continue/narrow/revoke`、`evidence`=sign-final.md | 与 `consumed` 并行：AC-014 要求 dp25"处理完成"必须这一条为真 |
| `supersedes` | 重试时指向被替代的 `decision_id` | — | 重试关联，无需新行类型 |
| 写失败 | 不写行；返回 `WriteResult(status="failed", error_class)` → 调用方 trace 一行 | — | 三态都不成立，状态派生为"失败"，绝不伪造 |

writer/reader 表：

| 字段/通道 | writer | reader | 无写者行为 |
|---|---|---|---|
| `decision_id`/`target` | 消费点经 `mw decide lifecycle` | `decision_history` join（`:2528` 按 `decision_id` 归并） | 视为未关联，不进该次 DAG |
| `lifecycle` 词 | 同上（写入口校验 ∈ `LIFECYCLE_VOCAB`） | `_last_lifecycle:1505`（last wins） | 阶段 `not-recorded` |
| `result` | 同上（closed set；自由文本走 sanitizer） | `_lifecycle_stage:1513`（`sanitizer.text`） | `None`，不补 `""` |
| `supersedes` | 重试方 | `StageFact.supersedes` | 无前次关联 |
| 幂等 | 写入口在锁内扫 `(decision_id, lifecycle)` 命中即 `skipped` | `stats.lifecycle_events` | 重复回执不产生第二行 |

## 5 RQ-D dp25 直接签收：硬门、原子性、幂等、phase 集成

### 5.1 现行硬门（已逐条核对代码，`F8`/`F11`）

调用前：①`cfg.signoff_error` → 拒（`mw.py:3988`）；②`signoff=disable` → 不写；③`--dry-run` 只预览、零模型调用零写入（`F8`）；`auto_conclusion` 内部：④`cfg.is_configured`；⑤dp25 已注册；⑥dp25 `enabled`；⑦transport 可用/预算；⑧`REQUIRED_STATE_FIELDS` 齐（`signoff_state:340` 自足）；⑨state ≤2000B；⑩`min_confidence`；⑪答案 ∈ `CONCLUSIONS`（`:434`）。调用后：⑫`verdict:449`（词表、`chain_ok`、`continue` 需 `N≥1` 且每行 `transport/model/confidence_source = timi-decisions/jev-latest/api`，`allow_empty` 只放宽 N=0）。写：⑬`write_signoff:664` 原子 replace。

### 5.2 建议：调用前必需门枚举（只做"这次调用是否合法/这次写入是否安全"，**不做交付判断**）

| 门 | 判据 | 失败行为 | 今天 |
|---|---|---|---|
| G1 配置可签 | `signoff_error` 空、非 `disable` | 拒，exit 2，零调用 | 有 |
| G2 材料完整 | spec §1.3 四部分在本 key 事实里可取（目标、完成、证据(已验证/未验证分列)、未完成影响） | 拒，exit 2，**零 POST**（AC-020） | **无**（新增，归 RQ1 契约） |
| G3 事实可证 | `collect():286` 成功、`chain_ok`、`rows` 非空（或显式 `narrow/revoke`） | 拒 | 部分（在 `verdict` 之后才判） |
| G4 引擎一致 | 每行真 jev 三元组 | 拒 | 有（`verdict`） |
| G5 未重复签收 | sign-final.md 存在且 `(key, rows_sha256, conclusion)` 与本次一致、`verdict` 通过 | 打印 `already signed` exit 0，**零模型调用** | **无** |
| G6 写面安全 | `<key>/evidence/review/` 与 `sign-final.md` 的父链每级 `lstat` 非 symlink 且 realpath 在 key 内 | 拒，exit 2，不写 | **无**（`F9`） |
| G7 不越权 | 本命令不调 `decide_for(intent="act")`、不写 phase、不改 `decide-points.json` | 结构性 | 有 |

`R2` 明确反对：**不要**在调用前加"AC 全部达成/质量门通过"这类本地结论再请 Jev 复述——那是 AC-007 材料的一部分（由 PM 生成、模型判断），本地只保留能机器证明的门（G1/G3/G4/G5/G6/G7）。G2 只判"四部分是否都在"，不判其内容真假。

### 5.3 原子性与幂等（建议顺序，替换 `mw.py:4086`–`:4120`）

1. G1–G7 → 2. `auto_conclusion`（唯一模型调用） → 3. 重读 facts + `verdict` → 4. 渲染到 `sign-final.md.tmp` 并 `fsync` → 5. **先**追加 `authority-change`（`trigger_id=f"signoff@{key}@{rows_sha256[:16]}"`，`note` 单行写 `rows_sha256=<full>`；现在 `note` 只写 `signed_via=auto-decide`）→ 6. `os.replace(tmp, path)` → 7. `lifecycle_event(lifecycle="signoff", target=key, result=<conclusion>, evidence="evidence/review/sign-final.md")`。
- 5 失败：删 tmp，exit 2，无文件 → 门禁 `MISSING`（fail-closed，`F11`）。
- 6 失败：权威行已在、无文件 → exit 2 报失败；重试时 G5 不成立但权威行可提供结论 → **复用该行结论跳过模型调用**，只重试 4/6（幂等）。
- 7 失败：签收已成立（文件+权威行），只记 trace；不得把成功改判失败。
- 重复执行（已完成）：G5 短路 → 零模型调用、零新行、文件字节不变。

### 5.4 phase 门禁集成

- 签收不写 phase，也不改 `.agenticdoc/<key>/pm-state.md`；`done` 仍须 achieved/quality-gate/pm-state PASS（`F11`）。
- 门禁只重算 `rows_sha256`/`counted_rows` + `continue` 时 `verdict`；**反馈行不进 `_ROW_FIELDS`（`decide_signoff.py:105`）**，所以新增反馈不会使已签收文件失效（必须保持）。
- 反馈写失败**不得**让 `done` 变红；`done` 的唯一签收判据仍是文件+哈希。

## 6 RQ-E 四状态派生、旧数据、重试、失败点

派生为纯函数（reader 侧，输入 = archive 行 + wire 事件 + lifecycle 行 + sign-final.md 解析）：

| 输出 | 规则（按优先级） |
|---|---|
| `失败` | `available is False`（含 `escalated_reason`）；或 dp25 有结论行但 sign-final.md 缺失/`rows_sha256` 不符（写失败）；或该次唯一回执行是写失败记录 |
| `处理完成` | `available is True` 且（dp25：`signoff` 阶段为 recorded **且** sign 文件校验通过；dp1/dp2/dp3：`consumed` 或 `executed`/`settled` 阶段 recorded） |
| `处理中` | `available is True` 且无上述终态阶段（含仅 `suggested`） |
| `旧数据无状态` | 该 `decision_id` 既无任何 wire 事件也无任何 lifecycle 行 → 状态置空、**DAG 入口为 0**（AC-016），不推断链路 |

- `R3` 派生放 `decision_history`（新增 `processing_state` 字段，与既有 `status` 并存），监控主表只读新字段；`status` 退回日志详情（AC-015）。
- `R4` 旧数据判据的诚实边界：捕获失败的**新**记录也会落到"无 wire 行"，因此归为"旧数据无状态"；页面必须同时显示 `capture_status`/`archive` 事实，禁止把"无证据"写成"处理中"。`P2`：是否为此加一个 `capture` 节点状态（"未捕获"）由 PM 定，本证据不主张。
- 重试：新 `decision_id`（`F3`+`R1`）+ `supersedes` 指前次；原记录不改（append-only）。
- 幂等：decide 行靠 `dedupe_decision_id`（`F4`，只对 decide 生效）；反馈行靠写入口锁内 `(decision_id, lifecycle)` 去重；签收靠 G5 + `signoff@<key>@<sha16>`。

## 7 RQ-F 安全边界（仅本功能触及面）

- 写入必须注入不透明 redactor：`decision.credential_redactor`（`decision.py:1006`）+ `decision_points.command_known_secret_redactor:3383` / `known_secret_superset:3330`。不可伪造的 `CredentialSnapshot` 必须拒（`:3359` 已如此）。无 redactor → `WireScope.capture:532` fail-closed 省略正文。
- 新记录不得把 harness/进程原文写进公开面；`result`/`evidence` 走 closed set + 相对路径（拒绝绝对路径与 `..`），与 `claimReadScope` 的做法一致。
- symlink/父目录（本功能面）：写侧新增 G6（父链 `lstat` + realpath 在 key 内）；lifecycle 写入继承 `WireScope` 的 production 固定路径（`:220`/`:633`）但**当前 `append_event:1584` 会跟随 symlink**，写入口需在打开前 `lstat` 拒绝（`F9`）。读侧沿用 `_inside(root_real, …)`（`F10`），新 ledger 读路径同样先 realpath 再读。
- **hash/id 不是安全证明**：`captured_redacted_sha256` 只描述"存了什么"（`decision_history.py:105`），已知秘密命中时输出仍需 omit；`rows_sha256` 只防篡改，不防泄漏。

## 8 生产创建路径验收建议（不手填 fixture）

1. 真派发一个 coding 任务 → 同一 key 再派发第二个 → 断言档案出现**两条不同 decision_id** 的 dp1 行，且各自带 `task_key`/`origin=decide:pm`（AC-010/012）。
2. 让同一任务跨两个检查点 → 两条 dp2 行，第二条 `supersedes` 指第一条（AC-012 重试关联）。
3. dp25：真实 key 上 `mw decide sign` 成功 → `lifecycle signoff` + 权威行 + 文件；再次执行 → 零模型调用、文件字节不变（AC-008 幂等）；把 `evidence/review` 换成 symlink → exit 2 且无写入（AC-019/020）。
4. 反馈写失败注入（ledger 只读/被占用）→ 业务动作照旧完成，页面显示 `失败` 或"无回执"，不出现"已接收"（AC-014/020）。
5. 旧 key（本 key 之前 DONE 的 `mw-signoff-decide-only`）→ 列表可查、状态为旧数据无状态、DAG 入口数 0（AC-016）。
6. 全流程零真实凭证：临时 HOME + 合成 key + 读前 spy（spec §2.2）。

## 9 待决（交 PM）

- `P1` PM 无 `PI_WORKER_TASK` 时 `task_key` 留空 vs 取当前活跃 task：本证据主张留空（AC-010 明文）。
- `P2` "无 wire 行"是否单独显示"未捕获"而非"旧数据无状态"。
- `P3` 反馈写入口是 CLI 子进程（方案 A 推荐）还是 TS 直写（被否，因无锁/无 redactor/无 fsync）——若 PM 选后者的任何变体，必须有锁与 redactor，否则本证据判其不满足 AC-019。
- `P4` `origin` 扩值是否需要 registry/TS 双向常量（`decide-registry.generated.ts` 为生成物，改动需同步生成脚本）。
- `P5` dp3 PM→用户路径（`F12`）由 RQ1/RQ3 补生产者，本 RQ 只留反馈写点；不在此扩大 dp3 权限。
