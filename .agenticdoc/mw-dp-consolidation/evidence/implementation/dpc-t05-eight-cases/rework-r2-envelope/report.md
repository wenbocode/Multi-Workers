# T05-R2-envelope — 八入口模板与准备时间出处（信封修正后重执行）

## 结论

**两根因都在授权产品面内真实修复，局部验证绿；原整文件 suite 仍是 12 失败，整体 L2/QG/签收未做，终态待 PM 复验/ack。**

- 根因 1（模板）：`decide_book_template.json` 不再携带 schema2 的 `dp3-worker-clarify`/`dp6-qg-verdict` 活模板，改为由真实 `decision_book.scaffold_book(dp)` 派生的八入口 schema3 骨架（8 本、无 `meta`、无 `state`/`questions_version`、material/preparation/evidence 全为占位符，`check_book` 仍拒绝 → 是待填骨架，不是有效请求也不是授予身份）。
- 根因 2（准备时间）：`CASE_PREPARED_AT` 由未来值 `2026-10-27T20:56:00+00:00` 改为**一次真实记录**的 `2026-10-27T13:45:28+00:00`（明确 UTC `+00:00`、冻结常量、不读 wall-clock、不用 run-start 回填、不改旧证据），并在注释与证据中原样声明它只是这套**合成 fixture 的编写时刻**，不是真实决策准备/授权发生过。八个随包 case 各只改这一行。
- 验证分界（不混写）：
  - 实现：完成（11 个面内产品）。
  - 局部验证：**绿** — 新两根因 focused 2 passed/rc=0；生产 gate 8/8 `check_book` 零 issue、逐 supported choice + basis 零 issue、8 case 私有 out 逐字节相等、四旧 case 字节不变、14 pyc 不变。
  - 原整文件验收：**仍红** — `12 failed, 18 passed`，rc=1，12 项与 T05 最终基线**同名同集**（monitor/history/DOM，owner T27/T28/T29，本轮未弱化、未改、未修）。18 = 原 16 绿 + 本轮 2 个新回归。
  - 整体 QG/S2/L2/check(仅 T32)/reviews/signoff：**未做**。

## 证据

所有路径为完整 canonical 路径，根 `H:\git\Multi-Workers`。证据根 `...\.agenticdoc\mw-dp-consolidation\evidence\implementation\dpc-t05-eight-cases\rework-r2-envelope\`（下称 `EV`）。

**1. 入场自检（信封修正是否真的到位）**

- `EV\readonly-protection.json`
  - `write_face_entries: 12`；前 11 条逐字等于卡 frontmatter 的 11 个产品，第 12 条是本 attempt 自己的 `...\rework-r2-envelope\**`；`eleven_products_plus_own_evidence: true`、`evidence_glob_is_own_attempt_dir: true`。
  - `card.sha256 = 49ebb4b47c610493632647c386e0c7f3feee1805924a83736a321584dd52394d`，与 `...\workers\dpc-t05-eight-cases-r2-envelope\task.md` 头 `card_sha256` 相同（`matches: true`）。
  - 未绕守卫、未改 task.md/卡/parser、未用 `allow_foreign_write`。

**2. fresh before（信封修正后的当前真实 11 文件，非从主树/旧 before 复制）**

- `EV\before-metadata.json` + `EV\before-bytes\**`：11 产品 bytes/SHA256/LF/CRLF/trailing byte 与原始字节副本。
- `EV\fresh-before-check.json`：11 产品 SHA 与 PM `t05-r2-envelope-pre-dispatch-20261027\before-metadata.json` **逐条相同**（`products_match_pre_dispatch: true`）；四旧 case SHA 等于 test 内锁值（`legacy_cases_match: true`）；T10 五文件 SHA 等于 PM `T10-products-protection.json`（`t10_matches: true`）；`inventory_file_count: 1891`、`pyc_count: 14`、`test_function_count: 28`。
- `EV\test-functions-before.json`：28 个 `test_` 函数的 `lineno/end_lineno/args/decorators/assert_count/ast_sha256/source_sha256` 与完整 source。
- 编码前已把 11 产品（`scripts\build_decide_cases.py` 902 行、`decide_book_template.json` 61 行、`test_decision_context_workbench.py` 2274 行、8 个 case 文件）分段读到实际 EOF（2274 行末为 `test_shipped_assets_keep_csp_textcontent_and_token_discipline` 收尾）。

**3. 真实红（先红，后实现）**

- `EV\logs\red-two-root-causes.{stdout,stderr,meta.json}`，argv `python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py -k "shipped_book_template_is_the_native or case_prepared_at_is_a_recorded"`，`rc=1`，`2 failed, 28 deselected`：
  - `AssertionError: the template must name the eight active entries, not the retired two`（左集 `{'dp3-worker-clarify','dp6-qg-verdict'}`）。
  - `AssertionError: prepared_at 2026-10-27T20:56:00+00:00 is in the future: it cannot claim a preparation that already happened`（观测 13:45:13Z）。
- 两根因红来自产品真实行为，不是 scope 故障伪造；红日志完整保留。

**4. 实现（定点，两处源码）**

- `...\packages\multi-workers\scripts\build_decide_cases.py`：
  - `CASE_PREPARED_AT = "2026-10-27T13:45:28+00:00"`，注释改写为“记录式、UTC 明确、冻结、非真实准备/授权证据”（保持 4 行注释，材料定义的 `path:line` 未漂移）。
  - 新增 `TEMPLATE_PATH` / `build_template()`（`{"books": {dp: decision_book.scaffold_book(dp)} for dp in CASE_IDS}`）/ `render_template()` / `write_template()`，以及 CLI `--template-out`（不改变验收命令行）。
- 时间出处记录：`EV\prepared-at-record.json`（`recorded_at_utc=2026-10-27T13:45:28+00:00`，读法 `datetime.now(timezone.utc)` 截到秒，`explicit_zone=+00:00`，`clock_source`、`meaning`、`not_evidence_of`、`frozen_into`、`wall_clock_per_run=false`、`backfilled_from_run_start=false`）。
- 模板整形：`...\decide_book_template.json` 现为 `{"books": {8 个活入口}}`，每本 `== decision_book.scaffold_book(dp)`、`schema_version=3`、无 `meta`、`material.review_evidence=[]` 之类按 registry 类型占位、`prepared_at="<待填: ISO-8601 含时区>"`。

**5. 绿（同一断言）**

- `EV\logs\focused-green-window.{stdout,stderr,meta.json}`：同一条 `-k` 命令 `rc=0`，`2 passed, 28 deselected`；`T10_dependency_window_stable: true`。（`EV\logs\green-two-root-causes.*` 为第一次绿，随后一次微调见“残留与未验证”第 5 条。）
- 生产 gate（独立于 PM probe，未改它）：`EV\product-check.json`
  - 8/8 `decision_book.check_book(book, project_dir=<EV>\fixture\project, repo_root=<implementation-worktree>)` 零 issue；
  - 逐 supported choice × basis：`prepared_request_issues == []`（choices 4/4/3/2/4/3/3/7）；
  - 8 随包 case 与私有 generator out **逐字节相等**；`case == build_case(dp)`；
  - `prepared_at_future_cases: []`，全部 `+00:00`；
  - 模板 `books` 8 本、`schema_version=[3]`、`failures: []`、每本被 `check_book` 拒绝（骨架）；
  - 四旧 case SHA 不变（`3131c02f…`、`a03e1a29…`、`82ff47e5…`、`bda25144…`）。
- 生成命令（验收命令 2）：`EV\logs\generate-private-out-final.*`，`python -B -X utf8 scripts/build_decide_cases.py --out <EV>\fixture\generator-out --quiet`，`rc=0`，只写 8 文件，bytes 3079/4089/4622/2991/4750/3825/4747/3994；重复执行幂等（产物与随包字节仍相等）。

**6. 原整文件验收（真实运行，真实 rc）**

- `EV\logs\full-workbench-suite-window.{stdout,stderr,meta.json}`：`python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py`，`rc=1`，`12 failed, 18 passed`，`T10_dependency_window_stable: true`。
- 12 个失败与 T05 最终基线完全同名（`...\dpc-t05-eight-cases\comparison-baseline-vs-final.json` 的 `remaining_failures`）：`test_case_loader_refuses_…`、`test_case_route_is_page_authenticated_…`、`test_case_route_makes_zero_credential_…`、`test_edited_cases_reach_…`、`test_history_forwards_…` + 7 个 `test_dom_*`。`new_failures` 为空。

**7. 28 原函数不变 + 2 只追加**

- `EV\test-function-delta.json`：`before_count 28` / `after_count 30`；`original_28_all_ast_and_source_identical: true`（`ast_sha256` 与 `source_sha256` 全同）、`original_28_all_locations_identical: true`（`lineno/end_lineno` 也全同）、`removed: []`、`added: [test_case_prepared_at_is_a_recorded_past_instant_with_explicit_zone, test_shipped_book_template_is_the_native_eight_entry_scaffold]`、28 个函数 `assert_count` 前后相等。
- `EV\full-diff.patch`：test 文件单 hunk `@@ -2272,3 +2272,97 @@`，**0 删除行**（纯追加）。

**8. inventory / pyc / 面外**

- `EV\changed-files.json`：`1891 → 1891` 文件（无新增/删除），`changed` 恰为 11 个声明产品，`outside_declared_face: []`；`pyc_unchanged: true`，14 个 pyc 前后同名同 SHA（含原 1 个历史漂移，未清理/未回填/未重取基线）。
- 四旧 case、T10 五产品/两 tests、PM negative/check/probe、`pm-state.md`、两份 DAG、原 T05/T10 证据、坏 R2 证据：`EV\readonly-protection.json` 记录 30 个只读文件 SHA，均未写。

**9. 隔离纪律**

- 每条 Python 调用都是 `PYTHONDONTWRITEBYTECODE=1` + `-B`（`tools\*.py` 内 `assert sys.dont_write_bytecode`）；cwd=副本 `packages\multi-workers`；`EV\logs\*.meta.json` 记录 argv/cwd/rc/env/python。
- 环境：私有 `EV\fixture\{home,userprofile,temp,tmp,tmpdir,project,appdata,localappdata}`；剥离凭证/provider/代理变量；`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`PYTHONHASHSEED=0`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`（无插件 autoload）、`-p no:cacheprovider`（无 pytest cache）、`NO_PROXY=*`。
- 工具脚本内 `socket.connect/connect_ex/create_connection` 全部抛错（禁真实网络/provider/决策 CLI/服务）；无 loopback submit、无多行 `python -c`、无外部 OS sink、未改任何 guard。
- import 根：`EV\logs\import-roots.stdout` 显示 `decision_book/decision_wire/decision_lifecycle/decision_task_state` 的 `__file__` 与父目录都在副本内（`inside_copy: true`）。

## 改动清单

产品（11 个，全部在声明写面内；`before → after` 全 SHA）：

| 文件 | 动作 | bytes | before sha256 | after sha256 |
| --- | --- | --- | --- | --- |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\scripts\build_decide_cases.py` | 改（`CASE_PREPARED_AT` + 模板派生函数/`--template-out`） | 41082 | `7987113fb597f9c8f5d6b48085292cf1a4f8c150839b2fc12efe5d4d4f6ffa70` | `4ac24aaa1e5e811b5f4019c550dfb96780b977e7545571cf6e3cd47d1f69cc5c` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_book_template.json` | 改（schema3 八入口骨架，`scaffold_book` 派生） | 12168 | `755253b61429271b4eb1fc5cb22cc2fb4e77a7fce07e7a67aa111dd896640df2` | `1cde56dfc814afd36e2b49d610e25e25be33561b2755ebf373a0f54e3802545e` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\test_decision_context_workbench.py` | 改（仅追加 2 个回归测试） | 100533 | `0320702d37146bd856b28e2b102fee2245c67fed15c64349fe0f637c2877dc1b` | `d221b9c8930bc9e48d661739843991ec4207c6b69b8ec774004641e9cf8f912c` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-w-type.json` | 再生成（仅 `prepared_at`） | 3079 | `dfb7ffc915a2c1de248629ec1d0a832c84b5d8a2920abc76427fdef60e6ddbf0` | `f70b5aa699d2636105107d98453852b0b81aa504ec691fdeda79b44fb5247758` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-pm-steer.json` | 再生成（仅 `prepared_at`） | 4089 | `814e7abf4172aba7c6828ab4e117f568ede18c5acf90d342640dc2235c744d10` | `6a8b946557d9d381707def7360691126f85e195495163f3ef0ba6bfff9f5967b` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-w-check-task.json` | 再生成（仅 `prepared_at`） | 4622 | `1908330e314b3da038c3a0e745504b30885e4717be91ef349c58383fdf3cad9c` | `e88fb31a167335824a5bd6f338ec3e0da9387d8b5e1299ce1de9fd94a1b1f7bb` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-QG.json` | 再生成（仅 `prepared_at`） | 2991 | `43afee46e192b19a08be5a17260d2a088fa9789594066dca730fdc999273d953` | `aacd487769caf4dceab0513b483d73c762da1d0d9914a1bfe3c6d201b1e10eb3` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-gate-approve.json` | 再生成（仅 `prepared_at`） | 4750 | `69e7970144ed7eb2cfd685e035f66872028172d4f594c3cda387b43ce6975ebd` | `269f07c212be2f8a9de6c3f8b7f180588133650890690dcbd1f1074287cfd67a` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-sign-key.json` | 再生成（仅 `prepared_at`） | 3825 | `f089deabae264503f096406cf42cd909bddbeab23b80dc13eea194ceaf81e408` | `4462e8163b6aaf6af0251eb3f6b10fd0e9571e4f71b878f791048d4e594fd232` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-auto.json` | 再生成（仅 `prepared_at`） | 4747 | `3b8f1f267ebf50bb88b015efb53c5f7783e07e2763d3a157109060f8d36890a9` | `b80e93a52a7e07947efd9d758e379deb09c5683d4ff7d1f09261da16ec3a75ef` |
| `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\decide_cases\dp-route.json` | 再生成（仅 `prepared_at`） | 3994 | `6f267c83a2dd704a17b48583d8a2c2380a6cdfdec2534797ab206424a49510d5` | `91569d4d576622da48f8b16995fd3e27da5744a90788600cda1cb46189e5a230` |

本 attempt 自己的证据文件（全部新增，均在 `...\dpc-t05-eight-cases\rework-r2-envelope\` 下）：

| 文件 | 内容 |
| --- | --- |
| `readonly-protection.json` | 入场写面 12 条、card SHA 匹配、30 个只读面文件 SHA |
| `before-metadata.json` | 11 产品 + 4 旧 case + T10 五文件 bytes/SHA/EOL |
| `before-bytes\packages\multi-workers\**` | 15 份原始字节（11 产品 + 4 旧 case） |
| `test-functions-before.json` / `test-functions-after.json` / `test-function-delta.json` | 28 函数 AST/source/lineno 基线、现状与 delta |
| `inventory-before.json` / `inventory-after.json` | 1891 文件 SHA 快照 |
| `pyc-before.json` / `pyc-after.json` | 14 pyc SHA 快照 |
| `fresh-before-check.json` | 与 PM pre-dispatch/T10 保护/四旧 case 的逐条比对 |
| `prepared-at-record.json` | 唯一一次时间读取记录（值、时区、语义、不冒充范围） |
| `product-check.json` | 生产 gate 复验（8 case、模板、四旧 case） |
| `case-install.json` | 8 随包 case 与私有 out 逐字节相等的安装记录 |
| `changed-files.json` / `full-diff.patch` | 增量清单与完整 unified diff |
| `logs\*.{stdout,stderr,meta.json}` | 红/绿/整文件 suite/生成/import 根/audit 的完整 argv、rc、环境、T10 依赖窗口 |
| `tools\*.py` | 取证脚本：`run_isolated.py`、`capture_before.py`、`verify_fresh.py`、`record_prepared_at.py`、`install_cases.py`、`verify_products.py`、`audit_after.py`、`readonly_protection.py`、`show_import_roots.py` |

## 残留与未验证

1. **原整文件 suite 仍红**：`12 failed, 18 passed`，rc=1。12 项是 monitor/history/DOM 的历史失败（owner history=T27，monitor/playground=T28，web=T29），本轮**未修、未删、未 skip/xfail、未弱化**；其根因归属沿用原 `comparison-baseline-vs-final.json` 的 log，本轮没有重新溯源，也没有把 scope 故障算成产品 red。完整消费者迁移与最终共享 suite 需 PM 协调。
2. **未跑的验证**：其它 test 文件、决策 CLI、服务/loopback submit 探针、真实 provider/网络、`npm run check`（仅 T32 PM-direct）。未做真实浏览器可见性与真实模型选择质量的端到端验收。
3. **未做的流程**：S2/L2/check/reviews/QG/signoff 全部未做；本轮只是“实现 + 局部验证 + 原 suite 真实 rc”。终态需要 PM 吸收 ack 后用原 `t05-pm-handoff-20261027\probe.py`（未改）在新证据目录重跑复验，再按原 36 任务 DAG 判定。
4. **PM probe 本体未运行**：按卡要求不改 PM 原 probe/check/report；本轮用 `EV\product-check.json` 做等价独立复验（同 `check_book`/`prepared_request_issues`/`_schema_issues`/`scaffold_book`），因此“PM 在新目录重跑”这一步仍是未验证项。
5. **过程偏差（如实记录）**：第一次绿尝试时新模板测试在 `dp-auto` 处失败——`scaffold_material` 的 `handling_options=[]` 让 `check_book` 先在 `book-state` 提前返回，而不是我最先假设的 `book-placeholder`。我把**自己新写的**那条断言从“必须出现某个 issue code”改成“必须被 `check_book` 拒绝 + 逐个 required path / preparation / evidence 仍是占位符”，这属于修正新测试的错误假设，不是弱化任何原断言（28 个原函数 AST/source/lineno 与 assert 数全同，见 `test-function-delta.json`）。
6. **T10 依赖窗口**：红那一轮尚无窗口工具，未记录其 before/after；窗口稳定记录在 focused-green 与最终整文件 suite 两轮（`T10_dependency_window_stable: true`），且 T10 五文件 SHA 自入场起等于 PM pre-dispatch 保护值，未变。
7. **pyc**：14 个现存 pyc 保持原状，其中原 1 个历史漂移仍在；未清理、未回填、未重取基线以抹偏差。
8. **未定义的未知**：`prepared_at` 的“真实”只到“本 attempt 实际读取到的合成 fixture 编写时刻”这一层；它不证明任何真实决策准备或授权发生——这一点已写进注释、常量记录与测试 docstring，PM 若要求改成纯合成标记（如固定纪元值）需另行决定。

## 上下文来源

- 卡：`H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\tasks\isolated\T05-eight-cases-r2-envelope.md`（`write_face` 11 产品 + 本 attempt 证据）、业务全文承接 `tasks\isolated\T05-eight-cases-r2.md`、原逻辑 `tasks\isolated\T05-eight-cases.md`。
- 派发：`...\workers\dpc-t05-eight-cases-r2-envelope\task.md`（header 12 条写面、`card_sha256`、decision `dp1-dispatch-type:53a97714-b886-4f6e-8a98-6042a96e1410`）。
- 目标/规格/设计：`.agenticdoc\goal.md:5`、`.agenticdoc\mw-dp-consolidation\spec.md:128`、`design.md:201`。
- PM 真实缺陷与正例（只读）：`...\evidence\implementation\t05-pm-handoff-20261027\{report.md,check.json,probe.json,probe.py}`、`...\t05-r2-envelope-pre-dispatch-20261027\{check.json,carrier.json,before-metadata.json,T10-products-protection.json,T05-R2-envelope-card.md}`。
- 原 attempt 与信封故障（只读）：`...\workers\dpc-t05-eight-cases\{run.json,output.md,trace.log,worker.log}`、`...\dpc-t05-eight-cases\{report.md,before-metadata.json,comparison-baseline-vs-final.json,pyc-deviation.md}`、`...\dpc-t05-eight-cases\rework-r2\{report.md,blocker\face-mismatch.json,blocker\guard-refusal.json}`。
- 契约/产品源码（只读，除上述 11 个面内产品）：`...\packages\multi-workers\decision_book.py`（`BOOK_SCHEMA_VERSION=3`、`scaffold_book/scaffold_material/scaffold_preparation/scaffold_context`、`_schema_issues`、`check_book`、`is_placeholder`、`PREPARED_AT_PLACEHOLDER`）、`decision_points.py`（`ENTRY_ROLES`、`prepared_request_issues`、`preparation_issues`、`resolve_entry_choices`、`entry_material_issues`）。
