# PM State: mw-rag-integration-fix

## 1. Snapshot
- Key: mw-rag-integration-fix
- Phase: DONE
- Next Action: 等 `mw-rag-fix-t15-role-defaults`（T-15 role/phase 运行时接线）与 `mw-rag-fix-t16-py-role-unreachable`（T-16 未起服务断言 + Python role 回落）回读；两者文件不重叠可并行。T-15 回读通过后派 T-17（VC-018 层级 + 文档 + 删 `MW_RAG_ENABLED` + dist 重建），最后 T-18 独立验证
- Started: 2026-09-22 21:21
- Updated: 2026-09-22 22:01
- Completed: 2026-09-22 22:01

## 2. Task Status

| 任务 | Stage | 状态 | 交付 / 证据 | 备注 |
|---|---|---|---|---|
| T-15-ROLE-DEFAULTS | 1 | **done（PM 已复核）** | `mw-rag-fix-t15-role-defaults` | F-1：`callRag` 注入 role/phase 默认 + `renderRagBlock` 单一解析源 + fixture 级 `[VERIFY] VC-008` |
| T-16-PY-ROLE-UNREACHABLE | 2 | **done（PM 已复核）** | `mw-rag-fix-t16-py-role-unreachable` | F-2 集成断言（`rag-unreachable.test.ts`：6 工具全注册 + `reachable.get("A")===false` + 全部描述含 marker + 首次调用 `kind=connect` + trace **增量**含 `rag-unavailable`）+ F-4 三处 role 回落统一 `coding`（`mw.py:1869`、`mw_common.py:303/903`） |
| T-19-DEFAULTS-PARITY | 1 | **done（PM 已复核）** | `mw-rag-fix-t19-defaults-parity` | T-15 的补正：`resolveDefaults` 单一解析器 + 删 `resolveForRole/Phase` + Python rewrite 兜底对齐 + VC-111 跨语言对照 fixture |
| T-17-DOCS-BUNDLE | 3 | **done（PM 已复核）** | `mw-rag-fix-t17-docs-bundle` | 依赖 T-15/T-19（dist 重建必须在最终 TS 源码上；已补「bundle 内必须含 `resolveDefaults`」的验证项） |
| 证据行（T-18 降级 + T-20 修正） | 2 | **已修正** | `[VERIFY] VC-102: … role_hits_a=0 role_hits_b=1 explicit_hits_a=1 explicit_hits_b=1 …`；`[VERIFY] VC-105: ts_role=coding ts_phase=unknown … server=A` / `py_role=coding … exit=1` |
| 证据行（T-17） | 1 | **已采集** | `[VERIFY] VC-106: runtime_doc_found=true sections=6 verdict=ok`（配对反例：无文档 → 打 `rag-required-missing role=research phase=EXECUTE server=A`） |
| 证据行（T-19） | 1 | **已采集** | `[VERIFY] VC-111: server=A source=docs rewrite=true`（TS `rag-parity` 与 Python `test_rag_config` 各一行，值取自解析结果） |
| 证据行 | 2 | **已采集** | `[VERIFY] VC-104: unreachable_marker=true rag_unavailable_line=true server=A`；`[VERIFY] VC-105: ts_role=coding ts_required=true type_literal=foobar server=A`；`[VERIFY] VC-105: py_role=coding py_required=true type_literal=foobar server=S`；`[VERIFY] VC-105: py_render_role=coding type_literal=foobar server=B` |
| T-18-VERIFY | 4 | **done（PM 已复核）** | `mw-rag-fix-t18-verify` | 产出 `evidence/verify-run-2026-09-22.md`（110 行）；三条反例全部按预期红并还原 |
| T-20-EVIDENCE-INTERP | 4.5 | **done（PM 直执）** | — | T-18 指出 `VC-102`/`VC-105`（两侧）证据行为字面量 → 改为实测插值（断言未变）；复跑全绿 | 已强化：反例试验从 2 条提到 3 条（新增「断掉 research-doc 判定路径 → VC-106 必须变红」与「`RAG_RESEARCH_PHASES` 清空 → Python VC-111 必须变红」），并要求独立判定 VC-018 层级、bundle 新鲜度检查 | 依赖 T-15/T-16/T-17 |

## 3. Evidence Ledger
*(empty)*

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions

- **D-101~D-108 全部沿用 `design.md`**，无新增设计决策。
- 完成判据口径（承接复核）：判「谁在运行时调用它」（P-005），证据行至少一个字段取自被测数据（AC-108）。

## 6. Turn End Records
*(empty)*

## 7. Process Log

- 2026-09-22 SPEC→EXECUTE：按用户「开」的决策创建修复 key，范围 = 独立复核 5 组缺口（F-1~F-5）。
  写 spec/design/plan/tasks 后 `advance_phase` 连跳 design→plan→tasks→execute（各阶段门禁均 PASS）。
  K3 硬门禁、`rag-research` conductor 派发、真实 rag-mcp 联调仍显式排除（与上位 key 一致）。
- 2026-09-22 VERIFY→DONE：T-18 回读并**独立复核**。它给出的核心价值不是「全绿」，而是三条独立判断：
  ① 三条反例全部按预期证伪（A/B/C，均还原且 sha256 复原）；② **如实降级** `VC-102`/`VC-105`（两侧）证据行为字面量
  → PM 判定这是 AC-108 的真实违规，**直执 T-20** 改为实测插值并复跑（TS 15 passed / Py vc105 passed / 全量 805 / check exit 0）；
  ③ **独立裁定 VC-018/VC-106 层级应为 L1**，与 T-17 自报的「维持 L2」相左 → PM 采纳 T-18（假 pi + 合成 `agent_settled`
  的进程内集成确实不是 L2），本 key `evidence-requirement.md` 写 L1，上位 `mw-rag-integration/evidence-requirement.md:26`
  追加 `REVISED @ 2026-09-22 → L1` 标记，L2 证据进「遗留 R-1」。
- 2026-09-22 PM 亲自复核反例 B（VC-106 是否装饰）：备份 `worker-mode.ts`（sha256 `203aca65…`）→ 把 `:539` 的 key 目录
  改到不存在的子目录 → `rag-required` 的「有文档→无 marker」用例**红**、反例用例仍绿 → 还原，sha256 复原一致。
  结论：VC-106 的 runtime 判定真的 consult 了那份文档，不是「永远不打 marker」的装饰。
- 2026-09-22 结构性修正（PM 直执）：design 的决策表 D-107 行曾被追加注记时吞掉换行、与 D-108 粘连；已修复
  （所有 `| D-###` 行 pipe 数回归 4）。同时把 design §2 的 mermaid 里 `resolveForRole`/`resolveForPhase` 节点改为
  `resolveDefaults` / 「声明值：role > phase > default_server」——T-19 删除这些函数后该图已与实现不符
  （mermaid gate 仍 PASS：语法对、语义错，正是「文档与实现脱节」的同类问题，故一并修掉）。
- 2026-09-22 DONE 前产物：`evidence-requirement.md`（AC-101~AC-108，VC-106 声明 L1）、
  `evidence/quality-gate-report-2026-09-22.md`（23 项：20 充分 / 3 ⚠️ / 0 ❌，判定 **✅ 通过**）、
  `achieved.md`（含 `## 系统行为变化` 7 条与 `## 遗留` R-1~R-4）。PASS 依据：全套件零回归 + golden 字节锁 + 3 条反例。
- 2026-09-22 EXECUTE：T-17 回读并**独立复核**：`rg -n 'MW_RAG_ENABLED' packages/ docs/` = **0 命中**；
  bundle `packages/multi-workers/dist/extensions/agent-team-loop.js` 888791 B / mtime 21:45 / `rg -c resolveDefaults` = **3**；
  `mw.py rag probe` help 已改为「不可达仍退 0，配置错误退 1」，README 补了退出码表（`:280-282`）；
  Python `test_rag_launcher.py + test_rag_cli.py` = **36 passed**（remane 后的函数名已确认无语义残留）。
- 2026-09-22 决策（T-17 偏离 1 的修正，PM 直改）：CHANGELOG 原本用「dead RAG-enabled worker env flag」回避字面量以凑「零命中」验收，
  判定**过头**——移除项必须能被用户按变量名 grep 到。已把 CHANGELOG 该句改回显式 `` `MW_RAG_ENABLED` ``，
  并把口径改为「**代码与 env 文档路径零命中**，CHANGELOG 一处刻意提及」（已写入 T-18 任务书，避免它据此误判失败）。
- 2026-09-22 EXECUTE：T-19 回读并**独立复核**：`rg` 确认 `resolveForRole|resolveForPhase` 在 `src`+`test` **零命中**；
  `resolveDefaults`（`rag/config.ts:597`）被 `block.ts:75` 与 `tools.ts:456` 共用；`rewriteDefaults`（`config.ts:579`）仍是唯一判定函数
  （`:608` 解析默认值、`tools.ts:556` 按**实际选中 server** 的能力判 wire）。
  证据行：TS `12 passed | 1 skipped (13 files)` / `103 passed | 1 skipped`、`[VERIFY] VC-111: server=A source=docs rewrite=true`
  与 `[VERIFY] VC-027: golden_byte_match=true fingerprint_match=true …` 同时打出；Python 六文件 **79 passed**；golden sha256 仍 `00f85e64…`。
- 2026-09-22 决策（T-19 落地后两处边界，已写入 design D-102/D-109）：
  ① `rewriteDefaults` 与 research 常量从 `adapter.ts` 迁入 `config.ts`（互 import 会成循环），唯一判定函数语义不变；
  ② **显式 `server:` 覆盖时的已知边界**：`[mw] Rewrite:` 行按**默认 server 选择**解析，而运行时按被调用 server 的
  `capabilities.rewrite` 重新判定，两者可能不同——这是「默认值声明」语义，Python 侧同理，已在 design 里写明而不是留给后人猜。
- 2026-09-22 EXECUTE：T-15 回读并**独立复核**：PM 亲自复跑 6 个相关套件 = **47 passed**，`[VERIFY] VC-008`
  （`role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1 coding_tool=rag_search`）、
  `VC-101/102/110`、`VC-027 golden_byte_match=true fingerprint_match=true` 均按实测值打出；golden sha256 仍 `00f85e64…`。
  即 AC-101 的「运行时真的发 `rag_search_multi_rounds`」已由 fixture 观测成立（不再是直调死函数）。
- 2026-09-22 决策（T-15 上报的两处真实偏差 → 新增 T-19）：**不能带病进 T-17**。
  ① `rag/tools.ts:458`/`rag/block.ts:80` 写 `roleRes?.server ?? phaseRes?.server ?? defaultServer`，而 `resolveForRole`
  内部已回落 `defaultServer` → 「`default_server` 已设 + 角色 spec 无 `server` + 阶段 spec 有 `server`」时阶段声明被 default 遮盖，
  与 Python `_rag_resolve_defaults`（`mw_common.py:856` 取**声明值**）和上位 design 的权威优先级「角色声明 > 阶段声明 > `defaultServer`」相矛盾；
  ② rewrite 兜底两侧相反（TS 角色**或**阶段；Python 只看角色）→ 仅阶段为 `design` 时注入块与 Python 解析结论相反。
  另把 `resolveForRole`/`resolveForPhase` 收敛掉（T-15 之后它们只剩被错误 `??` 链使用的用途，留着就是 P-005 复发点）：
  新增 `resolveDefaults` 作为每语言唯一的解析器，并加 VC-111 跨语言对照 fixture（`phase-only-target.yml`）。
  design 已同步修订 D-102/D-104 并新增 D-109/VC-111。
- 2026-09-22 EXECUTE：T-16 回读并**独立复核**：`mw.py:1869`、`mw_common.py:303/903` 三处 role 回落已统一为 `coding`（`rg` 全仓无残留 `, task_type)` 形态）；
  PM 自己复跑 `python -m pytest test_rag_audit.py test_rag_config.py test_rag_phase.py test_rag_cli.py test_rag_launcher.py test_rag_research.py -q` = **78 passed**，golden sha256 仍 `00f85e646e30d577…`。
  T-16 的三处偏离均可接受：新建测试文件（避免与 T-15 撞文件）、多补一条 `mw_common.py:901` 的 Python 用例（覆盖第二处回落点）、TS/Python 的 `phase` 证据字段格式差异（`unknown` vs `""`，role/required 结论一致）。
  待 T-15 落定后再复跑 TS 套件（避免与 T-15 的并发编辑互相干扰）。
- 2026-09-22 EXECUTE：T-17 派发（依赖 T-15+T-19 已落定）。任务书已补两处：bundle 内必须 `rg -c 'resolveDefaults'` >= 1
  （防止「`Self-check OK` 但新代码没进产物」），以及 VC-018 层级声明的位置说明（上位 key 的
  `evidence-requirement.md:26`，只追加修订标记、不重写已 DONE key 的历史）。
- 2026-09-22 EXECUTE：因 T-15 的 `pm/pm-orchestrator.ts:635` 未改（省略即 `role:""/phase:""`，零变化）无需 diff，符合任务书；
  T-15 偏离 2（D-104「无 role/phase 不写 `[mw] Rewrite:` 行」未实现）判定为**设计文档该改**而非代码该改：该行是既有字节契约
  （golden 347 B 含它），已把 D-104 修订为「照旧始终渲染，但值必须与运行时同源」。
- 2026-09-22 EXECUTE：并行派发 T-15（TS：`rag/*.ts`、`worker/worker-mode.ts`、`pm/pm-orchestrator.ts`）与
  T-16（Python：`mw.py`、`mw_common.py` + 两侧测试）。两者文件零重叠；T-17 因 dist 重建必须串行在 T-15 之后。
