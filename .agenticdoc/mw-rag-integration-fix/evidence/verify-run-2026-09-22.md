# T-18 独立验证报告（第三方视角）

- key: `mw-rag-integration-fix`
- 报告文件: `.agenticdoc/mw-rag-integration-fix/evidence/verify-run-2026-09-22.md`
- 源码基线: 工作区（未 commit）`HEAD=d106bcfb2` + T-15/16/17/19 的工作区改动
- 立场: 第三方复核，实测优先；每个 `[VERIFY]` 行给「断言 | 发射位置 file:line | 实测行原文 | 证据强度」

## 结论（TL;DR）

- **判定：通过（PASS）**，但附证据行降级（VC-102 与 VC-105 两侧行内为字面量；VC-111 两侧为直调纯函数）+ 1 条层级降级建议。
- 全套基线复现：TS `rag-*` **105 passed | 1 skipped**（与基线一致）；`agent-team-loop*`+`autopilot-*` **488 passed / 14 files**；Python 全量 **805 passed, 9 deselected**（基线 802，+3 为 T-16 新增，零失败）；定向 `test_rag_*.py` **79 passed**；golden sha256 `00f85e64…`（347 B）不变。
- `npm run check` **exit 0**（1080 files，`No fixes applied`）。
- bundle `packages/multi-workers/dist/extensions/agent-team-loop.js` = **888791 B**，`Self-check OK (activate)`，`resolveDefaults` **×3**，mtime `21:45:17` **晚于**全部 `rag/*.ts` 与 `worker/worker-mode.ts`（最晚 `21:36:40`）→ 产物新鲜，非假交付。
- 三条反例全部按预期证伪并 100% 还原（sha256 复原）：A 使 `rag-role-defaults` 红（wire 变 `rag_search`）；B 使 VC-106 有文档用例红、无文档用例仍绿；C 使 Python VC-111 红而 TS 侧不受影响。
- **降级项**：`[VERIFY] VC-102`/`VC-105`（TS+Py）行内字段是字面量而非常量观测 → **弱/装饰**（断言本身仍强，见 §2）。
- **层级裁定：VC-018/VC-106 应降 L1**（不是维持 L2）：证据定义 L2 = 真实时序/长调用/看门狗观察，而现有用例是假 pi + 合成 `agent_settled` 的进程内集成测试（L1）；反例 B 已证明其可证伪，故应如实声明 L1，不得保留 L2 声明（见 §2 VC-106 与 §6）。
- `rg -n 'MW_RAG_ENABLED'`：代码与 env 文档路径 **零命中**；`packages/multi-workers/CHANGELOG.md:41` 恰 **1 处刻意提及**（PM 要求可被变量名 grep 到，非残留读写方）。
- 红线：未 commit；除本报告外未改动任何文件（三条反例均已还原，见 §5）。

## §0 复现命令表

| # | 命令（cwd 见备注） | 结果 |
|---|---|---|
| 1a | `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag`（cd `packages/coding-agent`） | `Test Files 12 passed | 1 skipped (13)`；`Tests 105 passed | 1 skipped (106)` |
| 1b | `... --run test/extensions/agent-team-loop test/suite/autopilot` | `Test Files 14 passed (14)`；`Tests 488 passed (488)` |
| 2 | `python -m pytest -q`（cd `packages/multi-workers`） | `805 passed, 9 deselected in 81.33s`（无失败） |
| 3 | `python -m pytest test_rag_audit.py test_rag_config.py test_rag_phase.py test_rag_cli.py test_rag_launcher.py test_rag_research.py -q -s` | `79 passed in 9.27s` |
| 4 | `(Get-FileHash test/fixtures/rag-block.golden.md -Algorithm SHA256)` + `pytest test_rag_config.py -q -k golden -s` | sha256=`00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`，347 B；`1 passed, 13 deselected` |
| 5 | `git diff --stat -- test_autopilot_l0.py` | 空（exit 0）；`git status --porcelain -- test_autopilot_l0.py` 空 |
| 6 | `npm run check`（仓根） | **exit 0**；`Checked 1080 files … No fixes applied`；pinned-deps / ts-imports / shrinkwrap / install-lock / browser-smoke 全过 |
| 7 | bundle 体积 / 自检 / `rg -c resolveDefaults` / mtime | 888791 B；`Self-check OK: default export loads as a function (activate)`；3；bundle 21:45:17 > 源码最晚 21:36:40 |
| 8a | 反例 A（改 `rag-role-defaults.test.ts` 的 `rewrite:true→false`） | VC-101 测试红：`expected [ 'rag_search' ] to deeply equal [ 'rag_search_multi_rounds' ]`；已还原 |
| 8b | 反例 B（改 `worker-mode.ts:539` key 目录 → 不存在的子目录） | VC-106 用例 1 红（trace 含 `rag-required-missing`），用例 2 绿；已还原 |
| 8c | 反例 C（改 `mw_common.py:342` `RAG_RESEARCH_PHASES=frozenset()`） | Python VC-111 红（`'[mw] Rewrite: false' != '[mw] Rewrite: true'`），TS VC-111 仍绿；已还原 |
| 9 | `rg -n 'MW_RAG_ENABLED' packages docs`（排除 CHANGELOG 口径见 §4） | 代码/env 文档 0 命中；仅 `packages/multi-workers/CHANGELOG.md:41` 1 处刻意提及 |
| 10 | README 四条命令真跑（临时项目 `%TEMP%\mw-rag-t18-cli`，已删） | `list`=0 `probe`=0 `audit --json`=0 `sync`=0（enabled 集非空时 `[mw rag sync] installed …/.pi/skills/mw-rag.md`）；`probe --server X`=2 |

## §1 VC 汇总表

强度口径（复核报告 A 节）：**强** = `[VERIFY]` 行内至少一个字段直接取自被测运行时数据且可被反例改变；**弱** = 行内字段为字面量/常量，但同用例断言是真观测；**装饰** = 行本身不携带任何被测数据。

| VC | 断言原文摘要 | 发射位置 `file:line` | 实测行原文 | 强度 |
|---|---|---|---|---|
| VC-101 | role=design 且未显式开关 → fixture 观测 wire=`rag_search_multi_rounds`；coding → `rag_search`；显式 `multi_rounds:false` 仍 `rag_search` | `test/suite/rag-role-defaults.test.ts:199` | `[VERIFY] VC-101: design_wire=rag_search_multi_rounds coding_wire=rag_search explicit_off_wire=rag_search` | **强**（design/coding wire 来自 fixture `calls[].name`） |
| VC-102 | role 声明 `server:B` 且未显式 → 打到 B；显式 `server:A` 压过 role | `test/suite/rag-role-defaults.test.ts:234` | `[VERIFY] VC-102: role_server_hits=B explicit_A_hits=A role_default_wire=rag_search explicit_wire=rag_search` | **弱**（行内 `B`/`A` 是字面标签，两个 wire 恒为 `rag_search`；但同用例 `observedWires(fixtureA/B)` 断言为真观测） |
| VC-103 | `[VERIFY] VC-008` 的 `rewrite_tool` 与 fixture `calls[].name` 同源，反例可变 | `test/suite/rag-role-defaults.test.ts:195` | `[VERIFY] VC-008: role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1 coding_tool=rag_search` | **强**（反例 A 使 `designCall.wire[0]` 变为 `rag_search` 并判红） |
| VC-104 | 不可达 server 工具描述含 `[unreachable at session start]`；首次调用 trace 增量含 `rag-unavailable` | `test/suite/rag-unreachable.test.ts:161` | `[VERIFY] VC-104: unreachable_marker=true rag_unavailable_line=true server=A` | **强**（marker/line 为运行期计算；`server=A` 为字面标签） |
| VC-105 | `type: foobar` 未登记时 TS worker 判 role=`coding`、required 命中 | `test/suite/rag-required.test.ts:306` | `[VERIFY] VC-105: ts_role=coding ts_required=true type_literal=foobar server=A` | **弱/装饰**（行内全为字面量；真证据是 `trace.log` 含 `rag-required-missing role=coding phase=unknown server=A` 的断言） |
| VC-105 | 同上一份 `type: foobar` 的 Python audit 结论一致 | `test_rag_audit.py:453` | `[VERIFY] VC-105: py_role=coding py_required=true type_literal=foobar server=S` | **弱/装饰**（同上；真证据是 `record["role"]=="coding"`/`record["server"]=="S"`/`code==1` 断言） |
| VC-106 | 真实 key 布局下预置 `rag/A-symbol-lookup.md` → validator 取到并判 ok；无文档 → 打 marker | `test/suite/rag-required.test.ts:275` / `:290` | `[VERIFY] VC-106: runtime_doc_found=true sections=6 verdict=ok` / `[VERIFY] VC-106: missing_doc_emits_marker=true` | **强（runtime 断言）/ 行弱**（首行的 `docPath/headings/ok` 来自测试内直调 `validateResearchDoc(keyDir)`，非 runtime 捕获；runtime 主张由同用例 `trace.log`/`output.md` 无 marker 的断言承担，反例 B 可证伪） |
| VC-107 | README 四条 `mw rag` 命令逐条真跑成功；不含 `--server`；生产代码 `MW_RAG_ENABLED` 零命中 | 无 `[VERIFY]` 行 | 见 §0 #9/#10 与 §2 | **强（外部命令/文件观测）**，但无专用证据行 |
| VC-108 | 未启用项目四断言成立；`render_task_md` 旧调用逐字节相同；两套 `rag` 测试全绿；golden sha256 不变 | 无 `[VERIFY]` 行 | 见 §0 #1~#5、§3 | **强（聚合）**，无专用证据行 |
| VC-109 | 本 key 新增/修改的每条证据行至少一个字段来自被测数据（反例可变） | 无 `[VERIFY]` 行 | 见 §5（反例 A/B/C） | **强（三反例证伪）**；VC-102/VC-105 两行不满足此口径 → 已在表中降级 |
| VC-110 | 无 role/phase（PM 会话）不注入 `multi_rounds`、server 仍 `default_server`、零新文件 | `test/suite/rag-role-defaults.test.ts:264` | `[VERIFY] VC-110: role="" phase="" wire=rag_search server=default_server files_added=0` | **强**（`wire` 为 fixture 观测，`snapshotTree` 全等断言；`files_added=0` 为字面标签） |
| VC-111 | 跨语言默认解析一致：同 fixture 下 `server=A source=docs rewrite=true` | TS `test/suite/rag-parity.test.ts:302`；Py `test_rag_config.py:293` | `[VERIFY] VC-111: server=A source=docs rewrite=true`（两侧逐字相同） | **弱（两侧均直调纯函数，无 runtime 路径参与）**；但该 VC 本为解析器 parity 属性，且 `resolveDefaults` 的 runtime 接线由 VC-101/VC-110 独立覆盖，反例 C 可证伪 |

未覆盖 VC：无（VC-107/108/109 为口径/聚合型，无专用 `[VERIFY]` 行，已在上表与 §2/§3/§5 给出替代证据）。

## §2 逐 VC 明细

### VC-101（L2 fixture，强）
- 断言原文：`designCall.wire` = `["rag_search_multi_rounds"]`；`explicitOff.wire` = `["rag_search"]`；`codingCall.wire` = `["rag_search"]`。
- 运行时路径：`registerRagTools(pi, project, {role:"design"})` → `runtime.ready` → `rag_search` 工具 `execute()` → `callRag`（`rag/tools.ts:456` `resolveDefaults`）→ `ragToolCalls` 映射 wire 名 → fixture 记录 `calls[].name`。
- 实测行：`[VERIFY] VC-101: design_wire=rag_search_multi_rounds coding_wire=rag_search explicit_off_wire=rag_search`
- 强度：强。`design_wire`/`coding_wire` 来自 `observedWires()`（fixture 侧 `tools/call` 名），反例 A 改 `capabilities.rewrite` 后变为 `rag_search`（§5A）。

### VC-102（L2 fixture，弱）
- 断言原文：role 声明 `server:B` 且未显式传 → 请求命中 B 且 A 零请求；显式 `server:A` → 命中 A 且 B 观测到一次。
- 发射位置：`test/suite/rag-role-defaults.test.ts:234`。
- 实测行：`[VERIFY] VC-102: role_server_hits=B explicit_A_hits=A role_default_wire=rag_search explicit_wire=rag_search`
- 强度：**弱**。行内 `role_server_hits=B`/`explicit_A_hits=A` 是写死的标签（不是从 `fixtureA/fixtureB` 计数派生），两个 `*_wire` 恒为 `rag_search`，不随数据变。真正的证据是同用例的 `expect(observedWires(fixtureA)).toEqual([])` / `expect(observedWires(fixtureB)).toEqual(["rag_search"])`（两 server url 分离，属真观测）；即**断言强、证据行装饰**。建议后续把命中数插值进该行。

### VC-103（L2 fixture，强）
- 断言原文：`[VERIFY] VC-008` 的 `rewrite_tool` 取自 fixture 实际观测到的工具名，不得来自直调纯函数。
- 发射位置：`test/suite/rag-role-defaults.test.ts:195`（旧的 `rag-adapter.test.ts` 纯函数打印点已删，仅此一处）。
- 实测行：`[VERIFY] VC-008: role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1 coding_tool=rag_search`
- 强度：强。三个字段均为 `designCall.wire`/`codingCall.wire` 插值；反例 A 使其值改变并判红（§5A）。

### VC-104（L1 集成，强）
- 断言原文：不可达 server 激活后工具描述含 `[unreachable at session start]`；首次调用后 trace **增量**含 `rag-unavailable`。
- 运行时路径：真实 HTTP 连接到半开端口（`127.0.0.1` 不可达）→ `registerRagTools` 探活失败 → `markToolsUnreachable` 改描述；`rag_search` 首次调用返回失败并向 `trace.log` 追加 `rag-unavailable`。
- 发射位置：`test/suite/rag-unreachable.test.ts:161`。
- 实测行：`[VERIFY] VC-104: unreachable_marker=true rag_unavailable_line=true server=A`
- 强度：强。`unreachable_marker` 从捕获工具描述重算，`rag_unavailable_line` 从 trace 增量重算；仅 `server=A` 为字面标签。

### VC-105（L1+L2 两侧，弱）
- 断言原文：同一份 `type: foobar` 的 task.md，TS worker 判 role=`coding`（`roles.coding.require` 命中），Python audit 得同一 role 且 required 结论一致。
- 发射位置：TS `test/suite/rag-required.test.ts:306`；Py `test_rag_audit.py:453`。
- 实测行（两侧字面量相同 `type_literal=foobar`）：
  - `[VERIFY] VC-105: ts_role=coding ts_required=true type_literal=foobar server=A`
  - `[VERIFY] VC-105: py_role=coding py_required=true type_literal=foobar server=S`
- 强度：**弱/装饰**。两行每个字段都是字面量（`server` 一侧 `A` 一侧 `S` 甚至不同，说明它不是同一观测），不携带被测数据。真证据是同用例断言：TS `expect(trace).toContain("rag-required-missing role=coding phase=unknown server=A")`（`trace.log` 实文件）；Py `record["role"]=="coding"`、`record["server"]`==`"S"`、`code==1`（audit 报告实值）。跨语言一致性成立，但**证据行需插值才能满足 AC-108/VC-109**。

### VC-106（L1 或 L2，强但应声明 L1）
- 断言原文：真实 key 布局下预置 `rag/<server>-<slug>.md` → validator 经真实 key 路径取到并判 ok（无 marker）；无文档 → 同一路径打 marker。
- 运行时路径：`workerModeActivate` 读 `PI_WORKER_TASK` → `parseTaskMd` → `registerRagTools(..., {role: "research", phase: "EXECUTE"})`（`worker-mode.ts:669-675`）→ `agent_settled` 终态 → `emitRagRequiredMissing` → `validateResearchDoc(check.keyDir)`（`worker-mode.ts:539`），其中 `keyDir = path.dirname(meta.agenticdocRoot)`（`worker-mode.ts:1026`）指向真实 `.agenticdoc/key-a`。
- 发射位置：`test/suite/rag-required.test.ts:275`（ok）/ `:290`（missing）。
- 实测行：`[VERIFY] VC-106: runtime_doc_found=true sections=6 verdict=ok`；`[VERIFY] VC-106: missing_doc_emits_marker=true`
- 强度：**强（runtime 主张）/ 弱（[VERIFY] 行本身）**。首行字段取自测试内**直调** `validateResearchDoc(path.join(project, ".agenticdoc", "key-a"))`（真实 key 布局，但非从 worker runtime 捕获）；真正证明「runtime 确实 consult 了这份文档」的是同用例的 `expect(read(taskDir,"trace.log")).not.toContain("rag-required-missing")`（`agent_settled` 后实文件）——反例 B 改 `worker-mode.ts:539` 后正是该断言红。因此 VC 的 runtime 面证据强、行载体弱；T-17 任务原本要求的就是「runtime_doc_found 行」，若要严格，应从 runtime 的 `emitRagRequiredMissing` 返回值/内部 report 发射。
- **层级裁定：应降 L1，不应维持 L2。** 理由：
  1. 本仓证据口径（`.agenticdoc/mw-rag-integration/evidence-requirement.md` 通则）明确 L2 = **真实时序/长调用/看门狗观察**（例：`MW_RAG_SLOW=1` 的 180s 慢调用、撕裂拒 spawn 的真实 spawn 路径），L1 = **单元或进程内集成测试的 `[VERIFY]` 行（fixture 服务，不依赖真实网络）**。VC-106 用 `fakeWorkerPi()`（假 `pi.on`/`registerTool`，无真实 pi 进程）、`emit("agent_settled")` 合成事件、`PI_WORKER_IDLE_MS=60000` 注入（避开真实看门狗）、skill server（无真实 MCP 网络）——**全部落在 L1 定义内**。
  2. 它确实比纯函数强：走真实 key 布局与 `workerModeActivate` 接线，反例 B 能把它变红（非装饰）。但「可证伪的进程内集成」 = L1，不是 L2。
  3. AC-105 的二选一语义是「要么补运行时用例（升到与声明同层）、要么把层级降为 L1」；现有用例的实际层级是 L1，若仍声明 L2 就是重犯 F-3（声明高于证据）。
  4. 落地建议：本 key 待生成的 `evidence-requirement.md` 将 VC-018/VC-106 标为 **L1**；上位 `mw-rag-integration/evidence-requirement.md:26` 的历史 L2 行追加 `[REVISED @ 2026-09-22 → L1, superseded by mw-rag-integration-fix T-18]`。此项与 T-17 output 的「保持 L2」相左，以本独立裁定为准。

### VC-107（L1 文档/CLI，强但无证据行）
- 断言原文：README 四条 `mw rag` 命令逐条真跑成功；README 不含 `--server`；`rg MW_RAG_ENABLED` 生产代码零命中。
- 发射位置：无 `[VERIFY]` 行（文档型 VC）。
- 实测：见 §0 #9/#10。`rg "--server"` 在 README RAG 段零命中；四条命令 exit=`0/0/0/0`，`probe --server X` exit=2（argparse 拒收幻影参数）；已启用集下 `sync` 真实写出 `<tmp>/.pi/skills/mw-rag.md`（sha256 `5b58678d…`）；`MW_RAG_ENABLED` 在 `packages/`+`docs/` 仅 CHANGELOG 1 处刻意提及。
- 强度：强（外部命令与文件观测），但非证据行形式，需报告替代。

### VC-108（L1+L2 聚合，强但无证据行）
- 断言原文：未启用项目四断言成立；`render_task_md(phase="",role="",…)` 与旧调用逐字节相同；`rag-*` 与 `test_rag_*.py` 全绿；golden sha256 不变。
- 发射位置：无专用 `[VERIFY]`（由 `rag-tools`/`rag-parity` 既有 VC-001/VC-027 与套件结果覆盖）。
- 实测：§0 #1~#5；golden sha256 `00f85e64…`，`test_autopilot_l0.py` git diff 为空。
- 强度：强（聚合）。

### VC-109（口径，强，反例证明）
- 断言原文：本 key 新增/修改的每条证据行至少一个字段来自被测数据（反例试验可使其变化/变红）。
- 发射位置：无专用 `[VERIFY]`；由反例试验承担。
- 实测：§5 反例 A（`rewrite_tool` 变化且判红）、B（VC-106 判红）、C（Python VC-111 判红）。
- 强度：强，但**两条证据行不满足该口径**（VC-102/VC-105 行内字面量），已在 §1/§2 如实降级——这正是本口径要暴露的问题。

### VC-110（L2，强）
- 断言原文：无 role/phase 时不注入 `multi_rounds`、server 仍取 `default_server`、不写新文件。
- 发射位置：`test/suite/rag-role-defaults.test.ts:264`。
- 实测行：`[VERIFY] VC-110: role="" phase="" wire=rag_search server=default_server files_added=0`
- 强度：强。`wire` 为 fixture 观测；`expect(snapshotTree(project)).toEqual(before)` 是整棵目录树的字节比较（真零写入），仅 `server=default_server`/`files_added=0` 为标签。

### VC-111（L1 两侧，强）
- 断言原文：同一 fixture（`test/fixtures/rag/phase-only-target.yml`）下两侧解析必须同为 `server=A, source=docs, rewrite=true`。
- 发射位置：TS `test/suite/rag-parity.test.ts:302`；Py `test_rag_config.py:293`。
- 实测行（两侧逐字相同）：`[VERIFY] VC-111: server=A source=docs rewrite=true`
- 强度：**弱（形式）/ 强（断言几何）**。两侧均**直调纯函数**（TS `resolveDefaults`，Py `render_rag_block`），无 runtime 路径参与该用例；但字段是函数输出插值而非常量期望，且该 VC 本就是解析器 parity 属性。`resolveDefaults` 的 runtime 接线由 VC-101/VC-110（fixture 观测 wire/server）独立覆盖，故「纯函数对齐 + runtime 接线」合并成立；反例 C 只使 Python 侧红（TS 不受影响），证明确实钉住了两侧。

## §3 零回归与改动面

- **TS `rag-*`（13 文件）**：`105 passed | 1 skipped`，与基线逐数一致；唯一 skip 是 `rag-e2e-slow.test.ts`（`MW_RAG_SLOW` 门控，未启用）。
- **TS `agent-team-loop*` + `autopilot-*`（14 文件）**：`488 passed`，零失败（本 key 修改了 `test/extensions/agent-team-loop.test.ts`）。
- **Python 全量**：`805 passed, 9 deselected`（基线 802；+3 为 T-16 新增用例；9 deselected 与基线一致，为既有 e2e 门控）。定向 `test_rag_*.py`：`79 passed`。
- **golden 字节锁**：`test/fixtures/rag-block.golden.md` sha256 = `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`，347 B；`test_rag_config.py::…::test_golden_block_and_idempotent` `1 passed`；TS `[VERIFY] VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true fixture_digest_match=true`。两侧均未变。
- **文本层守护**：`git diff --stat -- test_autopilot_l0.py` 空，`git status --porcelain -- test_autopilot_l0.py` 空。
- **单解析器收敛**：`rg -n "resolveForRole|resolveForPhase" packages/coding-agent/src packages/coding-agent/test` **零命中**（exit 1）→ 未留第二个 P-005 死角；`resolveDefaults` 为 `block.ts` 与 `tools.ts:456` 共用。
- **仓根 `npm run check`**：exit 0，biome `1080 files` `No fixes applied`（即 `--write` 未改任何文件）。
- **bundle 新鲜度与内容**：`dist/extensions/agent-team-loop.js` = 888791 B，mtime `2026-09-22 21:45:17`；；源码 mtime 最大值 `21:36:40`（`rag/config.ts`），`rag/tools.ts` 21:36:06、`rag/adapter.ts` 21:36:15、`rag/block.ts` 21:31:53、`worker/worker-mode.ts` 21:24:34 → **产物晚于全部源**。`Self-check OK: default export loads as a function (activate)`，`rg -c resolveDefaults` = **3**（基线 3）。注：`packages/coding-agent/dist/extensions/agent-team-loop/` 无 `rag/` 且为 gitignored 陈旧产物，pi 实际加载的是本跟踪 bundle。
- **改动面**：任务开始与结束的 `git status --porcelain` 逐行一致（同样的 ` M`/`??` 集合）；除本报告 `.agenticdoc/mw-rag-integration-fix/evidence/verify-run-2026-09-22.md` 外**未新增/修改任何文件**（该路径本就在已未跟踪的 `?? .agenticdoc/mw-rag-integration-fix/` 目录内，不改变 porcelain 行集）。三条反例均已还原（sha256 复原，见 §5）。

## §4 失败归属

**本次全量可运行套件零失败项**：TS `rag-*`、`agent-team-loop*`、`autopilot-*`，Python 全量与定向均全绿；`npm run check` exit 0。因此无「本 key 缺陷」需归属。

环境/口径说明：
- **Windows 基线**（`packages/agent`/`packages/ai` 的已知环境噪声）不在本任务执行的套件内，未触发，无需按基线计数。
- **`packages/ai/src/providers/data/` 本地生成目录**：本任务未触碰，也未运行依赖它的套件。
- **其他会话改动**：工作区存在大量本 key 之外的未提交改动（如 `mw-provider-routing`、`mw-implementation-gate` 等）；本任务只读，未与它们交互。
- **`MW_RAG_ENABLED` 口径（重要）**：`rg -n 'MW_RAG_ENABLED' packages docs`（不带排除）会命中 **1 处**：`packages/multi-workers/CHANGELOG.md:41`。这是 PM 刻意保留的字面提及（移除项必须能被用户按变量名 grep 到），**不是残留读写方**。正确口径（代码 + env 文档）：在 `packages/` 与 `docs/` 中排除 `CHANGELOG.md` 后 **零命中**；`launcher.py` 无注入、`test_rag_launcher.py` 无断言、`packages/coding-agent/docs/environment-variables.md` 未登记。T-17 output 自称「CHANGELOG 用描述而非字面量以避免 rg 命中」，该说法已被 PM 后续编辑取代，以当前文件为准。

## §5 反例试验记录

统一步骤：备份到 `%TEMP%` → `edit` 注入 → 跑目标用例 → 从备份还原 → sha256 对比。

### 反例 A：反转 fixture 的研究角色 rewrite 配置
- 改动：`packages/coding-agent/test/suite/rag-role-defaults.test.ts` VC-101 用例中 `serversYaml([{ name: "A", url: fixture.url, rewrite: true }])` → `rewrite: false`（把 design role 所在 server 的改写能力反转）。
- 看到：`node … --run test/suite/rag-role-defaults.test.ts -t "routes design"` →
  ```
  FAIL test/suite/rag-role-defaults.test.ts > VC-101 role rewrite default at runtime > routes design to rag_search_multi_rounds and coding to rag_search
  AssertionError: expected [ 'rag_search' ] to deeply equal [ 'rag_search_multi_rounds' ]
   Test Files  1 failed (1)
        Tests  1 failed | 2 skipped (3)
  ```
  即 fixture 观测到的 wire 名从 `rag_search_multi_rounds` 变为 `rag_search`。**关于 VC-008 行**：`[VERIFY] VC-008` 的 `rewrite_tool` 字段正是 `designCall.wire[0]`（`rag-role-defaults.test.ts:195`），断言 diff 已证明它变为 `rag_search`；因为 `verify(...)` 调用排在首个 fail 断言之后，红运行时该行**不发射**（不是另一个断言覆盖了它）。结论：VC-008 字段确实随被测数据变化，非自证常量。
- 还原：从备份回拷；sha256 `9bf5a09e85aff395df6b02b7fd9563ce1f0fe038641e3e48bae7d02587b60f8d` **前后一致**（restored=True）。
- `git status --porcelain -- test/suite/rag-role-defaults.test.ts` = `?? packages/coding-agent/test/suite/rag-role-defaults.test.ts`（该文件本为未跟踪，与基线相同，无新痕迹）。

### 反例 B：断开 key 目录 → research-doc 判定路径
- 改动：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:539`
  `validateResearchDoc(check.keyDir)` → `validateResearchDoc(path.join(check.keyDir, "__t18_reverse_b__"))`（validator 恒看不到真实 `rag/<server>-<slug>.md`，等价于该路径恒判空）。
- 看到：`node … --run test/suite/rag-required.test.ts -t "VC-106"` →
  ```
  [VERIFY] VC-106: missing_doc_emits_marker=true
  FAIL test/suite/rag-required.test.ts > VC-106 research-doc runtime evidence > finds the compliant <server>-<slug>.md at the real key path and judges ok
  AssertionError: expected '[START] pid=84836\n[START] …' not to contain 'rag-required-missing'
   Test Files  1 failed (1)
        Tests  1 failed | 1 passed (12 skipped)
  ```
  第一个用例（**有文档 → 无 marker**）变红，第二个用例（**无文档 → 有 marker**，打出 `missing_doc_emits_marker=true`）**仍绿**——与任务预判完全一致：该用例不是「永远不打 marker」的装饰，而是真的 consult 了那份文件。
- 还原：sha256 `203aca65481aeb03e60162b84c7b489ba68b2ae803727e30e95750c140ad8172` **前后一致**。
- `git status --porcelain -- …/worker-mode.ts` = ` M packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（与基线一致；` M` 来自 T-15/T-17 的既有未提交改动，非本次反例残留）。

### 反例 C：Python `RAG_RESEARCH_PHASES` 改回空集
- 改动：`packages/multi-workers/mw_common.py:342`
  `RAG_RESEARCH_PHASES = frozenset(("spec", "design"))` → `frozenset()`。
- 看到：`python -m pytest test_rag_config.py -q -k vc111 -s` →
  ```
  self.assertEqual(rewrite_line, "[mw] Rewrite: true")
  AssertionError: '[mw] Rewrite: false' != '[mw] Rewrite: true'
  FAILED test_rag_config.py::RagConfigTest::test_vc111_phase_only_default_parity
  1 failed, 13 deselected in 0.16s
  ```
  同时 TS 侧不受影响：`node … --run test/suite/rag-parity.test.ts -t "phase-only"` → `[VERIFY] VC-111: server=A source=docs rewrite=true`，`1 passed | 7 skipped`。证明 VC-111 真的分别钉住两侧语言，不是同源自证。
- 还原：sha256 `f2a5369e912ee75ae29f2bea17eadb27d41fa8d08637c9ebd2e71197ad29d4ab` **前后一致**。
- `git status --porcelain -- mw_common.py` = ` M packages/multi-workers/mw_common.py`（与基线一致；` M` 来自 T-16/T-19 既有改动）。

### 反例总表

| 反例 | 改动点 | 红/绿 | 还原后 sha256 复原 | porcelain 与基线一致 |
|---|---|---|---|---|
| A | `rag-role-defaults.test.ts` `rewrite:true→false` | VC-101/VC-008 红（wire=`rag_search`） | 是（`9bf5a09e…`） | 是（仍 `??`） |
| B | `worker-mode.ts:539` keyDir→不存在子目录 | VC-106 用例 1 红、用例 2 绿 | 是（`203aca65…`） | 是（` M`） |
| C | `mw_common.py:342` 空集 | Py VC-111 红、TS VC-111 绿 | 是（`f2a5369e…`） | 是（` M`） |

## §6 未覆盖与限制

**未做（如实声明）：**
- 真实 rag-mcp 线上联调：未连任何真实 MCP server；VC-101/102/104/110/111 均基于 `rag-fixture` 假传输层或本地不可达端口。
- K3 硬门禁：不在本 key 范围。
- 多份调研文档遍历（R-4）：未测（`validateResearchDoc` 只验证单份 `<server>-<slug>.md`）。
- `rag_chat` 重复计费语义：未测（预算/熔断的 chat 面不在本任务）。
- `rag-e2e-slow.test.ts`（`MW_RAG_SLOW` 门控）未跑 → 真实慢调用/看门狗观察缺失；这也是 VC-018/VC-106 只能到 **L1** 的直接原因。
- 未逐条重念 VC-108 的「未启用项目四断言」；以 `rag-tools.test.ts` VC-001 套件结果（`[VERIFY] VC-001: rag_tools=0 task_md_block=0 probe_requests=0 skill_file_unchanged=true budget_file_absent=true`）与全绿结果覆盖，未做新的独立用例。
- VC-107 的四条 README 命令跑在临时最小 fixture（一个 skill server）上，未对真实业务项目跑；`sync` 的写路径（`<tmp>/.pi/skills/mw-rag.md`）已验证，但 `list/probe/audit` 的 `--json`/`--key`/`--out` 等组合未逐个展开（`--server` 幻影参数已验 exit=2）。

**现有证据的局限：**
- `[VERIFY] VC-102` 与 `[VERIFY] VC-105`（TS/Py）行内字段为字面量，不满足 AC-108/VC-109 的「至少一个字段来自被测数据」口径；断言本身仍是真观测（fixture url 分离 / `trace.log` 实文件 / audit 报告实值）。另 `[VERIFY] VC-111`（两侧）为直调纯函数、`[VERIFY] VC-106` 首行字段为直调 `validateResearchDoc`（非 runtime 捕获）——二者的 VC 结论分别由 VC-101/110 的 runtime 接线与 `trace.log` 无 marker 断言支撑，但**证据行本身不是 data-carrying 形式**。**未修改实现或测试**（T-18 只读），建议后续小任务把命中数/runtime 报告值插值进这些行。
- 反例 A 因 `verify()` 排在首个 fail 断言之后，未能在红运行时直接打印变化后的 VC-008 行；用同一表达式的断言 diff（`['rag_search']` vs `['rag_search_multi_rounds']`）代替，证据强度不强于直接打印。
- VC-104 的「不可达」为本机 loopback 拒绝连接，非真实远端超时；属真连接失败，但不等同 L2 的长时间超时观察。
- **层级遗留（需下游落实）**：本报告裁定 VC-018/VC-106 = **L1**。当前 `.agenticdoc/mw-rag-integration/evidence-requirement.md:26` 仍写 L2（历史文件未改，T-18 无写面）；本 key 待生成的 `evidence-requirement.md` 需写 L1，并建议给上位行追加 `[REVISED @ 2026-09-22 → L1, superseded by mw-rag-integration-fix T-18]`。在质检阶段不落地此声明，则 AC-105 仍不闭环。
- `packages/coding-agent/dist/extensions/agent-team-loop/`（gitignored 陈旧 tsc 产物）无 `rag/`、无 `resolveDefaults`，未重建；已确认 pi 实际加载的是 `packages/multi-workers/dist/extensions/agent-team-loop.js`。
- 本次未运行 `packages/agent`/`packages/ai` 套件，其 Windows 已知环境基线（13+76）未经本轮验证；它们不在本 key 的改动面内。

**报告自检：** 本文件是 T-18 唯一写入文件；三条反例均已还原（sha256 复原）；未 commit。
