# T03 协议卡证据（dpc-t03-protocol / 隔离实施）

> 角色：coding worker。实际 cwd 根：`.agenticdoc/mw-dp-consolidation/implementation-worktree`。
> 唯一写面：卡列 4 个副本文件 + 本证据目录。未切换阶段、未运行 QG/签收、未调用真实 provider/服务。
> 证据目录：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/`（下文路径相对该目录，除非另注）。

## 结论

- 完成：副本内八入口协议单源落地——`DP_REGISTRY` 精确 8 条
  `dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route`；
  25 个旧编号进入独立只读退役目录（6 migrated + 19 retired，aliases=0）；旧编号在
  `require_active_dp`/`get_decision_point`/`decide_for` 第一步即 retired 拒绝，后端调用数 0。
- 完成：每入口 role / material / 选择 / 候选来源 / 依据（D012A `preparation.basis_catalog`）由
  Python 单源声明，快照 `decide_registry.json` 由既有纯 API `registry_snapshot_text()` 离线重生成
  （schema 3→4，`preparation` 与 `retired` 为独立顶层 section，points 仍精确八条）。
- 验证：卡片验收命令实测 **142 passed, rc=0**（`green-03-final.log` / `green-04-acceptance-final.log`，Python 3.14.3，隔离
  HOME/TEMP/project，`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、
  `-p no:cacheprovider`，FakeBackend/零真实网络）。
- 边界：这是协议/注册/纯 validator 层的成立，**不是** VC-001/002/003 的全入口 L2 通过：
  TS 生成物、CLI/replay/观察入口、case/UI/提示词生产面分别归 T04/T11/T23/T24/T05，尚未验证；
  本卡也未做 L2 业务放行、签收、QG、真实 provider 或部署。

## 证据

### 1. 基线（before，与隔离基线逐字节一致）

`before-manifest.json` / `before-bytes/`（脚本 `capture_manifest.py`）：

| 文件 | sha256 | bytes | EOL |
|---|---|---|---|
| packages/multi-workers/decision_points.py | `a92bbdc2f12e6559c6e40bd571336655d190d84aa73268bbff4ee0dc8bdf1243` | 247920 | CRLF 5769 / bare LF 0 |
| packages/multi-workers/decide_registry.json | `0a5e16d64ab83b9f84a6a6776cef55b16d87349010b24bb1b40da4207d1283ae` | 56194 | LF 1771 / CRLF 0 |
| packages/multi-workers/test_decide_registry_contract.py | `7564cfdcb2ad261beda987299c27008f57bc3561eb3348e841aeb676106b61cb` | 19538 | LF 435 / CRLF 0 |
| packages/multi-workers/test_dp_consolidation_registry.py | 不存在（新建） | — | — |

与 `evidence/implementation/isolation-baseline-20261026/approved-file-baselines.json` 的同名 sha 相同；
既有 source-repo diff 保留在 `isolation-baseline-20261026/original-diff/packages/multi-workers/`。
单 writer：`workers/dpc-t03-protocol/run.json` 显示本卡 running（pid 57204）且无其他 T03 writer；
写入面检查见下（只 4 个卡列文件被动过）。

### 2. 红测（先失败，留原始 stdout/stderr/rc）

- `red-01-tests-before-impl.log`：新测试模块在实现前**收集期**即失败，
  `test_dp_consolidation_registry.py:511 AttributeError: module 'decision_points' has no attribute 'ACTIVE_DP_IDS'`，
  **rc=2**（八入口 API 尚不存在）。
- `red-02-contract-before-impl.log`：同时跑 `test_decide_registry_contract.py`，
  **59 failed / 29 passed，rc=1**。原始失败定位（节选）：
  - `test_snapshot_holds_exactly_the_eight_active_entries`：实际仍是 25 条旧注册；
  - `test_point_carries_its_protocol_identity[dp1..dp25]` 共 25 例：`KeyError: 'kind'`；
  - `test_snapshot_schema_is_four`：`assert 3 == 4`；
  - `test_all_eight_entries_are_unwired_until_the_caller_cards_land`：`dp1-dispatch-type != dp-w-type`；
  - `test_model_state_fields_are_declared_for_every_active_entry`、
    `test_state_field_descriptions_cover_the_retired_explanation` 失败（旧条目/未声明面）。
  说明：红测阶段未逐条执行 25 个旧 ID 的新参数化用例（模块收集期即失败），
  本报告不把该轮算作“旧 ID 逐条红测”；旧 ID 的逐条拒绝断言在绿测轮真实执行（见 3）。

### 3. 绿测（实现后，同一命令/同一隔离 env）

- `green-01-tests-after-impl.log`：**1 failed / 140 passed，rc=1**。真实缺陷：
  `test_auto_accepts_free_ids_and_refuses_invented_choices`——单候选集合仍被接受，
  因为选择校验只检查 id 是否属于（非空）候选集，未复用候选集合同。
- 修复脚本：`patch_followup.py`（一处锚定替换；`entry_choice_issues` 现在同时校验
  PM 候选集合），sha `b0acc2e7…` → `a3fb1fe8…`。
- `green-02-tests-after-followup.log`：**141 passed, rc=0**。
- `green-03-final.log`：新增“测试/导入绑定隔离副本”守卫后 **142 passed, rc=0**。
- `green-04-acceptance-final.log`：全部写面定型后的最终验收重跑，**142 passed, rc=0**（与绿色结果一致）。
  实际命令（cwd=`implementation-worktree/packages/multi-workers`，相对文件名）：
  `python -m pytest -p no:cacheprovider -q test_decide_registry_contract.py test_dp_consolidation_registry.py`
  → 见日志 `# argv:` 与 `# rc: 0`；日志同时记录隔离 home/project/temp 与
  `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`。
- 运行后检查：worktree 内无 `__pycache__`、无 `.pytest_cache`（命令输出 `cache-check-done`，未生成）。

关键断言定位（副本内）：

- 八入口/退役组成：`test_dp_consolidation_registry.py:243/253/264/275`；
- 25 旧 ID 逐条：resolver `:291`、`decide_for` 前置拒绝且 `FakeBackend.calls == 0` `:302`；
  拒绝信息不携带继任别名 `:311`；
- 角色只作资格、route 不授权：`:324/:337`；
- 固定选项基线（w-type 4 / pm-steer 4 / w-check-task 3 / QG 3 / gate 4 / sign 3）：`:344/:362/:393`；
- vision 图像硬门（无证/未知不启动、不回退 coding、其他框架类型保留）：`:406`；
- dp-auto 六候选/自由 id 合法、旧 cN/2..5 不适用、单候选/重复/越集/未备理由拒绝：`:426/:440`；
- dp-route 七目标、不得选自身、auto/route 均无可执行 executor：`:469/:487`；
- 材料/类型/未知键/`basis_catalog` 不得混入 material：`:502/:522`；
- sign-key 三数组 `[]` 合法、null/缺项拒绝：`:548`；
- gate `pm_note` 与模型依据分列、catalog 不接受 probability/失败原因作理由：`:571`；
- D012A `preparation` 完整必需且独立：`:592/:613`；
- 八入口 prepared request 正例/失败不默认：`:638/:654`；八入口经 `DecisionClient` 真实渲染：`:676`；
- 快照单源一致性/协议字段/退役 section：`:690/:710`；
- 快照契约侧（字段语义、wiring、schema 4、TS 遗留债标注）：`test_decide_registry_contract.py` 同名测试。

### 4. 生成快照（既有单源 writer，离线，仅本卡输出）

`write_registry_snapshot.py`（只写副本 `decide_registry.json`，写后 read-back 相等）：

- before sha `0a5e16d6…`（56194 B，1771 行）→ after sha `cc017e343f2f7702cf2fcdafc1239d543be472b4e6ab6b92d6adaaee7a06c604`
  （29869 B，894 行，UTF-8/LF，无 CRLF，末行 `\n`）。
- `--check` 复跑：expected == current（幂等，未二次改写）。
- 顶层键：`schema(4) / generated_from / question_types / preparation / points / retired`；
  points 顺序即 §1.1 八名；`retired` 25 条按原编号顺序，6 条 `migrated` 带 `migrated_to`。
- dp-auto 导出：`kind=dynamic-candidates`、`candidate_source=pm-supplied:handling_options`、
  `candidate_bounds={"min":2,"max":null,"id_scheme":"free"}`；dp-route：`target_entries` 七目标，
  `candidate_bounds=null`；两者 `executor=unwired`。
- 旧快照里手工维护的 wiring（dp1/api 等 TS `path:line`）不迁移到新注册：它描述的是旧调用点，
  原始字节已保留在 `before-bytes/decide_registry.json` 与隔离基线，供 T04/T11 迁移时取用。

### 5. post 状态与写入面

`after-manifest.json` / `after-bytes/`：

| 文件 | after sha256 | bytes | EOL |
|---|---|---|---|
| decision_points.py | `a3fb1fe8f3a9caea2a6a4acc660298ca6d2cb9921418c152025c401279089047` | 304640 | CRLF 7080 / bare LF 0（保持原 CRLF） |
| decide_registry.json | `cc017e343f2f7702cf2fcdafc1239d543be472b4e6ab6b92d6adaaee7a06c604` | 29869 | LF 894 / CRLF 0 |
| test_decide_registry_contract.py | `4c6aedadca32dd26316a5d18407dc1e7889a62b986b6e6860f973d908878c1d0` | 19527 | LF 463 / CRLF 0 |
| test_dp_consolidation_registry.py | `af20145ead7a031a9ec5ca5ffd4227a725ef2f3615111fda9423f3f2d80b5a97` | 31311 | LF 727 / CRLF 0 |

- `t03-changes.diff`：四文件 unified diff；行级统计
  decision_points.py +1623/−312、registry +641/−1518、contract test +209/−181、新测试 +727/−0。
- `write-scope-check.json`：worker 启动（2026-10-26T02:35:17Z）后 worktree 内**只有**卡列 4 个文件
  的 mtime 变化，`unexpected_files=[]`；四旧 case `dp1/dp2/dp3/dp25.json` 与 source-repo 副本 sha 逐一相同
  （read-only 未被写）。
- `untouched-files-check.json`：把 `isolation-baseline-20261026/approved-file-baselines.json` 的
  85 个逐文件基线与当前副本逐一对比——56 个已存在文件**全部相同**，唯 3 个差异正是本卡
  前置已存在写面（`decision_points.py`/`decide_registry.json`/`test_decide_registry_contract.py`），
  `missing=[]`、`changed_is_t03_write_face=true`。
- `handoff-inventory.json`：`scripts/gen_decide_registry_ts.py`、`decide-registry.generated.ts`、
  `triage-client.ts` 与隔离基线 sha 相同（未碰 T04/T11 写面）；`mw.py`/`decision_context.py`/
  `decision_book.py`/`decision.py` 同样未改（仅记录当前 sha 供接手）。
- `import-smoke.json`：`decision_points/decision/decision_context/decision_book/decide_signoff/
  decide_archive/decision_history/decision_wire/decision_lifecycle` 全部仍可 import（import 级兼容；
  运行级旧 ID 调用点属 T09/T23/T27）。

### 6. 本卡实际执行的命令（`# rc` 见对应日志）

1. `python capture_manifest.py before before` → rc 0（before 清单）
2. `python run_pytest.py red-01-tests-before-impl` → rc 2（收集期失败）
3. 仅 contract 文件的等价 red run（runner 内改 TESTS）→ rc 1，59 failed / 29 passed
4. `python patch_decision_points.py <copy>`（`--check` 预检先通过）→ rc 0，sha before/after 记录
5. `python write_registry_snapshot.py` → rc 0；`--check` → expected==current
6. `python run_pytest.py green-01-tests-after-impl` → rc 1（1 failed，真实缺陷）
7. `python patch_followup.py <copy>` → rc 0
8. `python run_pytest.py green-02-tests-after-followup` → rc 0，141 passed
9. 增加隔离绑定守卫后 `python run_pytest.py green-03-final` → rc 0，142 passed
10. `python capture_manifest.py after after`、`python write_diffs.py`、`python write_scope_check.py`、
    `python verify_untouched.py` → rc 0
11. `python run_pytest.py green-04-acceptance-final` → rc 0，142 passed（最终定型重跑）

未执行：`npm run check`、build/install、`mw` CLI、gen_decide_registry_ts / build_decide_cases、真实 DP/provider、
服务探针、commit/push（均按卡禁止面）。

## 残留与未验证

1. **VC-001 只在本卡可核范围成立**：Python 注册/快照 points=8、aliases=0、migrated=6、retired=19、
   added=2 有机器断言；生成 TS、CLI、观察 submit 集合仍是旧 25 条（`decide-registry.generated.ts`
   与 `triage-client.ts` sha 未变），归 T04（生成/字节锁）与 T11/T28（工具/观察）。
   `test_generated_ts_regeneration_belongs_to_t04` 是**明确的负债标记**，不是 parity 通过。
2. **VC-002 只覆盖协议入口**：25 旧 ID 在 `get_decision_point`/`require_active_dp`/`decide_for`
   前置拒绝且 `FakeBackend.calls==0` 已测；`mw.py` 的 CLI/replay/观察/validate/scaffold/cases
   路径尚未接线（T23，含已有 logical_id replay），因此不声称“所有运行入口 + replay 拒绝”。
3. **VC-003 未做生产 caller/case/UI/prompt 清单审计**：本卡写面不含这些面；旧 case 四文件保持原字节，
   但 `decide_cases` 仍可被旧代码提交（T05 负责生成八 case 并把旧四件标 readonly regression），
   SQL/提示词/UI 面属 T05/T27/T29/T30。
4. **快照 schema 3→4 的下游影响未验证**：`mw.py` 的 `dp export/verify`（T23）、case 构建（T05）、
   dashboard/docs/`test_decide_registry_export.py`/`test_decision_pin_contract.py` 等旧断言尚未适配；
   本卡未运行它们。`mw._dp_verify_state` 仍只有旧 25 条的最小值表，因此 contract 测试不再调用
   `mw._dp_verify_point`，改用本卡 FakeBackend 探针（不算产品级 probe 迁移）。
5. **T08/T09 的渲染/答案校验未接新契约**：`resolve_dynamic_choices/dynamic_choice_labels` 新增了
   `dp_id` 关键字（默认保持旧行为），但 `decision_book`/`decision_backends`/`wire` 调仍不传 `dp_id`，
   所以生产路径上 dp-auto 的“自由 id、无 2..5/cN”尚未生效；本卡只证明纯规则与注册声明。
6. **T10/T12/T13/T15/T17/T18 的消费层未做**：purpose 上“选择/请求/动作/结算/完成分开”、gate 四分支、
   Worker 三分支、PM note 分列持久化等业务效果均需各自卡片；本卡未造任何 executor、grant、签收或 gate 状态。
7. **未做 L2 / 产品验收 / QG / 签收**：无真实 provider、无运行中服务、无 `mw decide` 调用、无 DOM/历史投影；
   142 passed 只对应本卡两个测试文件，不代表完整仓库或其它 suite 绿。无 `npm run check`（T32 保护副本）。
8. **旧 wiring 事实**：旧手工 wiring（`path:line`）不再出现在新快照，原始字节保存在
   `before-bytes/decide_registry.json` 与隔离基线；若下游要求“运行位置可追溯”，需 T04/T11 明确迁移，
   本卡未偷偷复制成第二份契约。
9. 时间预算/看门狗/权限/预算/凭证/锁均未改；未创建 grant、未恢复任何刹车、未动 goal/spec/其他 key。

## 上下文来源

- 目标：`.agenticdoc/goal.md:5`（文件驱动、扩展实现、进程/凭证隔离、目标对齐）。
- 锁定 SPEC：`.agenticdoc/mw-dp-consolidation/spec.md` §1.1（八入口/6 migrated/19 retired/2 added）、
  §1.2（dp-sign-key 四部与三数组、w-type 四型+vision 硬门、pm-steer 四选项、w-check-task 三固定项、
  QG 三结论、gate 四选项、auto 无默认菜单、route 七目标）、§1.5（固定直调/临时路由/角色不变）、
  §3 AC-001/002/003/004/005/007/012/040–044/046/051/053。
- 已批设计：`.agenticdoc/mw-dp-consolidation/design.md` §10（D-001A 活动 Python 单源、D-002A
  material/meta/生命周期分层、D-003A 固定/动态/路由分离、D-009A 物理八活动 + 独立退役目录、
  D-012A 同次模型依据 + PM 预备可溯源理由）、§4.1（逐入口材料/选择/角色）、§4.2/§5 F-01/F-11。
- 写面/隔离：`.agenticdoc/mw-dp-consolidation/design-write-scope.md` §2/§3/§4/§6、
  `implementation-isolation.md`、`implementation-isolated-dag.json`（T03 的 4 文件 + evidence 面）、
  基线 `evidence/implementation/isolation-baseline-20261026/`（原始 bytes/diff/EOL/映射）。
- 研究证据（只用于字段候选与旧机制定位，不作为验收）：`evidence/research/design-protocol-full-read-20261026.md`
  §3/§4/§4.1/§7（`kind`/`material_fields`/`candidate_source`/`candidate_bounds`/`target_entries`/
  `role_scope`、dp-auto 无 cN 限制、route `acted=false`、sign `[]≠null`）；
  `design-entry-contracts-20261026.md`、`design-pm-contract-integration-20261026.md`（D012 依据合同）。
- 派发卡：`workers/dpc-t03-protocol/task.md`（已完整读到 EOF）、`tasks/T03-protocol.md`（源卡，历史）。

## 改动清单

产品（仅隔离副本，卡列 exact files）：

1. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py`
   - `DP_REGISTRY`：25 条 → 8 条活动 entry（含 `kind/role_scope/candidate_source/candidate_bounds/
     target_entries` 字段与 import-time 校验）；`EXPECTED_DP_COUNT=8`；
   - 新增 `ACTIVE_DP_IDS/ENTRY_IDS/ROUTE_TARGETS/ENTRY_KINDS/ACTOR_ROLES/ENTRY_ROLES/ENTRY_CHOICES/
     ENTRY_CANDIDATE_SOURCE/ENTRY_CANDIDATE_BOUNDS/RETIRED_DISPOSITIONS`；
   - 新增只读 `RetiredDecisionPoint` + `RETIRED_DP_REGISTRY`（25，6 migrated/19 retired）+ `RETIRED_DP_IDS`
     + `RETIRED_STATE_FIELDS` + `RETIRED_STATE_FIELD_CROSS_CHECKS`（历史解释，不被运行时消费）；
   - `require_active_dp()`（retired 明确拒绝）、`get_decision_point()` 走同一路径、`is_retired_dp/retired_dp`；
   - 状态合同：`REQUIRED_STATE_FIELDS/OPTIONAL_STATE_FIELDS/MODEL_STATE_FIELDS/
     STATE_FIELD_CROSS_CHECKS` 改为八入口 + 新字段语义（`images_required`、`reachability_facts`、
     `investigation.*`、`review_*`、`pm_note.*`、`background.tried/unknowns/constraints`、
     `decision_actor/object`），sign-key 四部与三数组逐字保留；
   - 纯 validator：`resolve_entry_choices/role_issues/pm_candidate_issues/entry_candidates_issues/
     entry_material_issues/sign_key_material_issues/pm_note_issues/entry_choice_issues/
     basis_catalog_issues/basis_selection_issues/preparation_issues/prepared_request_issues/
     vision_dispatch_issues`；`BASIS_SOURCE/PREPARATION_KEYS/BASIS_ITEM_KEYS/CANDIDATE_ITEM_KEYS/
     CANDIDATE_LABEL_MAX`；
   - 动态选择渲染新增可选 `dp_id=`（旧调用默认行为不变；dp-auto 改走 `pm_candidate_issues`）；
   - 快照 `SNAPSHOT_SCHEMA=4`、每点导出协议身份、顶层新增 `preparation` 与 `retired`（points 仍八条）。
2. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_registry.json`
   - 由 `decision_points.registry_snapshot_text()` 离线重生成（29869 B，LF，sha `cc017e34…`）。
3. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py`
   - 改为八入口快照契约：八点/schema 4/顶层键集合/退役 section/字段语义（含退役解释）/`model_state_fields`/
     协议身份/wiring 全 unwired/问题集合来自单源；TS 侧只锁“遗留行未变 + 生成物属 T04”的负债，
     不再伪造跨层 parity 或调用旧 `mw._dp_verify_point`。
4. `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_dp_consolidation_registry.py`
   - 新增 727 行、29 项测试函数（参数化展开后 105 例）：八入口/退役组成、25 旧 ID 逐条前置拒绝（0 后端调用）、
     角色/选项/图像门/候选/路由/材料/sign 数组/D012A 依据/prepared request/八入口渲染/快照单源。

证据/脚本（仅本卡 evidence 目录）：`capture_manifest.py`、`run_pytest.py`、`patch_decision_points.py`、
`patch_followup.py`、`write_registry_snapshot.py`、`write_diffs.py`、`write_scope_check.py`、
`before-manifest.json`、`after-manifest.json`、`before-bytes/`、`after-bytes/`、`red-01-tests-before-impl.log`、
`red-02-contract-before-impl.log`、`green-01-tests-after-impl.log`、`green-02-tests-after-followup.log`、
`green-03-final.log`、`green-04-acceptance-final.log`、`t03-changes.diff`、`handoff-inventory.json`、`import-smoke.json`、
`write-scope-check.json`、`untouched-files-check.json`、`isolated/{home,project,temp}`、`report.md`（本文件）。

未改（有 sha 证据）：主工作树同名文件、`scripts/gen_decide_registry_ts.py`、
`decide-registry.generated.ts`、`triage-client.ts`、`mw.py`、`decide_cases/dp{1,2,3,25}.json`、
其他 key/活配置/gate/ledger/签收/预算/凭证/依赖 lock/dist/mirror。
