# Research: sidecar 标记文件（marker）的锁协议 / 原子写 / 一次性消费先例（design）

> Key: mw-done-closure-repair（design 阶段输入）
> 日期: 2026-09-25 | 类型: 只读代码调研（RQ-2）
> 对象: 坏稿声明 marker `.agenticdoc/<key>/.mw-achieved-baddraft.json`（字段 file/sha256/declared_at/failures）的写入 / 校验 / 删除机制先例

## 决策问题

design 需要为 marker 定义四个机制，本调研逐项给出代码先例与出处：

1. per-key 锁协议：`acquire_conductor_lock(project_root, f"key-{key}")` 与 `mw_common.release_lock` 的用法、锁文件落点、获取失败语义（ConductorLockHeld）。
2. check-before-write / write-once 先例：`_persist_l3_verdict`（l3-verdict.txt + l3-report.md）的幂等写入；`_done_transaction` step 1 QG report 的 write-once。
3. 一次性消费先例：`_consumed_gate_ids` 的存储与重放（timeline 派生 vs 文件派生）对"marker 消费一次后删除"的借鉴。
4. 原子写先例：mw_common.py / dispatch.py 的临时文件 + os.replace（P-003 修复方式），marker 应复用哪个。
5. 落点选择依据：`.agenticdoc/<key>/` 点前缀文件 vs `.mw/` 状态文件——现有扫描面（state.py / gates.enumerate / audit / TS 扩展 / 框架）是否会误读；`.gitignore` 对 `.agenticdoc` 的排除现状。
6. 崩溃窗口枚举：marker 写入 / 校验 / 删除与 advance 调用交错中每步崩溃后的下一 tick 行为（fail-safe 方向恒为"不覆盖"）。

## 调研方法与出处（file:line）

只读代码核验（2026-09-25，未改任何源码），路径相对仓库根：

- `packages/multi-workers/autopilot/conductor.py`：锁常量与协议 59-132；门禁消费 255-330；L3 verdict 读取 603-611 与持久化 619-656；失败分类 710-741；streak 744-808；结果记录 809-848；verify 回路 1161-1269；PASS 行 1272-1301；done 事务 1319-1412；phase 探测 1423-1434；tick 1509-1581；stalled 审批消费 1733-1800；mark_stalled 1835-1900。
- `packages/multi-workers/mw_common.py`：acquire_lock 1480-1493；release_lock 1495-1499；_write_workers_file 1502-1508；pid/doctor 面板 1565-1701；launcher 心跳 1862-1915；sha256_eol_normalized 2926-2934。
- `packages/multi-workers/autopilot/gates.py`：_write_atomic 198-204；create 259-283；enumerate 480-505（GATE_FILE_RE 88）。
- `packages/multi-workers/autopilot/dispatch.py`：task.md 先写 517-518；锁内 upsert 537-570（P-003 注释 556-559）。
- `packages/multi-workers/autopilot/state.py`：read_index 97-109；read_key_states 133-140；scan_worker_tasks 209-222；used_rounds 224-256；artifact_mtimes 320-341。
- `packages/multi-workers/autopilot/timeline.py`：旋转常量 93-94；timeline_path 97-99；query_events 388-436；tail_events 438-467。
- `packages/multi-workers/autopilot/audit_evidence.py`：_RESEARCH_GLOBS 72-75；_index_evidence 170-182；build_dossier 215-263。
- `packages/multi-workers/autopilot/advance.py`：UTF-8 强制 41；advance() 返回 (code, stdout, stderr) 164-192。
- 框架 `.agents/skills/agentic-task/scripts/advance_phase.py`：done 门禁规则 69-95；check_gate 失败行 191-290；GATE BLOCKED stderr 输出 585-591。
- TS 扫描面 `packages/coding-agent/src/extensions/agent-team-loop/`：autopilot/status-model.ts 60-62（gates.lock）、636-652（listGates readdir）、874-902（usedRounds readdir）；autopilot/monitor.ts 259-263（gates readdir）；pm/pm-orchestrator.ts 406-421（.agenticdoc 根 readdir）。
- `.gitignore`（1-69 行）；`git ls-files .agenticdoc` = 555 个已跟踪文件；`git check-ignore` 对 marker 路径退出码 1（未忽略）。
- 本 key 既有 evidence：`evidence/research/spec-code-facts-20260924.md`（F1-F16）、`evidence/research/spec-incident-and-alternatives-20260924.md`（A1-A5）。
- 坑点原文：`.agenticdoc/_pitfalls.md` P-001（:5 起，PowerShell 文本管道损坏 BOM/UTF-8）、P-003（:24 起，`open(p, "w")` 先截断后求值）。

## 发现

### F-1 per-key 锁协议（问题 1）

- 锁文件落点：`lock_file(project_root, name)` = `.mw/{name}.lock`（conductor.py:92-94）。per-key 锁名为 `key-{key}` → `.mw/key-{key}.lock`。`.mw/` 为运行时目录，被 .gitignore:53 整目录排除；现存内容为锁、pid、日志、心跳（工作树 `.mw/` 实测：mw.pid / conductor.pid / mw.log / launcher-beat.* / serve.meta / window-model / dispatch.yml）。
- 获取协议 `acquire_conductor_lock`（conductor.py:97-132）：先快速路径 `mw_common.acquire_lock(path, retries=4, base_delay=0.02)`；失败后按锁文件 mtime 年龄判定——`age > 30s`（`STALE_LOCK_AGE_SEC`，conductor.py:59）视为持有者死亡（前提：conductor 锁持有均为毫秒级，conductor.py:88-90 docstring）→ unlink 抢占 + timeline `config` 事件 `stale {name}.lock stolen (age ...)`（conductor.py:124-131）；`age <= 30s` 抛 `ConductorLockHeld`（conductor.py:132，"a live holder — defer, never clobber"）。stat 时文件消失 → 普通重取（conductor.py:119-123）。
- 底层原语：`mw_common.acquire_lock`（mw_common.py:1480-1493）= `os.open(O_CREAT|O_EXCL|O_WRONLY)` + 指数退避（retries 次后 RuntimeError），注释"Same protocol as the TS side"（mw_common.py:1481；TS 侧同名锁见 status-model.ts:60-62 gates.lock）。`mw_common.release_lock`（mw_common.py:1495-1499）= unlink，FileNotFoundError 吞掉。
- 完整锁作用域示范 = `_append_pass_line`（conductor.py:1272-1301）：acquire（1280）→ `ConductorLockHeld` → `return False`（1281-1282）→ 锁内读 pm-state.md（1284-1286）→ PASS 幂等检查（1287-1288）→ `write_text` 全文重写（1292-1295）→ `except OSError` → timeline config 事件 + False（1297-1299）→ `finally release_lock`（1300-1301）。
- 获取失败语义统一为"推迟到下一 tick"：`_create_gate` 锁被占返回 None（conductor.py:1618-1644：acquire 1631 → ConductorLockHeld 返回 None 1633 → finally release 1640）；`_append_pass_line` 返回 False → 事务返回 "gated"（conductor.py:1378-1379）→ 下 tick 重试。tick 本身永不 raise（conductor.py:1509-1581，异常 → timeline config `tick error` 事件）；conductor 死亡由 `mw serve` 1s 内重生（conductor.py:4-6 模块 docstring，D-101）。

### F-2 PASS 行写法的非原子性（marker 的反例警示）

`_append_pass_line` docstring 自称 "atomic rewrite"（conductor.py:1275-1276），实际是锁内 `write_text` 全文重写（conductor.py:1292-1295），无 tmp + os.replace：写入中途崩溃会留下截断的 pm-state.md（丢失 `- Phase:` 接口行 → `_classify_advance_failure` 判 interface-drift，conductor.py:696-699）。仓库内两个真正的原子写先例在 F-6。**marker 只照抄 `_append_pass_line` 的锁协议，不照抄它的写法**——GC-2/spec §2.2 明确要求 tmp + `os.replace`。

### F-3 check-before-write 先例一：`_persist_l3_verdict`（conductor.py:619-656）

- 值域守卫：verdict 仅允许 meets/below，第三态永不落盘（conductor.py:630，D-008）。
- 幂等 = 逐文件内容比较：l3-report.md 仅当 `not (report.is_file() and report.read_bytes() == payload)` 才 `write_bytes`（conductor.py:644-645）；l3-verdict.txt 仅当 `before != verdict` 才写（649-650）；timeline 事件仅在有变化时发（651-656）。重复 tick / 崩溃重试 = 零写零事件（docstring D-004/D-005：report 先行，verdict 后行）。
- 双向刷新：done-meets 与 stall-below 都刷新同一对文件，防止 verdict 钉死在旧值（conductor.py:627-629 docstring D-002/D-003/D-004）。
- 无锁、非原子（write_bytes 直接写）。崩溃退路：verdict 文件半写 → `_l3_verdict`（conductor.py:603-610）读到非 meets/below → 返回 "none" → 下一个终态事件重新刷新。fail-safe 方向 = 无效值不参与判定。
- 对 marker 的可复用原则：值域/形状守卫 + "只在变化时写"。marker 的 AC-011"同一被拒内容重复失败保持单文件（内容原地更新）"即同一原则——固定路径重写，比较后决定是否写。

### F-4 check-before-write 先例二：`_done_transaction` step 1 QG report write-once（conductor.py:1343-1359）

- 存在性 glob 守卫：`if list(evidence_dir.glob("quality-gate-report-*.md"))` → 复用现存报告（sorted 首个，conductor.py:1346-1347）；否则才写新时间戳文件（1349-1359）。注释明示动机："any existing report is reused on a retry; the source verdict has not changed"（1344-1345）。
- 崩溃窗口：命名与写入之间崩溃 → 无文件 → 下 tick glob 未命中 → 重建（时间戳名不同无妨，glob 不挑名字）；写一半崩溃 → 留截断 report，但 done 门禁只查 `glob_has_files >= 1`（advance_phase.py:89-94），不读其内容 → write-once 的崩溃语义是"存在即可"。
- 事务幂等总闸：入口 `phase == DONE → return "advanced"`（conductor.py:1330-1332，"crash-after-advance resume"）。marker 方案需要同类锚点：phase 已终态后 marker 残留 = 惰性（见 F-13/W7）。

### F-5 现行 achieved.md 覆盖守卫（改动点 2 的现状基线）

step 2：`if not (achieved_path.is_file() and st_size >= 200): write`（conductor.py:1365-1369）+ 后验 `< 200B → below`（1373-1377）。≥200B 草稿永不覆盖 = 本 key 要修的缺口。marker 的三条件（marker 存在 ∧ sha 一致 ∧ 本次失败行含 achieved.md）将替换该守卫成为覆盖的唯一入口。注意现行写法同为非原子 `write_text`（1365-1367）——替换时应一并升级为 tmp + replace（与 GC-2 对齐）。

### F-6 原子写先例（问题 4，P-003 修复方式）

- 先例 A：`mw_common._write_workers_file`（mw_common.py:1502-1508）：`tmp = Path(str(path) + ".tmp")` → `tmp.write_text(content, encoding="utf-8")` → `tmp.replace(path)`。引用处 dispatch.py:556-560，注释明示动机："content fully precomputed, then tmp + os.replace … open("w") truncates before the write expression is evaluated (pitfalls P-003 / PM defect #50)"。P-003 原文：`.agenticdoc/_pitfalls.md:24` 起。
- 先例 B：`gates._write_atomic`（gates.py:198-204）：同配方 + `path.parent.mkdir(parents=True)` + `newline="\n"`，docstring "Atomic write with explicit UTF-8 and LF endings (mw_common style)"；`gates.create` 使用（gates.py:259-283）。
- 复用结论：两者都不是可直接导入的通用 helper（A 私有且绑定 workers 语义，B 模块私有）。marker 写入应照抄 **B 的形状**（mkdir + utf-8 + LF + 同目录 tmp + `os.replace`）在 conductor 侧内联为小函数；内容先 `json.dumps` 求值再写 tmp（P-003"先求值后写"）。tmp 用固定名 `.mw-achieved-baddraft.json.tmp`：同目录同卷（os.replace 原子成立）；固定名 → 崩溃残留至多 1 个且被下次写覆盖，无每 tick 文件增长（AC-009/AC-011 对齐）。

### F-7 一次性消费先例：`_consumed_gate_ids`（问题 3）

- 存储方式：**timeline 派生**，非文件派生。`_consumed_gate_ids`（conductor.py:255-272）用 `timeline.query_events`（timeline.py:388-436，读全旋转链）过滤 `ev == "gate-answered"` 事件，`re.match(r"(gate-\d{4})\b", detail)`（conductor.py:268）提取 gate id；`_consume_answered_gates`（conductor.py:274-330）对已消费 id `continue`。
- 为什么 timeline：gate 文件在 answer 后仍留在 gates 目录且被 enumerate 扫描（gates.py:480-505 扫全部状态），"文件存在"无法区分已消费/未消费，消费记录必须落在别处；timeline 是持久文件（timeline.jsonl + 2 代旋转，timeline.py:93-94、388-436），restart 后重派生同一集合（conductor.py:257-261 docstring）。
- 事故教训（对 marker 最关键）：2026-09-24 FeatureMigrator——`_apply_stalled_approvals` 曾仅以 key-status 重写为幂等守卫，key 同 tick 内再 stall 时同一人工答案被重放，12h 生成 6684 个 pending 门（conductor.py:1758-1766 注释原文）；修复 = timeline 消费记录 + `gate.id in consumed → continue`（conductor.py:1733-1800）。
- 对 marker 的映射（结构性差异）：marker 的消费动作**就是删除**（覆盖成功 / advance 成功后删除，AC-011）——文件本身即消费记录（self-consuming），不存在"answer 后文件还在"的重放源，因此：
  - 不需要 timeline 事件做消费守卫；文件真值即守卫（与 `_resume_credits` "re-derived … every call (zero private state)" 同哲学，conductor.py:1714-1723 docstring）；
  - 崩溃留下的"已消费但未删"marker 由 sha256 失配惰性化（achieved.md 已是新内容 → marker 绑旧 sha → 三条件假 → 永不覆盖），承担与 gate 消费记录等价的防重放作用，且更简单；
  - 需要防的唯一形态是"marker 从未消费也永不再被校验"的死文件（W7）——fail-safe（不覆盖）但违反 AC-011 删除断言，故删除应放在覆盖成功的同一锁作用域内（见结论 3）。

### F-8 timeline 不能承载失败原文（marker 的第二职责依据）

- 失败 err 写入 timeline 前经 `_one_line(err, 200)`（conductor.py:833；`_one_line` 710-713：空白拍平 + 200 字符截断 + 省略号）——多行 `NO MATCH:` / `MISSING:` 原文无法经 timeline 逐行还原。
- 守卫判定用的 `tail_events` 仅 400 事件 / 512KiB（timeline.py:438-467）；`query_events` 读全链但受旋转裁剪（10 MiB × 3 文件，timeline.py:93-94）。spec §5 记忆前馈已定性："timeline 有界尾部（400 事件/512KiB）不可作为守卫判定依据——marker 落盘的动机（research A3）"。
- 结论：失败原文的唯一持久通道 = 在失败现场从 `advance.advance` 返回的 `err`（conductor.py:1381-1383 拿到 live stderr）当 tick 写入 marker 的 `failures` 字段；下一轮 reprompt prompt 逐行引自 marker 文件，非 timeline。

### F-9 advance 失败行格式与 "achieved.md" 判定来源（问题 6 的输入）

- 失败行由框架 `check_gate` 产出（`.agents/skills/agentic-task/scripts/advance_phase.py:191-290`）：`MISSING: {path_pattern} — {desc}`（:203）、`TOO SMALL: {path_pattern} (…B < …B) — {desc}`（:204-207）、`NO MATCH: {path_pattern} missing pattern '{pattern}' — {desc}`（:223-227）、`MISSING DIR: {path_pattern}/ — {desc}`（:212）。
- done 门禁 5 条规则中 3 条的 path_pattern 字面量就是 `achieved.md`（advance_phase.py:70-87：file_min_bytes 200 / content_match `系统行为变化` / content_match `遗留`；另两条为 pm-state.md PASS 与 quality-gate-report glob）→ "失败行涉及 achieved.md" = 行内含字面量 `achieved.md`，天然覆盖 MISSING / TOO SMALL / NO MATCH 三形态，无需词表。
- 输出通道：失败时 stderr 打 `GATE BLOCKED: {key} cannot advance to '{target}'` + 每条失败行缩进一行，exit 1（advance_phase.py:586-591）；`advance.advance` 子进程捕获为 `(code, stdout, stderr)`（advance.py:164-192），子进程强制 `-X utf8` 防 Windows cp936 损坏中文行（advance.py:41）。
- 交错安全性：advance_phase.py 全程无文件锁、无 tmp/replace（lock/os.replace 关键字全文检索仅 :587 一处 stderr 打印命中）→ 框架侧不写 achieved.md；mw 侧唯一写者是 done 事务。marker 校验/覆盖/删除与 advance 的交错只有一个写者（conductor），且锁窗口毫秒级（F-1）。

### F-10 落点扫描面审计（问题 5）：`.agenticdoc/<key>/` 点前缀文件对现有扫描不可见

- Python 侧：
  - `state.read_key_states` 只读 `_index.parallel`（state.py:133-140 → read_index 97-109），**不遍历 key 目录**；
  - `state.scan_worker_tasks` glob `.agenticdoc/*/workers/*/task.md`（state.py:209-222）；`used_rounds` glob `workers_dir/*/task.md`（state.py:224-256）；`artifact_mtimes` 只 stat 指定文件（state.py:320-341）；
  - `gates.enumerate` **只扫 gates 目录**（`.agenticdoc/_autopilot/gates/`）且按 `^gate-(\d+)\.md$` 过滤，非 gate 文件与 .tmp 显式忽略（gates.py:480-505，GATE_FILE_RE gates.py:88）；
  - `audit_evidence.build_dossier` 只读指定文件 + `evidence/` rglob + research glob（audit_evidence.py:170-182、215-263）；
  - conductor 对 key 目录的所有访问均为指定文件名（achieved.md / l3-verdict.txt / l3-report.md / pm-state.md / tasks/*.md / evidence/…，conductor.py:603-611、1330-1369、1423-1434 等）；
  - `mw.py` rag audit iterdir key 目录但只读 `key_dir/rag`（mw.py:1850-1865）；patterns 只扫 `*/patterns`（mw.py:4487）。
- TS 侧（agent-team-loop 扩展）：`listGates` 只 readdir gates 目录 + 文件名过滤（status-model.ts:636-652）；`usedRounds` readdir workers 目录只取 isDirectory（status-model.ts:874-902）；monitor 只 readdir gates 目录（monitor.ts:259-263）；pm-orchestrator readdir `.agenticdoc` 根只取目录且跳过 `.` 前缀（pm-orchestrator.ts:406-421）；WorkerStore / IndexStore 读 `_workers.parallel` / `_index.parallel`。
- 框架侧：`check_gate` 全部指定 path_pattern（advance_phase.py:191-290），无 key 目录枚举。
- 结论：**点前缀不是安全性的承重墙；承重墙是"不被任何现有 glob / readdir / 命名过滤器命中"**。`.mw-achieved-baddraft.json`（点前缀 + .json 扩展 + 固定名）及其 `.tmp` 残留在所有过滤器下均不可见。风险仅剩 git 可见性（F-11）。

### F-11 `.gitignore` 现状（问题 5；spec §4 风险行勘误）

- `.agenticdoc` **未被整体排除**：.gitignore 只忽略 `.agenticdoc/**/workers/`（:66）、`.agenticdoc/**/_workers*`（:67）、`.agenticdoc/.mw/`（:68）、`.agenticdoc/**/*.lock`（:69）；`.mw/` 整目录被忽略（:53）。
- 实测：`git ls-files .agenticdoc` = 555 个已跟踪文件（spec/design/achieved.md 等均入库）；`git check-ignore .agenticdoc/mw-done-closure-repair/.mw-achieved-baddraft.json` 退出码 1 = **未忽略** → marker 会以 untracked 出现在 `git status`。
- 勘误：spec §4 风险行"（点前缀；`.agenticdoc` 已在 .gitignore 排除）"不准确——被排除的只是 workers/_workers/.mw/lock 运行时子集。plan 需显式决策：在 .gitignore 增加该 marker 模式（如 `.agenticdoc/**/.mw-achieved-baddraft.json`），或接受 untracked 噪音（多 pi session 并行时互相可见）。

### F-12 落点权衡：key 目录 vs `.mw/`

- `.agenticdoc/<key>/.mw-achieved-baddraft.json`（spec 已定方向）：与被绑定的 achieved.md 同目录，内容寻址配对可发现、provenance 就地；语义属 key 文档状态。缺点：git status 噪音（F-11）。
- `.mw/`：gitignored（.gitignore:53），但它是**全局运行时命名空间**——锁协议 `.mw/{name}.lock`（conductor.py:92-94、mw_common.py:1438-1439）、pid（mw_common.py:1565、conductor.py:62-63）、doctor/status 面板读它（mw_common.py:1599-1701、conductor_status conductor.py:1961-1984）、launcher 心跳（mw_common.py:1862-1915）。per-key 文档语义文件混入将：与锁命名共享前缀空间（`key-{key}.lock` 已占用该模式）、语义错置（运行时 vs 文档）、且与 `.mw/` 清理/诊断面耦合。
- 研究结论（不改码）：维持 spec 的 key 目录落点；gitignore 扩展作为 plan 显式决策项（F-11）。

### F-13 崩溃窗口枚举（问题 6）

marker 生命周期 = [advance 失败] → 写 marker → 派发 reprompt → in-flight → L3 meets → 三条件校验 → 覆盖 achieved.md → 删 marker → advance done。逐窗崩溃与下一 tick 行为：

| 窗口 | 崩溃点 | 下一 tick 行为 | fail-safe 判定 |
|---|---|---|---|
| W1 | advance 失败后、写 marker 前 | 无 marker → 三条件假 → 不覆盖；事务重走 advance（streak +1，conductor.py:744-848）→ 届时写 marker | 不覆盖；浪费一次 advance（research A4 已接受） |
| W2 | marker tmp 已写、replace 前 | marker 不存在（tmp 残留无人扫描，F-10）→ 同 W1；下次写覆盖同名固定 tmp | 不覆盖；无文件增长 |
| W3 | marker 写后、reprompt 派发前 | verdict 仍 meets → 事务重试 advance 失败 → marker 同 sha 原地更新（AC-011）；reprompt 条件满足即派发 l3-a{N+1}（同 loop/attempt，dispatch upsert 不增行，dispatch.py:549-560） | 不覆盖；不新增轮次 |
| W4 | reprompt in-flight 中（conductor 死亡） | serve 1s 内重生（conductor.py:4-6）；in-flight 守卫 `ap-{key}-l3-` 前缀拦截 advance 事件（conductor.py:1188-1190，AC-007） | 不覆盖 |
| W5 | 覆盖 achieved.md：tmp 写后、replace 前 | achieved.md 仍旧稿、marker sha 一致 → 三条件重验为真 → 幂等重放覆盖 | 不覆盖（未完成则重做） |
| W5b | replace 后、删 marker 前 | achieved.md 已新稿、marker 绑旧 sha → 失配 → 不覆盖 → 直接走 advance（QG 复用 F-4、PASS 幂等 conductor.py:1287-1288） | 不覆盖（防双覆盖核心窗） |
| W6 | 删 marker 后、advance 前 | marker 不存在 → 三条件假 → 不动新稿；步骤幂等 → advance exit 0 | 新稿保全 |
| W7 | advance exit 0 后（若删除滞后至此） | phase=DONE → 事务入口短路 "advanced"（conductor.py:1330-1332）→ marker 无人消费 = 惰性死文件（sha 失配永不触发覆盖） | 不覆盖；**违反 AC-011 删除断言** → 删除必须在覆盖成功同锁作用域内，不能等 advance |
| W8 | 人工重写 achieved.md 后任意点（场景 B） | sha 失配 → 不覆盖（AC-004）→ advance 直接验证新稿 | 不覆盖（永不误覆盖） |
| W9 | marker 原地更新中途（同 sha 重复失败） | 同 W2（旧 marker 仍在，绑同 sha，条件可判定）或 marker 缺失同 W1 | 不覆盖 |

- 全部窗口的下一 tick 判定方向一致：任一不确定状态 → 三条件至少一条为假 → **不覆盖**。非 fail-safe 的只有"死文件残留"（W7，靠删除时机消除）与"浪费一次 advance"（W1/W3，可接受退化）。
- 前提成立性：三条件校验 + 覆盖 + 删除同在 `.mw/key-{key}.lock` 内（单写者、毫秒级持有，F-1）；advance 子进程无锁不写 achieved.md（F-9）→ 交错在 mw 侧天然串行。

### F-14 sha256 计算方式（marker.sha256 字段）

- 现成 helper `mw_common.sha256_eol_normalized`（mw_common.py:2926-2934）先 CRLF→LF 归一再哈希（为 core.autocrlf 漂移设计，服务于 toolchain probe 指纹）——**不适用于 marker 绑定**：AC-003 要求 `marker.sha256 == sha256(当前 achieved.md)`，用字节精确 `hashlib.sha256(path.read_bytes())` 才能把"人工仅换行改稿"也判为失配（fail-closed）；且 done 门禁 content_match 用 `re.search`（advance_phase.py:223-227），EOL 差异不影响 advance 判定，字节精确不会造成假失败。
- 覆盖写入侧固定 `newline="\n"`（与现行转写一致，conductor.py:1367-1369）；若覆盖后仍失败，新 marker 对新稿重新字节哈希，闭环自洽。

## 结论 → 决策映射

1. **锁协议（→ GC-2、design marker 读写删协议）**：复用 `acquire_conductor_lock(project_root, f"key-{key}")` + `finally mw_common.release_lock(lock_file(...))`（`_append_pass_line` 范式，conductor.py:1272-1301）；`ConductorLockHeld` → 当 tick 放弃（gated 语义），不抢不重试（conductor.py:97-132）。三条件校验、覆盖、删除放**同一锁作用域**（F-1、F-13 前提）。
2. **原子写（→ GC-2 / P-003）**：照 `gates._write_atomic` 形状（gates.py:198-204）内联：mkdir → `json.dumps` 先求值 → 同目录固定名 tmp → utf-8 + LF → `os.replace`。禁止 `open("w")` / `write_text` 直写（`_append_pass_line` 与 step 2 的非原子写是反面教材，F-2/F-5；P-003 原文 `_pitfalls.md:24`）。
3. **一次性消费（→ AC-011）**：不引入 timeline 消费事件；marker 文件本身即消费记录（self-consuming，F-7）——**覆盖成功即在同锁作用域内删除**（堵 W7），不能等 advance exit=0 才删；重复同 sha 失败原地重写同一路径（F-3"只在变化时写"原则）。删除滞后到 advance 是被 W7 证明错误的顺序。
4. **failures 字段来源（→ 改动点 1 / AC-002）**：失败原文只能在失败现场从 `advance.advance` 返回的 err 捕获（conductor.py:1381-1383）写入 marker `failures`；reprompt prompt 逐行引自 marker。timeline 通道已被 `_one_line(err, 200)` 拍平截断（conductor.py:833）且有界（timeline.py:438-467）——不可用（F-8）。
5. **落点（→ spec §4 / plan 决策项）**：维持 `.agenticdoc/<key>/.mw-achieved-baddraft.json`（扫描面零命中，F-10；`.mw/` 落点语义错置且与锁命名耦合，F-12）；spec §4 gitignore 表述需勘误（F-11）——plan 显式决策：加 .gitignore 忽略行或接受 untracked 噪音。
6. **崩溃安全（→ AC-003/AC-004）**：三条件校验作为覆盖唯一入口 + sha 失配惰性化 → W1-W9 全窗口 fail-safe（F-13 表）；保留事务入口 phase=DONE 短路锚（conductor.py:1330-1332 先例）处理 advance 后崩溃。
7. **sha256（→ AC-003）**：字节精确 `hashlib.sha256(read_bytes())`；不复用 `mw_common.sha256_eol_normalized`（EOL 归一会弱化人工改稿保护，F-14）。
