# Plan: mw-rag-integration

> 目标：在 AgenticTask 工作流上接入**可配置**的 RAG(MCP) 能力——两层服务表 + 按项目启用 + 六工具面 + 可核对引用 + 五层降级 + 机器判据证据链；未启用项目**结构性零影响**。
> spec: `.agenticdoc/mw-rag-integration/spec.md`（AC-001~AC-017，locked 2026-09-22T12:10:00+08:00；AC-017 为第 1 轮评审后追加）
> design: `.agenticdoc/mw-rag-integration/design.md`（D-001~D-014，VC-001~VC-026）
> 分期：K1 = AC-001~AC-010 + AC-017（Stage 1~4，T-01~T-08）；K2 = AC-011~AC-016（Stage 5，T-09~T-10）；K3（RAG 硬门禁/gate）不在本 plan 内。
> 既有可复用先例（优先照抄而非新造）：`shared/target-config.ts`（两层 YAML 解析 + `TargetConfigError` + 顶层白名单校验）、`launcher.py::_check_config_tear`（fail-closed 拒 spawn + trace）、`mw_common.py`（PyYAML + `.mw/` 项目级配置先例）、`_stripped_env`（唯一凭据剥离点）。

## Stage 1 — TS 纯函数层：配置与适配（AC-002 / AC-003 / AC-005 / AC-006）

- 目标：配置合并/校验/默认/必需并集/指纹 与 归一化信封/引用语法/path_roots 契约 全部做成**无 IO 副作用的纯函数**，先用单测钉死语义，再接工具面。
- 改动：`rag/config.ts`（新增，照 `target-config.ts` 的 `fail/requireString` 形状）、`rag/adapter.ts`（新增，纯函数 + `resolve_path.py` 契约对齐）。
- 验证：`test/suite/rag-config.test.ts`、`test/suite/rag-adapter.test.ts` 全绿；`VC-002/024`（合并矩阵）、`VC-006/007/026`（引用语法往返 + 未配置/缺失可区分）、`VC-008`（rewrite 默认）。
- 依赖：无（T-01 / T-02 可并行，文件不重叠）。

## Stage 2 — 传输层与工具面（AC-001 / AC-003 / AC-004 / AC-007）

- 目标：能真连服务（fixture），并把工具按项目配置**门控注册**；未启用时零注册、零注入、零写盘。
- 改动：`test/support/rag-fixture-server.ts`（新增，脚本化 MCP fixture）、`rag/mcp-client.ts`、`rag/cli-bridge.ts`、`rag/tools.ts`、`rag/guidelines.ts`、`worker/worker-mode.ts`（幂等注入）、`pm/task-dispatcher.ts`（`mw-rag: v1` 块）、`pm/ui-bridge.ts`（前置校验）。
- 验证：fixture 契约测试 + `VC-001`（零影响四断言）、`VC-003`（未知 server 拒派发）、`VC-004/005`（恰六个 + 全量 enum + 能力错误）、`VC-009`（未起服务快失败）；既有 autopilot/worker 套件零回归。
- 依赖：T-02（adapter）、T-03（client）先于 T-04。

## Stage 3 — 证据、熔断、预算与心跳（AC-007 / AC-008 / AC-009 / AC-012 / AC-013 / AC-016）

- 目标：把"用了 RAG"变成机器可判据：五类证据行、熔断口径、次数/累计时间预算（含并发预留）、墙钟守卫、全类调用心跳。
- 改动：`rag/evidence.ts`、`rag/budget.ts`、`mcp-client`/`cli-bridge` 的跳线接入。
- 验证：`VC-010`（熔断第 4 次零请求 + capability 不计入）、`VC-011`（六类各一行）、`VC-012`（skill 主路径 / connect 兜底 / 写操作不兜底）、`VC-013`（token 零落盘 + argv + 错误脱敏）、`VC-016`（并发预留）、`VC-017`（L1 心跳周期 + L2 watchdog 集成）、`VC-021`（降级增量断言）、`VC-025`（累计预算 + 墙钟守卫）。
- 依赖：T-03、T-04。

## Stage 4 — Python 侧：配置 / 注入 / 撕裂 / CLI（AC-002 / AC-003 / AC-009 / AC-017）

- 目标：conductor 与 launcher 面与 TS 侧同语义——同构配置解析、token env 注入与剥离、rag 块注入、指纹撕裂拒 spawn、`mw rag` CLI 与 skill 同步。
- 改动：`mw_common.py`（`load_rag_config` / `render_rag_block` / `rag_token_env_names` / 跨平台路径）、`launcher.py`（`inject_rag_env` post-step、`_stripped_env` 扩展、`check_rag_tear`）、`autopilot/dispatch.py`（`render_task_md` 追加同块）、`mw.py`（`rag list|probe|sync` + doctor rag 段）。
- 验证：`test_rag_config.py` / `test_rag_launcher.py` / `test_rag_cli.py` 全绿 + golden 块 parity（TS 与 Py 同输入同输出）+ `VC-022`（撕裂正反例）、`VC-023`（skill 同步三断言）、`VC-013`（Py 侧扫描面）。
- 依赖：T-06 先于 T-07/T-08；与 Stage 1~3 可并行。

## Stage 5 — K2 类型、审计与跨语言锁定（AC-010 / AC-011 / AC-014 / AC-015 / AC-016）

- 目标：调研类任务可用 `rag_chat` 且不越权给 conductor；`mw rag audit` 提供只读引用核对与 required_missing 告警；TS↔Python 配置/渲染/指纹恒等。
- 改动：`worker/worker-mode.ts` + `shared/dispatch-models.ts` + `autopilot/dispatch.py`（`REGISTRY` 增 `rag-research` + `conductor_dispatchable=False`）、`mw_common.py`（`TASK_TYPE_TO_ROLE`）、`mw.py`（`rag audit`）、调研文档流程（`.agenticdoc/<key>/rag/<server>-<slug>.md`）。
- 验证：`VC-015`（parity 测试**零修改**下通过 + 活动工具集 11 + conductor 拒绝）、`VC-018`（调研文档六小节 + 引用可解析）、`VC-014`（required 未用只告警）、`VC-019`（audit 正负例 + 扫描边界 + 归属 + 不写盘）、`VC-020`（role∪phase + "用了"= 可核对引用）、`VC-027`（跨语言 golden/指纹/origin 恒等）。
- 依赖：T-04/T-05（工具与证据行）、T-06/T-07（Python 侧）。

## Stage 6 — 全量验证与结案（AC-001~AC-017）

- 目标：VC-001~VC-026 证据链落地 + 两侧全量测试 + `npm run check` 0/0/0 + 修改面（零回归）审计 + 人工验收说明。
- 改动：`evidence/verify-run-<date>.md`（逐 VC 的 `[VERIFY]` 输出）、`packages/multi-workers/README.md` RAG 章节、`packages/coding-agent/docs/environment-variables.md` 的 RAG env 登记、两包 `CHANGELOG.md` `[Unreleased]`、`achieved.md`、扩展 bundle 重建（`dist/extensions/agent-team-loop.js`，dist 为已追踪产物）；以及全量测试 + `./test.sh` 可比口径 + `npm run check` + `git diff --stat` 修改面审计（既有测试零修改的核对）。
- 依赖：Stage 1~5 全部完成。

## 任务清单

| Task | Stage | 内容 | ac_refs | vc_refs |
|------|-------|------|---------|---------|
| T-01-TS-CONFIG | 1 | `rag/config.ts`：两层逐字段合并 + 校验 + 默认/必需并集 + fingerprint | [AC-002, AC-003] | [VC-002, VC-024] |
| T-02-ADAPTER | 1 | `rag/adapter.ts`：归一化信封 + 引用语法 + path_roots 契约 + rewrite 默认 | [AC-005, AC-006] | [VC-006, VC-007, VC-008, VC-026] |
| T-03-TRANSPORT | 2 | fixture MCP server + `mcp-client.ts` + `cli-bridge.ts` | [AC-007] | [VC-009] |
| T-04-TOOLS | 2 | 七工具定义/门控注册/enum + worker 幂等注入 + task.md 块 + 前置校验 | [AC-001, AC-003, AC-004] | [VC-001, VC-003, VC-004, VC-005] |
| T-05-EVIDENCE | 3 | 证据行 + 熔断 + 次数/累计/墙钟预算（并发预留）+ 全类心跳 | [AC-007, AC-008, AC-009, AC-012, AC-013, AC-016] | [VC-011, VC-012, VC-013, VC-016, VC-017, VC-021, VC-025] |
| T-06-PY-CONFIG | 4 | `mw_common.py`：同构配置解析 + rag 块渲染 + token env 名集 + 跨平台路径 | [AC-002, AC-009] | [VC-024, VC-013] |
| T-07-PY-INJECT | 4 | launcher env 注入/剥离 + 指纹撕裂 + `dispatch.py` rag 块 | [AC-003, AC-009] | [VC-022] |
| T-08-PY-CLI | 4 | `mw rag list\|probe\|sync` + doctor rag 段 + skill 同步（AC-017） | [AC-017] | [VC-023] |
| T-09-RAG-RESEARCH | 5 | rag-research 类型双侧接入（parity 零修改）+ conductor 门 + 调研文档流程 | [AC-011, AC-014] | [VC-015, VC-018] |
| T-10-AUDIT | 5 | `mw rag audit` + require 判定（role∪phase）+ required_missing 告警 | [AC-010, AC-015, AC-016] | [VC-014, VC-019, VC-020, VC-021] |
| T-12-PARITY-LOCK | 5 | TS↔Py 配置/渲染/指纹/origin 恒等（以 Python/golden 为准修 TS 漂移） | [AC-002, AC-005] | [VC-027] |
| T-13-MCP-TOOLMAP | 3 | `overcode-v1` 逻辑工具名→服务端工具名映射表 + `rag_sources` 合并 + 重写开关走 `rag_search_multi_rounds` | [AC-004, AC-006, AC-018] | [VC-028] |
| T-14-PHASE-AXIS | 5 | task.md `phase:` 头双侧写入 + worker 解析 + 末态 `rag-required-missing` 发射与 output.md 标注 | [AC-010, AC-015, AC-016] | [VC-014, VC-020, VC-021] |
| T-11-VERIFY | 6 | 全量测试 + check + 逐 VC 证据链 + 修改面审计 + README/env 文档 + CHANGELOG + 结案材料 | [AC-001~AC-017] | [VC-001~VC-027] |

## 执行顺序与并行度

```
Stage 1  T-01 ─┐
         T-02 ─┴─→ Stage 2  T-03 ─→ T-04 ─→ Stage 3  T-05 ─┐
Stage 4  T-06 ─→ T-07                                    ├─→ Stage 5  T-09 / T-10 / T-12 ─→ Stage 6  T-11
         T-08 ───────────────────────────────────────────┘
```

- 可并行：`T-01 ∥ T-02 ∥ T-06`（文件不重叠：TS 纯函数层 / Python 配置层）。
- 串行为硬依赖：`T-03 → T-04 → T-05`（另：`T-04 → T-13 → T-05`，T-13 与 T-05 都要改 `rag/tools.ts` 的调用链，必须串行）（工具面测试要真连 fixture；证据行要工具面存在）、`T-06 → T-07/T-08`（渲染与注入共用解析结果）、`T-09/T-10/T-12` 需要 T-04/T-05 + T-07 落地（T-12 另需 T-01 + T-06）。
- 已知漂移风险：T-01 先于 T-06 落地，TS 侧字段命名/文件形态/指纹 canonical 规则可能与 Python 不一致 → 由 **T-12** 以 Python/golden 为准修 TS（这是一次有意的"先并行后对齐"，不是放任漂移）。
- 建议派发节奏：Stage 1 两个 worker 并行 → Stage 2 串行两个 → Stage 3 一个 → Stage 4 三个（T-06 先）→ Stage 5 两个 → Stage 6 PM 主窗口直执。

## 风险与缓解（plan 级）

| 风险 | 缓解 |
|------|------|
| 既有 parity 测试被"顺手改" | T-09 验收含"`test_autopilot_l0.py` 零 diff"；T-11 修改面审计核对 |
| 未启用项目被新代码影响 | `VC-001` 四断言（工具数/块数/请求数/文件存在性）作为 Stage 2 出口条件 |
| fixture 与真机语义漂移 | fixture 只实现协议与脚本化返回；adapter 契约测试用固定 JSON 快照 |
| 长调用测试变慢/假通过 | `VC-017` 拆 L1（注入时钟，快）+ L2（短阈值集成），避免 180s 实时 |
| `dist` bundle 被漏重建（src 与分发产物分叉） | T-11 把 bundle 重建列为验收项并纳入修改面审计 |
| 两侧配置解析漂移 | 同输入 golden（rag 块 / list --json / 指纹）双侧对比断言 |
