# T05 八入口隔离 case 单源生成 — 实施证据

- 卡：`workers/dpc-t05-eight-cases/task.md`（`card_sha256=8a7d7470…b3e85`）
- 实施根：`implementation-worktree/packages/multi-workers`
- 证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/`
- 记录时间（本文件事实的采集时刻）：2026-10-27T13:0x–13:2xZ（各 `logs/*/meta.json` 有时间戳）

## 结论

本卡范围内的实现与隔离验证完成：单源生成器现在只产出 §1.1 的八个入口 case，
schema **3**（`material` + `preparation` + 本地 `meta` + 独立 `path:line` provenance），
四个旧 case（dp1/dp2/dp3/dp25）逐字节未变，25 个退役编号在生成器与 schema 门被拒绝，
8/8 case 通过生产 `check_book`（**以副本为 repo_root**，证据只在本副本内解析），
每个受支持选择都有同次可选、可核的 PM 预备依据。

本卡**不**构成 S2/L2/QG/签收/部署/回移完成：
- 卡内验收命令的整文件结果为 `16 passed / 12 failed`（rc=1）；
- 12 个失败全部是**开工基线（1 passed / 16 failed）就存在、原因逐字相同**的
  monitor / history / DOM 测试，属 T28/T29/T06 写面，本卡未修、未弱化
  （见 `comparison-baseline-vs-final.json`：`new_failures=[]`，12/12 原因一致）；
- 本卡 T05 面的定向选择运行为 `16 passed / 12 deselected`（rc=0）。

## 证据

### 1. 基线（红）与最终（绿）

| 运行 | 命令（cwd=副本 `packages/multi-workers`） | 结果 | 日志 |
| --- | --- | --- | --- |
| baseline-red | `python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py` | 1 passed / 16 failed，rc=1 | `logs/baseline-red/stdout.txt`、`meta.json` |
| red-01（改测试后、尚未生成随包 case） | 同上 | 12 passed / 15 failed，rc=1（唯一红=`test_shipped_cases_match_the_offline_generator`：8 个目标文件尚无） | `logs/red-01-cases-missing/` |
| red-02/03 | 同上 | 逐步收紧守卫后仍只剩随包文件缺失一项红 | `logs/red-02-two-guards/`、`logs/red-03-shipped-missing/` |
| green-01 → green-08（最终） | 同上 | **16 passed / 12 failed**，rc=1 | `logs/green-08-full-final/stdout.txt` |
| green-07（T05 面定向） | `python -B -m pytest -p no:cacheprovider -q -k "<T05 面用例或式>" test_decision_context_workbench.py` | **16 passed / 12 deselected**，rc=0 | `logs/green-07-t05-face/` |

隔离运行条件（每次运行的 `meta.json` 记录）：private `HOME`/`USERPROFILE`/`TEMP`/`project`、
`PYTHONDONTWRITEBYTECODE=1`、`PYTHONPYCACHEPREFIX=<run tmp>`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、
`-p no:cacheprovider`、`PYTHONUTF8=1`；provider/worker/项目配置环境变量与 proxy 变量全部删除。
`imported-modules.json` 记录实际导入的 `__file__` 全部落在副本内。

### 2. 八 case 的合同事实（生产门，非自证）

- `test_eight_offline_cases_are_complete_schema3_and_contract_shaped`：
  `set(module.CASE_IDS) == set(CASE_FILES)`（恰好八名）、`questions == registry.questions_map(dp)`、
  `book.schema_version == 3`、无 `state`、`material`/`preparation`/`meta(封闭键+真实 role)` 齐全、
  无占位符、`title/note` 不进入 book、发送负载 ≤ `MAX_STATE_BYTES`。
- `test_eight_cases_pass_the_offline_registry_typed_check`：
  `decision_book.check_book(book, repo_root=REPO_ROOT)` **8/8 零 issue**（REPO_ROOT=副本根）。
- `test_case_evidence_is_really_checked_and_resolves_inside_the_copy`：
  每条 `notes.evidence` 都是 `packages/multi-workers/scripts/build_decide_cases.py:<行>`，
  且该行确实含对应材料文本；把同一本书换成空 repo_root 会真的报 `book-evidence`（证明门非空转）。
- `test_each_case_prepares_a_real_basis_for_every_supported_choice`：
  `basis_catalog` 覆盖集合 == 材料真实支持的选择集合；每个 `(choice, basis_id)` 经
  `prepared_request_issues` 零 issue（含 role 门）。
- `test_each_entry_refuses_missing_material_without_defaulting`：八入口分别缺必填项 → `input-incomplete`；
  同项错类型 → `expected string, got int`；缺选择 → `no default candidate is applied`；
  依据与选择不匹配 → `does not apply to the selected choice`。
- `test_dp_w_type_…`：四候选；`images_required=false` 且 `vision_dispatch_issues(..., "vision", "proven")`
  仍报 `requires images_required=true`（图像硬门不被 case 伪造）。
- `test_dp_pm_steer_…`：registry 问题原文（`narrow/split/direct-exec/escalate`，无 `continue`），
  材料 goal/requirements 未缩水。
- `test_dp_w_check_task_…`：三选择全合法；`investigate` 缺有界补证计划被拒；材料无“等待”类同步阻塞。
- `test_dp_sigkey_qg_and_gate_…`：QG `reopen` 缺 `basis_issue` 被拒、`pass` 与 `basis_issue` 互斥；
  gate `pm_note.basis.authority` 缺失被拒；缺选择不默认 approve。
- `test_dp_sign_key_…`：四段材料 + 三数组；`null`/缺失被拒，`[]` 合法（AC-051 区分）。
- `test_dp_auto_…`：三个**自由 id**（非 cN）候选，registry 枚举 == 候选集（无第二份候选副本）、
  候选外 id 被拒、单候选被拒、每个候选都能走通。
- `test_dp_route_…`：七目标可分别选中并给出依据；自路由被拒；材料只有主体/对象/问题三键。
- `test_legacy_cases_stay_byte_identical_read_only_history`：25 个退役 id 全部被生成器拒绝；
  四个旧 case SHA256 与锁值一致；旧 book 在 schema 门被 `book-schema` 拒绝
  （`legacy book contract`/`retired decision point id`，不进入材料解析）。
- `test_generator_refuses_retired_ids_and_never_writes_legacy_cases`：即使把旧 id 注入 `CASE_IDS`，
  `build_case` 先报 retired、`write_cases` 失败且不生成 `dp1.json`。

旧 case 被生产门拒绝的逐条输出：`legacy-case-refusals.txt`（4 × 5 条 `book-schema`）。

### 3. 单源与随包字节

- `after-metadata.json → isolated_generator_run`：真实生成器运行
  `python -B -X utf8 scripts/build_decide_cases.py --out evidence/…/generator-out --quiet`，rc=0，
  只写出 8 个文件名（无 `dp1/2/3/25.json`）。
- `after-metadata.json → shipped_vs_generated`：随包 8 个文件与隔离输出**逐字节相等**（8/8）。
- 随包 8 文件 SHA256（同见 `changed-files.md`）：
  `dp-w-type dfb7ffc9…`、`dp-pm-steer 814e7abf…`、`dp-w-check-task 1908330e…`、`dp-QG 43afee46…`、
  `dp-gate-approve 69e79701…`、`dp-sign-key f089deab…`、`dp-auto 3b8f1f26…`、`dp-route 6f267c83…`。
- 四个旧 case 仍为 `3131c02f…`、`a03e1a29…`、`82ff47e5…`、`bda25144…`（与开工前一致）。

### 4. 写入面完整性

- `mirror-integrity.json`：以 `s2-t05-t10-pre-dispatch-20261027/mirror-inventory.json`（1883 文件）为基线，
  无缺失文件；变化文件共 8 个：本卡 2 个手改文件 + T10 的 4 个文件
  （`decision_lifecycle.py`、`decision_task_state.py`、`decision_wire.py`、
  `test_decision_context_lifecycle.py`、`test_decision_task_state.py`）+ 1 个 pyc 偏差（见下）。
  其余 1875 个文件（含四个旧 case 与 `decide_book_template.json`）逐字节未变。
- `changed-files.md` / `.json`：逐文件 before/after SHA256、字节、±行、diff 路径（表头只用“文件”列名）。
- `diffs/`：两个手改文件的 unified diff（`build_decide_cases.py` +635/−209，20556→39431 B；
  `test_decision_context_workbench.py` +585/−106，74040→95205 B）；8 个新 case 为纯新增。
- `test-function-delta.json`：原 17 个测试函数中 14 个名字与实现保留（仅共享常量
  `CASE_FILES`→`LEGACY_CASE_FILES` 重新指向旧四面），3 个 case 级测试按八入口重命名/重写
  （映射见该文件 `renamed_case_tests`），新增 14 个；没有静默删除。

### 5. 共享读依赖（T10 并行）窗口

`dependency-window.json`：每次运行内 5 个依赖前后哈希一致；`decision_task_state.py`、
`decision_wire.py`、`decision_book.py`、`decision_points.py` 全程未变；
`decision_lifecycle.py`（T10 写面）在运行**之间**变了三次
（`c4122c4627…` 57977B → `11eb7f1189…` 59737B → `426b6c2c6d…` 60155B）。
四种状态下结果完全相同（16 passed / 12 failed、失败集合与原因一致），但这属于**不稳定输入窗口**，
不据此声称最终 qualified；终态以 PM 在两 writer 收口后的新鲜重跑为准。

### 6. AC/VC 对应（只写本面真实可核部分）

| 条款 | 本面证据 | 明确未在此面验证 |
| --- | --- | --- |
| AC-001/VC-001 | 生成器与随包 case 集合**精确八名**、旧编号生成数 0、别名 0 | registry/TS/CLI/观察提交的 `active=8/migrated=6/retired=19/added=2` 全局计数（T03/T04/T28 权威） |
| AC-002/VC-002 | 25 退役 id 生成器全拒；四旧 book 在 schema 门被 retired/legacy 拒绝，材料零解析 | 各运行入口与 replay 的拒绝、`model_calls=0` 实测（T23/T28） |
| AC-003/VC-003 | 生成器不再产出/改写旧 case；旧 4 文件字节不变 | 生产 caller/config/prompt/UI 菜单旧 id=0（T28/T29） |
| AC-004/VC-004 | w-type 四候选+图像硬门、pm-steer 四选择不降目标、w-check 三选择 fire-and-forget、sign-key 四段+三数组；各选择经 pure gate 合法 | 真实入口的正向观测（provider/loopback 提交） |
| AC-013/VC-013 | 旧 case 与历史字节变化 0；旧 book 只读拒绝、不按当前注册补造 | 列表/详情 UI 的 retired 展示（T28/T29/T06） |
| AC-040/VC-040 | route 只选七目标、自路由拒绝、材料仅三键 | `route_releases=0/route_actions=0` 的运行时实测（执行器属 T23/T28） |
| AC-042/VC-042 | auto 自由 id 候选（非 cN）、候选外/单候选拒绝、依据匹配真实材料引用 | 实际动作仍由 PM 执行（本卡无执行器） |
| AC-043/VC-043 | 八入口缺项/错类型/缺选择/依据不匹配逐例可观察失败（4 类 × 8 入口） | 服务不可用、真实入口的“换通道/默认 approve”运行时对照 |
| AC-051/VC-051 | sign-key 三数组 `null`/缺失拒绝、`[]` 合法；`task_before` 的 null/`[]` 投影不属本卡 | task 进展快照的序列化/投影（T10/T06） |

## 改动清单

| 文件 | 变化 | after_sha256 |
| --- | --- | --- |
| `packages/multi-workers/scripts/build_decide_cases.py` | 重写为八入口单源 schema-3 生成器（+635/−209，20556→39431 B） | `7987113fb597f9c8f5d6b48085292cf1a4f8c150839b2fc12efe5d4d4f6ffa70` |
| `packages/multi-workers/test_decision_context_workbench.py` | case 级断言迁移到八入口 + 新增 T05 面用例（+585/−106，74040→95205 B） | `0320702d37146bd856b28e2b102fee2245c67fed15c64349fe0f637c2877dc1b` |
| `packages/multi-workers/decide_cases/dp-w-type.json` | 新增 | `dfb7ffc915a2c1de248629ec1d0a832c84b5d8a2920abc76427fdef60e6ddbf0` |
| `packages/multi-workers/decide_cases/dp-pm-steer.json` | 新增 | `814e7abf4172aba7c6828ab4e117f568ede18c5acf90d342640dc2235c744d10` |
| `packages/multi-workers/decide_cases/dp-w-check-task.json` | 新增 | `1908330e314b3da038c3a0e745504b30885e4717be91ef349c58383fdf3cad9c` |
| `packages/multi-workers/decide_cases/dp-QG.json` | 新增 | `43afee46e192b19a08be5a17260d2a088fa9789594066dca730fdc999273d953` |
| `packages/multi-workers/decide_cases/dp-gate-approve.json` | 新增 | `69e7970144ed7eb2cfd685e035f66872028172d4f594c3cda387b43ce6975ebd` |
| `packages/multi-workers/decide_cases/dp-sign-key.json` | 新增 | `f089deabae264503f096406cf42cd909bddbeab23b80dc13eea194ceaf81e408` |
| `packages/multi-workers/decide_cases/dp-auto.json` | 新增 | `3b8f1f267ebf50bb88b015efb53c5f7783e07e2763d3a157109060f8d36890a9` |
| `packages/multi-workers/decide_cases/dp-route.json` | 新增 | `6f267c83a2dd704a17b48583d8a2c2380a6cdfdec2534797ab206424a49510d5` |

未改（有意）：`decide_book_template.json`（`book new` 的 dp3/dp6 骨架，被
`test_decision_book.py::test_decide_book_template_is_book_new_output` 与
`test_decision_input_contract_migration.py` 双向钉住；改它等于越界修改他卡断言）；
四个旧 case；任何 monitor/dashboard/history/registry/TS 文件。

## 残留与未验证

1. **整文件 suite 仍红 12 项（非本卡引入）**：11 项因 monitor 固定 case 表仍是旧四名 +
   `_validate_case` 仍是 schema-2（`case-invalid: the case names an unregistered decision point`，503），
   1 项因 `decision_history` 对旧 dp2 不再投影 `question_summary`。原因与基线逐字一致
   （`comparison-baseline-vs-final.json`），属 T28（monitor）/T29（dashboard）/T06（history）写面；
   八入口 case 路由迁移与旧 id 菜单下线仍未做。
2. **八 case 未经真实入口提交**：本卡只走生产 `check_book` + pure protocol gate；没有 provider、
   没有真实 loopback submit、没有 CLI 决策调用、没有服务探针（卡内禁止）。
3. **T10 依赖窗口不稳定**：`decision_lifecycle.py` 在两次运行之间变化，见上文 §5；
   最终资格需 PM 在 T05/T10 都收口后新鲜重跑。
4. **pyc 偏差（真实、已披露）**：`__pycache__/decision.cpython-314.pyc` 由一条未带 `-B` 的临时探针
   刷新为新哈希；13/14 受保护 pyc 未变；源 `decision.py` 哈希未变；原始字节不可得、未做无意义回写。
   详见 `pyc-deviation.md`。
5. **未运行**：`npm run check`（T32 串行保护）、T04 的 `gen_decide_registry_ts.py --check`、
   `mw.py` CLI/观察提交、任何 build/install/restart/commit/push。
6. **L2 层未证**：VC-001/002/003/013/040/042/043 的运行时计数（aliases/model_calls/releases/
   actions/failed_entries 等）只有在 T23/T28 接线后才可观测；本文件只给出**case/生成器/schema 面**的事实。
   `human/H12` 资格、真实 vision 能力、发布回移仍未证。
7. `MAX_STATE_BYTES` 预算按当前 8 个 case 自检通过（生成器会硬失败），但没有在真实发送帧上复测。

## 上下文来源

- 本卡：`workers/dpc-t05-eight-cases/task.md`（含隔离实施覆盖与 AC/VC 合同）；
  同源卡副本 `evidence/implementation/s2-t05-t10-pre-dispatch-20261027/T05-card.md`。
- 目标/规格/设计：`goal.md:5`、`spec.md:128`、`design.md:201`（本卡引用，未改）。
- 上游交接：`evidence/implementation/t09-r2-pm-handoff-20261027/report.md`、
  `evidence/implementation/s2-t05-t10-pre-dispatch-20261027/{check.json,frontier.json,remaining-seam-owner-map.json,pyc-protection.json,mirror-inventory.json}`、
  `evidence/implementation/isolation-baseline-20261026/`、`implementation-isolation.md`。
- 产品源码（副本内，已完整读到 EOF）：`scripts/build_decide_cases.py`（旧 475 行）、
  `test_decision_context_workbench.py`（旧 1795 行）、`decide_book.py`、`decision_points.py`、
  `decision_book_template.json`、四个旧 case。
