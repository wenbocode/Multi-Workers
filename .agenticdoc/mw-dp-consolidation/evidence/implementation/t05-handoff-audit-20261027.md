# T05 交接只读补核（dpc-t05-handoff-audit）

## 结论

12 项失败全部是 T05 改动之前就已存在的失败，不是 T05 的回归：`logs/baseline-red/stdout.txt` 为 `16 failed, 1 passed`，`logs/green-08-full-final/stdout.txt` 为 `12 failed, 16 passed`，当前 R2-envelope 窗口为 `12 failed, 18 passed`；当前 12 项是 16 项的真子集，且失败文本逐项相同（`comparison-baseline-vs-final.json.remaining_with_changed_reason = []`，`new_failures = []`）。

但"两根因/三个历史 owner"这种口号不成立。按实际调用链只有**两个 production 面 + 一个 test 面**：

- **11 项**（4 项直连 + 7 项经同一 helper）= 一条链：`decision_monitor.CASE_IDS` 仍只登记 4 个已退役 id（`decision_monitor.py:208-213`），而只读 case shell 的校验走的是活动 registry 门（`decision_monitor.py:378-380` → `decision_points.py:1842`/`1384`/`1367`），于是 `GET /api/test/cases` 恒 503 `case-invalid`。
- **1 项**（history）= `_question_table` 只覆盖活动 dp（`decision_history.py:2168-2198`），fixture 却用退役 `dp2-checkpoint-split` 造 v2 记录（测试 `1145-1149`），`_question_summary`（`2201-2220`）只能返回 None。

owner 以写面为准，不以报告口号为准：`decision_monitor.py` 在 T28 write_face、`decision_history.py` 在 T27 write_face、`test_decision_context_workbench.py` 在 T05 write_face；`decision_points.py` 属 T03，其 retire 行为是 AC-002/VC-002 明确要求的正确行为，回退它才是缺陷。**T29（web 资产）在这 12 项里没有任何失败证据**：7 个 DOM 测试都在 `_workbench_dom_payload` 的 `1800` 行 abort，node 从未执行，"DOM 债"是误判。

验证顺序：DAG 本身无环（见 §3）；但"T05 完成 ⟺ 整文件 rc=0"这个读法确实构成循环——12 项需要的两个 writer 都在 T05 下游（T28 显式 dep T05；T27 经 T18 dep T05），且两者都不能改 workbench 测试。T05 原卡写明"修改原 workbench 断言仅为新八入口衔接，原既有失败 fixture/原因保留"，因此存在不擅改 DAG、不降最终验收的合法出口：**现在按"八入口面已完成 + 12 项具名保留"收口 T05，把整文件绿保留为 S2 关闭/T31/T36 的必须验收项**（候选与权限影响见 §5）。

R2 runner 纪律：`run_tool` 是白名单 env + 进程内禁 socket（`run_isolated.py:108-131`/`99-105`）；`run_exec`（pytest）只是"继承减 DROP"（`75-96`/`133-164`），且 socket patch 不会进入子进程。实证：`logs/full-workbench-suite-window.meta.json` 的 `env` 里实际出现 `TAI_PAT_TOKEN`、`PI_*`、`UE_HORDE_URL`。suite 自身没有网络拒绝，也没有全局 fake backend（只有 `MonitorDeps(playground=…)` 这类逐调用注入 seam）。因此"零凭证/零模型"是**该测试自己的断言**，不是 harness 保证。

## 证据

### 1. 真实 EOF 与实跑记录（本次只读范围）

| 对象 | 实际读到 | 结论 |
| --- | --- | --- |
| `implementation-worktree/packages/multi-workers/test_decision_context_workbench.py` | 1–2368 行全部（`100533` bytes，`(Get-Content).Count = 2368`） | 30 个 test 函数；旧 28 函数 + 追加 2 个；已到 EOF |
| `rework-r2-envelope/logs/full-workbench-suite-window.stdout` | 全文件 553 行到 EOF（末行 `12 failed, 18 passed in 2.51s`，`29869` bytes） | 失败原文完整，含 12 段 traceback 与 short summary |
| `rework-r2-envelope/tools/run_isolated.py` | 全文件到 EOF | 见 §4 |
| `rework-r2-envelope/logs/full-workbench-suite-window.meta.json` | 全文件 | rc=1；`T10_dependency_window_stable: true`（5 个 T10 输入前后 hash 全同）；env 名单见 §4 |
| `dpc-t05-eight-cases/comparison-baseline-vs-final.json` | 全文件 | 12 项原因与基线逐项相同 |
| `logs/baseline-red/stdout.txt` | 仅 short summary + 关键失败文本 grep（**未读全文**） | `16 failed, 1 passed`；case-invalid 文本与当前一致 |
| `logs/green-08-full-final/stdout.txt` | 仅 short summary（**未读全文**） | `12 failed, 16 passed`，12 项名次与当前一致 |
| `decision_monitor.py` | 仅读 200–220/339–391/375–382/1495–1510/1910–2010 段与 grep | **未读 EOF（3102 行）**，结论限这些段 |
| `decision_history.py` | 仅读 2140–2240/2160–2170/2198–2204/2678–2684/3290–3298 段与 grep | **未读 EOF（4210 行）** |
| `decision_points.py` | 仅读 754–840/1330–1410/1800–1870 段与 grep | **未读 EOF（5694 行）** |
| `scripts/build_decide_cases.py`、`decide_book_template.json` | 未读 | 12 项失败测试没有一个执行 generator/template（失败点先于或无关它们），故本结论不依赖其内容 |

- 12 项失败测试中没有任何一项调用 `_generator_module()`/`build_cases()`/模板，R2 的"模板=8 本 scaffold / prepared_at 无未来值"两根因修复与本 12 项无因果关系。
- 既有事实保留：14 个 pyc、其中 `decision.cpython-314.pyc` 一次历史漂移（`e4b51f5b…`→`b95f933d…`，`pyc-deviation.md` 自述由一条未加 `-B` 的探针造成；`decision.py` 源码字节未变 `ef9c2c68…`）。该窗口 argv 带 `-B`、env 带 `PYTHONDONTWRITEBYTECODE=1`，与该窗口 pyc 不变一致，但不洗白此前越面写。

### 2. 12 行根因 / owner 表

| # | 测试（def 行） | 断言/失败行 | 实际异常 | fixture → production call → 失败点 | 根因 path:line | owner | 最小必要修改路径 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `test_case_loader_refuses_unknown_ids_traversal_and_symlinks` (1053) | 1068 | `CaseError: case-invalid: the case names an unregistered decision point`（前 4 组 bad-id/`case-unknown`/`case-unsafe` 断言已通过） | tmp 固定名拷贝 `decide_cases/dp1.json` → `decision_monitor.load_case("dp1-dispatch-type", cases_dir=good)` → `_validate_case` → `question_override_issues` → `require_active_dp` | `decision_monitor.py:378-380`；`decision_points.py:1842`→`1384`→`1367`（退役 dp1） | T28（读壳校验绑活动门）；T05（1054/1057 固定旧表） | T28 把"退役只读壳的 questions 校验"与 submit/validate 的活动门分开；旧表断言由 T05 在 T28 契约落地后迁移 |
| 2 | `test_case_route_is_page_authenticated_and_serves_only_fixed_ids` (842) | 860（401/403 已过） | 同一 503 信封 | `GET /api/test/cases` → `_act_test_cases` `1943 load_case(dp)` → 同链 | 同上 + `decision_monitor.py:1941-1946`（`case-invalid`→503） | T28 + T05（862 断言列表==旧 4 名） | 同上；`?dp=` 白名单与 400/404/405 语义要随新表一起定 |
| 3 | `test_case_route_makes_zero_credential_and_model_calls` (914) | 941 | 同一 503 信封（两条 path 都失败） | 同 #2；`decision.credential_snapshot` 被 monkeypatch 成 raise（927-930）但未被执行到 | 同 #2 | T28 + T05 | 同 #2；"零凭证/零模型"断言可原样保留 |
| 4 | `test_edited_cases_reach_the_real_loopback_typed_validate` (987) | 1008 | 同一 503 信封 | 同 #2；`POST /api/test/validate` 的 edited-book 段**未执行** | 同 #2 | T28 + T05 | 同 #2；validate/observe 段在 #2 修好后才有证据 |
| 5 | `test_dom_workbench_table_has_five_columns_four_states_and_facet_dropdowns` (1914) | helper 1800（调用点 1915） | 同一 503 信封，DOM 未运行 | `_workbench_dom_payload`(1775) → `GET /api/test/cases`(1799-1800) → 同链 | 同 #2；DOM 期望见 1954（`继续` in alpha_row） | T28 主因；T29 **无证据**；T05 断言 | 同 #2；修好后需重跑才能知道 DOM 断言是否还需要迁移 |
| 6 | `test_dom_legacy_payload_without_facets_never_fabricates_the_universe` (1971) | helper 1800 | 同上 | 同上 | 同上 | 同上 | 同上 |
| 7 | `test_dom_v2_record_opens_ten_node_dag_and_legacy_record_stays_log_only` (1993) | helper 1800 | 同上 | 同上 | 同上 | 同上 | 同上 |
| 8 | `test_dom_incomplete_dag_projection_is_reported_not_filled` (2062) | helper 1800 | 同上 | 同上 | 同上 | 同上 | 同上 |
| 9 | `test_dom_offline_case_loads_and_local_validate_makes_no_network_write` (2092) | helper 1800 | 同上 | 同上；另有 `caseOptions == ["", *LEGACY_CASE_FILES]`(2116) 与 `setValue dp3-worker-clarify`(2104/2150) 固定旧 id | 同上 + 测试 2104/2116 | T28 主因；T05 断言 | 同 #2；`case-select` 的 id 集合随新表迁移 |
| 10 | `test_dom_local_validate_refuses_placeholders_and_incomplete_material` (2134) | helper 1800 | 同上 | 同上 | 同上 | 同上 | 同上 |
| 11 | `test_dom_playground_submit_stays_observe_only_and_retry_points_at_the_previous_id` (2169) | helper 1800 | 同上 | 同上；`dp1.json` book 直接进编辑器段落未执行 | 同上 | T28 主因；T05 断言 | 同上 |
| 12 | `test_history_forwards_the_real_workbench_and_facets` (1183) | 1228 | `AssertionError: the registered question is projected` / `assert None` | `_seed_workbench_records`(1100) 用退役 `dp2-checkpoint-split` 写 v2 lifecycle+archive（1145-1149）→ `GET /api/history` → `_workbench` `2682 summary=_question_summary(dp)` → `_question_table` `2168-2198`（只取 `registry_snapshot()["points"]`）→ 退役 dp 不在表内 → None | `decision_history.py:2168-2198`、`2201-2220`、`2682`、`3296`；fixture `test:1145-1149` | T27（投影口径）；T05（fixture+断言） | T27 决定退役 dp 的诚实话术（"退役/未记录"，**不回填**问句）；T05 相应迁移断言，若要保留 AC-013 覆盖则另补一条退役记录"明确退役"的断言 |

补充事实（避免误判）：

- 11 项的 503 是**生产路径的唯一最早失败点**；`/api/test/validate`、`/api/test/submit`、node DOM harness 在后，均无本轮证据。
- `test_case_loader_...` 的失败位置是"注入目录里的固定名拷贝"，即该测试的 containment 证明段；`_case_file_path` 的 containment/symlink 逻辑本身在本轮未暴露缺陷。
- `LEGACY_CASE_FILES`（92-97）与 4 个旧 case 的 sha256（`LEGACY_CASE_SHA256` 100-105）都是测试内常量；旧 case 字节未被动过（`test_legacy_cases_stay_byte_identical_read_only_history` 本轮通过）。
- 12 项里没有任何一项断言"退役 id 可提交"；它们断言的是"退役 case 可被只读列出/加载"，与 AC-002 的"不可调用"并不互斥——这是 T28 契约必须显式区分的地方，也是不能靠回退 T03 来"修绿"的原因。

### 3. 实际依赖链与验证顺序循环

DAG 事实（`implementation-isolated-dag.json`，本次用只读 JSON 解析核对）：

- `T05.deps = [T03, T04, T09]`，`T05.status = running`，`T05.commands = pytest test_decision_context_workbench.py`（即本 30 项整文件）。
- `T11/T12/T17/T18.deps` 均含 `T05`（+`T10`）；`T18.deps = [T05,T06,T07,T08,T09,T10,T17]`。
- `T19/T26` ← `T18`；`T27.deps` 含 `T18`（⇒ T27 **传递依赖 T05**）；`T28.deps` 显式含 `T05` 与 `T27`；`T29/T30` 更下游。
- 无环：除 `T05→T09`（T09.deps=[T03,T04,T08]，不回头）外，所有边都指向 id 更大的节点；无 dangling dep。**DAG 本身无环。**
- 写面对照（原卡 frontmatter）：`decision_monitor.py`+`test_decision_monitor.py` → T28；`decision_history.py` → T27；`test_decision_context_workbench.py` → T05；`decision_points.py` → T03。

循环判定：**只有"T05 完成 ⟺ 整文件 rc=0"这一读法有循环**——12 项的修复点在 T27/T28 的写面，而 T27/T28 在 DAG 上都在 T05 下游，且两张卡都不许改 workbench 测试；T05 要绿就必须先让别人先改 → 反了。资格策略本身不是循环，因为 T05 原卡给了窄读法（"修改原 workbench 断言仅为新八入口衔接，原既有失败 fixture/原因保留"），且 baseline-red(16F1P)→green-08(12F16P) 证明这 12 项确实是既有失败。因此：不擅改 DAG、不降低最终验收的前提下，**窄读法是合法的，前提是 12 项被具名、带 owner、带重新验证时点地保留，并且整文件绿不被删除**。

必须始终保留的整体验收：

1. 整文件 30 项绿（或经 PM 明确批准的等价断言集），作为 S2 关闭、T31 集成、T36 正式 QG 的必须项，不能因 T05 先收口而消失。
2. AC-002/VC-002：25 个退役 id 在所有运行入口明确拒绝、可调用别名数=0；11 项的任何"修绿"不得把退役 id 变成可提交。
3. AC-013/VC-013：退役记录的列表/详情只读可见且明确退役，原始历史字节变化=0、不按当前注册回填。
4. 4 个旧 case 的 sha256 锁与 T05 的 8 个 case 生成字节一致性（本轮已绿，不得回退）。

### 4. R2 `tools/run_isolated.py` 静态核（没有运行它）

| 维度 | `run_tool`（证据工具） | `run_exec`（pytest 子进程） | 事实与限制 |
| --- | --- | --- | --- |
| env | `os.environ.clear()`(113) **后**才 `private_env()`(114)，而 `private_env()` 现读 `os.environ`(77) ⇒ 实际只剩显式白名单键 | `private_env()`(134) 在父进程完整 env 上做 `{k:v for k,v in os.environ.items() if k.upper() not in DROP}`(77) ⇒ **继承减 DROP，不是最小白名单** | `DROP`(48-61) 只列 6 个 provider 变量 + 3 个代理 + `PI_*`/`PI_CODING_AGENT_DIR`/`PI_WORKER_TASK`；`TAI_PAT_TOKEN`、`UE_HORDE_URL`、`PI_MODEL`、`PI_SESSION_*` 等不在其中，因此原样进入 pytest 子进程（`full-workbench-suite-window.meta.json` 的 `env` 名单实证） |
| socket | `deny_network()`(115/99-105) 在**本进程**替换 `socket.socket.connect`/`connect_ex`/`create_connection` | **没有调用 `deny_network()`**；即使调用了也不会生效——`subprocess.run`(136) 起新解释器，monkeypatch 不继承 | 即使 `run_tool` 的 patch 也不是全禁：`getaddrinfo`、UDP `sendto`、`subprocess` 起的 curl/其他客户端都不在 patch 范围内 |
| 其他纪律 | `-B` 断言(`sys.dont_write_bytecode`)、`PYTHONUTF8`、`PYTHONHASHSEED=0`、`NO_PROXY=*` | argv 带 `-B`、env 带 `PYTHONDONTWRITEBYTECODE=1`/`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，无 pytest cache（`-p no:cacheprovider`） | 与"该窗口 14 pyc 不变"一致；与更早一次无 `-B` 探针造成的 1 个 pyc 漂移区分开 |

suite 侧（只看本文件与其 helper，未读 T28 全文件）：

- autouse `_isolated_environment`(189-211) 只做：tmp `HOME`/`USERPROFILE`/`PI_CODING_AGENT_DIR` + 删除 12 个 provider/proxy/worker 变量。**没有 socket 拒绝，没有全局 fake backend，也不删 `TAI_PAT_TOKEN`。**
- 真正的隔离靠逐调用注入：`monitor_suite._running(root, deps=MonitorDeps(redactor=…, playground=spy))`、`playground_factory`、以及 `test_edited_cases_...` 里"验证绝不许构造 transport backend"的 `backend_factory`（990-993）。
- 因此"case 路由零凭证零模型"是被测断言（927-930 的 `credential_snapshot` monkeypatch + `spy.calls == []`），不是 harness 强制。
- **未证**：该次 12F 运行没有 socket 级审计/tcp 抓包，不能证明被测产品路径没有尝试外部连接；也不能断言 `TAI_PAT_TOKEN` 未被任何被测代码读取（fixture 未删该名）。本审计没有运行 pytest，也不主张"真实网络已发生"或"完全未发生"。

### 5. 最小工程处置候选与各自权限/承诺影响

| 候选 | 做法 | 权限 | 承诺/验收影响 |
| --- | --- | --- | --- |
| C1（推荐先做） | PM 按 T05 原卡窄读法收口：认定"八入口面完成"，把 12 项按名保留为 T27/T28/T05-test 债，明确 holder 与时点；不以整文件变绿为条件 | 不需要改 DAG、不需要扩写面；需要 PM 一条明确资格判断并记录 12 个名字 | T05 的 `commands` rc 仍为 1，必须写成"rc=1 且差异=已知 12 项"；整文件绿移到 S2 关闭/T31/T36，且不得删 |
| C2 | 以"顺序例外"提前派 T27/T28，T05 悬置 | 需要 PM 显式批准破坏 dep 顺序（T28 dep T05） | 即使 T27/T28 落地，12 项里的断言仍在 T05 文件内，仍需 T05 动测试；只是把循环拆成两段，且 T28 的验收会跑在未收口的 T05 之上 |
| C3 | 把 T05 写面扩到 `decision_monitor.py`/`decision_history.py` 让它自己修绿 | 不允许：违反单 writer（这两文件属 T27/T28 及其验收） | 会使 T28/T27 的验收失去可核 before/after；不推荐 |
| C4（C1 的配套，后置） | T28/T27 落地后，用同一 T05 key 起一个有界 attempt 只改 `test_decision_context_workbench.py` 做旧面断言迁移 | 在 T05 原写面内，且原卡已授权"仅为新八入口衔接" | T05 保持 open 直到该 attempt 完成；只有它完成，整文件绿才能作为 S2 关闭证据 |

推荐的组合是 **C1 立即 + C4 后置**：C1 让 T11/T12/T17/T18 能按 DAG 起步；C4 保证整文件绿不被悄悄放弃。若 PM 不接受 C1 的窄读法，则只剩 C2（顺序例外），代价是把一个确定的两段依赖换成一次 DAG 纪律例外。

不可省略的具体下一步（给 PM 排活）：

1. 给 T28 一条明确问题：`/api/test/cases` 在迁移后是"8 活动 + 4 退役只读"还是"仅 8 活动、退役走单独只读视图"？这一条决定 #2/#5-#11 的测试迁移形态，也决定 `?dp=` 白名单。
2. 给 T27 一条明确问题：退役 dp 的 `question_summary` 是保持 None 并在 `dp` 节点显式写"retired/未记录"，还是投影退役解释文本？（`RetiredDecisionPoint`(757-774) 不含 questions，且 `_question_summary` 为 None 时 `2779` 不加任何 basis 文案——这是 T27 侧的"明确退役"缺口。）
3. T05（C4）只改断言：不新增 skip/xfail，不删原始断言语义，旧 case 字节不动。

## 改动清单

| 文件 | 动作 | 说明 |
| --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/evidence/implementation/t05-handoff-audit-20261027.md` | 新增（write） | 唯一证据；本任务唯一写入。未改任何产品/旧证据/PM 状态/卡片/DAG |

## 残留与未验证

- 未运行任何 pytest/产品测试/CLI/服务/HTTP 决策/模型；12 项结论来自既有真实日志 + 当前源码静态追踪，不含本次实测复现。
- `decision_monitor.py`(3102)、`decision_history.py`(4210)、`decision_points.py`(5694) **未读 EOF**，只读上述段落；结论限这些段落。`baseline-red`/`green-08-full-final` 两个 stdout 只按 short summary 与关键文本 grep 比对，未读全文。
- `scripts/build_decide_cases.py`、`decide_book_template.json` 未读；本结论不依赖它们（12 项失败测试不执行它们）。
- 未验证真实浏览器、DOM node 实跑（被 1800 行 abort）、`/api/test/validate` 的 edited-book 段、`/api/test/submit` 观察段。
- 未验证 harness 是否有真实外连（无 socket 审计）；未验证 `TAI_PAT_TOKEN` 是否被被测代码读取；不推断真实网络已发生。
- T10 仅核到"窗口内 5 个输入前后 hash 相同"（`meta.json`），没有评估 T10 五输入自身资格。
- 既有历史不追认、不洗白：14 pyc 中含 1 次历史漂移；坏信封 R2 attempt 的 `BLOCKED/0 product bytes` 仍为事实；T10 外部 sink 未批准等原事实保留。
- 本审计不构成 T05/S2 完成，也不构成任何 QG/PASS/签收或 receipt；不给正式结论，由 PM 吸收后决定 ack。

## 上下文来源

- 任务卡 `.agenticdoc/mw-dp-consolidation/workers/dpc-t05-handoff-audit/task.md`（含 `mw-write-surface` 与 `mw-dispatch-card` 段）。
- 原逻辑卡 `tasks/isolated/T05-eight-cases.md`（写面/要求/验收命令）、`tasks/isolated/T05-handoff-audit.md`、`tasks/isolated/T27-history-projection.md`、`tasks/isolated/T28-observation-server.md`。
- `implementation-isolated-dag.json`（T05/T09/T11/T12/T17/T18/T19/T26/T27/T28/T29/T30 的 deps/face/status/commands）。
- 当前产品：`implementation-worktree/packages/multi-workers/test_decision_context_workbench.py`（全读）、`decision_monitor.py`、`decision_history.py`、`decision_points.py`、`decide_cases/dp2.json`（只读 case 壳）。
- 证据：`evidence/implementation/dpc-t05-eight-cases/{comparison-baseline-vs-final.json,logs/baseline-red/stdout.txt,logs/green-08-full-final/stdout.txt,pyc-deviation.md}`；`evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/{logs/full-workbench-suite-window.stdout,logs/full-workbench-suite-window.meta.json,tools/run_isolated.py,output.md}`；`evidence/implementation/t05-r2-envelope-pm-handoff-20261027/report.md`；`evidence/implementation/t05-pm-handoff-20261027/report.md`。
- 项目目标锚点 `.agenticdoc/goal.md:5`。
