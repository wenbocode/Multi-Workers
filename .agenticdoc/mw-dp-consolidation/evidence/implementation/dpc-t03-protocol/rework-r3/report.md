# T03-R3 局部测试返工报告（唯一产品写面：test_decide_registry_contract.py）

## 结论

R3 的有界测试返工已完成：两个实测残留根因都在唯一允许的测试文件内修复，行为按“先真实 red、后最小 green”走通，原 15 项 AC/VC 验收断言与两个 validator 的既有验收全部保留并通过。

- 残留A（before 行448 `_ts_required_fields`）：不再把 `dp4-failure-handling`（以及 `DP1_ID`）当作“解析成功/合法矩阵”的前提。解析证明改为结构性：声明锚点 + 表终止符存在、key 只能是双引号 id 或 `[CONST]`（且 CONST 有字符串常量声明）、value 是非空双引号字符串数组、无重复 id、无未消费残留、至少解析到一行。八 active 合法 required-field 矩阵（无旧行，含无 `DP1_ID`、新名常量/字面键形态）可解析；未解析/截断/重复/非法 key/字段异常/空矩阵均有明确拒绝。
- 残留B（before 行495-498 `test_ts_required_rows_follow_the_registry_stage`）：pre-T04 仍精确锁“四旧行内容 + 0 active 行”；post-T04 只要求“仍存在的旧行集合 ⊆ 四旧行、内容逐字未变、无未知ID”，不再强制四旧行必须存在，也不新增“T04/T11 必须同一轮同时迁移”或其他后继无写权的阶段锁。
- 实测：before 基线 166 passed；加入新回归后 red = 12 failed / 169 passed（full suite）、12 failed / 3 passed（new-only）；修复后 green = 15 passed（new-only）、181 passed（full suite，rc0；最终复跑同）。
- 产品变更仅 1 个文件：`23724B → 39079B`，sha256 `67b74a47…f32c → c0e35cf1…d719`，`+434/−27`，LF 风格与结尾换行不变。另 3 个产品文件、7 个受保护 peer、主树对应文件、原 T03/R2 证据字节全部未变；13 行 handoff 表 13/13 仍等于 R2 after。
- 本报告只签这份局部测试返工成果：不放行 T04/S1/L2/QG/产品签收，不声称 T04 生成、TS parity/接线/编译、或任何下游业务 PASS。

## 证据

### 1. 环境、命令与隔离

- 两条验收命令均在 `implementation-worktree/packages/multi-workers` 下运行，argv/rc 完整写入各 log：
  - `python -m pytest -p no:cacheprovider -q test_decide_registry_contract.py test_dp_consolidation_registry.py`
  - `python -m pytest -p no:cacheprovider -q -k "ts_required_parser or ts_required_stage or generated_ts_stage" test_decide_registry_contract.py test_dp_consolidation_registry.py`（仅新增/修改项；full suite 仍只跑原两文件）
- 最小 env（`run_tests.py`/`run_probe.py`）：仅 PATH/SYSTEMROOT/SYSTEMDRIVE/WINDIR/COMSPEC/PATHEXT + 隔离 HOME/USERPROFILE/APPDATA/LOCALAPPDATA=`isolated/home`、TEMP/TMP/TMPDIR=`isolated/temp`、`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、PYTHONIOENCODING/UTF8；不继承 provider/worker/project config，无决策 CLI、服务探针、HTTP、生成器、npm/build/install/restart/commit。
- 运行后 `packages/multi-workers` 下无 `__pycache__`/`.pytest_cache`。pytest `tmp_path` 落在 `isolated/temp`。
- 导入/子进程副本路径：`probe-r3.json.imports` 记录 `test_decide_registry_contract` 与 `decision_points` 均解析到 worktree 的 `packages/multi-workers`，不是主树。

### 2. Before 基线与保存

- `before-manifest.json`（真实起点 `2026-10-26T04:33:09.555166Z`，main HEAD `7a530ecb7cb86dac329dbc259459657b2e1608ea`）。
- before 四文件 bytes/SHA/EOL：

| 产品文件 | bytes | sha256 | CRLF/LF-style | 行数 |
|---|---|---|---|---|
| decision_points.py | 305745 | 78e72e03cfe3b03f0349d95113c1947713b91c4a143bbaaada404f08db7443e6 | 7102 CRLF | 7102 |
| decide_registry.json | 29869 | cc017e343f2f7702cf2fcdafc1239d543be472b4e6ab6b92d6adaaee7a06c604 | 894 LF | 894 |
| test_decide_registry_contract.py | 23724 | 67b74a47e22b3d500fa0799a3b1a33c439a69ae8d2bc8c6971a2afeba965f32c | 557 LF | 557 |
| test_dp_consolidation_registry.py | 35149 | f7bf030231558c258921bb286593bb89bb58b85f37ea4548b2e6c2eb4ce75d2f | 815 LF | 815 |

- 四个 before 字节副本在 `before-bytes/`；baseline 全量跑 `baseline-before-edit.log` = 166 passed，rc0。

### 3. 两个残留断言的真实 red（旧函数仍坏）

red 由“先加新回归测试、helper/断言未改”的中间态产生，非 monkeypatch 解析结果、非旧 collection、非测试自身拼写错误。

- `red-r3-full-suite.log`：12 failed, 169 passed, rc1。
- `red-r3-new-tests.log`：12 failed, 3 passed, 166 deselected, rc1。
- 断言A red（active-only 八行，真实 parser 读 TS 文本）：旧行448 报
  `the required_if matrix was not parsed: ['dp-QG', 'dp-auto', ...]` 并附
  `assert {'dp4-failure-handling'} <= {...} / Extra items: 'dp4-failure-handling'`。
  证明旧代码把“dp4 存在”当解析成功前提，而不是矩阵本身没解析出来。
- 断言B red（post-T04 + 仅保留 dp4 一行，helper 可过）：旧断言报
  `the documented legacy rows of retired ids changed; only those retired ids may keep a row: []`。
  因 dp4 在，red 精确落在第二条断言上，与断言A分离。
- 其余 red：重复 key、未加引号 key、非字符串字段、空字段名、未知常量、空矩阵、未终止行、截断表、未知 ID、无 `DP1_ID` 新名常量正例（15 项中的 10 项）。

### 4. Green：合法正例与非法反例（逐项）

`green-r3-new-tests.log` = 15 passed；`green-r3-full-suite.log` / `green-r3-acceptance-final.log` = 181 passed（= 原166 + 新15），rc0。

| # | 用例（本文件内） | 场景 | 期望/实测 |
|---|---|---|---|
| 1 | `test_ts_required_parser_accepts_the_active_only_eight_entry_matrix` | post-T04 生成 + 仅八 active 行、无 `DP1_ID`、无旧行，真实 parser + 第二条断言 | accepted（旧代码 red） |
| 2 | `test_ts_required_stage_keeps_the_legacy_rows_during_the_transition` | post-T04 生成 + 四旧行原样保留（T04 未改 triage-client 的过渡态） | accepted（行为保留） |
| 3 | `test_ts_required_stage_does_not_demand_every_legacy_row_after_t04` | post-T04 + 仅 dp4 旧行（部分退役） | accepted（旧代码第二断言 red） |
| 4 | `test_ts_required_parser_accepts_new_name_constants_and_literal_keys` | 无 `DP1_ID`，六条字面键 + `[CHECK_TASK_ID]`/`[SIGN_KEY_ID]` 新名常量，真实文本 | accepted（旧代码 red） |
| 5-11 | `test_ts_required_parser_refuses_malformed_required_field_tables[...]` | duplicate-key / unquoted-key / non-string-field / empty-field / unknown-constant / empty-matrix / unterminated-row | 全部 rejected，且各自 message 命中 |
| 12 | `test_ts_required_parser_refuses_a_truncated_table` | 缺 `\n};` 终止符 | rejected：`... table is truncated` |
| 13 | `test_ts_required_stage_refuses_unknown_ids_in_the_matrix` | `dp99-unknown` 行 | rejected：`unknown ids in REQUIRED_FIELDS_BY_DP` |
| 14 | `test_ts_required_stage_still_refuses_active_rows_before_t04` | pre-T04 生成 + active 行 | rejected：`grew a legacy TS row before T04`（实质反例保留） |
| 15 | `test_generated_ts_stage_refuses_mixed_and_duplicate_entry_ids` | 生成 TS 混合八 active+dp4 / 重复 id | rejected：`neither the frozen pre-T03 artifact...` / `duplicate entry ids` |

`probe-r3.json`（独立探针，真实 parser 读文本 fixture，`synthetic_only=true`、`product_generation=false`）交叉确认：post-T04 active-only 的 parser 与第二条断言均 accepted；post-T04 部分/全部旧行 accepted；pre-T04 active 行 rejected；未知 ID 由第二条断言 rejected；空矩阵/重复/非法 key/非字符串字段 rejected。真实树 `stage=pre-t04`、旧行为 dp4/dp5/dp6/dp13、active 行 `[]`。

### 5. 真实 parser 与合成边界

- 正例全部让真实 `_ts_required_fields()` 读一段真实 TS 文本文件；只切换 `TRIAGE_CLIENT`/`GENERATED_TS` 的文件路径（`_use_synthetic_peers`），不替换解析返回值，不 mock 业务 validator。
- fixture 文本首行明确 `SYNTHETIC FIXTURE ONLY`，`_synthetic_generated_ts` 首行同时标注 not T04 output / no parity/compile proof；它们不是 T04 真实生成、不是 parity/接线证据、未经 TS compile。
- 未改生产 TS/生成器/JSON；真实 `triage-client.ts` 仍是 pre-T04 四旧行，`decide-registry.generated.ts` 仍是 25 旧 id（probe 真实 stage=pre-t04）。
- 空矩阵被当作解析失败（契约里“空”是反例；目标矩阵是八 active 行），不是新增的迁移阶段锁。

### 6. 实际 diff、四文件 bytes/SHA/EOL 与 13-handoff（不混计）

- `r3-changes.diff`（518 行，5 个 hunk）：`@@ -417,37 +417,135 @@`、`@@ -480,10 +578,16 @@`、`@@ -492,9 +596,17 @@`、`@@ -502,6 +614,10 @@`、`@@ -521,6 +637,296 @@`。仅 `test_decide_registry_contract.py`，无全文件 reformat。
- after 四文件（`after-manifest.json`，`2026-10-26T04:36:41.589114Z`）：

| 产品文件 | after bytes | after sha256 | changed | CRLF/LF | 结尾 |
|---|---|---|---|---|---|
| decision_points.py | 305745 | 78e72e03…7443e6（同 before） | no | 7102 CRLF | `\n` |
| decide_registry.json | 29869 | cc017e34…c604（同 before） | no | 894 LF | `\n` |
| test_decide_registry_contract.py | 39079 | c0e35cf1961d1b7eb5abfacdd8c75c8fda201f4f96ee0a82f021b820fd69d719 | yes | 964 LF / 0 CRLF | `\n` |
| test_dp_consolidation_registry.py | 35149 | f7bf0302…5d2f（同 before） | no | 815 LF | `\n` |

EOL 风格保持（未引入 CRLF，结尾换行保留；`change-summary.json.eol_style_preserved=true`）。

- 13 行 handoff 表（源：`rework-r2/write-scope-check.json["handoff"]`）：R3 前后 13/13 路径的 `current_sha256` 都等于 R2 after（`boundaries-check.json.handoff_rows_matching_r2_after=13`、`handoff_rows_moved=[]`）。该表在 R2 里只有 `decision_points.py` 一个协议文件变化（`a3fb1fe8…→78e72e03…`），其余 12 项不变；**两个测试文件本来就不在这 13 行表内**（它们只在 `write_scope.touched`），所以 R3 的 1 个测试变化不能算进“13 表内 3 变”。如实口径：4 个产品表内 1 变 3 不变；13 handoff 表内 R3 0 变。
- 主树/受保护面：`boundaries-check.json.ok=true`；4 个 product 的 main-tree hash before=after；`protected_extra`（mw.py、decision.py、decision_context.py、decision_book.py、gen_decide_registry_ts.py、triage-client.ts、generated TS）全部 before=after。
- 原证据边界：`original-t03` 与 `rework-r2` 全部文件 count/sha 摘要 before=after（本 R3 只新增 `rework-r3/**`，原 T03/R2 证据、worker run/output/card/PM state/manifest/approval/baseline 未写）。
- mtime 扫描（真实起点 04:33:09Z 之后）：worktree 内只有 `packages/multi-workers/test_decide_registry_contract.py` 命中；`mtime-scan.json` 明确 caveat：mtime 不是独占作者或全树干净证明。

### 7. EOF 来源（读取范围）

- `test_decide_registry_contract.py` 557 行、`test_dp_consolidation_registry.py` 815 行：改动前逐行读到 EOF。
- `decision_points.py` 7103 行：分段 1–1000、1001–2135、2136–3339、3340–4516、4517–5743、5744–6880、6881–7103，最后一读到 EOF（`_apply_per_dp_budget` 结束）。
- `triage-client.ts` 1126 行：单次读到 EOF；`decide-registry.generated.ts` 930 行：单次读到 EOF。
- 另读：R2 `report.md`/`check.py`/`probe.json`、R3 人工处置 `t03-r3-approval-20261026.md`、13 行 handoff 表、before/after manifests、`t03-r3-pre-dispatch/` 的 4 个 baseline 副本（与当前 before hash 逐字相同，未刷新/未覆盖）。

## 残留与未验证

1. 不放行 T04/T11：真实树仍是 pre-T04（TS 25 旧 id、triage-client 四旧行）。post-T04/T11 过渡只由 synthetic 文本 fixture 在 parser 层证明，未在真实生成产物上观测。
2. 未执行 T04/T05 生成器、JSON 再生、TS tests/compile、npm check/build/install/restart/commit/push；无真实 HTTP、决策 CLI、服务探针、provider/basis/vision 证据。
3. 合成 fixture 只证明本文件 parser/断言行为，不证明 T04 生成、字段级 parity、真实接线、TS 类型正确；`generated.ts` 的 header/interface/`requiredStateFields` 仅是当前测试形状的最小合成。
4. parser 是“该字面表”的有界扫描（锚点+终止符+key/数组 token），不验证 triage-client 其余 TS；不支持转义字符串/模板字符串等非本表形态；表终止符要求 `\n};`（当前与生成器约定一致）。空 legacy 表按“空=反例”判为解析失败；若未来某卡要改成空表，需要改这条测试（本卡不新增此权限）。
5. mtime 扫描只覆盖真实起点之后，且不能证明独占作者或全树无其他 writer；未整树逐文件审计。13 行 handoff 表不含两个测试文件；测试文件变化由 4 文件 manifest 覆盖，不能记到 13 表。
6. 只运行了原两 pytest 文件（+本文件新增用例 selection）；未跑其它包测试/全 L2/QG/签收/部署。
7. 本报告不改写原 T03/R2 的 done/exit0/acked 事实，也不触碰 dp4 不可用的历史记录；R3 由具体人工确认授权 dispatch，不是 dp4 成功。

## 上下文来源

- 本卡 `workers/dpc-t03-protocol-r3/task.md`（card_sha256 `93951b69fd8d53ced07fe2366b096dfc1bab489c52a40261970e43bec5ccbc56`）与人工处置 `evidence/implementation/t03-r3-approval-20261026.md`。
- 只读协议/peer：`implementation-worktree/packages/multi-workers/decision_points.py`、`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`、`.../shared/decide-registry.generated.ts`（均读到 EOF，范围见证据7）。
- 两个验收测试（全文）；R2 PM handoff `report.md`/`check.py`/`probe.json`；R2 `write-scope-check.json`（13 行表）与 `before/after-manifest.json`；`t03-r3-pre-dispatch/` 基线副本。
- 未把 hash 相等当阅读替代：所有比较文件在改动前按 EOF 读取，hash 只用于冻结边界。

## 改动清单

- 唯一产品改动：`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py`
  - `_ts_required_fields()`：重写为“结构解析证明”的有界 TS 字面表扫描（`_TS_TABLE_KEY`/`_TS_STRING_CONST`/`_ts_skip`/`_ts_string_list`），去掉 `dp4-failure-handling` 与 `DP1_ID` 前提；支持 `[CONST]` 新名常量与字面键。
  - `test_ts_required_rows_follow_the_registry_stage()`：retired 行改为“存在的行内容锁定 + 集合 ⊆ 四旧行”，pre-T04 保留“四行齐全 + 0 active”，post-T04 不再强制四行存在。
  - 新增 15 个用例（4 个合法阶段/形态正例 + 7 个 malformed 参数化 + 截断表 + 未知 ID + pre-T04 active 反例 + 混合/重复生成 ID），fixture 全部标注 synthetic。
  - 模块 docstring 第 6 条同步为 stage-aware 的旧行语义（不改变断言）。
  - 实际 diff：`r3-changes.diff`，+434/−27，5 hunk；EOL/结尾换行保持（见证据6）。
- 本卡 evidence（`evidence/implementation/dpc-t03-protocol/rework-r3/**`）：before/after bytes+manifest、`baseline-before-edit.log`、`red-r3-*.log`、`green-r3-*.log`、`r3-changes.diff`、`change-summary.json`、`probe_r3.py`/`probe-r3.json`/`probe-r3.log`、`boundaries-check.json`、`mtime-scan.json`、运行/捕获脚本、synthetic fixtures 与隔离 home/temp/project。
- 未改动：decision_points.py、decide_registry.json、test_dp_consolidation_registry.py、任何生成 TS/生成器/case、原 T03/R2 证据、PM state/manifest/approval/baseline、主树、其他 key、config/policy/gate/budget/credential。
