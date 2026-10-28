# T05-R2 — 八入口模板与准备时间出处（执行报告）

## 结论

**BLOCKED（写入面未生效，0 产品改动）。** 本次派发的 `task.md` 只声明
`write_face: .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2/**`
一条；卡 frontmatter 声明的「原 11 个副本产品」全部落在运行时写面之外。第一次产品编辑
（`test_decision_context_workbench.py` 加两根因红测）即被出包守卫
`rule=write-scope / detail=outside-declared-write-face` 拒绝，写 0 字节。

因此本 R2 的两根因（schema2 老模板、`CASE_PREPARED_AT` 未来时刻）**均未修改**：红测未加、
实现未改、8 case 未重生成、`-k focused`/整文件 suite 未跑。产品与实施副本保持逐字节原样
（27 条产品/输入行复验一致，1891 文件清单零变化，14 个 pyc 零变化）。

阻断原因是卡体与派发器契约不一致，不是产品缺陷：

* 派发器只把 `## 写入允许面` 的**段落正文**抽成 `write_face:` 头（
  `autopilot/dispatch.py::_card_write_face_entries`），不读卡 frontmatter；
* 原 T05 卡的该段是 12 条 bullet list → 抽 12 条 → task.md 头 12 条，worker 可写产品；
* 本 R2 卡的该段被写成一句散文，只保留一个反引号 span（evidence glob）→ 抽 1 条 →
  task.md 头 1 条 → 11/12 声明产品被守卫拒绝。

修复面在 PM 侧（把 `## 写入允许面` 恢复成 12 条 bullet list 后重派），worker 侧不存在
合法放宽路径：`allow_foreign_write: true` 属于任务书自授权（禁止），`task.md`/卡本体也在
禁止写面内。未使用任何绕过手段。

## 证据

全部路径为完整 canonical 路径（根 `H:\git\Multi-Workers`）。

**1. 写面不一致（机器可复验，跑的是出包函数本体）**

- `H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\evidence\implementation\dpc-t05-eight-cases\rework-r2\blocker\face-mismatch.json`
  - `card_frontmatter_entry_count: 12`（11 产品 + `rework-r2/**`）
  - `dispatcher_extracted_entries`: 1 条，只有 `.../rework-r2/**`
  - `task_md_write_face_head`: 同 1 条；`parsed_head_kind: WriteFace`，
    `parsed_head_entries`: 同 1 条
  - `products_outside_dispatched_face`: 11/12
  - `previous_card_control`: 原卡同段同一抽取器 → 12 条，`rendered_head_entry_count: 12`，
    `head_is_the_extracted_list: true`
- 生成方式：`tools/diagnose_face.py`，`PYTHONDONTWRITEBYTECODE=1 python -B`，import 根
  `.../implementation-worktree/packages/multi-workers`（`autopilot.dispatch` /
  `autopilot.write_face` 的 `__file__` 即该副本），无网络、无 provider、无决策 CLI。

**2. 守卫拒绝原文（本会话真实 tool 结果，不是推测）**

- `...\rework-r2\blocker\guard-refusal.json`
  - `write-scope: blocked edit to H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree\packages\multi-workers\test_decision_context_workbench.py: outside the task's declared write_face [rule=write-scope]; allowed: H:\git\Multi-Workers`
  - `bytes_written: 0`

**3. 未改动证明（对 before 逐字节复验）**

- `...\rework-r2\blocker\unmodified.json`：`product_rows_checked: 27`（11 产品 + 4 旧 case +
  T10 五产品 + 7 共享输入），`all_products_unchanged: true`，
  `inventory_file_count: 1891` / `inventory_changed: []`，`pyc_file_count: 14` /
  `pyc_changed: []`。
- `...\rework-r2\before-metadata.json`：真实 R2 前 11 文件 bytes/SHA256/LF/CRLF，与 PM
  `t05-r2-pre-dispatch-20261027/before-metadata.json` 的 SHA 逐条相同（例如
  `build_decide_cases.py` `7987113f…ffa70` 39431B 901LF、`decide_book_template.json`
  `755253b6…40df2` 2367B 61LF、`test_decision_context_workbench.py` `0320702d…7dc1b`
  95205B 2274LF；8 case 与 4 旧 case 亦逐条相同）。
- `...\rework-r2\test-functions-before.json`：28 个 `test_` 函数的 `lineno/end_lineno`、
  参数、装饰器、`ast_sha256`、`source_sha256` 与完整 source（后续执行者可直接对照
  “原 assertion 强度保留”）。
- `...\rework-r2\inventory-before.json`：1891 文件 SHA（实施副本全量，含 14 pyc）；
  `...\rework-r2\pyc-before.json`：14 pyc 现存状态（继承原 1 漂移，未删除/重写/重取基线）。
- `...\rework-r2\before-bytes\**`：11 产品 + 4 旧 case 的原始字节副本，供后续 full 增量 diff。

**4. 源码已读到实际 EOF（本轮真实读取，不是片段）**

- `...\scripts\build_decide_cases.py`：902 行 / 39431B（含 `CASE_PREPARED_AT` 及其
  “synthesis timestamp” 注释、`_evidence_reference` 的 `path:line` 生成、`_check_case`
  的 basis 覆盖与预算闸）。
- `...\decide_book_template.json`：61 行 / 2367B（`books` 只有 `dp3-worker-clarify`、
  `dp6-qg-verdict` 两本 schema2 `state` 模板）。
- `...\test_decision_context_workbench.py`：2274 行 / 95205B，分 9 段读到末行
  （`test_shipped_assets_keep_csp_textcontent_and_token_discipline` 收尾）。
- 只读取证：`decision_book.py` 的 `BOOK_SCHEMA_VERSION=3`、
  `scaffold_book/scaffold_material/scaffold_preparation/scaffold_context`、
  `_schema_issues`；`decision_points.py::preparation_issues`（只校验 ISO-8601 与时区，
  不判未来）；`autopilot/dispatch.py::_card_write_face_entries/render_write_face_line`；
  `autopilot/write_face.py::parse_write_face`；
  `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts::checkBashWriteScopeTarget`。
- PM 侧红线证据（只读）：`...\t05-pm-handoff-20261027\probe.json`（模板 3 失败：入口集合
  2 名 + 两本 schema2；8 case `prepared_at=2026-10-27T20:56:00+00:00` 在
  13:16:41Z 观测时为未来）、`...\t05-r2-pre-dispatch-20261027\check.json`。

**5. 环境纪律**

所有 Python 调用（静态 import、探针、诊断脚本）均为
`PYTHONDONTWRITEBYTECODE=1 python -B …`；无 pytest 缓存/自动插件（本轮未跑 pytest）、
无真实网络/provider/loopback submit/决策 CLI/服务探针/多行 `python -c`；写面仅本卡
`rework-r2/**`。pyc 数量与 SHA 复验未变（14/14）。

## 改动清单

| 文件 | 动作 | bytes | sha256 |
| --- | --- | --- | --- |
| evidence\implementation\dpc-t05-eight-cases\rework-r2\tools\capture_state.py | 新增（before 取证器） | 8945 | — |
| ...\rework-r2\tools\diagnose_face.py | 新增（写面抽取/解析复现） | 6080 | — |
| ...\rework-r2\tools\verify_unchanged.py | 新增（27 行 + 1891 清单 + 14 pyc 复验） | 3304 | — |
| ...\rework-r2\tools\inspect_inventory.py | 新增（PM inventory 只读分析） | 1376 | — |
| ...\rework-r2\tools\inspect_inventory2.py | 新增（inventory 根/口径核对） | 1650 | — |
| ...\rework-r2\before-metadata.json | 新增（11 产品 + 4 旧 case + T10 5 + 共享 7 的 bytes/SHA/EOL） | — | — |
| ...\rework-r2\before-bytes\** | 新增（15 份原始字节副本） | — | — |
| ...\rework-r2\test-functions-before.json | 新增（28 函数 AST/source） | — | — |
| ...\rework-r2\inventory-before.json | 新增（1891 文件 SHA） | — | — |
| ...\rework-r2\pyc-before.json | 新增（14 pyc SHA） | — | — |
| ...\rework-r2\blocker\face-mismatch.json | 新增（写面不一致机器证据） | — | — |
| ...\rework-r2\blocker\guard-refusal.json | 新增（守卫拒绝原文） | — | — |
| ...\rework-r2\blocker\unmodified.json | 新增（未改动复验） | — | — |
| ...\rework-r2\report.md | 新增（本报告） | — | — |
| ...\rework-r2\output.md | 新增（交付摘要） | — | — |

产品改动 0 个（11 个产品全部保持 before SHA）：

| 文件 | 状态 | sha256（未变） |
| --- | --- | --- |
| packages\multi-workers\scripts\build_decide_cases.py | 未改 | 7987113fb597f9c8f5d6b48085292cf1a4f8c150839b2fc12efe5d4d4f6ffa70 |
| packages\multi-workers\decide_book_template.json | 未改 | 755253b61429271b4eb1fc5cb22cc2fb4e77a7fce07e7a67aa111dd896640df2 |
| packages\multi-workers\test_decision_context_workbench.py | 未改 | 0320702d37146bd856b28e2b102fee2245c67fed15c64349fe0f637c2877dc1b |
| packages\multi-workers\decide_cases\dp-w-type.json | 未改 | dfb7ffc915a2c1de248629ec1d0a832c84b5d8a2920abc76427fdef60e6ddbf0 |
| packages\multi-workers\decide_cases\dp-pm-steer.json | 未改 | 814e7abf4172aba7c6828ab4e117f568ede18c5acf90d342640dc2235c744d10 |
| packages\multi-workers\decide_cases\dp-w-check-task.json | 未改 | 1908330e314b3da038c3a0e745504b30885e4717be91ef349c58383fdf3cad9c |
| packages\multi-workers\decide_cases\dp-QG.json | 未改 | 43afee46e192b19a08be5a17260d2a088fa9789594066dca730fdc999273d953 |
| packages\multi-workers\decide_cases\dp-gate-approve.json | 未改 | 69e7970144ed7eb2cfd685e035f66872028172d4f594c3cda387b43ce6975ebd |
| packages\multi-workers\decide_cases\dp-sign-key.json | 未改 | f089deabae264503f096406cf42cd909bddbeab23b80dc13eea194ceaf81e408 |
| packages\multi-workers\decide_cases\dp-auto.json | 未改 | 3b8f1f267ebf50bb88b015efb53c5f7783e07e2763d3a157109060f8d36890a9 |
| packages\multi-workers\decide_cases\dp-route.json | 未改 | 6f267c83a2dd704a17b48583d8a2c2380a6cdfdec2534797ab206424a49510d5 |

四旧 case 亦未改：`dp1.json 3131c02f…6c9ff`、`dp2.json a03e1a29…342ea`、
`dp3.json 82ff47e5…07f2d`、`dp25.json bda25144…2cc7fd`。

## 残留与未验证

**根因状态：两根因都仍存在（未修，因写面被拒）**

1. `decide_book_template.json` 仍是 schema2 两本（`dp3-worker-clarify`、`dp6-qg-verdict`，
   带 `state`/`question`/`questions_version`），PM 的 3 条模板失败原样保留；未按
   `decision_book.scaffold_book` + 八入口 registry 生成 schema3 八入口模板。
2. `scripts/build_decide_cases.py` 仍是 `CASE_PREPARED_AT = "2026-10-27T20:56:00+00:00"`
   且注释称其为合成/实际发生时刻；8 个随包 case 的 `preparation.prepared_at` 仍是该未来值。

**完全未验证（本轮 0 覆盖，不得当作已过）**

- 未新增任何红测（模板/schema3、prepared_at 出处两根因），因此没有“红→绿”链条；
- 未跑 `python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py`
  （整文件真实 rc 未知），未跑 `-k` 定向；
- 未跑 `python -B -X utf8 scripts/build_decide_cases.py --out … --quiet`，无私有 out、
  无 8 文件逐字节比对、无四旧 case 原 SHA 复核（仅确认未改动，未重生成）、
  无生产 `check_book` 真实 `repo_root`/逐 choice-basis、无 scaffold-template 比对；
- 28 个测试函数与 12 个已知 monitor/history/DOM 失败的行为强度未被再次执行（AST/source
  基线已冻结在 `test-functions-before.json`）；T10 三模块 before/after 未产生（无测试轮次）；
- 历史归因（owner history=T27、monitor/playground=T28、web=T29）未触碰，T10 五产品
  未改（`unmodified.json` 复验一致）。

**需要的 PM 动作（解除阻断的最小改动，均在 PM 侧）**

1. 把 `tasks/isolated/T05-eight-cases-r2.md` 的 `## 写入允许面` 恢复为与原 T05 卡同形的
   12 条 bullet list（11 产品 + `evidence/implementation/dpc-t05-eight-cases/rework-r2/**`），
   让 `_card_write_face_entries` 抽出 12 条；
2. 重派本卡（或按 `allow_foreign_write` 之外的正规路径给足写面），新 `task.md` 头应含 12 条；
3. 重派后本 R2 可直接照卡执行：先红（模板 schema3 八入口 + prepared_at 真实过去时刻），
   再定点改 generator/template、私有 out 重生成 8 case、逐字节与四旧 SHA 复核。

未做：未伪造 `dp2` steer/id/receipt、未请求或伪造人批准、未改 task.md/卡/PM 证据、
未绕过守卫、未复制/影子共享模块、未新增预算/watchdog/timeout/权限。

## 上下文来源

- 卡：`H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\tasks\isolated\T05-eight-cases-r2.md`
  （frontmatter 12 条写面；`## 写入允许面` 散文段）
- 派发：`...\workers\dpc-t05-eight-cases-r2\task.md`（`write_face:` 单条 head）
- 原 T05 对照：`...\tasks\isolated\T05-eight-cases.md`（12 条 bullet）
  + `...\workers\dpc-t05-eight-cases\task.md`（12 条 head）
- PM 红线/前置：`...\evidence\implementation\t05-pm-handoff-20261027\{probe.json,check.json,report.md}`、
  `...\evidence\implementation\t05-r2-pre-dispatch-20261027\{check.json,before-metadata.json,before-test-functions.json,pyc-protection-current.json,T10-products-protection.json}`
- 产品（只读）：`...\implementation-worktree\packages\multi-workers\scripts\build_decide_cases.py`、
  `...\decide_book_template.json`、`...\test_decision_context_workbench.py`、
  `...\decide_cases\*.json`
- 契约/守卫（只读）：`...\packages\multi-workers\decision_book.py`、
  `...\decision_points.py`、`...\autopilot\dispatch.py`、`...\autopilot\write_face.py`、
  `...\packages\coding-agent\src\extensions\agent-team-loop\worker\worker-mode.ts`
- 目标/规格：`.agenticdoc/goal.md:5`、`.agenticdoc/mw-dp-consolidation/spec.md:128`、
  `design.md:201`
