# T-C3 配置与镜像（RQ-C3）— `max_parallel_keys` 生效链 / 两侧镜像 / 兼容面 / per-key 新键落点

- key: mw-dynamic-concurrency
- task: mdc-rq3-config-mirror（T-C3-config-mirror）
- 日期: 2026-10-14
- 角色: 只读；唯一写面 = 本文件
- 判据格式: `file:line` + 原文片段。未找到的写「未找到（命令 + 输出）」；推算值标 **[推算]**，其余均为实测。

---

## 0. 结论先行

1. **生效链是单点消费**：`max_parallel_keys` 定义 `config.py:87`，取值域 `config.py:122`（`(2, None)` = floor 2、无上限），校验 `config.py:147`，读取经 conductor 唯一配置缝 `_load_effective_config`（`conductor.py:136-154`），**唯一消费点** `conductor.py:744`（`if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"]))`）。全仓 Python 侧无第二个消费者（grep 实测）。
2. **机器层不可配（实测）**：`EFFECTIVE_KEYS` 只有 `xkey_verify_cmd` + `xkey_verify_cwd`（`effective_config.py:62-65`）。机器层写 `max_parallel_keys: 9` 被丢弃并出诊断 `'max_parallel_keys' is not machine-overridable (ignored)`，`origin=default`、值=2。即该键**只有项目层可配**。
3. **两侧镜像零漂移（实测）**：key 顺序、20 个默认值、`INT_RANGES` 全部、`_BOOL/_LIST/_STRING/_ENUM` 四张注册表逐字一致。唯一"非对称"是设计使然：Python `load_config` 返回 partial、TS `readConfig` 读时合并默认；以及 TS 多一层 JSON 整数字面量 reviver（防 `4.0/1e2/-0.0` 混入）。
4. **兼容面：既有实例不会因默认/floors 变更而非法，但改默认值对它们"空操作"**。现存实例只有 2 个（`E2Feature` 显式 `4`、`JCodingAss` 显式 `2`），都是 8 键 partial。实测：把默认改成 8、floor 降到 1 后，显式 2/4 仍解析为 2/4；无配置文件的项目变为 8。真正风险在"写路径 materialize"：TS `saveConfig` 与 Python `mw autopilot verify set` 都会把 partial 文件重写成全 20 键（实测 2 键 → 20 键）。
5. **新增 per-key 键的落点 = 4 处代码 + 1 处面板/JSON + parity 语料（含 sha256/计数/`partial-key-*` 覆盖）+ 6 张 Python 锁 + 3 张 TS 锁 + README 表 + 2 个 dist bundle**（§4 逐条 `file:line`）。
6. 最大跨版本风险：两侧 schema 互相 fail-closed（未知键即整份作废）。新键必须**两侧同波上线**，否则 21 键的 config.json 会被旧 bundle/旧 Python 判 `unknown field(s)`（README.md:314、docs/autopilot-observability-guide.md:23 有同名纪律）。

---

## 1. `max_parallel_keys` 生效链（定义 → 校验 → 读取 → 消费）

### 1.1 定义

| 环节 | 判据 | 原文片段 |
|---|---|---|
| 文档声明表 | `packages/multi-workers/autopilot/config.py:16` | `max_parallel_keys  int     2    (floor 2)` |
| 默认值表 | `packages/multi-workers/autopilot/config.py:83`（表首）、`:87` | `DEFAULT_CONFIG: dict = {` … `"max_parallel_keys": 2,` |
| 默认拷贝函数 | `config.py:142` | `def default_config() -> dict:` |

### 1.2 校验

| 环节 | 判据 | 原文片段 |
|---|---|---|
| 取值域注册表 | `config.py:120`（表首）、`:122` | `_INT_RANGES: dict[str, tuple[int, int \| None]] = {` … `"max_parallel_keys": (2, None),` |
| 校验入口 | `config.py:147` | `def validate_config(cfg: object) -> None:` |
| 未知键 fail-closed | `config.py:152` | `unknown = sorted(set(cfg) - set(DEFAULT_CONFIG) - {ENVELOPE_FALLBACK_KEY})` |
| bool 先于 int | `config.py:114` + int 分支 | `_BOOL_FIELDS = ("enabled", "paused", "xkey_repair", ENVELOPE_FALLBACK_KEY)`；int 分支 `if isinstance(value, bool) or not isinstance(value, int)` |

语义要点：`(lo, hi)=(2, None)` ⇒ `1` 被拒、无上限。语料实证：`packages/multi-workers/test/fixtures/autopilot-config-corpus.json:296-302`（`{"max_parallel_keys": 1}` → `reject / ["max_parallel_keys"]`）、`:309-313`（`{"max_parallel_keys": 2}` → `accept`）。
**语义变更点（硬上限→上界时）**：若要允许 `1` 作 kill switch，须把 `:122` 的 floor 由 `2` 改为 `1`；否则 AC-006（上界改 1 回串行）在该键上不可表达。

### 1.3 读取

| 环节 | 判据 | 原文片段 |
|---|---|---|
| conductor 唯一配置缝 | `conductor.py:136` | `def _load_effective_config(project_root: pathlib.Path) -> dict:` |
| 默认打底 | `conductor.py:148` | `values = config.default_config()` |
| 项目层合并 | `conductor.py:149` | `values.update(config.cached_load(project_root))` |
| 机器层解析 | `conductor.py:150` | `effective = effective_config.load_effective(project_root)` |
| 仅 xkey 两键接受机器层 | `conductor.py:151-153` | `for key in effective_config.EFFECTIVE_KEYS:` / `if effective.origins.get(key) == "machine":` / `values[key] = effective.values[key]` |
| orchestrate 读取 | `conductor.py:604` | `cfg = _load_effective_config(project_root)` |
| 其它读取缝 | `conductor.py:3441`（每 tick 开关判定）、`:2754`（advance 记账） | `cfg = _load_effective_config(project_root)` |
| 共享读取缝 | `packages/multi-workers/mw_common.py:2746` | `def _autopilot_effective_values(project_dir) -> tuple[dict, dict, list[str]]:` |

与 TS 的读取差异（设计使然，非漂移）：Python `config.load_config` 是 **raw** 加载器（partial 文件只返回它写的键，`config.py:194-213`）；TS `readConfig` 是 **merge-on-read**（缺省键回落默认，`status-model.ts:302-372`）。P6 parity 以此为前提（`test_autopilot_config_parity.py:389-429`）。

### 1.4 消费（唯一）

| 环节 | 判据 | 原文片段 |
|---|---|---|
| key 层硬闸 | `conductor.py:744` | `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):` （下一行注释 `# parallel cap — key starts on a later tick`） |
| 同 key 硬串行（per-key 层现状） | `conductor.py:742` | `if key in in_flight_keys: continue  # wait for the in-flight worker` |
| 第二重同 key 串行（exec 循环） | `conductor.py:1736`（`def execute_loop`）、`:1765`、`:1771` | `for stem in _plan_task_order([f.stem for f in files], plan):` … `if any(_is_in_flight(r) for r in fam): return False  # per-key serial: wait for the in-flight task` |
| 派发调用点 | `conductor.py:746` | `if _advance_key(project_root, st, key, rows, rounds, cfg, rm_path):` |

**per-key 新键的天然消费点**：`execute_loop`（`conductor.py:1736-1801`）目前**只派 1 个 task 就 return**（`:1799 return result.ok`）。要放开 per-key 并发，闸门必须落在这里（按 `cfg[<new per-key key>]` 与任务前沿取 min，并把 `:1771` 的"见任一在飞就 return"改成"在飞数 ≥ per-key 上界才等"）。key 层闸在 `:744`（已按"同时推进 key 上限"实现，只需把语义从"等于并发度"改为"上界"并把默认值/floor 重定）。

### 1.5 机器层不可配（实测证据）

- 键域定义 `packages/multi-workers/autopilot/effective_config.py:62-65`：
  `EFFECTIVE_KEYS = (` / `"xkey_verify_cmd",` / `"xkey_verify_cwd",` / `)`
- 机器层加载器 `effective_config.py:136`（`def _load_machine_layer(`）；越域拒绝 `:168`：
  `diagnostics.append(f"{path}: {key!r} is not machine-overridable (ignored)")`
- 非机器键 origin 判定 `effective_config.py:227-230`：
  `if field not in EFFECTIVE_KEYS:` / `if field in raw:` / `origins[field] = "project"`（否则保持 `default`）
- 实测（命令与输出见 §6 `[VERIFY] machine_layer`）：机器文件写 `{"max_parallel_keys": 9, "xkey_verify_cwd": "x"}` ⇒ `value=2, origin=default, diagnostics=[... 'max_parallel_keys' is not machine-overridable (ignored)], xkey_verify_cwd origin=machine`。

结论：`max_parallel_keys`（以及任何新增 per-key 键，除非显式加入 `EFFECTIVE_KEYS`）**只有项目层可配**，机器层写入只产生诊断。若要"机器层也能封顶"，须显式改 `EFFECTIVE_KEYS` + `EMPTY_VALUE`（`effective_config.py:68`）——本 key 的 spec 未要求，属决策项。

---

## 2. 两侧镜像对照表

### 2.1 逐字段（Python `config.py` ↔ TS `status-model.ts`）

默认值与取值域实测来自两侧注册表 dump（§6 `[VERIFY] registry_dump`），逐字一致。

| 键 | Python 默认 / 取值域（`config.py`） | TS 默认 / 取值域（`status-model.ts`） | 类别注册 |
|---|---|---|---|
| `enabled` | `:84` `False` | `:133` `false` | bool（Py `:114`，TS `:167`） |
| `paused` | `:85` `False` | `:134` `false` | bool |
| `poll_interval_sec` | `:86` `4` / `:121` `(1, 5)` | `:135` `4` / `:195` `[1, 5]` | int |
| **`max_parallel_keys`** | **`:87` `2` / `:122` `(2, None)`** | **`:136` `2` / `:196` `[2, null]`** | int |
| `round_budget` | `:88` `2` / `:123` `(1, None)` | `:137` `2` / `:197` `[1, null]` | int |
| `worker_timeout_min` | `:89` `30` / `:124` `(1, None)` | `:138` `30` / `:198` `[1, null]` | int |
| `l2_read_file_cap` | `:90` `8` / `:125` `(1, None)` | `:139` `8` / `:199` `[1, null]` | int |
| `l2_read_byte_cap` | `:91` `65536` / `:126` `(1, None)` | `:140` `65536` / `:200` `[1, null]` | int |
| `advance_stall_ticks` | `:92` `5` / `:127` `(1, 50)` | `:141` `5` / `:201` `[1, 50]` | int |
| `xkey_repair` | `:93` `False` | `:142` `false` | bool |
| `xkey_verify_cmd` | `:94` `[]` | `:143` `[]` | list[str]（Py `:115`，TS `:182`） |
| `xkey_verify_timeout_s` | `:95` `1800` / `:128` `(1, None)` | `:144` `1800` / `:202` `[1, null]` | int |
| `xkey_verify_cwd` | `:96` `""` | `:145` `""` | str（Py `:116`，TS `:185`） |
| `auto_gate_mode` | `:97` `"off"` / `:117-119` `off\|shadow\|live` | `:146` `"off"` / `:189-191` `off\|shadow\|live` | enum（Py `:117`，TS `:189`） |
| `launcher_max_workers` | `:98` `8` / `:129` `(1, 64)` | `:147` `8` / `:203` `[1, 64]` | int |
| `dispatch_max_per_scan` | `:99` `3` / `:130` `(1, 64)` | `:148` `3` / `:204` `[1, 64]` | int |
| `queue_alarm_delta` | `:100` `50` / `:131` `(10, 10000)` | `:149` `50` / `:205` `[10, 10000]` | int |
| `l3_abort_retry_limit` | `:101` `1` / `:132` `(0, 10)` | `:150` `1` / `:206` `[0, 10]` | int |
| `gate_reminder_after_min` | `:102` `30` / `:133` `(1, 1440)` | `:151` `30` / `:207` `[1, 1440]` | int |
| `gate_reminder_max` | `:103` `2` / `:134` `(1, 2)` | `:152` `2` / `:208` `[1, 2]` | int |
| （schema 外可选）`envelope_fallback` | `:113` `ENVELOPE_FALLBACK_KEY`，注册于 `_BOOL_FIELDS` `:114`，不在 `DEFAULT_CONFIG` | `:167` `BOOL_FIELDS`，`:177` `OPTIONAL_CONFIG_KEYS` 派生 | bool（optional） |

读取/写入镜像函数：

| 环节 | Python | TS |
|---|---|---|
| 默认拷贝 | `config.py:142` `default_config()` | `status-model.ts:157-159` `freshDefaults()` |
| 校验 | `config.py:147` `validate_config` | `status-model.ts:246` `validateConfigData` |
| JSON 整数语义 | `json.loads` → Python `int`（拒绝 bool） | `status-model.ts:233` `configReviver` + `:222` `INT_LITERAL_RE`（额外拒绝 `4.0/4.00/1e2/-0.0` 字面量） |
| 读 | `config.py:194` `load_config`（raw，partial 不补默认） | `status-model.ts:302` `readConfig`（merge-on-read） |
| 写 | `config.py:216` `save_config` | `status-model.ts:375` `saveConfig` |
| 分层解析 | `effective_config.py:200` `load_effective` | （无 TS 对应；TS 单层） |

### 2.2 已有漂移

**schema/注册表/取值域：未发现漂移**（§6 `[VERIFY] registry_dump` 六项全等）。发现的**文档漂移**（非 schema）：

- `packages/multi-workers/README.md:312`：`两个写者都会把 13 键材料化写进项目文件` —— 现为 20 键（`config.py:83-103` 共 20；`test_autopilot_config.py:117` `assert len(cfg.DEFAULT_CONFIG) == 20`）。
- `packages/multi-workers/autopilot/conductor.py:139`：`Returns the complete 13-key view.` —— 现为 20 键（`conductor.py:148` 用 `default_config()`）。
- 相邻键的**消费侧不对称（非 schema 漂移，设计使然）**：`launcher_max_workers` 仅 Python 消费（`launcher.py:1735`、`:1884`、`mw_common.py:1959`）；`dispatch_max_per_scan` 仅 TS 消费（`pm-orchestrator.ts:628-639`）；`queue_alarm_delta` 仅 Python 消费（`mw_common.py:2642`）。

### 2.3 parity 语料/测试 与重冻方式

| 件 | 判据 | 说明 |
|---|---|---|
| 共享语料 | `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`（schema `mw-autopilot-config-corpus/v1`，73 cases） | P1 裁决/P2 字节/P3 幂等/P6 视图分层 |
| Python 半边 | `packages/multi-workers/test_autopilot_config_parity.py:60-61` | `FROZEN_CORPUS_SHA256`、`FROZEN_CORPUS_COUNT = 73` |
| 冻结断言 | `test_autopilot_config_parity.py:311-315` | sha256 + count + D1-D6 覆盖 |
| TS 主判 | `packages/coding-agent/test/suite/autopilot-config-parity.test.ts` | spawn 真 Python 做反向差分 |
| TS 语料锁 | `packages/coding-agent/test/suite/autopilot-config-sync.test.ts:42-43`（`FROZEN_CORPUS_SHA256`/`COUNT`）、`:104-` P4、`:170-` P5 | P5 逐字比对 registry |
| TS 可选键锁 | `packages/coding-agent/test/suite/mwgal-t20-config-parity.test.ts:141`（`expect(py.keys).toHaveLength(20)`） | 可选键分类 |
| TS 显式计数锁 | `packages/coding-agent/test/suite/autopilot-console.test.ts:911`（`expect(Object.keys(DEFAULT_CONFIG)).toHaveLength(20)`）、`:937` | 20 键镜像 |
| TS P6 硬编码 20 | `autopilot-config-parity.test.ts:356`、`:361` | `toBe(20)` |
| Python P6 硬编码 20 | `test_autopilot_config_parity.py:423`、`:426` | `== 20` |
| Python 计数/键集锁 | `test_autopilot_config.py:117`、`:119-125`、`:153`、`:188`；`test_autopilot_effective_config.py:74`、`:209`；`test_mw_autopilot_cli.py:124`；`test_mwgal_t12_stage_close_auto.py:658-667`；`test_mwgal_t15_reattest_confirm.py:720-729`；`test_mwds_t14_producer_skew.py:600` | 见 §4 |
| 语料单键覆盖 | `test_autopilot_config_parity.py:405-429`（P6：`covered == expected_keys`，`expected_keys = set(KNOWN_FIELDS)`） | **新增键必须补 `partial-key-<new>` 用例**，否则 P6 直接红 |

**重冻方式**（deliberate re-freeze，三处同步）：
1. 改 `test/fixtures/autopilot-config-corpus.json`（加 `range-*` / `partial-key-<new>` 等用例，必要时改 `range-max-parallel-low` 的期望）；
2. 重算 sha256 与计数，同时更新 `test_autopilot_config_parity.py:60-61` 与 `autopilot-config-sync.test.ts:42-43`；
3. 跑两侧 parity（TS 主判 + Python 镜像）确认 P1-P6 全绿。

实测当前语料：`sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a, cases=73`，与冻结值一致。

---

## 3. 既有配置兼容面

### 3.1 会"显式 materialize 全部键"的写路径

| 写路径 | 判据 | 行为 |
|---|---|---|
| TS `saveConfig` | `status-model.ts:375`；有序全量对象 `:379-400` | 无论输入是否 partial，写出 `DEFAULT_CONFIG` 顺序的**全 20 键** |
| TS 控制台 RMW | `console.ts:558 saveConfigLocked`、`:580 saveConfig(...)`；调用点 `:592 cmdSetEnabled` | `readConfig`（补默认）→ `mutate` → `saveConfig`（全量）。`/autopilot enable\|pause` 一次即把 partial 文件变 20 键 |
| Python `mw autopilot verify set` | `mw.py:3508` `merged = {**_ap_config.default_config(), **(raw or {}), **changes}`；`:3530 save_config(project_dir, merged)` | 同上，全 20 键 materialize |
| Python `mw autopilot verify clear` | `mw.py:3611-3654`（`del raw[key]` → `save_config(project_dir, raw)`） | **不 materialize**：只删四个 xkey 键，其余键与 partial 形态保持 |
| `config.save_config` 本身 | `config.py:216-228` | 写它收到的字典（先 `validate_config`）；不主动补默认 |

注：`effective_config.py:33-35` 的注释已把"两个写者都会 materialize 全键"作为既定事实（"空值即未决定"规则的起因）。

### 3.2 语义变更（硬上限→上界 / floor 变更）在既有项目上的实际行为

现存实例（只读扫描，见 §3.3）均为 **partial 且显式写值**。实测（§6 `[VERIFY] compat_sim`，内存内改默认=8、floor=1）：
- 显式 `max_parallel_keys: 2` → 仍 `2`（JCodingAss 形态，**改默认值空操作**）
- 显式 `max_parallel_keys: 4` → 仍 `4`（E2Feature 形态）
- 文件缺失 → 采用新默认 `8`
- floor=1 后 `{"max_parallel_keys": 1}` 校验通过

含义：
- **不会变非法**：`2`/`4` 落在 `[1, ∞)` 内；新 per-key 键在 partial 文件里缺省 ⇒ 回落默认（`status-model.ts:341`、`effective_config.py:238-242`）。满足 AC-004 后半句。
- **默认值语义变更对已 materialize 的实例是空操作**（与 `mw-autopilot-slot-capacity/achieved.md` §3 (c3′)/D-020 的已知失败模式一致）。若要让既有项目吃到新默认/新上界，**必须显式迁移**（改文件值，或提供一次性 CLI/迁移），改常量不够。
- key 层 `:744` 今天已是"在飞 ≥ cap 就停"的**上界语义**；把定义改为"由依赖前沿动态求出、配置封顶"时，消费点本身无需改语义，只需上游算前沿（RQ-C2）+ 默认/floors 重定。
- **floor 从 2 降到 1** 才会让语料 `range-max-parallel-low`（corpus:296-302，期望 reject）与 `test_autopilot_config.py:50`（`{"max_parallel_keys": 1}` 期望被拒）翻转；这两处必须随语义改。

### 3.3 会被影响的现存 `config.json` 实例（只读扫描）

扫描命令与范围：`cd H:/git; foreach ($d in @('E2Feature','DSH','evo-mind','J3AgenticTask','JCodingAss','LearningTree')) { Test-Path "$d/.agenticdoc/_autopilot/config.json" }`；另 `H:/git` 全树 `Get-ChildItem -Recurse -Force -File -Filter config.json | Where-Object FullName -match '_autopilot'`。
结果：**只找到 2 个**（本仓 `Multi-Workers` 自身无此文件；`~/.agents/autopilot-defaults.json` 不存在）。

| 实例 | 键数 | `max_parallel_keys` | 其它显式键 | mtime | sha256 |
|---|---|---|---|---|---|
| `H:/git/E2Feature/.agenticdoc/_autopilot/config.json` | 8 | **4** | enabled=true, paused=false, poll_interval_sec=4, round_budget=2, worker_timeout_min=240, l2_read_file_cap=128, l2_read_byte_cap=4194304 | 2026-10-13T21:42:37 | `37FB0581BCB2A2C88A949E5012059B9224CA5465880C999C142A8FAE049AF0F0` |
| `H:/git/JCodingAss/.agenticdoc/_autopilot/config.json` | 8 | **2** | enabled=true, paused=false, poll_interval_sec=4, round_budget=2, worker_timeout_min=30, l2_read_file_cap=8, l2_read_byte_cap=65536 | 2026-09-10T23:02:25 | `A9A4863B72AD3BBBD313FB3AF70C15488619A5DC63E7E413549847D39D69B1A3` |

两侧读时行为实测（§6 `[VERIFY] compat_read`）：TS `readConfig` 对 8 键 partial → `merged_keys=20, mpk=2`；再 `saveConfig` → `written_keys=20, mpk=2`（materialize 并保留显式值）。

跨版本风险（对这两个实例的直接影响）：若只更新一侧 schema 后这两个项目被新版写者 materialize 成 21 键，另一侧（未更新）会 fail-closed 整份作废（`config.py:152` unknown 分支 / `status-model.ts:252-258`）。故新键上线必须两侧同波（README.md:314）。

---

## 4. 新增 per-key 上界键需要改的文件清单（每条 `file:line`）

> 键名/默认/取值域未定（spec §4 待确认），下表只给**落点**。

### 4.1 Python（定义/校验/读取/消费）

| # | 文件:行 | 动作 |
|---|---|---|
| P1 | `packages/multi-workers/autopilot/config.py:83`（表）+ 表尾 `:103` 后 | `DEFAULT_CONFIG` 增键+默认值（顺序变更会牵动 §4.4 的顺序锁） |
| P2 | `packages/multi-workers/autopilot/config.py:120`（表）+ 尾 `:134` | `_INT_RANGES` 增取值范围（若 floor 由 2→1，同时改 `:122`） |
| P3 | `packages/multi-workers/autopilot/config.py:16-50`（docstring 键表） | 同步字段说明 |
| P4 | `packages/multi-workers/autopilot/conductor.py:1736 execute_loop`（闸门 `:1765-1771`、派发 `:1779-1799`） | per-key 上界消费点：把"见在飞即 return"改为"在飞数 ≥ min(上界, 任务前沿)"；`return result.ok` 改为继续迭代 |
| P5 | `packages/multi-workers/autopilot/effective_config.py:62-65`、`:68` | **仅当**允许机器层覆盖时才改；否则不动（默认项目层可配，见 §1.5） |
| P6 | `packages/multi-workers/mw.py:3508` | `verify set` 已用 `default_config()` 合并，自动带上新键（无需改，但回归需覆盖） |

### 4.2 TS（镜像/校验/读取/呈现）

| # | 文件:行 | 动作 |
|---|---|---|
| T1 | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:76`（`AutopilotConfig`，`max_parallel_keys` 在 `:80`） | 接口增字段 |
| T2 | `status-model.ts:132`（`DEFAULT_CONFIG`）+ 表尾 `:153` | 增默认值 |
| T3 | `status-model.ts:194`（`INT_RANGES`）+ 尾 `:209` | 增取值范围（`max_parallel_keys` 在 `:196`） |
| T4 | `status-model.ts:325-341`（`intOf` 联合类型） | 增字段到 intOf 白名单 |
| T5 | `status-model.ts:347-367`（merged read 对象） | `readConfig` 输出增字段 |
| T6 | `status-model.ts:379-400`（`saveConfig` 有序对象） | `saveConfig` 写出增字段（materialize 面） |
| T7 | `status-model.ts:1602-1607`（`StatusConfigView`）、`:1738-1743`（`--json` config 子对象） | 状态 JSON 增字段 |
| T8 | `status-model.ts:1793-1795`（文本摘要） | 文本面增字段（如需） |
| T9 | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:933`（`slotsMax`）、`:1217`（面板行 `slots ${a.slotsUsed}/${a.slotsMax}`） | **AC-005**：面板同时给"配置上界"与"本 tick effective 并发"，两者口径可复算 |
| T10 | `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts:558-585`（`saveConfigLocked`） | 无需改（通用 RMW），但受 T5/T6 影响 |

### 4.3 parity 语料与重冻

| # | 文件:行 | 动作 |
|---|---|---|
| C1 | `packages/multi-workers/test/fixtures/autopilot-config-corpus.json` | 增 `partial-key-<new>`（P6 覆盖必需，`test_autopilot_config_parity.py:405-429`）；payload 里 `max_parallel_keys` 相关用例复核 |
| C2 | 同上 `:296-302` | 若 floor 2→1：`range-max-parallel-low` 期望 reject→accept |
| C3 | `packages/multi-workers/test_autopilot_config_parity.py:60-61` | 重算并更新 `FROZEN_CORPUS_SHA256` / `FROZEN_CORPUS_COUNT` |
| C4 | `packages/coding-agent/test/suite/autopilot-config-sync.test.ts:42-43` | 同上两个常量 |
| C5 | `packages/multi-workers/test_autopilot_config_parity.py:423`、`:426` | 硬编码 `20` → 21（或改为 `len(KNOWN_FIELDS)`） |
| C6 | `packages/coding-agent/test/suite/autopilot-config-parity.test.ts:356`、`:361` | 硬编码 `20` → 21 |

### 4.4 Python 锁（计数/键集/顺序，全部硬编码）

| # | 文件:行 | 动作 |
|---|---|---|
| L1 | `packages/multi-workers/test_autopilot_config.py:117`、`:119-125` | 20→21；新增/调整 `[-1..-n]` 顺序断言 |
| L2 | `packages/multi-workers/test_autopilot_config.py:153`、`:188` | `20`→21 |
| L3 | `packages/multi-workers/test_autopilot_effective_config.py:74`、`:209` | `20`→21 |
| L4 | `packages/multi-workers/test_mw_autopilot_cli.py:124` | `20`→21 |
| L5 | `packages/multi-workers/test_mwgal_t12_stage_close_auto.py:658-667`、`:679` | 键集/计数 `20`→21 |
| L6 | `packages/multi-workers/test_mwgal_t15_reattest_confirm.py:720-729`、`:741` | 同上 |
| L7 | `packages/multi-workers/test_mwds_t14_producer_skew.py:600` | `len(config.DEFAULT_CONFIG) == 20` → 21 |
| L8 | `packages/multi-workers/test_autopilot_config.py:50` | 若 floor 2→1：`{"max_parallel_keys": 1}` 从 reject 用例移出 |
| L9 | `packages/multi-workers/test_autopilot_config.py:124`、`:128` | 新增键的默认值/位置锁（新增项） |

### 4.5 TS 锁

| # | 文件:行 | 动作 |
|---|---|---|
| S1 | `packages/coding-agent/test/suite/autopilot-console.test.ts:911` | `toHaveLength(20)` → 21 |
| S2 | `packages/coding-agent/test/suite/autopilot-console.test.ts:937`（bool 列表）、`:939`（list）、`:940`（str） | 若新键改变类别注册表则同步 |
| S3 | `packages/coding-agent/test/suite/mwgal-t20-config-parity.test.ts:141`（`toHaveLength(20)`）、`:194`、`:208`（`merged_keys=20`） | 20→21 |
| S4 | `packages/coding-agent/test/suite/autopilot-config-sync.test.ts:170-200`（P5 分类逻辑） | 由 `DEFAULT_CONFIG` 派生，通常无需改；确认 `optional` 分类仍成立 |

### 4.6 文档与产物

| # | 文件:行 | 动作 |
|---|---|---|
| D1 | `packages/multi-workers/README.md:225`（`max_parallel_keys` 行） | 说明改为"上界"；新 per-key 键加一行 |
| D2 | `packages/multi-workers/README.md:220-232`（配置表） | 新键/新默认/新取值域 |
| D3 | `packages/multi-workers/README.md:303-314`（两层配置）+ `:312`（"13 键"过期） | 同步键数/机器层键域纪律 |
| D4 | `packages/multi-workers/docs/autopilot-observability-guide.md:23` | 两侧同版本上线纪律（若键数变化） |
| D5 | `packages/multi-workers/dist/extensions/agent-team-loop.js:24081`（`DEFAULT_CONFIG`）、`:24113`（`INT_RANGES`） | 重建 bundle（`mw build` / `mw build --install`） |
| D6 | `packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js:68`、`:119`、`:253`、`:285`、`:1412`、`:1463` | 重建 bundle（`npm run build` 或 `mw build --install`） |

---

## 5. 残留与未验证 / 未覆盖面声明

### 5.1 已实测
- 两侧注册表六项（key 顺序、默认、bool/list/str/enum、int_ranges）逐字一致。
- 机器层 `max_parallel_keys` 被忽略 + 诊断 + origin=default。
- 语料 sha256/count 与冻结值一致。
- 显式 2/4 在"默认改 8 + floor 改 1"下不变；无文件者变 8；floor=1 校验通过。
- TS 8 键 partial → readConfig 合并 20 键、saveConfig materialize 20 键并保留显式值。

### 5.2 未验证（须在实现/校验阶段补）
- **未跑任何测试套件**（角色约束：只读、禁跑测试写快照）。两侧 parity（P1-P6）与全部计数锁的当前红绿状态未实测，只做了直接 registry dump 比较。
- 未跑 conductor tick 实采（不注入 roadmap/index 数据），"effective 并发 = min(上界, 前沿)"尚无运行期样本；属 RQ-C2 / 实现阶段。
- 未验证新键两侧同波上线的具体失败样本（需真实旧 bundle + 21 键文件）。
- 未验证 `dist/` 与 `src/` 是否完全同源；只核对了 `max_parallel_keys` 相关行存在。
- 未扫描 `H:/` 之外的项目（本机 `~/.agents/autopilot-defaults.json` 不存在；`H:/git` 全树只 2 个实例）。

### 5.3 未覆盖面（明确声明）
- 本报告**不覆盖**任务级依赖/前沿的机器可读载体（RQ-C2）、per-key 写面重叠拒绝（`mw-write-face-guard`）、key 层前沿计算（`conductor.py::orchestrate` 的 deps_of/in_flight_keys 语义）。
- **不决定**新 per-key 键的名称/默认值/取值域（spec §4 待确认项）。
- 不改任何生产文件；不改 `.agenticdoc` 其它 key 的文件。

---

## 6. [VERIFY]（数值实测打印）

- `[VERIFY] registry_dump: keys_order_equal=true defaults_equal=true int_ranges_equal=true bool_fields_equal=true list_fields_equal=true str_fields_equal=true enum_fields_equal=true schema_keys=20 py_optional=envelope_fallback ts_optional=envelope_fallback`（py dump 与 node dump 逐字比对，§2.1）
- `[VERIFY] machine_layer: machine_wrote=9 effective_value=2 origin=default xkey_verify_cwd_origin=machine diagnostics=1 ("'max_parallel_keys' is not machine-overridable (ignored)")`（§1.5）
- `[VERIFY] corpus: sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a cases=73 frozen_sha256_match=true frozen_count_match=true`（§2.3）
- `[VERIFY] compat_sim: default_8_floor_1 explicit_2=2 explicit_4=4 absent=8 valid_1=true`（§3.2）
- `[VERIFY] compat_read: ts_partial_keys_in=2 (enabled,max_parallel_keys) readConfig_ok=true merged_keys=20 mpk=2 saveConfig_ok=true written_keys=20 written_mpk=2`（§3.3）
- `[VERIFY] existing_instances: count=2 E2Feature.keys=8 mpk=4 JCodingAss.keys=8 mpk=2 machine_layer_file_absent=true`（§3.3）
- `[VERIFY] consumers: py_max_parallel_keys_consumers=1 (conductor.py:744) ts_consumers=2 files (monitor.ts:933, status-model.ts:1742/1794) floor=2 upper=None unique_writer_paths=3 (status-model.ts:375, mw.py:3530, config.py:216)`
