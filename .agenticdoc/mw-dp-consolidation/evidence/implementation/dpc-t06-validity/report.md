# T06 (dpc-t06-validity) — implementation report

Card: `.agenticdoc/mw-dp-consolidation/tasks/isolated/T06-validity.md`
(11768 B, SHA256 `1a81029454f59cf2e69c32643f30735efa0827c482f382ca8879c02ef37df15c`,
0 CRLF / 108 LF, no BOM; equals the dispatch envelope `card_sha256`).
Dispatch envelope `workers/dpc-t06-validity/task.md` 13999 B,
SHA256 `eb6c3f5404071fbc56da87636e58b7e2549526a3d6e541af5a53e7224f41fc9b`
(0 CRLF / 128 LF), read fully to EOF.
All values below are from `baseline/before.json`, `write-scope.json` and the
red/green logs in this directory.

## 结论

- 状态：**代码完成，局部（纯判断）验证通过**；**不是** L2、不是真实并发/锁/效果对账通过，也不是 S2/全 VC/QG/签收/运行切换通过。
- 唯一产品改动：新增 `decision_validity.py`（只读事项/实质版本/授权/证据/claim/重放纯判断）与 assigned 测试 `test_dp_consolidation_concurrency.py`；assigned 命令 `python -m pytest -p no:cacheprovider -q test_dp_consolidation_concurrency.py` 在隔离副本内 **65 passed / rc=0**（两次重跑一致）。
- 红→绿：模块缺失 red rc=2；行为 red（stub）**63 failed / 1 passed** rc=1；实现后 64→65 passed rc=0。中途 2 次失败均为自身测试/实现缺口（set 未规范化、测试把有序 list 当 `$set`），已修并留证。
- 与 AC-011/019/025/027/028/029/039/052 对应的纯判断均有正/负例；`agent-report`/`editable`/token 不构成授权，prose 差异=unknown fail-closed，整文件 hash 变化不触发重复审批。

## 证据

### 1. before（真实不存在，未伪造旧 before）

`baseline/before.json`：两产品文件 `mirror_exists=false`、`live_exists=false`、`baseline_existed=false`；与 `isolation-baseline-20261026/approved-file-baselines.json` 的 `existed:false` 一致。捕获时副本 **1864** 个文件。
单 writer 核对：`decision_validity.py` 仅 T06；`test_dp_consolidation_concurrency.py` 同属 T06/T20/T31（T20/T31 均 `not-queued`，stage 4/6，后续接管须依赖本卡 hash）。

### 2. 验收命令与 rc（隔离 env，副本绑定）

runner：`run_pytest.py`（cwd=副本 `packages/multi-workers`；最小 env + 独立 HOME/USERPROFILE/TEMP/TMP；`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`；`PYTHONUTF8=1`）。probe 记录 `module_file`/`test_file` 均位于 `implementation-worktree`。

| 阶段 | rc | 观测 | 日志 |
|---|---|---|---|
| red-01 module missing | 2 | ImportError: No module named 'decision_validity' | `red-01-module-missing.log` |
| red-02 / red-03 stub | 1 | 63 failed, 1 passed（每个判断 NotImplementedError） | `red-02-facing-behaviours.log`、`red-03-stub-after-test-fix.log` |
| green-01 | 1 | 62 passed, 2 failed（`set` kind 未去重排序；自身实现缺口） | `green-01-first-impl.log` |
| green-02 | 1 | 63 passed, 1 failed（测试用有序 list 表达顺序无关 scope） | `green-02-second-impl.log` |
| green-03 | 0 | 64 passed | `green-03-third-impl.log` |
| **green-06 / 07 final + rerun** | **0** | **65 passed / 65 passed** | `green-06-final.log`、`green-07-final-rerun.log` |
| green-09 verbose | 0 | 65 个测试逐条 PASSED | `green-09-verbose.log` |

未运行：`npm run check`（T32 串行保护）、TS build/install、真实 provider、真服务探针、T03/T04/T05 生成器（本卡不需要）。

### 3. 断言与 VC 映射

`assertions.json`：8 个 VC 各自的测试 node id + 源文件行号、可观测值、明确 limit；`not_verified` 单列。计数全部来自纯 verdict 字段（如 8 入口对同一 gate-action 事项仅 1 个 valid owner、route releases=0、重放 additional_approvals=0、applied 动作不重复、prose 差异 unknown、legacy/disable/scope 扩张被拒），**不冒充真实并发/效果对账**。

### 4. 纯函数边界（静态断言）

`test_module_imports_only_stdlib_and_never_writes`：模块 import 仅 `__future__/hashlib/json/posixpath/re/collections/dataclasses/types/typing`；无 `open/exec/eval/compile`、无 `write_text/write_bytes/unlink/mkdir`，无 `write_grant/grant`。不 import `decision*`/`mw*`/`autopilot`（T07/T08 正在写这些文件，未形成读写依赖）。`test_validity_is_deterministic_for_repeated_calls` 与 `test_history_objects_are_not_mutated_by_assessments` 证同参重复调用一致、输入 frozen 对象不被改写。

### 5. 写面/前后核对

`write-scope.json`：1864 → 1883。`own_changes` 仅两项；`other_task_changes` = T07 `decision_policy.py`、T08 `decision.py`/`decision_backends.py`/`test_dp_consolidation_materials.py`、T07 `test_dp_consolidation_recovery.py`（并发窗口，**不归本卡**）；`unexpected = []`。
`concurrent_bytecode` 14 个 `.pyc`（含 `decision*`、`mw_common`、`autopilot/*`），mtime 全部 **20:16:49**，落在本卡两次 pytest 之间（green-03 20:16:16 / green-04 20:17:03）且**不含** `decision_validity*.pyc` 或本测试 pyc；本卡所有运行均以 `PYTHONDONTWRITEBYTECODE=1` 执行。未删除、未认领这些他人产物。

### 6. 终态字节

| 文件 | bytes | SHA256 | CRLF | LF | EOF |
|---|---|---|---|---|---|
| `packages/multi-workers/decision_validity.py` | 54353 | `64b9b9e1060aab955a4d0428385e2d450ae94826d1a548088c65f5874c049eb1` | 0 | 1652 | newline |
| `packages/multi-workers/test_dp_consolidation_concurrency.py` | 49049 | `c9dc013110de702f733b5ec292c1d62ccdaa93d7ffb4fa7ffcec9101c2a97349` | 0 | 1297 | newline |

两文件均已在写后完整读到实际 EOF。

## 残留与未验证

- 本卡只证**纯判断**：无真实 producer→writer→consumer→projection、无真实 O_CREAT|O_EXCL 锁/双调用者/崩溃窗口对账；VC-011/019/025/027/028/029/039/052 的 L2 证据仍待 T20/T31（同测试文件后续接管，须先声依赖+hash）。
- 25 个旧 ID 仅抽样 dp1/dp4/dp25（完整矩阵属 T03/VC-002）；`ACTIVE_ENTRIES`/`MATTER_OWNERS` 在本模块重复一份常量，T31 需与 T03 单源交叉核对，避免漂移。
- D012A「模型理由 vs PM 预备 basis」、失败 reason/probability/note 不得冒充理由：不在本模块判断面（属 T03/T08/T11），未在本次验证；未新增 API。
- 真实 authority/policy 文件、真实撤销来源、真实 budget usage 来源、dp-QG reopen / gate reject 的真实消费者：均未接线、未验证；本模块只落只读判断与「选择不产生效果」的显式声明。
- 真实 AC/VC 文件、goal、签收文件、gate/ledger 未读未写；未做任何 baseline 刷新、deploy/install/restart/commit/push；未跑 npm check。
- 并发 T07/T08 期间出现的 14 个 pyc 属他人运行产物（见 §5），未清理也未据以判断产品状态。
- 未执行真实 provider/HTTP/决策 CLI/服务探针；所有 env 均最小化并禁用 plugin/cache/pyc。

## 上下文来源

- 卡：`tasks/isolated/T06-validity.md`（SHA 见首段）；dispatch 全文 `workers/dpc-t06-validity/task.md`。
- 已批设计：`design.md` §4.1/§4.3/§4.5、§7（VC-011/019/025/027/028/029/039/052）、§8 映射；`design-write-scope.md`（decision_validity.py 职责：只读判断，不授予权限）；`evidence-requirement.md` AC-011/019/025/027/028/029/039/052 证据要求。
- 前置交接：`evidence/implementation/t03-r3-pm-handoff-20261026/report.md`、`evidence/implementation/t04-r2-pm-handoff-20261026/report.md`；`s2-frontier-pre-dispatch-20261026/check.json`（T06 `not-queued`、两文件 `exists:false`）与 `mirror-inventory.json`。
- 隔离边界：`implementation-isolation.md`、`evidence/implementation/isolation-approval-20261026.md`、`isolation-baseline-20261026/approved-file-baselines.json`。
- 本卡证据：`baseline/before.json`、`write-scope.json`、`assertions.json`、`red-0*.log`、`green-0*.log`、`capture_baseline.py`、`run_pytest.py`、`write_scope_check.py`。

## 改动清单

| 路径（key-relative） | 类型 | bytes / SHA256 |
|---|---|---|
| `implementation-worktree/packages/multi-workers/decision_validity.py` | 新增 | 54353 / `64b9b9e1…c049eb1` |
| `implementation-worktree/packages/multi-workers/test_dp_consolidation_concurrency.py` | 新增 | 49049 / `c9dc0131…1c2a97349` |
| `evidence/implementation/dpc-t06-validity/**` | 新增证据（baseline/write-scope/assertions/日志/runner） | 见各文件 |

未改动：主树同名文件、T03/T04 产物、T07/T08 产品与测试、其他 task/活对象、config/gate/ledger/policy/goal/spec、TS 源码与依赖/lock；未新增 symlink/junction/hardlink。
