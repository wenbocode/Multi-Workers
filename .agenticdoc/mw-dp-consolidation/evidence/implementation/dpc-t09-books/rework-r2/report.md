# T09 R2 — book 库面四个已复现根因的定点修复（本层报告）

仓库根相对路径；本报告只覆盖 `.agenticdoc/mw-dp-consolidation/implementation-worktree` 下 book 库面这一层，不代表完整 L2、`npm run check`、QG、signoff 或人工权限。

## 结论

本层完成：PM 独立复验暴露的四组根因已在 book 库面按「先复现红、再最小实现、后全绿」修完，未重写架构、未扩大产品面。

- 根因 1（stdin 非对象）：`prepare_stdin_request` 过去把 JSON 解析后的 `null/[]/[book]/bool/int/float` 当路径传给 `prepare_request`，六次 TypeError，且 JSON 字符串指向真实 book 文件时竟准备成功。现在 stdin 只接受单个 book 对象，非对象一律返回具体 `book-schema` issue（`path=book`，detail 含 JSON 类型名与「one book object」），`prepared=None`，不读文件、不写账本、无逃逸异常；`prepare_request(path)` 仍是唯一文件权威且照旧工作。
- 根因 2（非法文件报告）：`check_book_file` 装载失败时追加的 entry 缺 `ok`，`BookReport.as_dict()` 抛 `KeyError: 'ok'`。现在装载失败 entry 带 `ok=False` + 原始 issue，`as_dict()` 可完整序列化，非法文件仍然 ok=false 且不造合法书；合法/混合 bundle 的独立结果保留。
- 根因 3（schema detail 回显已知秘密）：unknown top-level key、unknown notes key、坏 `schema_version`、unknown `decision_point` 直接 `repr` 业务输入，注入的 known redactor 无效。现在 schema/装载/检查失败路径统一走既有 `decision.secret_hit` / `decision.safe_path_text` 与传入的 known redactor（键名折叠为 `<key>`，值为 `<redacted>`），notes/state/错误码的具体措辞与码值不降级、非秘密值仍原样点名；`material`/`preparation`/`context`/`meta`/evidence 路径同口径。
- 根因 4（schema 版本）：`version != 3` 让 `3.0` 通过。现在只接受真正的非 bool 整数 `3`，`3.0`/`2`/`"3"`/`True`/`None`/`[3]` 全部拒绝，int 3 控制合法；不引入旧版升级或别名。

量化结果：原 109 测试函数体（43 个函数、AST 与源码段 SHA 全等）零改动，新增 7 个函数 → 采集 22 例，套件 109→131；assigned 命令两次 `131 passed` / rc 0。独立 21 例边界 probe（含 PM 那 17 例等价输入）：修前 7 通过 14 失败（17 例基准 4 通过 13 失败，与 PM `check.json` 的 4/13 一致），修后 21 通过 0 失败（基准 17/17）、rc 0。镜像 1883 文件净变化恰为两个产品文件，14 个既有 `.pyc` 与 692 个原 T09/PM 证据文件字节未变。

本层不宣称：semantic 通过、`npm run check`、完整 L2、观察/context projection、CLI stdin 接线、QG、signoff、部署；PM 的 17 fixture 独立复验与 ack 仍由 PM 执行。

## 证据

### 1. 阅读与 before 冻结（写入前完成）

两个产品副本在写入前被完整读到 EOF（`decision_book.py` 1560 行 / `test_decision_context_contract.py` 1348 行），before 字节与 R2 卡期望一致：

| 文件 | before bytes | before SHA256 | 行 | LF | CRLF | BOM | 末尾换行 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py` | 59531 | `dbe2329aa0b84ae10c484f526e812cae36545590c17d857bbfde040f302d32a0` | 1559+1 | 1559 | 0 | 无 | 是 |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py` | 51264 | `9bbf89d6e03a6b6d60dd511d37509cc632d61e6c4ea9f3ae7c821da079ff2176` | 1348+1 | 1348 | 0 | 无 | 是 |

- before 冻结副本（只读快照，未被覆盖）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes/decision_book.py.before`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes/test_decision_context_contract.py.before`
- 记录：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes.json`（含 14 个既有 `.pyc` 路径/字节/SHA）
- 既有（原 T09）完整 diff 原样保护并核对哈希，未改动：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/diffs/decision_book.py.diff`（76761 B，`254d18042238b93b9f43233620e372b93bd61d14dd423325bfc705dc76f6f8fd`，27 hunks）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/diffs/test_decision_context_contract.py.diff`（90078 B，`d178bf84fc3684499c4f8c6a12f0eaefcdc9f3b3b57328dd31b9d35472fb76d5`，4 hunks）；与 PM `t09-pm-handoff-20261027/check.json` 的 `worker_diff_raw_sha256` 一致。
- 隔离基线（原仓 seed，非本次写入）：`fc6d74a31abbddfa2c4a246f7a55cc23ba4c4844a41ed10d6547b2fc006b129f`（54796 B）、`ea6429088c285382736f634a3233b7c94659c2a381e60b0ad9380a0157b8e7cf`（35858 B），见 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/prior-artifacts.json`

### 2. 复现红（真实失败，不是环境/collection）

assigned 命令（cwd = `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`，最小环境、私有 HOME/USERPROFILE/TEMP、`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、无 cache）：

```
python -B -m pytest -p no:cacheprovider -q test_decision_context_contract.py --basetemp <R2>/fixture/basetemp-<label>
```

| run | 结果 | rc | 证据 |
| --- | --- | --- | --- |
| baseline-1（未改任何文件） | 109 passed | 0 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-1.stdout` / `.stderr` / `.rc` |
| baseline-2（未改任何文件） | 109 passed | 0 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-2.stdout` / `.stderr` / `.rc` |
| red-1（只加新测试，未改实现） | 14 failed, 117 passed | 1 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.stdout` / `.stderr` / `.rc` |

red-1 的 14 个失败逐条是四组真因（stdout 原文摘要）：六次 `TypeError: argument should be a str or an os.PathLike object ... not 'NoneType'/'list'/'bool'/'int'/'float'`；`AssertionError: a non-object stdin payload must never load a file`；`KeyError: 'ok'`；四次 `AssertionError: ["book-schema ... detail 内含 pm-known-opaque-business-secret"]`；`TypeError: load_book() got an unexpected keyword argument 'redactor'`；`schema_version=3.0 → issues=[]`。原 109 在 red-1 中仍全绿（117 = 109 + 8 个新用例，那 8 例是已正确路径/其它取值）。

独立 probe（本 R2 自有脚本，网络 deny，导入绑定副本；before 运行通过 `fixture/before-module/decision_book.py` 载入冻结快照，产品文件从未被换回）：

| probe run | 基准 17 例 | 全部 21 例 | rc | 证据 |
| --- | --- | --- | --- | --- |
| before-red | 4 通过 / 13 失败 | 7 / 14 | 1 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe-before-red.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-before-red.stdout` / `.stderr` / `.rc` |
| after-green | 17 通过 / 0 失败 | 21 / 0 | 0 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe-after-green.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-after-green.stdout` / `.stderr` / `.rc` |

before-red 的 13 个失败与 PM `evidence/implementation/t09-pm-handoff-20261027/probe.json` 的 4/13 逐例同因（六种 stdin 非对象 TypeError、JSON 字符串被当路径、`as_dict` KeyError、四次秘密回显、`3.0` 被接受）；本 probe 另含 4 个额外判据（嵌套 schema 错型不回显、非秘密 unknown DP 仍点名、混合 bundle 独立 ok、int3/3.0/"3"/True 版本控制），修前 `extra-version-controls` 失败（3.0 被接受），修后全过。

### 3. 绿（新红→实现→全绿，两次 repeat）

| run | 结果 | rc | 证据 |
| --- | --- | --- | --- |
| green-1 | 131 passed | 0 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-1.stdout` / `.stderr` / `.rc` |
| green-2 | 131 passed | 0 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.stdout` / `.stderr` / `.rc` |
| green-3（写报告后复跑） | 131 passed | 0 | `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.stdout` / `.stderr` / `.rc` |

三次运行的 `argv`/`cwd`/env 见 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.argv.json` 与 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.argv.json`（stderr 均 0 B）。

### 4. 原 AST 完整保留对账

- 对账脚本：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/ast_inventory.py`；结论：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/ast-preservation.json`，逐函数明细 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/test-functions-before.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/test-functions-after.json`
- 结果：before 43 个 `test_*` 函数 → after 50 个；`missing=[]`、`changed=[]`（源码段 SHA256 与 `ast.dump` SHA256 双口径全等）、`added=7`、`preserved_exactly=true`。
- 采集数：43 函数 → 109 例（baseline/green 稳定），50 函数 → 131 例；新增 7 函数展开 22 例：6 种非对象 stdin 形状、1 JSON 字符串、1 非法文件报告、6 种 schema 秘密回显层、1 装载路径秘密、1 具体措辞、6 种 schema_version 取值。

### 5. after 字节/SHA/EOL 与增量 diff

| 文件 | before bytes | after bytes | before SHA256 | after SHA256 | 行 | LF | CRLF | BOM | 末尾换行 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py` | 59531 | 62612 | `dbe2329aa0b84ae10c484f526e812cae36545590c17d857bbfde040f302d32a0` | `07c08bf4aff069c2f99d606d7e6a73859873bb5b6ddd9a7c7b1f7b09375f071f` | 1646+1 | 1646 | 0 | 无 | 是 |
| `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py` | 51264 | 60473 | `9bbf89d6e03a6b6d60dd511d37509cc632d61e6c4ea9f3ae7c821da079ff2176` | `e1d46887fdbb2ab4e36243d6813218f31e58a4129aa3e796966801612a21e1f0` | 1585+1 | 1585 | 0 | 无 | 是 |

- 完整增量 diff（before 快照 → 当前，`-U3`）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/diffs/decision_book.py.diff`（14308 B，21 hunks，+127/−40）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/diffs/test_decision_context_contract.py.diff`（9834 B，2 hunks，+237/−0；两个 hunk 分别是 `from unittest import mock` 与文件末尾新增第 8 节）
- 记录：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/after-bytes.json`（`pyc_count=14`、`pyc_unchanged=true`）

### 6. 净 inventory（只动两个产品面）

- 镜像（implementation-worktree 全量，含 14 pyc）：before 1883 / after 1883，`added=[]`、`removed=[]`、`modified` 恰为两个产品文件、`outside_declared_products=[]`：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/net-changes.json`（快照 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/mirror-before.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/mirror-after.json`）
- 原 T09 worker 证据 + PM handoff + R2 pre-dispatch + 原 pre-dispatch 共 692 文件：`protected_added=[]`、`protected_removed=[]`、`protected_modified=[]`（`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/protected-before.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/protected-after.json`）
- 14 个既有 `.pyc` 未删未改（同一路径集合 + 同一 SHA，见 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/after-bytes.json`）；未生成 `.pytest_cache`/新 `__pycache__`（镜像无新增文件）；R2 证据目录内无 `.pyc`/缓存目录。
- live 同名源码未被本次写入：`packages/multi-workers/decision_book.py`（`fc6d74a…`，mtime 2026-10-22 16:00:44）与 `packages/multi-workers/test_decision_context_contract.py`（`ea64290…`，mtime 2026-10-23 16:36:44）仍是隔离 seed 原字节，mtime 早于本次会话。
- 未改 `decision.py` / `decision_points.py` / 其它 key redactor / CLI / store / context / 观察 / 框架 / goal / spec / design / 预算 / 权限 / 签收 / 14 pyc。

### 7. 终态自检

`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/verify_final.py` 重算磁盘字节并比对全部记录：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.json`（`problems=[]`，rc 0；stdout/stderr/rc 同目录）。所有 run 的 stdout/stderr/rc 齐全，stderr 除该次 probe 外的两个失败 run 都为 0 B（失败原因全在 stdout）。

## 改动清单

产品文件（仅两个，均在隔离副本）：

- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py`
  - 新增 detail 安全 helper：`_safe_detail_text`（对 `decision.secret_hit` 命中的值输出 `<redacted>`，否则保持原 `repr`）、`_safe_key_names`（逐键走 `decision.safe_path_text`，秘密/异常键折叠 `<key>`）、`_json_type_name`（只给 JSON 类型名）、`_is_schema_version`（真正的非 bool 整数 3）。
  - `_schema_issues(data, *, redactor=None)`：unknown top-level keys、unknown notes keys、坏 `schema_version`、retired/unknown `decision_point` 的 detail 全部改走上述 helper；版本判定由 `isinstance(version, bool) or version != 3` 改为 `_is_schema_version`。
  - `load_book` / `load_books` / `_split_bundle` / `_load_shape` / `_require_active`：新增可选 `redactor` 关键字并透传（纯增量参数，全部既有位置调用不受影响）。
  - `check_book`：把调用方 `redactor` 传入 `_schema_issues` 与 `_check_placeholders`；`check_book_file` 把 `redactor` 传入 `load_books`。
  - `_check_placeholders` / `_evidence_problem`：新增可选 `redactor`，占位值与 evidence 路径的 detail 不再原样 `repr` 秘密（非秘密值措辞不变）。
  - `prepare_request`：按 path 装载时把自己的 `redactor` 传给 `load_book`。
  - `prepare_stdin_request`：bundle 拒绝保持；新增非 `Mapping` 守卫 —— 返回 `(None, Issue("book-schema", "book", "stdin carries exactly one book object; got a JSON <type> ..."))`，永不进入 `prepare_request`。
  - `check_book_file`：装载失败 entry 补 `"ok": False`（`label`/`decision_point` 仍为 `None`，issue 原样），`BookReport.as_dict()` 不再 KeyError，`report.ok` 仍 False。
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py`
  - 顶部新增 `from unittest import mock`（stdlib，单行）。
  - 文件末尾新增第 8 节（原有第 1–7 节与 43 个函数一字未改）：`KNOWN_SECRET` 合成哨兵、`_no_file_authority`，以及 7 个新函数 `test_stdin_refuses_every_non_object_json_shape_as_a_schema_issue`（6 例）、`test_stdin_json_string_is_data_and_never_a_file_path`、`test_an_invalid_book_file_report_is_serializable_and_still_failed`、`test_schema_refusals_never_echo_a_known_secret`（6 层）、`test_a_schema_refusal_on_load_never_echoes_a_known_secret`、`test_schema_details_stay_specific_for_non_secret_values`、`test_schema_version_must_be_the_real_non_bool_integer_three`（6 例）。

R2 证据/脚本（全部新增，未覆盖任何旧证据）：

- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/report.md`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/output.md`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/after-bytes.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes/decision_book.py.before`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes/test_decision_context_contract.py.before`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/diffs/decision_book.py.diff`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/diffs/test_decision_context_contract.py.diff`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe-before-red.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe-after-green.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/capture_before.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/capture_after.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/run_assigned.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/run_probe.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe_r2.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/ast_inventory.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/verify_final.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/ast-preservation.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/test-functions-before.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/test-functions-after.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/mirror-before.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/mirror-after.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/protected-before.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/protected-after.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/net-changes.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/prior-artifacts.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-1.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-1.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-1.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-1.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-2.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-2.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-2.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-2.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-1.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-1.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-1.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-1.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-before-red.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-before-red.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-before-red.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-before-red.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-after-green.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-after-green.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-after-green.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-after-green.argv.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/ast-inventory.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/ast-inventory.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/ast-inventory.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/capture-after.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/capture-after.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/capture-after.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/inventory-after.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/inventory-after.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/inventory-after.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.stdout`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.stderr`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.rc`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/before-module/decision_book.py`（before 快照的只读运行副本，SHA `dbe2329a…`，仅用于红 probe）
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/probe-project/`（probe 私有 project/home/临时夹具，仅本目录）
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/basetemp-baseline-1/`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/basetemp-baseline-2/`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/basetemp-red-1/`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/basetemp-green-1/`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/basetemp-green-2/`（pytest `--basetemp`，仅临时夹具）
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/home/`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/fixture/tmp/`（私有 HOME/USERPROFILE/TEMP）

## 残留与未验证

- 未运行 `npm run check`（按卡只由 T32 PM-direct 在等价保护副本执行），因此 biome/tsgo/依赖类检查对本次两文件无结论；未跑任何其它源测试、CLI、生成器、provider、全量套件。
- 未验证/未改：`prepare_stdin_request` 在副本内仍无生产调用方（CLI 的 stdin 入口接线属 T23 债）；context projection、观察 seam 的字段面、CLI/store、`decision.py`/`decision_points.py`/其它 redactor 实现均未触碰，原 T09 报告中的 context/观察项与旧独立 26AC 测试债仍归原后继写面，本 R2 不清偿。
- 版本门只做拒绝（float/string/bool 不再冒充 3），未新增任何旧版升级、别名或兼容分支；未扩大 schema 版本范围。
- 秘密防护只覆盖「调用方注入的 known redactor + `decision` 既有 env 启发式」：未注入 redactor 的调用方仍只有启发式（本层不宣称能识别配置里的任意凭据）；测试用本卡合成哨兵 `pm-known-opaque-business-secret`，全程未读/未写真实凭证，未真实 HTTP/provider，probe 内 socket 已 deny。
- 只在 Windows / Python 3.14.3 上取证，未做跨平台（POSIX 路径/权限/EOL 编码器差异）验证。
- PM 的 17 fixture 独立复验脚本与旧输出未被我运行、修改或覆盖；我的是独立实现（`probe_r2.py`）的等价输入，PM 仍需用自己的脚本对终态重跑。原 PM/worker run/output/trace/manifest/state 与前端证据全部字节未变（692 文件哈希核对）。
- 未改 phase/预算/watchdog/权限/签收/部署，未 commit/push，未改 live 同名源码，未重启服务；本层终态只等 PM 吸收与 ack，semantic/QG/signoff 不由本报告自判。
- `fixture/basetemp-*` 与 `fixture/probe-project/` 下是 pytest/probe 临时夹具（含 probe 生成的 `book.json`/`legacy.json`/`bundle.json`/`.git` 空标记），不是产品、不是业务 PASS 证据。

## 上下文来源

- 本 R2 卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-t09-books-r2/task.md`（含 `card_sha256=f34bf2252bef66d990cc2c5b97a2c57402015eedcbc5ae6dd497ade2d46bf9bc`、`decision: dp1-dispatch-type:1aa40474-…`、写入允许面三行）
- 原隔离任务卡（全文读，AC/VC/禁止面/隔离合同继承）：`.agenticdoc/mw-dp-consolidation/tasks/isolated/T09-books.md`
- PM handoff 证据：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-pm-handoff-20261027/check.json`（两次 assigned 109 passed/rc0、`probe_passed=4`/`probe_failed=13`、`semantic_handoff_verified=false`）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-pm-handoff-20261027/probe.json`（13 例失败明细）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-pm-handoff-20261027/bootstrap.py`（PM 的隔离/网络 deny/绑定副本方式，本 R2 未修改亦未覆盖其输出）
- R2 派发前核对：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-r2-pre-dispatch-20261027/check.json`（card sha、`mirror_net_changes_since_PM_verification=[]`、`real_independent_fixture_failures=13`、`only_existing_two_product_faces=true`）
- 目标/规范/设计锚点：`.agenticdoc/goal.md:5`、`.agenticdoc/mw-dp-consolidation/spec.md:128`、`.agenticdoc/mw-dp-consolidation/design.md:201`；隔离实施映射：`.agenticdoc/mw-dp-consolidation/implementation-isolation.md`、`.agenticdoc/mw-dp-consolidation/implementation-isolated-dag.json`
- 隔离基线原字节：`.agenticdoc/mw-dp-consolidation/evidence/implementation/isolation-baseline-20261026/original-bytes/packages/multi-workers/decision_book.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/isolation-baseline-20261026/original-bytes/packages/multi-workers/test_decision_context_contract.py`
- 原 T09 worker 证据（原样保护，未改）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/report.md`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/diffs/decision_book.py.diff`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/diffs/test_decision_context_contract.py.diff`
- 当前产品源码（写入前均读到 EOF，写入后逐行复核）：`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py`、`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py`
- 复用而不修改的安全 helper 实现（只读定位）：`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision.py`（`known_secret_redactor`/`secret_hit`/`safe_path_text`）、`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py`（`require_active_dp`/`is_retired_dp`/`entry_material_issues`/`preparation_issues`）
- 产物证据目录：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/`（本报告全部路径的根）
