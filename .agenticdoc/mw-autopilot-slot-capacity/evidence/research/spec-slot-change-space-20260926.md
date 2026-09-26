# Research: RQ-4 改动空间与首个失败模式（"改 / 不改"的候选与代价）

> Key: mw-autopilot-slot-capacity（spec 期调研，只读角色）
> 日期: 2026-09-26
> 边界声明：本笔记**不下最终决策**（决策是 PM + 用户的事），只给"选项与代价"；成因判定（AC-002）与吞吐实测（AC-003）分别属 RQ-1/RQ-3。

## TL;DR

- 5 个方案：**M1** 只提默认值 / **M2** 默认不变 + 机器层扩域 / **M3** 自适应 / **M4** 两层上限（key × 每 key worker）/ **M5** 不改。
- **M1 的两个隐藏事实**：(a) 现场项目（FM/E2）的 config.json **都显式写了 `max_parallel_keys: 2`**，所以"提默认值"对已存在项目是**空操作**（只有"文件里没这个键"的项目才吃新默认）；(b) 若只改 Python 侧默认，TS 的 `saveConfig` 写全 13 键的路径会**静默把值改回 TS 默认**（不改 floor 则不会 fail-closed，只会被覆盖）。
- **M2 的首个失败模式是"静默空操作"（有锚点的推导）**：机器层的"空值即未决定"哨兵 `EMPTY_VALUE` 对 int 无定义，项目层显式 `2` 与"未写"不可区分，而两条规范写路径都把 13 键材料化 ⇒ 机器层设了也不生效、且不告警。M2 落地前必须先解决这个语义缺口。
- **M4 不是"改参数"**：它撞既有"每 key 串行"不变量（`conductor.py:1095`），属语义变更。
- **M3 代价最高且有 GC-1 风险**：只要调节逻辑进内存即违反 GC-1；要做到 GC-1 又缺"槽位等待时长"的可观测载体（cap 阻塞今天不留 timeline 事件）。
- **前置问题结论**：`key-status=stalled` 的 key **不占槽**（`conductor.py:274` 在 cap 判定前就跳过）；但**"行状态卡住"的 key 占槽，而且不会被标成 stalled**（`_advance_key` 见 in-flight 即 return，launcher 孤儿静默窗默认 **90 分钟**）——这才是 spec §4 风险 1 的真实机制。
- GC 校验：无方案天然违反 GC-1/GC-3/GC-4；**M3 有条件违反 GC-1**；M4 违反的是既有串行不变量（非 GC 条目）。
- 可观测性缺口：面板 `slotsUsed` 只数 `running`（conductor cap 数的是**非终态**，含 `pending`）；cap 阻塞**零留痕**；`mw doctor`/`mw status` **无槽位分节**；无机器级总账（U-5）。

## 决策问题

支撑 spec §3 draft **AC-004**（≥3 个候选改动方案 + 首个失败模式 + 可逆性 + GC 校验）、**AC-005**（新默认值与生效层两侧逐字段一致；不改也要有证据链）与 **AC-006**（可观测性），并为 §4 **U-1**（目标形态 A/B/C/D）、**U-3**（能否接受成本与失败率上升）、**U-5**（多项目各自计额 vs 机器层统一计额）提供决策输入：

1. "提高并行度"这条路上有哪几种形态，各自改哪里、取值域多大、两侧镜像要同步什么？
2. 每种形态**第一个**坏在哪个环节，判据是什么，本仓库有没有同类史实？
3. 每种形态怎么退回，退回后留下什么残留？
4. 哪些形态违反 GC-1/GC-3/GC-4（或需要额外改动才满足）？
5. 提高后操作者需要看到什么才不会盲飞？现在已有多少、缺多少？
6. 前置问题："stalled key 是否占槽"——代码上能否确认？（这是 M1/M2 有无收益的前提）

## 调研方法与出处

只读操作；除本笔记与本人 worker 目录的 `output.md` 外未写任何文件，未 commit。

grep 模式：
- `max_parallel_keys`、`in_flight_keys`、`_is_in_flight`、`_row_belongs_to`
- `max_workers|max-workers`、`slots|slotsUsed|slotsMax`、`EFFECTIVE_KEYS|EMPTY_VALUE|autopilot-defaults`
- `stalled`、`orphan`、`acquire_lock|Could not acquire lock|configLockPath|retries`
- `429|rate.?limit|quota|port conflict|lock busy`（multi-workers / coding-agent CHANGELOG、`_pitfalls.md`、`_project_log.md`）
- timeline 事件类型分布（`ev` 字段 group-by）与 `_workers.parallel` 尾部

读过的文件（含行段）：
- `packages/multi-workers/autopilot/config.py`（1–160）
- `packages/multi-workers/autopilot/effective_config.py`（1–250）
- `packages/multi-workers/autopilot/conductor.py`：80–340（tick / in-flight / cap gate）、1082–1117、1595–1610、2113–2155、3944–4020、4019–4090
- `packages/multi-workers/autopilot/dispatch.py`：409–610（dispatch 事件）
- `packages/multi-workers/mw_common.py`：1444–1560（parse/serialize/lock/update_status）、1857–1930（orphan 静默窗）、2014–2100（`_doctor_autopilot`）
- `packages/multi-workers/launcher.py`：1–60、510–625（orphan reconcile）、775–880（poll 循环）、940–1000（spawn）、1015–1050（CLI）
- `packages/multi-workers/mw.py`：300–340（serve）、400–435（start）、4485–4500（bootstrap）
- `packages/multi-workers/autopilot/timeline.py`：55–100（EVENT_TYPES）
- `packages/multi-workers/proxy_multi.py`（全文）、`providers.json`（全文）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`：1–310（readConfig/saveConfig/INT_RANGES）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`：80–110、240–280、463–525、590–650
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`：70–110、280–320
- `packages/coding-agent/src/extensions/agent-team-loop/shared/file-lock.ts`（全文）、`worker-store.ts`（全文）、`index-store.ts`（全文）
- `packages/multi-workers/test_autopilot_config_parity.py`：1–130、`test/fixtures/autopilot-config-corpus.json`、`test_autopilot_config.py`、`test_autopilot_effective_config.py`、`test_autopilot_docs.py`、`test_autopilot_conductor.py`（730–750）
- `packages/multi-workers/README.md`：220–230；`CHANGELOG.md`（相关条目）；`UPDATE.md`
- `.agenticdoc/_pitfalls.md`：185–235（P-017…P-022）；`.agenticdoc/_project_log.md`
- 现场数据：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\{_autopilot/config.json,_autopilot/_roadmap.md,_workers.parallel}`、`H:\git\E2Feature\.agenticdoc\_autopilot\config.json`、`H:\git\JCodingAss\.agenticdoc\_autopilot\`

---

## 发现

### 0. 先决事实：并行度的两条层与两侧镜像（M1–M5 的共同边界）

**[事实] key 层上限**
- 默认 2、floor 2：`autopilot/config.py:52`（`DEFAULT_CONFIG`）、`:70`（`_INT_RANGES` → `(2, None)`，**无上限**）、`:16`（注释 `(floor 2)`）；TS 镜像 `status-model.ts:106`、`:136`。
- 唯一 gate 点：`conductor.py:289` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])): continue  # parallel cap — key starts on a later tick`。
- `in_flight_keys` = 有**非终态 worker 行**的 key 集合：`conductor.py:258-263`，`_is_in_flight` = `status not in mw_common._TERMINAL_STATUSES`（`conductor.py:2131-2132` + `mw_common.py:158`，终态 = `done|failed|needs-clarification`）。⇒ 判定依据是 `_workers.parallel` 的行状态，**不是** key-status，**不是** 是否真有进程存活。

**[事实] worker 层上限（今天只有 CLI 一条路）**
- `launcher.py:837` `if max_workers and len(running_procs) >= max_workers:` → 超限入 `pending_queue`（`:868`），reap 后补位（`:809-811`）。
- `max_workers` 默认 **None = 不限制**：`launcher.py:847`、`:1021`；只有 `mw serve --max-workers` / `mw start --max-workers` 会转发（`mw.py:327-328`、`mw.py:423-424`），`mw bootstrap` 固定传 `max_workers=None`（`mw.py:4495`）。
- `max_workers` **不在 `_autopilot/config.json` 的 13 键里**（`config.py:48-79` 全表；`autopilot/*.py` 内 `max_workers` 零命中，仅 launcher CLI 命中）。⇒ 它是 P-015 家族的"仅进程参数"：重启路径换一条（bootstrap / 手动 serve）即丢。

**[事实] 两层配置（project fail-closed + machine fail-soft）今天只覆盖 2 个键**
- `effective_config.py:62-66` `EFFECTIVE_KEYS = ("xkey_verify_cmd", "xkey_verify_cwd")`；`:68` `EMPTY_VALUE`；越域键的规则是"**告警并忽略**"（`:167-168` `is not machine-overridable (ignored)`，进 `diagnostics`）。
- 消费侧只补这 2 个键：`conductor.py:87-105`（`for key in effective_config.EFFECTIVE_KEYS: if origins[key] == "machine": values[key] = ...`）。
- **TS 侧没有机器层**：`autopilot-defaults` 在 `packages/coding-agent/src` 与 `packages/coding-agent/test` 下零命中；`status-model.ts::readConfig` 只读 `<project>/.agenticdoc/_autopilot/config.json`（`:238-241`），缺文件即 `freshDefaults()`。⇒ 机器层是 **Python-only**。

**[事实] 两侧镜像的判据在哪里**
- 跨语言 parity 表：`test_autopilot_config_parity.py`，语料 `test/fixtures/autopilot-config-corpus.json` **53 例、冻结 sha256**（`:56-57` `FROZEN_CORPUS_SHA256`/`FROZEN_CORPUS_COUNT`）；判据 P1（accept/reject + 字段名集合逐例相同）、P2（`save_config` 与 `saveConfig` 逐字节）、P4（语料 sha + 覆盖），TS 侧由 vitest `autopilot-config-parity.test.ts` 反向判定。
- 语料里与 `max_parallel_keys` 直接相关的锚点：`range-max-parallel-low` = `{"max_parallel_keys": 1}` → **reject**（`error_fields=[max_parallel_keys]`）；`range-max-parallel-min` = `2` → accept；`partial-key-max_parallel_keys` = `2` → accept；`bigint-2p53` = `9007199254740992` → accept（既有已知残差 P-022）。
- 文档锚点：`test_autopilot_docs.py` 的 `README_ANCHORS` 钉死 `~/.agents/autopilot-defaults.json`、"machine-overridable pair" `xkey_verify_cmd + xkey_verify_cwd`、"out-of-domain example keys" `xkey_repair`/`xkey_verify_timeout_s`、"告警并忽略"。README 配置表已有该键：`README.md:225`（`max_parallel_keys | 2`）。

**镜像失败的两种形态（给锚点证明）**
1. **fail-closed 拒绝（改小 floor 时）**：若只把 Python `_INT_RANGES` 的 floor 从 2 降到 1，则 TS `INT_RANGES`（`status-model.ts:136`）仍为 `[2, null]` → 语料 `range-max-parallel-low` 从"两侧 reject"变成"Python accept / TS reject" ⇒ P1 与 P2/P4（冻结 sha）同时红（`test_autopilot_config_parity.py:56-57`）。
2. **fail-silent 覆盖（改大默认值时）**：`INT_RANGES` 的 hi 是 `None`，所以"默认 2→4"**不会**被任何一侧拒绝——但两条写路径都会把默认值材料化：Python `save_config`（`config.py:147-160`，写全 13 键）与 TS `saveConfig`（`status-model.ts:289-300` 按 `DEFAULT_CONFIG` 顺序写全 13 键）。TS 的 RMW 入口 `console.ts:308-310` 先 `readConfig`（缺键 → TS 默认 2）再 `saveConfig` ⇒ **只改 Python 默认时，任何"文件里没有该键"的项目，在一次 `/autopilot enable|disable|pause|resume` 后会被静默改回 2**。

**[事实] 现场项目都把该键材料化了**
- `E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\config.json`：9 键，显式 `"max_parallel_keys": 2`；`_workers.parallel` 尾部同时存在 **2 行 `status=running`（2 个不同 key：`ap-gui-run-control-hitl-007-…`、`ap-gui-live-monitor-repair-a1`）**，与 cap=2 打满一致。
- `H:\git\E2Feature\.agenticdoc\_autopilot\config.json`：9 键，显式 `2`。
- `H:\git\JCodingAss`：有 `_autopilot/`；MW 根 `.agenticdoc/` 下**没有** `_autopilot/`（= autopilot 从未启用，默认值生效）。

> 现场含义：**"改默认值"对已有项目是空操作**——FM/E2 的文件都显式写了 2，只有"文件里没这个键"的项目才吃新默认。要改已有项目就得改各项目 config.json，或走机器层（M2）。

### 1. 候选方案 M1–M5 并列比较

| | M1 只提默认值 | M2 默认不变 + 机器层 | M3 自适应 | M4 两层上限（key × 每 key worker） | M5 不改 |
|---|---|---|---|---|---|
| **确切改动点** | `config.py:52`（+ `:16` 注释）与 `status-model.ts:106` 同改；`README.md:225` | `effective_config.py:62-66` 增键、`:68` `EMPTY_VALUE` 增哨兵、`:31` 注释；`conductor.py:87-105` 无需改（循环 `EFFECTIVE_KEYS`）；**另需**给 TS 加机器层读取（今天没有） | 新键（如 `parallel_policy`）或给 `max_parallel_keys` 加"自适应"取值；conductor 需新增"等待时长/队列深度"状态；两侧 `DEFAULT_CONFIG`/`INT_RANGES`/`BOOL_FIELDS`、语料 53 例、README、doctor 全动 | 新键（如 `max_workers`）落 `config.json`；launcher 读它（今天 `launcher.py:837` 只认 CLI）；serve/bootstrap 转发（`mw.py:327/4495`）；两侧镜像 + 语料 + 文档 | 无 |
| **取值域与校验** | `(2, None)` 不变；默认改 N≥2 即不动 floor/语料；若想允许 1（串行）则动 floor → 语料红 | 取值域沿用 `(2, None)`，`config.validate_config({key: value})`（`effective_config.py:171`）已可校验；但 `EMPTY_VALUE` 是"空值即未决定"语义，int **没有空值**（见 §2 M2） | 需重新定义（枚举 + 上限 + 触发阈值）；新增域的每一条都要进语料 | 新键 `(1, None)` 或 `(2, None)`；与 `round_budget`（同 key 内轮预算）语义必须区分开 | — |
| **两侧镜像成本** | 低：两处默认值 + README；改错方向（动 floor）则 P1/P2/P4 红 | **中高**：Python 侧 3 处 + 全部"越域告警"测试 + README 锚点；TS 侧要从 0 造一个机器层读取，否则 monitor 显示与 conductor 实际值不一致 | **最高**：新键=第 14 键，跨语言 parity 语料 53 例重冻、TS 类型/校验/快照全动 | 高：新键 + launcher 消费 + serve 透传 + 两侧镜像 | 无 |
| **可逆性 / 残留** | 改回两个默认值即回到今天；**残留**：被写路径材料化过的项目文件保留新值（写全 13 键），不会自动回退 | 删 `~/.agents/autopilot-defaults.json` 里的键即回退；残留 = `EFFECTIVE_KEYS`/`EMPTY_VALUE` 代码与测试（无害）、以及**未加 TS 机器层时永远不会生效** | 删策略键即回退；残留 = 自适应状态文件（需显式清理声明） | 删键即回退；残留 = 既有 CLI `--max-workers`（本就存在） | 无 |
| **GC-1（无中央调度器）** | 满足（纯参数） | 满足 | **条件满足**：只要"调多少"是每 tick 从文件重推即可；一旦引入进程内自适应控制器即**违反 GC-1** | 满足（launcher 的 `pending_queue` `launcher.py:868` 本就是进程内、由文件驱动的补位队列，不是跨进程调度器） | 满足 |
| **GC-3（文件锁并发控制）** | 满足；但锁竞争随并发升（见 §2） | 满足 | **需额外改动**：等待时长状态要么进新文件（+1 个锁面）要么只能靠 timeline 反推 | 满足；worker 数上升放大 `_workers.parallel` RMW 频率 | 满足 |
| **GC-4（看门狗语义不退化）** | 表面不退化（活动看门狗按 token/工具/轮活动判定，`worker-mode.ts:148` `DEFAULT_IDLE_MS=10min`），但机器变忙后需重测 | 同 M1 | 自适应会改变并发曲线，看门狗误判风险需重测 | 同 M1 | 不退化 |
| **首个失败模式（详见 §2）** | **机器级共享配额/上游饱和**（先于锁） | **静默空操作**：项目层显式值永远赢过机器层 | **震荡/抖动**（瞬时队列深度驱动的反复放缩） | **撞既有"每 key 串行"不变量**（`conductor.py:1095`） | 无新增；继续承受 cap 打满时的停滞（`CHANGELOG.md:78` 史实） |

### 2. 每个方案的"首个失败模式"（带判据；`[事实]` / `[推断]` 分开）

先说判据来源：**第一个坏的环节**必须在现有可观测面上留痕，否则不可判定。今天可留痕的位置只有三处：`worker.log` / `trace.log`（`[END] exit=N`、`[TOOL_ERR]`）、`timeline.jsonl`（`advance` 分类、`stalled`、`l3-no-verdict`、`config`）、PM 窗口的 monitor 面板（`slots used/max`、`advance Nx class`）。

**M1（默认 2→N）**
- 主判据（首选）：**机器级共享 LLM 配额/上游饱和**。依据是 `[事实]`：本机同一 CLI 类型的 proxy 是**共享单实例**——`proxy_multi.py` 每个 CLI 类型只起一个 `LocalProxyServer`，`providers.json` 里 `timi` 只有一条凭证链（env `TIMI_API_KEY` → `~/.pi/agent/auth.json`），端口被占用时 `mw serve` 直接"sharing existing proxy"（`mw.py:305-315`）。spec §1.3 场景 3 的三项目（FM/E2/MW）各自 cap=2 时机器层面已是"最多 6 个 key 并发"；任一项目提 cap 都直接乘到同一条凭证上。
  - 判据（可观测）：worker.log / trace.log 出现 provider 侧失败；`timeline` 的 `advance` 事件出现 `class=other|timeout-env`（分类器见 `conductor.py:882-900`），累计到 `advance_stall_ticks`（默认 5）后出现 `stalled` 事件。
  - `[事实]` 同类史实：`CHANGELOG.md:80` —— E2Feature 一个 reviewer 因 **bad model id → provider 403 within 6s** 死掉，还被 `_parse_l3_output` 误判成 `below`，白烧 2 轮 L3 并 `mark_stalled`。这说明"provider 侧批量失败"是本系统真实发生过的第一类坏法，但**仓库里没有 429/rate-limit 的成文事故** ⇒ "提高并发先把配额打爆"这一步是 `[推断]`，验证方法：对同一凭证在 cap=2/4 下各跑一个夜跑窗口，统计单位时间 provider 非 2xx 率与 `advance class=other` 率（本卡范围外，建议 RQ-2 或单独立 key）。
- 次判据（低概率，需要先有泄漏）：**文件锁预算耗尽**。`[事实]` 锁预算：`mw_common.acquire_lock`（`:1482`）默认 20 次/50ms 指数退避；conductor 侧另走 4 次/20ms + 过期偷锁（`conductor.py:121-150`）；TS `file-lock.ts:13-14,36` 10 次/50ms，耗尽即 `throw new Error("Could not acquire lock at … after 10 retries")`；config 锁两侧都是 6 次/20ms（`console.ts:285`、`CHANGELOG.md:66`）。`[事实]` 同类史实：`CHANGELOG.md:93`（并发 config 写 **28/30 丢更新**，两侧加锁修掉）；`CHANGELOG.md:66`（**残留锁永不自动偷**——TS 侧无 stale steal）。`[推断]`：并发升高使"崩溃时正持锁"的窗口变多 → 残留 `.mw/{workers,index}.lock` 让后续 TS 写永久 throw；验证方法：人为在 `index-store.upsert` 持锁窗口内 kill 进程，看后续 PM 是否持续报 `Could not acquire lock`。
- 明确判断：**M1 最容易先坏的不是锁，而是机器级共享配额**（锁持有是毫秒级、预算从 ~1s 到 ~51s 不等；配额是被整个机器共享的）。若只看单项目视窗，则因为 cap 从 2 提到 N 后"每次 tick 派发的 key 数"增加，**首个可见症状是 `_workers.parallel` 的 running 行数上升后的 provider 失败率**，而不是本地锁。

**M2（默认不变 + 机器层扩域）**
- 主判据：**静默空操作（silent no-op）**，这是本方案最尖锐的"首个失败模式"，且是 `[事实]` 推导而非推断：
  - 机器层对每个键的合并规则是"**空值即未决定**"：`EMPTY_VALUE = {"xkey_verify_cmd": [], "xkey_verify_cwd": ""}`（`effective_config.py:68`），`project_unset = project_value is _MISSING or project_value == EMPTY_VALUE[field]`（`:232`）。
  - 对 int **没有等价的"空"**：`0` 是非法值（floor 2），`null` 被 `validate_config` fail-closed 拒绝（`config.py:113-124`；`effective_config.py` 头部"Known deviation"明说 project `null` 走不到合并），`2` 恰好是默认值——于是"项目层显式 2"与"项目层没写"在语义上**无法区分**。
  - 而两条规范写路径都把 13 键**材料化**（`config.py:147-160`、`status-model.ts:289-300`），现场 FM/E2 的文件就是显式 `2`。
  - ⇒ 结果：**操作者在机器层写 `max_parallel_keys: 4`，所有已 materialize 的项目都不生效，且没有任何诊断**（因为该键"可覆盖"，不触发 `is not machine-overridable` 告警）。第一个失败模式 = 改了像没改。
  - 判据：`mw autopilot verify show` / `_doctor_autopilot`（`mw_common.py:2022-2065`）的 `origins` 会报 `max_parallel_keys=project`；`monitor` 的 `slotsMax` 仍为 2。验证方法：在临时项目上写机器层 4 + 项目层 2，跑一次 `load_effective` 断言 origin。**建议在 M2 立项前先做这一步（本笔记最推荐的下一步实测）。**
- 次判据：**观测面撒谎**。TS 没有机器层读取（§0），机器层一旦对 `max_parallel_keys` 生效，`status-model.ts::readConfig` 与 `monitor.ts:522`（`slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`）会显示项目层/默认值，与 conductor 实际值不一致 ⇒ 违反 AC-006 的精神（"来源可追溯"）。

**M3（自适应）**
- 主判据：**震荡/抖动（thrash）**。`[事实]`：conductor 每 tick 完全从文件重推（无跨 tick 调度内存，`conductor.py:183-300`），cap 判定用的是"当前 in-flight key 数"这个**瞬时值**（`:258-263, :289`）。`[推断]`：以瞬时队列深度/等待时长驱动的自适应会形成"放→派→打满→收→再派"的极限环，表现为 per-tick 派发/停派的高频翻转，机器层面变成配额脉冲式超限。判据：`timeline` 中相邻 tick 的 `dispatch` 数量方差骤增、`config` 事件里出现自适应调整记录（当前**不存在**，需要新建）。验证方法：先只做"只读的自适应决策日志"（不改并发），对比决策序列的翻转频率。
- 次判据：**GC-1 越界的实现诱惑**。若"调多少"落在进程内存（一个 controller 对象/线程/全局队列），即直接违反 GC-1（spec §0）。要满足 GC-1 必须每 tick 从文件（`_index.parallel` pending 行 + `_workers.parallel` 行）重推，而"槽位等待时长"这类量今天**没有落盘载体**：`timeline` 里 cap 阻塞**不留事件**（`conductor.py:289` 只有 `continue`，无 `append`），所以只能靠 tick 序列反推。⇒ M3 需要**额外改动**才能同时满足 GC-1 与 AC-006（这正是 M5/推迟 M3 的实证理由）。

**M4（两层上限：key 数 × 每 key worker 数）**
- 主判据：**撞既有"每 key 串行"不变量**，不是运行时偶发故障而是设计冲突：`conductor.py:1095` `if any(_is_in_flight(r) for r in fam): return False  # per-key serial: wait for the in-flight task`，`:1600-1602` 对 `l3-`/`repair-` 前缀同样"等 in-flight 评审/修复"。轮次记账（`state.used_rounds` 按 loop label）与 `mark_stalled` 的连击判定都建立在"同 key 同一时刻只有一个 worker"之上。⇒ 要让"每 key N 个 worker"真正并行，必须改派发语义与轮次记账（远超"改参数"），首个失败模式是"第二轮 worker 与第一轮抢同一任务目录/轮次计数，导致 `used_rounds` 双计或 `mark_stalled` 误判"（判据：同 key 出现两条同 `loop` 的 `advance` 记录、或 `stalled` 在无失败时触发）。
- `[事实]` 的反面价值：worker 层今天**确实**只有一个**全局**上限（`--max-workers`，`launcher.py:837`），没有 per-key 上限；且它不落盘（P-015），重启即丢。如果用户的真实痛点是"一个 key 内能不能多开 worker"，M4 是唯一对口形态，但代价最大。
- 次判据：多项目共享机器时，per-key 上限会让 `_workers.parallel` 的 running 行数上限变成 `Σ keys`，与 M1 叠加才是真正的机器级放大。

**M5（不改）**
- 无新增失败模式。代价是继续承受现状：cap 打满时排队的 key 只能等下一 tick（`conductor.py:289`），且**等待不可观测**（无事件）；`[事实]` 同类史实 `CHANGELOG.md:78` —— 2026-09-22 E2Feature 一个 key 的 advance 卡死导致 `execute->verify` **重试 2242 次 / 2h35m**，整个 stage 被一个 key 的依赖拖住（当日另有 3891 次 design→plan 失败 / 4h25m）。这是"少槽位 + 一个坏 key"组合的真实代价样本。

### 3. 约束校验（逐方案对照 GC-1/GC-3/GC-4）

| 方案 | GC-1 不引入中央调度器 | GC-3 文件锁并发控制 | GC-4 看门狗语义 |
|---|---|---|---|
| M1 | 满足（纯参数） | 满足但**放大**：共享文件 RMW 频率随并发线性上升（`_workers.parallel`：`mw_common.py:1512` update_status；`_index.parallel`：`index-store.ts::upsert/claim` 全量重写整文件） | **不满足即需补测**：活动看门狗按活动判定（`worker-mode.ts:148`），机器变忙不直接改其判据，但 spec GC-4 要求"不因机器更忙而误判"——这条只能在实测里证 |
| M2 | 满足 | 满足（不新增文件/锁） | 同 M1 |
| M3 | **潜在违反**：只要调节逻辑进内存即违反；必须做到"每 tick 从文件重推"才算满足 | **需额外改动**：等待时长要么新增持久化载体（+1 锁面），要么放弃该输入 | 需重测并发曲线下的误判率 |
| M4 | 满足 | 满足 | 同 M1 |
| M5 | 满足 | 满足 | 满足 |

**明说结论**：**没有任何方案"天然"违反 GC-1/GC-3/GC-4**；唯一有真实违反风险的是 **M3**（若把"自适应"实现为进程内控制器 → 违反 GC-1；若引入自适应状态文件 → 扩大 GC-3 面），因此 M3 若要做，必须先改 spec 明确"调节量必须每 tick 由文件重推、不得引入内存控制器"，并说明它比 M1/M2 多出的可观测载体重用什么机制。**M4 不违反 GC 任一条，但它违反本仓库既有的"每 key 串行"不变量**（`conductor.py:1095`），所以它不是"改参数"而是"改派发语义"，应在 spec 里按语义变更卡对待（P-018/P-019 家族）。

### 4. 可观测性：提高并行度后操作者需要看到什么

需要有 4 件事才能不盲飞：(a) 槽位用量的**来源**（谁占着槽）；(b) 是否**stalled/挂死占槽**；(c) 因 cap 被**跳过**的 key（等待，而不是"没被派发"）；(d) 多项目时机器级总用量。

**已有（`[事实]` + 锚点）**
- 面板槽位行：`monitor.ts:521-522`（`slotsUsed`/`slotsMax`）、`:596` 渲染 `slots ${used}/${max}`；`slotsMax` 取 `config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`（`:522`）。
- 谁占着槽：`workers: N running (all keys)` + 每行 `taskKey` 与已运行分钟数（`monitor.ts:638-643`）；每 key 的 attention 行给 `N running`、`deps blocked by …`、`advance Nx <class> <age>`、stalled 门禁提示（`:601-620`）。`inFlight` 的计数来源是 task_key 前缀匹配（`:502-506`）。
- 进程/勾稽：`serve`/`conductor` 存活行（`monitor.ts:560-583`）、tick 新鲜度（`:485-497`）；`mw doctor` 的 `autopilot` 分节（`mw_common.py:2022-2065`，**只讲 xkey verify**）；`mw doctor` 的 queue/launcher 行（`mw_common.py:_doctor_issues`）。
- timeline：17 类事件（`timeline.py:64-83`：beat/dispatch/worker-terminal/advance/gate-created/gate-answered/stalled/skip/stage-close/config/goal-halt/goal-snapshot/type-rejected/target-config-rejected/reconcile/resume/l3-no-verdict）；monitor 还派生"advance 连击"（`monitor.ts:394-439`）。

**缺口（M1/M2 若落地必须补）**
1. **槽位用量的口径不一致**：面板 `slotsUsed` 只数 `status == "running"` 的行（`monitor.ts:248` + `:509-512`），而 conductor 的 cap 数的是**非终态**行（含 `pending`）（`conductor.py:2131`）。⇒ 已派发未 spawn 的 `pending` 行**实际占槽但面板不显示**（显示 N/max 时可能少 1）。
2. **cap 阻塞零留痕**：`conductor.py:289` 是纯 `continue`，不 append 事件 ⇒ **"槽位等待"今天不可直接观测**，只能靠 tick 序列反推（AC-003 的"未派发 tick 次数"必须自建推导——建议在 design 里显式写成新增 `skip`/`parallel-wait` 事件，或明确接受反推）。
3. **`mw doctor` / `mw status` 没有槽位分节**：`slots*` 全仓只在 TS monitor 命中（dist 与 `monitor.ts`），Python 侧 `slots` 零命中 ⇒ 无 autopilot 面板的路由（纯 CLI / 无人值守夜跑）看不到槽位。
4. **没有"谁在挡"的判定**：当 `slots used == max` 时，面板不回答"哪个 in-flight key 是挂死/超龄的那个""下一个会被派发的 key 是谁"。已有 `elapsedMs`（`monitor.ts:249`）但没有阈值告警；孤儿静默窗是 90 分钟（`mw_common.py:1861,1917-1928`），与 `worker_timeout_min`（默认 30）和活动看门狗（10 分钟，`worker-mode.ts:148`）三个时间尺度并存但面板不解释它们的关系。
5. **无机器级总账**（spec U-5）：三个项目各一个 serve/面板，没有任何地方汇总"本机此刻 X/Y 个槽在用"；机器层配置（M2）落地前也没有机器级上限可显示。

### 5. 前置问题："stalled key 是否占槽"

**明确结论（可分两层，均有锚点）**
- `[事实]` **key-status=stalled 的 key 不占槽**。理由：(1) 派发循环在 cap 判定**之前**就跳过 stalled：`conductor.py:274` `if status_of.get(key) in ("done", "stalled", "closed-legacy"): continue`；(2) cap 只数"有非终态 worker 行的 key"`conductor.py:258-263`，判定函数 `_is_in_flight` 只看行状态 `:2131-2132`。
- `[事实]` **但"行状态卡住"的 key 占槽，而且它恰恰不会被标成 stalled**。`_advance_key` 在发现同 key 有 in-flight 行时直接 `return False`（`conductor.py:1095` 执行类、`:1600-1602` L3/repair 类），**不会**进入 `mark_stalled`（`mark_stalled` 调用点在 in-flight 检查之后，如 `:1099`）。而 launcher 的孤儿行收敛有 **90 分钟静默窗**（`launcher.py:588-607` + `mw_common.py:1861,1917-1928` `PI_WORKER_ORPHAN_DEAD_MIN`，默认 90）。⇒ 一个"进程已死但行还是 `running`"的 key 会**占着槽最多 90 分钟**，期间 conductor 既不再派发它、也不把它标 stalled，别的 key 只能等。
- 推论（`[推断]`，需实测）：这正是 spec §4 风险 1（"槽位被 stalled key 占住 ⇒ 提高上限只是让更多 key 一起卡住"）的**真实机制名称**——不是"stalled 占槽"，而是"**挂死行占槽，且不会变成 stalled**"。
  - 对 M1/M2 的收益含义：**提高 cap 仍有收益**（cap=2 时 1 个挂死行把可用槽降到 1；cap=4 时降到 3），并**不能靠"先等 stalled 释放"来解释现状**；但"先修孤儿收敛"（缩短静默窗 / 让 conductor 参与判定）是比提 cap 更直接的收益，建议在 design 里作为并列选项。
  - 验证方法（本卡未做，属可执行的下一步）：造一个"进程已死 + 行 running + task 目录无活动"的项目，cap=2 起 conductor，断言：(a) 后续 tick 不再派发该 key；(b) 第二个 ready key 仍能占第二个槽；(c) 第三个 ready key 在 90 分钟内不派发；(d) `timeline` 无 `stalled` 事件直到静默窗结束。现有测试 `test_autopilot_stall.py` / `test_launcher.py` 是合适的挂载点。

## 结论 → 决策映射

- **AC-004（≥3 方案 + 首个失败模式 + 可逆性 + GC）**：本笔记给出 5 个方案（M1–M5），逐项填满比较表、失败模式（§2）、可逆性（表内）、GC 校验（§3）。
- **AC-005（新默认值与生效层两侧一致）**：
  - 若选 M1：必须**同时**改 `config.py:52` 与 `status-model.ts:106`（+ `README.md:225`）；只改一侧不会 fail-closed，而是**静默覆盖**（§0 第 2 点）；**且 M1 对 FM/E2 这类已材料化项目不生效**（现场文件显式 2）——这是 M1 最大的"看起来做了其实没做"风险。
  - 若选 M2：需在 `effective_config.py:62-66/68` 扩域，并**同时**为 TS 补机器层读取，否则 `slotsMax` 与 conductor 实际值不一致（违反 AC-006 精神）；另需先解决 §2-M2 的"int 无空值 ⇒ 项目层显式 2 永远赢"的语义缺口，否则机器层是空操作。
  - 若选 M5：按 spec §3 AC-005 的要求，必须用 AC-002（成因）+ AC-003（吞吐/利用率）的证据链解释"为什么 2 是对的"，本笔记只能提供"2 把机器级并发锁在 ≤6 key（三项目 × 2）"这一条机器层论据 + FM 现场 cap 打满的事实。
- **U-1（目标形态 A/B/C/D）**：A=M1（最小、但默认只影响新/部分项目）、B=M2（机制最贴"机器参数"语义，但需先补 TS 机器层与 int 空值语义）、C=M3（代价最高且有 GC-1 风险，不建议在无"等待时长"可观测载体前立项）、D=M4（对口"每 key 多 worker"，但撞 `conductor.py:1095` 串行不变量，属语义变更卡）。
- **U-3（能否接受成本与失败率上升）**：M1/M2 的成本上升主要在**机器级共享配额**（共享 proxy + 单条 timi 凭证，`proxy_multi.py` / `providers.json`），以及共享文件 RMW 频率；**没有本仓库的 429 史实**，所以这一条必须在 design 前用一次受控实测（cap=2 vs cap=N）定价，不能拍脑袋。
- **U-5（各自计额 vs 机器层统一计额）**：机器层配置（M2）是唯一能表达"机器级统一计额"的现成载体；但今天机器层与 TS 面板脱节、且项目层显式值优先（§2-M2），所以"统一计额"在 M2 落地前只是名义上的。面板侧的机器级总账也是缺口（§4 缺口 5）。

## 数据缺口

1. **无 429/rate-limit 事故记录**：仓库 CHANGELOG/`_pitfalls.md` 里没有 rate limit 事故；只有 provider 403（`CHANGELOG.md:80`）与超时。⇒ "提高并发先把配额打爆"目前是 `[推断]`，需受控实测（RQ-2 或新 key）。
2. **锁持有时长无实测**：`acquire_lock` 的退避上界可达数十秒（`mw_common.py:1482` 20 次指数退避；TS 10 次/50ms ≈ 51s），但真实持有时长分布没有度量。⇒ "锁预算耗尽"的触发概率无法定量。
3. **"槽位等待"无直接证据**：`conductor.py:289` 不留事件，本卡无法量化因 cap 未派发的 tick 数（属 RQ-3）。
4. **机器级并发现状未审计**：本笔记只确认 FM/E2 有 autopilot 配置且 `max_parallel_keys=2`、FM `_workers.parallel` 尾部恰有 2 行 running；**没有**确认三项目是否真的在同一时间窗内并发运行（spec §1.3 场景 3 是假设还是事实，需单独取证）。
5. **M2 的 TS 机器层成本**：本笔记用 grep 确认 TS 今天**没有**机器层；若在 spec 定稿前 TS 侧补上机器层，M2 的成本会显著下降（此结论有时效性）。
6. **`_workers.parallel` 行状态口径漂移**：面板（running）与 conductor（非终态）口径不一致（§4 缺口 1）本身也是一个待修项，本笔记只记录未评估改动量。

## [VERIFY]

[VERIFY] RQ-4: options=5 first_failure=M1:shared-provider-quota(推断)|lock-exhaustion(次) M2:silent-noop-project-value-wins(事实) M3:oscillation|GC-1-risk M4:per-key-serial-invariant(conductor.py:1095) M5:none mirror_anchors=config.py:52/70,status-model.ts:106/136,corpus-53,README.md:225 gc_violations=M3-if-in-memory;none-outright stalled_holds_slot=no(stalled-status)/yes(hung-nonterminal-row,90min)
