# M-03 证据 · 配置上界放宽 + per-key 上界键 + 面板三量（MDC B0）

- key: mw-dynamic-concurrency
- task: mdc-m03-config-panel（T-C-M03）
- 日期: 2026-10-14
- 目标锚点: `.agenticdoc/goal.md` —— key 层上界与 per-key 上界都是配置里的上界（默认放开、下限允许 1），两侧语言镜像一致；面板同时可见"配置上界"与"本 tick effective 并发"。
- 角色: coding；写面 = 卡列 4 个源/夹具 + 全仓 sweep 到的同类计数锁文件。

---

## 结论

1. `max_parallel_keys` 默认 **2 → 8**、下限 **2 → 1**，`max_workers_per_key` 默认 **4**、下限 **1**，插在 **index 4**（`max_parallel_keys` 之后）；`config.py` 与 `status-model.ts` 逐字段镜像（P5 `key_order_match/defaults_match/int_ranges_equal` 全 true，`keys=21 int=15`）。
2. 既有 materialized `config.json`（缺席新键）**不变非法**：`load_config` 通过，`load_effective().values` 补默认 4，21 键。
3. 面板显示 `cap / eff / frontier`，`used` 改为与 conductor 同源（非终态 ∧ origin=conductor ∧ path key）；同一快照 `eff == min(cap, |F|)` 成立（cap8: 2==2；cap1: 1==1）。只新增一行，既有行内容与行序未改。
4. 上界配 1 ⇒ `eff=1`，且配置每 tick 重读、无需重启 serve（实测 8→1 无 `invalidate_cache`）。
5. parity 语料重冻：`sha256=1e27f5…4744a/cases=73` → `sha256=f5b60e…13e9c1/cases=77`；四处冻结常量同步；两侧 parity/sync/console/monitor 与 tsgo 全绿。

---

## 证据

### 命令清单（可复跑）

```powershell
cd H:/git/Multi-Workers/packages/multi-workers
python -m pytest test_autopilot_config.py test_mwgal_t12_stage_close_auto.py test_mwgal_t15_reattest_confirm.py -q
python -m pytest test_autopilot_config_parity.py test_autopilot_effective_config.py test_mw_autopilot_cli.py test_mwds_t14_producer_skew.py -q
python -m pytest test_autopilot_readcap_injection.py -q
$env:PYTHONUTF8="1"; python -m pytest -q; Remove-Item Env:PYTHONUTF8
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-config-parity.test.ts test/suite/autopilot-config-sync.test.ts test/suite/autopilot-console.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t20-config-parity.test.ts test/suite/mwgal-t21-qg-fixes.test.ts
npx tsgo --noEmit
node C:/Users/WENBOZ~1/AppData/Local/Temp/m03-panel-evidence.mjs        # 面板三量复算
python C:/Users/WENBOZ~1/AppData/Local/Temp/m03-config-evidence.py     # 默认/floor/回退
python C:/Users/WENBOZ~1/AppData/Local/Temp/m03-refreeze.py            # 语料重冻（输出 sha/count）
python -c "import json,hashlib,pathlib; p=pathlib.Path('test/fixtures/autopilot-config-corpus.json'); d=json.loads(p.read_text(encoding='utf-8')); out=json.dumps(d,ensure_ascii=False,indent=2)+'\n'; print('roundtrip_sha', hashlib.sha256(out.encode('utf-8')).hexdigest(), 'count', len(d['cases']), 'bytes_equal', out.encode('utf-8')==p.read_bytes())"
```

### ① 语料重冻：新旧 sha256 与计数

```
# 旧（HEAD 态，round-trip 自证）
roundtrip_sha 1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a count 73 bytes_equal True
# 重冻脚本（2 改 + 4 增）
old_sha256=1e27f59396c4076575743ea0bb71b05371b8532322adfb4c8bfa3c20ade4744a old_count=73
new_sha256=f5b60e81cd690930cc9afb4ef1ccdee6bd8d517e6d40521a3f1b84e65a13e9c1 new_count=77
```

语料改动（`packages/multi-workers/test/fixtures/autopilot-config-corpus.json`，1-based 新行号）：

| case id | 行 | before | after |
|---|---|---|---|
| `range-max-parallel-low` | 292（payload 296） | `payload {"max_parallel_keys": 1}` → `reject / [max_parallel_keys]` | payload **不动** → `accept / []` |
| `range-max-parallel-below-floor` | 874（新增，payload 878） | — | `{"max_parallel_keys": 0}` → `reject / [max_parallel_keys]` |
| `partial-key-max_workers_per_key` | 887（新增，payload 891） | — | `{"max_workers_per_key": 4}` → `accept / []` |
| `range-max-workers-per-key-low` | 898（新增，payload 902） | — | `{"max_workers_per_key": 0}` → `reject / [max_workers_per_key]` |
| `range-max-workers-per-key-min` | 911（新增，payload 915） | — | `{"max_workers_per_key": 1}` → `accept / []` |

- `range-max-parallel-min`（`:303`，payload `:307` `{"max_parallel_keys": 2}`）按卡面要求**保持不变**（accept）。
- 两个 bigint 行 `bigint-2p53`（`:351` payload `:355`）与 `bigint-2p53-minus-1`（`:362` payload `:366`）**payload 与期望均未动**：上界放宽/新键不影响 `accept` 结果，且 P4 以 payload 含 `9007199254740992` / `9007199254740991` 为硬判据（`test_autopilot_config_parity.py:319`），故只做核对、未改。
- 冻结常量（两侧同值）：
  - `packages/multi-workers/test_autopilot_config_parity.py:60-61`：`1e27f5…4744a`/`73` → `f5b60e…13e9c1`/`77`
  - `packages/coding-agent/test/suite/autopilot-config-sync.test.ts:42-43`：同上

两侧重冻校验输出：

```
[VERIFY] P4: corpus_sha256=f5b60e81cd690930cc9afb4ef1ccdee6bd8d517e6d40521a3f1b84e65a13e9c1 cases=77 categories=D1,D2,D3,D4,D5,D6
[VERIFY] P5: key_order_match=true defaults_match=true keys=21 bool=4 list=1 str=1 enum=1 int=15 optional=envelope_fallback
[VERIFY] P1: crosslang_verdict_match=77/77
[VERIFY] P2: canonical_sha_match=41 sha256_equal=true
[VERIFY] P3: py_to_ts_idempotent=41 ts_to_py_idempotent=41
[VERIFY] P6: partial_single_key=38 raw_view_partial=true effective_view_21=true fields_covered=21
```

### ② 默认值 / floor 三处 before→after

Python `packages/multi-workers/autopilot/config.py`（新行号）：

| 处 | 行 | before | after |
|---|---|---|---|
| 文档串 | 16 | `max_parallel_keys  int     2    (floor 2)` | `max_parallel_keys  int     8    (key-layer upper bound; … floor 1 = kill switch)` + 新增 `max_workers_per_key int 4 (per-key upper bound, floor 1)` |
| 默认值表 | 91 | `"max_parallel_keys": 2,` | `"max_parallel_keys": 8,` + `"max_workers_per_key": 4,` |
| 取值域 | 127 | `"max_parallel_keys": (2, None),` | `"max_parallel_keys": (1, None),` + `"max_workers_per_key": (1, None),` |
| 文案 | 69 / 115 / 207 | `frozen 20-key` / `complete 20-key view` | `21-key` |

TS `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（新行号）：

| 处 | 行 | before | after |
|---|---|---|---|
| 接口 | 80-85 | `max_parallel_keys: number;` | 同字段 + 新增 `max_workers_per_key: number;`（含 JSDoc） |
| 默认值 | 141 | `max_parallel_keys: 2,` | `max_parallel_keys: 8,` + `max_workers_per_key: 4,` |
| 取值域 | 202 | `max_parallel_keys: [2, null],` | `max_parallel_keys: [1, null],` + `max_workers_per_key: [1, null],` |
| read/write | 336/359/392 | — | `intOf` 联合、merged read、`saveConfig` 有序对象各 +1 行 |
| 视图/文本 | 1617/1754/1807 | — | `StatusConfigView`、`/autopilot status --json` config、`renderStatusText` 各 +`max_workers_per_key` |

配置复算原始输出：

```
keys=21 index4=max_workers_per_key
max_parallel_keys default=8 range=(1, None)
max_workers_per_key default=4 range=(1, None)
max_parallel_keys=0 -> reject (invalid _autopilot/config.json: max_parallel_keys: must be >= 1, got 0)
max_parallel_keys=1 -> accept
max_parallel_keys=2 -> accept
max_parallel_keys=8 -> accept
max_workers_per_key=0 -> reject (invalid _autopilot/config.json: max_workers_per_key: must be >= 1, got 0)
max_workers_per_key=1 -> accept
max_workers_per_key=4 -> accept
no_restart_reload first=8 second=1 (no invalidate_cache call)
legacy_materialized_no_new_key valid=true has_new_key_in_raw=False effective_max_workers_per_key=4 effective_keys=21
```

> 既有 materialized 文件（20 键、缺席 `max_workers_per_key`）仍合法：raw loader 只回写它带的键，`load_effective` 补默认值 4，完整视图 21 键；无 `unknown field(s)`。

### ③ 面板三量（原始渲染行 + 同快照复算）

合成快照：roadmap running stage，`kA=running, kB=running, kC=running(dep kB), kD=done`；`_workers.parallel` = `kA running/conductor`、`kB pending/conductor`、`kC running/manual`、`kD done/conductor`。|F| = kA+kB = 2，kC 因 dep 未满足被挡，kD 终态。

```
[cap8] cap=8 eff=2 frontier=2 used=2 slotsMax=8
[cap8] recompute eff == min(cap, |F|) -> 2 == 2 : true
[cap8] RENDER: autopilot: tick: none yet | slots 2/8 | keys 4 (running 3, stalled 0, done 1) | stall-ticks 5
[cap8] RENDER: autopilot: cap 8 | eff 2 (frontier 2)
[cap1] cap=1 eff=1 frontier=2 used=2 slotsMax=1
[cap1] recompute eff == min(cap, |F|) -> 1 == 1 : true
[cap1] RENDER: autopilot: tick: none yet | slots 2/1 | keys 4 (running 3, stalled 0, done 1) | stall-ticks 5
[cap1] RENDER: autopilot: cap 1 | eff 1 (frontier 2)
```

`used` 口径选择（AC-012 子问题）：**与 conductor 同源** —— 非终态（`pending` 计入）∧ `origin=conductor` ∧ `path` key；`manual` 行不占槽。理由：`conductor._is_in_flight` + `mw_common.row_belongs_to` 是唯一在飞事实源，面板只读面必须复用它才可复算；实测同一队列 running-only 口径 `used=1`，conductor 口径 `used=2`（差 1 即 `pending` 行）。本卡不动 conductor 语义，只在 TS 侧新增 `conductorInflightKeys`（`monitor.ts` `readMonitorState`），`nonTerminalByKey`（喂 `blockedOnHuman`，含 manual）保持原样。

实现落点（`monitor.ts`）：
- `readMonitorState`：新增 `conductorInflightKeys`，仅非终态行里 `owner!=="" && workerBelongsToKey(...)` 的 owner 入集合；作为第 5 参传入 `deriveAutopilotPanel`。
- `deriveAutopilotPanel`：`|F|` = running stage 内、key 状态 ∉ `{done,stalled,closed-legacy,pending-review}`、deps 全 ∈ `{done,closed-legacy}` 的 key 数；`slotsCap = config.max_parallel_keys`；`slotsEffective = min(slotsCap, frontierSize)`；`slotsUsed = |conductorInflightKeys ∩ allKeys|`（无参直呼时回退旧 running-only 扫描）。
- `renderMonitorLines`：在既有 summary 行**之后**新增一行 `autopilot: cap X | eff Y (frontier Z)`；`slots U/M` 与 `keys …`/`stall-ticks` 原样保留，避免 110 列截断吃掉既有断言（`stall-ticks 3`）。
- 残差：TS 不读 claim（`state.read_key_states`），故 `frontier_panel >= |F_conductor|`，`eff` 是上界；等式 `eff == min(cap, |F|)` 在面板自身 |F| 上成立（代码注释已声明）。

### ④ 上界 = 1 的复算输出

```
[cap1] cap=1 eff=1 frontier=2 used=2 slotsMax=1
[cap1] recompute eff == min(cap, |F|) -> 1 == 1 : true
[cap1] RENDER: autopilot: cap 1 | eff 1 (frontier 2)
no_restart_reload first=8 second=1 (no invalidate_cache call)
max_parallel_keys=1 -> accept
max_workers_per_key=1 -> accept
```

- key 层：`conductor.py:744` 用 `max(1, int(cfg["max_parallel_keys"]))`，配 1 ⇒ 每次最多 1 个在飞 key。
- per-key 层：`max_workers_per_key` 下限 = 1（M-02 以 `cfg.get("max_workers_per_key", 4)` 消费）。
- 无需重启 serve：`load_config` 不缓存（`cached_load` 每次重读），实测同一进程内 8→1 即时可见。

### ⑤ 计数锁文件完整清单（file:line + before → after）

Python：

| file:line（新） | before | after |
|---|---|---|
| `test_autopilot_config.py:50` | `({"max_parallel_keys": 1}, …)` reject 负例 | `({"max_parallel_keys": 0}, …)`（1 已合法，负例下移） |
| `test_autopilot_config.py:112` | `def test_default_config_has_20_keys_in_order` | `…_21_keys_in_order` |
| `test_autopilot_config.py:119` | `len(cfg.DEFAULT_CONFIG) == 20` | `== 21` |
| `test_autopilot_config.py:155` | `len(cfg.default_config()) == 20` | `== 21` |
| `test_autopilot_config.py:156` | `len(ec.load_effective(...).values) == 20` | `== 21` |
| `test_autopilot_config.py:190` | `len(eff.values) == 20` | `== 21` |
| `test_autopilot_config_parity.py:60-61` | frozen `1e27f5…`/`73` | `f5b60e…`/`77` |
| `test_autopilot_config_parity.py:423/426` | `== 20`（py/ts parsed count） | `== 21` |
| `test_autopilot_config_parity.py:437` | `effective_view_20=true` | `effective_view_21=true` |
| `test_autopilot_effective_config.py:74` | `len(eff.values) == 20` | `== 21` |
| `test_autopilot_effective_config.py:184` | `partial_project_keys=20` | `=21`（VERIFY 打印） |
| `test_autopilot_effective_config.py:209` | `len(eff.values) == 20` | `== 21` |
| `test_autopilot_effective_config.py:386` | `project_keys=20` | `=21`（VERIFY 打印） |
| `test_mwds_t14_producer_skew.py:600` | `len(config.DEFAULT_CONFIG) == 20` | `== 21` |
| `test_mw_autopilot_cli.py:124` | `len(stored) == 20` | `== 21` |
| `test_mwgal_t12_stage_close_auto.py:660` | 键集合 20 项 | +`"max_workers_per_key"`（21 项，`:679` VERIFY 自动 21） |
| `test_mwgal_t15_reattest_confirm.py:722` | 键集合 20 项 | +`"max_workers_per_key"`（21 项，`:741` VERIFY 自动 21） |
| `test_autopilot_readcap_injection.py:1013-1024` | `_GOLDEN_REGRESSION_SHA256["test_autopilot_config.py"] = 27b222b9…` | `= ce52c20e…`（该文件字节锁随合法的计数/floor 改动重冻） |

TS：

| file:line（新） | before | after |
|---|---|---|
| `autopilot-console.test.ts:394-402` | `s.config` 等值 `max_parallel_keys: 2` | 保持 2（fixture 显式写 2）+ 新增 `max_workers_per_key: 4` |
| `autopilot-console.test.ts:434` | 无 | +`toContain('max_workers_per_key=…')`（VC-017 视图一致） |
| `autopilot-console.test.ts:460` | 手工 `StatusConfigView` 字面量 | +`max_workers_per_key: 4` |
| `autopilot-console.test.ts:494-500` | 默认等值 `max_parallel_keys: 2` | `8` + `max_workers_per_key: 4` |
| `autopilot-console.test.ts:841` | `saveConfig(..., max_parallel_keys: 1)` 期望拒绝 | `0`（1 已合法，负例下移） |
| `autopilot-console.test.ts:923/927` | `toHaveLength(20)` | `21` |
| `autopilot-console.test.ts:960` | `INT_RANGES` 全序表 14 项 | +`"max_workers_per_key"`（index 4，15 项） |
| `autopilot-console.test.ts:1273-1274/1295` | enable 物化 `max_parallel_keys: 2`、`toHaveLength(20)` | `8` + `max_workers_per_key: 4`、`21` |
| `autopilot-config-parity.test.ts:356/361` | `toBe(20)` | `toBe(21)` |
| `autopilot-config-sync.test.ts:42-43` | frozen `1e27f5…`/`73` | `f5b60e…`/`77` |
| `autopilot-config-sync.test.ts:11/15/172/176` | `20-key` / `21 registrations` | `21-key` / `22 registrations` |
| `mwgal-t20-config-parity.test.ts:142` | `py.keys).toHaveLength(20)` | `21` |
| `mwgal-t20-config-parity.test.ts:196` | `Object.keys(read.config)).toHaveLength(20)` | `21` |
| `mwgal-t20-config-parity.test.ts:209` | `merged_keys=20` | `merged_keys=21` |
| `mwgal-t20-config-parity.test.ts:218` | `Object.keys(written)).toHaveLength(20)` | `21` |
| `mwgal-t21-qg-fixes.test.ts:497` | `Object.keys(DEFAULT_CONFIG)).toHaveLength(20)` | `21`（test 名同步为 "one config key was added by MDC M-03"） |

### ⑥ 不得回归：验收命令原始输出

```
# packages/multi-workers
python -m pytest test_autopilot_config.py test_mwgal_t12_stage_close_auto.py test_mwgal_t15_reattest_confirm.py -q
65 passed in 3.72s
python -m pytest test_autopilot_config_parity.py test_autopilot_effective_config.py test_mw_autopilot_cli.py test_mwds_t14_producer_skew.py -q
96 passed in 4.06s
python -m pytest test_autopilot_readcap_injection.py -q
1 failed, 16 passed   # 仅 test_baseline_left_end_bound：外部 E2Feature baseline vs git HEAD dispatch.py，见残留
$env:PYTHONUTF8="1"; python -m pytest -q
4 failed, 2208 passed, 10 deselected   # 4 条全部与本卡写面无关，见残留

# packages/coding-agent
vitest --run autopilot-config-parity / autopilot-config-sync / autopilot-console
Test Files 3 passed (3) | Tests 44 passed (44)
vitest --run autopilot-monitor
Test Files 1 passed (1) | Tests 26 passed (26)
vitest --run mwgal-t20-config-parity / mwgal-t21-qg-fixes
Test Files 2 passed (2) | Tests 23 passed (23)
npx tsgo --noEmit
tsgo_exit=0
```

全量 `python -m pytest -q` 的 4 条失败（PYTHONUTF8=1 隔离后，与 HEAD 无关）：

1. `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` —— 比对 `H:\git\E2Feature\...\baseline_20260924\dispatch.head.py`（sha `219ed809…`）与 `git show HEAD:packages/multi-workers/autopilot/dispatch.py`（sha `960cceec…`）；本卡未触碰 `dispatch.py` 与该外部 baseline。
2. `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` —— 读取外部 `H:/git/E2Feature` 真实 key 的 L3 轮次（`latest report is not from the last round`），外部仓库状态。
3. / 4. `test_launcher.py::…test_bom_historical_books…`、`test_task_type_parity.py::test_bom_historical_books` —— 本仓缺 `.agenticdoc/mw-dispatch-reliability/workers/mw-dr-glm53/task.md`（`Test-Path` = False），与配置面无关。

（未设 `PYTHONUTF8` 时另有 6 条 gbk/编码相关失败：`test_mwds_t27`/`test_mwds_t29`/`test_worktree_e2e`/`test_tree_watch` 等；置 `PYTHONUTF8=1` 后全部转绿，属 Windows GBK 环境噪声。）

---

## 残留与未验证

- **未重建 dist bundle**：`packages/coding-agent/dist/.../status-model.js`、`monitor.js` 与 `packages/multi-workers/dist/extensions/agent-team-loop.js` 仍含旧值（`max_parallel_keys: 2`）。dist 不在本卡写入允许面（且 `npm run check` 被 P-017 禁止），需由 M-06/PM 收口时 `npm run build`/`mw build` 重建。
- **面板 `|F|` 是上界**：TS 不读 claim（`state.read_key_states`），`frontier_panel >= |F_conductor|`；同快照等式只在面板自身 |F| 上成立。若需严格单源，应走 design §4.3(5) 的 `beat.data` 单源导出，但那是 M-02 的 `conductor.py` 面。
- **`conductor.py` 过期文案未修**（M-02 唯一写者，禁改）：`:139` `Returns the complete 13-key view.`、`:3978` `13-key output is frozen …` 均已过期（早已 20 键，现 21 键）；只记录。
- **README / docs 未更新**（不在写入允许面）：`packages/multi-workers/README.md:225/312`、`docs/autopilot-observability-guide.md:23` 的默认值/键数文案仍为 2/20。
- **未跑 `npm run check`**（P-017 禁止）；未跑无文件参数的 vitest（P-032）。
- 语料新增一条 `range-max-parallel-below-floor`（0→reject）以在 floor=1 后保留"低于下限被拒"的负例；`range-max-parallel-low` 按卡面要求 payload 不动、期望 reject→accept。

## 上下文来源

- 卡：`.agenticdoc/mw-dynamic-concurrency/workers/mdc-m03-config-panel/task.md`、`.agenticdoc/mw-dynamic-concurrency/tasks/T-C-M03-config-panel.md`
- spec：`.agenticdoc/mw-dynamic-concurrency/spec.md` AC-004/005/006/007/012；design D-102；plan §2 M-03、§3.3/§3.4、§5
- 研究：`.agenticdoc/mw-dynamic-concurrency/evidence/research/design-cap-and-status-20261014.md` §1/§2/§4
- 目标：`.agenticdoc/goal.md`
- 实现锚点：`packages/multi-workers/autopilot/config.py:16/91/127`；`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:80/141/202`；`monitor.ts:241/511/891/946/1283`；`.../shared/worker-store.ts:65`（`workerBelongsToKey`）

## 改动清单

源/夹具：

- `packages/multi-workers/autopilot/config.py`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
- `packages/multi-workers/test/fixtures/autopilot-config-corpus.json`

计数锁同步（sweep 清单见证据 ⑤）：

- `packages/multi-workers/test_autopilot_config.py`
- `packages/multi-workers/test_autopilot_config_parity.py`
- `packages/multi-workers/test_autopilot_effective_config.py`
- `packages/multi-workers/test_mwds_t14_producer_skew.py`
- `packages/multi-workers/test_mw_autopilot_cli.py`
- `packages/multi-workers/test_mwgal_t12_stage_close_auto.py`
- `packages/multi-workers/test_mwgal_t15_reattest_confirm.py`
- `packages/multi-workers/test_autopilot_readcap_injection.py`
- `packages/coding-agent/test/suite/autopilot-console.test.ts`
- `packages/coding-agent/test/suite/autopilot-config-parity.test.ts`
- `packages/coding-agent/test/suite/autopilot-config-sync.test.ts`
- `packages/coding-agent/test/suite/mwgal-t20-config-parity.test.ts`
- `packages/coding-agent/test/suite/mwgal-t21-qg-fixes.test.ts`

本证据文件：`.agenticdoc/mw-dynamic-concurrency/evidence/M-03-config-panel.md`

---

## 附：面板/配置复跑脚本（ad-hoc，OS temp）

`m03-panel-evidence.mjs`（面板三量，`node C:/.../m03-panel-evidence.mjs`）：

```js
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";
const { readMonitorState, renderMonitorLines } = await import(
	pathToFileURL("H:/git/Multi-Workers/packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts").href,
);
function mkproject(mpk) {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "m03-panel-"));
	const ap = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(ap, { recursive: true });
	fs.writeFileSync(path.join(ap, "config.json"), `${JSON.stringify({ enabled: true, paused: false, poll_interval_sec: 4, max_parallel_keys: mpk, max_workers_per_key: 1 }, null, 2)}\n`, "utf8");
	fs.writeFileSync(path.join(ap, "_roadmap.md"), ["# Roadmap", "> status: running", "> key-status: kA=running, kB=running, kC=running, kD=done", "### Keys", "| key | role | depends_on |", "|-----|------|-----------|", "| kA | w | - |", "| kB | w | - |", "| kC | w | kB |", "| kD | w | - |", ""].join("\n"), "utf8");
	fs.writeFileSync(path.join(root, ".agenticdoc", "_index.parallel"), ["kA", "kB", "kC", "kD"].map((k) => `| ${k} | active | EXECUTE | free | - | d | 2026-10-14T00:00:00 |`).join("\n") + "\n", "utf8");
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.writeFileSync(path.join(agenticdoc, "_workers.parallel"), [["ap-kA", "running", "kA", "conductor"], ["ap-kB", "pending", "kB", "conductor"], ["ap-kC", "running", "kC", "manual"], ["ap-kD", "done", "kD", "conductor"]].map(([k, st, owner, origin]) => `${k} | ${st} | pi | timi | ${path.join(agenticdoc, owner, "workers", k, "task.md")} | 2026-10-14T00:00:00 | 2026-10-14T00:00:00 |  | ${origin}`).join("\n") + "\n", "utf8");
	return root;
}
for (const mpk of [8, 1]) {
	const root = mkproject(mpk);
	const snap = readMonitorState(root, Date.parse("2026-10-14T00:00:10+00:00"));
	const a = snap.autopilot;
	console.log(`[cap${mpk}] cap=${a.slotsCap} eff=${a.slotsEffective} frontier=${a.frontierSize} used=${a.slotsUsed} slotsMax=${a.slotsMax}`);
	console.log(`[cap${mpk}] recompute eff == min(cap, |F|) -> ${a.slotsEffective} == ${Math.min(a.slotsCap, a.frontierSize)} : ${a.slotsEffective === Math.min(a.slotsCap, a.frontierSize)}`);
	for (const l of renderMonitorLines(snap).filter((l) => l.startsWith("autopilot:"))) console.log(`[cap${mpk}] RENDER: ${l}`);
}
```

`m03-config-evidence.py`（默认/floor/回退，`python C:/.../m03-config-evidence.py`）：

```python
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(".").resolve()))
from autopilot import config as cfg
from autopilot import effective_config as ec
root = pathlib.Path(tempfile.mkdtemp(prefix="m03-config-"))
for value in (0, 1, 2, 8):
    try: cfg.validate_config({"max_parallel_keys": value}); print(f"max_parallel_keys={value} -> accept")
    except cfg.ConfigError as exc: print(f"max_parallel_keys={value} -> reject ({exc})")
for value in (0, 1, 4):
    try: cfg.validate_config({"max_workers_per_key": value}); print(f"max_workers_per_key={value} -> accept")
    except cfg.ConfigError as exc: print(f"max_workers_per_key={value} -> reject ({exc})")
a = cfg.default_config(); a["max_parallel_keys"] = 8; cfg.save_config(root, a)
first = cfg.cached_load(root)["max_parallel_keys"]
a["max_parallel_keys"] = 1; cfg.save_config(root, a)
second = cfg.cached_load(root)["max_parallel_keys"]
print(f"no_restart_reload first={first} second={second} (no invalidate_cache call)")
legacy = {k: v for k, v in cfg.default_config().items() if k != "max_workers_per_key"}
legacy["max_parallel_keys"] = 2
cfg.config_path(root).write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8", newline="\n")
eff = ec.load_effective(root)
print("legacy_materialized_no_new_key valid=true has_new_key_in_raw=" + str("max_workers_per_key" in cfg.load_config(root)) + f" effective_max_workers_per_key={eff.values['max_workers_per_key']} effective_keys={len(eff.values)}")
```
