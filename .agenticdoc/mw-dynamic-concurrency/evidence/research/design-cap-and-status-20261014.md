# T-C-D5 配置改动集 / parity 重冻 / 面板口径 / advance 阻塞量化（RQ-D5）

- key: mw-dynamic-concurrency
- task: mdc-rq-d5-cap-and-status（T-C-D5-cap-and-status）
- 日期: 2026-10-14
- 角色: 只读；唯一写面 = 本文件
- 上游: `spec.md`（AC-004/005/006/007/013）、`design.md`（D-101/D-102/D-107/D-109）、`evidence/research/spec-config-mirror-20261014.md`
- 判据格式: `file:line` + 原文片段（行号为本轮实测工作树 1-based）。未找到的写「未找到（命令 + 输出）」；推算值标 **[推算]**；其余为实测。

---

## 0. 结论先行

1. **配置改动集 = Python 6 处 + TS 9 处 + 2 个 dist bundle + 文档 3 处**（§1 逐条 `file:line`）。两侧 schema 是"未知键即整份作废"的 fail-closed（`config.py:152` / `status-model.ts:251-258`），新键 `max_workers_per_key` 必须**两侧同波**上线 + 重建两个 bundle，否则 21 键文件被旧侧判 `unknown field(s)`。
2. **`max_parallel_keys` floor 2→1 翻转两处**：语料 `autopilot-config-corpus.json:296-302`（`range-max-parallel-low`）与 `test_autopilot_config.py:50`；TS 侧还有第三处 `autopilot-console.test.ts:826`（`saveConfig(..., max_parallel_keys: 1)` 期望拒绝）。默认 2→8 另翻转 5 处 `toEqual` 硬编码（§2 表）。
3. **新键插入位置建议放在 `max_parallel_keys` 之后（index 4），不要放表尾**：Python `test_autopilot_config.py:119-127` 与 TS `autopilot-console.test.ts:912-919` 用 `[-1]..[-9]` / `at(-1)..at(-7)` **锁了尾部顺序**；插在尾部会让这 9 条断言全部平移失败。插在 index 4 时尾部 9 键不变，且与语义分组一致。design.md §3.1 写的"DEFAULT_CONFIG 尾 + `_INT_RANGES` 尾"应改为"`max_parallel_keys` 之后"。（§1.3）
4. **重冻三件套 + P6 覆盖**：语料改 5 条（2 改 3 增）→ 73→76 cases；按本轮给定改法实测新 `sha256=713db5c5f30d46b14eae53036e9c1368517bd0b3024e69b7cbb8540ca126eb4b, count=76`；同步 `test_autopilot_config_parity.py:60-61` 与 `autopilot-config-sync.test.ts:42-43`；**必须补 `partial-key-max_workers_per_key`**，否则 P6 `covered == expected_keys`（`test_autopilot_config_parity.py:434` / `autopilot-config-parity.test.ts:373`）直接红。（§3）
5. **面板口径今天确实分叉（实测）**：同一份合成队列，面板 `slotsUsed=1`（只数 running conductor 行，`monitor.ts:920-924`），而 conductor 口径在飞 key 数 = 2（`pending` 计入，`conductor.py:3539 _is_in_flight` + `mw_common.py:2026 row_belongs_to`）。统一做法：**面板把 `slotsUsed` 改成 conductor 同口径（非终态 ∧ origin=conductor ∧ path key）**，conductor 语义不动；三个量 `cap / eff=min(cap,|F|) / |F|` 由 conductor 在既有 `beat` 事件的 `data` 里单源导出，面板只读不重算（重算仅作交叉校验）。（§4）
6. **`advance()` 阻塞今天没有上界打点，且每次 tick 的同步 advance 调用数上界不是 cap 而是 `|前沿|`**：`_advance_key` 返回 False（只做 phase 推进、不派发）时不占用 `in_flight_keys` 名额，`conductor.py:744` 的 cap 闸挡不住它，故 cap=2 的 tick 仍可能串行调用 42 次 `advance.advance()`（每次超时 120s，`advance.py:36`）。量化方案 = 在 3 个调用点包一层计时，把 `advance_ms/tick_ms` 挂到下一 tick 的 `beat.data`；缓解首选"每 tick 限一次 advance"（改动 1 个计数器），备选"独立执行器"（改动面大、有双推进风险）。（§5）
7. **不引入新 timeline 事件类型**：`EVENT_TYPES` 有跨语言集合等值锁（`test_autopilot_timeline.py:34-94`，23 名；`autopilot-event-parity.test.ts:73`），加名要动 3 处 + 锁。打点复用既有 `beat`（`timeline.append` 已支持可选 `data`，`timeline.py:308-330`）即可零锁变更。
---

## 1. 配置改动集（完整 diff 清单，Python + TS 两侧）

D-101/D-102 的取值（本表按此写）：`max_parallel_keys` 默认 **8**、取值域 `(1, None)`（floor 1 = kill switch）；新键 `max_workers_per_key` 默认 **4**、取值域 `(1, None)`，仅项目层可配（不进 `EFFECTIVE_KEYS`）。

### 1.1 Python

| # | file:line | 原文（实测） | 改成 | 为什么 |
|---|---|---|---|---|
| P1 | `packages/multi-workers/autopilot/config.py:16` | `max_parallel_keys  int     2    (floor 2)` | `max_parallel_keys  int     8    (upper bound, floor 1 = kill switch)`；并在其后新增一行 `max_workers_per_key int    4    (per-key upper bound, floor 1)` | docstring 键表是人工可读契约（§4.4 L1 的字段说明来源）；不改会与 `DEFAULT_CONFIG` 漂移 |
| P2 | `config.py:87` | `"max_parallel_keys": 2,` | `"max_parallel_keys": 8,` 并在其后新增 `"max_workers_per_key": 4,` | 默认值 + 新键落点；位置见 §1.3 |
| P3 | `config.py:122` | `"max_parallel_keys": (2, None),` | `"max_parallel_keys": (1, None),` 并在其后新增 `"max_workers_per_key": (1, None),` | AC-006：上界=1 才能回串行；今天 `1` 被拒（实测见 §7 `[VERIFY]`） |
| P4 | `config.py:65` / `:110` / `:201` | `the frozen 20-key schema and the TS parity table (read via` / `# frozen 20-key project schema (D-110) and the TS <-> Python parity table stay` / `Consumers that need the complete 20-key view must use` | `20-key` → `21-key`（三处文案） | 键数变更后文案过期；`status-model.ts:165/170/175` 镜像同名文案 |
| P5 | `packages/multi-workers/autopilot/conductor.py:139` | `Returns the complete 13-key view. The project layer is loaded through` | `Returns the complete 21-key view.` | 早已是 20 键（`conductor.py:148 values = config.default_config()`），本来就是过期文案；本轮顺带修正 |
| P6 | `conductor.py:744` | `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):` | **不改** | 今天已是"在飞 ≥ 上界就停"的上界语义；D-101 只重定默认/floor + 上游算前沿（RQ-D4） |
| P7 | `packages/multi-workers/autopilot/effective_config.py:62-65` | `EFFECTIVE_KEYS = ( "xkey_verify_cmd", "xkey_verify_cwd", )` | **不改** | D-102 明示仅项目层可配；`load_effective` 从 `config.DEFAULT_CONFIG` 派生 `values/origins`（`effective_config.py:225-242`），新键自动进入完整视图，无需改 |
| P8 | `packages/multi-workers/mw.py:3508` | `merged = {**_ap_config.default_config(), **(raw or {}), **changes}` | **不改** | `default_config()` 拷贝自动带上新键；`verify set` 会把新键 materialize 进文件（`mw.py:3530 save_config`） |
| P9 | `packages/multi-workers/autopilot/config.py:114-119` | `_BOOL_FIELDS / _LIST_FIELDS / _STRING_FIELDS / _ENUM_FIELDS` | **不改** | 新键是 int，自动进 `_INT_RANGES` 校验分支（`config.py:161-172`） |

Python 端**无需改** `validate_config` 本体、`load_config`、`save_config`、`cached_load`：全部由 `DEFAULT_CONFIG` / `_INT_RANGES` 数据驱动（实测 registry dump，见 §7）。

**消费点（本轮只登记，不实现）**：`max_parallel_keys` 唯一消费仍是 `conductor.py:744`；`max_workers_per_key` 的消费点是 `conductor.py:1737 execute_loop`（`def execute_loop(` 实测在 :1737，闸门 `:1770-1772`、返回 `:1800`）——注意与卡面种子的 `:1736/:1771/:1799/:1801` 差 1 行，以本轮实测为准。

### 1.2 TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts` 为主）

| # | file:line | 原文（实测） | 改成 | 为什么 |
|---|---|---|---|---|
| T1 | `status-model.ts:76`（接口）`:80` | `export interface AutopilotConfig {` … `max_parallel_keys: number;` | 在其后加 `max_workers_per_key: number;`（并给 `max_parallel_keys` 补一行 JSDoc"upper bound"） | `readConfig`/`saveConfig` 的类型源 |
| T2 | `status-model.ts:132` 表，`:136` | `max_parallel_keys: 2,` | `max_parallel_keys: 8,` + 其后 `max_workers_per_key: 4,` | 默认值镜像（P5 逐字比对） |
| T3 | `status-model.ts:194` 表，`:196` | `max_parallel_keys: [2, null],` | `max_parallel_keys: [1, null],` + 其后 `max_workers_per_key: [1, null],` | 取值域镜像（P5 `JSON.stringify(INT_RANGES)` 等值） |
| T4 | `status-model.ts:325-341`（`const intOf = (` 的联合类型） | `| "max_parallel_keys"` | 在 `"max_parallel_keys"` 后加 `| "max_workers_per_key"` | 不加则 `intOf` 白名单拒绝该键（TS 编译错：不在联合类型） |
| T5 | `status-model.ts:346-367`（merged read） | `max_parallel_keys: intOf("max_parallel_keys"),` | 其后加 `max_workers_per_key: intOf("max_workers_per_key"),` | partial 文件读时回落默认（merge-on-read） |
| T6 | `status-model.ts:378-399`（`saveConfig` 有序对象） | `max_parallel_keys: config.max_parallel_keys,` | 其后加 `max_workers_per_key: config.max_workers_per_key,` | materialize 全键时写出；漏了则该键被静默丢弃 |
| T7a | `status-model.ts:1602-1607`（`StatusConfigView`） | `max_parallel_keys: number;` | 其后加 `max_workers_per_key: number;` | `--json` 视图的类型源 |
| T7b | `status-model.ts:1738-1743`（`AutopilotStatus.config` 子对象） | `max_parallel_keys: config.max_parallel_keys,` | 其后加 `max_workers_per_key: config.max_workers_per_key,` | `/autopilot status --json` 的 config 子对象（`:1611 AutopilotStatus`） |
| T8 | `status-model.ts:1793-1795`（`renderStatusText` 文本摘要） | `` ` \| round_budget=${...} \| max_parallel_keys=${...}` `` | 追加 `` ` \| max_workers_per_key=${status.config.max_workers_per_key}` `` | 人读面与 `--json` 同源（VC-017） |
| T9a | `monitor.ts:225-243`（`MonitorAutopilot`） | `slotsUsed: number;` `slotsMax: number;` | 新增**可选**字段 `slotsEffective?: number;`、`frontierSize?: number;`、`slotsCap?: number;`（不重载 `slotsMax`） | `monitor.ts:1423-1424` 的手工 fallback 对象保持可构造；`slotsMax` 语义保持 cap 以免既有断言 `slots X/Y` 全红 |
| T9b | `monitor.ts:920-924`（`busyKeys` 计算） | `for (const w of workers) { const owner = workerOwnerKey(w); if (owner !== "" && allKeys.includes(owner) && workerBelongsToKey(w, owner)) busyKeys.add(owner); }` | 在 `readMonitorState` 里改用**非终态**行集合（见 §4.2），把结果作为 `conductorInflightKeys` 传入 `deriveAutopilotPanel` | D-106：`slotsUsed` 与 conductor `_is_in_flight` 同口径；`deriveAutopilotPanel` 直接测试调用点为零（`rg deriveAutopilotPanel test/` 无命中），签名可扩 |
| T9c | `monitor.ts:1217`（渲染行） | `` `autopilot: ${tick}${stale} \| slots ${a.slotsUsed}/${a.slotsMax} \| ` `` | 保持 `slots U/M`（M=cap），新增尾段 ` \| eff ${slotsEffective} (frontier ${frontierSize}, cap ${slotsCap})`，并在可行处加 `adv ${advance_ms}/${tick_ms}ms` | AC-005 两个量同屏；`MONITOR_LINE_MAX = 110`（`monitor.ts:85`），需保证截断不切掉 `eff`（放在 `keys ...` 之前） |
| T10 | `console.ts:558-585`（`saveConfigLocked`） | `const cfg = readConfig(projectDir); … saveConfig(projectDir, mutate(cfg.config))` | **不改** | 通用 RMW，经 T5/T6 自动带上新键 |

TS 端**无需改** `validateConfigData`（`:246-291`，由 `INT_RANGES` 数据驱动）、`configReviver`（`:233`，按 `INT_RANGES` 成员判定整数字面量）、`freshDefaults`（`:157-159`，从 `DEFAULT_CONFIG` 派生）、`OPTIONAL_CONFIG_KEYS`（`:177`，新键在 `DEFAULT_CONFIG` 内，不会进可选表）。

### 1.3 新键插入位置（顺序是否被锁断言约束）——结论：插在 `max_parallel_keys` 之后，不要放表尾

实测顺序锁：

- Python `test_autopilot_config.py:117` `assert len(cfg.DEFAULT_CONFIG) == 20`；`:119-127` 锁最后 9 位（`[-1]=gate_reminder_max` … `[-9]=xkey_verify_timeout_s`）。
- TS `autopilot-console.test.ts:911` `toHaveLength(20)`；`:912-919` 锁 `at(-1)..at(-7)`（`gate_reminder_max` … `auto_gate_mode`）。
- TS `autopilot-console.test.ts:941-956` **全序**锁 `Object.keys(INT_RANGES)` 的 14 个 int 键顺序。
- 两侧 P5 锁（`autopilot-config-sync.test.ts:170-200`）：`Object.keys(DEFAULT_CONFIG).toEqual(py.keys)`、`JSON.stringify(DEFAULT_CONFIG) === JSON.stringify(py.defaults)`、`JSON.stringify(INT_RANGES) === JSON.stringify(py.int_ranges)` ⇒ **两侧插入位置必须逐位一致**。

**[推算]** 由上述键序：`max_workers_per_key` 插在 index 4（`max_parallel_keys` 之后）时，21 键列表的最后 9 位仍是 `xkey_verify_timeout_s, xkey_verify_cwd, auto_gate_mode, launcher_max_workers, dispatch_max_per_scan, queue_alarm_delta, l3_abort_retry_limit, gate_reminder_after_min, gate_reminder_max` ⇒ Python `[-1..-9]` / TS `at(-1..-7)` 断言**原样通过**，只需把 `20→21` 与 `INT_RANGES` 全序表加一项。
若按 design.md §3.1 追加到表尾，则上述 9 条尾部断言全部平移失败，还需新增 `[-10]`/`at(-8)` 断言。**故设计稿的"尾"落点应改为"`max_parallel_keys` 之后"。**

### 1.4 文档面（键数/口径文案）

| # | file:line | 原文 | 改成 |
|---|---|---|---|
| D1 | `packages/multi-workers/README.md:225` | `| `max_parallel_keys` | 2 | 同时推进的 key 上限 |` | 默认改 8，说明改"key 层并发**上界**（实起 = min(上界, 依赖前沿)）"；表格新增 `max_workers_per_key` 一行（默认 4，per-key 上界） |
| D2 | `packages/multi-workers/README.md:312` | `两个写者都会把 13 键材料化写进项目文件` | `21 键`（早已是 20，本轮顺带修正） |
| D3 | `packages/multi-workers/docs/autopilot-observability-guide.md:23` | `注册表条数 = 20 默认键 + 1 可选键` | `21 默认键 + 1 可选键`；同段提醒"两侧同版本上线"纪律不改 |
| D4 | `packages/multi-workers/README.md:220-232`（配置表头） | 表格 | 与 D1 同批更新 |

### 1.5 dist bundle（必须重建，否则源码改了行为不变）

| # | file | 证据 | 动作 |
|---|---|---|---|
| B1 | `packages/multi-workers/dist/extensions/agent-team-loop.js` | 实测含 `:24081 max_parallel_keys: 2,`、`:24113 max_parallel_keys: [2, null],`、`:24213/:24240`、`:25133`、`:25173`、`:25912` | `mw build`（或 `mw build --install`）重建 |
| B2 | `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js` + `.d.ts` + `monitor.js` | 实测 `status-model.js:68 max_parallel_keys: 2,`、`:119 [2, null]`、`:253/:285/:1412/:1463`；`monitor.js:706 slotsMax` | `npm run build` 或 `mw build --install` |
| B3 | `.agenticdoc/...` 之外无 | — | 运行期纪律见 `docs/autopilot-observability-guide.md:23` 与 README `:314` |
---

## 2. floor / 默认值变更的连带断言（翻转表）

### 2.1 floor 2→1 直接翻转（1 从非法变合法）

| # | file:line | 现状（实测） | 改成什么 | 理由 |
|---|---|---|---|---|
| F1 | `packages/multi-workers/test/fixtures/autopilot-config-corpus.json:293-302`（id `:293`、`payload_text` `:296`、`error_fields` `:300`） | `"payload_text": "{\"max_parallel_keys\": 1}"` → `reject / ["max_parallel_keys"]` | 方案 A（推荐）：payload 改成 `{"max_parallel_keys": 0}`，期望**保持** `reject / ["max_parallel_keys"]`（0 < 新 floor 1，负例仍在）。方案 B：期望改 `accept`，另加一条 0 → reject | 保留"低于 floor 被拒"的语料语义；1 在新语义 = kill switch，必须另有正例（F2） |
| F2 | 同上 `:303-313`（id `range-max-parallel-min`，payload `:309`） | `{"max_parallel_keys": 2}` → accept | payload 改成 `{"max_parallel_keys": 1}` → accept | 证明 floor=1 合法（AC-006 kill switch）；2 仍合法但不证明 floor |
| F3 | `packages/multi-workers/test_autopilot_config.py:50` | `({"max_parallel_keys": 1}, "max_parallel_keys"),`（`test_invalid_values_rejected` 参数） | 改为 `({"max_parallel_keys": 0}, "max_parallel_keys"),` | 1 变合法；0 仍非法 |
| F4 | `packages/coding-agent/test/suite/autopilot-console.test.ts:826` | `const tooLow = saveConfig(root, { ...DEFAULT_CONFIG, max_parallel_keys: 1 });` `expect(tooLow.ok).toBe(false);`（`:827`） | 值改 `max_parallel_keys: 0`（期望仍 `ok=false`）；或改测新键 `max_workers_per_key: 0` | 1 变合法；负例需下移一格 |
| F5 | 同上 `:51` | `({"max_parallel_keys": "2"}, "max_parallel_keys"),` | **不改** | 类型错例，与 floor 无关 |

### 2.2 默认 2→8 翻转（硬编码 `2` 的 `toEqual`）

| # | file:line | 现状（实测） | 改成什么 |
|---|---|---|---|
| G1 | `autopilot-console.test.ts:394` | `expect(s.config).toEqual({ enabled: true, poll_interval_sec: 4, round_budget: 2, max_parallel_keys: 2 });` | `max_parallel_keys: 8` + 新增 `max_workers_per_key: 4` |
| G2 | `autopilot-console.test.ts:451` | 手工 `StatusModel.status.config` 字面量 `{ enabled: true, poll_interval_sec: 4, round_budget: 2, max_parallel_keys: 2 }` | 同上（否则 `StatusConfigView` 加必填字段后 TS 编译错） |
| G3 | `autopilot-console.test.ts:485` | `expect(s.config).toEqual({ enabled: false, poll_interval_sec: 4, round_budget: 2, max_parallel_keys: 2 });` | `max_parallel_keys: 8` + 新键 `4` |
| G4 | `autopilot-console.test.ts:1245-1276` | `/autopilot enable` 后 `expect(enabled).toEqual({...20 键..., max_parallel_keys: 2, ...})`（`:1256`）+ `:1276 toHaveLength(20)` | `max_parallel_keys: 8`、加 `max_workers_per_key: 4`、`toHaveLength(21)` |
| G5 | `autopilot-console.test.ts:424-425`（VC-017 文本断言） | `toContain("max_parallel_keys=${...}")` 等 | **不红**；建议补 `toContain("max_workers_per_key=${...}")` 以覆盖 T8 |
| G6 | `autopilot-monitor.test.ts:1084` / `:1214` | `writeConfigJson(root, { ..., max_parallel_keys: 2, ... })` 显式写值 | **不改**（显式值不受默认变更影响；`:1194/:1236/:1243` 的 `slots X/2` 断言随之保持） |
| G7 | `packages/multi-workers/test_autopilot_conductor.py:403`（`cfg["max_parallel_keys"] = cap`，默认 `cap=2`）与 `:730 test_max_parallel_keys_cap` | 显式 `cap=2` | **不改**（显式值；cap 语义本来就是"上界就停"）。注意：若 RQ-D4 让 `execute_loop` 一次派多卡，`:738 len(_rows_of(...,"ap-")) == 2` 需重估，但那是 per-key 并发的翻转，不属本轮 floor/default |

### 2.3 计数锁 20→21（新键引入，非 floor 翻转）

| 侧 | file:line | 内容 |
|---|---|---|
| Py | `test_autopilot_config.py:117` / `:153` / `:154` / `:188` | `len(DEFAULT_CONFIG)==20` / `len(default_config())==20` / `len(load_effective().values)==20` / `len(eff.values)==20` → 21 |
| Py | `test_autopilot_effective_config.py:74` / `:209` | `len(eff.values)==20` → 21；（`:184 partial_project_keys=20` 只是 `_verify` 打印，建议同步为 21） |
| Py | `test_mw_autopilot_cli.py:124` | `len(stored)==20` → 21（`:121 set(stored)==set(DEFAULT_CONFIG)` 自动通过） |
| Py | `test_mwgal_t12_stage_close_auto.py:658-666`、`test_mwgal_t15_reattest_confirm.py:720-729` | 硬编码键**集合** `expected_config_keys` 加 `max_workers_per_key`（`:679`/`:741` 的 `_verify` 计数同步） |
| Py | `test_mwds_t14_producer_skew.py:600` | `len(config.DEFAULT_CONFIG)==20` → 21（`:599` 的 `envelope_fallback not in DEFAULT_CONFIG` 不变） |
| TS | `autopilot-console.test.ts:911` / `:1276` | `toHaveLength(20)` → 21 |
| TS | `autopilot-console.test.ts:941-956` | `Object.keys(INT_RANGES)` 全序表加 `max_workers_per_key`（index 4） |
| TS | `mwgal-t20-config-parity.test.ts:142` / `:196` / `:218` | `toHaveLength(20)` → 21 |
| TS | `autopilot-config-parity.test.ts:356` / `:361` | `toBe(20)` → 21 |
| TS | `autopilot-config-sync.test.ts:12-16`（注释 `20-key defaults` / `21 registrations over the 20-key schema`） | 注释改 `21`/`22`（无断言语义变更；`P5` 的 `registered.length === py.keys.length + optionalRegistered.length` 自动成立） |
---

## 3. parity 语料重冻流程（deliberate re-freeze）

### 3.1 现状锚点（实测）

- 语料：`packages/multi-workers/test/fixtures/autopilot-config-corpus.json`，schema `mw-autopilot-config-corpus/v1`，`cases=73`，`sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a`（与两处冻结常量一致）。
- Python 半边：`test_autopilot_config_parity.py:60-61`（`FROZEN_CORPUS_SHA256` / `FROZEN_CORPUS_COUNT = 73`），P4 断言 `:311-315`。
- TS 半边：`test/suite/autopilot-config-sync.test.ts:42-43`（同两常量），P4 断言在 `:100-160`。
- 主判：`test/suite/autopilot-config-parity.test.ts`（spawn 真 Python 反向差分）+ `test_autopilot_config_parity.py`（镜像半边）。
- 文件是 `json.dumps(obj, ensure_ascii=False, indent=2) + "\n"` 的字节固化（实测 round-trip 逐字节相等 true），所以重算 sha 必须用同一序列化形态。

### 3.2 步骤（可执行）

1. **改语料** `test/fixtures/autopilot-config-corpus.json`（只动 `cases`，不动 `schema`）：
   - 改 `range-max-parallel-low`：`payload_text` → `"{\"max_parallel_keys\": 0}"`（期望 `reject / ["max_parallel_keys"]` 不变）。
   - 改 `range-max-parallel-min`：`payload_text` → `"{\"max_parallel_keys\": 1}"`（期望 `accept / []` 不变）。
   - **新增 3 条（追加到 `cases` 末尾即可，顺序无锁）**：
     - `partial-key-max_workers_per_key`：`categories ["D2"]`，`payload_text "{\"max_workers_per_key\": 4}"`，`expected {"verdict":"accept","error_fields":[]}` —— **P6 覆盖必需**。
     - `range-max-workers-per-key-low`：`categories ["D5"]`，`payload_text "{\"max_workers_per_key\": 0}"`，`expected {"verdict":"reject","error_fields":["max_workers_per_key"]}`。
     - `range-max-workers-per-key-min`：`categories ["D5"]`，`payload_text "{\"max_workers_per_key\": 1}"`，`expected {"verdict":"accept","error_fields":[]}`。
2. **重算 sha256 + 计数**（在 `packages/multi-workers` 下；生成物写系统临时目录，勿写回 fixture）：
   ```python
   import json, hashlib, os, tempfile
   src = "test/fixtures/autopilot-config-corpus.json"
   d = json.load(open(src, encoding="utf-8"))
   # ... 按步骤 1 改 d["cases"] ...
   out = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
   open(os.path.join(tempfile.gettempdir(), "cand-corpus.json"), "w", encoding="utf-8", newline="\n").write(out)
   print(hashlib.sha256(out.encode("utf-8")).hexdigest(), len(d["cases"]))
   ```
   把真值直接写回 fixture（`write_text(out, encoding="utf-8", newline="\n")`），**再**用同一 `out` 的 sha/len 更新常量。本轮按步骤 1 的确切改法实测：`sha256=713db5c5f30d46b14eae53036e9c1368517bd0b3024e69b7cbb8540ca126eb4b`，`cases=76`。**这只是"若按本改法"的实测值；实际落地后必须用上一步命令重新打印，禁止照抄。**
3. **改两侧冻结常量**（必须同值）：
   - `test_autopilot_config_parity.py:60-61`；
   - `test/suite/autopilot-config-sync.test.ts:42-43`。
4. **改硬编码 21**：`test_autopilot_config_parity.py:423` / `:426`；`autopilot-config-parity.test.ts:356` / `:361`（细节见 §2.3）。
5. **跑两侧 parity（就这两个测试文件）**：
   - Python 镜像：`cd packages/multi-workers && python -m pytest -q test_autopilot_config_parity.py`
   - TS 主判 + 语料锁：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts`
   （P5 的 `mwgal-t20-config-parity.test.ts:142/196/218` 也在 `20→21` 清单内，建议同批跑。）

### 3.3 P6 "covered == expected_keys" 的新键覆盖要求

- 机制：`test_autopilot_config_parity.py:384-434`（`_single_key_cases` → 每个"单键且 accept"的 payload 收集其键名，最后 `assert covered == set(KNOWN_FIELDS)`，`KNOWN_FIELDS = list(config.DEFAULT_CONFIG)`）；TS 对应 `autopilot-config-parity.test.ts:343-378`。
- 因此**新键必须至少有一条"只含该键且 accept"的语料**：`partial-key-max_workers_per_key`（值为 4，落在 `(1, None)` 内）。`range-max-workers-per-key-min` 也是单键 accept，会重复覆盖同名键，不冲突。
- 注意 `expected_keys` 由 `DEFAULT_CONFIG` 动态派生（两侧都是），所以 P6 的"集合"部分自动含新键；但 `len(effective_keys) == 20` 是**硬编码**，必须同步为 21（§2.3），否则 P6 先红在计数断言上。
---

## 4. 面板口径统一：配置上界 / effective 并发 / 前沿大小

### 4.1 三个量的确切来源与计算

| 量 | 定义 | 今天来源 | 计算 |
|---|---|---|---|
| **配置上界** `cap` | key 层并发上界 | 面板：`monitor.ts:933 slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`（今天就这么取）；config：`conductor.py:744 max(1, int(cfg["max_parallel_keys"]))` | `cap = cfg.max_parallel_keys`（per-key 层另有 `cfg.max_workers_per_key`，面板可选展示） |
| **前沿大小** `|F|` | 依赖已满足、非终态、无主、未被终态过滤的 running-stage key 数 | **今天无任何面**（conductor 隐式算） | `F = {k : stage(k).status == "running" ∧ status_of[k] ∉ _DISPATCH_SKIP_STATUSES ∧ deps_satisfied(k) ∧ claim_free(k)}`；`deps_satisfied(k) ⇔ ∀d∈depends_on(k): status_of[d] ∈ _DEP_SATISFIED` |
| **effective 并发** `eff` | 本 tick 允许并发推进的 key 上限 | **今天无** | `eff = min(cap, |F|)` |

谓词逐条 `file:line`（conductor 侧）：
- running stage 过滤：`conductor.py:718-720`（`for stage in rm.stages:` / `if stage.status != "running":` / `continue`）。
- 终态过滤：`conductor.py:71` `_DISPATCH_SKIP_STATUSES = ("done", "stalled", "closed-legacy", "pending-review")`；消费 `conductor.py:721 if status_of.get(key) in _DISPATCH_SKIP_STATUSES: continue`。
- 依赖满足：`conductor.py:64 _DEP_SATISFIED = frozenset({"done", "closed-legacy"})`；`conductor.py:740 if not _deps_satisfied(entry.depends_on, status_of): continue`；`_deps_satisfied` 定义 `conductor.py:3559-3561`。
- claim free：`conductor.py:723-737`（`CLAIM_LIVE` 跳过；`_foreign_synthetic_claim` 跳过）。
- 在飞/上界：`conductor.py:742` `if key in in_flight_keys: continue`、`:744` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])): continue`。

### 4.2 今天 `slotsUsed`（只数 running）与 conductor（含 pending）的差异

**conductor 口径**（唯一在飞事实源）：
- `conductor.py:698-704`：`in_flight_keys = {key for key in deps_of if any(_is_in_flight(row) and _row_belongs_to(row, key) for row in rows)}`。
- `conductor.py:3539-3540`：`def _is_in_flight(row): return row.get("status","") not in mw_common._TERMINAL_STATUSES`；终态集 `mw_common.py:2342 _TERMINAL_STATUSES = {"done","failed","needs-clarification","lost"}` ⇒ **`pending` 算在飞**。
- `conductor.py:3543-3546` → `mw_common.py:2026-2036 row_belongs_to`：`origin` 先决（`worker_is_conductor`），再 `worker_owner_key`（path 锚）⇒ **manual/legacy 行不占槽**。

**面板口径**：
- `monitor.ts:508` 收集 `workers` 时 `if (entry.status !== "running") continue;`（只 running）。
- `monitor.ts:920-924` `busyKeys`：对 `workers`（running-only）逐行 `workerOwnerKey` + `workerBelongsToKey`（`shared/worker-store.ts:65-67` 同样 origin 先决）⇒ `slotsUsed = busyKeys.size`。
- `monitor.ts:477-501` 还另算了一份 `nonTerminalByKey`（非终态、path 口径、**含 manual**）——只喂 `blockedOnHuman`，没喂 `slotsUsed`。

⇒ 差在"pending 行算不算"：conductor 算，面板不算。

**实测复算（[VERIFY] panel_slots，合成队列）**：4 行 = `kA/running/conductor`、`kB/pending/conductor`、`kC/running/manual`、`kD/done/conductor`。把"running-only"列表喂给 `deriveAutopilotPanel`（模拟 `monitor.ts:508` 的收集）后：`slotsUsed=1`；同数据的 conductor 口径 `{kA,kB}` = **2**。Python 镜像同样得 `{kA,kB}`（`pending` 计入、manual 不计），两侧谓词一致，只有面板的输入集合被截断。

**统一做法（不改 conductor 语义）**：
1. `readMonitorState` 里用**全量非终态行**构造 `conductorInflightKeys = { owner(w) : w.status ∉ TERMINAL_WORKER_STATUSES ∧ workerBelongsToKey(w, owner) ∧ owner ≠ "" }`（复用 `monitor.ts:477` 的同一循环，只换谓词；`TERMINAL_WORKER_STATUSES` 定义 `status-model.ts:1564`，与 `mw_common._TERMINAL_STATUSES` 同集）。
2. 把它作为新参/新字段传进 `deriveAutopilotPanel`，`slotsUsed = |conductorInflightKeys ∩ allKeys|`（保留今天"只算出现在 roadmap/index 的 key"这一交集，避免把孤儿 key 计入）。
3. `conductor.py` / `mw_common.py` 一行不改：`_is_in_flight`、`_row_belongs_to` 已是各自语言的单源；本轮只是让 TS 面板复用它。
4. `manual` 行继续不占槽（D-019/T-12 不变），`pending` 从此占槽（与 conductor 一致）。

### 4.3 AC-005 可复算等式

同一快照 `S`（同一 tick、同一文件读面）内记：

```
cap    = cfg.max_parallel_keys                       # 配置上界（面板 slotsMax，monitor.ts:933）
F      = {k : stage running ∧ status ∉ SKIP ∧ deps_satisfied ∧ claim_free}   # 前沿集合（§4.1 谓词）
eff    = min(cap, |F|)                               # 本 tick effective 并发
I      = conductorInflightKeys ∩ roadmap keys        # 在飞 key（非终态 ∧ origin=conductor ∧ path key）
used   = |I|                                         # 面板 slotsUsed（统一后）
started= 本 tick 实际派发的 key 数                    # 新增观测量
```

可复算等式（AC-005）：

1. **口径等式**：`used(S) = |{k : ∃ row ∈ queue(S): row.status ∉ {done,failed,needs-clarification,lost} ∧ origin=conductor ∧ owner(row)=k}|`——面板与 conductor `_is_in_flight ∧ _row_belongs_to` 逐字同式（§4.2）。
2. **上界等式**：`eff(S) = min(cap(S), |F(S)|)`，且 `used(S) ≤ eff(S)` 恒成立。
   证明（tick 内）：派发前 `in_flight_keys` 只增不减；每个 `_advance_key` 派发的 key 必过 `:721/:740` 且不在 `in_flight_keys`，且 `:744` 保证派发后 `len(in_flight_keys) ≤ cap` ⇒ `|I_post| ≤ min(cap, |F_pre|)`。
3. **前沿恒等（VC-101 形态）**：当 `F_pre` 内每个 key 的 `_advance_key` 都返回 True、且 `|F_pre \ I_pre| ≥ cap - |I_pre|` 时取等号：`used_post = min(cap, |F_pre|)`。窄前沿（|F|=1）时 `eff=1`，与 cap 无关（AC-006 回退：cap=1 ⇒ `eff ≤ 1`）。
4. **差值账**：`used_post = used_pre + started`，`started ≤ |F_pre \ I_pre|`，`used_pre + started ≤ eff_pre`。
5. **单源导出（推荐落地）**：`cap/|F|/used/started` 由 conductor 写进**下一 tick 的 `beat` 事件 `data`**（不新增事件类型，见 §5.2），面板直接显示这些数；面板自算的 `F_panel` 只作交叉校验（`F_panel ⊇ F_conductor`，因为 TS 不读 claim 状态——见 §6 残留）。这样 AC-005 的"同一快照可复算"不再依赖两套读面同时对齐。

**必须承认的边界**：面板不读 `state.read_key_states`（claim 文件），所以 `F_panel` 可能比 `F_conductor` 大（被 foreign claim 持有的 key 面板仍算前沿）。因此等式 (2) 用 conductor 的 `F`；若面板显示的是 `F_panel`，只能断言 `eff_panel ≥ eff_conductor`。消除这一残差的唯一无锁方案就是 §4.3(5) 的单源导出。

### 4.4 呈现落点与连带测试

- `monitor.ts:225-243`：新增可选 `slotsEffective`、`frontierSize`、`slotsCap`；`monitor.ts:1423-1424` 的 fallback 对象不必改（可选字段）。
- `monitor.ts:1217`：保留 `slots ${used}/${slotsMax}`（M=cap，既有断言不红），在 `keys ...` 之前插入 `| eff ${eff} (frontier ${fr}, cap ${cap})`；`MONITOR_LINE_MAX=110`（`:85`），截断点须保证 `eff` 先于 `keys` 段被渲染。
- 会受影响的 TS 测试：`autopilot-monitor.test.ts:1194/:1236/:1243`（`toContain("slots X/2")` 保持通过，因为 `slotsMax` 仍是 cap）；新增 eff/frontier 断言建议放同文件新用例。
---

## 5. `advance()` 阻塞量化方案

### 5.1 现状（为什么必须量化）

| 事实 | 判据 | 原文 |
|---|---|---|
| 唯一相位通道、同步阻塞 | `advance.py:164-191` | `def advance(` … `proc = subprocess.run(` … `timeout=_ADVANCE_TIMEOUT_SEC` |
| 单次超时 120s | `advance.py:36` | `_ADVANCE_TIMEOUT_SEC = 120` |
| 调用点 3 个 | `rg -n "advance\.advance\("` = `conductor.py:1621, 1801, 2749` | `code, _out, err = advance.advance(key, nxt, project_root, summary=summary)` / `advance.advance(key, "verify", ...)` / `advance.advance(key, "done", ...)` |
| 每 tick 调用数上界 = **前沿大小，不是 cap** | `conductor.py:718-746` | `_advance_key` 返回 False（phase 推进、不派发）时 `:746 if _advance_key(...): in_flight_keys.add(key)` 不加名额 ⇒ `:744` 的 cap 闸挡不住下游 key；故同 tick 可为 `|F|` 个 key 各串行跑一次 advance |
| 无时长打点 | `conductor.py:1536-1557`（`_record_advance_result`） | 只写 `st.timeline.append("advance", key=key, detail=f"{edge} exit={code} class={cls}")`，无 ms |
| tick 无时长打点 | `conductor.py:3432-3434` | `# 1. Beat first — liveness even when disabled (AC-019).` / `st.timeline.append("beat")`（无 `data`） |
| 主循环 act-then-sleep | `conductor.py:8370-8380` | `tick(project_root, st)` 后 `interval = ...["poll_interval_sec"]` → `time.sleep(...)` |

最坏情况量级 **[推算]**：`|F|` 个 key 各一次 advance × 120s 超时。E2Feature 实测 key 数 42（RQ-C3 证据），若前沿=42 则单 tick 最坏 84 分钟 > poll_interval(4s)。**这就是 AC-013 必须量化的原因；不得假设 N 倍延迟可接受。**

### 5.2 打点方案（可落地）

**原则：不新增 timeline 事件类型**（`EVENT_TYPES` 是跨语言集合等值锁：`test_autopilot_timeline.py:34-94` 共 23 名，`autopilot-event-parity.test.ts:73` TS 侧等值断言；加名要动两侧 + 锁）。复用既有 `beat`（`timeline.py:308-330 append()` 的 `data` 参数自 T-07 起支持任意映射，且 legacy 六字段行不受影响）。

1. **计时包装**：在 conductor 加一个 `_advance_timed(st, key, phase, project_root, summary)`：
   ```python
   t0 = time.perf_counter()
   code, out, err = advance.advance(key, phase, project_root, summary=summary)
   dt_ms = int((time.perf_counter() - t0) * 1000)
   st.advance_ms += dt_ms; st.advance_calls += 1
   return code, out, err, dt_ms
   ```
   3 个调用点（`:1621`、`:1801`、`:2749`）改调它，并把 `dt_ms` 传给 `_record_advance_result`。
2. **单次落盘**：`_record_advance_result(...)` 追加 `data={"ms": dt_ms, "phase": phase, "edge": edge}`（`detail` 保持 `"{edge} exit={n}[ class=...]"` 形态不变，`monitor.ts:728 ADVANCE_DETAIL_RE` 与停滞连击派生零影响；`data` 是可选载荷，`:432` 的查询/渲染不读它）。
3. **tick 汇总落盘**：`tick()` 用 try/finally 量出本次 `tick_ms`（`perf_counter` 差；**不含** sleep），并把本 tick 的 `advance_ms / advance_calls / frontier / cap / in_flight / started / stage_keys` 存进 `st`；在**下一次** `tick()` 的第 1 步：
   ```python
   st.timeline.append("beat", data={
       "tick_ms": st.prev_tick_ms, "advance_ms": st.prev_advance_ms,
       "advance_calls": st.prev_advance_calls, "frontier": st.prev_frontier,
       "cap": st.prev_cap, "in_flight": st.prev_in_flight, "started": st.prev_started,
   })
   ```
   这样**每 tick 仍恰好一条 beat**（AC-019 心跳只增不减，`_advance_failure_streak` 跳过 beat，`monitor.ts:892-897` 的 `tickSeq` 取 last beat 仍是本 tick），无需改 `EVENT_TYPES`、无需改 parity 锁。语义上这是"最近完成 tick"的统计量（滞后一 tick，读法见下）。

### 5.3 怎么读出"tick 被 advance 阻塞的墙钟占比"

定义（对 `beat` 序列，过滤 `data` 存在的行）：

```
per_tick_ratio_i  = advance_ms_i / max(1, tick_ms_i)          # 单 tick 阻塞占比
window_share      = Σ advance_ms_i / Σ tick_ms_i              # 墙钟加权占比（推荐主指标）
blocked_ticks     = #{i : per_tick_ratio_i ≥ 0.5}             # "被 advance 主导的 tick" 计数（阈值可配）
amplification_i   = advance_calls_i / max(1, frontier_i)      # 是否贴近 |F| 上界
```

只读派生脚本（不改任何文件；`timeline.jsonl` 路径 `timeline.py:123-129`）：

```python
import json, pathlib
p = pathlib.Path("H:/git/<project>/.agenticdoc/_autopilot/timeline.jsonl")
beats = []
for line in p.read_text(encoding="utf-8").splitlines():
    try: e = json.loads(line)
    except ValueError: continue
    if e.get("ev") == "beat" and isinstance(e.get("data"), dict) and "tick_ms" in e["data"]:
        beats.append(e["data"])
adv = sum(b["advance_ms"] for b in beats); tk = sum(max(1, b["tick_ms"]) for b in beats)
print("ticks", len(beats), "window_share", round(adv / max(1, tk), 4),
      "blocked_ticks", sum(1 for b in beats if b["advance_ms"] / max(1, b["tick_ms"]) >= 0.5),
      "max_advance_calls", max((b["advance_calls"] for b in beats), default=0),
      "max_frontier", max((b["frontier"] for b in beats), default=0))
```

VC-109 判定素材 = `window_share` + `max_advance_calls vs max_frontier` + `blocked_ticks`；N≥4 并发样本（构造宽前沿 roadmap）前后各跑一次即可对照。注意 tick 间的 sleep 不计入 `tick_ms`，否则占比会被 poll_interval 稀释。

### 5.4 两条备选缓解

**缓解 A（推荐，先做）：每 tick 限一次 advance（per-tick advance budget）**

- 改动面：`ConductorState` 加 `advance_budget_used`（tick 开头重置）；`_advance_timed` 入口 `if st.advance_budget_used >= 1: return "deferred"`（不调用子进程、不写 `advance` 事件、`_advance_failure_streak` 不计数）；3 个调用点的返回值处理改为"deferred 时本 tick 跳过该 key，下 tick 重试"。约 10-15 行，全部在 `conductor.py`；**无**新事件类型、**无**跨语言锁、**无**新配置键（或加可选上限 `PI_/config` 键）。
- 效果：单 tick advance 墙钟 ≤ 120s（而不是 `|F|×120s`）；相位推进延迟上界 **[推算]** `≤ poll_interval × |F|`（4s × |F|）。
- 风险：(a) 宽前沿时相位推进变慢（吞吐换稳定），需用 §5.3 指标确认可接受；(b) **饿死**——若每次都是同一顺序的 key 抢到名额，后面的 key 永远拿不到 advance ⇒ 必须配 round-robin 游标（按 tick 序号轮转起点）或"deferred 集合优先"，并把"该 key 连续 deferred 次数"写成 audit 行（否则是静默卡死，违反 spec §2.3 fail-closed 精神）；(c) deferred 不是失败，绝不能进 `advance_stall_ticks` 连击（否则误报 stalled gate）——这是本方案唯一必须写测试的点。
- 变体 A′（更保守的吞吐）：budget = `cap` 而不是 1（把 advance 调用数与并发上界对齐），改动同 A，延迟上界缩小 `cap` 倍。

**缓解 B（备选，仅当量化证明 A 不够）：把 advance 移出 tick 临界路径（独立执行器）**

- 改动面：`advance.py` 加非阻塞入口（`concurrent.futures.ThreadPoolExecutor` 或 `subprocess.Popen` + pid/结果文件）；conductor 需要"该 key 有一次 advance 在飞"的第三态（建议 `.mw/advance/<key>.json` 或 timeline `advance-start`/`advance-done` 两条新事件——后者要动 `EVENT_TYPES` 等值锁 3 处 + `test_autopilot_timeline.py:34` 的 23 名锁 + TS 镜像）；3 个调用点改成提交 + 下 tick 轮询结果；`_advance_key`/`execute_loop`/`_verify_loop` 在"在飞"期间不得再派发该 key；同 key 两次 advance 必须互斥（`advance_phase.py` 会写 key 状态 → 串接 `key-{key}` 锁或专用锁）。
- 风险：(a) conductor 崩溃/重启丢在飞结果 → advance 可能被重放或永久卡住，需要幂等键或恢复扫描；(b) 派发与相位不同步（相位未前进就派下一个 worker）；(c) 与 RQ-D3 的 check-then-act 洞叠加，双推进概率放大；(d) "advance 是唯一相位通道、fail-closed"（`advance.py:1-28` 的模块契约、AC-005/D-107）需要重新论证；(e) 改动面横跨 Python + timeline 锁 + TS 读面，明显大于 A。⇒ D-107 的默认取向应是"先按 A 收敛 + 量化"，B 留作实测不达标时的 escape hatch。
---

## 6. 残留与未验证 / 未覆盖面声明

### 6.1 未验证（本轮只读，未跑任何测试）

- **未跑任何测试套件**（角色约束：只读、禁跑测试写快照）。§2 的全部"翻转/计数锁"清单来自静态 `rg` + 逐文件精读，红绿状态未实测。
- **面板 `F_panel ⊇ F_conductor`**：TS 侧不读 claim 状态（`state.read_key_states`），被 foreign claim 持有的 key 面板仍算前沿；运行期未采样，§4.3 等式 (2) 的 `eff` 必须以 conductor 的 `F` 为准（或走 §4.3(5) 的 beat 单源导出）。
- **未跑 conductor tick 实采**：`|F|` 的最坏值、advance 每 tick 调用数、`window_share` 均无运行期样本，全部为源码推导 + [推算]。
- **未验证 dist 与 src 完全同源**：只核对了 `max_parallel_keys` 相关行存在（B1/B2 表）；重建后的 bundle 未比对。
- **未验证旧 bundle/旧 Python 读 21 键文件的实际失败样本**（需真实旧构建 + `unknown field(s)` 输出）。
- **新键名称/默认/取值域以 design.md D-101/D-102 为准**（`max_workers_per_key`=4、`(1,None)`；`max_parallel_keys`=8、`(1,None)`）。若 PM 改值，本报告 §1 的取值、§3.2 的语料期望、§7 的 verdict 需同步。
- **advance 打点在 `tick()` 的 early return 路径上的正确性未验证**：`tick()` 有 `return "idle"/"ok"/"lock-held"/"error"` 等多条返回（`conductor.py:3427-3475` 起），需 `try/finally` 或 `_tick_inner` 包装把 `tick_ms` 落到所有路径；未实现、未测。
- **`data` 载荷对 legacy 锁的影响未实测**：`timeline.py:322-330` 只在传入映射时写 `data`；已有先例（`gate-auto-decision` 用 data），预计 `test_autopilot_timeline.py` 的六字段基线不受影响，但未跑。
- **`readMonitorState` 改口径的副作用未测**：`monitor.ts:497-500` 的 `nonTerminalByKey`（path 口径、含 manual）现在喂 `blockedOnHuman`；统一 `slotsUsed` 时必须**新增** `conductorInflightKeys` 集合，不得改动 `nonTerminalByKey`，否则 `blockedOnHuman` 语义漂移（采集 `monitor.ts:607`，判定 `status-model.ts:1586`，渲染 `monitor.ts:1227`）。

### 6.2 未覆盖面（明确声明）

- 本报告**不覆盖**：RQ-D3 的锁临界区实现、RQ-D4 的任务级 `deps:` 载体/校验/前沿消费、`execute_loop` 的 per-key 并发改造（只给指针 `conductor.py:1737/1770-1772/1800`）、写面重叠拒绝（前置 key）。
- **不决定** `max_workers_per_key` 的最终命名/默认/上界。
- 不改任何生产文件；不写 `pm-state.md`/`_workers*`/`_index.parallel`/其它 key/`packages/**`。
- 不覆盖 per-key 并发放开后 provider rate limit / proxy 上游池的实测（spec §2.2 风险 1）。

---

## 7. [VERIFY]（数值实测打印）

- `[VERIFY] corpus: sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a cases=73 frozen_sha256_match=true frozen_count_match=true`（§3.1；与 `test_autopilot_config_parity.py:60-61`、`autopilot-config-sync.test.ts:42-43` 一致）
- `[VERIFY] corpus_candidate_refreeze: 按 §3.2 步骤 1 的确切改法（2 改 + 3 增）⇒ sha256=713db5c5f30d46b14eae53036e9c1368517bd0b3024e69b7cbb8540ca126eb4b cases=76`（该 sha 仅对"本轮列出的确切改法"成立，落地必须重算）
- `[VERIFY] registry_dump: keys_order_equal=true defaults_equal=true int_ranges_equal=true bool_fields_equal=true list_fields_equal=true str_fields_equal=true enum_fields_equal=true schema_keys=20 py_optional=envelope_fallback ts_optional=envelope_fallback int_ranges_keys=14`（Python `autopilot.config` dump vs Node `status-model.ts` dump 逐字比对，§1；两处全 20 键顺序一致）
- `[VERIFY] proposed_floor_verdict: max_parallel_keys 0=reject 1=accept 2=accept 8=accept ; max_workers_per_key 0=reject 1=accept 2=accept 4=accept 8=accept`（在"默认 8 / floor 1 / 新键默认 4 / `(1,None)`"的内存态下，§2.1）
- `[VERIFY] current_floor_verdict: max_parallel_keys 0=reject 1=reject 2=accept 8=accept`（现态 floor 2，佐证 §2.1 的 F1/F3/F4 翻转）
- `[VERIFY] panel_slots: 合成队列 4 行（kA running/conductor、kB pending/conductor、kC running/manual、kD done/conductor）；面板输入=running-only ⇒ slotsUsed=1；conductor 口径在飞={kA,kB} count=2；frontier(去 SKIP、deps 满足)={kA,kC} count=2；eff=min(cap=8,frontier=2)=2`（§4.2）
- `[VERIFY] predicate_mirror_py: terminal_statuses=['done','failed','lost','needs-clarification'] ; python_conductor_inflight=['kA','kB'] count=2 ; pending_counts_as_inflight=true ; manual_counts_as_slot=false`（§4.2；两侧谓词同集）
- `[VERIFY] advance: call_sites=3 (conductor.py:1621/1801/2749) ; docstring_mentions=2 (conductor.py:28/601) ; timeout_sec=120 (advance.py:36) ; cap_consumer=1 (conductor.py:744) ; tick_beat_data=absent (conductor.py:3434)`（§5.1）
- `[VERIFY] dist_hits: multi-workers/dist/extensions/agent-team-loop.js: 24081/24113/24213/24240/25133/25173/25912 ; coding-agent/dist/.../status-model.js: 68/119/253/285/1412/1463 ; .../monitor.js: 706`（§1.5 B1/B2）
- `[VERIFY] order_lock: DEFAULT_CONFIG tail-9 ([-1..-9]) 与 INT_RANGES 全序表在插入 index 4 时不变；TS at(-1..-7) 同理`（§1.3；由键序推导 [推算]，未跑测试确认）