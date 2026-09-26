# Design: 取证源优先级与证据快照绑定（AC-029 / D4）

> 角色：design 期（key `mw-autopilot-slot-capacity`，**只读**）。本文件是本卡**唯一写面**：未改代码、未答任何 gate、未写 FM/E2/JC 任何文件、未 commit（探测脚本只落在 `%TEMP%`）。
> 代码基线：`H:/git/Multi-Workers` HEAD `191a069a4e95bdcfb2a0bac88f800a566490c1a6`。RQ-12/RQ-14 的基线是 `4ef71e053`，本文件所有 `file:line` 已在当前 HEAD **重新核对**（未漂移锚点与漂移项见 §方法）。
> 数据快照：**2026-09-26T08:32Z**（复算实测；FM/E2 仍在跑，数字会随时间变，本文件所有数字附复算命令）。
> 边界：**已有诊断，本卡只做设计**。不做 AC-025（处置三分）、AC-026（呈现契约）、AC-030（防伪字段）的题；不重复 RQ-10/RQ-11/RQ-13。

## TL;DR

1. **证据源不是一个线性优先级问题**：这些源答的是**三个不同命题**——① 框架在磁盘上记录了什么（`l3-verdict.txt` / dossier verdict 列 / roadmap `key-status`），② 机器对**末轮**判定源复算出什么（`l3-verdict-provenance.json` / `_l3_resolve_source`），③ 项目声明"这条记录错了"（correction sidecar）。任何一个"单一优先级表"都会在真实数据上取反：FM `gui-shell-spike`（记录 `below` / 复算 `meets` / 人工 31/31）与 E2 `feature-l3-readcap-injection`（记录 `meets` / 复算 `below` / correction `below`）方向相反。⇒ 设计 = **先用 verdict-producing 源定 bind 终态值，再把 correction 作为单向 dispute 叠加**。
2. **框架自己的终态记录零绑定**：`l3-verdict.txt` 的内容只有 `meets\n` 或 `below\n`（值域 `_VERDICT_VALUES`，`conductor.py:672`），无 sha256、无 mtime 字段、无来源轮次、无 writer。dossier 的 `l3 verdict` 列（`_closure_dossier_md`，`conductor.py:744`）直接读它（`_l3_verdict`，`conductor.py:659`）。⇒ **dossier 是"最不可信源"的副本，却是 stage-close 门的唯一证据面**。
3. **已有可复用原语，缺口精确**：`l3-verdict-provenance.json`（`_l3_provenance_record` `conductor.py:1356` / `_persist_l3_provenance` `:1451`）带 `source_mtime_ns` / `anchor_path` / `anchor_mtime_ns` / `suspect`，**但不带 sha256**；correction sidecar 带 `original_sha256`（字节级绑定），**但框架对它零可见**（`grep -i correction packages/` 在 `autopilot/*.py` 与 `autopilot/*.ts` **零命中**）。
4. **覆盖面（实测，非引用）**：22 个 `l3-verdict.txt` / 3 项目；provenance **4 文件 / 6 记录 / 2-of-22 key**（另 2 文件属于尚无 verdict 文件的在飞 key），6/6 `suspect=false`（fail-closed 路径生产 **0 样本**）；correction **2/22 带 `original_sha256`、3/22 带任何 correction**（全在 E2，均为项目侧产物）。
5. **口径修正**：RQ-12 的 "6/22 与复算不一致" 按本卡复算是 **4/22 recompute≠record**（另 1 例 recompute==record 但 ≠人工 attestation，1 例为一致行）。本卡以 **4/22** 为设计输入并给出复算命令（§F0）。这是需要 design 期冻结口径的一项差异，不是笔误。
6. **快照绑定选型 = 每门独立 sidecar**（`<gates>/gate-NNNN.evidence.json`，与 gate frontmatter 解耦），conductor 在**建门**（`_create_gate`，`conductor.py:2159`）与**消费该门那一刻**（`_consume_answered_gates` `:316` / `_apply_stalled_approvals` `:2295` / `_apply_stalled_rejections` `:2363`）各写一份 `(path, sha256, mtime_ns, bytes)` 四元组；两份之差 = `changed[]` = "应答窗口内证据被改写"的机器判据（对应 RQ-14 的 **24/34 门**漂移）。写侧只在 Python；TS 只读、只镜像字段名（`status-model.ts`）。
7. **与 roadmap `done` 对账**：`claimed_done ∧ ¬bound_meets` ⇒ ① 告警 `evidence-reconciliation`（timeline + doctor + 面板），② **新**的 stage-close 转换前置（`_stage_closure` `:616`，现有判据只有 `status_of ∈ {done, closed-legacy}` `:628-630`）。**历史已闭合 stage 一律只 warn，不回退**（E2 Stage 2 今天必然命中：correction 在效 + `counted_as_done=false` + roadmap `=done` + stage `closed`）。
8. **迁移不改写历史**：不回填、不回写 dossier、不碰 `_DEP_SATISFIED`（`:56`）/`_consumed_gate_ids`（`:297`）/`_set_stage_status`（`:380`）。历史无快照 ⇒ `unbound`（如实显示，不报错）。只读面零写（复用既有契约注释 `_doctor_autopilot` "Read-only: it never creates a directory or a file"，`mw_common.py:2022`；`_l3_provenance_record` "Never writes"，`conductor.py:1373`）。
9. **交付 6 条机器可判 VC**（VC-D4-1..6），每条给判定式 + 验证层级 + 真实数据反例 + 反向用例；含 1 条"证据记录被带外改写且无痕"的真实命中（E2 三个 key 于 `2026-09-24T16:47:33Z` 被批量改写，`l3-verdict` 事件 **0 条**）。

## 决策问题

1. **证据源清单**：与"结论是否达成"相关的证据源有哪些？逐个给**谁写**（`file:line`）、**何时写**、**当前是否带 sha256/mtime 绑定**（真实样例字段与值）、**覆盖实测**。
2. **优先级与冲突规则**：不一致时哪一侧赢？fail-closed 还是取高优先？给理由与**反例**（必须双向：记录偏高与记录偏低都要覆盖）。
3. **快照绑定设计**："应答时刻的证据快照"如何记录（`path + sha256 + mtime` 三元组）？载体选型（gate 文件字段 / 独立 sidecar / ledger）、字段名、写入点 `file:line`、**两侧镜像面**（Python `gates.py` + TS `status-model.ts`）。
4. **与 roadmap `done` 的对账**：何时必须告警、何时必须拦住 stage 收口？告警面（timeline 事件名 + doctor/面板字段）？修法选项 ≥2（给 pros/cons，不要求选一个）。
5. **迁移**：既有项目（FM/E2/JC 的历史 gate 与已闭合 stage）如何在不改写历史记录的前提下接入？
6. **VC 候选**：≥3 条机器可判、每条给判定方式与验证层级。

## 调研方法与出处

### 代码锚点（只读；行号 = HEAD `191a069a`，本文件逐条 `Select-String` 核对）

| 面 | 位置 | 与本卡的关系 |
|---|---|---|
| gate 12 字段 schema / kind / status 闭集 / fail-closed | `autopilot/gates.py:68-81`（`FRONTMATTER_FIELDS`）、`:54-61`（`GATE_KINDS`）、`:63`（`GATE_STATUSES`）、`:86-89`（`_REQUIRED_FIELDS`）、`:347`（`unknown frontmatter field`） | 新增 gate **frontmatter** 字段必须两侧同改且 fail-closed ⇒ 快照不走 frontmatter 的理由 |
| gate 文件命名闭集 | `gates.py:91`（`GATE_FILE_RE = ^gate-(\d+)\.md$`）、`:256`（`_next_seq`）、`:496`（`enumerate`）；TS `status-model.ts:600`/`:750`、`monitor.ts:260` | 证明 `gate-NNNN.evidence.json` 旁挂文件**不会被三个读取面当成门** |
| gate 创建 / 渲染 / 解析 | `gates.py:262`（`create`）、`:159`（`_gate_file_content`）、`:463`（`parse`）、`:509`（`pending_gates`） | 快照 sidecar 的写入点与同构实现位置 |
| gate 应答（只改 4 行；`answeredAt` 可 override） | `gate-writer.ts:139`（`answerGate`）、`:146-147`（`answered_at`/`answered_by` 替换）、`:101`（`rewriteAnswerFields`） | 快照**不得**由应答者写（AC-030） |
| 消费 / 门有效状态 | `conductor.py:297`（`_consumed_gate_ids`，正则 `(gate-\d{4})\b`）、`:316`（`_consume_answered_gates`）、`:2295`（`_apply_stalled_approvals`）、`:2363`（`_apply_stalled_rejections`） | 快照 `reason=consumed` 的写入点 |
| stage 状态机 | `conductor.py:380`（`_set_stage_status`）、`:409`（`_ensure_next_stage_gate`）、`:616`（`_stage_closure`）、`:628-630`（终态集 `("done","closed-legacy")`）、`:635`（`if not dossier.is_file()`）、`:638-641`（`dossier.write_text`）、`:650`（建 stage-close 门） | 对账拦截面 + "重放复用旧 dossier"的根因 |
| 终态裁决记录 | `conductor.py:659`（`_l3_verdict`）、`:672`（`_VERDICT_VALUES`）、`:675`（`_persist_l3_verdict`）、`:712`（`l3-verdict` timeline 事件）；调用点 `:1634`/`:1663`/`:1722`/`:1736`/`:1855` | 本卡的核心"低绑定源" |
| dossier | `conductor.py:722`（`_closure_dossier_md`）、`:744`（verdict 列 = `_l3_verdict`） | 最不可信源的副本 |
| provenance guard（现成原语） | `conductor.py:1223`（`_l3_fail_marker_line`）、`:1246-1248`（`_PROVENANCE_FILENAME`/`_PROVENANCE_SLACK_SEC=60.0`）、`:1251`（`_l3_source_paths`）、`:1274`（`_l3_resolve_source`）、`:1292`（`_l3_round_verdict`）、`:1356`（`_l3_provenance_record`）、`:1451`（`_persist_l3_provenance`） | 快照绑定应复用的形态与写入纪律 |
| done 前置 | `conductor.py:1507`（`_done_credentials_present`：要求 `l3-verdict.txt=meets`）、`:2240`（`_mark_key_done`）、`:2259`（roadmap `done`） | 证明 roadmap `done` 是 S1 的**派生值** ⇒ correction 一改，roadmap 就与证据脱钩 |
| sha256 原语（别重造） | `conductor.py:3200`（`_xkey_sha256_bytes`）、`:3204`（`_xkey_file_sha256`）；xkey ticket 已有 `authorization_snapshot`/`target_file_sha256`（`:2691-2698`） | 快照哈希实现 |
| roadmap 解析/校验 | `roadmap.py:53`（`STAGE_STATUSES`）、`:63`（`KEY_STATUSES`）、`:367`（`validate_roadmap`）、`:479`（`dependency_graph`）、`:492`/`:505`（覆盖写 helpers）、`:50`（`roadmap_check.py:50` 是唯一调用点，conductor 不调用） | 对账读面 + key-status 历史不可回读 |
| timeline | `timeline.py:67-85`（`EVENT_TYPES`）、`:93-94`（10MB / 2 代轮转）；TS `status-model.ts:779`（`EVENT_TYPES`） | 新事件名必须两侧同改；轮转会剪掉消费记录（AC-028） |
| 只读面 | `mw_common.py:2022-2024`（`_doctor_autopilot` 契约 "Read-only: it never creates a directory or a file"）、`:2067`（`_doctor_issues`）、`:2177`（`report["autopilot"]`）；`monitor.ts:122`（`MonitorAutopilot`）、`:150`（`scanPendingGate`）、`:186`（`readMonitorState`）、`:463`（`deriveAutopilotPanel`）、`:604-626`（attention 行）、`:645-653`（gate 行）、`:61`（`MONITOR_LINE_MAX=110`）；`console.ts:182-198` | 迁移的"零写"契约与新增字段的落点 |
| 状态 JSON 版本面 | `status-model.ts:1009`（`STATUS_SCHEMA = "autopilot-status/1"`）、`:1055`（`AutopilotStatus`）、`:1035`（`GateView`） | 新字段是否进版本面的取舍 |

### 数据（只读；3 项目，快照 2026-09-26T08:32Z）

| 项目 | 根 | gate 文件 | 已答 | `l3-verdict.txt` | `l3-report.md` | provenance | correction sidecar | 备注 |
|---|---|---|---|---|---|---|---|---|
| JC | `H:\git\JCodingAss` | 8（6 已答 + 2 pending） | 6 | 4 | 4 | **0** | 0 | 无 `.git`；stage 1 因 gate-0008 重放由 `closed` 退回 `running` |
| FM | `E:\CLI_workspace\FeatureMigrator` | 10 | 10 | 7 | 7 | **2**（`gui-live-monitor`、`gui-run-control-hitl`） | 0 | 两个 provenance 文件所属 key 尚无 `l3-verdict.txt`（在飞） |
| E2 | `H:\git\E2Feature` | 18 | 18 | 11 | 11 | **2**（`feature-false-meets-remediation`、`feature-gui-time-mvp-board`） | **3 key**（其中 2 个带 `original_sha256`） | Stage 3 running |
| 合计 | — | **36**（34 已答） | 34 | **22** | **22** | **4 文件 / 6 记录** | **3 key / 5 文件** | 见 §F1 覆盖列 |

### F0 复算命令（全部只读、可复现）

1. **证据漂移 = 24/34**（本卡复算命中，与 RQ-14 同值）：
   对每个已答门取 `newest = max(mtime(<key>/{l3-verdict.txt,l3-report.md,achieved.md,workers/*/{output.md,report.md,worker.log}}))`；stage 级门取 `_autopilot/stages/stage-<N>-close.md`；判 `newest > answered_at` ⇒ `answered=34 drift=24`（`now_utc=2026-09-26T08:32:22Z`）。逐门命中：JC 4（gate-0001/0003/0004/0006）、FM 4（0001/0002/0003/0006）、E2 16（见 §F0.2 列表）。
2. **recompute ≠ record = 4/22**（本卡复算；口径见 §数据缺口 G6）：
   `N = max(现存 ap-<key>-l3-a<k> 编号)`；`recompute = conductor._l3_resolve_source([(p,_l3_read_source(p)) for p in _l3_source_paths(key_dir, task_key) if readable])[0]`；与 `l3-verdict.txt` 比对。命中：`FM/gui-shell-spike`（`meets` vs `below`）、`FM/gui-contract-mock-tests`（`below` vs `meets`）、`E2/feature-l3-readcap-injection`（`below` vs `meets`）、`E2/feature-sampling-human-channel`（`below` vs `meets`）。**该脚本用的是 `_l3_resolve_source`（`conductor.py:1274`）；conductor 的完整轮求值入口是 `_l3_round_verdict`（`:1292`），它多一道 worker 状态门（`failed`/`needs-clarification` ⇒ `no-verdict`）。两者都**不会**给出 `meets`，故 fail-closed 结论不受影响。**
3. **provenance / correction 覆盖**：`glob(**/l3-verdict-provenance.json)` = 4；`grep '"suspect": true'` 命中 **0**；`glob(**/*correction*.json)` 中带 `"original_sha256"` = **2**（`feature-l3-readcap-injection`、`feature-sampling-human-channel`），任一 correction = **3 key**（多 `feature-inline-marker-patchkit`，只有 `achieved-correction`）。
4. **correction 字节绑定校验**：`sha256(H:\git\E2Feature\.agenticdoc\feature-l3-readcap-injection\l3-verdict.txt)` = `1e01e3da4a54438288d5e205b7aa535dd8e34c3eb6c3e0e9b2d1ff829f1417d2` **逐字等于** sidecar 的 `original_sha256` ⇒ 该 correction **在效**（CR-4 的判据在真实数据上可判）。同文件 `l3-report.md` sha256 = `6d07d711822f73465cbf59a38adda9c2d10f060eef29ca7abede9dc32c2908b2`，等于 sidecar `evidence_source.sha256`。
   E2 `feature-l3-readcap-injection` 的 correction sidecar **逐字节核对过的节选**（文件 `H:\git\E2Feature\.agenticdoc\feature-l3-readcap-injection\l3-verdict-correction-fm-136c65a70b2b.json`；字段值逐字，仅删去与本节无关的 `fv_version`/`fv_schema_version`/`generated_at`/`evidence_source_path`/`evidence_source_sha256` 冗余副本）：
   ```json
   {
     "run_id": "fm-136c65a70b2b", "key": "feature-l3-readcap-injection",
     "ledger_items": ["VC-006"], "dispositions": ["pending-authorization"],
     "counted_as_done": false, "kind": "verdict-value-correction", "correction": "value",
     "original_value": "meets",
     "original_sha256": "1e01e3da4a54438288d5e205b7aa535dd8e34c3eb6c3e0e9b2d1ff829f1417d2",
     "corrected_value": "below",
     "recorded_path": ".agenticdoc/feature-l3-readcap-injection/l3-verdict.txt",
     "corrected_basis": "landed recompute verdict (same run_id)",
     "evidence_source": {"path": ".agenticdoc/feature-l3-readcap-injection/l3-report.md", "sha256": "6d07d711822f73465cbf59a38adda9c2d10f060eef29ca7abede9dc32c2908b2", "exists": true},
     "owner": "用户/PM",
     "unlock_condition": "授权补一轮 L3 复评（底层修复已落地，尚未复评）"
   }
   ```
   同 key 的 `achieved-correction-fm-136c65a70b2b.json` 给出 `recorded_verdict_value: "meets"` / `corrected_verdict_value: "below"` / `counted_as_done: false` / `zero_write_policy: "achieved.md is a protected record: it is never rewritten by this key; the correction is carried by this sidecar only"` / `rewrite_request.status: "pending-authorization"`。⇒ "correction 声称记录错、但项目选择零写" 这一语义**在盘上有原文**，可直接作为 O4 的输入契约。

5. **writer 可归因性 = 15/22 缺失**：对每个 `l3-verdict.txt` 的 mtime，在 `_autopilot/timeline.jsonl*` 中找同 key 的 `config` 事件 `detail` 以 `l3-verdict ` 开头且 `|ts-mtime| < 120s`；**无命中 15/22**（JC 4/4、FM 4/7、E2 7/11）。E2 最早的 `l3-verdict` 事件是 `2026-09-25T06:48:30+00:00`，而存活 timeline 最老一行是 `2026-09-22T03:35:07+00:00` ⇒ 缺失是"写入早于该事件类型上线"，**不是**轮转剪代；JC 则 0 条 `l3-verdict` 事件。
6. **无痕带外改写（真实命中）**：E2 `feature-mvp-closeout` / `feature-params-service` / `feature-tier-a-closeout` 三个 `l3-verdict.txt` 的 mtime **同为 `2026-09-24T16:47:33Z`**（`.197087` / `.198120` / `.199159`），该时刻 `timeline.jsonl.1` 的 `seq 65820-65829` **全部是 `beat`**，无任何非 beat 事件；三者的 `l3-report.md` 同刻被改写（`feature-params-service` 现 7130B，而 E2 `gate-0003` 的 note 原文记录当时是 "`l3-report.md` 为空壳 181B"）。归因链**不在框架侧**而在项目侧：`H:\git\E2Feature\.agenticdoc\feature-l3-verdict-freshness\evidence\exec-l3-verdict-freshness-remediation-20260924.json` 的 `generated_at = "2026-09-24T16:47:33Z"`、`captured_by = "remediate_stale_l3_verdicts.py"`、`writer = "autopilot.conductor._persist_l3_verdict (T-002) ; st=None"`、`changed_files = 6`、`keys_stale_before_count = 3`；同目录 `achieved.md` 亦声明 "`keys_stale` 3 → 0"。⇒ `st=None` 使 `_persist_l3_verdict`（`:711` 的 `if st is not None`）**静默跳过** `l3-verdict` 事件 ⇒ 框架侧零痕。

## 发现

### F1 证据源表（10 源；"谁写 / 何时写 / 绑定 / 覆盖"）

> 判据：**绑定** = 该源自身是否携带"它描述的那份字节"的 `sha256` 与/或 `mtime` 与/或"它是谁写的"。**框架可见** = coordinator/doctor/面板/TS 是否会读它。行内所有值均为实测（快照 2026-09-26T08:32Z）。

| # | 源 | 谁写（`file:line`） | 何时写 | 绑定（真实样例字段与值） | 覆盖实测 | 框架可见 |
|---|---|---|---|---|---|---|
| **S1** | `<key>/l3-verdict.txt` | `conductor._persist_l3_verdict`（`conductor.py:675`），调用点 `:1634`/`:1663`/`:1722`/`:1736`/`:1855` | 仅该 key 的 **L3 终态事件**（done-meets / stall-below / no-verdict / suspect / repair 耗尽）；内容幂等（同值零写） | **无**。内容 = `meets\n` 或 `below\n`（值域 `_VERDICT_VALUES` `:672`）。唯一样例：`H:/git/E2Feature/.agenticdoc/feature-l3-readcap-injection/l3-verdict.txt` = `meets`，sha256 `1e01e3da…`（该 sha 只在**项目侧** sidecar 里出现） | 22/22 key 有文件；**4/22** 与末轮复算不一致（§F0.2）；**15/22** 无 `l3-verdict` 事件可归因 writer（§F0.5） | ✔（`_l3_verdict` `:659`、`_done_credentials_present` `:1507`） |
| **S2** | `<key>/l3-report.md` | 同 `_persist_l3_verdict`（`conductor.py:675`，`:704-710` 逐字节复制 deciding source） | 同 S1 | **无**（不记来源轮、不记 sha、不记 mtime） | 22/22；`feature-params-service` 现 7130B 而 gate 时是"181B 空壳"（§F0.6） | ✔（`_l3_verdict` 只把它当"存在则给路径"，`:663-667`） |
| **S3** | `<key>/l3-verdict-provenance.json` | `_persist_l3_provenance`（`:1451`）由 `_l3_provenance_record`（`:1356`）产出；调用 `:1649-1653` | 每个**有可读判定源**的 L3 轮（append-only，按 `task_key` 去重；损坏文件**不覆盖** `:1467-1476`） | `source_mtime_ns` + `anchor_path`（同轮 `trace.log`）+ `anchor_mtime_ns` + `suspect` + `raw_verdict`/`verdict` + `fail_line` + `recorded_at`；**无 sha256**。样例：`E2/feature-gui-time-mvp-board` 第 2 条 `{"round":"l3-a5","task_key":"ap-feature-gui-time-mvp-board-l3-a5","deciding_source":"workers/.../l3-a5/report.md","source_mtime_ns":1790404873879630600,"anchor_path":"workers/.../l3-a5/trace.log","anchor_mtime_ns":1790404907249918200,"suspect":false,"reasons":[],"raw_verdict":"meets","verdict":"meets","fail_line":null,"recorded_at":"2026-09-26T06:41:55Z"}` | **4 文件 / 6 记录**；相对"有 verdict 文件的 key"是 **2/22**（另 2 文件属于尚无 verdict 的在飞 key）；**6/6 `suspect=false`**、`reasons=[]` | ✔（仅 conductor 内部；doctor/面板**不读**） |
| **S4a** | `<key>/l3-verdict-correction-*.json`（值纠正） | **项目侧**工具链（E2 `feature-false-meets-remediation`）；框架 0 写点 | key 的纠正轮（本项目一次性） | `original_value`/`original_sha256`/`corrected_value`/`counted_as_done`/`dispositions`/`ledger_items`/`corrected_basis`/`evidence_source{path,sha256,exists}`/`unlock_condition`/`owner`；`generated_at` 是**声明值**（两条都是 `2026-09-25T00:00:00Z` 占位，真实写时刻是文件 mtime） | **2/22** 带 `"original_sha256"`；两条的 `original_sha256` **仍与当前文件逐字相等** ⇒ 在效 | ✘（`grep -i correction` 在 `autopilot/*.py` 与 `autopilot/*.ts` **0 命中**） |
| **S4b** | `<key>/achieved-correction-*.json`（文书纠正） | 同上 | 同上 | `original{path,exists,bytes,sha256}`/`recorded_verdict_value`/`corrected_verdict_value`/`zero_write_policy`/`rewrite_request{status,owner,unlock_condition}`/`counted_as_done` | **3/22** key 有任一 correction（多 `feature-inline-marker-patchkit`） | ✘ |
| **S5** | `_autopilot/stages/stage-N-close.md`（dossier） | `_closure_dossier_md`（`:722`），由 `_stage_closure` 在 `:638-641` 写；**仅当文件不存在**（`:635`） | stage 首次收口那一刻；重放收口**复用旧文件** | **无**（列 `key/final phase/l3 verdict/l3 report/evidence`；`generated_at` 是自声明时间）。样例：`E2/_autopilot/stages/stage-2-close.md` 行 `| feature-l3-readcap-injection | DONE | meets | …l3-report.md | …achieved.md |`，而同文件末尾由项目侧追加的 correction 块写 `l3-verdict.txt corrected value = below` + `counted_as_done = false`（同文件自相矛盾，机器可判） | 全部已闭合 stage 各 1 份（FM 1 / E2 2 / JC 1）；verdict 列 = S1 的副本 | ✔（人读；conductor 不读） |
| **S6** | `_roadmap.md` `> key-status:` / `> status:` / `> goal:` | `_mark_key_done`（`:2240`/`:2259`）、`_apply_stalled_approvals`（`:2340`）、`_apply_stalled_rejections`（`:2381`）、`mark_stalled`（`:3961`）、`_set_stage_status`（`:380`/`:396`） | 终态/停滞/恢复/收口时 | **无**（覆盖写，历史不可回读）。样例：`E2/_roadmap.md` Stage 2 → `> status: closed` + `> key-status: … feature-l3-readcap-injection=done …` | 22/22 key 在 `key-status` 中 | ✔（`roadmap.load_roadmap`） |
| **S7** | gate 文件（`question`/`context_refs`/`note`/`answered_at`/`answered_by`） | 问题与 refs：`_create_gate`（`:2159`）→ `gates.create`（`gates.py:262`）；应答：`gate-writer.ts:139` **或手改**（`gates.py:1-20` 明文"Manual file edits are equally legal answers"） | 建门 / 应答 | **无防伪**：`answered_at`/`answered_by` 应答者可写（`gate-writer.ts:146-147` 允许 override）；RQ-12 实测 E2 `gate-0007` 早 4.1h、FM `gate-0002/0003` 晚 104s；`answered_by` 34 门 4 种自由写法 | 36 文件 / 34 已答 | ✔（`gates.enumerate`、TS `listGates`） |
| **S8** | `<key>/achieved.md`、`<key>/evidence/quality-gate-report-*.md`、`<key>/pm-state.md` PASS 行 | `_done_transaction` `:1860`（achieved）、`:1836-1843`（qg report，**已存在则复用最早一份**）、`_append_pass_line` `:1763`/`:1889`（pm-state PASS）、`mark_stalled` `:3980+`（遗留草稿） | done 事务 / stall | **无**。`_done_credentials_present`（`:1507`）只判"`l3-verdict.txt=meets` + report 非空 + 有 qg 文件 + achieved ≥200B + pm-state 含 `PASS` 子串" | qg 文件 80 个 / 22 key | ✔（done 前置） |
| **S9** | `_autopilot/timeline.jsonl*` | `st.timeline.append`（conductor / TS 侧 `gate-answered` 由 conductor 写） | 每次状态改变 | append-only + 单调 `seq`；但**会轮转**（`timeline.py:93-94`：10MB / 保留 2 代）⇒ 消费记录可被剪掉（AC-028 的 JC 实证） | E2 存活 2 代（seq 1..80243 / 80244..97654）；`l3-verdict` 事件 9 条（E2）、3 条（FM）、**0 条（JC）** | ✔ |
| **S10** | `build-runs/verdict/write-journal-<run>.jsonl`（E2 项目侧） | 项目工具链（`producer: correct/ledger/disclose`） | 每次纠正写盘 | **最强绑定**：`path`/`op`/`producer`/`run_id`/`sha256_before`/`sha256_after`/`bytes_before`/`bytes_after`/`generated_at`（真实样例见 `H:\git\E2Feature\build-runs\verdict\write-journal-fm-136c65a70b2b.jsonl` 第 2 行） | E2 单 run 16 行 | ✘ |

**F1 结论（3 条）**

- **R1：真正带字节级绑定的只有项目侧产物（S4/S10）+ 框架侧未来的 S3 扩展**；框架自身的终态记录（S1/S2/S5/S6/S8）**全部零绑定**。而 stage 收口的唯一机器判据（`_stage_closure` `:628-630`）读的正是 S6，dossier 的 verdict 列读的正是 S1 ⇒ **当前"stage 是否可收口"的判定链上没有任何一环可自证**。
- **R2：绑定缺口不是"字段缺失"而是"写入路径不闭环"**：`_persist_l3_verdict` 在 `st=None` 时静默跳过事件（`:711`），真实发生过（§F0.6，3 个 key / 6 个文件）⇒ 即使补了 sha256 字段，**只要存在"绕过审计的调用路径"，绑定仍可被绕过**。设计必须让"落盘"与"留痕"原子化（F3）。
- **R3：三个命题必须分开取源**（TL;DR 1）。把 S1..S10 塞进单一优先级表会在真实数据上取反；正确形态 = **verdict-producing 的 fallback 顺序 + dispute 覆盖层**（F2）。

### F2 优先级与冲突规则

**命题分解**

| 命题 | 含义 | 主源 |
|---|---|---|
| `Q-record` | 框架在磁盘上把该 key 的终态裁决记成了什么 | S1（→ S5、S6 派生） |
| `Q-recompute` | 对**末轮**判定源按现行解析器重算，结果是什么 | S3、`_l3_resolve_source`/`_l3_round_verdict` |
| `Q-claim` | 项目/人声明"这条记录是错的" | S4a/S4b（correction）；S7 的 `note` 只作 attestation 展示 |

**verdict-producing fallback 顺序（用于 `Q-record`/`Q-recompute` 的 bind 终态值 `V_bound`）**

| 优先 | 源 | 生效条件 | 理由 |
|---|---|---|---|
| P1 | **S4a correction（in force）** | `original_sha256 == sha256(当前 S1)` 且（`corrected_value != original_value` 或 `counted_as_done == false`） | 唯一"绑定被纠对象字节"的源；语义**单向**（只能把 meets 降为 below） |
| P2 | **S3 provenance 末轮** | `record.round == max(现存 ap-<key>-l3-a<k>)` 且 `suspect == false` | 框架自产、带同轮 `trace.log` 锚 mtime；但**只覆盖 2/22 key** |
| P3 | **末轮复算** | `_l3_round_verdict`（`:1292`）可判 | 与现行判定逻辑同源；口径已冻结（`_L3_SOURCE_ORDER = ("output.md","report.md")`） |
| P4 | **S1 `l3-verdict.txt`** | 存在 | 现行 dossier/roadmap 的实际输入；**§F0.5 实测 15/22 归因失败** |
| P5 | **S5 dossier verdict 列** | — | = P4 的副本，无独立信息（`_l3_verdict` `:744`） |
| P6 | **S7 `note` / 人工 attestation** | — | 只展示、不参与计算（RQ-14 D6；`answered_at` 应答者可写） |

**冲突规则（CR）**

- **CR-1 值层 = 可信源取最小（fail-closed）**：`credible = {P2 provenance 末轮, P3 末轮复算, P4 l3-verdict.txt}` ∩ 可用。① `credible` 为空 ⇒ `indeterminate`；② 全一致 ⇒ 该值；③ 不一致 ⇒ `min(below < meets)`（即 `below`），标 `confidence=disputed`。理由 = 成本不对称：误 `below` 的代价是 +1 轮（`_resume_credits` `:2273`，由人工 approve 授予，可逆）；误 `meets` 的代价是 roadmap `done` → `_DEP_SATISFIED`（`:56`）→ **解锁依赖 + 放行 stage 收口**，且 `_set_stage_status`（`:380`）**非单调**（JC 已实测 `closed → running`）。
- **CR-1b（值层 ≠ 自动放行层）**：值层取最小只决定"**不允许自动判定为达成**"，它**不**宣称记录为假。反例：FM `gui-shell-spike` 的值层为 `below`（record `below` vs 复算 `meets`），但人工 31/31 已在 `gate-0008` 的 note 里 attestation ⇒ 正确输出是 `below(record) / meets(recompute) / 31-31(human) — adjudicate`（机器不替人裁决"谁对"），而不是把该 stage 判成"不该 closed"（该 stage 已 closed，属历史层 warn，见 F5.2）。
- **CR-1c correction 在值层之上（单向）**：`P1` 命中 ⇒ 值层强制 `below` 且 `disputes += correction`。理由同 CR-1，且 correction 带字节绑定（唯一能证明"被纠对象就是当前字节"的源）。
- **CR-2 记录值不得单独支撑 meets**：`P4` 只有在 ① 与 `P2`/`P3` 一致，或 ② 有可归因 writer（同 key `l3-verdict` 事件 ±slack，§F0.5）时才能让值层为 `meets`。反例（双向失真，都是实测）：
  - **记录偏高**：FM `gui-contract-mock-tests`（record `meets` / 复算 `below`，失败行是 `PASS … 0 FAIL —` 散文行 ⇒ 机器假阴）；E2 `feature-l3-readcap-injection` / `feature-sampling-human-channel`（record `meets` / correction `below`）。
  - **记录偏低**：FM `gui-shell-spike`（record `below` / 复算 `meets`）。
- **CR-3 `suspect` 即 `below`**：直接复用现成 fail-closed（`conductor.py:1657-1660`：`suspect ∧ raw=meets → below`），不新增语义。
- **CR-4 correction 失效判据（防止永久钉死）**：`original_sha256 != sha256(当前 S1)` ⇒ correction **失效**，且必须记 `correction-stale`（禁止静默忽略——静默忽略等于把"记录已被后续轮刷新"当成"记录仍然错误"）。真实数据：两条 correction 当前**仍匹配**（§F0.4）⇒ 在效；E2 三个 key 的 `16:47:33Z` 改写则**没有**对应 correction（且它们不是 victim key），属于"改了记录但无人声明"的第三类。
- **CR-5 散文不入算**：S7 的 `question`/`note`、S5 的 `goal` 文本、S8 的 `achieved.md` 一律只作**展示/attestation**（加 `sha256`+`mtime` 锚），不得作为值层的派生输入（RQ-14 D6；反例：E2 `gate-0003` 的 note 在 2026-09-23 记录"`feature-params-service` l3-verdict=below 且 l3-report.md 为 181B 空壳"，而今天 S1=`meets`、report=7130B——**若把 note 当输入，就会与最新盘面冲突且无法判谁对**）。
- **CR-6 `unbound ≠ meets`（第三态，绑定层）**：目标文件缺失/不可读/无归因 writer ⇒ `binding = unbound`，**即使值层为 `meets` 也不得自动放行**。它也不等于 `below`（避免制造假故障：JC `llm-router` 在 `done` 且**根本没有** `l3-verdict.txt`，dossier 列写 `none`）。

**两级判据（本设计的核心）**：**自动放行 = 值层 `meets` ∧ 绑定层 `bound`**。两者缺一即落人工/待复核。

**"哪个赢"总表（真实数据逐例）**

| 案例 | S1 record | P3 复算 | P1 correction | S7 人工 note | 值层 `V_bound` | 可自动放行？ | 谁赢 / 理由 |
|---|---|---|---|---|---|---|---|
| FM `gui-shell-spike` | below | meets | — | 31/31（`gate-0008` note 逐字） | **below**（disputed） | 否（且无快照 ⇒ 绑定层亦不可用） | CR-1 ③ + CR-1b：人工 attestation 只展示 |
| FM `gui-contract-mock-tests` | meets | below | — | 18/18 | **below**（disputed） | 否 | CR-1 ③ |
| FM `gui-contract-surface` | below | below | — | 23/23 人工复验 | **below**（机器一致、与人冲突） | 否（历史层 warn） | 机器不替人裁决 ⇒ 第 (3) 类 |
| E2 `feature-l3-readcap-injection` | meets | below | **below（在效）** | — | **below**（disputed） | 否 | CR-1c + CR-4 |
| E2 `feature-sampling-human-channel` | meets | below | **below（在效）** | — | **below**（disputed） | 否 | CR-1c + CR-4 |
| E2 `feature-inline-marker-patchkit` | below | below | below（no-op） | — | **below** | 否 | 三源一致 |
| E2 `feature-params-service` | meets | meets | — | `gate-0003` note 曾记 below | **meets** | 否（绑定层 `unbound`：无 `l3-verdict` 事件，§F0.5） | CR-2 ② + CR-6 |
| JC `llm-router` | 文件不存在（dossier 列 `none`） | 无 `l3-a*` 目录 | — | `gate-0005` note | **indeterminate**（无可信源） | 否 | CR-6：历史层 warn，不回退已 closed stage |

### F3 快照绑定设计：记录"应答时刻的证据快照"

#### F3.1 要绑的到底是什么（定义）

- **对象**：一个门 → 一组**证据指针**。指针集合由门的 `kind` + `scope`（`stage`/`key`，`gates.py:68-81`）推导，不来自 `context_refs` 的自由文本（`context_refs` 由 conductor 生成，但 `stalled` 的第 2 项是**散文 reason**，不可当路径用）。
- **三元组**：每个指针记 `(path, sha256, mtime_ns)`，另加 `bytes` 与 `exists`。四元组比三元组多一个"体量"，用于识别占位件（RQ-14 F7 的证据：E2 占位 `output.md` 465B / 582B；`feature-params-service` 的 `l3-report.md` 181B 空壳）。
- **"应答时刻"的可得性（必须先说清）**：唯一观察得到"门已被应答"的框架进程是 conductor 的 tick（`tick` `:2050` → `orchestrate` → `_consume_answered_gates` `:316`）。应答文件由 TS/手写在**任意时刻**落盘，conductor 最快也要下一个 tick 才看到（`poll_interval_sec` 量级）。⇒ 严格意义的"应答那一瞬间"快照**不可得**；本设计的诚实替代是**两份快照 + 差集**：
  - `reason="created"`：建门那一刻（`_create_gate` `:2159`）；
  - `reason="consumed"`：conductor 第一次看到 `status != pending` 那一刻（同一 tick 内、**在**任何状态转换之前）；
  - `changed[] = {path | created.sha256 != consumed.sha256}`，并额外记 `gate_file.mtime_ns`（应答落盘时刻的最近证据）⇒ "应答窗口内证据被改写"变成**机器可判**，这正是 AC-029 补记的"必须绑定应答时的证据快照"的落地形态。
- **为什么不能只写一份**：只写 `created` 会漏掉"人答题前/后证据被改"（RQ-14 的 E2 `gate-0010`：交付后 13 分钟被 repair 轮改写）；只写 `consumed` 会漏掉"人看到的是哪一版"（若证据在窗口内被改写，`consumed` 是对的但没人知道它变了）。两份之差是唯一能同时表达两者的机制。

#### F3.2 载体选型（3 选 1 + 组合）

| 选项 | 形态 | pros | cons | 判定 |
|---|---|---|---|---|
| **A. 写进 gate 文件自身字段** | 新增 frontmatter 字段（如 `evidence_snapshot:`） | 与门同生命周期、单文件、无新面 | ① gate frontmatter 是 **12 字段闭集 + 两侧 fail-closed**（`gates.py:68-81`/`:347`、`status-model.ts:572`/`:660`）⇒ 改一次触发两侧 schema + 既有门全量解析路径 + parity 语料；② 快照必须在**应答时**写，而唯一能改门文件的 TS `answerGate`（`gate-writer.ts:139`）**只改 4 行**且 `answeredAt` 可被调用方 override ⇒ 快照变成**应答者可写**（直接违反 AC-030）；③ 一份门文件只能放一份快照，无法表达 `created`/`consumed` 两份 | **否** |
| **B. 独立 sidecar（每门一份）** | `<gates>/gate-NNNN.evidence.json` | ① 不碰 gate schema（命名已被三处 `^gate-\d+\.md$` 过滤：`gates.py:91`/`:256`/`:496`、`status-model.ts:600`/`:750`、`monitor.ts:260` ⇒ 安全）；② 写者 = conductor（可归因，不可由应答者写）；③ 与既有 `l3-verdict-provenance.json` 同构（append-only + `tmp`+`os.replace` + 损坏不覆盖，`conductor.py:1451-1480`）；④ 天然支持多份快照（按 `reason` 去重） | 新增文件族（读取面 + 清理策略）；每门 2 次写（GC-3 面：per-gate 无竞争，且写点在已持有的 `gates.lock` 内 `conductor.py:2168-2178`，无需新锁） | **选（主）** |
| **C. 项目级 ledger** | 单文件 append-only（形态参照 E2 的 `build-runs/verdict/write-journal-*.jsonl`，`producer`/`run_id`/`sha256_before`/`sha256_after`） | ① 已有真实先例且绑定强度最高（sha256_before/after）；② 单文件便于"一次 grep 看全部纠正史"；③ 便于人审 | ① 单文件是**共享写面**（GC-3），需要锁 + 轮转策略，与 GC-1（不引入中心化协调面）的精神冲突；② 无法自然表达"每门两份快照"；③ 与 `gate-*` 的对应关系要额外 join | 否（可作**可选**的跨门审计镜像，不进 wave 1） |
| **A+B 组合** | gate 只存 `evidence_snapshot_id`（弱引用），实体在 sidecar | 门自述有绑定 | 仍需改 12 字段 schema；且引用完整性多一层 | 否 |

**选定：B**。理由排序：① 不改两侧 frontmatter 闭集（最小 blast radius）；② 写者只能是 conductor ⇒ 满足 AC-030"不得依赖应答者可写字段"；③ 与既有 provenance sidecar 的落地纪律完全同构，评审成本最低。

#### F3.3 sidecar schema（字段名 + 类型 + 语义）

```
文件名：<gates_dir>/gate-<NNNN>.evidence.json        （与 gate-<NNNN>.md 同目录同前缀）
顶层：
  schema            str   = "gate-evidence/1"
  gate_id           str   = "gate-0007"
  kind              str   ∈ GATE_KINDS（gates.py:54）
  scope             obj   {stage: int|null, key: str|null}
  snapshots         list  （按 taken_at 升序；按 reason 去重）
snapshots[]：
  reason            str   ∈ {"created","consumed"}
  taken_at          str   iso8601（conductor 时钟，机器写）
  taken_by          str   = "conductor"（闭集；禁止 "human"/"answerer"）
  gate_file         obj   {path, status, answered_at, answered_by, sha256, mtime_ns}
  evidence          list  [{path, role, exists, bytes, sha256, mtime_ns}]
  evidence_digest   str   sha256(canonical_json(evidence, 按 path 排序))  ← 一次比较代替逐项比较
  unresolved        list  [path]   ← 想绑但读不到/算不出的指针（**不静默跳过**）
  changed           list  [path]   ← 仅 consumed 快照：与 created 的 sha256 不同的项
  roster_digest     str|null       ← 仅当 evidence 含 glob 展开时：目录项清单的 sha256（成员增删可判）
```

- `role` 闭集（少而稳，避免自由文本）：`l3-verdict` / `l3-report` / `achieved` / `quality-gate-report` / `pm-state` / `dossier` / `worker-output` / `worker-report` / `worker-trace` / `roadmap` / `goal` / `gate-file`。
- `path` 一律项目相对、`/` 分隔（沿用 `_xkey_norm_path`，`conductor.py:3216`），便于跨机器复算。
- **每 kind 的指针模板**（`EVIDENCE_TEMPLATES`，推导函数）：

| kind | 指针集合 |
|---|---|
| `stalled`（key=K） | `.agenticdoc/K/l3-verdict.txt`、`.agenticdoc/K/l3-report.md`、`.agenticdoc/K/achieved.md`、`.agenticdoc/K/pm-state.md`、`.agenticdoc/K/workers/<末轮 task_key>/{output.md,report.md,worker.log,trace.log}`、`_roadmap.md` 的 K 行、gate 文件自身 |
| `stage-close` / `stage-confirm`（stage=N） | `stage-N-close.md`（若存在）、`.agenticdoc/_autopilot/_roadmap.md`、该 stage **每个 key** 的 `l3-verdict.txt` + `achieved.md`、gate 文件自身 |
| `goal-change` | `.agenticdoc/goal.md`（**当前无 before-image**，RQ-12 数据缺口 4 ⇒ 只能绑 after）、gate 文件自身 |
| `budget-exhausted`（key=K） | 该 loop 的 `used_rounds` 输入集（`.agenticdoc/K/workers/*/task.md`，`state.py:224` 的同一集合）、dossier gaps 来源（`audit_evidence.build_dossier`）、gate 文件自身 |
| `xkey-authorize` | ticket JSON（已有 `authorization_snapshot`/`target_file_sha256`，`conductor.py:2691-2698`）、被冻结文件的当前 sha、gate 文件自身 |

- **成本上界（设计约束）**：`workers/*` 只绑**末轮**（`max(ap-<K>-l3-a<k>)` 与 `max(ap-<K>-repair-a<k>)`），不绑全部轮次；E2 `feature-cigate-install-kit` 实测有 **29** 个 worker 目录（`feature-inline-marker-patchkit` 25 个），全绑会让每门 O(29) 次哈希 × 2 份快照。**未绑的轮次必须进 `unresolved`**（"未绑"与"绑了且一致"必须可区分）。

#### F3.4 写入点（`file:line`）与调用契约

| 快照 | 写入点 | 说明 |
|---|---|---|
| `reason=created` | `conductor._create_gate`（`:2159`）内、`gates.create(...)` 成功之后、`st.timeline.append("gate-created", …)`（`:2179`）之前 | 此处已持有 `gates.lock`（`:2168-2178`）⇒ sidecar 写入可复用同一临界区，**不新增锁**；先写 sidecar 再写 timeline，保证"有事件必有快照" |
| `reason=consumed` | 新增 helper `_snapshot_answered_gates(project_root, st)`，在 `tick()`（`:2050`）的启用判定之后（`:2062-2063` 之下的新步骤 2b）调用一次；对每个 `status != pending` 且尚无 `consumed` 快照的门写一份 | ① 单点、幂等（按 `reason` 去重）；② 覆盖三种消费路径（`_consume_answered_gates` `:316`、`_apply_stalled_approvals` `:2295`、`_apply_stalled_rejections` `:2363`）而无需改它们的内部逻辑；③ **注意** `tick()` 在 `goal-change` 打开时于 `:2112` 提前 return ⇒ 该 tick 不会写 consumed 快照（下一 tick 补写；设计上允许，因为 sidecar 幂等） |
| 写入纪律 | 复用 `_persist_l3_provenance`（`:1451`）的形态：`json.dumps(..., indent=2)` + `tmp` + `os.replace`；**损坏文件不覆盖**（`:1467-1476`），返回 False + timeline `config` 事件；按 `reason` 去重 ⇒ 重复 tick 零写 |
| 哈希原语 | `_xkey_sha256_bytes`（`:3200`）/ `_xkey_file_sha256`（`:3204`）；**不重造** | 现有实现已满足"整文件字节 sha256"，并已在 xkey ticket 上以 `authorization_snapshot` 形式存在（生产 0 样本） |
| **原子化要求（针对 R2 的"带外改写"）** | `_persist_l3_verdict`（`:675`）的落盘与 `l3-verdict` 事件（`:711`）必须同源：把 `st` 从 `ConductorState \| None` 收紧为**必填**（或对 `st=None` 的调用改为"落盘 + 追加一条无 key 的 `config` 事件"），否则"有记录无痕"永远可复现 | 真实反例 = §F0.6（3 key / 6 文件 / 0 事件） |

#### F3.5 读取面与 fail-closed 行为

- 判官函数（只读）：`reconcile_key(project_root, key) -> ReconcileView`（新，建议落在 `autopilot/`，被 conductor 前置 + doctor + 面板共用；**不得**落在 TS 以免两侧逻辑分叉）。
- `binding` 三态：`bound`（`gate_file.sha256` 与 `evidence_digest` 齐备且 `unresolved == []`）/ `partial`（有快照但 `unresolved != []` 或只 `created`）/ `unbound`（无 sidecar 或读失败）。
- **fail-closed 表**：
  | 情形 | `V_bound` | 自动放行 | 显示 |
  |---|---|---|---|
  | `bound` + 全源 `meets` | `meets` | 允许 | — |
  | `bound` + 任一 `below`/dispute | `below` | 禁止 | `!DISPUTED` |
  | `bound` + `changed[] != []` | `indeterminate` | 禁止 | `!DRIFT` |
  | `partial` | `indeterminate` | 禁止 | `!UNBOUND` |
  | `unbound`（历史门） | `indeterminate` | 禁止（但**不拦历史**，F5） | `!UNBOUND(legacy)` |
  | sidecar 损坏 | `indeterminate` + `config` 事件 | 禁止 | `!CORRUPT` |

#### F3.6 两侧镜像面（Python `gates.py` + TS `status-model.ts`）

| 面 | Python（`autopilot/gates.py`） | TS（`autopilot/status-model.ts`） |
|---|---|---|
| schema 常量 | `EVIDENCE_SCHEMA = "gate-evidence/1"`（新增，紧邻 `FRONTMATTER_FIELDS` `:68-81` 之后） | `export const GATE_EVIDENCE_SCHEMA = "gate-evidence/1"`（紧邻 `GATE_FRONTMATTER_FIELDS` `:572` 之后） |
| 字段序（fail-closed 校验的锚） | `EVIDENCE_SNAPSHOT_FIELDS: tuple[str, ...]`（= 上面 9 个字段的规范顺序，含 `snapshots[]` 内 8 字段） | `export const GATE_EVIDENCE_FIELDS = [...] as const`（同序） |
| 角色闭集 | `EVIDENCE_ROLES` | `export const GATE_EVIDENCE_ROLES = [...] as const` |
| 读 | `read_evidence_snapshot(path) -> EvidenceFile \| None`（不抛；损坏 → `None` + 可选 `config` 事件由调用者写） | `readGateEvidence(projectDir, gateId): {ok:true, file} \| {ok:false, error}`（**只读、不建目录、不写**） |
| 写（仅 Python） | `write_evidence_snapshot(path, payload) -> bool`（调 `_xkey_sha256_bytes`；`tmp`+`replace`；损坏不覆盖） | **不提供**（TS 只读；应答者不得写快照） |
| 消费面 | `conductor._create_gate` `:2159`（created）、`_snapshot_answered_gates`（consumed）、`reconcile_key`（判官） | `monitor.ts` 门行 `:645-653`（加 `!DRIFT`/`!UNBOUND`/`!DISPUTED` token）、`/autopilot gates` 卡片（`console.ts:182-198`）新增 `bound`/`changed` 行；`deriveAutopilotPanel` `:463` 增加计数 |
| parity 测试 | 新增 `packages/multi-workers/test_autopilot_gate_evidence_parity.py`（两侧字段序/闭集/哨兵逐字一致；参照 `test_autopilot_config_parity.py`、`test_mwpp_collection_parity.py` 的现有范式） | 同一测试文件的 TS 侧调用；**P-021**：verify 期两侧都要跑 |

**明确不改**：不新增 gate frontmatter 字段（`gates.py:68`）；不改 `STATUS_SCHEMA = "autopilot-status/1"`（`status-model.ts:1009`）与 `AutopilotStatus`（`:1055`）——reconciliation 数据在 wave 1 **不进版本化 JSON**（doctor/面板直读 sidecar）。若最终要进 JSON，必须 bump 到 `autopilot-status/2` 并同步冻结语料（这是一项独立决策，费用 = 版本面 + parity 语料重冻）。

### F4 与 roadmap `done` 的对账

#### F4.1 判官（只读）与四个判据

```
reconcile_key(project_root, key) -> {
  claimed:   roadmap 的 key-status（S6）,
  bound:     {value, source_path, sha256, mtime_ns} | None,      # F2 的 V_bound
  binding:   "bound" | "partial" | "unbound",                     # F3.5
  disputes:  [{kind, detail, source_path}],                        # 见下
  effective: "meets" | "below" | "indeterminate",
  changed:   [path]                                                # F3.3 的快照差集
}
```
`disputes[].kind` 闭集：`correction`（F2 P1 命中）/ `recompute-vs-record`（P3≠P4）/ `unattributed-writer`（P4 无 `l3-verdict` 事件，§F0.5）/ `missing-record`（`claimed=done` 但无 S1，JC `llm-router` 实例）/ `correction-stale`（CR-4）/ `drift`（F3 快照 `changed` 非空）。

| 判据 | 触发条件 | 动作 | 真实数据命中 |
|---|---|---|---|
| **R-A 告警** | `claimed ∈ {done} ∧ effective != meets` | 写 `evidence-reconciliation` timeline 事件（每 key 每次状态翻转一次，去重复用 `_timeline_has_event` `:1553` 的窗口模式）；doctor `reconciliation.disputed` +1；面板 attention 行 | E2：`feature-l3-readcap-injection`、`feature-sampling-human-channel`（correction 在效）、`feature-params-service`/`feature-mvp-closeout`/`feature-tier-a-closeout`（`unattributed-writer`）；FM：`gui-contract-mock-tests`、`gui-shell-spike`；JC：`llm-router`（`missing-record`） |
| **R-B 拦收口（仅新转换）** | 某 stage 的 `_stage_closure`（`:628-630`）即将建 stage-close 门，且该 stage 存在任一 key 的 `effective != meets ∨ binding != bound` | **不建门**（保持未收口），写 `stage-close-blocked-evidence`（`stage=N`, detail=逐 key disputes），下一 tick 重算（状态变化即自动重开） | 今天无新转换 ⇒ 0 命中；若按 E2 当时的数据（correction 在效 + `counted_as_done=false` + roadmap done）会**命中** |
| **R-C 不自动答** | 门已建但 `binding != bound ∧ effective != meets` | 自动决策（AC-016/AC-025 第 (1) 类）**不得**答 approve；落第 (3) 类给人（或第 (2) 类待复核，但 `stage-close` 属"绝不可延后"⇒ 必须给人） | 同上 |
| **R-D 历史不回退** | gate/stage 的 `created_at`（或 stage `status=closed` 的既有事实）早于绑定机制上线点 | **只告警**，绝不 re-close/re-open，绝不改 `_set_stage_status`（`:380`）的既有语义 | FM Stage 1 / E2 Stage 2 / JC Stage 1 全部属此列 |

**R-B 的落点细节**（必须写清，否则会撞既有语义）：`_stage_closure` 现在是"全 key 终态 ⇒ 建门"（`:628-630` 是唯一判据）。R-B 只**加一条前置**（在 `:630` 与 `:631` 之间插入 `if not reconciliation_ok(...): return`），不删除任何既有判据，不改 `_DEP_SATISFIED`（`:56`）、不改 `_ensure_next_stage_gate`（`:409`）。副作用：`stage-close` 门会晚建 → 但 `_stage_closure` 每 tick 都会重算，故"晚"是幂等的、可自愈的，不会像 cap 阻塞那样"零痕迹"（这正是 AC-017 的要求：新机制必须留痕）。

#### F4.2 告警面（事件名 + doctor/面板字段）

| 面 | 新增内容 | 两侧镜像要求 |
|---|---|---|
| timeline 事件名 | `evidence-reconciliation`（R-A）、`stage-close-blocked-evidence`（R-B）、`evidence-drift`（`changed != []`）、`evidence-unbound`（`binding != bound`）、`correction-stale`（CR-4） | Python `timeline.EVENT_TYPES`（`timeline.py:67-85`）与 TS `EVENT_TYPES`（`status-model.ts:779`）**同改**；顺带补上已漂移的 `target-config-rejected`（AC-022 D3）。事件 `detail` 必须带机器可判 token（kind/计数/paths），不得只有散文 |
| doctor | `_doctor_autopilot`（`mw_common.py:2022`）新增只读子段：`gates {pending, unbound, drifted, disputed}`、`reconciliation {claimed_done, bound_meets, disputed, unbound_legacy, corrections_in_force, corrections_stale, errors[]}` | 只读（沿用 `:2023-2024` 的 "never creates a directory or a file" 契约）；`_doctor_issues`（`:2067`）决定哪些进 issues、哪些只进 suggestions（建议：`disputed` 进 issues，`unbound_legacy` 只进 suggestions，避免历史噪声变故障） |
| 面板（`MonitorAutopilot` `monitor.ts:122`） | `reconciliation {disputed, unbound, drifted}` + attention 行（现只在 `status=stalled` 时生效，`:604-626`）泛化为"有 dispute 的 key 各一行"；门行（`:645-653`）在 110 列预算内加固定 token `!DISPUTED`/`!DRIFT`/`!UNBOUND` | 纯读；`MonitorGate`（`:89-95`）**当前只有 id/kind/stage/key** ⇒ 若门行要显示 dispute，需要给它加字段（或让面板直读 sidecar）——这是一处必须的接口扩展 |
| `/autopilot gates` 卡片 | 新增两行：`bound: {bound\|partial\|unbound} evidence_digest={sha256[:12]} changed=[…]`、`disputes: {kind}×{n} ({source})` | `GateRecord`（`status-model.ts:587`）不含 `context_refs`，更没有快照 ⇒ 卡片需要新的读取面（`readGateEvidence`）而不是扩 `GateRecord` |
| `--json` | **不进** `autopilot-status/1`（`status-model.ts:1009`/`:1055`） | 若要进，须 bump `autopilot-status/2` + 语料重冻（独立决策） |

#### F4.3 修法选项（≥2，含 pros/cons）

| # | 选项 | 做法 | pros | cons |
|---|---|---|---|---|
| **O1** | **只读判官 + 告警（零写）** | 新增 `reconcile_key`；conductor 只在 R-B/R-C 用它；doctor/面板直读盘面 | ① 零新写面（GC-1/GC-3 无损）；② 立刻作用于历史数据；③ 无迁移 | ① 不修数据，FM/E2 的档案矛盾仍在（只是被看见）；② 没快照 ⇒ 只有"现在"可比，没有"当时"（RQ-14 的 24/34 漂移仍不可复现）；③ "看过一次"没有持久留痕（除非写 timeline 事件，那就变成"半写"） |
| **O2** | **O1 + 门级快照 sidecar（F3）** | 加 `gate-NNNN.evidence.json` 与 created/consumed 两份快照 | ① 补齐"当时看到什么"；② drift 可判（`changed[]`）；③ 写者=conductor、不可被应答者写（AC-030）；④ 与既有 provenance sidecar 同构 | ① 新文件族（读取面 + 每门 2 次写）；② 历史门 `unbound`（需如实显示，见 F5）；③ `MonitorGate`/`GateRecord` 需扩字段 |
| **O3** | **就地收敛记录**（`_persist_l3_verdict` 之外，直接把 S1 刷成 `V_bound`，并把 dossier 重生） | 让记录追平证据 | 单一真值、面板干净 | ① **改写受保护历史**（E2 明确选了 sidecar：`achieved-correction-*.json` 的 `zero_write_policy` 原文 "achieved.md is a protected record: it is never rewritten by this key; the correction is carried by this sidecar only"）；② 需要授权门；③ 一旦允许改写，"证据不可事后修改"这一属性没了（AC-030 的反面）；④ `_stage_closure` 复用旧 dossier 的行为会让 dossier 重生与 gate 语义脱节 |
| **O4** | **把 correction 升为框架契约** | 框架读 `<key>/*-correction-*.json`（`original_sha256`/`corrected_value`/`counted_as_done`），在 `_l3_verdict`/判官里作为 P1 | ① E2 的真实数据立刻可用；② 单向降级（只 fail-closed）；③ 无需历史改写；④ 项目侧已有 5 个真实文件（3 key） | ① 把项目约定固化为框架契约（RQ-12 I6 的风险）；② 需要失效/退役规则（CR-4）与"谁有权写"的治理（当前 `owner: "用户/PM"`）；③ 可被滥用把 key 永久钉在 `below`（需配合 R-D 与人工复核） |

**推荐组合：O2 + O4（O1 作为其告警面）**，明确拒绝 O3。理由：AC-029 的两个诉求分别是"取证源优先级"（O1+O4）与"证据快照绑定"（O2）；而风险 27 的反面（"可被事后改写的历史"）只有 O2 能治，O3 恰好是它的病因。

### F5 迁移（既有项目：FM/E2/JC 的历史 gate 与已闭合 stage）

1. **不回填、不回写**：历史门（本卡实测：3 项目 gates/ 共 36 个，另有 FM _autopilot/_gates-flood-20260924/ 的 **6684** 个归档洪泛门）不加 sidecar；历史 dossier 不改。判定分界用**部署时间戳**（绑定机制上线的 commit/版本），不用文件 mtime（mtime 可被测试/复制污染）。
2. **历史 = `unbound`，如实显示而不是报错**：R-A 的告警把 `unbound_legacy` 单列（doctor suggestion，不进 issues）；R-B/R-C 只作用于 `created_at > deploy_ts` 的门。落地结果（今天按此规则跑）：
   - **会告警**：E2 `feature-l3-readcap-injection`（correction 在效 + roadmap `done` + Stage 2 `closed`）、`feature-sampling-human-channel`（同型）、`feature-params-service`/`feature-mvp-closeout`/`feature-tier-a-closeout`（`unattributed-writer`）；FM `gui-contract-mock-tests`（recompute≠record）、`gui-shell-spike`（同）、`gui-contract-surface`（机器两源一致但与人 23/23 冲突）；JC `llm-router`（`missing-record`：`done` 但无 `l3-verdict.txt`、无 `workers/`）。
   - **不会被动**：任何已 `closed` 的 stage 状态、任何 `_roadmap.md` 的既有行、任何历史 dossier。
3. **只读路径零写（本轮硬约束）**：`reconcile_key`、doctor、面板、`/autopilot gates` 一律不 `mkdir`/`touch`/不建临时文件（复用 `mw_common.py:2023-2024` 与 `conductor.py:1373` 的既有契约措辞）。**唯一例外**是 conductor 的 sidecar 写入（O2），它必须走"conductor 是唯一写者 + 已有 `gates.lock` 临界区（`:2168-2178`）"，读面永不写。
4. **correction 兼容**：按 E2 现有字段原样读（`original_value`/`original_sha256`/`corrected_value`/`counted_as_done`/`dispositions`/`ledger_items`/`evidence_source{path,sha256,exists}`/`unlock_condition`/`owner`）；缺 `original_sha256` 的旧式 sidecar（本仓暂无）⇒ 用 `original_value == 当前 S1 值` 作**弱绑定**并在 doctor 标 `weak-binding`。**不要求项目改文件**（否则等于逼迫历史改写）。
5. **JC gate-0008 型重放的专门处理**：`_stage_closure` 只在 dossier 缺失时生成（`:635`）⇒ 重放收口会复用 14 天前的 dossier（JC `stage-1-close.md` mtime `2026-09-11T20:25:02Z`，而 gate-0008 `created_at 2026-09-26T04:37:27+00:00`）。设计对策：**快照必须绑门**（F3 的 `reason=created`）+ 门卡片显示 `dossier.mtime < gate.created_at ⇒ DRIFT`，**不**改 dossier 生成策略（那是 AC-028 的面）。
6. **可选回填（非本波、显式命令）**：`mw autopilot reconcile backfill --write`（默认不跑），按 key 逐目录、持 `.mw/` 锁、只写 sidecar 不写历史记录，且必须幂等（重跑零写）。**GC-1 语义**：回填是显式人工命令，不是 tick 内的自动行为。
7. **明确不动**：`_DEP_SATISFIED`（`:56`）、`_consumed_gate_ids`（`:297-313`）、`_set_stage_status`（`:380`）、`gates.FRONTMATTER_FIELDS`（`gates.py:68`）、`STATUS_SCHEMA`（`status-model.ts:1009`）、`_l3_resolve_source` 的判据（`:1274`）。

### F6 VC 候选（6 条机器可判）

| VC | 判定式（可执行） | 验证层级 | 真实反例（命中） | 反向用例（必须绿） |
|---|---|---|---|---|
| **VC-D4-1 correction 不得与 roadmap `done` 共存**（新转换层拦截） | 对 stage 的**新**收口转换：`∀key: in_force_correction(key) ⇒ V_bound(key)=below`，且 `effective != meets` 时不得建 `stage-close` 门（R-B） | conductor 单元/集成（`test_autopilot_closure.py` 范式 + fixture）；离线判官对历史数据只告警 | E2 `feature-l3-readcap-injection`：correction `corrected_value=below` + `counted_as_done=false` + roadmap `=done` + Stage 2 `closed` ⇒ 离线判官必须报 `disputed` | ① correction 的 `original_sha256` 与当前 S1 不匹配 ⇒ **不算 in force**（CR-4），不得拦；② 无 correction 且三源一致 `meets` ⇒ 必须放行 |
| **VC-D4-2 快照漂移必须可判** | `created`/`consumed` 两份快照的 `sha256` 差集非空 ⇒ 必须产生 `evidence-drift` 且 `binding=partial`（不得判 `meets`） | conductor 集成（fixture：`created` 后改写 evidence 再 `consumed`）；真实数据回放 E2 `gate-0010`（应答后 13 分钟 `l3-a2/output.md` 被改写 ⇒ 若该门在窗口内被消费，`changed` 必然非空） | RQ-14 实测 **24/34 门**证据 mtime > `answered_at`；本卡复算同值（§F0.1） | `created` 后不改写 ⇒ `changed == []` 且 `binding=bound`，不得误报 |
| **VC-D4-3 writer 不可归因 ⇒ 不得自动 meets** | 对每个 key：若 S1 的 mtime 无同 key `l3-verdict` 事件（±slack）⇒ `disputes += unattributed-writer`、`binding != bound`、`effective != meets` | 离线判官（全量 22 key 一次跑）；conductor 侧只用于新转换 | **15/22** 无事件（§F0.5）；最强命中 = E2 三 key 同 mtime `2026-09-24T16:47:33Z` + 该秒 `timeline.jsonl.1` 全为 `beat`（`seq 65820-65829`）+ 项目侧证据 `writer: "…_persist_l3_verdict (T-002) ; st=None"` | ① 有事件（FM `gui-skeleton-shell` 有 `2026-09-25T04:14:55+00:00` 的 `l3-verdict none -> meets`）⇒ 必须**不**告警；② 轮转剪掉事件的情形需按"分界时间"豁免（否则会把正常写入误报） |
| **VC-D4-4 双向失真都必须 fail-closed** | `P3 recompute ≠ P4 record` ⇒ `effective != meets`（不得自动放行）；且该判据必须**双向**成立（谁高谁低都拦） | 单元（6 例语料：4 例 mismatch + 2 例 agree）；离线复算 | 偏高：FM `gui-contract-mock-tests`（`meets` vs `below`）、E2 两 key（`meets` vs correction `below`）；偏低：FM `gui-shell-spike`（`below` vs `meets`） | 16/22 三源一致 `meets` ⇒ `effective=meets`、`bound`、可自动放行 |
| **VC-D4-5 只读面零写** | 在**无** `_autopilot` 目录、**有** 门但无 sidecar、**有** 损坏 sidecar 三种输入下跑 `mw doctor` + 面板派生 + `/autopilot gates`：目录树（path 集合 + mtime_ns 集合）与调用前**逐字相同** | pytest（`test_doctor_autopilot.py` 范式，`monkeypatch` 断言 `mkdir`/`open(...,"w")` 零调用 + 全树 stat 快照比较） | 反例（现状历史）：`_persist_l3_verdict` 在 `st=None` 时静默跳过事件（§F0.6） ⇒ 这条 VC 的作用就是禁止把这类路径引入读面 | conductor 写 sidecar 时**允许**写（写面不属于只读面）⇒ 测试必须区分调用面 |
| **VC-D4-6 correction 在效判据** | `in_force(c) := sha256(S1) == c.original_sha256`；`in_force ∧ (c.corrected_value != c.original_value ∨ c.counted_as_done == false)` ⇒ 作为 P1 dispute | 单元（用 E2 两条真实 sidecar 的原文 + 两个数） | E2 两条 `original_sha256` 均**等于**当前文件 sha（§F0.4）⇒ 在效、必须 dispute | 构造"文件被后续轮刷新"的 fixture（sha 改变）⇒ 必须报 `correction-stale` 且**不再**降级为 dispute 主因（仍 fail-closed 为 `indeterminate`，不得静默 `meets`） |

## 结论 → 决策映射

| 目标 | 本卡交付 | 关键判据（可复算） |
|---|---|---|
| **AC-029 前半（取证源优先级表 + 一致性规则 + fail-closed + 与 roadmap `done` 对账）** | §F1 的 10 源表（谁写/何时/绑定/覆盖）、§F2 的 P1..P6 + CR-1..CR-6、§F4 的 R-A..R-D 与告警面/修法选项 | 每个源给 `file:line` + 真实字段值；`V_bound` 由 `reconcile_key` 单点计算；不一致一律 `≠ meets` |
| **AC-029 后半（"应答时的证据快照"sha256+mtime 绑定）** | §F3 的 sidecar schema + created/consumed 两份快照 + 写入点 + 两侧镜像面；`changed[]` 把"窗口内改写"变成机器判据 | `gate-NNNN.evidence.json`（与 gate frontmatter 解耦）；写者仅 conductor；`evidence_digest` + `gate_file.sha256` |
| **AC-025（第 (1) 类"可自举"的边界）** | 自举只能建立在 **P1/P2/P3 且 `binding=bound`** 之上；`indeterminate` 一律不得自动答（CR-6、F4.1 R-C） | 今天能落 `bound` 的只有 2/22 key（provenance）⇒ 生产上第 (1) 类实际几乎为空，与 RQ-12 的"部分可自举"结论一致 |
| **AC-026（门卡片最小信息集）** | 门卡片需新增两行（`bound/evidence_digest/changed`、`disputes`）+ L6 证据行的 `sha256[:12]`/`mtime`/`DRIFT` 标记（RQ-14 D5/D7 已有格式约束） | 复用 RQ-14 的 13 行卡片序；本卡只补"证据可自证"维度 |
| **AC-012（可观测性）** | doctor `reconciliation` 段 + 面板 dispute 行；`unbound_legacy` 单列避免新增误报 | 只读；零写（VC-D4-5） |
| **AC-030（不可由被审方伪造的审计字段）** | 本设计只采信"写入点可归因（conductor）+ 内容哈希"的来源；`answered_at`/`answered_by`/`generated_at`/`submitted` 一类声明值一律**不作为**判据输入（CR-5） | 反例：E2 sidecar 的 `generated_at` 是 `2026-09-25T00:00:00Z` 占位，真实写时刻只能靠 mtime |
| **AC-028（消费记录持久化 + stage 单调性）** | D4 不修它，但快照绑门使"同一 gate id 出现第二份 consumed 快照"可判 ⇒ 为 AC-028 提供检测面 | JC gate-0008 重放（stage 1 `closed → running`）即该族 |
| **风险 25（双向失真）** | 4/22 mismatch 清单 + 双向测试语料（VC-D4-4） | FM 两向、E2 两 key 均入语料 |
| **风险 27（证据被事后改写）** | created/consumed 快照差集；15/22 无痕改写基线；`st=None` 原子化要求 | §F0.5/§F0.6 |

## 数据缺口

| # | 缺口 | 性质 | 影响 | 需要什么才能补 |
|---|---|---|---|---|
| **G1** | provenance 只覆盖 **2/22 key（4 文件 6 记录）**，且只在 `2026-09-25` 之后产生 | **不可回填** | P2 在历史数据上几乎不可用；绑定只能前向生效 | 历史轮次当时没有 anchor，无法补；只能接受"历史 = unbound"（F5.2） |
| **G2** | correction 只在 **E2**（3 key），且是项目自建工具链产物 | 无数据源 | 无法判定 FM/JC 是否也有"已纠正/未纠正"的失真；`FC/JC` 的 `Q-claim` 面全空 | 框架若采 O4，需要跨项目统一契约与治理规则 |
| **G3** | 框架侧**没有任何** sha256 记录（S1/S2/S5/S6/S8 全无） | 可补（前向） | 无法证明"现在 hash 的字节 = 当时渲染裁决的字节"；`st=None` 带外写路径无痕（§F0.6） | F3 的 sidecar + `_persist_l3_verdict` 原子化 |
| **G4** | 6/6 provenance `suspect=false`，`reasons=[]` | 无样本 | fail-closed 路径（`suspect ∧ meets → below`）的**误报率为 0 样本**；上线可能误拦 | 影子模式或真实窗口内改写样本（VC-D4-2 的 fixture 只能证明逻辑，不能证明误报率） |
| **G5** | `l3-report.md` 的**来源轮**不落盘（只在 timeline `l3-verdict` 事件 detail 里，可被轮转剪掉） | 半可补 | 报告与轮次的绑定不可持久复算 ⇒ P3 复算的输入可靠性下降 | 把 `report_src` 的相对路径与 sha256 落到 sidecar（F3 已含 `role=l3-report` 的 sha） |
| **G6** | **口径差异**：RQ-12 报 "6/22 与复算不一致"，本卡复算为 **4/22**（另 1 例 recompute==record 但与人工 attestation 冲突、1 例为一致行） | 需冻结口径 | 影响"自举率"与验收数字 | design 期冻结：建议 `mismatch = |{key: recompute != record}| = 4/22`，另单列 `human-vs-machine = 1`（FM `gui-contract-surface`） |
| **G7** | `budget-exhausted` / `xkey-authorize` 生产 **0 门**；`xkey_repair` 三项目均未开 | 无样本 | F3 的这两个 kind 的指针模板与 F2 的 P1 判据**未经真实数据检验** | 影子模式（RQ-10 已建议）或明确标注"模板来自代码、非历史" |
| **G8** | stage 级"未达成台账"仍只在 `note`/`achieved.md` 散文里（E2 `gate-0003` "approve 不表示其完成"、FM `C-09`/`NRR-1/2`、dossier 只有 5 列） | 无数据源 | 对账只能覆盖 **verdict 面**；"目标是否达成"里的非 verdict 项（未接线 / 待授权 / 人工项）机器不可判 ⇒ R-B 只能拦"证据语义上的未达成"，不能拦"业务语义上的未达成" | 结构化 `open_items`（RQ-12 F-6 已列字段），属 AC-025/AC-026 面 |
| **G9** | 本卡的 writer 归因检查只做了"mtime ±120s 与事件匹配"的粗口径（对 E2 覆盖完整、JC 为 0 事件），**未**验证轮转边界处的误判率 | 半可补 | VC-D4-3 在旧项目上可能误报 | 用"分界时间"豁免（F5.2）+ 对 FM/JC 手工核对边界样本 |
| **G10** | 未确认：`l3-verdict.txt` 是否还有其他写者（除 `_persist_l3_verdict` 之外） | **未确认 + 如何确认** | 若存在第三写者，CR-2 的归因判据不完整 | 确认方法：对 `.agenticdoc/*/l3-verdict.txt` 做全仓 `grep -rn "l3-verdict.txt"` 写点审查（本卡只确认了 `conductor.py` 与测试；**未**穷尽 `mw.py`/`launcher.py`/扩展代码，也未审查 FM/E2 项目侧脚本） |

**未确认项（诚实声明）**：① `l3-verdict.txt` 的写者闭集（G10）；② E2 `feature-inline-marker-patchkit` 的 `achieved-correction` 为何没有 `l3-verdict-correction`（其 `original_value`=`corrected_value`=`below` ⇒ 推测为"不需要值纠正"，**未确认**）；③ FM 是否有未落盘的 correction（无 `.git` 历史可查、无 sidecar ⇒ 无法确认）。

## 机器行

```
[VERIFY] Design D4: sources=10(l3-verdict.txt/l3-report.md/l3-verdict-provenance.json/l3-verdict-correction/l3-achieved-correction/dossier/roadmap-key-status/gate-file/achieved+qg+pm-state/timeline; plus project write-journal observed) framework_visible=8 python_only=1 never=none(new) binding_present={l3-verdict.txt:0, l3-report.md:0, provenance:0(sha), correction:1(original_sha256), dossier:0, roadmap:0, gate:0} coverage={verdict_keys:22, provenance_files:4, provenance_records:6, provenance_keys_vs_verdict_keys:2/22, suspect_true:0, corrections_with_original_sha256:2/22, corrections_any:3/22, l3-report.md:22/22, qg_reports:80, gates_total:36, gates_answered:34} recompute_vs_record=4/22(RQ-12 said 6/22; per-row accounting in RQ-12 includes 1 human-vs-machine row and 1 agreeing row) human_vs_machine=1(FM gui-contract-surface 23/23 vs recompute below) evidence_drift=24/34(eq RQ-14) writer_unattributable=15/22(no matching l3-verdict timeline event within 120s; E2 7/11, FM 4/7, JC 4/4) out_of_band_rewrite=1 verified(E2 feature-mvp-closeout/feature-params-service/feature-tier-a-closeout all mtime 2026-09-24T16:47:33Z, timeline seq 65820-65829 all beat, attributed to project-side exec-l3-verdict-freshness-remediation-20260924.json writer='autopilot.conductor._persist_l3_verdict (T-002) ; st=None' changed_files=6) priority=P1 correction(in-force, original_sha256==sha256(l3-verdict.txt)) > P2 provenance terminal round(suspect=false) > P3 terminal-round recompute > P4 l3-verdict.txt > P5 dossier column > P6 note/prose(exhibit only) rules=CR1..CR6(dispute overrides, fail-closed only for auto-pass, unbound!=meets, correction supersession, prose never derived, suspect=>below) snapshot=[B] per-gate sidecar <gates>/gate-NNNN.evidence.json schema=gate-evidence/1 fields=[schema,gate_id,kind,scope,snapshots[{reason(created|consumed),taken_at,taken_by,gate_file{path,status,answered_at,answered_by,sha256,mtime_ns},evidence[{path,role,exists,bytes,sha256,mtime_ns}],evidence_digest,unresolved,changed,roster_digest}]] write_points=[_create_gate conductor.py:2159, _snapshot_answered_gates at tick() 2b after :2062], reuse=[_xkey_sha256_bytes :3200, _xkey_file_sha256 :3204, _persist_l3_provenance :1451 discipline] mirror=[gates.py EVIDENCE_SCHEMA/EVIDENCE_SNAPSHOT_FIELDS/EVIDENCE_ROLES/read_evidence_snapshot/write_evidence_snapshot, status-model.ts GATE_EVIDENCE_SCHEMA/GATE_EVIDENCE_FIELDS/GATE_EVIDENCE_ROLES/readGateEvidence] no_gate_frontmatter_change=true no_status_schema_change(wave1)=true reconciliation=[R-A warn(effective!=meets while claimed=done), R-B block new stage-close(_stage_closure :628-630), R-C no auto-answer, R-D history never re-closed] alarm_surfaces=[timeline: evidence-reconciliation/stage-close-blocked-evidence/evidence-drift/evidence-unbound/correction-stale (both EVENT_TYPES must add), doctor: _doctor_autopilot(:2022) gates+reconciliation sections(read-only), panel: MonitorAutopilot(monitor.ts:122) + gate line tokens !DISPUTED/!DRIFT/!UNBOUND + attention generalization] real_hits_today=[E2 feature-l3-readcap-injection(correction in force+counted_as_done=false vs roadmap done vs stage closed), E2 feature-sampling-human-channel(same), E2 3 keys unattributed-writer, FM gui-contract-mock-tests recompute!=record, FM gui-shell-spike recompute!=record, FM gui-contract-surface human-vs-machine, JC llm-router done-without-any-record(no l3-verdict.txt, no workers/)] migration=[no backfill, no history rewrite, unbound=legacy honest display, deploy-ts boundary, correction read as-is(E2 field set), optional explicit backfill cmd, untouched: _DEP_SATISFIED :56/_consumed_gate_ids :297/_set_stage_status :380/gates.py:68/status-model.ts:1009] vc=[VC-D4-1 correction vs roadmap done(block new, warn history), VC-D4-2 snapshot drift(changed!=[]=>partial), VC-D4-3 unattributed writer(15/22 real), VC-D4-4 two-way mismatch fail-closed(4/22 corpus), VC-D4-5 read-only paths zero-write, VC-D4-6 correction in-force supersession] data_gaps=10(G1 provenance<=2/22 non-backfillable, G2 corrections E2-only, G3 no sha256 anywhere, G4 suspect 0 samples, G5 report round not persisted, G6 4/22 vs 6/22口径, G7 0 samples for budget-exhausted/xkey-authorize, G8 open_items prose-only, G9 attribution slack boundary unverified, G10 l3-verdict.txt writer set unconfirmed)
```

## 附：本文件的自我边界声明

- 本卡**只做设计**：所有结论以真实文件字段与复算命令支撑；不确定处标"未确认 + 如何确认"（G10 及"未确认项"三条）。
- 本卡**未**给出的（属其他 AC）：`open_items` 的结构化字段契约（AC-026）、自动决策白名单（AC-016）、`reject` 语义（RQ-12 I5）、护栏机制（AC-017）。
- 引用关系：RQ-12（`evidence/research/spec-gate-selfverifiable-20260926.md`）提供 6 类门命题与 4 个 `stage-close` 前置反例；RQ-14（`spec-gate-review-material-20260926.md`）提供 34 门信息集与 **24/34** 漂移实测、D1-D7 呈现判据；本卡在其上补 **取证源优先级/冲突规则/快照绑定/对账判据/迁移/VC**，并修正两处口径（`6/22 → 4/22`；provenance 覆盖 `2/22 key（4 文件 6 记录）`）。
