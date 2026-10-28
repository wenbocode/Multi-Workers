# T04 — 生成TS八入口合同/角色/白名单/字段约束，核心材料不进入可裁剪context

## 结论

代码完成、卡内本地验证通过（L0/L1，非 L2/QG/签收）：`scripts/gen_decide_registry_ts.py` 现在是唯一的 TS 写出方，产出精确八入口投影（`dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route`，registry 顺序），每个入口携带 questionsVersion/kind/roleScope/required+optional 字段约束/modelStateFields 白名单/contextSlots/`preparation` 依据层；25 个旧编号只以非 entry 形状的只读 retired 投影存在（aliases=0，无可调用字段合同），不再有任何旧编号作为 context slot producer。核心材料与 `preparation.basis_catalog` 不可能进入可裁剪 context：`decision_context.trimmable_slot_conflicts()` + 生成器在渲染前 fail-loud 拒绝（含“producer 必须是活动入口”）。`decide_registry.json` 未被改动（仍为 T03 交接 SHA `cc017e34…`），并由新测试以 `registry_snapshot_text()` 字节相等锁证明它仍是同源产物。

卡列验收命令 `python -m pytest -p no:cacheprovider -q test_decide_registry_ts_lock.py` → 35 passed / rc0；`--check` → rc0 且 stdout 为空；T03 只读合同 181 passed 未回归。**未做**：TS 编译/模块解析/`npm run check`（T32）、T11 consumer 迁移、真实 provider/HTTP/CLI/服务。两个卡外面（一个属于 T09、一个 DAG 无 owner）的旧期测试仍持 pre-T04 期望，已具体列出，未修改。

## 证据

### 基线（改动前，均在本卡隔离副本内）

`baseline/before-manifest.json`：五文件 before bytes/SHA256/EOL 全部等于 T04 pre-dispatch（`evidence/implementation/t04-pre-dispatch-20261026/check.json`，卡 SHA `99c0fb85…`），即无新漂移；`samefile_live=false`（副本≠活树同 inode）。

| 文件 | before SHA256 | bytes | EOL |
|---|---|---|---|
| packages/multi-workers/decision_context.py | `5eeb8605…ab58b06` | 11949 | 288 CRLF / 0 bare LF |
| packages/multi-workers/scripts/gen_decide_registry_ts.py | `a0ed7a80…8317077d` | 11684 | 285 LF |
| packages/multi-workers/decide_registry.json | `cc017e34…a06c604` | 29869 | 894 LF |
| packages/multi-workers/test_decide_registry_ts_lock.py | `dc6332f1…b2a92e` | 2424 | 63 LF |
| …/shared/decide-registry.generated.ts | `699719c2…fbb30127e4` | 30264 | 930 LF |

改动前已存在的真实红灯（不是本任务新引入）：`logs/baseline-context-ts-lock.log` rc1，2 failed / 3 passed — `test_generated_registry_matches_a_fresh_render` 与 `test_generator_check_mode_is_clean` 因 generated.ts 仍是 pre-T03 冻结产物而失败（T03-R3 已声明该债）。

### 红测 → 绿测（逐次日志，含完整 stdout/stderr/rc）

- `logs/red-01-new-tests.log`（rc1）：先只写新测试、未改实现 → **32 failed / 3 passed**。失败点含：`DECIDE_REGISTRY` 仍是 25 旧 id、无 kind/roleScope/preparation/retired 投影、`slot_names_for("dp-QG")==()`、`trimmable_slot_conflicts` 不存在（AttributeError）、两个 fail-loud 守卫未触发。
- `logs/green-01…` rc1（24 failed/11 passed）：实现后暴露测试侧 TS 字面量解析器把对象 key 误当引用（`_Reference('questionsVersion')`）——修正解析器，非放宽断言。
- `logs/green-02…` rc1（1 failed/34 passed）：`preparation: DECIDE_REGISTRY_PREPARATION` 断言漏了切片末行无换行；修断言。
- `logs/green-03-context-ts-lock.log` / `logs/green-04-context-ts-lock.log` / `logs/final-acceptance-context-ts-lock.log`：**35 passed / rc0**。无 skip/xfail、无删断言。
- `logs/nonregress-t03-contract.log`、`logs/nonregress-t03-contract-02.log`（卡列命令之外新增的只读非回归核对，不写任何文件）：T03 两个只读合同测试 **181 passed / rc0**，即真实 generated.ts 被 T03 判为 post-T04 八入口投影，四旧 legacy 行保持合法过渡。

### 生成器命令（隔离副本，最小 env，无 provider/项目配置）

- `logs/gen-stdout-dryrun.log` rc0（`--stdout`，不写盘）。
- `logs/gen-write-01.log`、`logs/gen-write-03.log` rc0：`wrote …decide-registry.generated.ts (19193 chars)`；`logs/gen-write-02-idempotent.log` rc0 再次写同字节（幂等）。
- `logs/gen-check-01.log`、`logs/gen-check-02.log`、`logs/final-gen-check.log` rc0，stdout 与 stderr 均为空（`--check` 干净）。
- 静态核对 `_REPO_ROOT`（= implementation-worktree）、`sys.path` 入口模块、`output_path()` 全指向副本；`test_check_and_stdout_modes_write_nothing` 实跑证明 `--check/--stdout` 不改 generated.ts、不改 `decide_registry.json`、不改四旧 case（`decide_cases/dp1|dp2|dp3|dp25.json` 哈希逐一比对），并在 1864 文件 mirror inventory 上验证没有第二个落点。

### 生成产物结构（解析已签入文件本身，非 render() 自查）

- entry ids 精确 `('dp-w-type','dp-pm-steer','dp-w-check-task','dp-QG','dp-gate-approve','dp-sign-key','dp-auto','dp-route')`（registry 顺序），与 retired 集合零交集。
- roleScope：7×`pm` + 1×`worker`（仅 `dp-w-check-task`），且 entry 无 grants/permissions/authority/allowedTools 键。
- 字段级 parity：8 入口 × required/optional 全字段 `name/type/description/enum/maxItems/itemType/maxBytes/itemMaxBytes/signed/minValue/emptyIsValue` 与 `decision_points.registry_snapshot()` 逐项相等，属性顺序亦锁定。
- `emptyIsValue` 保留 5 处：`dp-QG.review_evidence` + `dp-sign-key.verification_evidence.verified/.unverified/unfinished_impact` + `dp-gate-approve.condition_evidence`；`dp-sign-key` 仅此三数组，`[]` 语义未改。
- modelStateFields 与 `MODEL_STATE_FIELDS` 逐入口相等（白名单非第二手写表）；`preparation.basis_catalog` 不在任何 entry 的 modelStateFields 内（依据层与材料层分离）。
- `DECIDE_REGISTRY_PREPARATION` = JSON `preparation` 节 + `basisStateField: "preparation.basis_catalog"` + `contextTrimmable: false`，被 8 入口共同引用。
- contextSlots：仅 `dp-QG`、`dp-auto` 各 `["error_excerpt"]`，其余 6 入口 `[]`；25 旧 id 全部 `()`；producer 集合 = `{"dp-QG","dp-auto"}` ⊆ 活动集合。
- retired 投影：25 条，顺序 = `RETIRED_DP_REGISTRY`，disposition 6 migrated / 19 retired，migratedTo ⊆ 活动 id，retired 的 migratedTo 为 null，键集恰为 `id/tier/description/disposition/migratedTo/note`（无 required/model/context 合同），且文本中不存在 `\t"<old-id>": {` 形状（alias=0）。
- 生成模块无 `choices:`/`labels:`/`instructions:`/`targetEntries:`（未手写第二菜单/第二路由表）。

### 核心材料不进入可裁剪 context（fail-loud，红→绿）

- `decision_context.trimmable_slot_conflicts(declared_paths)`：slot 名与任意活动入口 required/optional 路径或 `preparation(.…)` 相撞即返回冲突（按 SLOT_ORDER 稳定排序）。
- `gen.assert_slot_boundary(doc)`：渲染前拒绝上述冲突，并拒绝“producer 不是本文档声明入口”（旧 id 无法借 slot 白名单复活）。两条都由测试在真实扰动下触发：`test_generator_refuses_a_slot_that_collides_with_core_material`（把 `dp-sign-key.delivery_goal` 改名为 slot 名 `change_summary` → ValueError "collide with core decision material"）、`test_generator_refuses_context_provenance_of_a_retired_id`（注入 `dp4-failure-handling` producer → ValueError "provenance"）。守卫不存在时这两例在 red 阶段是 AttributeError/未触发的真实失败。
- `validate_context({"preparation.basis_catalog": …}, "dp-sign-key"/"dp-QG")` 返回 `unknown slot`，即依据不可能借 context 传输。
- 保留：`fit_context` 裁剪顺序/60%-40% 截断标记、`CONTEXT_MAX_BYTES`、producers 白名单、empty_is_value、快照 null 与 `[]` 区分均未改；`decision_context.py` 保持 CRLF（323 CRLF / 0 bare LF）。

### after 状态与写入面（`after/after-manifest.json`、`after/changed-files.diff`）

| 文件 | after SHA256 | bytes | 结果 |
|---|---|---|---|
| packages/multi-workers/decision_context.py | `c6f5783c…e26fb2d70` | 13784 | changed（+1835B） |
| packages/multi-workers/scripts/gen_decide_registry_ts.py | `e454cefd…237124c6` | 21280 | changed（+9596B） |
| packages/multi-workers/decide_registry.json | `cc017e34…a06c604` | 29869 | **未改**（= T03 交接 hash） |
| packages/multi-workers/test_decide_registry_ts_lock.py | `9603a817…c828e635b` | 22960 | changed（+20536B，5→35 测试） |
| …/shared/decide-registry.generated.ts | `8c316042…12337b8f` | 20629 | changed（仅生成器写出） |

- mirror inventory 对 pre-dispatch `mirror-inventory.json`：1864 → 1864 文件，added=[]、removed=[]、changed 恰为上述 4 个；`changed_outside_write_face=[]`。五文件 `samefile_live=false`（未写活主树，未建链接）。
- 完整 diff：`after/changed-files.diff`（hunk 数：decision_context.py 5、生成器 9、测试 2、generated.ts 6）。
- 事故与清理（如实记录）：第一次跑 static legacy probe 时未走隔离 runner，在副本 `packages/multi-workers/__pycache__`、`scripts/__pycache__` 生成 4 个 `.pyc`（14:30:33 本地时间）；随即删除该 4 文件及两空目录，改用 `PYTHONDONTWRITEBYTECODE=1` 的 runner 重跑（`logs/legacy-expectations-probe.log`），当前副本 `__pycache__` 目录数 = 0。

## 残留与未验证

1. **卡外旧期测试仍持 pre-T04 期望（未运行、未修改，静态探针实测值见 `logs/legacy-expectations-probe.json`）**：
   - `packages/multi-workers/test_decision_context.py`（DAG 85 文件中无 owner）：`test_slot_names_match_the_card_whitelist` 断言 `slot_names_for("dp4-failure-handling") == ("error_excerpt",)`，实际 `()`；`test_validate_context_accepts_a_well_formed_block` 对 `dp4-failure-handling`/`dp6-qg-verdict` 断言 `[]`，实际各返回 `context.error_excerpt: not a slot of <retired id>`。该文件另有 3 条旧 id 断言仍成立。
   - `packages/multi-workers/test_decision_context_contract.py`（T09 写面）：`test_generated_ts_is_fresh_and_carries_the_model_table` 以 `dp1/dp2/dp3/dp25` 旧 id 锚点取 entry block，T04 后 4 个锚点均不存在（4 条断言会失败；T09 需按其自身写面迁移）。
   - `decision_book.py`（T09 写面）的 `DP_CONTEXT_SLOTS` 仍以旧 id 作 fallback 表；`_shared_context_slots` 优先读 `decision_context`，故 Python 主链路已按新入口，但该书层 fallback 未迁移。
   以上均为“具体未列面”，非本卡授权内可改；未修改其断言、未以 skip/xfail 掩盖。
2. TS 编译/类型/模块解析等价性、biome formatter 等价性、`npm run check`（仅 T32 保护副本）：未验证。新增非字段行按 CJK=2 宽度最大 85 列（<120），但 formatter 度量等价未证。
3. T11 consumer（decision-tool/triage-client/decide-policy）仍按旧行过渡，未强制迁移；真实调用链接线未验证。
4. 无真实 provider/HTTP/决策 CLI/服务探针；无 H12/human 资格、无 L2 端到端、无 QG/签收/stage 关闭；未 build/install/commit/push/重启；未写活主树、未改 spec/goal/原证据/四旧 case/其他 key。
5. 未证明全树无其他人工 writer（除 1864 inventory 比对外），未做回移/切换授权。

## 上下文来源

- 卡与编排：`tasks/isolated/T04-context-ts-generation.md`（SHA `99c0fb85…`）、`implementation-isolated-dag.json`（T04 写面/命令/依赖）、`implementation-isolation.md`、`spec.md:128`、`design.md:201`（D-012A、§4.1 表、§4.6 context 语义）。
- 前置证据（全文读）：`evidence/implementation/t03-r3-pm-handoff-20261026/{report.md,check.json,probe.json}`、`evidence/implementation/t04-pre-dispatch-20261026/check.json`（五文件 before + 1864 inventory）。
- 本任务完整读取的源码/测试：`decision_context.py`、`scripts/gen_decide_registry_ts.py`、`decide_registry.json`、`test_decide_registry_ts_lock.py`、`decide-registry.generated.ts`、`test_decide_registry_contract.py`（T03 只读合同全文）、`decision_points.py` 的 registry/snapshot/preparation 段、`test_decision_context.py` 的 slot 段、`test_decision_context_contract.py` 的 generated-TS 段。
- 本卡证据目录：`evidence/implementation/dpc-t04-context-ts-generation/**`（baseline/、after/、logs/、tmp/、fixture/）。

## 改动清单

产品（仅卡列 5 个副本，原仓同名文件未写）：

1. `implementation-worktree/packages/multi-workers/decision_context.py` — slot producer 迁到活动入口（`error_excerpt → dp-QG/dp-auto`）、新增 `PREPARATION_ROOT`、`trimmable_slot_conflicts()`、docstring 契约（核心材料/依据不进可裁剪 context）。
2. `implementation-worktree/packages/multi-workers/scripts/gen_decide_registry_ts.py` — 八入口投影 + kind/roleScope/preparation/retired 渲染；entry 顺序改为 registry 顺序；`assert_slot_boundary()` 两道 fail-loud 守卫；`_formatter_config` 缓存；接口/注释扩充。
3. `implementation-worktree/packages/multi-workers/test_decide_registry_ts_lock.py` — 5→35 测试：字节锁/`--check`/`--stdout` 不写、JSON 同源字节锁、8 入口顺序、字段级 parity、emptyIsValue、role/kind、preparation 分层、context slot 真实来源与材料隔离、两道守卫负例、retired 只读投影/alias=0/无第二菜单。
4. `implementation-worktree/packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts` — 由生成器写出（非手改）：8 入口 + `DECIDE_REGISTRY_PREPARATION` + 25 条 `DECIDE_REGISTRY_RETIRED`。
5. `implementation-worktree/packages/multi-workers/decide_registry.json` — **未改**（同源字节锁证明其仍等于 `registry_snapshot_text()`，SHA `cc017e34…`）。

证据（本卡目录）：`baseline/{before-manifest.json,5×before bytes}`、`after/{after-manifest.json,changed-files.diff,5×after bytes}`、`logs/*`（红/绿/生成器/`--check`/T03 非回归/legacy 探针，含 rc）、`tmp/*`（可复现脚本：baseline、红绿 runner、after、宽度与产物探查）。
