# Evidence: plan-baseline-drift-map-20260925（T-00）

基线 commit：`a0c36fcce fix(autopilot): read the L3 round verdict from the documented fallback chain (output.md -> report.md) with fail-closed FAIL scan [feature-l3-verdict-source-fallback]`（前序 `1b2a1efde` verdict-freshness）。该提交落地后 `git status` 对 `packages/multi-workers/autopilot/` 净空（2026-09-25 实测）。

漂移源：上述两提交改 `_verify_loop`/`_l3_round_verdict`（+93/-30），行号整体 +57..+63。结构性论断三条复验（现行树）：

1. **`_done_transaction` 唯一调用点** ✅ —— conductor.py:1292（`if _done_transaction(project_root, st, key, l3_source) != "below":`）。
2. **meets 分支无 l3 预算检查** ✅ —— :1288 `if verdict == "meets" and l3_source is not None:` → :1289-1291 事务调用与 `return False`；`used >= l3_limit`（:1295）仅在事务返回 below 的 fall-through 落径可达。reprompt 分支须自持预算（F-10/P-009 依据在现行树成立）。
3. **`_done_transaction` 步骤序不变** ✅ —— def :1382；入口 DONE 短路 :1394-1395；QG write-once :1406-1421；step-1b verdict 持久化 :1425；step-2 覆盖守卫 :1427-1431（stat → write_text，仍非原子）；≥200B 后验 :1432-1439；step-4 PASS :1441-1442；step-5 advance :1444-1452（err 于 :1447 交 `_record_advance_result` 后在 :1451-1452 丢弃——D-001 依据成立）；set-phase 后验 :1453-1468；OSError catch :1470-1472。

## 锚点映射表（研究时 → 现行）

| 结构 | 研究时 | 现行 |
|------|--------|------|
| `_l3_prompt` def | :1110 | :1113 |
| `_l3_round_verdict` def | :1131（2 元组） | :1186（**3 元组** `(verdict, worker_status, l3_source)`） |
| `_verify_loop` def | :1161 | :1218 |
| in-flight 双前缀守卫 | :1188-1190 | :1245-1247 |
| `l3_limit =` | :1181-1182 | :1239 |
| no-verdict 预算先例 | :1210 | :1273 |
| meets 分支 | :1225-1230 | :1288-1296（新增 `and l3_source is not None`；无源回退 fall-through 至 below 路径——**D-005 分支 4 映射点**） |
| `_done_transaction` 调用点 | :1229 | :1292 |
| below 预算检查 | :1232 | :1295 |
| `_done_transaction` def | :1319 | :1382 |
| 9 个 return 点 | :1332/:1336/:1340/:1376/:1379/:1389/:1405/:1406/:1409 | **:1395(adv)/:1399(below)/:1403(below)/:1439(below)/:1442(gated)/:1452(gated)/:1468(gated)/:1469(adv)/:1472(gated)** |
| 入口 DONE 短路 | :1330-1332 | :1394-1395 |
| step-2 覆盖守卫 | :1363-1369 | :1427-1431 |
| step-5 advance + err 丢弃 | :1381-1389 | :1444-1452 |
| `_advance_failure_streak` def | :744 | :747 |
| `_record_advance_result` def | :809 | :812 |
| `_closure_dossier_md` def | :663 | :666 |
| `_persist_l3_verdict` def | :619 | :619（未动） |
| `_append_pass_line` def | :1272 | :1335 |
| `_mark_key_done` def | — | :1752（终态清扫插入点） |
| `_apply_stalled_rejections` def | — | :1864（终态清扫插入点） |
| `mark_stalled` def | :1835 | :1898 |

## 新增事实（本 key 消费面相关）

- `_GATE_BLOCKED_MARKERS`（:703, :731）：verdict-freshness key 在 `_classify_advance_failure` 区域新增的门禁分类标记——与 streak 机制协作，不影响本 key 的 failure-line 解析（本 key 从 `_done_transaction` 回传的 err 原文提取，不经过分类器）。
- 其余 advance 调用点（:896 `_advance_key`、:1066 execute->verify）同样 `code, _out, err = advance.advance(...)` 捕获 err——D-001 仅需改 `_done_transaction` 内部一处 + 调用点。

## 结论

设计 D-001..D-007 的全部结构性依据在现行基线成立；T-03..T-05 以本表现行锚点施工。meets∧无源回退（I-1/I-2 注释：fail-closed 冗余分支）fall-through 至 below 路径，与 D-005 分支 4 语义无冲突。
