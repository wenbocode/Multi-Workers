# T06 R2 — 签收finalize/key/ref、契约适用性、完整claim请求/任务绑定、未知effect失败关闭

## 结论

本层定点返工完成并已验证：九项PM报告边界在本层全部失败关闭，正向控制全部保持；唯一assigned测试 `test_dp_consolidation_concurrency.py` 由 65 passed 增至 73 passed（rc0，三次独立运行一致），七项缺口各有真实行为 red→green，第八个新增用例是正向控制（red前即绿）。

仅声明本层通过：不是生产授权、不是L2/QG/签收、不是真实并发/文件锁/CAS/消费者对账，也不代表原stage或全53AC/VC通过。原任务终态、phase、DAG后继由PM独立复验决定。

## 证据

证据根（key-relative）：`evidence/implementation/dpc-t06-validity/rework-r2/`；完整路径 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/rework-r2/`。产品根：`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/`。

### before / after 字节（`after.json`，原文副本在 `before-bytes/`、`after-bytes/`）

| 文件 | before bytes/LF/CRLF/SHA256 | after bytes/LF/CRLF/SHA256 |
| --- | --- | --- |
| decision_validity.py | 54353 / 1652 / 0 / `64b9b9e1060aab955a4d0428385e2d450ae94826d1a548088c65f5874c049eb1` | 58410 / 1745 / 0 / `cf01bbe2aa15b1794cd5868c49897f7b4616e8f17ab11dbbb92cc6b145ef5d51` |
| test_dp_consolidation_concurrency.py | 49049 / 1297 / 0 / `c9dc013110de702f733b5ec292c1d62ccdaa93d7ffb4fa7ffcec9101c2a97349` | 57243 / 1522 / 0 / `7e9dcb2bc407d724e6f56ab9ae2001d62d4ac5e4e3fc85d335a8844936a6db1b` |

before 两项与PM报告 `t06-pm-handoff-20261026/report.md` 记录值逐一相等，说明本轮起点就是PM复验的同一份源码（未被他人先行改写）。EOL 全 LF（CRLF=0），未做整文件格式化。

增量 diff（机械生成，非人工转录）：`decision_validity.py.diff`（10111B，SHA256 `efb631517529b1bc35c71600023671b0711f62fbd5fd48c8d3e4d8ec92d687d3`）、`test_dp_consolidation_concurrency.py.diff`（9750B，SHA256 `12ba974b9063a73d9d788d7f026017d000b76cfa4f91c00c1f0e9f217cf988fc`）。

既有diff状态：`git-status.txt` 记录两文件在实施副本所在git仓中均为 `??`（untracked，`git ls-files --error-unmatch` rc1），无已提交基线可覆盖，故既有diff=全文件，本轮以 before-bytes 作为唯一比对源；未与任何他session改动争用。

### 命令 / rc / 断言定位（全部 `python -B` + `PYTHONDONTWRITEBYTECODE=1`，私有 minimal UTF8 env/home/TEMP/project，`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，`-p no:cacheprovider`）

- 环境：`fixture/envrun.py` 以显式最小 env 在副本内执行唯一assigned命令 `python -B -m pytest -p no:cacheprovider -q test_dp_consolidation_concurrency.py`（cwd=副本 packages/multi-workers）。无HTTP/CLI/provider/服务/活对象探针。
- before 基线：`before-baseline.stdout` = `65 passed in 0.13s`，`before-baseline.rc`=0。
- red（先加测试、未改产品）：`red-r2.stdout` = `7 failed, 66 passed in 0.25s`，`red-r2.rc`=1。七项都是业务断言失败，不是import/collection错误。
- green（产品修复后）：`green-r2.stdout` = `73 passed in 0.15s`，rc0；文档措辞微调后 `green-r2-final.stdout` = `73 passed in 0.14s`，rc0；重复运行 `green-r2-repeat.stdout` = `73 passed in 0.15s`，rc0。
- 边界复测：`boundary_check.py` 以与PM `supplement.json` 完全相同的九个输入 + 九个正向控制只读调用实际副本，`boundary-after.json`：`boundary_failures=0`、`positive_control_failures=0`，stdout/stderr/rc 见 `boundary-after.{stdout,stderr,rc}`（rc0）。PM 的 `supplement.py` 未执行（避免覆盖原证据），其 `supplement.json` 仅作 before 只读记录。

逐项 red→green（测试文件行号为本轮after版本）：

| 边界 | 用例（行号） | red 断言（red-r2.stdout 实测） | green 实测 |
| --- | --- | --- | --- |
| required签收只认finalize | `test_required_signoff_accepts_only_the_finalize_word` (1284) | `AssertionError: continue`，`assert 'valid' != 'valid'` | `status=blocked`, reason `not_a_required_signoff` |
| 签收绑定真实key | `test_signoff_must_be_bound_to_the_required_key` (1304) | `assert 'valid' == 'blocked'` | `signoff_key_mismatch` / `missing_signoff_key` |
| 签收引用非空可追溯 | `test_signoff_reference_must_be_non_empty_and_traceable` (1325) | `AssertionError: None`，`assert 'valid' == 'blocked'` | `missing_signoff_reference` |
| 契约变更不得仍 reusable | `test_evidence_under_a_changed_contract_is_not_reusable` (669) | `assert 'applies' != 'applies'` （`reusable=True` 同时带 `contract_version_changed`） | `status=stale`, `reusable=False` |
| 非法路径使整个claim请求失败关闭 | `test_invalid_path_blocks_the_whole_claim_request` (904) | `assert 'clear' == 'blocked'` | `blocked` + `parent_traversal`/`absolute_path` + `invalid_claim_request` |
| 同owner他task的active claim不得clear | `test_same_owner_other_task_active_claim_is_not_clear` (944) | `assert 'clear' != 'clear'` | `conflict` + `own_claim_on_other_task`；同任务复入仍 `clear` |
| 已存effect非法/缺失状态不得proceed | `test_unrecognised_or_missing_effect_status_blocks_retry` (1366) | `AssertionError: unrecorded`，`assert 'proceed' == 'blocked'` | `blocked`, `actions=()`, `effect_state_unrecognised` |
| 正向控制（red前即绿） | `test_effect_plan_keeps_legal_states_unfrozen` (1401) | 未失败（`66 passed` 中的一项） | 无记录 `proceed`、`failed` 可重试、`applied` 去重 |

### 九项边界实测（`boundary-after.json`）

`signoff-continue`/`signoff-user-confirm` → blocked `not_a_required_signoff`；`signoff-wrong-key` → blocked `signoff_key_mismatch`；`signoff-missing-ref` → blocked `missing_signoff_reference`；`evidence-contract-change` → stale（`reusable=false`）；`claim-mixed-traversal` → blocked；`claim-other-task-same-owner` → conflict；`effect-unrecognized`/`effect-missing` → blocked。正向控制 9/9 通过（finalize valid、同契约/仅字节变化复用、同任务复入 clear、无记录 proceed、failed 重试、applied 去重、unknown/in-progress blocked）。

### 面与库存

- `net-inventory-diff.json`：整副本 1883→1883 条，added=0、removed=0；changed 仅 4 项：本卡两产品 + `test_dp_consolidation_recovery.py`、`test_dp_consolidation_materials.py`（并行 T07/T08 自有测试，非本卡写入面，本卡未读写）。T03/T04、TS、框架、config/gate/ledger/live、goal/spec、mirror、旧证据均未改。
- `pycache.json`：`.pyc` 共 14 个，逐个SHA与PM `out-of-face-bytes` 记录相等（`pyc_hashes_equal_pm_record=true`）；未删除、未新增任何pyc，未产生 `.pytest_cache`（added=0 亦覆盖）。
- 纯函数：`decision_validity.py.diff` 无新增import；文件内 `test_module_imports_only_stdlib_and_never_writes` 仍绿，未引入T08在写模块或任何peer依赖。

## 残留与未验证

- 本层只判纯函数行为；真实claim/锁（O_CREAT|O_EXCL）、CAS、效果写入、并发对账、消费者仍未执行也未验证，T20/T31 后续接管同一测试文件必须先声明依赖并交接hash。
- `SignoffRef` 仍不携带合同版本/审批主体等字段，本卡只在可证明范围内加“key∈required scope、matter_key、substantive_version、非空signoff_ref、artifact_ref、scope不扩张”判据；生产签收引用解析与trust源仍属后继，未造trust源。fixture中的 `fixture-artifact-reference` 文本不是生产产物已验的证明。
- 签收强制范围未扩大：`continue`/`user-confirm` 仍是 `FINALIZE_CHOICES` 合法菜单词，只有“必需成功签收”判定收窄为 `finalize`。
- `plan_actions` 中 `not-started`/`blocked` 等已在 `EFFECT_STATES` 内的显式未执行态保持原契约（可proceed），未无差别冻结；若产品意图要求它们也冻结，需另一次授权判断（本卡不改）。
- 契约变更现在只做到“不可复用/需按当前合同重新证明”，未定义语义等价合同迁移（如仅版本号递增）的复用路径；`unaffected_changes` 仅在同合同下计算。
- 未跑其它测试/生成器/npm check/build/install；未验证TS依赖解析；未做真实HTTP/决策CLI/服务探针；UTF-8/minimal env/-B/禁插件与cache 只是本地验证前提。
- 整副本inventory相等/差异不能证明历史瞬时无写或作者独占；T07/T08 同窗口变更按观测原样记录，不计入本卡。`ACTIVE_ENTRIES`/`MATTER_OWNERS` 与T03单源一致性仍留后续。

## 上下文来源

- `.agenticdoc/goal.md:5`、锁定 `spec.md:128`、design `design.md:201`（§4.3/4.5、D007、VC039/VC052）。
- 授权：`.agenticdoc/mw-dp-consolidation/evidence/implementation/s2-r2-approval-20261026.md:1`（用户明确批准T06定点返工并自动续推）。
- PM 只读输入：`evidence/implementation/t06-pm-handoff-20261026/{report.md,probe.json,supplement.json}`（九个当前失败边界）。
- 原卡 `tasks/isolated/T06-validity.md`、`implementation-isolated-dag.json`、原worker `workers/dpc-t06-validity/{task.md,run.json,output.md}` 与 `evidence/implementation/dpc-t06-validity/{report.md,assertions.json}`（只读，未回填、未覆盖）。
- 本轮实际副本两文件完整读到EOF（before-bytes 即读取时字节）。

## 改动清单

产品（仅本卡write_face两项）：

- `implementation-worktree/packages/multi-workers/decision_validity.py`
  - 新增 `REQUIRED_SIGNOFF_CHOICES=("finalize",)`；`FINALIZE_CHOICES` 保持三词菜单不变。
  - `assess_signoff`：非finalize菜单词→`not_a_required_signoff`；`key` 为空/不在required scope→`missing_signoff_key`/`signoff_key_mismatch`；`signoff_ref` 空→`missing_signoff_reference`（均 blocked）。
  - `assess_evidence`：`contract_version_changed` 同时置 `status=stale`、`reusable=False`（不再“仅记reason仍applies”）。
  - `assess_claim`：任一非法/绝对/穿越路径→整请求 `blocked` + `invalid_claim_request`；同owner同task复入仍clear；同owner他task重叠→`conflict` + `own_claim_on_other_task`。
  - `plan_actions`：匹配记录状态不在 `EFFECT_STATES`（含None/空串）→`blocked` + `effect_state_unrecognised`；applied去重、failed可重试、无记录可执行、unknown/in-progress阻塞均保持。
- `implementation-worktree/packages/multi-workers/test_dp_consolidation_concurrency.py`：新增8个用例（7 red→green + 1正向控制），65→73。

证据（仅本卡 rework-r2 目录）：`before-bytes/`、`after-bytes/`、`after.json`、两个 `.diff`、`before-baseline.*`、`red-r2.*`、`green-r2*.*`、`boundary-after.{json,stdout,stderr,rc}`、`pycache.json`、`net-inventory-diff.json`、`git-status.txt`、`fixture/{envrun.py,after_check.py,boundary_check.py}`。

未改：原仓库同名文件（不存在）、T03/T04、T07/T08 产品与测试、TS/框架/mirror、config/gate/brake/ledger/权限/预算/签收/goal/spec、原worker run/output、phase 与依赖。
