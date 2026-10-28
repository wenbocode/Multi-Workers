# T03-R3 worker output（dpc-t03-protocol-r3）

## 结论

R3 完成：唯一允许的测试文件内两个残留根因修复，真实 red→green，原验收与两 validator 断言保留；仅改 1 个产品文件，4 文件/13-handoff/主树/原证据边界均已核。只签局部测试返工，不放行 T04/S1/L2/QG/签收。

## 证据

- before：`2026-10-26T04:33:09.555166Z`，基线 166 passed（`baseline-before-edit.log`）；四文件 bytes/SHA/EOL 与 before 字节副本已保存。
- red（旧 helper/断言未改）：`red-r3-full-suite.log` = 12 failed/169 passed；`red-r3-new-tests.log` = 12 failed/3 passed。断言A red 在旧行448 `assert {"dp4-failure-handling"} <= set(by_dp)`；断言B red 在旧 post-T04 `retired_rows == LEGACY_TS_ROWS`（仅保留 dp4 时失败），两者分别可证。
- green：`green-r3-new-tests.log` = 15 passed；`green-r3-full-suite.log`、`green-r3-acceptance-final.log` = 181 passed，rc0（cwd/argv/最小 env 全量记录）。
- 正例：post-T04 active-only 八行（无旧行/无 `DP1_ID`）、post-T04 四旧行过渡、post-T04 部分旧行、新名 `[CONST]`+字面键。反例：重复/未加引号 key、非字符串/空字段、未知常量、空矩阵、未终止/截断表、未知 ID、pre-T04 active 行、生成 TS 混合/重复 id；全部有明确拒绝（`probe-r3.json` 交叉确认，synthetic 标记明确，非 T04 生成/parity/接线/编译证据）。
- 边界：after 仅 `test_decide_registry_contract.py` 变化（23724→39079B，`67b74a47…→c0e35cf1…`，+434/−27，964 LF/0 CRLF，`r3-changes.diff` 518 行 5 hunk）；另 3 产品文件、7 受保护 peer、主树 hash、原 T03/R2 证据均未变；13 行 handoff 13/13 等于 R2 after（该表 R2 仅 decision_points.py 一变；两个测试不在 13 表内，不混计）。

## 残留与未验证

- 真实树仍 pre-T04；T04/T11 过渡仅 parser 层 synthetic 证明，未真实生成/编译/parity/接线。
- 未跑 T04/T05 生成器、JSON 再生、TS tests、npm check/build/install/restart/commit；无 HTTP/决策 CLI/服务/真实 provider。
- parser 仅覆盖该字面表；空 legacy 表按反例拒绝；mtime 扫描非独占作者/全树干净证明；13 表不含两个测试文件。

## 上下文来源

- 本卡 task.md 与 `t03-r3-approval-20261026.md`；R2 handoff report/check/probe、13 行 handoff 表、before/after manifests、`t03-r3-pre-dispatch/` 基线。
- 两测试全文；`decision_points.py` 1–7103、`triage-client.ts` 1126、`decide-registry.generated.ts` 930 行均读到 EOF。

## 改动清单

- 唯一产品改动 `implementation-worktree/packages/multi-workers/test_decide_registry_contract.py`：`_ts_required_fields` 结构解析（去 dp4/DP1_ID 前提，支持 `[CONST]`/字面键，拒绝未解析/截断/重复/非法 key/空矩阵）、`test_ts_required_rows_follow_the_registry_stage` post-T04 旧行不强制、新增 15 用例、docstring 同步。
- evidence：`evidence/implementation/dpc-t03-protocol/rework-r3/**`（report.md、manifest、diff、日志、probe、boundaries、mtime、fixtures、隔离环境）。
