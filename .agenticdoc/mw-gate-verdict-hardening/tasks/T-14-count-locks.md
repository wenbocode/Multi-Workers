# T-14: 计数锁与冻结语料重冻（跨语言 + 跨测试的收口卡）

- 波次: **3** · 依赖: T-02, T-03, T-05, T-10
- 写面（独占）:
  - `packages/multi-workers/test_autopilot_auto_decision.py`（`:301` / `:333` / `:338` 三处）
  - `packages/multi-workers/test_autopilot_timeline.py`（`:48/:53/:54` 集合计数）
  - `packages/multi-workers/test_autopilot_config_parity.py` + 冻结语料 `autopilot-config-corpus.json`
  - `packages/coding-agent/test/suite/autopilot-event-parity.test.ts`
  - `packages/coding-agent/test/suite/autopilot-console.test.ts`（`:374-378` 精确 `toEqual`）
- AC: AC-014 · VC: VC-019
- 基线: `10446aefb`

## 目标

把四条**跨语言 / 跨文件**的计数锁一次性刷新到新语义，避免留给下一个 key 当"陈旧断言"引爆（P-021；上一 key 的 T-11/T-15/T-17 就是这么欠债的）。

## 交付物

| 锁 | 旧 → 新 | 文件:行 |
|---|---|---|
| `reason_code` 数量 | 12 → **14** | `test_autopilot_auto_decision.py:301`（`len(STALL_REASON_CODES)==12`）、`:333`（`len(calls)==12`）、`:338`（集合相等） |
| timeline 事件集合 | 23 → **26** | `test_autopilot_timeline.py:48/53/54` |
| 配置键数 | 14 → **17**（T-18 已落地；T-02 三键到齐后 → **20**）| `test_autopilot_config_parity.py` + 冻结语料 |
| TS 事件集合 | 集合相等断言同步 | `autopilot-event-parity.test.ts` |
| TS gates 行形状 | `toEqual` 期望值同步 | `autopilot-console.test.ts:374-378` |

- 冻结语料：**新增** 3 条单键 accept 例（每键一条）+ 3 条越界 reject 例；**不得**删除或替换既有用例。
- 重冻流程：先逐例 diff 确认语义（P-021），再重算 sha 并写入语料。
- 若 `test_autopilot_timeline.py` 的计数窗口已被改成动态（读 `EVENT_TYPES`），改为断言**集合相等**而不是硬数字——并在回执里说明为什么这是更强的判据。

## 契约（不得重定义）

- 只动**锁与语料**，不动任何生产代码（生产代码归 T-01…T-13）。
- 不得为了让测试变绿而放宽断言（P-016：非空洞对照必须仍然成立）。
- 语料 sha 重冻必须两侧同时（Python 语料 + TS parity 测试），不得只改一侧。

## 实现进度（T-18 提前完成了一半，2026-10-10）

T-18 的 G5/G6 三键（`launcher_max_workers` / `dispatch_max_per_scan` / `queue_alarm_delta`）已把**配置键锁推到 17**，并完成本卡要求的语料重冻流程：

- 语料 55 → **64** 例（+3 单键 accept + 6 范围 reject），sha256 双侧同时写入（`test_autopilot_config_parity.py::FROZEN_CORPUS_SHA256`、`autopilot-config-sync.test.ts::FROZEN_CORPUS_SHA256`）。
- 计数/顺序锁同步位置：`test_autopilot_config.py:112-119`、`test_autopilot_effective_config.py:70-73/204-207`、`test_autopilot_gate_schema_v2.py:349`、`test_mw_autopilot_cli.py:122`、`autopilot-console.test.ts:869-900/1212`、`autopilot-config-parity.test.ts:356/361`。
- 旁路冻结哈希：`test_autopilot_readcap_injection.py::_GOLDEN_REGRESSION_SHA256` 的 `test_autopilot_config.py` 项已** deliberate re-freeze**（注释已记录原因），否则 T-18 会把它误报为回归。

**剩余给本卡**：`reason_code` 12 → 14、timeline 事件集合 23 → 26、TS 事件集合、TS gates 行形状，以及 **T-02 三键到齐后的 17 → 20**。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py test_autopilot_timeline.py test_autopilot_config_parity.py -q`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts test/suite/autopilot-console.test.ts`

## 非空洞对照（必须附在回执里）

- 把 `STALL_REASON_CODES` 临时改回 12 项 ⇒ 锁必须转红（证明锁真的在读生产常量，而不是自己抄了一份）。
- 摘掉语料里的一条单键 accept 例 ⇒ parity 用例必须转红。

## 风险与注意

- 本卡是全 key **最后一张改测试的卡**：开工前确认 T-01…T-13 都已落，否则会反复重冻。
- 若 `autopilot-config-corpus.json` 有 golden sha 之外的字段（如排序后的键列表），必须一并同步并在回执里列出 diff。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-14-count-locks/report.md`（含 `[VERIFY]` 命令原文与输出、语料 diff、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。


## PM 追记（2026-10-10 19:00，T-23 落地后必须一并刷新）

T-23（AC-025，G3 锚点建立）新增了一个 timeline 事件名 **`contract-frozen`**（Python `timeline.py::EVENT_TYPES` 已加）。因此本卡的计数锁必须按**新数字**刷新，两侧同时：

| 锁 | 就绪前 | **就绪后（本卡）** | 位置 |
|---|---|---|---|
| timeline 事件集合 | 23 → 26 | **27**（+`contract-frozen`）| `test_autopilot_timeline.py:48/53/54`（建议改为对 `EVENT_TYPES` 的集合相等断言）|
| TS 事件集合 | 集合相等 | **27**，`status-model.ts EVENT_TYPES` += `contract-frozen` | `autopilot-event-parity.test.ts`（两侧集合相等）|
| `reason_code` 数量 | 12 | **14**（T-01/T-10 已落，本卡只改锁）| `test_autopilot_auto_decision.py:301/333/338` |
| 配置键数 | 17 | **20** | `test_autopilot_config_parity.py` + 冻结语料 + `autopilot-config-sync.test.ts` |

- **新增事件名的 TS 半边归你**（T-23 不碰 `status-model.ts`，以免与 T-12 的 `authorizes` 镜像同文件冲突）。
- 若 `test_autopilot_timeline.py` 已改成动态读 `EVENT_TYPES`，则本卡只需保证**两侧集合相等**且 TS 侧含 `contract-frozen`，并在回执里说明“集合相等比硬数字更强”的理由。


## 实施记录（PM 核销 2026-10-10 19:12）

| 锁 | 旧 → 新 | 落点（实测行号） |
|---|---|---|
| `reason_code` | 12 → **14** | `test_autopilot_auto_decision.py:301`（`len(STALL_REASON_CODES)`）、`:333`（`len(calls)`）；`:338` 集合相等在计数修正后自洽（调用点 14 = 源码 14）；陈旧测试名/注释里的 `twelve` 字样已更名 |
| timeline 事件集合 | 23 → **27** | `test_autopilot_timeline.py`：硬数字改为**对照 `LOCKED_EVENT_TYPES`（27 名字面量）的集合相等** + 派生 seq 区间；PM 认可其强于硬数字（增删都逼人改字面量）|
| 配置键数 | 17 → **20** | `test_autopilot_config_parity.py:60-61`（sha `4921…`→`1e27…`、例数 64→73）+ `:422-426` 计数/注释；`autopilot-config-sync.test.ts` sha/计数；`autopilot-config-parity.test.ts` 17→20（×2）|
| 冻结语料 | 64 → **73** 例 | `autopilot-config-corpus.json` **只追加**：3 条单键 accept（T-02 三键）+ 6 条越界 reject（两界/键）|
| TS 事件集合 | +`contract-frozen` | `status-model.ts EVENT_TYPES`（T-23 欠的 TS 半边）；`autopilot-event-parity.test.ts` 本就是集合相等 ⇒ 无数字改动，`count=27` 绿 |
| TS gates 行形状 | 无需改 | `autopilot-console.test.ts:374-378` 经核实已是 T-05/T-12 后的 `{id,kind,status,ageMs}`（`authorizes` 不进 `GateView`）|

- `test_autopilot_readcap_injection.py`：**无需**再重冻（`test_autopilot_config.py` 未被本卡改动，T-02 的 golden 保持）。
- PM 亲跑：Python 三文件 **47 passed**（开工前 4 红全消）；TS 四文件 **47 passed**；`[VERIFY] P6: partial_single_key=35 raw_view_partial=true effective_view_20=true fields_covered=20`。
- 四组非空洞对照 A~D（`STALL_REASON_CODES` 回 12 / 摘一条语料 accept 例 / 摘 `timeline.EVENT_TYPES` 的 `contract-frozen` / 摘 TS 侧同名）均转红并逐字节还原。
- 回执：`evidence/runs/t-14-count-locks-report.md`。
