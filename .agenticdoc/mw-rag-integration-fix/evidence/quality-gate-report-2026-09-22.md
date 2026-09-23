# Quality Gate Report: mw-rag-integration-fix

- key: `mw-rag-integration-fix`
- generated_at: 2026-09-22（PM 直执，supersedes 无）
- 判定：✅ **通过（附 3 项 ⚠️ 与 2 项遗留）**
- 依据：`evidence/verify-run-2026-09-22.md`（T-18 **独立验证**报告，含 3 条反例试验 + 层级裁定）+ PM 独立复核
  （亲自复跑 T-15/T-16/T-19 的关键断言、亲自复现反例 B）+ 上游 `mw-rag-integration` 的独立复核
  （`evidence/quality-gate-review-2026-09-22.md`，F-1~F-5/D-1~D-8）
- 上位裁决定位：本 key 存在的唯一目的就是关掉上面那份复核的 5 组缺口，因此本报告的判定标准 = **「缺口是否真的闭合且可证伪」**，
  而不是「是否有测试变绿」。

## 1. 汇总

| 类别 | 项数 | 充分 | ⚠️ 部分 | ❌ 不成立 |
|---|---|---|---|---|
| AC（AC-101~AC-108） | 8 | 8 | 0 | 0 |
| VC（VC-101~VC-111） | 11 | 8 | 3 | 0 |
| 结构与零回归检查（golden 字节锁 / bundle 新鲜度 / 文本层守护 / 全套件） | 4 | 4 | 0 | 0 |
| **合计** | **23** | **20** | **3** | **0** |

**上游 5 组缺口的闭合判定**：

| 缺口 | 判定 | 决定性证据 |
|---|---|---|
| F-1（AC-006 无运行时调用点：`rewriteDefaults`/role·phase 解析在生产中零调用） | ✅ 闭合 | `resolveDefaults` 成为 `block.ts:75` 与 `callRag`（`tools.ts:456`）的**唯一**解析入口；`[VERIFY] VC-008` 的 `rewrite_tool` 取自 fixture 的 `calls[].name`（反例 A 使其变为 `rag_search` 并判红）；`resolveForRole`/`resolveForPhase` 已删除（`rg` 零命中，第二个 P-005 死角消除） |
| F-2（`[unreachable at session start]` 零测试命中） | ✅ 闭合 | 新 `test/suite/rag-unreachable.test.ts`：绑定后释放端口制造**真实**连接拒绝，断言 6 个基工具全部注册且描述均带标记、首次 `rag_search` 的 `details.kind === "connect"`、trace **增量**含 `rag-unavailable`（`[VERIFY] VC-104`） |
| F-3（VC-018 声明 L2、实际 L1） | ✅ 闭合 | T-18 **独立裁定降为 L1**（假 pi + 合成 `agent_settled` 的进程内集成），本 key `evidence-requirement.md` 写 L1，上位文件追加 `REVISED → L1` 标记，L2 证据进「遗留 R-1」 |
| F-4（未登记 `type:` 的 role 回落两侧不一致） | ✅ 闭合 | 三处对齐 `"coding"`：`mw.py:1869`、`mw_common.py:903`、`dispatch-models`；`VC-105` 两侧判 role=`coding`，证据行字段改为从 trace/audit 实测值插值 |
| F-5/D-1~D-8（文档/契约不一致、死变量、幻影参数） | ✅ 闭合 | README 四条命令以 argparse 为唯一真源（补 `--project`、删 `--server`、退出码表）；probe help 与行为一致；`MW_RAG_ENABLED` 死变量删除（代码与 env 文档零命中）；`rag-rewrite-degraded` 语义澄清 |

## 2. 逐 AC

| AC | 依据（VC/检查） | 判定 | 证据 |
|---|---|---|---|
| AC-101 角色/阶段默认在运行时生效（显式 > 角色 > 阶段 > `default_server`） | VC-101, VC-102, VC-103, VC-110, VC-111 | ✅ 充分 | fixture 观测 wire 名（`rag_search_multi_rounds` vs `rag_search`）；VC-102 证据行已改为实测命中数（`role_hits_a=0 role_hits_b=1 explicit_hits_a=1 explicit_hits_b=1`）；跨语言同 fixture 三方一致 |
| AC-102 fixture 级 VC-008（不得是直调纯函数常量） | VC-008 | ✅ 充分 | 旧打印点在 `rag-adapter.test.ts` 已删，现由 `rag-role-defaults.test.ts:195` 从 fixture 观测值发射；反例 A 证伪（wire 变 `rag_search`） |
| AC-103 不可达 server 的两条子句都有断言 | VC-104 | ✅ 充分 | 见 F-2 行 |
| AC-104 跨语言 role 回落一致 | VC-105（TS+Py） | ✅ 充分 | `type: foobar` 两侧 role=`coding`；TS 行由 trace 正则解析（`ts_phase=unknown`），Py 行由 audit 记录 + exit code 插值 |
| AC-105 VC-018 层级与证据同层 | VC-106 + 层级声明 | ✅ 充分 | 运行时双用例（有文档→无 marker / 无文档→marker）已落地且**可证伪**；层级按独立裁定声明 L1 |
| AC-106 文档与实现一致（含 `MW_RAG_ENABLED`） | VC-107 | ✅ 充分 | 四条命令真跑 exit 0/0/0/0、`probe --server` exit=2、`rg` 口径见 §4 |
| AC-107 零影响/零回归 | VC-108 | ✅ 充分 | TS `rag-*` 105|1 skipped、`agent-team-loop*`+`autopilot-*` 488、Python 805（+3 为本 key 新增）、golden sha256 不变、`test_autopilot_l0.py` 零 diff |
| AC-108 可复核性（证据行 ≥1 字段取自实测数据） | VC-109 + 3 条反例 | ✅ 充分（经 T-20 修正后） | 反例 A/B/C 均按预期证伪；**T-18 如实指出 VC-102 与 VC-105（两侧）行内字段为字面量并降级 → PM 直执 T-20 改为实测插值**（断言未变），这正是该口径要暴露的问题 |

## 3. 逐 VC 证据强度（采用 T-18 的「强/弱/装饰」口径，PM 复算）

| VC | 行原文（关键字段） | 强度 | 说明 |
|---|---|---|---|
| VC-101 | `design_wire=rag_search_multi_rounds coding_wire=rag_search explicit_off_wire=rag_search` | 强 | 三值来自 fixture `calls[].name` |
| VC-102 | `role_hits_a=0 role_hits_b=1 explicit_hits_a=1 explicit_hits_b=1 …` | 强（T-20 后） | 由字面标签改为 `observedWires().length` 插值 |
| VC-103（=VC-008） | `role=design rewrite_tool=rag_search_multi_rounds explicit=false fixture_calls=1 coding_tool=rag_search` | 强 | 反例 A 证伪 |
| VC-104 | `unreachable_marker=true rag_unavailable_line=true server=A` | 强 ⚠️ | 真连接拒绝；但为 loopback 拒绝而非远端长超时（L1 即可，见 §5-1） |
| VC-105（TS） | `ts_role=coding ts_phase=unknown ts_required=true type_literal=foobar server=A` | 强（T-20 后） | role/phase/server 由 trace 正则解析 |
| VC-105（Py） | `py_role=coding py_required=true type_literal=foobar server=S exit=1` | 强（T-20 后） | 由 audit 记录 + exit code 插值 |
| VC-106 | `runtime_doc_found=true sections=6 verdict=ok` / `missing_doc_emits_marker=true` | 强（断言）/⚠️（行载体） | 行内字段来自测试内直调 `validateResearchDoc`；runtime 主张由同用例「trace 无 marker」断言承担，反例 B 证伪（PM 已**亲自复现**） |
| VC-107 | 无专用行（外部命令观测） | 强 | 四条命令真跑 + `rg` 口径 + `--server` exit=2 |
| VC-108 | 无专用行（聚合） | 强 | 全套件 + golden 字节锁 + 文本层守护零 diff |
| VC-109 | 无专用行（口径型） | 强 | 由三条反例承担 |
| VC-110 | `role="" phase="" wire=rag_search server=default_server files_added=0` | 强 | `wire` fixture 观测 + 整棵目录树字节比较 |
| VC-111 | `server=A source=docs rewrite=true`（两侧逐字相同） | ⚠️ | 两侧均为直调纯函数（parity 属性本身成立，字段为函数输出插值）；runtime 接线由 VC-101/VC-110 独立覆盖；反例 C 只令 Python 侧红，证明真钉住两侧 |

## 4. 结构与零回归检查

| 检查 | 结果 |
|---|---|
| golden 字节锁 | `test/fixtures/rag-block.golden.md` sha256 `00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`（347 B）与本 key 开工前逐字节一致；TS `[VERIFY] VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true fixture_digest_match=true` ✅ |
| bundle 新鲜度与内容 | `packages/multi-workers/dist/extensions/agent-team-loop.js` 888791 B，mtime `21:45:17` **晚于**全部 `rag/*.ts` 与 `worker-mode.ts`（最晚 `21:36:40`），`Self-check OK (activate)`，`rg -c resolveDefaults` = 3 ✅ |
| `MW_RAG_ENABLED` 口径 | 代码与 env 文档 **零命中**（`launcher.py` 无注入、`test_rag_launcher.py` 无断言、env 文档未登记）；`packages/multi-workers/CHANGELOG.md:41` **恰 1 处刻意提及**（移除项必须可被用户按变量名 grep 到）✅ |
| 零回归（全套件） | TS `rag-*` `105 passed | 1 skipped`；`agent-team-loop*`+`autopilot-*` `488 passed`；Python 全量 `805 passed, 9 deselected`；定向 `test_rag_*.py` `79 passed`；仓根 `npm run check` **exit 0**（biome 1080 files，`No fixes applied`）✅ |
| 文本层守护 | `git diff --stat -- test_autopilot_l0.py` 与 `git status --porcelain -- test_autopilot_l0.py` 均为空 ✅ |

## 5. ⚠️ 部分（不影响通过，但必须留痕）

1. **VC-104 的「不可达」是本机 loopback 拒绝连接**，不是远端长超时/看门狗观察。AC-103 只要求「不可达可被证明」，
   真连接失败即满足 L1；L2 形态（远端 hang、180s 超时）属未做项（见遗留 R-1 同源）。
2. **VC-106 的证据行载体是直调 `validateResearchDoc`**：runtime 主张靠「trace 无 marker / 有 marker」这对断言承担，
   反例 B 已证明该对断言可证伪（PM 亲自复现：改 `worker-mode.ts:539` 的 key 目录 → 有文档用例变红、无文档用例仍绿）。
   若要严格 data-carrying，应让 runtime 的 `emitRagRequiredMissing` 回吐自己的 report（未做，属可选加强）。
3. **VC-111 两侧均为直调纯函数**：作为「解析器 parity」属性这是合适的（反例 C 证明两侧各自独立钉住），
   但不要把该行读成「运行时用上了解析结果」——后者由 VC-101/VC-110 的 fixture 观测承担。

## 6. 遗留（明确去向）

- **R-1（证据层级）：VC-018/VC-106 的 L2 证据未做** —— L2 需要真实 rag-mcp 服务（真实 worker 进程跑 `rag-research`
  并产出带可验证引用的 `<key>/rag/<server>-<slug>.md`）。本 key 已如实声明 L1 并给上位文件加修订标记。
  **去向**：接受不处理（真实 RAG 联调已在两轮 key 中明确排除）；若将来做真实联调，应把它并入该轮的 L2 清单。
- **R-2（框架级）：review 型 worker 的交付通道缺陷**（只读工具 → 结论只能靠最后一条消息；12 次 review 任务 8 次零交付）。
  本 key 的处置是流程规避（coding 型 reviewer + 单文件写入 + 骨架优先），**不是修复**。
  **去向**：记入 `_pitfalls.md` P-007（已记），需用户决定是否在框架层立新 key（给 review worker 一个受限写通道，
  或 harness 在 stream close 时持久化部分最终消息）。

## 7. 判定

**✅ 通过。** 上游复核的 5 组缺口全部闭合且经独立验证与反例试验证伪检验（3 条反例全部按预期红、100% 还原、sha256 复原）；
无 ❌ 项；3 项 ⚠️ 已逐条写明边界与替代证据；2 项遗留均已指明去向。
唯一由 T-18 独立指出、由 PM 直执修正的实现性偏差（VC-102/VC-105 证据行为字面量）已修复并复跑全绿。
