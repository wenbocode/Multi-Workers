# T03-R2 定点返工报告（dpc-t03-protocol-r2）

## 结论

三项获批返工已在本卡写面内完成并通过红→绿：缺失/非法角色不再通过准备请求校验；`prepared_at` 按既有 ISO-8601 + 显式时区合同拒绝非法/缺失/错类型；旧的“永久锁旧 TS + 全未接线 + 旧矩阵等值”三处阶段锁改为可演进的真实契约断言（后继 T04/T11 已获权接线后无需越面改本测试）。八入口合法材料/角色正例、准备阶段不提前索取模型 choice/basis、旧历史行（4 条 retired 债务）与快照单源字节锁均保持。

- 验收命令（cwd=副本 packages/multi-workers，`python -m pytest -p no:cacheprovider -q test_decide_registry_contract.py test_dp_consolidation_registry.py`）：**rc=0，166 passed**（返工前 142 passed）。
- 改动面：3 个产品/replica 文件被改（`decision_points.py`、两个测试），`decide_registry.json` 未改（快照数据与纯函数输出一致，无需重生成，未运行 T03/T04/T05 生成器）。
- 13 条交接路径中仅上述 3 条变化，其余 10 条字节不变；主树同名文件、原 T03 全部证据（29 个文件）、活源码/配置/服务/ledger/gate 均未触碰。
- 未签 L2、未放行 T04、未推进 phase/签收；T04 的 TS 生成/parity、CLI/replay、真实 provider、npm check 仍未验证。**T03 语义交接仅在“本轮三项缺口”意义上可复核，不构成全 L2 通过。**

## 证据

证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t03-protocol/rework-r2/`（唯一新证据目录；父目录原 T03 证据未被写入，`write-scope-check.json.original_t03_evidence.ok=true`）。

开工基线（编码前）：
- `before-manifest.json` / `before-bytes/`：四文件当前 bytes/SHA256/EOL/行数，且 `matches_pm_handoff=true`、`matches_t03_after_bytes=true`（与 PM 交接 check.json、原 T03 after-bytes 完全一致，证明开工时无并发改写）。`decision_points.py`=a3fb1fe8…（304640B，CRLF 7080）；`decide_registry.json`=cc017e34…（29869B，LF 894）；`test_decide_registry_contract.py`=4c6aedad…（19527B，LF 463）；`test_dp_consolidation_registry.py`=af20145e…（31131B，LF 727）。
- `before-dirty-vs-main-tree.diff`：四文件相对主树同名文件的既有脏差异（implementation-worktree 整体未纳入 git，故用主树源文件作为基线），202289B。
- 读取范围：两测试文件全文（463/727 行）；`decision_points.py` 全文 7102 行中的 T03 protocol 段（3800–4340，含 `preparation_issues`/`prepared_request_issues`/`role_issues`/basis/candidate 校验）与 `__all__`/快照/注册表段定位读取；未逐行通读 7102 行全源（见残留 2），以 before-manifest 的哈希一致性作为“未被他处改写”的替代证据。

红测（行为反例，先红）：
- `red-02-tests-before-impl.log`：**rc=1，16 failed / 150 passed**，失败恰为新增反例的 8+8：
  - `test_prepared_request_refuses_a_missing_or_non_eligible_role[dp-*]`：缺失/None/空串/未知/跨角色均返回 `()`（原始断言定位 `AssertionError: ('dp-w-type', None, ())`）。
  - `test_preparation_refuses_a_prepared_at_outside_the_iso_contract[dp-*]`：`not-an-ISO-timestamp`、裸日期、无时区、空、非字符串等全部返回 `()`（原始定位 `AssertionError: ('dp-route', 'not-an-ISO-timestamp', ())`）。
- `red-01-tests-before-impl.log`（保留不删）：同批首次红测，除上述 16 项外另含 1 项**我自己新测试的顺序比较缺陷**（`ids` 渲染顺序按字典序 vs `RETIRED_DP_REGISTRY` 声明序），已修正为 sorted 比较；不拿它冒充产品红测。
- 第三项（测试阶段锁）的“旧锁确实阻碍后继”证据用同一输入的对照探针给出（见下），不是本轮源码红测。

第三项阶段锁对照（合成 fixture，非 T04 产物）：`probe_stage.py` → `probe-stage.json`
- 合成八入口 TS（`fixture/eight-entry.synthetic.ts`）：旧断言（要求 `dp1-dispatch-type` 且禁止八入口）→ `rejected`；新 `_generated_ts_stage()` → `post-t04`；新契约测试 → `accepted`。
- 单边改名（25 旧 ID 去掉 dp1 加 dp-w-type，`fixture/mixed-rename.synthetic.ts`）：新 stage/新契约均 `rejected`（保留“单边改名必红”）。
- 接线：合成 wired=true 且 trigger 指向真实文件 `packages/multi-workers/decision_points.py:666` → 旧 `all(wired is False)` → `rejected`，新接线契约 → `accepted`；trigger 指向不提及该 ID 的 `usage.py:1` → 新契约 `rejected`（“wired 必须是真接线，不是占位”）。
- `triage-client.ts` 矩阵：合成 post-T04 行（dp-sign-key 一行）→ 旧 `by_dp == LEGACY_TS_ROWS` → `rejected`，新阶段化契约 → `accepted`。
- 真实产物的 stage：`real_artifact_stage="pre-t04"`，说明新契约在当前（未 T04 生成）状态下仍然全部成立。

绿测（最小实现后）：`green-02-tests-after-impl.log`、`green-03-acceptance.log`：**rc=0，166 passed，0 failed**。合法正例覆盖：
- 八入口 `actor_role=ENTRY_ROLES[entry]` + 合法 material/preparation + 合法 choice/basis → `()`（`test_prepared_request_passes_for_the_legal_fixture`）。
- 准备阶段（无 choice/basis 回答）在真实角色下 → `()`（`test_preparation_does_not_demand_the_answer_before_the_model_call`），证明修复未把“缺角色拒绝”扩大为“提前索取模型答案”。
- `prepared_at` 合法：`…T00:00:00Z`、`+00:00`、`+08:00`、`.123456Z` 全部 `()`。
- 旧历史债务保留：4 条 retired 行（dp4/dp5/dp6/dp13）等值断言仍在；快照 `decide_registry.json == registry_snapshot()` 字节锁仍通过；25 旧 ID 拒绝、八入口合同、sign 三数组 `[]` 语义、route 七目标、auto 自由候选等原断言全部保持。

执行隔离：`run_pytest.py` 用**从零构造的最小 env**（仅 PATH/SYSTEMROOT/… 透传），私有无害 `isolated/{home,project,temp}`，`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`；cwd 为副本 `packages/multi-workers`，测试内 `test_tests_bind_the_isolated_copy_only` 断言 `decision_points/decision/mw.__file__` 均在 implementation-worktree；无网络/provider/决策 CLI/服务调用，未运行生成器与 `npm run check`。运行后副本内无 `__pycache__`/`.pytest_cache`。

写面与不可变核对：`capture_after.py` → `after-manifest.json`、`write-scope-check.json`、`r2-changes.diff`、`after-bytes/`
- 副本内 mtime≥R2 起点（2026-10-26T03:33Z）的文件**恰为 3 个预期文件**：`unexpected=[] missing=[] ok=true`。
- 13 条交接路径：`decision_points.py` 78e72e03…（305745B，CRLF 7102）、两个测试 67b74a47…（23724B，LF 557）、f7bf0302…（35149B，LF 815）为 CHANGED；其余 10 条（`decide_registry.json` cc017e34…、`decision_context.py` 5eeb8605…、`decision_book.py` fc6d74a3…、`decision.py` c2b6d0a6…、`mw.py` 35fa4689…、`scripts/gen_decide_registry_ts.py` a0ed7a80…、`decide_cases/dp1.json` 3131c02f…、`dp2.json` a03e1a29…、`dp3.json` 82ff47e5…、`dp25.json` bda25144…、`decide-registry.generated.ts` 699719c2…、`triage-client.ts` 70551a67…）字节不变；`handoff_ok=true`。
- 主树同名四文件 `main_tree_unchanged=true`；`original_t03_evidence`: 29 个文件、`touched_after_r2_start=[]`、`ok=true`（未改原卡/原 run/output/原日志/父目录证据）。

## 残留与未验证

1. **未覆盖下游（不声称）**：T04 的真实 TS 生成与 `--check`、TS 依赖解析/编译/parity、T05 case 生成、CLI/replay/legacy 人面、真实 provider 模型返回的 choice+basis 同次有效、vision 实际能力门、全项目 `npm run check`、全 L2/QG/签收——全部未验。本卡未运行任何生成器，`decide_registry.json` 与 `decide-registry.generated.ts` 保持原字节。
2. **源码通读范围有限**：本轮完整读了两测试与 protocol 校验段，未逐行通读 7102 行 `decision_points.py`；T33 全源审核仍未做。开工未被他处改写的证据是哈希一致（PM handoff + 原 after-bytes），不是全仓净写面证明。
3. **角色校验的边界**：`role_issues` 仍只是“请求资格”参数校验，**不是**生产身份认证；无 token/TTY/self-report 授权。`prepared_request_issues` 现在无条件校验 role，任何省略角色参数的调用方都会得到 `actor_role` 阻塞项——当前副本内除测试外无生产调用方（grep 已核），但 T04 接线时必须显式传真实角色，否则按设计阻塞（这是预期行为，不是默认放行）。
4. **时区规则的选择**：`prepared_at` 采用与副本 `decision_task_state.validate_task_state` 相同的 ISO 合同（`fromisoformat` + `Z` 归一 + 必须有 `T` 与显式偏移）；裸日期/无偏移本地时间被拒。若后续设计要接受无偏移时间，需另批修改（本卡未扩大/缩减既定格式之外的东西）。
5. **阶段锁的演化前提**：新 TS 契约只在“恰好 25 retired 全量旧件”或“恰好八入口”两态通过；若 T04 选择第三种中间态（例如仅部分入口），本测试会红并需在 T04 写面内显式扩展，这是刻意保留的防单边改名闸门。`triage-client.ts` 的 post-T04 分支只要求“active 行只出现在 post-T04 阶段且字段名为非空字符串”，不做字段级 parity（那属 T04）。
6. 本轮删除了两个旧测试函数（`test_generated_ts_regeneration_belongs_to_t04`、`test_no_python_only_dp_reappears_in_the_legacy_matrix`）并把 `test_legacy_ts_required_rows_are_unchanged_debt` 改写为 `test_ts_required_rows_follow_the_registry_stage`：其断言被吸收（旧件全量/sorted 等值、retired 行等值、pre-T04 下 active 行必须为空），未无条件 skip/xfail，未放宽为任意输入；`test_all_eight_entries_are_unwired_until_the_caller_cards_land` 改写为“接线声明必须有真实引用背书”。真实 T04 接线后仍需由 T04 自己的 parity 检查补位。
7. 未改：八职责/退役 25/53 AC-VC/写面/预算/watchdog/授权；未伪造 decision_id 或服务回执（上一轮 dp4 UNAVAILABLE 已由人工批准处理，本卡不重复询问、不写 executed/settled）。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t03-protocol-r2/task.md`（完整读至 EOF，含优先返工段与交付段契约）。
- 人工批准：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t03-rework-approval-20261026.md`（三项返工、范围/并行性、验证与禁止面）。
- PM 交接与探针：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t03-pm-handoff-20261026/{report.md,probe.py,probe.json,check.py,check.json}`（三项缺口的实测复现与四文件 hash）。
- 原 T03 只读事实：`evidence/implementation/dpc-t03-protocol/{report.md,after-manifest.json,handoff-inventory.json,green-*.log,run_pytest.py}`；未改。
- 设计/合同：`.agenticdoc/mw-dp-consolidation/design.md:174–176`（basis_catalog 独立、失败 reason/概率不是理由）、`:237`（preparation.basis_catalog+prepared_at 独立于 material/meta）、`:241`（`validate_request(active_dp, material, preparation, bound_actor)` 顺序与旧 ID 先拒）。
- 隔离/依赖：`.agenticdoc/mw-dp-consolidation/{implementation-isolation.md,implementation-isolated-dag.json,plan.md}`；`.agenticdoc/goal.md:5`。
- 同包既有 ISO 合同先例：`packages/multi-workers/decision_task_state.py:29–38`（副本内只读）。

## 改动清单

实际修改（3，均在写面内；`r2-changes.diff` 为逐行差异）：

1. `packages/multi-workers/decision_points.py`（a3fb1fe8… → 78e72e03…，+462B/+22 行）
   - `preparation_issues`：`prepared_at` 由“非空字符串”改为 ISO-8601 + 显式偏移校验（`fromisoformat`、`Z`→`+00:00`、要求 `T` 与 `tzinfo`）；错误路径给出 `prepared_at` 具名 issue，不新增预算/年龄阈值、不回显调用方原文。
   - `prepared_request_issues`：移除 `if actor_role is not None` 旁路，角色一律校验（缺失=阻塞）；docstring 明确 bound_actor 语义、自报角色不等于授权、不提前索取模型 choice/basis。
2. `packages/multi-workers/test_decide_registry_contract.py`（4c6aedad… → 67b74a47…，+4197B/+94 行）
   - 新增 `_generated_ts_entry_ids()`、`_generated_ts_stage()`（pre-t04 / post-t04，其他一律失败）。
   - `test_all_eight_entries_are_unwired_until_the_caller_cards_land` → `test_wiring_claims_are_backed_by_the_call_site_they_cite`（未接线不得声明 trigger/adopted_at；接线必须指向真实文件且该文件点名该入口）。
   - `test_legacy_ts_required_rows_are_unchanged_debt` → `test_ts_required_rows_follow_the_registry_stage`（retired 行等值保留；未知 ID 禁止；active 行仅 post-T04 允许；字段名非空）。
   - `test_generated_ts_regeneration_belongs_to_t04` → `test_generated_ts_registry_is_the_frozen_legacy_or_the_t04_projection`（两态精确 ID 集 + 头部/接口/`requiredStateFields` 形状锁；单边改名必红）。
   - 新增 `test_universal_required_fields_stay_the_frozen_identity_block`（冻结 identity 块）。
   - 删除 `test_no_python_only_dp_reappears_in_the_legacy_matrix`（断言并入上条 pre-T04 分支），模块 docstring 第 3/6 条同步改写。
3. `packages/multi-workers/test_dp_consolidation_registry.py`（af20145e… → f7bf0302…，+3838B/+88 行）
   - 新增 `test_prepared_request_refuses_a_missing_or_non_eligible_role`（8 参数化：None/空串/空白/未知/跨角色/省略参数）。
   - 新增 `test_preparation_does_not_demand_the_answer_before_the_model_call`（8 参数化，合法角色 + 无 choice/basis → `()`）。
   - 新增 `test_preparation_refuses_a_prepared_at_outside_the_iso_contract`（8 参数化：11 个非法/缺失+4 个合法正例+缺键）。

未修改：`packages/multi-workers/decide_registry.json`（cc017e34…，快照纯函数输出与磁盘字节仍相等，无需重生成）；13 条交接路径中其余 10 条；主树同名四文件；原卡、原 T03 run/output/证据、活源码/配置/服务/ledger/gate/签收/预算/watchdog。

本卡新增证据（全部在 `evidence/implementation/dpc-t03-protocol/rework-r2/`）：`capture_before.py`、`inspect_ts.py`、`run_pytest.py`、`probe_stage.py`、`capture_after.py`、`before-manifest.json`、`before-bytes/`、`before-dirty-vs-main-tree.diff`、`red-01-tests-before-impl.log`、`red-02-tests-before-impl.log`、`green-01-tests-after-impl.log`、`green-02-tests-after-impl.log`、`green-03-acceptance.log`、`probe-stage.json`、`fixture/{eight-entry.synthetic.ts,mixed-rename.synthetic.ts}`、`isolated/{home,project,temp}`、`after-manifest.json`、`after-bytes/`、`r2-changes.diff`、`write-scope-check.json`、`report.md`。
