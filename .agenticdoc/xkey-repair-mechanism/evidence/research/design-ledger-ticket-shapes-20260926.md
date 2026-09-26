# Research RQ-D2：账本 / 工单 / 证据包的数据形状与落盘设计面

- Key: xkey-repair-mechanism / Phase: DESIGN（research RQ-D2）
- 日期: 2026-09-26
- 产出: 本文件为唯一写入；未改任何 key 文件、未跑写状态命令、未 commit（FM 树与 MW 树均只读）
- 行号口径: 当前工作区 HEAD（dirty 树）实测行号；方法 `Select-String -Path <file> -Pattern '...' | % { "$($_.LineNumber): ..." }`，逐字引用均为本会话实读
- 服务对象: 设计决策 D-002（跨 key 红账本载体与去重键）/ D-003（工单载体）/ D-004（证据包载体与落点），以及 conductor tick 内“聚合扫描”的挂载点与开销边界（spec §2.2）

## 决策问题

1. **Q1 现有 sidecar 形状清单**（落盘范式对照）：`l3-verdict-provenance.json`、`.mw-achieved-baddraft.json`、gate frontmatter、`_closure_dossier_md` 四者逐个给出：文件路径 / 字段 / 原子写实现 / 去重键 / 生命周期收口点（谁删）。
2. **Q2 可选载体方案对比**（≥3 个）并给出推荐：单一 append-only JSON sidecar（仿 provenance）vs 每工单一文件+目录枚举（仿 gates seq 重扫）vs 单一 markdown 账本表。判据绑定 AC-001 / AC-007 / Q9 / GC-1 / spec §2.2 / P-003 / P-013。
3. **Q3 工单形状**：以 FM 人工工单 `cross-key-repair-request-20260925-n1.md` 逐字字段为基线，对照 A-06 的 `refreeze-request-20260925-guarded-closeout.md`（三条 decision 行），给出“机器化工单应含哪些字段”清单（每字段：来源 / 是否机器可判 / 谁写）。
4. **Q4 conductor tick 挂载点**：每 tick 增量聚合扫描应插在哪个函数 + file:line；同类“消费已落盘产物”的模板步骤；挂载点的幂等性与重启安全要求（durable / 幂等 / 零私有状态）。
5. **Q5 证据包落点**：现有证据落盘约定；新机制的票据/账本/证据包应落在哪个目录及理由（与 FM 现状对齐 vs 框架级统一）。

## 调研方法与出处

- **全文精读（不靠搜索片段）**：`packages/multi-workers/autopilot/conductor.py`（2513 行）、`autopilot/gates.py`（508 行）、`autopilot/closure.py`（187 行）、`autopilot/config.py`（全文）；`autopilot/dispatch.py` 相关段。
- **FM 语料逐字**：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\evidence\cross-key-repair-request-20260925-n1.md`（6752 B）、`.agenticdoc\gui-skeleton-shell\evidence\refreeze-request-20260925-guarded-closeout.md`（A-06 的受理件）、`.agenticdoc\_autopilot\reflect\plan-writeface-gap.md`（A-06 归因）、`.agenticdoc\_autopilot\evidence\xkey-n1-repair-20260926.txt`（人工修复证据包）。
- **目录枚举**：MW 仓 `.agenticdoc/*/evidence` 与 `evidence/runs`（30+ key）、FM 仓 `.agenticdoc/_autopilot/` 与逐 key `evidence/` 文件计数。
- **否定结论检索（本会话自测）**：`xkey|ledger|ticket|工单|账本|cross_key|crosskey|handoff` 在 `packages/multi-workers/*.py, autopilot/*.py` 命中 **0**（与本 key RQ-1/RQ-3 的 0 命中一致）。
- **只读纪律**：未修改 `pm-state.md` / `_index.parallel` / spec / FM 或 MW 的任何文件；仅 `read` / `Select-String` / `Get-ChildItem`。
- **上游**：`spec.md`（§1.1/§2.2/§2.3/§2.4/§5）、`key-decision.md`（Q8/Q9）、`evidence/research/spec-reusable-parts-20260926.md`（RQ-3）、`spec-code-facts-20260926.md`（RQ-1）。

## 发现

### Q1 现有 sidecar 形状清单（逐项五要素）

#### 1. `l3-verdict-provenance.json`（append-only 审计 sidecar，per-key）

| 要素 | 事实 | 锚点 |
|---|---|---|
| 文件路径 | `<project>/.agenticdoc/<key>/l3-verdict-provenance.json`（per-key，与 key 目录同级） | 常量 `_PROVENANCE_FILENAME = "l3-verdict-provenance.json"` `conductor.py:1187`；路径拼接 `path = key_dir / _PROVENANCE_FILENAME` `conductor.py:1370` |
| 字段（12） | `round / task_key / deciding_source / source_mtime_ns / anchor_path / anchor_mtime_ns / suspect / reasons / raw_verdict / verdict / fail_line / recorded_at` | record 字典字面量 `conductor.py:1294-1305`；构造函数 `_l3_provenance_record` `conductor.py:1267` |
| 原子写 | 读全 list → 去重 → `tmp.write_text(json.dumps(...)+"\n", UTF-8, newline="\n")` → `os.replace(tmp, path)`；写前无锁（依赖 conductor 单点/单线程） | `conductor.py:1377-1383`；读+校验 `:1362-1371` |
| 去重键 | **`task_key`**（同一 round 已有记录 → 直接 `return False`，零写入） | `conductor.py:1372-1375` |
| 生命周期收口 | **永不删除**（append-only 审计史；corrupt 文件也**不覆盖**，`return False` + timeline `config` 事件，audit history outranks 新记录） | corrupt 分支 `:1362-1371`；`_PROVENANCE_FILENAME` 全仓仅出现在 `:1187`（定义）与 `:1370`（拼接），无 unlink |
| 写入时机 | L3 每轮的判定源被解析后（meets 与 below 都写） | 调用点 `_verify_loop`：`record = _l3_provenance_record(...)` `conductor.py:1555`；`_persist_l3_provenance(key_dir, record, st=st)` `:1558` |

**对照意义**：这是 spec §2.4 点名的“append-only+去重+原子写”范式（`conductor.py:1359`）。但其**去重键不是 `(file,test_id,指纹)`**，且**没有状态字段**（只有 verdict），故账本不能原样照抄——需要“记录可寻址 + 状态可变”。

#### 2. `.mw-achieved-baddraft.json`（内容寻址授权 marker，per-key）

| 要素 | 事实 | 锚点 |
|---|---|---|
| 文件路径 | `<project>/.agenticdoc/<key>/.mw-achieved-baddraft.json`（固定文件名，per-key 至多一个） | 常量 `BAD_DRAFT_MARKER_NAME = ".mw-achieved-baddraft.json"` `closure.py:40`；`_marker_path(key_dir)` `closure.py:101`；tmp 名 `BAD_DRAFT_TMP_NAME` `:41` |
| 字段（4） | `{file, sha256, declared_at, failures}`：`file`=`"achieved.md"`；`sha256`=`hashlib.sha256` over **精确字节**（无 EOL 归一）；`declared_at`=UTC ISO；`failures`=逐字失败行 list | payload 构造 `closure.py:126-131`；hash `:135`；读取 `read_bad_draft_marker` `:105`；删除 `delete_bad_draft_marker` `:151` |
| 原子写 | `tmp.write_text(content, UTF-8, newline="\n")` → `os.replace(tmp, _marker_path(key_dir))`；**调用方持锁**（per-key） | `closure.py:146-148`；锁在调用侧：`acquire_conductor_lock(project_root, f"key-{key}", ...)` `conductor.py:1785` / `:1812` / `:1827` |
| 去重键 | **无显式键**（固定文件名 → 每 key 单文件、最后写胜）；语义上的“同一性”靠内容寻址三条件 `overwrite_authorized(marker, current_bytes, lines)`：marker 存在 ∧ `sha256(current_bytes)==marker.sha256` ∧ marker.failures 提及 achieved.md | `overwrite_authorized` `closure.py:159-187`（hash 比对 `:182`） |
| 生命周期收口 | 三个删除点：① 授权覆盖成功、同锁删 `conductor.py:1783`；② advance exit=0 惰性清理（覆盖事务外被修好的草稿）`:1833`；③ 终态清扫——`_mark_key_done` DONE `:2163`、`_apply_stalled_rejections` closed-legacy `:2286` | 见左列；`delete_bad_draft_marker` 对缺失文件静默 no-op `closure.py:151-156` |

**对照意义**：这是“**内容寻址 + 前置三条件授权**”范式（AC-005 要沿用的家族）；也是“sidecar 生命周期必须显式收口（否则陈旧 marker 滞留）”的正面先例。

#### 3. gate frontmatter（一 gate 一文件 + 目录枚举）

| 要素 | 事实 | 锚点 |
|---|---|---|
| 文件路径 | `<project>/.agenticdoc/_autopilot/gates/gate-{seq:04d}.md`（一 gate 一 markdown；目录扫描即队列） | 目录构造 `conductor.gates_dir` `conductor.py:66-67`；路径策略 docstring `gates.py:20-23`；文件正则 `GATE_FILE_RE` `gates.py:96` |
| 字段（12） | `id, kind, stage, key, created_at, created_by, question, context_refs, status, answered_at, answered_by, note`（frontmatter=机器契约，body=人读散文，parse 忽略 body） | `FRONTMATTER_FIELDS` `gates.py:65-81`；必填子集 `_REQUIRED_FIELDS` `:83-84`；`Gate` dataclass `:116`；解析 `parse` `:460`；渲染 `_gate_file_content` `:159` |
| 原子写 | `_write_atomic(path, content)`：`tmp = path + ".tmp"` → `tmp.write_text(UTF-8, newline="\n")` → `tmp.replace(path)` | `gates.py:198-205`；create `:259`；调用方锁 `conductor._create_gate` `:2064-2091`（`.mw/gates.lock`） |
| 去重键 | **`id`**，由 `_next_seq` = `max(existing gate id)+1` **每次从目录重扫**（无内存计数器 → 重启安全） | `_next_seq` `gates.py:243-256`；create 内 `seq = _next_seq(gates_dir)` `:273`；注释 `:243-247` |
| 生命周期收口 | **Python 侧从不删除 gate 文件**；消费由 timeline `gate-answered` 事件承担（durable 消费记录，重启重派生） | `_consumed_gate_ids` `conductor.py:255-272`；`gates.enumerate` `gates.py:480`；`pending_gates` `:506` |
| 承载约束 | `question` 必须**单行**（拒 `\n`/`\r`）；`context_refs` 为非空**单行**字符串 block list 或 `[]`；无嵌套、双引号标量拒收、未知字段 raise `GateFormatError` | `_validate_new_gate` `gates.py:209-241`；`_parse_frontmatter` `:308-364`；`_to_gate` `:404+` |
| 反面教材（flood） | 无 durable 消费记录时，同一待答 gate 每 tick 被重建：`0.5***` 实测 **6684 pending stalled gates + 6685 事件 / ~12h**（两条已批 gate 复读） | 逐字事故注释 `conductor.py:2213-2222` |

**对照意义**：gate 是 spec §2.4 点名的“抬起/作答/消费”协议与 Q2(b) 的目录枚举手法的原型；flood 注释是本设计最重要的反面约束（**任何每 tick 抬起的对象都必须有“恰好一次”的 durable 消费记录**）。

#### 4. `_closure_dossier_md`（stage 闭环 dossier 生成器，project-level、write-once）

| 要素 | 事实 | 锚点 |
|---|---|---|
| 文件路径 | `<project>/.agenticdoc/_autopilot/stages/stage-{N}-close.md` | `_stage_closure` 内 `stages_dir / f"stage-{stage.number}-close.md"` `conductor.py:578-579` |
| 形状 | 人读 markdown：`# Stage N Close Dossier` / `- stage:` / `- goal:` / `- generated_at:` / `## Keys` / 表头 `| key | final phase | l3 verdict | l3 report | evidence |` + 每 key 一行；`evidence` 列硬编码 `.agenticdoc/<key>/achieved.md` | 生成器 `_closure_dossier_md` `conductor.py:666-699`；表头 `:684-686`；行 `:693`；`_l3_verdict` `:603-613` |
| 原子写 | **非原子**：`dossier.write_text(..., UTF-8, newline="\n")`（无 tmp+replace） | `conductor.py:583-586` |
| 去重键 | 无；靠 **write-once 守卫** `if not dossier.is_file():`（已存在则跳过，不重写） | `:580-586` |
| 生命周期收口 | 不删除；stage 复核用一次性产物（键值不进机器判定，人在 gate 前阅读） | 抬 stage-close gate `:595-600` |

**对照意义**：它是“**人读 markdown 汇总**”的落点先例——可作为账本/工单的**只读人读视图**（render-from-JSON），但**不能作为机器真值载体**（非原子、无字段契约、消费方若用 `_md_section` 会截断，见 Q2/P-013）。

### Q2 载体方案对比与推荐

约束来源：AC-001（每处 `(file,test)` 红恰好 1 行、重复扫描行数不变）、AC-007（闭合写状态 closed + 两侧登记标注，重复闭合幂等，无新增行/无重复标注）、Q9（多窗口并发 → 文件锁 `O_CREAT|O_EXCL`）、GC-1（文件驱动去中心化）、spec §2.2（O(新增 verdict) 增量、不重复全量解析历史 verdict、重复扫描不产生新行）、P-003（禁 `open(w)` 截断式写、须 tmp+replace）、P-013（markdown 转录器在下一个 `## ` 截断）。

| 判据 | (a) 单一 JSON sidecar（仿 provenance） | (b) 每红一文件 + 目录枚举（仿 gates seq 重扫） | (c) 单一 markdown 账本表 |
|---|---|---|---|
| 实现形态 | `<xkey>/ledger.json`，一个 JSON 数组，一条记录 = 一处红；新红 append，闭合改该记录 `status`；每次写入整文件 tmp+`os.replace` | `<xkey>/ledger/<id>.json`，文件名/记录字段承载去重键；新红 = 新建文件，闭合改该文件；`enumerate` 目录即队列 | `<xkey>/ledger.md`，markdown 表；一行一红 |
| AC-001 幂等去重 | ✅ 载入成 `{dedup_key: record}` 索引，命中即零写入（provenance `:1372-1375` 同构） | ✅✅ 文件存在性 = O(1) 去重；`O_CREAT|O_EXCL`/锁内 create-if-absent，是最强幂等 | ⚠️ 需文本行扫描 + 分列解析；重复/畸形行无法机械保证 |
| AC-007 重复闭合幂等 | ✅ 单次原子整写；“已 closed → no-op 零写”易判 | ✅ 单文件重写；“已 closed → no-op”易判 | ⚠️ 文本重排敏感；字节级 no-op 难保证 |
| Q9 并发（文件锁） | ✅ 整文件 RMW 持一把 `.mw/xkey-ledger.lock`（`mw_common.acquire_lock:1480`，O_CREAT\|O_EXCL）；锁粒度粗但 N 小 | ✅✅ 每文件锁/`O_EXCL` 创建；锁粒度细、争用低 | ⚠️ 整表 RMW；一旦解锁窗口并发追加即表损坏 |
| GC-1 文件驱动 | ✅ 单文件即协议 | ✅ 目录即协议（gates 先例 `gates.py:480`） | ✅ 单文件 |
| spec §2.2 增量 | ⚠️ 每次整读 O(账本行)；但**不重解析历史 verdict**（增量点在建账去重，不在读文件） | ✅ 目录 `stat`/mtime 可跳过未变文件 | ⚠️ 整表文本解析 O(行) |
| P-003 原子写 | ✅ provenance 原语 `conductor.py:1377-1383` | ✅ gates 原语 `gates.py:198-205` | ⚠️ 可 tmp+replace，但文本 RMW + 人编辑易触发 `open(w)` 类事故 |
| P-013 转录截断 | ✅ JSON 不经 `_md_section` | ✅ JSON 不经 `_md_section` | ❌ 若被 `_md_section` 消费则在下一个 `## ` 截断（`conductor.py:1076-1089`；事故模式见 P-013） |
| 文件规模/寿命 | ✅ 单文件、可整体备份与 diff | ⚠️ 目录无限增长（gate flood 教训 `conductor.py:2213-2222`） | ✅ 单文件 |
| 人可读性 | ⚠️ JSON（需 render 视图） | ⚠️ 多个小 JSON（可用 `jq`/面板） | ✅✅ 直接可读 |

**推荐：账本用 (a)；工单与证据包用 (b)。**

理由（绑定约束，不是偏好）：
1. **账本用 (a)**：AC-001 的措辞是“生成**恰好 1 行**记录”，与“JSON 数组的一个元素”1:1 对应；spec §2.4/RQ-3 已把 `conductor.py:1359` 的 append-only+去重+原子写原语点名为**直接复用**对象；(a) 只引入一个跨 key 文件（`.agenticdoc/_autopilot/xkey/ledger.json`），是 GC-1 的最小实现；AC-007 的状态改写落成**一次整文件原子写**，天然幂等（“已 closed → 零写”）。预期规模极小（FM 真实红数 = 1），(b) 的目录增长优势在此不成立。
2. **必须补一个关键点（(a) 不是纯 append-only）**：provenance 是“审计史上位、永不改写”，而账本行**必须可变 status**（AC-007）。故 (a) 应实现为“**单 JSON 文档 + 记录可寻址 + 状态字段可更新**”，并**在每条记录内保留 append-only 的 `history: []` 转移序列**以保住审计性（与 P-012/P-013 的“留原文”精神一致）。写入一律 `tmp` + `os.replace`（P-003），读改写持 `.mw/xkey-ledger.lock`（Q9）。
3. **工单/证据包用 (b)**：D-003 已定“工单必须是独立文件”（gate payload 承载不下，`gates.py:209-241`）；AC-006 的五项证据天然是**逐工单独立**的原始 stdout/哈希；这正对应 (b) 的“一对象一文件 + 目录枚举”，且沿 gates 的 seq 重扫（`gates.py:243-256`）保证重启安全。
4. **(c) 明确否决为机器真值**：P-013 的截断机制（`conductor._md_section` 到下一个 `## ` 截止，`conductor.py:1076-1089`）意味着任何 markdown 载体一旦进入转录/消费链就有静默截断风险；(c) 只能作为**从 (a)/(b) 渲染的只读人读视图**（不在写侧参与判定，不被 `_md_section` 消费）。

**D-002 落地形状建议（供 design.md 引用）**

- 落点：`<project>/.agenticdoc/_autopilot/xkey/ledger.json`（project-level，与 `config.json` / `gates/` / `stages/` 同级，见 Q5）。
- 记录字段（最小集）：`dedup_key`（= `(file, test_id, 冻结块指纹)`，Q8）、`file`、`test_id`、`block_fingerprint`、`source_key`、`owner_key`、`reason`、`status`（Q8 状态机全集：`detected/ticketed/pending-auth/approved/applied/verified/closed` + 旁支 `rejected/escalated/stale`）、`fail_line`（逐字）、`deciding_source`、`round`、`request_id`（无工单时 null）、`first_seen_at`、`updated_at`、`history`。
- 指纹口径（**design 需定死**）：建议“字节精确 `hashlib.sha256` 为主口径 + `mw_common.sha256_eol_normalized:2926` 另记”，避免 P-010 的 LF/CRLF 双计；AC-006 的 old→new sha256 同样须声明口径（RQ-3 §6 已提此要求）。

### Q3 工单形状

#### 3.1 FM 人工工单逐字字段（`_autopilot/evidence/cross-key-repair-request-20260925-n1.md`）

文件头 code block（逐字）：

```
request_id     : XKEY-2026-09-25-01
created_by     : PM 窗口（user-via-pm-window）
created_at     : 2026-09-25T02:20Z
status         : authorized-R1（2026-09-26T03:04:05+00:00 经人工批准）
affected_keys  : cli-run-state-and-events（红之来源）· cli-hitl-channel（守卫所在 key）
memory_refs    : reflect/plan-writeface-gap.md（A-06 同族：红无 owner）
```

正文逐节字段：

| 节 | 字段/内容 | 机器性 |
|---|---|---|
| §1 事实（可复跑） | 复跑命令（powershell 行）、原始结果（`1 failed…`）、`[COUNT] cli_groups=13`、断言位置（`tests/test_hitl_channel.py:268`）、冻结常量位置、**时间归属**（`runs` 由 source key 新增 vs 守卫由 owner key 冻结） | 命令/计数/路径/行号**可机器抽取**；时间归属为叙述 |
| §2 两侧 L3 的原话 | source key 的登记行逐字（`[VERIFY] REPAIR-R1-F1: cross_key_test=… owner=… handoff=registered not_fixed_by_this_key=True`）+ owner key 的登记行逐字（K-1） | 逐字引文可锚定；登记本身需 D-001 机器化后才是字段 |
| §3 候选处置 | R1/R2/R3 三方案 + 各自代价/风险 | **需判断**，不可机器生成 |
| §4 拟授权的精确边界 | 唯一可写路径；禁止面（断言主体/`ANSWER_OK_KEYS`/负例探针/`migrator/**`/放宽判据）；**必须提交的证据**（`old → new sha256`；`reason`；`是否放宽断言=否`；复跑命令 + 原始 stdout（新文件名，A-09）；对 owner key 原 L3 结论的影响声明）；验收（`pytest … -q` 全绿；全量套件红数 1→0） | 边界/证据/验收**必须机器可判** |
| §5 追认入口 | 决定行格式 `decision: <approved\|rejected> by <who> at <ts>（备注）`；未追认前零写 | 格式固定，可机器解析 |
| §6 执行结果（收口） | worker 名/类型/exit/耗时/工具数；唯一改动（文件:行 + 逐字节前后对照）；`old sha256`/`new sha256`；`是否放宽断言=否`；定向验收（worker 与 PM 窗口各一次复跑原文）；证据文件名；越界检查（逐项未触碰）；查重结果；**两侧登记的意义/闭合声明**；**仍未闭合（故意）** | 逐项可机器核验 |

#### 3.2 A-06 受理件逐字字段（`gui-skeleton-shell/evidence/refreeze-request-20260925-guarded-closeout.md`）

文件头 code block（逐字）：

```
requester : PM window（autopilot 停滞处置）
key       : gui-skeleton-shell
phase     : EXECUTE（P5 两次耗尽 → stalled，gate-0006；2026-09-24T11:33:21Z）
created   : 2026-09-25
status    : ratified-by-human（2026-09-25T03:09:28+00:00 追认；见 §6）
scope     : tasks/006 写面白名单「收窄例外」+ tasks/005 判据 #8 口径澄清
```

正文：§0 触发事实（实测全量结果 + **时间归属对照表**）、§1 申请什么（表：`路径 | 允许的改动 | 为什么非动不可`）、§2 为什么必须申请（结构性不可收敛）、§3 伴随判据口径澄清、§4 真实原因、§5 **反向证据要求**（`old→new sha256` + `reason`；逐条“是否放宽断言/判据=否”；未列明项 sha256 必须不变；**若发现红并非本表归因 → 回头改本申请而不是继续修**）、§6 追认入口。

三条 decision 行（逐字）：
- `**decision: approved by user-via-pm-window at 2026-09-25T03:09:28+00:00**`（+ 4 条收工要求）
- `**decision-2: approved by user-via-pm-window at 2026-09-25T06:48:31+00:00（D-2：三处越表改动追认）**`（含 3 行越表改动的 `路径 | 改了什么 | 机器可核` 表）
- `**decision-3: accepted-as-known-leftover by user-via-pm-window at 2026-09-25T06:48:31+00:00（D-3 / W-1）**`（**显式指派 owner** + 候选修复 + 一并移交项）

#### 3.3 两份额外共同字段（任务点名）

在 FM 列出的基线之外，两份文档还共同具备以下字段，机器化工单必须补上：

1. **时间归属 / 可复算锚点**：FM §1「时间归属」；A-06 §0 的“参照 ↔ 本日实测”双点表。→ 机器工单需 `attribution: {reference, observed, window}`（A-06 明确“用可复算的两点钉住，避免谁弄红的扯皮”）。
2. **反向证据 / 可否证要求**：FM §4「必须提交的证据」；A-06 §5「若发现红并非本表归因，须回头改本申请而不是继续修」。→ 机器工单需 `falsification`：绑定 `authorization_snapshot.sha256` + “越界/归因不符 → 作废”的 fail-closed 规则（直接服务 AC-005）。
3. **收口结果登记**：FM §6（worker/改动/前后 sha/复跑原文/证据文件名/两侧登记闭合）；A-06 decision-2 的越表登记表。→ 机器工单需 `closure` 段（AC-006 五项 + 两侧登记标注，服务 AC-007）。
4. **owner 显式指派（含遗留移交）**：FM §2（`owner=cli-hitl-channel`）；A-06 decision-3（把 C-09 指派给 Stage 3 key）。→ 机器工单需 `owner_key` 与 `leftover_owner`（无 owner → 只升级，服务 AC-002/§2.3）。
5. **唯一的 request_id**：FM 有 `request_id`；**A-06 没有**（只有 `key`+`phase`）。→ 机器工单必须由 conductor **mint `request_id`**（A-06 已暴露“同一治理动作两个文件名形状、无法互相寻址”的缺口）。

#### 3.4 机器化工单字段清单（每字段：来源 / 机器可判 / 谁写）

| # | 字段 | 来源 | 机器可判 | 谁写 |
|---|---|---|---|---|
| 1 | `request_id` | FM 头 `request_id`（A-06 缺失，须 mint） | ✅ 由 `dedup_key`+序号确定性生成 | conductor |
| 2 | `schema_version` | 新建（无先例；机器契约演进所需） | ✅ | conductor |
| 3 | `created_by` | 两文头（`created_by`/`requester`） | ✅ 固定 `conductor` | conductor |
| 4 | `created_at` | 两文头（`created_at`/`created`） | ✅ UTC now | conductor |
| 5 | `status` | 两文头 | ✅ 闭集（Q8 状态机） | conductor（单点推进，Q9） |
| 6 | `source_key` | FM §2（红来源 key） | ✅ provenance `task_key` 反解 | conductor |
| 7 | `owner_key` | FM §2 / A-06 `key` | ✅ 仅当登记机器可读（AC-011）；否则 → 升级不提案（AC-002） | conductor |
| 8 | `affected_keys` | FM 头 `affected_keys` | ✅ = `[source_key, owner_key]` | conductor |
| 9 | `dedup_key` | Q8（`(file, test_id, 冻结块指纹)`） | ✅ | conductor |
| 10 | `file` / `test_id` | FM §1/§2（`cross_key_test=`） | ✅ 仅当结构化登记可得；否则升级 | conductor |
| 11 | `block_fingerprint` | FM §4（冻结常量块） | ✅ 字节精确/EOL 归一（口径 design 定死） | conductor |
| 12 | `reason` | FM §1+§4 `reason` | ⚠️ 锚点（`fail_line`/登记逐字）机器可判；自然语言理由不可 | conductor 写锚点；人/PM 可补叙述 |
| 13 | `fail_line`（逐字） | FM §1 / provenance `:1304` | ✅ | conductor（从 provenance 复制） |
| 14 | `deciding_source` / `round` | provenance `:1295-1296` | ✅ | conductor |
| 15 | `repro_command` + `observed_result` | FM §1 | ✅ 机器复制（框架不重跑，见 RQ-1 Q4） | conductor |
| 16 | `attribution`（双点可复算） | **额外共同字段**（FM §1 / A-06 §0） | ⚠️ 参照点机器可读，归属判定需锚 | conductor |
| 17 | `memory_refs` | 两文头 | ⚠️ 自由文本（可空） | conductor（自登记播种） |
| 18 | `candidates`（候选处置） | FM §3 | ❌ 需判断 | PM/人（agent 起草），conductor 原样承载 |
| 19 | `proposed_boundary`（唯一可写路径 + 冻结块行集合 + 允许改动种类） | FM §4 | ✅ 必须机器化（D-006 启发式 + 人追认；AC-005 行集合子集判定） | conductor（启发式推导）+ 人追认 |
| 20 | `forbidden`（禁止面） | FM §4 | ✅ 路径/模式集合（默认：断言主体、其它文件、放宽判据） | conductor（默认）+ 人 |
| 21 | `authorization_snapshot`（工单创建时文件 sha256） | FM §4 `old sha256`；AC-005 | ✅ | conductor |
| 22 | `required_evidence`（AC-006 五项固定清单） | FM §4 + AC-006 | ✅ 固定清单，缺一不闭合 | conductor |
| 23 | `verification`（定向复跑命令 + 全量红数 before→after） | FM §4 验收 | ✅ 命令/计数机器可核 | conductor（命令）+ 执行侧落原文 |
| 24 | `falsification`（归因不符 → 作废重开） | **额外共同字段**（A-06 §5） | ✅ 规则可判（sha 漂移/越界即 fail-closed） | conductor |
| 25 | `authorization_entry`（追认入口） | 两文 §6 | ✅ gate id + 决定行格式 | conductor（指路 gate） |
| 26 | `decisions: []`（append-only 多条决定：approved/rejected/leftover） | FM decision 1 条；A-06 decision×3（含 `accepted-as-known-leftover`） | ✅ 结构可判；“who”为人类声明（见 D-008） | 人（gate 作答）→ conductor 折叠 |
| 27 | `leftover_owner`（遗留显式指派） | 额外共同字段（A-06 decision-3） | ✅ | 人 + conductor |
| 28 | `closure`（执行结果收口） | FM §6（AC-006/007） | ✅ 逐项机器核验 | conductor 组装 |
| 29 | `escalation`（无登记红只升级） | spec §2.3/AC-002 | ✅ | conductor |
| 30 | `budget` / `stall_streak`（R-3：无 gate TTL，时间维度靠预算+streak） | 复用 `advance_stall_ticks`/`mark_stalled` 家族 | ✅ | conductor |

**载体（D-003）**：独立文件，JSON 为机器契约（仿 gate frontmatter 的角色分离），落在 `<xkey>/tickets/<request_id>.json`；人读视图（可选）由它 `render` 成 markdown，但**不参与机器判定**（P-013）；gate 的 `context_refs` 只放该文件的**单行相对路径**（承载约束：`gates.py:209-241`）。

### Q4 conductor tick 内“增量聚合扫描”的挂载点与开销边界

#### 4.1 主循环与 tick 结构

- 进程主循环 `conductor.main` `conductor.py:2463`：`--once` 走单 tick `status = tick(project_root, st)` `:2494`；常驻循环 `while not stop.is_set(): tick(project_root, st)` `:2497`（act-then-sleep，首 tick 在任何等待之前）。
- `tick()` `conductor.py:1955`：先写 `beat`（AC-019）→ `config.cached_load` 的 enabled/paused 门 `:1964` → goal.md 变更检测 `:1967+` → **`orchestrate(project_root, st)` `:2019`** → 返回 `ok`；异常被兜底为 `config` 事件 + `error`（`:2021-2023`，tick 永不抛）。
- `orchestrate()` `conductor.py:159`（docstring 明写 **Zero private state：每个决策每 tick 从文件重派生，D-102**）：
  - `cfg = config.cached_load(project_root)` `:168`
  - **步骤 F**：`if not _consume_answered_gates(project_root, st): return` `:172`（corrupt gate → 整 tick 跳过）
  - **F2**：`reconcile_orphans(project_root, st)` `:176`
  - roadmap 加载/错误分支 `:179-186`；无 roadmap → 派 roadmap-writer 并 return `:189-191`
  - `if not _stage_activation(...): return` `:193`
  - 跨 stage 视图构建 `for stage in rm.stages:`（`deps_of/status_of/stage_of`）`:203-214`
  - `_apply_stalled_approvals(project_root, st, status_of, stage_of)` `:211`
  - `_apply_stalled_rejections(project_root, st, status_of, stage_of)` `:214`
  - `in_flight_keys = {...}` `:216`
  - 派发循环 `for stage in rm.stages:` `:224`（内含 `_stage_closure` `:229` 与 per-key `_advance_key`）

#### 4.2 推荐挂载点

**在 `orchestrate()` 内、`conductor.py:214`（`_apply_stalled_rejections` 调用）之后、`conductor.py:216`（`in_flight_keys` 计算）之前，插入新步骤：**

```
    _apply_stalled_rejections(project_root, st, status_of, stage_of)   # :214

    if cfg.get("xkey_repair", False):                                  # AC-008 开关，默认 false
        _xkey_aggregate(project_root, st, status_of, cfg)              # ← 新增：每 tick 增量聚合扫描

    in_flight_keys = {                                                 # :216
```

理由（绑定现有控制流，非偏好）：
1. **在 `_consume_answered_gates` 之后**（`:172`）：xkey-authorize 的已答 gate 必须先被消费/折叠，聚合扫描才能看到本 tick 的最新工单状态；且 `_consume_answered_gates` 的 corrupt-gate 跳 tick 策略（返回 False）继续对它前置兜底。
2. **在 `_apply_stalled_approvals/_apply_stalled_rejections` 之后**（`:211/:214`）：这两步会就地改 `status_of`（stalled→running / →closed-legacy）；聚合扫描要用“本 tick 已生效的 key 终态视图”判断 owner key 是否终态（AC-002/AC-003 的前提），否则会用陈旧状态。
3. **在 per-stage 派发循环之前**（`:224`）：本 tick 新抬起的 `xkey-authorize` gate 与新登记的待处置工单，能在同一 tick 的后续流程可见（与 `_apply_stalled_approvals` “就地改 `status_of` 让本 tick 的 per-key 机器已看到”的设计一致，`conductor.py:2205-2206`）。
4. **受 `enabled/paused` 与 AC-008 开关双重门控**：`tick` 已挡 enabled/paused（`:1964`）；聚合扫描再加 `cfg["xkey_repair"]`（默认 false，落 `_autopilot/config.json`，P-015），保证关闭时对既有流程零行为变化。
5. **不新增 return 早退**（除非与既有策略一致）；异常沿 `tick` 的兜底被记 `config` 事件，不杀循环。

#### 4.3 同类“消费已落盘产物”的模板步骤

| 模板 | 锚点 | 可借用之处 |
|---|---|---|
| `_consume_answered_gates` | def `conductor.py:274`；调用 `:172` | “目录枚举 → 幂等消费 → 抬下一动作”的主形状；返回 False 让整 tick 跳过 corrupt 输入的策略 |
| `_consumed_gate_ids` | `conductor.py:255-272` | **durable 消费记录**：timeline `gate-answered` 事件为持久记录，重启重派生同一集合（AC-007 幂等的现成范式） |
| `_apply_stalled_approvals` | `conductor.py:2190` | 消费已答 gate → 改盘面 → 就地改 `status_of` → 追加 `gate-answered`/`resume`；且带**durable 消费守卫**（`:2213-2222` 的 flood 注释） |
| `_apply_stalled_rejections` | `conductor.py:2258` | 拒绝去向 + 终态清扫（`delete_bad_draft_marker` `:2286`）——对应 AC-007“闭合写回 + sidecar 收口” |
| `_resume_credits` | `conductor.py:2168` | “每次调用从 gate 目录重派生计数，零私有状态、重启安全、不可漂移”的正面范式 |
| `_stage_closure` | def `conductor.py:560`；调用 `:229` | “终态条件满足 → write-once 产物（`:580`）+ 抬 gate（`:595`）”的幂等抬升范式 |
| `reconcile_orphans` | `conductor.py:2371`；调用 `:176` | 孤儿/丢失产物的文件驱动对账范式（可借用于“工单跨重启后存活”） |
| `_create_gate` / `_gate_open` | `conductor.py:2064` / `:2093` | 抬 gate 的唯一入口（锁内、None=下 tick 重试）与 pending 探测；**注意**：`_gate_open` 目前只按 `kind/loop/stage` 过滤，**没有 `key`/`request_id` 过滤参数**，xkey 逐工单去重需扩展它（加 `ref=` 或新增 `_xkey_gate_open(request_id)`），否则会重演 gate flood |

#### 4.4 挂载点的幂等性与重启安全要求（durable / 幂等 / 零私有状态）

- **durable（持久）**：任何“已消费/已建账/已抬起”事实必须能从文件重派生——账本自身的 `dedup_key` + 每条记录的 `history`、gate 目录、timeline 事件。**禁止**在 `ConductorState` 里新增内存游标/计数器来记“扫到哪”。（先例：`_consumed_gate_ids` 从 timeline 重派生，`conductor.py:255-272`；`_resume_credits` 从 gate 目录重派生，`:2168`。）
- **幂等**：① 同一 `(file, test_id, 指纹)` 重复扫描 → 账本零新增（AC-001）；② 同一 request_id 重复闭合 → 零新增行、零重复标注（AC-007）；③ 同一 request_id 不重复抬 gate（`_gate_open` 家族，且须加 request_id 维度——见 4.3）。**gate flood 是本设计的一等红线**（实测 6684 条 / ~12h 的全部成因是缺少 durable 消费守卫，`conductor.py:2213-2222`）。
- **零私有状态**：聚合输入全部来自落盘：各 key 的 `l3-verdict-provenance.json`（新 below 记录 = 新红候选，写入点 `conductor.py:1555-1558`）+ 其 `deciding_source`（承载 D-001 的机器登记）+ `_autopilot/xkey/ledger.json` + gates 目录 + `status_of`（本 tick 派生）。`orchestrate` 的 docstring 已把这一条定为模块级契约（`conductor.py:159-166`）。
- **抗锁竞争**：账本写入持 `.mw/xkey-ledger.lock`（`mw_common.acquire_lock:1480`，O_CREAT|O_EXCL）；锁忙时**不得**半写——按现有惯例返回并下 tick 重试（先例 `_create_gate` 锁忙返回 None `conductor.py:2071-2074`）。多窗口并发（Q9）下，工单状态推进只在 conductor 单点发生（worker 只落修复产物，不改状态）。

#### 4.5 开销边界（spec §2.2）

- **输入**：只读“本 tick 尚未建账的 red 候选”。候选来源 = 各 key 目录的 provenance sidecar 中的 `verdict=="below"` 记录；用账本 `dedup_key` 索引做 **O(1) 去重**，因此**不重复全量解析历史 verdict**（满足 §2.2 的“O(新增 verdict 数)”）。（若跨 key 数或红数增长，可在 `_all_workers_dirs`（`conductor.py:2028`）之上加 mtime 短路，但当前 FM 真实规模 N=1 无需。）
- **账本读写**：load O(账本行) + 命中则零写；新红/状态变更 → 单次整文件 `tmp`+`os.replace`。
- **gate 探测**：`_gate_open` 是一次 `gates.enumerate`（O(gate 数)）；**必须**先 `_gate_open(request_id)` 再 create，保证 pending 工单不重复抬 gate。
- **对既有 tick 周期的扰动**：与 `_consume_answered_gates`/`_apply_stalled_*` 同量级（各自都做目录枚举）；判定验收口径沿用既有“tick 测试不超时”而非新指标（spec §2.2）。

### Q5 证据包落点

#### 5.1 现有证据落盘约定（实测）

- **per-key**：`.agenticdoc/<key>/evidence/`（研究/设计证据 `evidence/research/*.md`、`quality-gate-report-*.md`、人工申请件如 `refreeze-request-*.md`）+ `.agenticdoc/<key>/evidence/runs/`（原始 run 产物、复跑 stdout、`collect_*.py`）。MW 仓 30+ 个 key 均有 `evidence/`，其中 16 个带 `evidence/runs/`；FM 仓逐 key 同构（如 `cli-hitl-channel/evidence/` + `runs/` 45 文件）。
- **key 根**：`achieved.md`、`l3-report.md`、`l3-verdict.txt`、`l3-verdict-provenance.json`、`.mw-achieved-baddraft.json`。
- **project-level**：`.agenticdoc/_autopilot/` = `config.json` / `_roadmap.md` / `timeline.jsonl` / `gates/` / `stages/` / `evidence/` / `reflect/`；**conductor 自己写**的产物落在这里：stage dossier → `_autopilot/stages/`（`conductor.py:578-586`）、QG report → key `evidence/`（`_done_transaction` `:1741-1757`）。
- **FM 现状（关键）**：这次跨 key 治理的**人工工单与修复证据都落在 project-level**：`.agenticdoc/_autopilot/evidence/cross-key-repair-request-20260925-n1.md` 与 `_autopilot/evidence/xkey-n1-repair-20260926.txt`（扁平文件名，非某个 key 的 `evidence/`）。

#### 5.2 推荐落点与理由

**推荐：新机制的账本/票据/证据包统一落在 project-level 的 `.agenticdoc/_autopilot/xkey/`，不写进任何受影响 key 的 `evidence/`。**

| 对象 | 推荐路径 | 理由 |
|---|---|---|
| 跨 key 红账本（D-002） | `.agenticdoc/_autopilot/xkey/ledger.json` | 账本是**跨 key**对象，无单一 owner key；`_autopilot/` 已是 conductor 拥有的 project-level、文件驱动落点（config/roadmap/timeline/gates/stages） |
| 工单（D-003） | `.agenticdoc/_autopilot/xkey/tickets/<request_id>.json`（+ 可选 `.md` 人读视图） | D-003 要求独立文件；`<request_id>` 命名与 FM 的 `XKEY-2026-09-25-01` 直接对应，可被 gate 的 `context_refs` 单行指路 |
| 证据包（D-004，AC-006 五项） | `.agenticdoc/_autopilot/xkey/tickets/<request_id>/evidence/`（仿 key 的 `evidence/runs/`：原始 stdout/哈希/前后红数各一文件 + `closure.json` 索引） | 证据天然逐工单独立；把“原始 stdout 逐字落盘”（P-012）放进子目录，闭合时 `closure.json` 汇总并校验五项齐备 |
| 关闭/审计留痕 | 复用 `.agenticdoc/_autopilot/timeline.jsonl`（`xkey-*` 事件） | 与 gate 消费同构，durable/幂等/可重派生（`_consumed_gate_ids` 范式） |

**为什么不写进受影响 key 的 `evidence/`**：① 受影响 key 多为 **DONE**（FM 案例 owner key 已 DONE）——写它的目录本身就是“改冻结面”，会自相矛盾并需要另一次授权；② 跨 key 对象没有单一 owner，写任一侧都是偏置；③ 证据链的单点真相（“这次治理到底改了什么”）应落在治理通道自己的目录，才能被 gate、面板与审计一致寻址。此点也**与 FM 现状对齐**（FM 把 XKEY 工单与修复证据放在 `_autopilot/evidence/`），只是把扁平手搓文件升级为 `_autopilot/xkey/` 的结构化机器形状（框架级统一）。保留 `_autopilot/evidence/` 给纯人工/历史叙述件（如 FM 现有两份）。

**命名避坑**：FM 另有一个 key 叫 `migration-ledger`（含 `evidence/research/design-ledger-storage-2026-09-17.md`），与本机制“跨 key 红账本”**同名不同物**；本机制路径带 `xkey/` 前缀可消歧。

### Q6 未发现（附搜索模式）

| 未发现项 | 搜索模式 | 范围 | 命中 |
|---|---|---|---|
| 跨 key 红账本 / 工单 / xkey | `xkey\|ledger\|ticket\|工单\|账本\|cross_key\|crosskey\|handoff` | `packages/multi-workers/*.py, autopilot/*.py`（本会话自测） | **0** |
| 证据包组装器（old→new sha256 + 复跑 stdout + 红数 before→after 打成一包） | `sha256` + 证据包结构 | `packages/multi-workers/**` | 未发现（RQ-3 §7 同结论；碎片：`closure.py:135` / `mw.py:995-1040` toolchain run meta） |
| 机器化工单模板 / 字段契约 | `request_id\|authorized\|ratified` | `packages/multi-workers/**/*.py` | 0（仅存在于 FM 人工 md） |
| xkey 专用 gate kind / 消费分支 | `GATE_KINDS` 闭集 | `gates.py:52-58` | 仅 `stage-confirm/stage-close/stalled/budget-exhausted/goal-change`，无 xkey |
| 现成活体 sidecar 实例（供形状核验） | 文件枚举 `l3-verdict-provenance.json` / `.mw-achieved-baddraft.json` | MW 仓与 FM 仓 `.agenticdoc/**` | 均未发现（文件为运行期生成，已在 DONE 树清收；形状以代码为准） |

## 结论 → 决策映射

| # | 结论（见上文） | 服务的决策 / 验收 |
|---|---|---|
| 1 | Q1：四个 sidecar 的落盘范式已盘点清楚；provenance = “append-only+去重(`task_key`)+原子写、永删不覆盖”；baddraft = “内容寻址+三条件授权+**显式生命周期收口**”；gate = “一对象一文件+seq 目录重扫+durable timeline 消费”；dossier = “人读 markdown write-once，非机器契约” | D-002 复用 provenance 写原语但须**加可寻址去重键与可变 status**；D-004 复用 baddraft 的“缺项/漂移即拒 + 收口”范式；工单勿用 markdown 作机器契约 |
| 2 | Q2：推荐**账本用 (a) 单一 JSON sidecar**（记录含 `dedup_key`+`status`+append-only `history`，整文件 tmp+replace，锁内 RMW）；**工单/证据包用 (b) 一对象一文件+目录枚举**；**(c) markdown 表否决为机器真值**（P-013 截断：`_md_section` `conductor.py:1076-1089`），仅可作 render 视图 | **D-002** 载体与去重键、**D-003** 独立文件、**D-004** 逐工单证据目录；判据 AC-001/AC-007/Q9/GC-1/§2.2/P-003/P-013 全部落位 |
| 3 | Q3：机器化工单 30 字段清单（§3.4），其中 **`request_id`/`proposed_boundary`/`authorization_snapshot`/`required_evidence`/`decisions[]`/`closure` 必机器可判**；`candidates`/`memory_refs` 不可机器生成；两份文档额外共同字段 = **时间归属双点、反向证据要求、收口登记、owner 显式指派（含遗留）、唯一 request_id** | **D-003** 工单 JSON schema；AC-003（字段含 request_id/affected_keys/精确边界/追认入口）、AC-006、AC-007；P-014（多字形/逐字锚定） |
| 4 | Q4：挂载点 = `orchestrate()` 内 `conductor.py:214` 与 `:216` 之间（`_apply_stalled_rejections` 之后、`in_flight_keys`/派发循环之前），受 `cfg["xkey_repair"]` 门控；模板 = `_consume_answered_gates:274` / `_consumed_gate_ids:255` / `_apply_stalled_approvals:2190` / `_resume_credits:2168` / `_stage_closure:560` / `reconcile_orphans:2371`；`_gate_open:2093` **须扩 request_id 维度**否则重演 flood（`conductor.py:2213-2222`）；要求 durable/幂等/零私有状态（`orchestrate` docstring `:159-166`） | **conductor 挂载点与开销边界（spec §2.2）**；AC-008（默认关、关闭零行为变化）；AC-001/AC-007 幂等；Q9 单点推进 |
| 5 | Q5：账本/票据/证据包统一落 `.agenticdoc/_autopilot/xkey/`（project-level），**不写任何受影响 key 的 `evidence/`**（DONE key 不可写、跨 key 无单 owner；与 FM 把 XKEY 件放 `_autopilot/evidence/` 对齐并升级为结构化形状） | **D-002/D-003/D-004 落点**；与 GC-1 一致；避免路径命名与 FM `migration-ledger` key 混淆 |
| 6 | 需 design.md 定死的两个子口径：① **冻结块指纹与 old→new sha256 的哈希口径**（字节精确为主、EOL 归一另记，避开 P-010）；② **`_gate_open` 的逐工单去重维度**（新参数或新函数） | D-002/D-004 的 AC-001/AC-005/AC-006 可判定性；AC-003 工单不重复抬 gate |
