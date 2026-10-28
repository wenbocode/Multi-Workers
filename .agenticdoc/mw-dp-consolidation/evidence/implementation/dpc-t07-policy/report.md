# T07 — 只读policy校验真实授权引用/范围/单位/累计预算及恢复条件

任务卡：`tasks/isolated/T07-policy.md`（sha256 `88bee76800c724909e277485117335cf91d93e989ccc6d9fb09d4e9d99adeb5d`，11550 bytes，LF），
dispatch envelope：`workers/dpc-t07-policy/task.md`（sha256 `77a8354d2ccb2f98418b8f58196126b5af4737e09b12dbbc514bb913923f1da1`）。
task_key `dpc-t07-policy`，stage 2，deps T03/T04（前置项按 PM 交接 T03 局部 181 及 T04-R2 12:04:12Z 47 passed 视为成立，见 `t03-r3-pm-handoff-20261026/report.md`、`t04-r2-pm-handoff-20261026/report.md`）。

## 结论

真实 done（本卡范围内）：在隔离实施副本新增两个产品文件——`decision_policy.py`（纯只读 policy 校验/预算/恢复判断，1785 行，60498 bytes，sha256 `f4c44456…dde6bb`）与 `test_dp_consolidation_recovery.py`（31 个用例，1520 行，53478 bytes，sha256 `434412b3…380a974`）。指定验收命令实跑 `31 passed`，rc=0；八个 VC 的 `[VERIFY]` 计数行均为 0（`observed_retrip=1` 按要求为 1）。四个 fail-closed 分支的定向变异对照产生 8 个失败用例（含原始断言行号），证明用例非空转。

明确未证明（见「残留与未验证」）：不构成 H12 生产人资格/真实受控恢复/L2/QG/签收/部署证据；无真实 grant/policy/CLI/provider/HTTP/服务；未跑全项目 check、其他测试或生成器。

## 证据

全部路径为 key-relative（根 `.agenticdoc/mw-dp-consolidation/`），证据目录 `evidence/implementation/dpc-t07-policy/`。

1. before（真实缺失，不是伪造旧 before）
   - `evidence/implementation/dpc-t07-policy/before-check.py` / `before-check.json`（观察时间 2026-10-26T20:12:14+0800）
   - 两目标文件 `exists=false`（`decision_policy.py`、`test_dp_consolidation_recovery.py`），主树同名文件 `live_absent`；与 `evidence/implementation/s2-frontier-pre-dispatch-20261026/check.json` 的 T07 `exists=false, live_exists=false` 一致。
   - 同期 peer 面在 before 时：T06 两文件不存在；T08 `decision.py` 99249 bytes / `decision_backends.py` 44577 bytes 存在、`test_dp_consolidation_materials.py` 不存在。
2. 红测（真实 red：产品不存在）
   - `red-01-module-absent.log` / `.stdout` / `.stderr`：`ModuleNotFoundError: No module named 'decision_policy'`，`1 error in 0.14s`，rc=2，原始定位 `test_dp_consolidation_recovery.py:55`。
   - 说明：本条 red 是 import/collection 级（产品文件真实不存在），不是断言级；断言级证据见第 5 条负向对照。
3. 绿测（指定命令，cwd 为副本 `packages/multi-workers`）
   - 命令：`python -B -m pytest -p no:cacheprovider -q test_dp_consolidation_recovery.py`
   - `green-final.log/.stdout/.stderr`：`31 passed in 0.20s`，rc=0（最终态）。
   - 迭代过程真实保留：`green-01`（3 failed：授权 scope 用例测试 bug、user-stop 分支、`__future__` 结构断言）、`green-02`（1 failed：`guard-clearance-unverified`）、`green-03`（31 passed, rc=0）。
   - 每次运行均为：`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`、`-B`、HOME/USERPROFILE/TEMP/TMP/TMPDIR 固定在 `evidence/implementation/dpc-t07-policy/fixture/`，只跑本卡列出的单一测试文件（driver `run-assigned-test.py` 记录 cwd/argv/env/rc）。
4. VC 计数（`-s -rA` 同一文件、同一隔离环境，`verify-01-s.log`）
   - `[VERIFY] VC-008: unauthorized_releases=0 unauthorized_effects=0 missing_failure_reasons=0`
   - `[VERIFY] VC-020: unbounded_extensions=0 unsupported_extensions=0`
   - `[VERIFY] VC-021: hard_budget_overruns=0 self_granted_limits=0 reset_usage=0`
   - `[VERIFY] VC-022: event_only_resumes=0 unsupported_resumes=0 mandatory_human_waits=0`
   - `[VERIFY] VC-034: erased_stop_facts=0 reset_usage=0 unsupported_resumes=0`
   - `[VERIFY] VC-035: unauthorized_user_stop_unlocks=0 hard_guard_bypasses=0 false_resumes=0`
   - `[VERIFY] VC-036: breaker_self_approvals=0 unauthorized_recoveries=0 transport_bypasses=0`
   - `[VERIFY] VC-037: unauthorized_unlocks=0 erased_breaker_history=0 reject_project_closures=0 observed_retrip=1`
5. 负向对照（证明用例能抓缺失的 fail-closed 逻辑；变异体只在证据目录，不是产品）
   - `negative-control.py` / `negative-control.json` / `negative-control/decision_policy.py`
   - 4 个变异：gate 丢弃 policy issues、允许预算越界、技术批准解除 user-stop、被熔断链自批恢复。
   - 结果：`8 failed, 23 passed`，rc=1；原始断言定位如 `negative-control/test_dp_consolidation_recovery.py:1174`。
   - 产品文件在本对照中只被读取；对照后产品 sha256 仍为 `f4c44456…dde6bb`（`negative-control.json.product_file_sha256`）。
6. after（真实终态）
   - `after-check.py` / `after-check.json`：
     - `decision_policy.py` 60498 bytes / `f4c44456316b8c60c7934a209de389ef6366aa864f026f9ba5fba40569dde6bb` / LF / 尾换行 / 1785 行 / EOF 行 `return ObservationVerdict(False, "released", True)`
     - `test_dp_consolidation_recovery.py` 53478 bytes / `434412b3ea60e60807ea23b52cdc474e892457a0a1747ecf7cb6bf809380a974` / LF / 尾换行 / 1520 行 / EOF 行 `assert before_files == after_files`
   - import 绑定探针（cwd=副本包目录）：`decision_policy.__file__ = …implementation-worktree\packages\multi-workers\decision_policy.py`，`POLICY_SCHEMA_VERSION=1`，`FROZEN_CONFIG_UNITS=["round_budget","worker_timeout_min"]` → 导入的是副本，不是主树/缓存。
   - 副本内 `__pycache__` 与 `.pytest_cache` 目录：均为 `[]`（无 pyc 事故）。
   - `changed-files.py` / `changed-files.json` / `mine.diff`：本 worker 唯一变更=上述两个 added 文件；主树同名文件不存在。
7. 语义落点（用例名 → 合同）
   - AC-008/VC-008：`test_policy_absent_yields_zero_permissions`、`test_illegal_policy_json_is_fail_closed`、`test_self_reported_authority_fields_are_not_authority`、`test_authority_ref_must_resolve_to_a_trusted_controlled_writer`、`test_revoked_and_out_of_scope_authority_blocks_release`、`test_gate_missing_or_failed_conditions_never_release`、`test_steer_and_need_fix_do_not_release`
   - AC-021/VC-021：`test_spend_blocks_unknown_unit_and_unknown_usage`、`test_spend_accumulates_and_never_resets_usage`、`test_limit_increase_requires_concrete_human_authorization`、`test_hard_limit_needs_explicit_unit_source_and_not_a_config_knob`
   - AC-020/VC-020：`test_soft_extension_needs_policy_authorization`、`test_soft_extension_needs_a_complete_pm_note`、`test_hard_balance_alone_cannot_extend_rounds`、`test_soft_extension_is_limited_to_the_explicit_delta`
   - AC-022/VC-022：`test_pending_review_event_only_triggers_evaluation`、`test_pending_review_resume_needs_valid_goal_clearance_evidence_and_budget`
   - AC-034/VC-034：`test_halted_recovery_requires_a_complete_note`、`test_halted_recovery_requires_approve_and_valid_authority`、`test_halted_recovery_preserves_stop_facts_and_usage`、`test_recovery_rule_missing_conditions_blocks_only_recovery`
   - AC-035/VC-035：`test_user_stop_and_hard_guard_cannot_be_lifted_by_a_technical_fix`
   - AC-036/VC-036：`test_breaker_recovery_rejects_the_tripped_chain_and_bypass_channels`、`test_breaker_recovery_requires_evidence_and_machine_checks`、`test_breaker_recovery_transport_unavailable_keeps_brake`、`test_breaker_recovery_positive_is_limited_and_keeps_history`
   - AC-037/VC-037：`test_user_disabled_keeps_brake_with_a_concrete_question_and_no_closure`、`test_observed_retrip_engages_the_brake_again`
   - 结构性只读/边界：`test_module_is_pure_and_imports_no_cli_conductor_or_config`（AST 导入集 ⊆ `__future__/json/pathlib/dataclasses/collections/typing`，禁止 argparse/subprocess/socket/autopilot/mw/decision*/conductor）、`test_frozen_config_keys_are_not_an_authority_source`（DEFAULT_CONFIG 仍 21 键，`round_budget`/`worker_timeout_min` 仅作被拒单位）、`test_policy_reads_are_read_only_and_side_effect_free`（多次评估前后 policy 文件 sha 与项目文件集合不变）

## 残留与未验证

- 本模块是纯判断，不是生产切换：没有真实 policy 文件、真实 grant、受控 writer、CLI/conductor 消费者接线；`evidence/.../fixture/authority/*.json` 是隔离 fixture 里由 `FixtureAuthorityWriter`（tmp+`os.replace` 真字节写）产出的模拟授权，不能冒充真实用户授权或 H12 生产人资格。
- 真实 H12 通道隔离/预授权来源、T21 恢复 handler 接线、真实 transport 可用性、观察/停止条件的实际运行语义均未验证（T21 在本卡后接管恢复测试）。
- 未跑：全项目 `npm run check`（T32 PM-direct 保护副本）、其他任何测试文件、`gen_decide_registry_ts.py`/`build_decide_cases.py` 等生成器、build/install/restart/commit/push；未修改冻结 21 键 config、活 policy/gate/brake/ledger/凭证/预算/签收/goal/spec/其他 key/四旧 case。
- 未做真实断言级「先红」：红测为 import 级（产品真实不存在）；断言级失败证据来自第 5 条变异对照（标注为负向对照，不冒充红测）。
- 未量化验证的语义边界：scope 匹配为 token/`prefix:*` 语义；`usage` 由调用方提供（本模块不读真实消耗账本），真实累计消耗来源对接留给消费者任务；恢复 scope 仅取 `required_scope ∩ rule.scope`。
- 整 mirror 净差包含同期 peer 合法变化，不归本 worker：after 观察时 T06 `decision_validity.py`/`test_dp_consolidation_concurrency.py`、T08 `decision.py`(115186 bytes)/`decision_backends.py`(48970 bytes)/`test_dp_consolidation_materials.py` 均已存在（见 `after-check.json.peer_faces_not_authored_here`）。未 import T06/T08 未稳定模块、未复制其代码、未形成新读写依赖。
- 卡片「改动历史」段未追加：`tasks/isolated/T07-policy.md` 与 `workers/dpc-t07-policy/task.md` 均在本卡 write_face 之外（禁止面），等价记录在本 evidence 目录（before/after/changed-files/mine.diff/red-green 日志），由 PM 吸收。
- 未删除 human ask / legacy 显示 / dead helper，未触碰未列面；如需改动另批报告。
- 并发 peer pycache：20:15:34 的 after-check 记录副本内 `__pycache__`/`.pytest_cache` 均为空；20:17:06 观察到副本内出现 peer 模块 pyc（`decision*`、`mw_common`、`autopilot/*`，时间戳 20:16:49），**无** `decision_policy*.pyc`、无测试 pyc，且本卡每次运行均 `-B` + `PYTHONDONTWRITEBYTECODE=1`。判定为并发 peer 测试产物，不归本 worker；`__pycache__` 在 write_face 之外，未删除/未改动。见 `pycache-attribution.json`。

## 上下文来源

- `goal.md:5`（项目级目标锚点，只读）
- `spec.md:128` 及 §1.6 H01–H13 / AC-008、020、021、022、034、035、036、037（锁定 AC 原文，只读）
- `design.md:201` 及 §4.2/§4.5（M05 只读授权旁载、`assess_validity`/`consume_gate` 候选接口、policy 候选字段、H12 隔离与观察/停止条件、预算单位/使用来源规则）
- `design-write-scope.md:64`（`decision_policy.py` 只读授权旁载校验，接原 config 硬门，非 grant writer）
- `implementation-isolation.md`、`implementation-isolated-dag.json`（隔离 root、逐文件 write_face、T07 deps/AC/VC/命令）
- `evidence/design-approval-20261026.md`（设计批准）
- `evidence/implementation/s2-frontier-pre-dispatch-20261026/check.json`（新鲜 before：T07 两文件均不存在，unordered overlap=0）
- `evidence/implementation/t03-r3-pm-handoff-20261026/report.md`、`evidence/implementation/t04-r2-pm-handoff-20261026/report.md`（前置交接）
- 只读参考源码（完整读取相关片段，未修改）：`autopilot/config.py`（冻结 21 键/默认值/`ConfigError` 语义，用作用例中「config 键不是硬授权」的对照）、`test_decide_policy.py`/`test_autopilot_gate_guards.py`（既有 `[VERIFY] tag: k=v` 证据风格）、`pytest.ini`

## 改动清单

仅以下两个产品文件为 added（此前真实不存在，见 `before-check.json`）；证据目录为本卡新增证据，不是产品。

| # | 路径（key-relative） | 动作 | bytes | sha256 | EOL/EOF |
|---|---|---|---|---|---|
| 1 | `implementation-worktree/packages/multi-workers/decision_policy.py` | added | 60498 | `f4c44456316b8c60c7934a209de389ef6366aa864f026f9ba5fba40569dde6bb` | LF，尾换行，1785 行，EOF `return ObservationVerdict(False, "released", True)` |
| 2 | `implementation-worktree/packages/multi-workers/test_dp_consolidation_recovery.py` | added | 53478 | `434412b3ea60e60807ea23b52cdc474e892457a0a1747ecf7cb6bf809380a974` | LF，尾换行，1520 行，EOF `assert before_files == after_files` |

证据（本卡新增，非产品）：`evidence/implementation/dpc-t07-policy/` 下 `before-check.{py,json}`、`run-assigned-test.py`、`red-01-module-absent.*`、`green-01/02/03/final.*`、`verify-01-s.*`、`literal-command.log`、`negative-control.py|json|/`、`after-check.{py,json}`、`changed-files.py|json`、`mine.diff`、`pycache-attribution.json`、`fixture/`（隔离 project/home/TEMP 与 fixture writer 写出的模拟授权记录）、本报告 `report.md`。

未改动：主树同名文件（`live_absent`）、冻结 21 键 config 及其 fallback/默认 disabled/合法 disable、活 policy/gate/brake/ledger/凭证/预算/签收/goal/spec/其他 key/四旧 case、T06/T08 与 T03/T04 产品面、依赖/lock/dist/mirror/install/服务/commit/push。
