# Quality Gate Report: mw-rag-integration

**时间**: 2026-09-22T19:10:00+08:00
**触发**: Stage 6（T-11 验证）完成后、`advance_phase(done)` 前的全量质检
**范围**: 全量（K1+K2；K3 硬门禁经用户显式排除，见 `achieved.md`）

> ⚠️ **本报告已修订（2026-09-22 晚）**：独立复核 `mw-rag-qg-review-c`（coding 型审查 worker，含反例试验）判定「需修订」——原判把 AC-006 记为 ✅ 属**高估**（运行时语义未接线），另有 AC-007/AC-014/AC-015、VC-008/VC-009/VC-018/VC-023 记账过强。结论已由 ✅ 改为 **❌ 需修订**；逐项修正见文末「独立复核修订」一节，被推翻的判定行保留原文并改标状态。复核全文：`evidence/quality-gate-review-2026-09-22.md`。

## 前置门禁

| 检查项 | 结果 |
|---|---|
| spec.md 存在 AC 编号 | ✅ 18 条（AC-001~AC-018） |
| design.md 存在 VC 编号 | ✅ 28 条（VC-001~VC-028） |
| AC→VC 映射覆盖 100% | ✅ 18/18 AC 均有 `Source:` 绑定或显式归属（VC-022→AC-003、VC-023→AC-017、VC-028→AC-018） |
| evidence-requirement.md 存在 | ✅ 本次同步生成（`ac_fingerprint=ce271f032d25`） |
| ac_fingerprint 一致 | ✅ 当前 spec 重算 `ce271f032d25` = 记录值（spec 自 2026-09-22 冻结后未再改） |
| evidence/baseline/ 非空 | ⚠️ 本 key 不使用 baseline 目录：PASS 基线是 `evidence/verify-run-2026-09-22.md` 的 28 条 `[VERIFY]` 行（一次性全量采集，非增量基线对比） |
| 每个 task 有非空 ac_refs/vc_refs | ✅ T-01~T-14 全部非空（plan.md 任务表逐行核对） |

## 问题清单与核查结果（来源 A：spec AC）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-AC-001 | 在 target.yml 无 `rag:` 段或 `rag.enabled: []` 的项目下，pi 会话启动后注册表中 `rag_*` 工具数量为 0，且 | ✅ 充分 | VC-001 |  |
| Q-AC-002 | 机器级与项目级同时定义同名 server S（项目级覆盖 `mcp.url`）时，`mw rag list --project <dir> --json`  | ✅ 充分 | VC-002, VC-024, VC-027 |  |
| Q-AC-003 | 在 target.yml `rag.enabled` 引用机器级/项目级都未定义的 server 名时，`dispatch_worker` 拒绝派发：wor | ✅ 充分 | VC-003, VC-022 |  |
| Q-AC-004 | 启用服务 A/B 后，会话注册的工具集恰为 `rag_search` / `rag_symbol` / `rag_graph` / `rag_impact` | ✅ 充分 | VC-004, VC-005 |  |
| Q-AC-005 | 对返回 `engine::Runtime/Renderer/X.cpp` 的 fixture 结果，`rag_search` 返回项含 `local_pat | ✅ 充分 | VC-006, VC-007, VC-026 |  |
| Q-AC-006 | 角色为调研类（spec/design 阶段）调用 `rag_search` 未显式传 `multi_rounds`/`auto_rewrite` 时，适配器 | ❌ 不成立 | VC-008 | **F-1**：`rewriteDefaults`（`rag/adapter.ts:247`）与 `resolveForRole`/`resolveForPhase`（`rag/config.ts:583/595`）无任何生产调用方，`callRag` 只透传 agent 显式参数 → 适配器不会按角色/阶段自动解析开关 |
| Q-AC-007 | 服务未启动时：activate 仍注册工具且描述含 `[unreachable at session start]`；首次调用在 5s 内返回类型化错误并追 | ⚠️ 部分 | VC-009, VC-010 | **F-2**：`[unreachable at session start]` marker 与 `trace=rag-unavailable` 两子句无测试 |
| Q-AC-008 | 每次成功的 `rag_*` 调用在 worker `trace.log` 追加一行 `rag_call`，含 server / tool / 实现路径（`m | ✅ 充分 | VC-011, VC-012 |  |
| Q-AC-009 | token env 值为 `SECRET123`（配置只持有 `token_env` 名，不含值）时，对 task.md / trace.log / out | ✅ 充分 | VC-013 |  |
| Q-AC-010 | target.yml 声明 `roles.review.require: true`，review worker 全程未调用任何 `rag_*` 时：wor | ✅ 充分 | VC-014 | 告警语义（K3 硬门禁排除）；成功收尾路径已验证，失败/超时退出不发射（设计如此，见 R-3） |
| Q-AC-011 | `rag-research` 类型任务下发后，worker 的活动工具集为 `read/find/grep/ls` + RAG 全集（含 `rag_chat | ✅ 充分 | VC-015 |  |
| Q-AC-012 | task.md 声明 `rag_chat_budget: 2` 时，第 3 次 `rag_chat` 调用被工具拒绝（错误文本含预算与已用次数），且不产生服 | ✅ 充分 | VC-016 |  |
| Q-AC-013 | 在把 idle 阈值调低到 60s 的测试配置下，单次 180s 的 fixture 慢 `rag_chat` 调用期间 worker 未被 idle 看门 | ✅ 充分 | VC-017, VC-025 |  |
| Q-AC-014 | `rag-research` 任务结束后必须产出 `.agenticdoc/<key>/rag/<server>-<slug>.md`，且含六个固定小节（查 | ⚠️ 部分 | VC-018 | **F-3**：`evidence-requirement.md` 声明 VC-018 需 L2，实际只有纯函数 validator 证据，无 rag-research 真实产出文档的运行时用例 |
| Q-AC-015 | `python mw.py rag audit --project <dir> --json` 对产出物引用做解析与本地存在性核对，输出含 `missing | ⚠️ 部分 | VC-019, VC-020 | **F-4**：未注册 `type:` 时 role 回落 TS `coding`（`dispatch-models.ts:78`）vs Python `task_type`（`mw.py:1866`），required 判定分歧 |
| Q-AC-016 | 服务端 LLM 不可用导致 rewrite 降级时（fixture 返回降级标记），`rag_search` 返回结果带降级标记字段，并追加 `rag-re | ✅ 充分 | VC-021 |  |
| Q-AC-017 | (K1) 在 `rag.enabled` 非空的项目执行 `mw rag sync --project <dir>` 后，`<control>/.pi/sk | ✅ 充分 | VC-023 |  |
| Q-AC-018 | 六个逻辑工具名必须映射到 `overcode-v1` 参考服务（OverCode rag-mcp）的真实工具名：`rag_graph` → `graph_q | ✅ 充分 | VC-028 | 映射逻辑经 fixture 全验；**未对线上 rag-mcp 实测**（发布前 smoke，见风险 R-1） |

## 问题清单与核查结果（来源 B：design VC）

| 问题 ID | 描述 | 状态 | 实测（verify-run §2） | 备注 |
|---|---|---|---|---|
| Q-VC-001 | 在 target.yml 无 rag 段（或 enabled=[]）的项目下，会话注册的 ^rag_ 工具数必须等于 0 | ✅ 充分 | `VC-001: rag_tools=0 task_md_block=0 probe_requests=0 skill_file_unchanged=true b` |  |
| Q-VC-002 | 机器级与项目级同时定义同名 server S 时，mw rag list --json 中 S.url 必须等于项目级值 | ✅ 充分 | `VC-002: server=S url_match=true origin=project` |  |
| Q-VC-003 | 在 target.yml rag.enabled 引用未定义 server 时，dispatch_worker 必须返回 | ✅ 充分 | `VC-003: rejected=true error_kind=unknown-rag-server queued=0` |  |
| Q-VC-004 | 在启用服务 A/B 的项目下，会话注册的 rag 工具名集合必须等于 {rag_search, rag_symbol,  | ✅ 充分 | `VC-004: tools=6 chat_visible=false server_enums=6/6` |  |
| Q-VC-005 | 在 server 声明 capabilities.graph=false 时，rag_graph 必须返回 kind 等 | ✅ 充分 | `VC-005: error_kind=capability message_match=true api_calls=0` |  |
| Q-VC-006 | 在 fixture 返回 file_path=engine::Runtime/Renderer/X.cpp、line_s | ✅ 充分 | `VC-006: citation_roundtrip=true line_hint=123 exists=true` |  |
| Q-VC-007 | 映射未配置时必须 local_path=null、exists=false、meta.hint 含 "path_root | ✅ 充分 | `VC-007: unconfigured_hint=true missing_file_distinct=true` |  |
| Q-VC-008 | 在角色为 spec/design（调研类）且未显式传参时，fixture 记录的实际请求参数 multi_rounds  | **❌ 伪覆盖** | `VC-008: research_rewrite=true coding_rewrite=false` | **F-1**：只直调无生产调用方的 `rewriteDefaults`，未走 fixture、未观测实际发出的工具名；design §7 的 VC-008 期望是「fixture 记录的实际请求参数」 |
| Q-VC-009 | 在服务未启动时，工具描述必须含 "[unreachable at session start]"，首次调用必须返回 ki | ⚠️ 部分 | `VC-009: session_handshake=true session_id_present=true requests=2; VC-009: error` |  |
| Q-VC-010 | 在同一 server 连续 3 次 connect/timeout/protocol 类失败后，第 4 次调用必须返回  | ✅ 充分 | `VC-010: short_circuited=true api_calls=0 capability_not_counted=true` |  |
| Q-VC-011 | 对六类工具各成功调用一次后，trace.log 增量中必须每类各出现一行匹配 ^rag_call server=\S+  | ✅ 充分 | `VC-011: rag_call_types=6 impact_results_semantics=affected-files` |  |
| Q-VC-012 | (a) transport=skill 的服务调用成功时，trace 增量必须是 rag_call 且 via 等于 " | ✅ 充分 | `VC-012: skill_primary=true fallback_on_connect=true write_tool_no_fallback=true;` |  |
| Q-VC-013 | 在 OVERCODE_MCP_TOKEN=SECRET123 且配置仅含 tokenEnv=OVERCODE_MCP_T | ✅ 充分 | `VC-013: secret_hits=0 error_redacted=true argv_clean_scope=T-07/T-08; VC-013: se` | `argv_clean=true`（T-07/T-08 范围）+ 错误文本脱敏独立断言 |
| Q-VC-014 | 在 roles.review.require=true 且 review worker 全程未调用 rag_* 时，队列 | ✅ 充分 | `VC-014: required_unused_emitted=true output_marked=true idempotent=true; VC-014:` |  |
| Q-VC-015 | Python REGISTRY 必须包含 rag-research 且 conductor_dispatchable 等 | ✅ 充分 | `VC-015: parity_unchanged=pass tools=11 conductor_dispatchable=false; VC-015: rag` |  |
| Q-VC-016 | 在 rag_chat_budget=2 时第 3 次调用必须被拒（错误含预算与 used=2）且 fixture cha | ✅ 充分 | `VC-016: rejected=true chat_calls=2 concurrent_single_grant=true` |  |
| Q-VC-017 | (L1) 以注入时钟断言 onUpdate 心跳周期必须 <= 30s（180s 调用期间 >= 4 次）；(L2) 在 | ✅ 充分 | `VC-017: heartbeat_interval_le_30s=true pings=5 l2_worker_alive_scope=T-11; VC-01` | L1（心跳节拍）+ L2（`MW_RAG_SLOW=1` 实跑 180.06s，`ms=180004`）齐备 |
| Q-VC-018 | 在 rag-research 任务终态后，key 目录下必须存在 rag/<server>-<slug>.md，六个固定 | ⚠️ 部分 | `VC-018: doc_exists=true sections=6 citations_parseable=true; VC-018: missing_sec` |  |
| Q-VC-019 | mw rag audit --json 对引用指向不存在文件的产出物必须退出码非 0 且 missing >= 1；对引 | ✅ 充分 | `VC-019: negative_exit=1 scan_boundary=rag-dir-only attribution=present writes=0` |  |
| Q-VC-020 | 必需判定必须等于 role.require OR phase.require：仅 role.require=true 未 | ✅ 充分 | `VC-020: worker_reads_phase=true missing=unknown; VC-020: phase_written=true ts_e` |  |
| Q-VC-021 | 服务端 rewrite 降级时结果必须含 meta.rewrite_degraded=true 且 trace 增量含  | ✅ 充分 | `VC-021: degraded_flag=true trace_delta=rag-rewrite-degraded clean_delta=0` |  |
| Q-VC-022 | 在 task.md 的 mw-rag 块 fingerprint 与 spawn 时按 D-009 范围重算的指纹不一致 | ✅ 充分 | `VC-022: torn_refused=true unrelated_change_ok=true health_excluded=true; VC-022:` | L2 真实 spawn 路径：撕裂拒 spawn / 无关变更放行 / 健康状态不进指纹 |
| Q-VC-023 | 在 rag.enabled 非空的项目执行 mw rag sync 后 .pi/skills/mw-rag.md 必须存 | ⚠️ 等价覆盖 | `VC-023: sync_installed=true sha_match=true activate_no_write=covered_by(T-04 VC-` | 第三子句（activate 不写 skill）由 VC-001 的 `skill_file_unchanged=true` 覆盖 → 复核（C-③）：**作用域不同**（VC-001 走注册/dispatch 路径且只断言「文件仍存在」，非 activate 时序、非字节不变），从 ✅ 降为 ⚠️ |
| Q-VC-024 | 机器层 server A 含 mcp.url/tokenEnv/timeoutMs/capabilities/sourc | ✅ 充分 | `VC-024: field_merge=true array_replace=true null_delete=true origin_per_field=tr` |  |
| Q-VC-025 | 在累计 RAG 耗时超过 task.md rag_time_budget_s（缺省 900s）后，新的 RAG 调用必须 | ✅ 充分 | `VC-025: cumulative_rejected=true wall_guard_chat_rejected=true cheap_call_allowe` |  |
| Q-VC-026 | 引用语法契约 fixture 必须覆盖 `::` 形态、无 role 前缀形态、含空格、含反斜杠、Unicode 五类输 | ✅ 充分 | `VC-026: grammar_cases=5 roundtrip=5/5` |  |
| Q-VC-027 | 跨语言 parity —— 对同一组共享 fixture（机器层 + 项目层 + target.yml + path_r | ✅ 充分 | `VC-027: golden_byte_match=true fingerprint_match=true origin_table_match=true fi` |  |
| Q-VC-028 | 逻辑工具名到服务端工具名的映射由 `overcode-v1` 适配器的数据表声明：`rag_graph` 必须以 `gr | ✅ 充分 | `VC-028: mapped_names=6/6 sources_merged=true multi_rounds_tool=rag_search_multi_` | fixture 依据厂商 `references/tools-reference.md`；线上实测见 R-1 |

## 问题清单与核查结果（来源 C：Coverage Matrix 行）

| 问题 ID | 路径 | 状态 | 证据引用 |
|---|---|---|---|
| Q-COV-F1 | 启用门控与工具注册 / 启用 → 普通会话六个工具 / enabled 为空 / 缺段 / skill-only 服务 / 未知 server 名 / L1 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F2 | 两层配置逐字段合并与校验 / 项目级覆盖单字段 / 只机器级 / 只项目级 / 数组显式清空 / null 删除 / 坏 YAML / 未知 server / skill 无 cli_entry / L0+L1 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F3 | 工具调用主路径 / 检索 → 归一化结果 / top_k / depth 边界 / 能力不支持 / 熔断 / 预算拒绝 / L1 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F4 | 引用归一化与语法 / path_roots 命中 → exists=true / 含 `::` / 空格 / 反斜杠 / Unicode / 越界 `..` / 未配映射、文件缺失、未知 role / L1 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F5 | 降级与熔断 / mcp 正常 / skill-only 走 cli / connect 失败 → 只读工具兜底 / 写操作与超时不兜底；3 连败熔断 / L1 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F6 | 长调用、预算与墙钟 / 180s chat 存活 + 心跳 / 次数预算用尽 / 累计时间超限 / 墙钟 70% / 并发争抢最后一个额度 / L1+L2 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F7 | 调研文档与 audit / 六小节齐全 + 引用全可达 / 仅 phase.require / 引用指向不存在文件 / 非终态文档 / L1+L2 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F8 | task.md 注入与撕裂 / 双侧块一致（golden） / 未启用 → 无块 / 指纹不一致 → 拒 spawn / L0+L2 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |
| Q-COV-F9 | skill 同步（K1） / 启用项目 sync → 字节一致 / 未启用项目 sync → 移除 / 会话 activate 不动该文件 / L1 | ✅ 覆盖 | verify-run-2026-09-22.md §1/§2 |

## 问题清单与核查结果（来源 D：交叉问题，PM 主动推导）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-X-01 | 未被 VC 覆盖的交互：`phase.require=true` 但 `role.require=false` 且该角色**未**被任何 `roles` 键声明时，`required` 是否仍为真？ | ✅ 充分 | `test_rag_audit.py`/`test_rag_phase.py` 的 `phase_only=missing`、`role_only=missing` 两断言 + `test/suite/rag-required.test.ts` | 并集语义在两侧各有一条反向用例 |
| Q-X-02 | 未启用项目在**派发路径**上是否真的不发探活请求？（VC-001 断言的是会话注册与 task.md 块） | ✅ 充分 | `VC-001: probe_requests=0`（结构门禁：`registerRagTools` 在 `enabled` 为空时不注册、`applyRagTools` 不探活） | 与 D-014 一致 |
| Q-X-03 | `mw rag audit` 与 worker 侧判定不一致时如何裁决？ | ⚠️ 欠债 R-2 | worker 用语法级 citation（`validateResearchDoc`），audit 用逐 citation 本地 `exists` | 告警语义，audit 为权威面；未做同一输入的两侧对照测试 |
| Q-X-04 | 凭证是否会经 **task.md 的注入块**泄漏？ | ✅ 充分 | `VC-013: provider_creds=0 rag_token_envs=0` + `secret_hits=0`（扫 task.md/trace/output/evidence/worker.log/.mw） | token 只以 `token_env` 名出现 |
| Q-X-05 | 阶段轴在 `_scratch` 派发下是否会产生脏数据？ | ✅ 充分 | `_scratch`/缺 pm-state → `''`（`unknown_phase_omitted=true scratch_omitted=true`）；PM 独立脚本复核真仓 `EXECUTE` | 不猜阶段 |
| Q-X-06 | `both` 传输的 cli 回落路径是否被真实覆盖？ | ⚠️ 欠债 R-2（同类） | `VC-012: skill_primary=true fallback_on_connect=true write_tool_no_fallback=true`（fixture 的 mcp 失败注入） | 回落**判定**有证据；真实服务断连未实测 |
| Q-X-08 | 阶段轴大小写精确匹配（`target.yml` 的 `phases:` 键 vs `pm-state.md` 的 `- Phase:` 值）不匹配时，`phase.require` 静默失效，且 worker 与 audit 会「一致地错」（都判不需）→ 无告警 | ⚠️ 欠债（复核新增） | `rag/config.ts:607`、`mw_common.py:845` 精确字典查找；原仅记入 R-5、未计入 ⚠️ | 建议：声明了 `phases` 却从未匹配到任何已观测阶段时输出提示 |
| Q-X-07 | 追踪产物 `dist/extensions/agent-team-loop.js` 是否为**最终**源码重建（T-14 在其后改过 `worker-mode.ts`）？ | ✅ 充分 | T-11 在 T-14 之后重建（`build-ext.txt`：864.9kb + `Self-check OK`），随后重跑 TS 套件全绿 | 顺序正确（流水线显式排了 T-14 → T-11） |

## 汇总

- **总问题数**: 18 AC + 28 VC + 9 Coverage + 8 交叉 = 63
- **通过（充分）**: 14 AC + 24 VC + 9 Coverage + 5 交叉 = 52
- **有条件通过（⚠️）**: 9 项（AC-007 / AC-014 / AC-015；VC-009 / VC-018 / VC-023；Q-X-03 / Q-X-06 / Q-X-08）
- **未通过（❌）**: 2 项（Q-AC-006 / Q-VC-008，同一根因 F-1：AC-006 运行时语义未接线）

**质检结论**: ❌ **需修订**（原判 ✅ 通过系 PM 自评高估，经独立复核 `mw-rag-qg-review-c` 推翻：
1 项功能性缺口（F-1）、3 项 AC ⚠️、3 项 VC ⚠️、3 项交叉 ⚠️。机制主体成立，不是「不可信」，
但不得以 ✅ 收尾；处置见「独立复核修订」§3）

## 独立复核修订（2026-09-22，`mw-rag-qg-review-c`）

复核口径：不采信「PM 已复跑 / 文档这么写」，逐条给 `file:line`，并对关键 VC 做**反例试验**
（改被测数据 → 看红 → 还原 + sha256 自检）。复核全文 `evidence/quality-gate-review-2026-09-22.md`（34 KB）。

### 1. 被推翻的判定

| 原判定 | 复核判定 | 依据（PM 已独立复核确认） |
|---|---|---|
| Q-AC-006 / Q-VC-008 ✅ | **❌ / 伪覆盖** | `rg` 全仓：`rewriteDefaults`（`rag/adapter.ts:247`）、`resolveForRole`/`resolveForPhase`（`rag/config.ts:583/595`）**仅测试引用**；`callRag`（`rag/tools.ts:515-526`）只透传显式参数，`ragToolCalls` 仅在 `args.multi_rounds===true` 时改走 multi 工具（`rag/adapter.ts:313`）→ 运行时永远不会自动改写 |
| Q-AC-007 ✅ | ⚠️ | `rg` 全仓：`unreachable at session start` 只命中 `rag/tools.ts:9,223` 与 dist，测试零命中（`rag-unavailable` 本身有 4 处测试命中；复核该项表述略宽，此处按精确结论记账） |
| Q-AC-014 / Q-VC-018 ✅ | ⚠️ | `evidence-requirement.md` 写 VC-018 需 L2，实际 `rag-research-doc.test.ts` 只对测试自写文档跑纯函数 |
| Q-AC-015 ✅ | ⚠️ | `dispatch-models.ts:78` 回落 `coding` vs `mw.py:1866` 回落 `task_type`（`mw_common.py:303` 又回落 `coding`）→ 未注册 type 时两侧分歧 |
| Q-VC-023 ✅（等价覆盖） | ⚠️ | VC-001 的 `skill_file_unchanged=true` 走注册/dispatch 路径且只断言「文件仍存在」，与 activate 时序/字节不变**不同一作用域** |
| 阶段轴（仅记入 R-5） | ⚠️（升格为 Q-X-08） | 精确大小写匹配 → 静默失效，且两侧「一致地错」不告警 |

### 2. 反例试验（复核者执行，PM 复核其留痕结论）

| 试验 | 动作 | 结果 | 还原 |
|---|---|---|---|
| A | 改 `test/fixtures/rag-block.golden.md` 末位 hex | `rag-parity` 3 failed，`[VERIFY] VC-027` 未打印（断言先抛）；`test_rag_config` 1 failed | ✅ sha256 回 `00f85e64…` |
| B | 改 `test/fixtures/rag/machine-servers.yml` 的 `token_env` | `test_rag_config` 3 failed（含 `test_vc013_token_env_names_only`） | ✅ sha256 回 `99c745c0…` |
| C | VC-001 `probe_requests=0` 的计数源活性 | 间接论证（同文件 VC-004 证明计数器会动），未注入外部数据 | 无改动 |

结论：28 条 `[VERIFY]` 行**不存在「跑红跑绿都打印」的装饰行**；强度分布为 20 强 / 5 弱或混合 /
1 伪覆盖（VC-008）/ 1 层声明过强（VC-018）/ 1 等价替代（VC-023）。

### 3. 闭合裁定

- 机制主体（配置合并、零影响、工具面、证据行、熔断、预算、audit、撕裂拒 spawn、跨语言 golden）经独立复跑与反例试验**成立**，不是「不可信」。
- 未闭合项：F-1（AC-006 运行时接线，**功能性缺口**）、F-2（补 2 条断言）、F-3（VC-018 降级或补运行时用例）、
  F-4（跨语言 role 回落对齐 + 对照用例）、F-5/D-1~D-8（文档与实现不一致：README 缺 `--project`、`probe --server` 幻影参数、
  `MW_RAG_ENABLED` 死变量与不实注释、`rag-rewrite-degraded` 语义被 README 混淆、probe help 与退出码矛盾）。
- 处置：待用户决策后开修复 key；候选范围（T-15~T-17）见 `pm-state.md` 的 Next Action。

## 风险与验证欠债（非 VC 缺口）

| ID | 内容 | 影响 | 处置 |
|---|---|---|---|
| R-1 | AC-018/VC-028 的逻辑名→线上工具名映射全部基于厂商 `SKILL.md`/`references/tools-reference.md` 构造的 fixture，**未对真实 overcode 服务发过请求** | 若线上工具名与文档不符，映射会命中 `tool` 类错误（有结构化错误与 trace 行，不会静默） | 发布前 smoke：对真实服务跑 `mw rag probe` + 各工具一次 |
| R-2 | worker 侧「可核对引用」是语法级；audit 的 `exists` 判定是权威面。两者可能同向偏差（引用不存在的文件时 worker 静默、audit 报警） | 告警可能延迟到 audit 才出现 | 已记录；后续可把 `exists` 判定下沉到 worker（需 path_roots 在 worker 侧可用） |
| R-3 | `rag-required-missing` 只在成功收尾（status=done）发射；超时/失败退出不发射 | 失败任务不产生该告警（失败本身已可见） | 设计选择，VC-014 明确要求 status 保持 done |
| R-4 | `validateResearchDoc` 只检查 key 下第一份 `<server>-<slug>.md` | 多份调研文档时可能漏判 | 后续按 key 遍历全部文档 |
| R-5 | 阶段轴为精确大小写匹配（`target.yml` 的 `phases:` 键 vs `pm-state.md` 的 `- Phase:` 值） | 大小写不匹配时 `phase.require` 静默失效 | 文档已写明（README + design §2） |
| R-6 | 两处文本层守护的钝边（`mw-rag/SKILL` 字面量守护、VC-007 的 `- Phase:` 字面量扫描） | 会误伤语义正确的注释/只读前缀 | 未放宽守护；已在 verify-run §5.1 记录 |

## 二次印证结论

- 检查 1（spec 约束是否有 Q 覆盖）：spec 的平台约束（Windows/PowerShell 5.1）、安全约束（token 不落盘）、
  性能约束（180s 慢调用/看门狗）分别由 VC-013、VC-009/VC-017、VC-025 覆盖 ✅。
- 检查 2（Function Flow 节点是否都有 Q）：TS 侧 6 个模块与 Python 侧 5 处接线均有对应 VC（F1~F9）✅。
- 检查 3（Coverage Matrix 异常路径是否有 Q-COV）✅（上表 F1~F9 全覆盖，含异常列）。
- 检查 4（task 的 vc_refs 是否有遗漏绑定）：T-01~T-14 的 `vc_refs` 并集 = VC-001~VC-028，无遗漏、无重复绑定 ✅。

## 验证执行记录（命令 + 输出证据）

见 `evidence/verify-run-2026-09-22.md`：9 条命令、28 条 VC 的实测行、套件计数、
3 个外部失败的逐条归属（2 个 `packages/agent` Windows 基线 + 1 个 `packages/ai` 本地生成目录漂移），
以及「未对真实服务实测」等限制的如实标注。PM 另行独立复核：`render_task_md(phase="")` 与不传逐字节相同、
`_owner_phase(仓, "mw-rag-integration") == 'EXECUTE'`、`npm run check` exit 0（当前树）。

