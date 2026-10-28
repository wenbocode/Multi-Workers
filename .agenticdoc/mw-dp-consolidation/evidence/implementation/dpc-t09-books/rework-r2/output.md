# T09 R2 输出（本层：book 库面四个定点根因）

## 结论

状态：完成（本层），rc 全绿；四组已复现根因按「先真红、再最小实现、后全绿」修复，只动两个产品文件。

- stdin 只接受单个 book 对象：`null/[]/[book]/bool/int/float` 与「JSON 字符串指向真实 book 文件」都变成具体 `book-schema` issue（`path=book`），`prepared=None`，不读文件、不写账本、无逃逸 TypeError；`prepare_request(path)` 文件 API 照旧工作。
- 非法文件报告可序列化：装载失败 entry 补 `ok=False`，`BookReport.as_dict()` 不再 `KeyError: 'ok'`，非法文件仍 ok=false 且保留原 issue；合法/混合 bundle 独立结果不变。
- schema/装载/检查失败 detail 不再回显已知秘密：unknown top-level/notes key、坏 version、unknown DP 等改走既有 `decision.secret_hit` / `decision.safe_path_text` 与传入 redactor（键 → `<key>`，值 → `<redacted>`），具体措辞、错误码与 notes/state 语义不降级，非秘密值仍点名。
- `schema_version` 只接受真正的非 bool 整数 `3`：`3.0`/`2`/`"3"`/`True`/`None`/`[3]` 拒绝，int 3 控制合法，无旧版升级或别名。

量化：原 109 用例（43 个测试函数，AST 与源码段 SHA 全等）零改动；新增 7 函数 → 22 例；套件 109 → 131，assigned 两次 `131 passed`/rc0。独立 21 例 probe：修前 7/14（PM 那 17 例基准 4/13，与 PM `probe.json` 同因），修后 21/0（基准 17/17）/rc0。镜像 1883 文件净变化恰为两个产品文件；14 个既有 `.pyc`、692 个原 T09/PM 证据文件字节未变。

不宣称：semantic 通过、`npm run check`、完整 L2、观察/context projection、CLI stdin 接线、QG、signoff、部署；PM 独立 17 fixture 复验与 ack 仍由 PM 执行。

## 证据

全部路径仓库根相对，根目录 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/`。

- before 冻结（与卡期望一致，写入前完整读两产品到 EOF）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes/decision_book.py.before`（59531 B，`dbe2329a…`，1559 LF/0 CRLF）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/before-bytes/test_decision_context_contract.py.before`（51264 B，`9bbf89d6…`，1348 LF/0 CRLF）
- 未改实现时的真实红：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.stdout`（`14 failed, 117 passed`，六次 stdin TypeError、`must never load a file`、`KeyError: 'ok'`、四次秘密回显、`load_book(redactor=)` TypeError、`3.0 → issues=[]`）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.stderr`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/red-1.rc`（1）
- assigned 基线（未改文件，两次）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-1.stdout`（`109 passed`）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/baseline-2.stdout`（`109 passed`），各自 `.stderr`/`.rc`(0)/`.argv.json`
- 绿（实现后三次）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-1.stdout`（`131 passed`）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-2.stdout`（`131 passed`）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/green-3.stdout`（写报告后复跑，`131 passed`），各自 `.stderr`(0 B)/`.rc`(0)/`.argv.json`（argv = `python -B -m pytest -p no:cacheprovider -q test_decision_context_contract.py --basetemp …`，cwd = 副本 `packages/multi-workers`，最小环境 + 私有 HOME/USERPROFILE/TEMP + `PYTHONDONTWRITEBYTECODE=1` + `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`）
- 独立 probe（网络 deny，导入绑定副本；红跑用冻结快照副本）：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe-before-red.json`（基准 17 例 4 通过/13 失败，全部 7/14，rc1）+ `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-before-red.stdout|.stderr|.rc|.argv.json`；`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe-after-green.json`（基准 17/0，全部 21/0，rc0）+ `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/probe-after-green.stdout|.stderr|.rc|.argv.json`
- 原 AST 对账：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/ast-preservation.json`（43→50 函数，missing=[]、changed=[]、added=7、preserved_exactly=true），明细 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/test-functions-before.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/test-functions-after.json`，脚本 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/ast_inventory.py` + `runs/ast-inventory.stdout|.stderr|.rc`
- after 字节/SHA/EOL：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/after-bytes.json` —— decision_book.py 59531→62612 B、`dbe2329a…`→`07c08bf4aff069c2f99d606d7e6a73859873bb5b6ddd9a7c7b1f7b09375f071f`、1646+1 行、LF 1646/CRLF 0；test 51264→60473 B、`9bbf89d6…`→`e1d46887fdbb2ab4e36243d6813218f31e58a4129aa3e796966801612a21e1f0`、1585+1 行、LF 1585/CRLF 0；两者无 BOM、末尾换行、`pyc_count=14`、`pyc_unchanged=true`
- 完整增量 diff：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/diffs/decision_book.py.diff`（14308 B，21 hunks，+127/−40）、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/diffs/test_decision_context_contract.py.diff`（9834 B，2 hunks，+237/−0）
- 净 inventory：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/net-changes.json`（1883→1883，added/removed 空，modified 恰两产品，outside_declared_products=[]，protected 692 文件 0 变更）；快照 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/mirror-before.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/mirror-after.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/protected-before.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/protected-after.json`、旧 diff/基线哈希 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory/prior-artifacts.json`
- 终态自检：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.json`（`problems=[]`，重算磁盘 SHA/字节/pyc/run rc 全一致）+ `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/runs/verify-final.stdout|.stderr|.rc`
- 运行脚本：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/run_assigned.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/run_probe.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/probe_r2.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/capture_before.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/capture_after.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/inventory.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/verify_final.py`
- 完整报告：`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/report.md`

## 改动清单

产品（仅两个，均在隔离副本）：

- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py`：新增 `_safe_detail_text` / `_safe_key_names` / `_json_type_name` / `_is_schema_version`；`_schema_issues` 加 `redactor` 并对 unknown top-key/notes key/version/DP detail 去回显、版本判定收紧；`load_book`/`load_books`/`_split_bundle`/`_load_shape`/`_require_active` 增可选 `redactor` 透传；`check_book`/`check_book_file`/`prepare_request` 传递 redactor；`_check_placeholders`/`_evidence_problem` detail 去回显；`prepare_stdin_request` 新增非 Mapping 守卫（具体 book-schema issue）；`check_book_file` 装载失败 entry 补 `ok=False`。
- `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py`：顶部加 `from unittest import mock`；末尾新增第 8 节与 7 个测试函数（6 形状 stdin、JSON 字符串非路径、非法文件报告、6 层 schema 秘密、装载路径秘密、非秘密措辞保持、6 种 schema_version 取值），原 43 个函数一字未改。

证据：新增 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/**` 下的脚本、JSON、runs、diffs、inventory 与本报告/输出；未改原 T09 worker 证据、PM handoff/probe/bootstrap、R2 pre-dispatch、隔离基线、14 pyc、live 同名源码。

## 残留与未验证

- 未跑 `npm run check`（按卡仅 T32 PM-direct），未跑其它源测试/CLI/生成器/provider/全量套件。
- `prepare_stdin_request` 在副本内仍无生产调用方（CLI stdin 接线属 T23 债）；context projection、观察 seam 字段面、store、`decision.py`/`decision_points.py`/其它 redactor 未改，原 T09 的 context/观察项与旧独立 26AC 债仍归原后继写面，本 R2 不清偿。
- 版本门只拒绝，不新增升级/别名/兼容分支。
- 秘密防护仅覆盖注入的 known redactor + `decision` 既有 env 启发式（未注入时只有启发式）；测试用合成哨兵，未读写真实凭证，未真实 HTTP/provider（probe 内 socket deny）。
- 仅 Windows / Python 3.14.3 取证，无跨平台结论。
- PM 的 17 fixture 独立复验脚本/旧输出未被运行、修改或覆盖；PM 需用自己脚本对终态重跑。未改 phase/预算/watchdog/权限/签收/部署，未 commit/push，未改 live 源码；本层终态等 PM 吸收与 ack，semantic/QG/signoff 不由本报告自判。

## 上下文来源

- `.agenticdoc/mw-dp-consolidation/workers/dpc-t09-books-r2/task.md`（card_sha256 `f34bf225…`）
- `.agenticdoc/mw-dp-consolidation/tasks/isolated/T09-books.md`（原 AC/VC/禁止面/隔离合同，全文读）
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-pm-handoff-20261027/check.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-pm-handoff-20261027/probe.json`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-pm-handoff-20261027/bootstrap.py`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/t09-r2-pre-dispatch-20261027/check.json`
- `.agenticdoc/goal.md:5`、`.agenticdoc/mw-dp-consolidation/spec.md:128`、`.agenticdoc/mw-dp-consolidation/design.md:201`、`.agenticdoc/mw-dp-consolidation/implementation-isolation.md`、`.agenticdoc/mw-dp-consolidation/implementation-isolated-dag.json`
- `.agenticdoc/mw-dp-consolidation/evidence/implementation/isolation-baseline-20261026/original-bytes/packages/multi-workers/decision_book.py`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/isolation-baseline-20261026/original-bytes/packages/multi-workers/test_decision_context_contract.py`
- 写入前完整读的两个产品副本 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py`、`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py`；只读复用 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision.py`、`.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py` 的既有安全 helper
- 原 T09 worker 证据（原样保护）`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/report.md`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/diffs/decision_book.py.diff`、`.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/diffs/test_decision_context_contract.py.diff`
