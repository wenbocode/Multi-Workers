# Research: G1「`l3-aborted` 指纹 + 有界自动重掷」实现接线与夹具（DRQ-1）

> Key: `mw-gate-verdict-hardening` ｜ 角色: DESIGN 只读调研（DRQ-1，G1 = AC-001~AC-004） ｜ 快照: 2026-10-09
> 工作树 HEAD: `10446aefb` ｜ 项目根: `H:\git\Multi-Workers`
> 前置: `evidence/research/spec-l3-abort-taxonomy-20261009.md`（RQ-1 现状普查：语料 正 6 / 负 48）
> 只读声明: 本轮不修改任何代码或其它文件；本文是唯一产物。
> 方法: `read` 逐行定位 `packages/multi-workers/**` + `packages/coding-agent/{src,test}/**`；
> 只读枚举两份真实语料（`H:\git\E2Feature`、`E:\CLI_workspace\FeatureMigrator`）与合成临时夹具（系统 temp，仓库外）实测；
> `git show b8bc115ff` 取「新增配置键」的既定先例。所有事实带 `文件:行号`。

## 1 决策问题（DRQ-1）

1. 指纹函数落点与读成本：`_l3_round_verdict`（`conductor.py:1556`）状态门 `:1585-1586` 之前怎么插；
   `worker.log` 路径怎么拼、读多少字节、"读尾巴"helper 先例；指纹要不要持久字段、写哪里、
   与 `l3-verdict-provenance.json` 对齐还是另立。
2. 专用有界计数的机制：`state.used_rounds`（`state.py:224-249`）key 形状、loop 标签写点（`dispatch.py:359-360`）、
   `l3:{key}` / `repair:{key}` 先例（`conductor.py:2008,2017,2027`）、与 `l3_limit`（`:1858`）如何共存、上限从哪读。
3. 重掷分支改造：`conductor.py:1888-1914` 现状逐行 + 确切 diff 形状 + 与 `used >= l3_limit` 的先后。
4. 配置键注册全步骤（P-019/P-023）：`config.py:55`/`:79` + `status-model.ts` 镜像 + 冻结语料 +
   `test_p4_corpus_integrity` + 重冻 sha 步骤与同步测试。
5. `reason_code` 同步：`STALL_REASON_CODES`（`:4891-4904`）、`REASON_CODES`（`:4925-4927`）、
   `_recompute_l3_stall_code`（`:5348-5373`）、测试 `==12` 锁；AC-013 的 `_REQUIRED_FIELDS` 不可动。
6. timeline 事件 vs gate `reason_code` 对 TS 的影响；"两个都加" vs "只加 reason_code" 改动清单。
7. 测试矩阵：既有 Python 夹具风格 + G1 用例清单 + AC-014 非空洞对照；真实语料是否可做夹具。

## 2 方法与出处

- `read`：`autopilot/{conductor,state,dispatch,config,effective_config,gates,timeline,evidence}.py`、
  `launcher.py`、`mw_common.py`、`status-model.ts`、`monitor.ts`、`console.ts`、`test_autopilot_*.py`、`test/suite/autopilot-*.test.ts`。
- 跨仓 grep：定位 count/order 锁、golden sha 锁、`reason_code` 透传面。
- 只读语料枚举：`worker.log` 体积/命中行字节位置、`output.md` 节标题、`task.md` 的 `loop:`/`attempt:` 标签、
  各 key 的 L3 轮史与 gate。
- 合成探针（临时目录，仓库外）：把 `stream closed` 3 行日志 + harness 占位 `output.md` + 队列行喂给**真实**
  `conductor._l3_round_verdict`，实测当前返回值（见 F1.6）。
- 复算命令见 §6。

## 3 发现

### F1 指纹函数的落点、路径拼接、读成本与持久面（Q1）

**F1.1 落点：`_l3_round_verdict` 内、状态门之前。**
- 签名与 4 元组：`conductor.py:1556-1562`（`registration_out` 是既有 optional out-param 先例）。
- round task_key = `dispatch.task_key_for(key, f"l3-a{attempt}")`（`conductor.py:1580`；`task_key_for` = `f"ap-{owner}-{stem}"`，`dispatch.py:453-456`）。
- 状态门：`conductor.py:1585-1586`（`status in ("failed","needs-clarification")` ⇒ `("no-verdict", status, None, None)`）。
- 源路径 helper：`_l3_source_paths(key_dir, task_key)` = `key_dir/"workers"/task_key/{output.md,report.md}`
  （`conductor.py:1515-1517`；`_L3_SOURCE_ORDER` `:1475`）。
- 两节合格判据 `_l3_qualifies`（`:1530-1536`）；fail-closed 源解析 `_l3_resolve_source`（`:1538-1554`，
  任一可读源含 FAIL ⇒ below，且 veto 覆盖不合格源）。
- 4 元组长度被测试钉死：`test_autopilot_verdict_provenance_guard.py:637-655`（`_parse_l3_output`/`_md_section` 区域 sha + `tuple_len == 4`）；
  **第一槽 value 域未被钉死** ⇒ 可新增 `"aborted"`（推荐，长度不变）；备选是仿 `registration_out` 加 `abort_out` sink（`conductor.py:1561`）。

**F1.2 `worker.log` 路径：conductor 侧无 helper，按既有目录形状拼。**
- launcher 侧 helper 是 `launcher.py:53-54` `_worker_log_path(entry)` = `Path(entry["task_path"]).parent / "worker.log"`，
  入参是队列 entry dict（`:952`、`:961-962` 用它把子进程 stdout+stderr 合并写入）——conductor 无 entry dict，不可直接复用。
- conductor 既有等价形状 = `_l3_source_paths`（`:1515-1517`）的 `key_dir/"workers"/task_key/`。
  ⇒ 新增局部 helper `_l3_worker_log_path(key_dir, task_key)` = `key_dir/"workers"/task_key/"worker.log"`，与源路径同源。

**F1.3 读成本：只需尾 N KB；"读尾巴"先例 = `mw_common.parse_end_exit`。**
- 推荐模板：`mw_common.parse_end_exit`（`mw_common.py:2029-2051`）`open("rb")` + `seek(SEEK_END)` +
  `fh.seek(max(0, size - _TRACE_TAIL_BYTES))`，只读尾 `_TRACE_TAIL_BYTES = 64 * 1024`（`mw_common.py:2026`）；
  注释明写 "stat + tail-read so polling stays cheap"。
- **不适合**：`mw_common.read_log_tail`（`mw_common.py:1905-1911`）先 `read_text()` 读整文件再切片 —— 无字节上界。
- 语料实测（本次快照，§6 复算）：
  - 命中轮 6/6 的 `stream closed before response.completed` 是最后一条内容行，距 EOF `40` B，文件体积 `160~179` B；
  - 全部 `worker.log` = `878` 个（活语料，RQ-1 快照 844、前稿 845，随 spawn 漂移），max `14120` B、p95 `5101` B、p99 `9875` B、median `3218` B，**0 个 > 64 KiB**；
  - L3 轮 `worker.log` = `57` 个，max `14120` B。
  ⇒ 尾 64 KiB 一次读覆盖 100% 现存语料；建议新增 `_L3_WORKER_LOG_TAIL_BYTES = 64 * 1024` 并镜像 `parse_end_exit` 的 open/seek 模式。
  尾窗正/负例测试模板：`test_common.py:466-484`（`test_end_within_tail_window_found` / `test_end_beyond_tail_window_not_found`）。
- 顺序建议：先 tail-read `worker.log`（常规轮只付这一笔），命中 marker 才读 sources，避免给正常轮加两次文件读。

**F1.4 指纹谓词（AC-001/AC-002/AC-004 与 A 类回退同时成立）。**
- marker 常量：`"stream closed before response.completed"`（**子串**，不带 `WebSocket ` 前缀；RQ-1 F1 实测 6/6 无前缀；
  本仓唯一近似抛出点 `packages/ai/src/api/openai-codex-responses.ts:1377` 带前缀，子串匹配覆盖两者）。
- 推荐谓词（比只查 `_l3_qualifies` 更严，直接复用既有 fail-closed 解析器，使三类构成**划分**）：
  `stream_in_tail(worker.log) AND _l3_resolve_source(readable_sources) == ("below", None, None)`
  即"有中止行"且"本轮完全没有裁决内容"（无合格源、也无任何 FAIL 标记行）。
  - AC-001 正例：marker + `output.md` 缺两节（无 `report.md`）⇒ `resolve = (below,None,None)` ⇒ 命中；
  - AC-004 否定一：无 marker ⇒ 不命中；否定二：`output.md` 两节齐备 ⇒ `resolve` 至少 `meets` ⇒ 不命中；
  - AC-002 互斥（按构造）：A 类（`report.md` 合格）⇒ `meets`；C 类（两节 + FAIL）⇒ `below + fail_line`；
    只要 `resolve` 不是 `(below,None,None)` 就不是 aborted ⇒ 三种输入各只命中一类。
  - 优先级（写进 design）：真裁决（含 FAIL）> abort 指纹 > 载体不符；abort 只在"无任何裁决内容"时生效。
- AC-001 的 `done exit=0`（`worker.log` 的 `[worker] done exit=0` 行，非队列 status；RQ-1 F1）建议记录但不作为门：
  AC-004 的假阳性判据只列"无 stream 行 ∨ 两节齐备"；且 D 类 provider 403 轮（实测样本，`worker.log` 第 4 行
  `OpenAI API error (403): ...`）也有 `done exit=0`，不可判别。把它写进事件 `data`（`done_exit_zero`）。

**F1.5 持久字段：timeline 事件 + `data` 载荷（+ stall 时 gate `reason_code`）；不动 provenance sidecar。**
- 事件已支持结构化载荷：`Timeline.append(..., data: dict | None = None)`（`timeline.py:293-339`，`payload["data"] = dict(data)` `:338-339`）；
  TS `TimelineEvent.data?: Record<string, unknown>`（`status-model.ts:1001,1010`），parity 测试已放开 `data`
  （`test/suite/autopilot-event-parity.test.ts` "admits the optional `data` payload"）。
- 纯 timeline 不够持久：`timeline.jsonl` 轮转 `ROTATE_THRESHOLD_BYTES = 10 MiB` / `ROTATE_GENERATIONS = 2`（`timeline.py:104-105`）；
  gate `reason_code` 只在 stall 时落地，均不满足 AC-001 的"该轮记录 + 持久字段"。
- 不要污染 `l3-verdict-provenance.json`：`_l3_provenance_record`（`conductor.py:1620-1713`）要求 `deciding_source`，
  写点被 `if l3_source is not None` 前置（`:1915-1920`，aborted 轮零痕迹，RQ-1 F2）；其消费者
  `_xkey_below_records`（`:3287-3325`，按 `raw_verdict == "below"` 取红）、`_last_provenance_record`（`:5300-5311`）、
  done 事务的 recompute 源装配（`:6474-6487`，读 `raw_verdict`/`suspect`）都按"有裁决源"的形状读 —— 混入无源记录是 latent hazard。
- 推荐：aborted 轮发
  `timeline.append("l3-aborted", key=key, detail=..., data={round,task_key,worker_status,output_bytes,done_exit_zero,retry_used,retry_limit,recorded_at})`。
  若 DESIGN 还要 O(1) 单轮查表/doctor 可见面，再另立 `<key>/l3-abort-reports.json`
  （append-only、按 `task_key` 去重、tmp + `os.replace`，镜像 `_persist_l3_provenance`）—— 但不是 AC-001 的最小必需面，且新增写面。
- 第三个持久面 = gate `reason_code="l3-aborted"`（仅 stall 时，属 `REASON_CODES` 闭集，F5）。

**F1.6 当前行为实测（合成探针，仓库外 temp；证明 G1 的判据缺口）。**
用真实 `conductor._l3_round_verdict` 喂 4 个合成轮（`worker.log` 含/不含 marker、`output.md` 占位/两节齐备、队列行 failed/done）：

| 输入 | 当前返回 |
|---|---|
| marker + 占位 output.md + 行 `failed` | `('no-verdict','failed',None,None)` |
| marker + 占位 output.md + 行 `done` | `('below','done',None,None)` |
| 无 marker + 占位 output.md + 行 `failed` | `('no-verdict','failed',None,None)` |
| marker + `output.md` 两节齐备 + 行 `failed` | `('no-verdict','failed',None,None)`（状态门先短路） |

⇒ 第 1 行与第 3 行完全不可分（AC-001/AC-002 的核心缺口）；第 2 行会被判 `below`（与 A 类载体不符混同）。
⇒ 指纹必须挂在 `:1585-1586` 之前，且必须在状态门短路前读到 marker。

### F2 专用有界计数（Q2）

**F2.1 `used_rounds` 的形状（先例基础）。**
- `state.used_rounds(workers_dirs)`（`state.py:224-249`）：扫 `.agenticdoc/*/workers/*/task.md`，读 `loop:`/`attempt:` 标签，
  按 loop 去重 attempt 计数，返回 `{loop_label: distinct_attempt_count}`。
- 标签写点：`dispatch.render_task_md` 渲染 `loop: {loop}` / `attempt: {attempt}`（`dispatch.py:359-360`）。
- conductor 每 tick 派生一次：`rounds = state.used_rounds(_all_workers_dirs(project_root))`（`conductor.py:247`；
  `_all_workers_dirs` `:2415-2421`）；`_verify_loop` 读 `rounds.get(l3_loop, 0)`（`:1859`）。
- 现成范式：`repair:{key}` 独立成族（`conductor.py:2008` 读、`:2017` mark_stalled、`repair_base = f"repair-a{used}"` `:2005`、`:2027` dispatch），
  即"父回路计数不被子族消耗"。

**F2.2 三个候选机制。**
- 机制 A（推荐）：新增独立 loop 标签 `l3abort:{key}`，共享 stem 序号空间 `l3-a{N}`，`N = used + abort_used`。
  - `used = rounds.get("l3:{key}", 0)`（普通轮，保持预算语义）；`abort_used = rounds.get("l3abort:{key}", 0)`；`round_no = used + abort_used`（最新轮全局序号）。
  - 普通轮 dispatch：stem `l3-a{round_no+1}`，`loop="l3:{key}"`，`attempt=used+1`；
    abort 重掷轮：stem `l3-a{round_no+1}`，`loop="l3abort:{key}"`，`attempt=abort_used+1`。
  - `_l3_round_verdict(attempt=round_no)` 的 `task_key` 推导（`:1580`）无需改签名；in-flight 前缀检查 `ap-{key}-l3-`（`:1864-1866`）仍覆盖两种轮（stem 同前缀）。
  - 与 `l3_limit` 共存：`l3_limit` 只约束 `used`（普通轮）；abort 上限只约束 `abort_used`；两者互不消耗 ⇒ 满足 RQ-1 的"不占共享轮预算"。
  - 计数一致性（关键）：`proposition_stalled` 要求 `used_rounds == round_limit + credits_used`（`conductor.py:5043-5051`）。
    普通 stall 仍传 `used/l3_budget/(l3_limit-l3_budget)`（`:1903-1904,1997-2002`，stall 点 `used == l3_limit` 恒成立）；
    abort stall 传 `used_rounds=abort_used, round_limit=abort_limit, credits_used=0`（该点 `abort_used == abort_limit`）⇒ 两个族各自守恒，无需伪造 `credits_used`。
  - 代价（改动点已定位）：`_verify_loop` 内 `l3-a{used}`/`l3-a{used+1}`/`repair-a{used}` 改 `round_no`
    （`conductor.py:1861,1881,1886,1892,1895,1908,1909,1940,1941,1976,1980,2005,2033,2034`）；
    `_recompute_l3_stall_code`（`:5354`）与 `recompute_false_negative_class`（`:5395`）的 `used` 改 `used + abort_used`；
    `_stall_family`（`:5288-5301`）把 `l3abort:` 归入 family `"l3"`（否则 `recompute_stall_cause` 落 `advance-class`
    ⇒ `stalled-reason-drift`，`:5039-5042`）。
  - 无 abort 轮时 `round_no == used` ⇒ 与今天同一路径（语料 54 轮零漂移）。
- 机制 B：abort 重掷仍用 `loop="l3:{key}"`（消耗共享预算），专用计数另存。
  缺点：与 spec §2.4/RQ-1 的"不占共享轮预算"冲突；计数只能从 timeline 尾派生，而 `_timeline_has_event`（`:1817-1834`）
  是有界布尔去重，不能表达次数（RQ-2 已指出）。
- 机制 C：abort 重掷用 `loop="l3abort:{key}"` + 独立 stem 前缀 `l3abort-a{N}`。
  缺点：`_l3_round_verdict` 硬编码 `l3-a{attempt}`（`:1580`），跨命名空间无法只用一个 `attempt` 定位"最新轮"，需第二套指针 —— 比 A 复杂。
  ⇒ 推荐 A。

**F2.3 上限配置从哪读（配合 Q4）。**
- 新增 `l3_abort_retry_limit`（int，默认 `1`，`_INT_RANGES` 域建议 `(0, 10)`）；conductor 经
  `_load_effective_config`（`conductor.py:108-126`）拿到完整键集（`config.default_config()` 打底 + 原始文件覆盖 + machine 层覆盖），
  故 `cfg["l3_abort_retry_limit"]` 与 `cfg["round_budget"]` 一样可硬下标（`:1857`）。
- `l3_limit = l3_budget + _resume_credits(project_root, key)`（`:1858`；`_resume_credits` `:2660-2679`）保持不变；
  `abort_limit = max(0, int(cfg["l3_abort_retry_limit"]))` 是另一条上限。上限 `0` = 关闭重掷（aborted 轮直接 stall）。

**F2.4 语料轮史复核：机制 A 会改变"第二次 abort"的终止点（实测）。**
逐 key 读 `task.md` 标签 + `worker.log`（§6 复算）：

| key | L3 轮与 abort | 说明 |
|---|---|---|
| `feature-inline-marker-patchkit` | a1 abort, a2 abort, a3 正常 | 现状：a1→no-verdict 重掷 a2；a2→no-verdict 重掷 a3。机制 A（limit=1）：a2 是第二次 abort ⇒ 直接 stall（无 a3） |
| `feature-gui-time-mvp-board` | a1 abort, a2/a3 正常, a4 abort, a5 正常 | 同型：a4（第二次 abort）直接 stall（无 a5） |
| `feature-false-meets-remediation` | a1/a2 正常, a3 abort, a4 abort, a5 正常 | 同型 |

- 三 key 的 `round_budget = 2`（`.agenticdoc/_autopilot/config.json`），`used` 实际到 3/5/5 ⇒ 有 `_resume_credits`
  （approved `stalled` gate：gate-0009 / 0011,0014,0017 / 0015,0016,0018 —— 全 v1，无 `reason_code`）。
- 必须写进 design 的取舍：`abort_limit=1` 时机制 A 对"同一 key 第二次 abort"直接 stall，而现状会继续按共享预算重掷
  （这正是 AC-003"专用上限"的预期效果，但会在真实轮史里提前终止 a3/a5）。若 product 要求"预算耗尽前仍可重掷"，
  则 abort 分支耗尽后应回退既有 no-verdict 重掷（机制 A′：专用计数只决定是否打 `l3-aborted` 分类/是否走 abort 族，耗尽落回共享预算）。
  两种都自洽，但 F7.2 的 P3/P6 期望不同，需先拍板。

### F3 重掷分支改造（Q3）

**F3.1 `conductor.py:1852-1914` 现状逐行。**
- `:1852` `key_dir`；`:1853` `l3_loop = f"l3:{key}"`；
- `:1857-1859` `l3_budget = max(1,int(cfg["round_budget"]))`、`l3_limit = l3_budget + _resume_credits(...)`、`used = rounds.get(l3_loop, 0)`；
- `:1860-1863` `l3_report_src = key_dir/"workers"/task_key_for(key,f"l3-a{used}")/"output.md"`；
- `:1864-1866` 在飞等待（前缀 `ap-{key}-l3-` / `ap-{key}-repair-`）；
- `:1867-1875` `used == 0` 首轮派发 `l3-a1`（`loop=l3_loop, attempt=1`）；
- `:1876-1880` `_l3_round_verdict(project_root, rows, key, used, registration_out=...)`；
- `:1881` `round_key = task_key_for(key, f"l3-a{used}")`；`:1882-1887` `l3_source_rel`（缺省 output.md）；
- `:1888` `if verdict == "no-verdict":` → `:1892` 重算 `round_key` → `:1893-1896` 发 `l3-no-verdict`
  （detail `l3-a{used} worker status={worker_status} → re-review`）→ `:1897` `if used >= l3_limit:` stall
  （`reason_code="l3-no-verdict"`, `loop=l3_loop`, `used_rounds=used`, `round_limit=l3_budget`, `credits_used=l3_limit-l3_budget`）
  → 否则 `:1907-1913` 派 `l3-a{used+1}`（`loop=l3_loop, attempt=used+1`）→ `:1914` `return result.ok`。
- 后续分支复用同一 `used`：`:1915-1946` provenance suspect 重掷、`:1947-1992` meets + evidence reprompt、`:1994-2004` `used >= l3_limit ⇒ l3-below`、`:2005-2040` repair / 下一 L3 轮。

**F3.2 确切 diff 形状（只读推演，不改）。**
```diff
@@ _verify_loop
-    l3_loop = f"l3:{key}"
+    l3_loop = f"l3:{key}"
+    l3_abort_loop = f"l3abort:{key}"           # 专用有界计数（机制 A）
     l3_budget = max(1, int(cfg["round_budget"]))
     l3_limit = l3_budget + _resume_credits(project_root, key)      # 不变
-    used = rounds.get(l3_loop, 0)
+    abort_limit = max(0, int(cfg["l3_abort_retry_limit"]))          # 新键
+    used = rounds.get(l3_loop, 0)                                  # 普通轮预算（语义不变）
+    abort_used = rounds.get(l3_abort_loop, 0)                      # 专用计数
+    round_no = used + abort_used                                   # 最新一轮全局序号
     l3_report_src = (
-        key_dir / "workers" / dispatch.task_key_for(key, f"l3-a{used}")
+        key_dir / "workers" / dispatch.task_key_for(key, f"l3-a{round_no}")
@@
-    if used == 0:
+    if round_no == 0:
@@
-    verdict, worker_status, l3_source, fail_line = _l3_round_verdict(
-        project_root, rows, key, used,
+    verdict, worker_status, l3_source, fail_line = _l3_round_verdict(
+        project_root, rows, key, round_no,
@@
-    round_key = dispatch.task_key_for(key, f"l3-a{used}")
+    round_key = dispatch.task_key_for(key, f"l3-a{round_no}")
+    if verdict == "aborted":                    # 新分支：必须在 no-verdict / 预算判定之前
+        st.timeline.append(
+            "l3-aborted", key=key,
+            detail=f"l3-a{round_no} worker status={worker_status} stream-closed"
+                   f" → reroll {abort_used + 1}/{abort_limit}",
+            data={"round": round_no, "task_key": round_key,
+                  "worker_status": worker_status, "output_bytes": <int|None>,
+                  "done_exit_zero": <bool>, "retry_used": abort_used,
+                  "retry_limit": abort_limit, "recorded_at": _iso_now()},
+        )
+        if abort_used < abort_limit:
+            result = dispatch.dispatch(
+                project_root, key, f"l3-a{round_no + 1}", "reviewer",
+                _l3_prompt(key, round_no + 1),
+                loop=l3_abort_loop, attempt=abort_used + 1,
+                read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
+                timeline=st.timeline,
+            )
+            return result.ok
+        _persist_l3_verdict(key_dir, "below", l3_report_src, st=st)
+        mark_stalled(
+            project_root, st, key,
+            f"L3 流中止（{round_key}）重掷 {abort_used}/{abort_limit} 次仍未裁决",
+            reason_code="l3-aborted", loop=l3_abort_loop,
+            used_rounds=abort_used, round_limit=abort_limit, credits_used=0,
+        )
+        return False
     if verdict == "no-verdict":
-        round_key = dispatch.task_key_for(key, f"l3-a{used}")
+        round_key = dispatch.task_key_for(key, f"l3-a{round_no}")
         st.timeline.append(
             "l3-no-verdict", key=key,
-            detail=f"l3-a{used} worker status={worker_status} → re-review",
+            detail=f"l3-a{round_no} worker status={worker_status} → re-review",
         )
         if used >= l3_limit:            # 预算判据仍只数普通轮，abort 轮不消耗它
             ...
         result = dispatch.dispatch(
-            project_root, key, f"l3-a{used + 1}", "reviewer",
-            _l3_prompt(key, used + 1),
+            project_root, key, f"l3-a{round_no + 1}", "reviewer",
+            _l3_prompt(key, round_no + 1),
             loop=l3_loop, attempt=used + 1,
             ...
```
- 其余 `l3-a{used}`/`l3-a{used+1}`/`repair-a{used}`（`:1886,1940,1941,1976,1980,2005,2033,2034`）同改 `round_no`；`attempt=` 保持 `used+1` / `repair_used+1`。

**F3.3 返回值载体。**
- 推荐：第一槽 value 域加 `"aborted"`（4 元组长度不变，`tuple_len == 4` 锁不破，`test_autopilot_verdict_provenance_guard.py:637-655`）。
- 备选：加 `abort_out: dict | None = None` sink（镜像 `registration_out` `:1561`），第一槽仍 `"no-verdict"`；缺点：`_verify_loop` 多一个变量，`_recompute_l3_stall_code` 也要读 sink。
- 调用方影响（全仓仅 3 处）：`_verify_loop:1877`、`_recompute_l3_stall_code:5361`、`recompute_false_negative_class:5399`。

**F3.4 与 `used >= l3_limit` 的先后（不破坏既有 6/6）。**
- abort 分支必须在 `verdict == "no-verdict"` 与其内 `used >= l3_limit` 之前（AC-003 的"专用计数未耗尽则重掷"要在共享预算耗尽时仍发生，如 `round_budget=1` + 一次 abort）。
- 48 个负例（RQ-1 F5：21 两节齐备 + 24 report 回退 + 1 散文 report + 2 provider 403）`worker.log` 无 marker
  ⇒ F1.4 谓词不命中 ⇒ 走既有 `no-verdict`/`below`/`meets` 路径，逐字节不变；6 个正例全部转 `aborted` 并进入专用重掷。
- 三处调用方都拿到 `"aborted"`：`_verify_loop` 走新分支；`_recompute_l3_stall_code` 须在 `:5369` 前加 `if verdict == "aborted": return "l3-aborted"`；
  `recompute_false_negative_class` 落 `undecidable`（`:5404-5408` 只有 meets/below 两个出口）⇒ 该门不会被自动 approve（fail-closed）。

### F4 配置键 `l3_abort_retry_limit` 注册全步骤（Q4）

**F4.1 先例**：`git show b8bc115ff`（`auto_gate_mode` 上线）改了
`config.py`（`DEFAULT_CONFIG` + registry + docstring）→ 语料 `test/fixtures/autopilot-config-corpus.json`（+2 例）→
`test_autopilot_config_parity.py`（`FROZEN_CORPUS_SHA256`/`COUNT` + 13→14）→ `test_autopilot_config.py` / `test_autopilot_effective_config.py`（计数/顺序锁）→
`status-model.ts`（6 处镜像）→ TS `autopilot-config-parity.test.ts` / `autopilot-config-sync.test.ts` / `autopilot-console.test.ts`（计数/深比较锁）。

**F4.2 Python 侧必改。**
1. `autopilot/config.py:55-70` `DEFAULT_CONFIG` 末尾追加 `"l3_abort_retry_limit": 1`（追加在 `auto_gate_mode` 之后，保持"新键最后"惯例）；
2. `autopilot/config.py:79-88` `_INT_RANGES` 追加 `"l3_abort_retry_limit": (0, 10)`；
3. `autopilot/config.py:11-38` 模块 docstring 字段表 + `:154` "complete 14-key view" → 15；
4. `autopilot/effective_config.py:62-66` `EFFECTIVE_KEYS` 不动（仍 2 个 xkey 键；新键 project/default-only，与 `auto_gate_mode` 同范式）；
   其 docstring 的 "13-key"（`:1-50` 多处）与 `conductor.py:111` "complete 13-key view" 是既有陈旧漂移（实为 14），顺手改 15；
5. 消费点：`conductor.py:1858` 邻域新增 `abort_limit`（F2.3）。

**F4.3 TS 侧 `status-model.ts` 六处镜像（与 b8bc115ff 同点位）。**
- 接口字段：`:75-106`（`auto_gate_mode` 之后加 `l3_abort_retry_limit: number`）；
- `DEFAULT_CONFIG`：`:108-123`；
- `INT_RANGES`：`:147-156`；
- `readConfig` 的 `intOf` 键联合：`:272-282`；
- `readConfig` 的 `merged` 对象：`:287-302`；
- `saveConfig` 的 `ordered` 对象：`:313-328`（顺序 = `DEFAULT_CONFIG` 顺序，漏一处即 byte parity 红）。

**F4.4 跨语言冻结语料 + 重冻 sha 的确切步骤。**
- 语料文件：`packages/multi-workers/test/fixtures/autopilot-config-corpus.json`（`{"schema","cases"}`，当前 55 例，sha 实测
  `c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6`，与两侧冻结常量一致）。
- 冻结常量两处（必须同时改）：`test_autopilot_config_parity.py:60-61`（`FROZEN_CORPUS_SHA256` / `FROZEN_CORPUS_COUNT=55`）与
  `test/suite/autopilot-config-sync.test.ts:38-39`（TS 副本，P4 主判）。
- 必须新增 1 个单键 accept 例，否则 `test_p6_partial_single_key` 的 `assert covered == expected_keys`（`test_autopilot_config_parity.py:434`）红 ——
  `covered` 只由"接受且 payload 恰好 1 键"的语料累积（`_single_key_cases` `:298-307`、`:414-433`），当前 14/14 键各有单键例。
  建议：`{"id":"partial-key-l3_abort_retry_limit","categories":["D2"],"payload_text":"{\"l3_abort_retry_limit\": 1}","expected":{"verdict":"accept","error_fields":[]}}`。
- 建议同时加 1 个越界 reject 例（fail-closed）：`{"l3_abort_retry_limit": 11}` → `reject` / `error_fields=["l3_abort_retry_limit"]`。计数 55→56（或 57）。
- 重冻步骤（顺序执行）：
  1. 编辑语料 JSON（加上述 1~2 例；只增例，不改既有语义 —— T-11 契约）；
  2. 算新 sha：`python -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('packages/multi-workers/test/fixtures/autopilot-config-corpus.json').read_bytes()).hexdigest())"`；
  3. 更新 `test_autopilot_config_parity.py:60`（sha）与 `:61`（count）；
  4. 更新 `test/suite/autopilot-config-sync.test.ts:38-39`（sha + count）；
  5. 跑 `test_p4_corpus_integrity`（`test_autopilot_config_parity.py:310-321`：sha + count + D1~D6 覆盖 + 字面量锚）确认绿；
  6. 跑 `test_p1/p2/p3/p6`（`:324-439`）与 TS `autopilot-config-parity.test.ts` + `autopilot-config-sync.test.ts`。
- P-023 咽喉点（grep 证明）：`FROZEN_CORPUS_*` 只存在于上述 2 个文件；P5 镜像判由 `autopilot-config-sync.test.ts:153-181` 以真实 Python 子进程 dump 逐字段比对（不写死期望）。

**F4.5 需同步的计数/顺序/形状锁（逐个 file:line，漏一处即红）。**
- Python：
  - `test_autopilot_config.py:112-121`（`len==14`→15、`:116` `[-1]=="auto_gate_mode"`→新键、`:117-118` 向后顺移）、`:136-139`（`default_config()`/`load_effective` 14→15）、`:126,136` 注释；
  - `test_autopilot_gate_schema_v2.py:349`（`[-1]=="auto_gate_mode"`→新键）；
  - `test_autopilot_effective_config.py:70-73`（`len(eff.values)==14`→15）、`:183,204-207`（`len==14`→15 与注释）；
  - `test_autopilot_config_parity.py:23,166,392,422-426,437`（注释/`len==14`/`[VERIFY] effective_view_14`）；
  - `test_mw_autopilot_cli.py:120-123`（`len(stored)==14`→15；`:120` 已断言 `set(stored)==set(DEFAULT_CONFIG)`，会跟随）；
  - `test_autopilot_readcap_injection.py:996-1001` 的 `_GOLDEN_REGRESSION_SHA256["test_autopilot_config.py"]` 是 byte-exact 锁：
    只要编辑 `test_autopilot_config.py`（14→15）就必须重冻该 sha（`:1009-1011` 断言），否则该用例红。上稿遗漏，本条为新增发现。
- TS：
  - `test/suite/autopilot-config-parity.test.ts:17-18,119,343,355-361,372,376`（注释 + 14→15）；
  - `test/suite/autopilot-config-sync.test.ts:11`（注释）、`:38-39`（冻结常量）、`:168`（注释）；`:170-178` 的"注册表恰好划分 N 键"由 Python dump 动态推导，新增键只要注册表齐全即自动通过；
  - `test/suite/autopilot-console.test.ts:869-899`（`toHaveLength(14)`→15、`at(-1)` 新键、`INT_RANGES` 顺序表加一行；`:881-884` machine-overridable 仍恰为 2 键的负断言不变）、`:1194-1212`（`enabled` 深比较对象 + `toHaveLength(14)`→15）。
- 文档/审计面（不红但 P-019 要求列全）：`packages/multi-workers/README.md:219-227` 配置表、两包 `CHANGELOG.md` 的 `[Unreleased]`、`packages/multi-workers/UPDATE.md` §6。

### F5 `reason_code` 同步（Q5）

**F5.1 必须改（若采纳 `l3-aborted` 作为 stall code）。**
- `STALL_REASON_CODES`（`conductor.py:4891-4904`，现 12 项）追加 `"l3-aborted"`；`REASON_CODES`（`:4925-4927`）由其推导，自动包含
  （实测 `len(STALL)=12`、`len(PREDICATE)=23`、`len(ENGINE)=10`、`len(REASON_CODES)=45`）。
- 新增 mark_stalled 调用点：abort 预算耗尽分支（F3.2）用 `reason_code="l3-aborted"`。
- `_recompute_l3_stall_code`（`:5348-5373`）：在 `if verdict == "no-verdict"`（`:5369-5370`）之前加 `if verdict == "aborted": return "l3-aborted"`；
  `used` 改为 `used + abort_used`（机制 A），否则会评估错轮。
- `_stall_family`（`:5288-5301`）：`l3abort:` 归入 `"l3"`（否则 `recompute_stall_cause` 走 `advance-class` ⇒ `stalled-reason-drift`）。
- 测试锁：`test_autopilot_auto_decision.py:299-307`（`:301` `==12`→13；`:306-307` `[VERIFY]` 自动跟随）、
  `:330-339`（`:333` `len(calls)==12`→13，且 `:338` `codes == set(STALL_REASON_CODES)` 要求新代码必须有调用点）。
- 注释同步：`conductor.py:4890` "12 `mark_stalled` call sites"、`mw_common.py:2287-2295` "the 12 `mark_stalled` call sites"。

**F5.2 不能改（AC-013 / 冻结面）。**
- `gates._REQUIRED_FIELDS`（`gates.py:138-145`，导入期断言 `len==6`）一格不加；`reason_code` 本就是可选 v2 字段（`gates.py:102`），新原因码不触 required 面 ⇒ AC-013 成立。
- `FRONTMATTER_FIELDS` 顺序/允许集（`gates.py:87-131`）不动。
- `_L3_SOURCE_ORDER`（`:1475`）、FAIL 正则族（`:1478-1508`）、`_parse_l3_output`（`:1411-1431`）、`_l3_resolve_source`（`:1538-1554`）不动（spec §1.4：不改 L3 严格性）。
- `_l3_round_verdict` 4 元组长度（`test_autopilot_verdict_provenance_guard.py:637-655`）不动。
- 历史 gate 全部 parse 成功：21 个 E2 gate 全 v1（无 `reason_code`），新码只影响新 gate。

### F6 timeline 事件 vs gate `reason_code`：对 TS 的影响（Q6）

**事实。**
- Python 事件词汇 `timeline.EVENT_TYPES`（`timeline.py:67-96`，`l3-no-verdict` `:84`）；TS 镜像 `status-model.ts:962-990`（`l3-no-verdict` `:979`）。
- parity 判据 = 集合相等（`test/suite/autopilot-event-parity.test.ts:72-98`，两侧差集均须为空；明文 "cardinality is recorded, never the judge"，无魔数锁）。
  TS `NEW_EVENT_TYPES`（`:37-44`）只是上一 key 的文档列表，新名不必须入列。
- Python 侧另有计数锁：`test_autopilot_timeline.py:48`（`len(EVENT_TYPES)==23`）、`:53`（`len(events)==23`）、`:54`（`range(1,24)`）。
- gate `reason_code` 在 TS 是透传、无闭集校验：`status-model.ts:894`（`reasonCode: optional("reason_code")`）、
  `monitor.ts:108-109,226,246,782-783`、`console.ts:409`。
- 事件渲染通用：`console.ts:512` 用 `nonBeatFilter()`（`console.ts:61`），`:525` 直接打印 `ev.ev`，无 per-event 分支；`nonBeatFilter()`（`status-model.ts:994-999`）自动收录新事件。

**改动清单。**
- "两个都加"（推荐，AC-001 要求 timeline 事件 + 持久字段）：
  - Python：`timeline.py:67-96` 加 `"l3-aborted"`（23→24）；`conductor` 发事件（F3.2）；`STALL_REASON_CODES` +1（F5.1）；
    `test_autopilot_timeline.py:48,53,54` 23→24。
  - TS：`status-model.ts:962-990` 加 `"l3-aborted"`（集合相等自动锁两侧；console/monitor 零改）。
  - `reason_code` 仅 Python（TS 透传）。
- "只加 reason_code"（不满足 AC-001）：
  - Python：仅 `STALL_REASON_CODES` / `_recompute_l3_stall_code` / 测试锁；`timeline.py` 与 `test_autopilot_timeline.py` 零改。
  - TS：零改。
  - 缺口：AC-001 明写"timeline 写入机器可读的 `l3-aborted` 标记（事件 + 持久字段）"，无事件即无该持久面 ⇒ 不可取。

### F7 测试矩阵（Q7）

**F7.1 既有命名/夹具风格。**
- 模块级 `test_autopilot_*.py`（34 个）；L3 相关代表：`test_autopilot_verdict_source_fallback.py`、`test_autopilot_verdict_provenance_guard.py`、`test_autopilot_stall.py`、`test_autopilot_conductor_exec.py`、`test_autopilot_fail_marker_forms.py`。
- 共享 harness = `test_autopilot_conductor_exec.py`：`_project`(`:34-42`)、`_key_project`(`:44-73`)、`_verify_key_project`(`:389-401`)、
  `_state`(`:76-79`)、`_events`(`:81-83`)、`_rows`(`:85-90`)、`_set_row`(`:92-101`)、`_worker_output`(`:103-107`)、
  `_tasks`(`:109-116`)、`_fake_advance_factory`(`:160-184`)、`_L3_MEETS`/`_L3_BELOW`(`:131-157`)、`_verify`(`:24-25`)。
  其它模块 `import test_autopilot_conductor_exec as harness` 后逐名别名（`test_autopilot_stall.py:19-30`）。
- 语义：真实 `conductor.tick` 链 + 队列行状态翻转 + 合成 `output.md`；advance 用 gate-validating fake。
  现无任何写 `worker.log` 的 harness helper（grep `worker.log` 在测试里只出现在 launcher/rag 套件）⇒ G1 需新增局部 helper。
- L3 负例模板：`test_autopilot_stall.py:396-417`（`test_l3_worker_failure_is_no_verdict`）、`:420-441`
  （`test_l3_failed_worker_with_placeholder_output_is_still_no_verdict`，181 B 占位）、`:444-463`（`test_l3_no_verdict_stall_reason_names_worker`）。
- 尾窗读模板：`test_common.py:466-484`。`_verify` 打印 `[VERIFY] VC-0NN: k=v`；自审用例统计 `[VERIFY]` 事实（`test_autopilot_verdict_source_fallback.py:76-86`）。
- 运行：`cd packages/multi-workers && python -m pytest -q test_autopilot_<x>.py`；全非 e2e 用仓库根 `./test.sh`。

**F7.2 G1 用例清单（新建 `test_autopilot_l3_stream_abort.py`，import harness）。**

| # | 用例（建议名） | 输入夹具 | 断言 |
|---|---|---|---|
| P1 | `test_stream_abort_round_is_marked_and_rerolls` | `worker.log` = 真实 3 行形状（`[worker] start…` / `[worker] done exit=0 …` / `stream closed before response.completed`）；`output.md` = harness 占位（无两节）；行 `failed` | `l3-aborted` 事件存在且 `data.round/task_key/worker_status/retry_used=0/retry_limit=1`；派 `ap-k1-l3-a2` 且 `task.md` 有 `loop: l3abort:k1` / `attempt: 1`；`state.used_rounds(...)["l3abort:k1"]==1`；无 `l3-verdict-provenance.json` 记录 |
| P2 | `test_stream_abort_reroll_verdict_advances` | P1 后给 a2 写 `_L3_MEETS`，行 `done` | `tick` ⇒ done 事务（QG/achieved/PASS/advance 各 1），key done（AC-003 后半"重掷出裁决则正常推进"） |
| P3 | `test_second_abort_stalls_with_dedicated_reason` | 两轮都 abort（limit=1） | 建 stalled 门：`reason_code=l3-aborted`、`loop=l3abort:k1`；`recompute_stall_cause(...)=="l3-aborted"`（无 drift）；无 `l3-a3`；门计数 `used_rounds=1, round_limit=1, credits_used=0` |
| P4 | `test_abort_does_not_consume_shared_budget` | `round_budget=1`（`l3_limit=1`）+ 一轮 abort | 仍重掷（专用计数），且 `rounds["l3:k1"]` 不变；随后普通 no-verdict 轮才 `used>=l3_limit` stall（`l3-no-verdict`） |
| P5 | `test_abort_limit_zero_stalls_immediately` | `l3_abort_retry_limit=0` + 一轮 abort | 直接 stall `l3-aborted`（`used_rounds=0, round_limit=0, credits_used=0`），无 `l3-a2` |
| P6 | `test_abort_limit_two_allows_two_rerolls` | limit=2 + 连续 abort | 派 a2、a3；第三次 abort 才 stall；`used_rounds["l3abort:k1"]==2` |
| P7 | `test_abort_event_data_shape_frozen` | P1 夹具 | `data` 键集 == `{round,task_key,worker_status,output_bytes,done_exit_zero,retry_used,retry_limit,recorded_at}` |
| P8 | `test_abort_limit_default_is_one` | `config.default_config()` | `DEFAULT_CONFIG["l3_abort_retry_limit"] == 1`；`_INT_RANGES["l3_abort_retry_limit"] == (0,10)`（配置面回归） |
| N1 | `test_no_stream_line_stays_no_verdict` | `worker.log` 无 marker；`output.md` 占位；行 `failed` | `l3-no-verdict`；重掷 a2 且 `loop: l3:k1`（既有行为；AC-004 第一句） |
| N2 | `test_stream_line_with_both_sections_is_not_aborted` | `output.md=_L3_MEETS` + marker；行 `done` | 走 meets ⇒ done；无 `l3-aborted`（AC-004 第二句） |
| N3 | `test_stream_line_with_report_fallback_is_not_aborted` | `output.md` 缺两节 + `report.md=_L3_MEETS` + marker；行 `done` | `_l3_resolve_source` ⇒ meets（A 类）；无 aborted（AC-002 互斥） |
| N4 | `test_fail_marker_is_below_not_aborted` | `output.md` 含 FAIL + marker | below ⇒ repair 路径；无 aborted（C 类） |
| N5 | `test_provider_403_placeholder_stays_no_verdict` | 真实 D 类形状（`OpenAI API error (403): …`，无 marker，占位，行 `failed`） | `l3-no-verdict`；无 aborted（假阳性 = 0） |
| N6 | `test_marker_beyond_tail_window_not_detected` | `worker.log` > 64 KiB，marker 埋在 >64 KiB 之后 | 不判 aborted（尾窗契约；模板 `test_common.py:466-484`） |
| X1 | `test_three_way_classification_exclusive` | 同一 fixture 分别造 A/B/C，直接调 `_l3_round_verdict` | 三者输出两两不同且各只命中一类（`meets` / `aborted` / `below`+`fail_line`；AC-002） |
| X2 | `test_abort_fingerprint_counterfactual` | monkeypatch `conductor._L3_ABORT_STREAM_MARKER`（或指纹 helper → 恒 False）后重跑 P1 | 事件变 `l3-no-verdict`、重掷 `loop: l3:k1`、无 `data`；还原后恢复 aborted ⇒ 摘掉指纹即转红（AC-014 非空洞，先例 `test_autopilot_effective_config.py:646-655`） |

- AC-014 的第二种对照（夹具级）：把 P1 的 `worker.log` 去掉 marker 行 ⇒ 断言必须红（已写成 N1，两者都留）。
- 若无新配置键（不采纳 F4），P4/P5/P6/P8 改从固定常量驱动；但不建议（AC-003 要求"可配置"）。

**F7.3 真实语料可否直接做夹具。**
- 不可：单测不得依赖项目外路径（先例 `test_autopilot_verdict_source_fallback.py:26-27` 自审 "absence of real-tree reads"；其 AC-006 用 fixture 合成复现语料类）。
- 做法：把 6 个真实轮的最小字节形状复刻成字符串常量（实测 3 行；≤179 B；`output.md` = harness 占位，
  首行 `## TL;DR`、末行 `## Exit Reason` + `Agent settled after N tool call(s).`）。真实语料重算留作只读证据脚本（不进 CI），
  并保留计数漂移说明（844 → 878 量级的活语料）。

## 4 结论 → 决策映射

1. 指纹落点：`_l3_round_verdict`（`conductor.py:1556`）内、状态门 `:1585-1586` 之前插入
   `_l3_stream_aborted(key_dir, task_key)`（F1.1/F1.4/F1.6）⇒ DESIGN 需明示"新增一次 worker.log 尾读（≤64 KiB）"，
   不再宣称零额外读取（spec §2.2 已修正）。
2. 路径/读法：路径 = `key_dir/"workers"/task_key/"worker.log"`（同 `_l3_source_paths:1515-1517` 形状）；
   读法镜像 `mw_common.parse_end_exit:2029-2051` 的尾 64 KiB（`_TRACE_TAIL_BYTES:2026`）；不要用 `read_log_tail:1905-1911`。
3. 持久字段：`l3-aborted` timeline 事件 + `data` 载荷为主（`timeline.py:293-339`、`status-model.ts:1001,1010`）；
   stall 时 gate `reason_code=l3-aborted`；不动 provenance sidecar（`:1510/1620-1713/1915`，消费者 `:3287-3325/5300/6474-6487`）。
4. 专用计数：机制 A（`l3abort:{key}` 标签 + 共享 stem 序号 `l3-a{used+abort_used}`），由 `state.used_rounds:224-249` 派生；
   `l3_limit:1858` 语义不变；新键 `l3_abort_retry_limit`（默认 1，域 0..10）。待 PM/design 拍板：第二次 abort 是"直接 stall"（机制 A）
   还是"回落共享预算"（A′）—— 见 F2.4。
5. 重掷分支：`:1888` 之前加 `if verdict == "aborted":`（专用计数未耗尽 → 派 `l3-a{round_no+1}` / `loop=l3abort`；
   耗尽 → `mark_stalled(reason_code="l3-aborted", used_rounds=abort_used, round_limit=abort_limit, credits_used=0)`）；
   所有 `l3-a{used…}` / `repair-a{used}` 改 `round_no`（F3.2）。
6. 配置键：F4 全清单（Python 5 处 + TS 6 处镜像 + 语料 1 单键 accept 例（+1 reject 例）+ 2 处 `FROZEN_CORPUS_*` + 计数锁含
   `test_autopilot_readcap_injection.py` 的 golden sha + 文档），重冻顺序见 F4.4。
7. reason_code：F5.1 必改 / F5.2 不可改；`_REQUIRED_FIELDS` 一格不加 ⇒ AC-013 成立。
8. TS 面：走"两个都加"（事件 + reason_code）；TS 只需 `status-model.ts:962-990` 加一个名字，Python 侧补 `test_autopilot_timeline.py:48/53/54` 23→24（F6）。
9. 测试：F7.2 用例表，合成夹具、不读真实树；X2（+N1）提供 AC-014 非空洞对照。

## 5 数据缺口与风险

- `stream closed before response.completed` 的逐字节出处不在本仓（RQ-1 F1：网关/旧构建）⇒ 谓词只按子串，DESIGN 不得声称"该文本由 pi 产生"。
- 谓词对"`output.md` 完全缺失 + 有 marker"的轮也会命中（`sources` 为空 ⇒ `resolve` 返回 `(below,None,None)`）。
  AC-001 字面暗含 `output.md` 存在；AC-004 未排除该形态。待 design 拍板：按 AC-004 最小门（不额外要求 `output.md` 存在，推荐），或加 `output_path.is_file()`。
- 机制 A 使 `round_no != used`（存在 abort 轮时）；任何仍以 `used` 当"轮号"的第三处消费者须一起审。已定位：`_recompute_l3_stall_code:5354`、
  `recompute_false_negative_class:5395`；全仓 `l3-a{used}` 仅在 `_verify_loop` 内（grep 复核）。
- `abort_limit` 默认 1 会改变真实轮史里的终止点（F2.4）⇒ 属行为变更，不是纯分类；design 需显式确认。
- 活语料漂移：`worker.log` 计数 RQ-1 冻结 844 → 本次 878；`max=14120` 稳定。语料类结论以 RQ-1 快照为准，单测必须合成夹具。
- 配置键数量/顺序锁面宽（Python 5 + TS 5 + 语料 2 + golden sha 1），漏一处即使功能正确也红；F4.5 已逐条列坐标。

## 6 复算脚本（只读）

```python
# marker 命中轮的字节位置与体积（实测 6/6：距 EOF 40B、为最后一条内容行）
from pathlib import Path
NEEDLE = b"stream closed before response.completed"
for root in (Path(r"H:\git\E2Feature"), Path(r"E:\CLI_workspace\FeatureMigrator")):
    for p in (root / ".agenticdoc").glob("*/workers/*/worker.log"):
        data = p.read_bytes()
        i = data.find(NEEDLE)
        if i >= 0:
            print(p.parent.name, "size", len(data), "from_eof", len(data) - i)
```

```python
# worker.log 体积分布（本次实测 n=878, max=14120, p95=5101, p99=9875, >64KiB=0）
from pathlib import Path
sizes = []
for root in (Path(r"H:\git\E2Feature"), Path(r"E:\CLI_workspace\FeatureMigrator")):
    sizes += [p.stat().st_size for p in (root / ".agenticdoc").rglob("worker.log")]
sizes.sort(); n = len(sizes)
print("n", n, "max", sizes[-1], "p50", sizes[n // 2], "p95", sizes[int(n * .95)], "over64k", sum(s > 65536 for s in sizes))
```

```python
# 计数锁现状（本仓，实测）
import sys; sys.path.insert(0, "packages/multi-workers")
from autopilot import config, conductor, timeline
print("default_keys", len(config.DEFAULT_CONFIG))        # 14
print("stall_codes", len(conductor.STALL_REASON_CODES))  # 12
print("reason_codes", len(conductor.REASON_CODES))       # 45
print("event_types", len(timeline.EVENT_TYPES))          # 23
import hashlib, pathlib
print("corpus_sha", hashlib.sha256(pathlib.Path(
    "packages/multi-workers/test/fixtures/autopilot-config-corpus.json").read_bytes()).hexdigest())
```

```python
# 合成探针：当前 _l3_round_verdict 对 abort 轮的返回（临时目录，仓库外；结果见 F1.6）
# 构造 .agenticdoc/<key>/workers/ap-<key>-l3-a1/{task.md,worker.log,output.md} + _workers.parallel 行，
# 然后 conductor._l3_round_verdict(root, rows, key, 1)。
```

[VERIFY] DRQ-1: default_keys=14 stall_codes=12 reason_codes=45 event_types=23 corpus_sha=c97eeafc087bc2ef311d4422f84f8359ac5dd2f7f4ce73e1d8c0b4db4ddcf2b6 corpus_cases=55(frozen,measured) marker_rounds=6/6 from_eof=40B(last_content_line,size160-179B) worker_log_max=14120B n=878(live;p50=3218,p95=5101,p99=9875,>64KiB=0) l3_worker_logs=57 current_verdict_probe=failed+marker->no-verdict, done+placeholder+marker->below, no-marker+failed->no-verdict, both-sections+failed->no-verdict fingerprint_site=conductor.py:1556 before_status_gate=conductor.py:1585-1586 worker_log_path=key_dir/workers/task_key/worker.log(conductor.py:1515-1517 shape) tail_read_precedent=mw_common.py:2029-2051(_TRACE_TAIL_BYTES=64KiB@2026) read_log_tail=whole-file@mw_common.py:1905-1911 reroll_branch=conductor.py:1888-1914 l3_limit@1858 used_rounds=state.py:224-249 loop_labels=dispatch.py:359-360 repair_precedent=conductor.py:2005,2008,2017,2027 event_data=timeline.py:293-339+status-model.ts:1001,1010 provenance_sidecar=conductor.py:1510,1620-1713,1915(consumers:3287-3325,5300-5311,6474-6487;not_extended) stall_reason_codes=conductor.py:4891-4904+4925-4927 recompute=conductor.py:5348-5373 stall_family=conductor.py:5288-5301 stall_count_invariant=conductor.py:5043-5051 test_locks=test_autopilot_auto_decision.py:301,333+test_autopilot_timeline.py:48,53,54 config_mirror=status-model.ts:75-106,108-123,147-156,272-282,287-302,313-328 corpus_integrity=test_autopilot_config_parity.py:310-321 refreeze=test_autopilot_config_parity.py:60-61+autopilot-config-sync.test.ts:38-39 p6_single_key_lock=test_autopilot_config_parity.py:434 golden_sha_lock=test_autopilot_readcap_injection.py:996-1001 print_locks=test_autopilot_config.py:112-121,136-139+test_autopilot_gate_schema_v2.py:349+test_autopilot_effective_config.py:70-73,204-207+test_mw_autopilot_cli.py:120-123+autopilot-console.test.ts:869-899,1194-1212 required_fields=gates.py:138-145(6,frozen) config_key_precedent=b8bc115ff(auto_gate_mode) HEAD=10446aefb
