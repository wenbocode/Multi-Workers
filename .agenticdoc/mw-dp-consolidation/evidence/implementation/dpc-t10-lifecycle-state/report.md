# T10 lifecycle state — worker evidence (2026-10-27)

## 结论

代码完成、局部验证通过：T10 在隔离副本内新增三类独立事实（`request` / `note` / `terminal`）并加固快照关联；指定两个测试文件在本卡隔离环境连续两次 `116 passed, rc=0`，对改动前源码的同一批测试 `31 failed / 85 passed, rc=1`（红）。未做：CLI/消费者接线、历史与观察投影新事实、真实 provider/HTTP/决策 CLI、完整 `npm run check`、签收/gate/phase、human/H12 资格。故本卡为“实现+局部验证完成”，不是 L2/QG/签收或运行切换完成。

## 证据

完整路径均相对 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/`。

- `baseline.json`：开工前 5 个写面文件的 bytes/SHA256/EOL/结尾 LF，及与 live 同名文件的逐字节一致性（`worktree_equals_live=true`，5/5）。本仓库 `packages/multi-workers` 未被 git 跟踪，因此“既有 diff”基线取 live 同名副本的字节，不是 git blob；`baseline.py` 里 git diff 字段为空仅表示“未跟踪”，不作为无 diff 的证据。
- `baseline-green.stdout|rc|meta.json`：改动前、隔离 cwd 下运行本卡指定两文件 → `6 failed, 78 passed in 4.09s`, rc=1。6 个失败均为同一既有原因：fixture 用退役 `dp1-dispatch-type`（T03 协议迁移在任何 replay/传输前即拒绝）。失败清单见 `check.json.baseline_worktree_red_6`，原失败保留。
- **首次运行的真实失败（已保留痕迹、日志未留存）**：第一次把 `TEMP` 放在本卡 evidence 内运行，`LifecycleStore.test` 的 test-scope guard 正确拒绝 `.agenticdoc` 内 sink，产生 40 个 setup `WireScopeError`、rc=1；随后改用 OS 私有 basetemp，同名 label（`baseline-green`）被重跑覆盖，原 stdout 未单独留存。失败痕迹保留为 `fixture/temp/pytest-of-*/`（仅 pytest 临时目录，无账本、无产品写入）。这是环境约束而非产品红：`.agenticdoc` 内 test sink 被拒是既有安全行为，故不修产品。
- `live-repo-baseline.stdout|rc|meta.json`：同一测试文件在未迁移的 live 仓库 cwd 下 → `84 passed`, rc=0，证明上述 6 个失败来自副本内协议迁移而非本卡行为改动。
- `red-prefix.stdout|rc|meta.json`：把改动前的 3 个产品模块（live 字节，SHA 与 `baseline.json` 一致）放进 OS 临时副本、仅替换为本卡新测试后运行 → `31 failed, 85 passed in 3.91s`, rc=1（`AttributeError: record_request/record_note/record_terminal/same_snapshot` 等，逐条在 stdout）。
- `final-green.stdout` / `final-green-2.stdout`（各含 `.rc`、`.meta.json`）：隔离副本内 `python -B -m pytest -p no:cacheprovider -q --basetemp <os-temp> test_decision_context_lifecycle.py test_decision_task_state.py` 连续两次 `116 passed`, rc=0（2.74s / 2.54s）。cwd 与 `sys.path[0]` 解析见 `after.json.imports`：5 个模块 `__file__` 全部落在 `implementation-worktree/...` 内。
- `exact-acceptance.stdout|rc|meta.json`：与卡内验收命令逐字一致（`python -B -m pytest -p no:cacheprovider -q test_decision_context_lifecycle.py test_decision_task_state.py`，无额外 `--basetemp`）在隔离 cwd 下 → `116 passed in 3.96s`, rc=0。
- 运行隔离（`*.meta.json` + `run_tests.py`）：`PYTHONDONTWRITEBYTECODE=1`、`-B`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`-p no:cacheprovider`、私有 HOME=`fixture/home`、basetemp/TEMP 在 OS 临时目录、最小 env（不继承 provider/worker/项目配置）。**偏差说明**：卡要求 TEMP 限本卡 evidence；实测 `LifecycleStore.test` 会正确拒绝任何解析到 `.agenticdoc` 内的 sink（test-scope guard），故 `tmp_path/basetemp` 放在 OS 私有临时目录（`tmp_outside_agenticdoc=true`），HOME/project fixture 仍在本卡 evidence。
- `after.json` + `diff-<file>.diff`：5 个写面文件 after bytes/SHA/EOL（均 LF、以 LF 结尾）与相对 live 基线的完整增量 diff（统一 diff，格式固定 `before/<file>`→`after/<file>`）。
- `after.json.mirror`：相对 PM pre-dispatch `s2-t05-t10-pre-dispatch-20261027/mirror-inventory.json`（1883 条，实测该清单描述的是 worktree 镜像而非 live 仓库——如 `decision_policy.py` 只在镜像中存在）的镜像漂移：1891 个文件、0 删除；变化为本卡 5 个文件 + 并行 T05 在途 3 个文件（`scripts/build_decide_cases.py`、`test_decision_context_workbench.py`、8 个新增 `decide_cases/*.json`）+ 1 个 `.pyc`。live 5 个同名产品文件仍与 `baseline.json` 逐字节相同（`live_product_files_unchanged_since_baseline` 全 true）。
- `after.json.pyc`：受保护 14 个 pyc 全在、0 缺失；13 个与 pre-dispatch 快照逐字节相同；`packages/multi-workers/__pycache__/decision.cpython-314.pyc` 与快照不同，mtime `2026-10-27T12:57:43Z`，早于本次首个 worktree python 运行（`2026-10-27T13:03:57Z`）且本 attempt 全部 python 运行均 `-B`+`PYTHONDONTWRITEBYTECODE=1`+`PYTHONPYCACHEPREFIX`，故不是本 attempt 写出/删除；但不能证明是哪个外部进程（并行 T05）写出。
- `after.json.ast`：原测试函数零丢失、零改写于 `test_decision_context_lifecycle.py`（37→64 函数，`changed_original_functions=[]`，仅追加）；`test_decision_task_state.py` 原 22 函数全在，7 个仅改 fixture id（`backend.DP1`→`DP="dp-gate-approve"`，`_record` 同），断言未减、未删。
- `check.json`：机器可读汇总（products、runs/rc/summary/失败清单、AST、mirror、pyc、imports、未验证标记）。

原始命令（均在 repo root 调用，脚本内使用绝对隔离 cwd）：

| 命令 | rc |
|---|---|
| `python -B <ev>/baseline.py` | 0 |
| `python -B <ev>/run_tests.py baseline-green worktree` | 1（改动前 6 既有失败） |
| `python -B <ev>/run_tests.py live-repo-baseline live` | 0（84 passed） |
| `python -B <ev>/red_evidence.py` | 1（31 failed / 85 passed） |
| `python -B <ev>/run_tests.py final-green worktree` | 0（116 passed） |
| `python -B <ev>/run_tests.py final-green-2 worktree` | 0（116 passed） |
| `python -B <ev>/run_tests.py exact-acceptance worktree exact` | 0（116 passed，卡内命令原文） |
| `python -B <ev>/collect_evidence.py` | 0 |
| `python -B <ev>/check.py` | 0 |

新增行为（本卡写面内）：

- `decision_lifecycle.record_request`：消费 `decision.DecisionClient.request_prepared` 的冻结结果 + schema-3 `material`/`preparation`；`available`/`attempts`/`transport_attempts` 与 `business_decisions`/`choice`/`basis_*` 分开；`available=True, business_decisions=0` 只作拒绝事实（冻结 `reason`），不产生选择/依据/执行/结算；`replayed=True` 无业务决定、无传输尝试；成功业务决定必须携带真实 prepared catalog，经 `decision_points.preparation_issues`（单源）复核，并写入 `basis_id/basis_text(prepared item text)/basis_source=pm-prepared/prepared_at/basis_catalog_sha256`。
- `decision_lifecycle.record_note`：PM 送审前 note 独立成行（`pm_note` + `prepared_at` + `note_source=pm-prepared`），仅 `initiator_role=pm` 可写；与模型依据不同行、不同字段。
- `decision_lifecycle.record_terminal`：本任务真实终态（`completed/incomplete/blocked` + 真实 reason + 必填 `task_after` + 可选 evidence），要求同一 task 的 creation fact，且 `observed_at` 不早于 creation before 与任何已记录 after；`settled` 单独存在时不再产生 terminal。
- 交叉校验：`parent_ref` 必须是本账本已记录、同 key 的 decision id（父后继引用可核）；三类新事实用确定性 `event_id`（同一 logical_id/dp/parent 重复调用返回 `duplicate`、字节不变）；`task_before` 只能逐字段等值复述 creation fact 的 before（晚到的“当前状态”作为 before 被拒绝）；over-limit note/basis 直接拒绝且不截断。
- `decision_wire`：新增 `request`/`note`/`terminal` 三个 schema-v1 kind（`EVENT_KINDS` 动态扩展，`decision_history` 读到 `unknown_kind=0`），自由文本字段入 redact→clip 管理路径，新增 `NOTE_TEXT_BYTES`/`BASIS_TEXT_BYTES`；既有四词 lifecycle/既有字段与限制未改。
- `decision_task_state`：新增 `observation_time` 与 `same_snapshot`（`None` 与 `[]`、列表顺序均严格区分），`validate_observation_order` 复用前者，语义不变。

## 改动清单

| 文件 | before bytes | before SHA256 | after bytes | after SHA256 | EOL | diff hunks / bytes |
|---|---|---|---|---|---|---|
| decision_wire.py | 73650 | 076fd3dee161a038fcc3597815863609d34b181da3f9f7646a8f0ee3dd911579 | 79832 | 8863e534f0a74edec1fc0105c0619c9dd19c85a472b82db6d622c23a7f85a5e6 | LF | 5 / 7458 |
| decision_lifecycle.py | 34814 | e4ea5183cd28167a9ef35915c054d472c12b5b474817b93436564d2958d33248 | 60811 | 0c0f7fffb353cc829e054dfbeec409915cb4bebce11d998c5d810feb533dc8e4 | LF | 5 / 27896 |
| decision_task_state.py | 2452 | e82fc6b94f120d1d4ee561b6160d969b5ef36a86b6e3a0e8a3774c59a37e35e9 | 3871 | b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d | LF | 2 / 2493 |
| test_decision_context_lifecycle.py | 26028 | 106f17198a9de3552d2dc3e43aeb1c67474a6e4cb9c597811e792640d87a24f8 | 50338 | bdedfd4301fab76929beb0156f429f973fcb6404382b8893d2cbecbfaa711d1a | LF | 2 / 25434 |
| test_decision_task_state.py | 13537 | c3de3c0456269aa3c8d1e0dfaf3f2098d9c9c657f6673ce93dc8cd5e7e54aff5 | 15480 | 30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f | LF | 8 / 7223 |

同目录另有本卡唯一证据脚本/日志（`baseline.py|json`、`run_tests.py`、`red_evidence.py`、`collect_evidence.py`、`check.py|json`、`*.stdout|stderr|rc|meta.json`、`diff-*.diff`、`fixture/`）；未写 live 仓库、未写工作副本其它文件、未运行生成器/观察 submit/决策 CLI。

## 残留与未验证

- **消费者未接线**：`mw`/决定 CLI/Worker 工具尚未调用 `record_note/record_request/record_terminal`（`mw.py` 不在本卡写面，属 T12/T15/T23）；本卡只证明 writer 在 fake 结果上真实落账，不证明真实 producer→writer 链路。
- **投影未覆盖**：`decision_history` 能读取新 kind（`unknown_kind=0`、`unlinked_events=0`），但不把它们投影成 note/basis/request/terminal 节点；观察 UI/DOM/TS 边（T27/T29/T35）未核。
- **材料引用不再复核**：`material_refs` 的“引用真实材料事实”由 `decision_points` 在 `request` 写入时结合调用方 `material` 复核，但 `material` 不入账本，读者只能凭 `basis_catalog_sha256` 回连 book；账本内无法独立重放 refs 校验。
- **顺序约束范围**：`terminal` 对 creation before 与全部已记录 after 做非递减；`executed/settled` 仍只核 against before（原行为未改）。
- **并发未加测**：只有 store 既有 O_CREAT|O_EXCL 锁与 event_id 幂等；未做双进程/双 writer 竞争测试（无新增锁语义）。
- **秘密边界未扩展**：仅注入的已知秘密 redactor；高熵/未知秘密检测与 C0 全链路不属本卡。
- 未运行完整 `npm run check`（T32），未改 TS、未跑 T03/T04/T05 生成器 `--check`；`pip`/依赖/lock/dist/mirror/install/服务重启/commit/push 均未动。
- 未验证 human/H12 真实资格、真实 grant、gate/policy/brake、签收/key 关闭、phase/stage 验收；未造任何真实授权或 PASS。
- `packages/multi-workers` 在 git 中未跟踪：本卡 before 基线是 live 同名文件的字节等价副本，不是 git blob，故不存在可引用的 git diff 基线。
- 受保护 pyc 中 `decision.cpython-314.pyc` 与 pre-dispatch 快照不同来源未明（文件 mtime 与外部并行任务重合），本 attempt 未写未删但无法证明外部写出者。

## 上下文来源

派发卡 `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\workers\dpc-t10-lifecycle-state\task.md`（含 frontmatter write_face/AC/VC 摘录）与源卡 `tasks/isolated/T10-lifecycle-state.md`；依赖交接 `evidence/implementation/t09-r2-pm-handoff-20261027/report.md`、`evidence/implementation/s2-t05-t10-pre-dispatch-20261027/{check.json,frontier.json,T10-card.md,pyc-protection.json,mirror-inventory.json}`；目标/契约 `.agenticdoc/goal.md`、`spec.md`（AC-007/AC-012/AC-014/AC-046/AC-049/AC-050/AC-051/AC-052）、`design.md`（§4.2 D012A、§4.6 节点映射、AC-050/051）、`implementation-isolation.md`、`implementation-isolated-dag.json`；实际源码 `implementation-worktree/packages/multi-workers/{decision_wire,decision_lifecycle,decision_task_state,decision_points,decision,decision_book,decision_history}.py`；运行 `workers/dpc-t10-lifecycle-state/run.json`（`run_id=dpc-t10-lifecycle-state@2026-10-27T12:56:07.428Z`, pid 84564）。所有证据根：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/`。
