# T10 R2 阶段A — 回归测试与 PM 离线执行脚本准备（局部完成，待 PM 真红测）

## 结论

局部完成：本 stage 只做了两件事 —— (1) 在受影响最集中的既有测试文件
`test_decision_context_lifecycle.py` 尾部**纯追加** 11 个测试函数（14 个 item：预计 8 红 / 6 绿），
覆盖 S1/S3/S5/S7/S4 的规格事实并保留 S2/S6/S8 的未决边界，另加 S9 常量同源一致性正控；
(2) 生成可由 PM 直接执行、自带子进程网络/子进程护栏与前后保护快照的
`rework-r2/test-preparation/run_pm_tests.py`（含 `sitecustomize.py`/`guard_preflight.py`/
`probe_imports.py`）。`test_decision_task_state.py` 未改动（该文件已覆盖 `same_snapshot` 的
null/`[]` 与顺序敏感正控，S7 的根因在 writer 的比较侧，不重复造）。

本 worker **没有执行**任何产品导入、pytest、runner、生成器、HTTP/CLI/service/model/node，
**没有实现或修改**三个 implementation 产品文件，**没有**写获批 OS 测试根或其兄弟目录，
也没有创建/复用任何 OS fixture 对象。所有 8 个预计红项都是**预期**，不是已观测的真实 red；
`116` 是历史局部绿，本 stage 不产生 PASS/QG/签收/receipt。T10 修复、semantic=true、整体完成
均**未**达成。

静态校验（`python -B`，纯 AST/文本，无产品 import）通过：旧 64 个 lifecycle 测试文件顶层函数
（其中 50 个 `test_`）与 24 个 task-state 顶层函数（其中 20 个 `test_`）的 AST 摘要、源码段、
assert 数量**逐一相等**；旧字节是新文件完整 head 前缀；estimator 对旧两文件复算 = **116**
（与历史 item 数一致），新两文件 = **130**（+14）；mirror 差异只有
`packages/multi-workers/test_decision_context_lifecycle.py` 一项，14 个受保护 pyc、744 个旧
evidence 文件、live 五文件全部未变。

**注意（勘误）**：`t10-handoff-audit-20261027.md` §3 写“原 37 个生命周期测试函数 / 22 个
task-state 测试函数”，本人按当前字节实测为 **50 / 20** 个 `test_` 函数（顶层函数总数
**64 / 24**，其余为 fixture/helper）。本报告一律用实测值：审计文本的 37/22 不是当前文件的
函数数，不能当作 item 锁；item 面以 `116 → 130`（估计）和收集列表为准。

## 证据

### 1. 本 worker 的真实 read 范围（到实际 EOF，非 snapshot 代读）

| 文件（canonical，相对 repo root） | 本人读取范围 | LF | bytes | sha256（本人实测） |
| --- | --- | --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py` | 1..1548（EOF） | 1548 | 60811 | `0c0f7fffb353cc829e054dfbeec409915cb4bebce11d998c5d810feb533dc8e4` |
| `.../decision_wire.py` | 1..2264（EOF） | 2264 | 79832 | `8863e534f0a74edec1fc0105c0619c9dd19c85a472b82db6d622c23a7f85a5e6` |
| `.../decision_task_state.py` | 1..82（EOF） | 82 | 3871 | `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d` |
| `.../test_decision_context_lifecycle.py` | 1..1401（EOF，改前） | 1401 | 50338 | `bdedfd4301fab76929beb0156f429f973fcb6404382b8893d2cbecbfaa711d1a` |
| `.../test_decision_task_state.py` | 1..278（EOF） | 278 | 15480 | `30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f` |

三个 implementation 文件只读，bytes/sha 与 `evidence/implementation/t10-r2-pre-dispatch-20261028/
check.json.five_products_before` 完全一致（含 LF 计数）；`decision_wire.py` 本人实测 **2264 LF /
79832 B**，与 precheck 一致（旧审计文本写 2263，是计数口径差异，不是字节漂移）。

采用的关联协议/已批合同（本次实际读到的范围）：
`tasks/isolated/T10-lifecycle-state.md`（全文，含 AC-004/012/014/049/050/051/052 摘录与本阶段
write_face/验收命令）、`tasks/isolated/T10-r2-test-preparation.md`（全文）、
`evidence/implementation/t05-t10-audit-disposition-20261028/report.md`（全文，§B 是本次
“先复现再定点”的处置边界、§D 是已获批目录范围）、
`evidence/implementation/t10-handoff-audit-20261027.md`（全文，S1..S9 静态预测与 §4 链核）、
`evidence/implementation/t10-r2-pre-dispatch-20261028/{approval.md,check.json,prepare.py}`（全文）、
`decision_points.py` 的 `REQUIRED_STATE_FIELDS:2037`、`state_field_issues:3467`、
`state_unknown_key_issues:3562`、`_missing_required:3802`、`resolve_entry_choices:3832`、
`entry_material_issues:3953`、`pm_candidate_issues`、`basis_catalog_issues:4104`、
`basis_selection_issues:4194`、`preparation_issues:4226`、`prepared_request_issues:4284`、
`ACTIVE_DP_IDS:666`/`ENTRY_CHOICES:706`/`ENTRY_ROLES:697`/`dp-auto:1147`；
`decision.py:140-250`（`REASON_CODES:158`、`_PREPARED_REASONS:176`、`_PREPARED_RESULT_FIELDS:182`、
`BASIS_QUESTION_ID:167`）；
`test_decision_context_readable_backend.py:1-300`（`_root`/`_meta`/`_store`/`_append_archive`/
`_hermetic`/`SECRET`）、`test_decision_context_readable_ui.py:1-95`（`_isolated_environment` autouse）。

### 2. S 项 → 本 stage 的处理（有规格回归 / 未决 / 证伪依据）

| ID | 本 stage 做了什么 | 规格依据与源码锚点 |
| --- | --- | --- |
| **S1** 拒绝后被吞 / 冲突不可见 | **红 2 项 + 绿 1 项**：`test_a_refused_request_does_not_swallow_the_later_real_choice`、`test_a_different_choice_for_the_same_request_stays_visible`、`test_an_identical_repeated_business_request_stays_idempotent` | AC-050“同 key/task/logical_id 及非递减观察时间可核”“不伪造执行”；writer 自称每个事实一条（`decision_lifecycle.py:879` `dedupe_event_id=True`），但 `record_request` 的 id 只由 `(logical_id, dp, parent_ref)` 决定（`:1374` `_stable_event_id("rq", …)`），拒绝行与真实业务决定共用同一 id |
| **S2** 同一 logical_id 挂不同 decision_id | **不加失败测试**（未决） | 已批合同只要求“同 key/task/logical_id”（AC-050）与 `_ledger_facts` 的单 creation fact（`:347-377`）；“一个 logical_id 只能有一个 decision_id、或改派需 supersedes”在已批卡/design 里**没有**确认。审计 §5 S2 本身写“需 PM 确认是否允许改派决策点”，故不写错误期望，报告为未知 |
| **S3** dp-auto 非法 choice 入账 | **红 2 item（1 函数 2 param）+ 绿 1 项**：param `no-handling-options`（material 缺 `handling_options`）与 `single-candidate-set`（候选集非法）；正控 `test_a_dp_auto_choice_inside_the_prepared_candidates_is_recorded` | AC-012“材料非法/无有效裁决时保持阻塞、默认放行 0”；`record_request` 只调 `preparation_issues`（`decision_lifecycle.py:534`），`basis_catalog_issues` 在 legal 为空集时跳过 applies_to（`decision_points.py:4184`），`entry_material_issues`（`:3953`）/`entry_choice_issues` 未被调用 |
| **S4** Windows 大小写/8.3 绕过 test-scope 安全门 | **红 2 item**（`.AgenticDoc` 的 wire sink 与 lifecycle sink）+ **绿 2 item 正控**（精确 `.agenticdoc` 已被拒）；**8.3 短名只记录未验，不构造** | 安全门谓词 `decision_wire.py:555-556`（`part == ".agenticdoc"` 大小写敏感）+ `:625` 只查 given/canonical；8.3 是否被 `os.path.realpath` 展开需在该 Windows/Python 上实证，本次不猜、不造探针 |
| **S5** executed/settled after 可倒序 | **红 1 项（含同测试内合法递增顺序正控）+ 绿 1 项**：`test_executed_and_settled_observations_stay_non_decreasing`、`test_a_failed_executed_round_is_never_recorded_as_executed` | AC-050“非递减观察时间可核”“未执行/失败不得伪造 executed”；`record_lifecycle` 只核 `meta.task_before` 与账本已存 before（`decision_lifecycle.py:1018`、`:1027`），而 terminal 会遍历已记录 after（`:1464-1470`） |
| **S6** 多终态 / 无单一终态不变量 | **不加失败测试**（未决） | “每 logical_id 至多一条终态”或“修订用显式 supersedes”在已批合同里未定义；审计 §5 S6 亦写“需明确…属 decision_lifecycle 面”。不新增未经确认的全局不变量 |
| **S7** 含密 before 的等值复述不可满足 | **红 1 项**：`test_a_secret_bearing_creation_before_can_be_repeated`（同时断言 null 与 `[]` 仍可区分、秘密不落盘） | AC-050“不以当前状态回填旧 before”的正面即“可复述已记录 before”；AC-051 null/`[]` 可分；`_check_before` 用**已脱敏**存储值对比调用方原文（`decision_lifecycle.py:395` `same_snapshot(stored, given)`），含密复述永远不等 |
| **S8** builder 不做 writer 级不变量 | **不加失败测试**（未决） | “唯一 production caller 是 writer”是纪律声明；给 builder 加形状断言或私有化 public builder 都是未确认契约（审计 §5 S8 明确列为“需 PM 另批”）。不删/不私有化既有 public builder |
| **S9** producer 冻结常量第二份副本 | **绿 1 项一致性自检**：`test_the_writer_consumes_the_producers_frozen_prepared_contract` | 审计 §5 S9 允许“T10 面内只能加一致性自检测试”：`set(lifecycle.REQUEST_RESULT_FIELDS) ⊆ set(decision._PREPARED_RESULT_FIELDS)`、`REQUEST_REASONS == decision._PREPARED_REASONS`、`BASIS_SOURCE == decision_points.BASIS_SOURCE`、`resolve_entry_choices("dp-auto")` 无静态菜单且随 material 派生 |

新增 14 item 的分布：红 8（S1×2、S3×2、S5×1、S7×1、S4×2）/ 绿 6（S1 幂等、S3 正控、S5 失败回合、
S4 精确大小写正控×2、S9 常量）。S4 的红项带 `skipif(os.name != "nt")`（Windows 事实），在
Windows 上会真的执行；这不是对既有测试的 skip/xfail（新增 `skip_markers` 全表只有这一条，
且只落在新增函数上）。

### 3. 旧函数/断言保护与 item 面（工具结果，非自述）

`checks/verify_tests.result.json`（`python -B checks/verify_tests.py`，rc=0，`ok=true`，
`python 3.14.3`，`dont_write_bytecode=true`）：

| 文件 | 旧顶层函数 | 新顶层函数 | 旧函数 AST+源码+assert 全同 | 旧 item 估计 | 新 item 估计 | 行数 | bytes | sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `test_decision_context_lifecycle.py` | 64（50 个 `test_`） | 79（61 个 `test_`） | 是 | 91 | 105 | 1401 → 1815 | 65105 | `1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9` |
| `test_decision_task_state.py` | 24（20 个 `test_`） | 24 | 是（字节完全未变） | 25 | 25 | 278 | 15480 | `30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f` |

同一结果文件里：`mirror.before_files=1891 / current=1891`，diff = `changed:["packages/multi-workers/
test_decision_context_lifecycle.py"]`，`added=[]`，`removed=[]`；`pyc 14 == 14 unchanged`；
`old_evidence before=744 / current=744 / diff 空`；live 五文件 = check.json 的 `live_sha256`；
三个 implementation 文件 = 冻结 SHA。estimator 对旧两文件复算 91+25=**116**（与历史局部位一致，
说明估计器可信），新 91+25 → **105+25=130**。

行号变化原因唯一且明确：在 import 块插入 `import decision` / `import decision_points` 两行
（S9 一致性测试需要），其后所有行 +2；除该 2 行与 EOF 追加块外，旧字节是新文件完整 head 前缀
（`append-bytes=14703`，统一 diff 428 行，见 `diff/test_decision_context_lifecycle.py.diff`；
task-state 的 diff 为 0 字节）。旧断言强度未降：`assertions` 计数逐个函数相等。

### 4. 本 stage 交付的工具（PM 可直接运行，本人未执行）

| 文件（canonical） | sha256 / bytes | 作用 |
| --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/run_pm_tests.py` | `7513cbec9075b030a980576f1d35faf3201ee773ad228da7ea46509a4ce83d4d` / 31847 B / 729 LF | 唯一入口：独占新建 `<fixture-root>/<label>` 与 `runs/<label>`，最小 env 白名单，5 个受控子进程（guard 自控 → import 溯源 → 收集清单 → 两文件 pytest → 可选 `--focus`），raw log 先落盘再解析，前后保护快照 + sentinel 审计，写 `report.json`，rc = pytest rc（已知失败绝不 rc0） |
| `.../test-preparation/sitecustomize.py` | `1f3bbcc91a9c4c1e298a27ce2ccaacaf227af550c0a77c9e8dfb8ba130b21a2f` / 7444 B / 232 LF | 每个 Python 子进程经受控 `PYTHONPATH` 自动加载：**先写 sentinel 再装护栏**；patch `socket.socket.connect/connect_ex/bind/sendto(/sendmsg)` 与 `create_connection`/`getaddrinfo`/`gethostbyname*`（子类如 `ssl.SSLSocket` 继承）；只允许 Python 家族子进程，`os.system/popen/exec*/spawn*/startfile` 硬拒；记录凭据形状 env **键名** |
| `.../test-preparation/guard_preflight.py` | `6c4da5e7030e3697c39a20180bbec017f22a02151bd325316c7826912cf9633b` / 4722 B / 128 LF | 护栏自控（在**子进程内部**）：DNS/TCP/UDP/非 Python 子进程 4 个负控 + Python 孙进程继承正控 + 文件 IO 正控 + 凭据 env 必须为空；未装护栏时**不尝试任何真实外连**，直接失败 |
| `.../test-preparation/probe_imports.py` | `cac791a30affbd04746df9e0e4a18c20492020ac5f656aad30042cd710c26ee6` / 2922 B / 90 LF | 真实解释器报告 9 个产品模块的 `__file__`/`__cached__`/sha256 与两个 test 模块的 `find_spec.origin`（不执行 test 模块）；runner 逐项核“在隔离树内、不是 live、sha = 当前隔离字节” |
| `.../test-preparation/checks/verify_tests.py` + `verify_tests.result.json` | 见文件头字节；结果 rc=0 | 本人用过的纯 AST/文本校验器（旧函数保护、head 前缀、item 估计、mirror/pyc/旧 evidence/live 差异、脚本语法与常量一致性）；PM 可复跑同一证据 |
| `.../test-preparation/before-bytes/…`、`after-bytes/…`、`diff/…` | — | 本阶段两 test 的真实 before/after 字节与统一 diff |

runner 关键约束（对应卡 §5–§8）：label 目录用 `os.mkdir` **独占新建**，已存在即 rc=3 拒绝，
从不 `rmtree`/`remove`/`unlink`/`rmdir`（AST 审计已确认无这些 token、无 `shell=True`）；
child env 完全从零构造（HOME/USERPROFILE、TEMP/TMP、`PYTHONPYCACHEPREFIX`、`PYTHONDONTWRITEBYTECODE=1`、
`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`PYTHONPATH=<本目录>`、
`SYSTEMROOT/WINDIR/PATH/PATHEXT/COMSPEC` 仅在父进程存在时透传），不继承任何 provider/worker/
`PI_*`/项目/credential 变量，只打印**键名**；`--basetemp` 在 `<label>/pytest-basetemp`；
`-B` + `-p no:cacheprovider` 全程。

`report.json` 会留下：完整 argv/cwd/rc、env 键名、5 个命令的 raw stdout/stderr/rc/meta、
`collection.node-ids.txt`（完整收集清单）、`pytest.summary.json`、`guard-preflight.json`、
`imports.json`、`guard-sentinel.jsonl`（每 pid 的 import/guard-installed/network-denied/
subprocess-denied）、`before.json`/`mirror.before.json`/`old-evidence.before.json`、
`protection`（mirror/pyc/旧 evidence/live/products 前后差异）、`expected_red.{observed,missing,
unexpected_failures}`、`problems`。任一保护树在运行中变化 → `harness-failed` + rc=2，不会变绿。

## 改动清单

| 文件 | 改动 |
| --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_lifecycle.py` | +2 顶层 import（`decision`、`decision_points`）；EOF 追加 1 个说明块 + 4 个 helper + 11 个测试函数（14 item）。1401→1815 LF，50338→65105 B，sha `bdedfd43…11d1a`→`1bca28c5…6ae9`；旧 64 顶层函数（含 50 个 `test_`）AST/源码/assert 全同；旧 item 91 → 105 |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_task_state.py` | **未改动**（278 LF / 15480 B / sha 不变）。理由：`same_snapshot` 的 null/`[]`、顺序敏感与“来路不同即不等”已有既有正控；S7 根因在 writer 比较侧，重复造测试只增面积 |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/run_pm_tests.py` | 新增（PM 唯一入口，见上表） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/sitecustomize.py` | 新增（子进程护栏） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/guard_preflight.py` | 新增（护栏正负自控） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/probe_imports.py` | 新增（import 溯源） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/checks/verify_tests.py` | 新增（本人纯 AST/文本校验器） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/checks/verify_tests.result.json` | 新增（本次校验结果，ok=true，problems=[]） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/checks/last-run.stdout.json` | 新增（上面校验器最后一次运行的原始 stdout，rc=0） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/{before-bytes,after-bytes}/packages/multi-workers/*.py` | 新增（两 test 的真实 before/after 字节） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/diff/*.diff` | 新增（lifecycle 428 行真实 diff；task-state 0 字节） |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/report.md` | 新增（本文件） |

未写：三个 implementation 产品、任何其他 test、旧 evidence（744 文件零变化）、DAG/state/卡、
live 全树（五文件 sha 仍为 before）、14 个 pyc、四旧/八新 cases、`decide_registry.json`/dashboard
三件、TS registry（均在 mirror 快照内零变化）、获批 OS 根及其兄弟目录。

## 残留与未验证

1. **没有真实 red / green**。新增 14 item 中 8 个是**预期**红（S1×2、S3×2、S5×1、S7×1、S4×2）、
   6 个是预期绿；本 worker 未运行 pytest，未导入产品，未执行 runner。真实 red 只能由 PM 在获批
   PM 子面执行后产生；预计结果形态是 `8 failed, 122 passed`、收集 **130**（估计），失败集合应等于
   `run_pm_tests.py::EXPECTED_RED_NODE_IDS`。若实际不同（例如绿项变红、或多于 130 / 少于 116），
   先按 `report.json.problems` / 原始 stdout 判定“环境 or 测试 or 产品”，不得把 rc 改写。
2. **S3 修复的相容性风险（给产品 writer 与 PM）**：现有 `_material()`（dp-pm-steer，只有
   `task_goal/task_requirements/task_deliverables`，缺 `pm_decision_background`）在“无条件调用
   `entry_material_issues`”的修复下会让既有十余个 request 测试变红。可行方向二选一：(a) 在
   dynamic-candidates 的 basis 复核里要求 `legal` 非空/候选集合法（本 stage 的 param
   `single-candidate-set` 也要求覆盖非法候选集，故仅“legal 非空”不够），或 (b) 全面接入
   `entry_material_issues` 并同步补齐既有 fixture 的 `dp-pm-steer` 材料——(b) 属修改既有测试数据，
   需 PM 明确并保留原断言强度。本 stage 只写正控（dp-auto 完整合法材料可入账），不预设修法。
3. **S4 的 8.3 短名未构造、未验证**：`realpath` 在该 Windows/Python 上是否展开 `AGENTI~1` 属实证
   问题；没有合法方式在 fixture 里“猜”短名且不制造活路径探针，故只记未知。大小写变体测试在
   Windows 上会执行，非 Windows 上 skip（标记只在新增函数上，不弱化既有测试）。
4. **S2/S6/S8 仍未决**：按卡要求不新增未经确认的“decision_id 全局唯一/单终态/私有化 builder”契约，
   也没有写会失败的错误期望。它们仍是“需要 PM/design 决定是否成为契约”的开放项，不是本 stage
   的缺陷结论。S9 只落实了同源自检（pass），不改 `decision.py` 面。
5. **guard 的证明上限**：`guard_preflight` 证明的是“护栏在该子进程内已安装并拒绝了 DNS/TCP/UDP/
   非 Python 子进程、Python 孙进程继承了护栏、凭据形状 env 为空”，**不是**抓包证明“整机瞬态绝无
   外连”；没有 packet capture 就不说“绝对未外连”。若某个既有 item 在最小 env/护栏下失败而基线
   绿，应作为环境发现单独报告，不能直接当产品红。
6. **本阶段一处过程偏差（如实披露）**：本人复核 `checks/verify_tests.py` 退出码时，曾把其 stdout
   重定向到机器 `%TEMP%` 下的一个临时文件并立即删除（仅为读 rc，未触碰任何 key/product/旧
   evidence/获批 OS fixture 对象，也未在获批 OS 根内留下任何对象）。此后所有输出都只写本 key
   evidence 面。原 T10 早期 OS 写（4 个 production 账本、40 setup 日志丢失、1 pyc 漂移）仍未被
   追认，本 stage 不清理、不复原、不重取基线。
7. **PM 的下一步（唯一 argv，原样可执行）**：

   ```bash
   cd H:/git/Multi-Workers
   python -B .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/run_pm_tests.py \
     --fixture-root C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification \
     --label t10-r2-red-<UTCyyyyMMddTHHMMSSZ>
   ```

   `fixture-root` 目前不存在（获批 OS 根存在且为空），runner 会以 `os.mkdir` 独占新建并记录
   `fixture_root_created=true`；`<label>` 目录与 `runs/<label>` 必须都不存在（已存在 → rc=3，
   不重用）。runner 内部实际执行的就是原合同命令
   （cwd=`…/implementation-worktree/packages/multi-workers`）：
   `python -B -m pytest -p no:cacheprovider -q --basetemp <fixture-root>/<label>/pytest-basetemp
   test_decision_context_lifecycle.py test_decision_task_state.py`。
   预期 rc=`1`（8 红），收集 130（≥116 且旧 50+20 个 `test_` 函数全部在收集列表内）。
   加固跑（可选，附加证据，不改主 rc 语义）：同 argv 追加 `--focus`，只跑新增 14 item；
   单项复查可直接用 `python -B -m pytest -p no:cacheprovider -q
   test_decision_context_lifecycle.py::<node id>`（node id 见 `EXPECTED_RED_NODE_IDS`）。
   下一条件：PM 先在本 sub-面跑出真实 red 并吸收 `report.json`，再由原产品 writer 按 S1/S3/S4/S5/S7
   的最小修复落地；修复后必须以**新 label** 重跑同一 runner（或跑原两文件合同）确认 8 红转绿、
   6 正控与既有 116 不变，且 mirror 仍只有两 test 的合法差异。
8. **原全 suite 合同仍在**：本 stage 不删原验收、不少收集；原卡“两文件 pytest”“生成器 `--check`”
   “全项目 `npm run check` 由 T32 串行保护”均原样保留，未执行。

## 上下文来源

- `.agenticdoc/goal.md:5`（项目目标）。
- `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md`（原卡全文：write_face、
  AC-004/012/014/049/050/051/052 摘录、VC、验收命令、隔离 fixture 约束）。
- `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-r2-test-preparation.md`（本阶段卡全文）。
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t05-t10-audit-disposition-20261028/report.md`
  （§B 有界修复处置、§C 过强结论不采纳、§D 目录授权边界）。
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-handoff-audit-20261027.md`
  （S1..S9 静态预测与 §4 链核；其“37/22 函数”与实测 50/20 不符，已在结论中勘误）。
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-pre-dispatch-20261028/`
  （`approval.md`、`check.json`、`prepare.py`、`before-bytes/`、`old-functions-before.json`、
  `mirror-before.json`、`pyc-before.json`、`products-before.json`、`history-before.json`、
  `dispatch-refusal.md`）。
- 当前五文件全文（本人读到 EOF）：`decision_lifecycle.py`、`decision_wire.py`、
  `decision_task_state.py`、`test_decision_context_lifecycle.py`、`test_decision_task_state.py`。
- 关联只读范围：`decision_points.py`（ACTIVE_DP_IDS/ENTRY_*/REQUIRED_STATE_FIELDS/
  resolve_entry_choices/entry_material_issues/pm_candidate_issues/basis_catalog_issues/
  basis_selection_issues/preparation_issues）、`decision.py`（REASON_CODES/_PREPARED_REASONS/
  _PREPARED_RESULT_FIELDS）、`test_decision_context_readable_backend.py`（fixture helpers）、
  `test_decision_context_readable_ui.py`（`_isolated_environment`）、`test_decision_monitor.py`
  （模块级无副作用确认）。
- 本 stage 工具输出：`checks/verify_tests.result.json`（ok=true、problems=[]、item 116→130、
  mirror/pyc/旧 evidence/live 差异如上）。
