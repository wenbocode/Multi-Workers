# Quality-Gate Review: `mw-rag-integration`（独立质检复核 / 对抗性证伪）

- 复核对象：`evidence/quality-gate-report-2026-09-22.md`（PM 自写质检，声称 62 项、❌0/⚠️2、✅通过）
- 复核者：`mw-rag-qg-review-c`（coding 型 worker，独立执行）
- 复核时间：2026-09-22
- 复核口径：不采信「PM 已复跑 / 文档这么写」；每条结论给出可复现的 `file:line`；对关键 VC 做反例试验（改被测数据 → 看红 → 还原）
- 本文件只读复核，未修改任何源码/测试/配置；反例试验的临时改动已全部还原（见「反例试验记录」）

## 结论

**需修订**——机制主体（配置合并/零影响/工具面/证据行/熔断/预算/audit/撕裂拒 spawn/跨语言 golden）经独立复跑与反例试验确认成立，**不是**"不可信"；但质检报告把它判为"✅ 通过（❌0）"是**高估**：至少 AC-006 的运行时语义无实现、AC-007 的一个子句无测试，另有 2~3 处证据层级/断言强度被按"✅ 充分"记账。建议：修 AC-006（或在报告中降级为未实现）、补 AC-007 marker 断言、把 VC-008/VC-018/VC-023 的记账从"充分"改为"有条件"，然后重签质检。

## TOP FINDINGS

### F-1（高）AC-006 的角色/阶段 rewrite 默认在运行时未接线，VC-008 只测了一个死函数
- 现象：AC-006（[REVISED @ 2026-09-22]）要求「调研类角色/阶段调用 `rag_search` 未显式传 `multi_rounds`/`auto_rewrite` 时，适配器为该次调用解析出的开关必须为 true，落到线上是 `rag_search_multi_rounds`」。实现里 `rewriteDefaults`（`rag/adapter.ts:247`）与 `resolveForRole`/`resolveForPhase`（`rag/config.ts:583`/`:595`）**只被测试引用**（`grep -rn` 全仓确认），生产调用链 `callRag` 只把 agent 传入的 params 原样收集（`rag/tools.ts:515-517`）交给 `ragToolCalls`；而 `ragToolCalls` 只在 `args.multi_rounds === true || args.auto_rewrite === true` 时才改走 multi 工具（`rag/adapter.ts:313`）。agent 无法从工具 schema 得知自己的角色（`rag/tools.ts:243-244` 只有可选开关，无默认、无 role 参数）。
- 位置：`packages/coding-agent/src/extensions/agent-team-loop/rag/tools.ts:515`、`rag/adapter.ts:247,313`、`rag/config.ts:583,595`。
- 反例/缺失：`test/suite/rag-adapter.test.ts:247-258` 直接调 `rewriteDefaults(...)`，**完全没用 fixture**；`[VERIFY] VC-008` 于 `rag-adapter.test.ts:259` 打印常量。VC-008 的断言原文（design §7）要求「fixture 记录的实际请求参数」，该 fixture 从未参与。TS/全局套件全绿也说明不了这一点。
- 建议动作：在 `callRag` 里用 worker 的 role/phase（经 `runtime.config` + meta）注入默认 `multi_rounds/auto_rewrite`，并用 fixture 断言实际发出的工具名/参数；否则把 AC-006 标为未实现、VC-008 降级，不可再记 ✅。

### F-2（中）VC-009 的两个子句无任何测试：`[unreachable at session start]` 与 `trace=rag-unavailable`
- 现象：AC-007 要求「服务未启动时 activate 仍注册工具且描述含 `[unreachable at session start]`；首次调用返回类型化错误并追加 `rag-unavailable` 证据行」。`[VERIFY] VC-009` 实测行（`rag-transport.test.ts:118-311`）全是裸 `McpSession` 的分类型断言，**不含**这两个字段；全仓 `grep -rn "unreachable at session start"` 只命中 `rag/tools.ts:223` 与 dist/README，**测试零命中**。
- 反例/缺失：design §7 的 VC-009 期望行含 `trace=rag-unavailable`；verify-run 的 VC-009 行没有它，也没有 `[unreachable ...]` 断言（`evidence/verify-run-2026-09-22.md` §2 VC-009）。
- 建议动作：新增一条集成测试：启用一个不可达 fixture 端口 → `registerRagTools` + `runtime.ready` → 断言 `capturedTool.description` 含 marker；执行一次工具 → 断言 `trace.log` 增量含 `rag-unavailable`。

### F-3（中）VC-018 声明为 L2，实际只有 L1 纯函数证据；没有任何 rag-research 任务产出文档的运行时证据
- 现象：`evidence-requirement.md` 写「VC-018 需 L2 证据」（真实时序/长调用），但 `test/suite/rag-research-doc.test.ts` 只对测试自己写死的 `COMPLIANT_DOC` 跑纯函数 `validateResearchDoc`；没有任何用例真正驱动一个 rag-research worker 到终态并断言 key 下出现 `rag/<server>-<slug>.md`。
- 位置：`packages/coding-agent/test/suite/rag-research-doc.test.ts:160-289`；`rag/research-doc.ts:184`。
- 反例/缺失：`MW_RAG_SLOW` 的 L2 只覆盖 VC-017（`rag-e2e-slow.test.ts`），VC-018 无对应慢路径。
- 建议动作：把 VC-018 降为 L1，或补一条 `workerModeActivate` + 假 agent 的 finalize 集成用例（文档由测试预置，断言 validator 在真实 key 布局下取到并判 ✅）。

### F-4（中）"required 判定"的 role 推导在 TS 与 Python 两侧不一致（未注册 type 时）
- 现象：worker 侧 `emitRagRequiredMissing` 用 `roleForTaskType` = `DISPATCH_ROLE_BY_TYPE[type] ?? "coding"`（`shared/dispatch-models.ts:78`，`worker/worker-mode.ts:537`）；Python audit 用 `mw_common.TASK_TYPE_TO_ROLE.get(task_type, task_type)`（`mw.py:1866`，回落到 **type 本身**）。`mw_common` 自己的模型解析又用 `TASK_TYPE_TO_ROLE.get(task_type, "coding")`（`mw_common.py:303`）。
- 位置：`mw.py:1866`、`mw_common.py:303`、`shared/dispatch-models.ts:78`、`worker/worker-mode.ts:537`。
- 反例/缺失：对 `type: foobar` 的 task.md，TS worker 会按 `coding` 判 required（`roles.coding.require: true` 时发 `rag-required-missing`），Python audit 按 `foobar` 判不为 required（`required_missing` 为空）。登记的类型全在映射表内，所以现有用例覆盖不到这个分歧。
- 建议动作：Python audit 改成 `.get(task_type, "coding")`（或其等价），并补一条两侧同一 `type: foobar` 的对照用例。

### F-5（低-中）文档/契约与实现不一致（详见 D 节）
- README `mw rag list|probe|audit|sync` 用法缺必填 `--project`、`probe [--server X]` 是不存在的参数（`packages/multi-workers/README.md:272-275` vs `mw.py:4617-4637`）；`mw rag probe` 的 argparse help 写「never a non-zero exit」但配置错误时返回 1（`mw.py:4623` vs `mw.py:1426-1428`）。
- `MW_RAG_ENABLED` 由 `launcher.py:353` 注入，但全仓无读取方（只有测试断言它存在）；`launcher.py:352` 注释声称「worker-side extension reads it to gate its RAG tool registration」与实现不符。


## A. 28 VC 断言强度

强度口径：**强** = 期望值与实际值异源，且实参可复现；**弱** = 证据行字段是硬编码回显，或期望/实际同源（自证）；**伪覆盖** = 断言对象不是 VC 文字要求的东西。所有 `[VERIFY]` 都在测试断言之后打印，红灯会中断打印，因此没有"无条件装饰"的行；下面是逐条实测后的判定。

| VC | 断言要点 | 发射位置（file:line） | 强度 | 依据 / 反例 |
|---|---|---|---|---|
| VC-001 | 未启用零影响四断言 | `test/suite/rag-tools.test.ts:237`；`test_rag_launcher.py:184` | 弱行/强断言 | 断言真（`capture.tools.size=0`、`fixture.calls=0`、skill/budget 存在性）；但证据行五字段全为字面量，未打印实参。`probe_requests=0` 由 live fixture 计数背书（同文件 VC-004 证明计数会变） |
| VC-002 | 项目层 url 覆盖 + origin=project | `test/suite/rag-config.test.ts:195` | 强 | `urlMatch`/`origin` 为变量；期望来自测试写的项目层，实际来自 `loadRagConfig` |
| VC-003 | 未知 server 拒派发、无目录/无行 | `rag-tools.test.ts:379` | 强 | 断言错误文案 + `store.readAll()` 行数 + 目录不存在 |
| VC-004 | 恰六工具 / chat 隐藏 / enum 6/6 | `rag-tools.test.ts:309` | 强 | enum 从 schema `anyOf[].const` 读；chat 不在注册表；工具名集合排序比较 |
| VC-005 | graph=false → capability + 0 请求 | `rag-tools.test.ts:337` | 强 | `fixture.calls` 差值为 0 + `kind=capability` + message 含 "no knowledge graph" |
| VC-006 | citation 往返 + local_path/exists/line_hint | `rag-adapter.test.ts:136` | 强 | 仓临时真文件；`local_path` 与 `path.resolve` 相等；四元组往返全等 |
| VC-007 | 未配置 vs 文件缺失可区分 | `rag-adapter.test.ts:198` | 强 | 两 reason 不同 + `meta.hint` 含 `path_roots` |
| VC-008 | rewrite 默认按角色 | `rag-adapter.test.ts:259` | **伪覆盖** | 只直调死函数 `rewriteDefaults`（`adapter.ts:247`，无生产调用方），未走 fixture、未走工具链；VC 原文要求 fixture 记录的实际请求参数（见 F-1） |
| VC-009 | 未起服务快失败 + trace | `rag-transport.test.ts:118,131,145,163,184,204,224,245,298,311` | 混合 | `error_kind`/`elapsed_ms`/`pings` 为实算且分类来自真注入故障；但 `trace=rag-unavailable` 与 `[unreachable at session start]` **无任何断言**（F-2），部分布尔尾缀为字面量 |
| VC-010 | 3 连败熔断 + capability 不计 | `rag-evidence.test.ts:427` | 强 | 第 4 次 `kind=circuit` + 请求增量 0 + `breaker.isOpen` 双断言 |
| VC-011 | 六类各一行 + impact results 语义 | `rag-evidence.test.ts:372` | 强 | 从 trace 行解析；`byTool.size` 实算；`mcp_tool` 断言具体 wire 名与 `results` 计数 |
| VC-012 | skill 主路径 / connect 兜底 / 写不兜底 | `rag-evidence.test.ts:456,532` | 强 | 三条独立用例；cli 脚本真执行（兜底）/真不执行（write、timeout） |
| VC-013 | token 零落盘 + argv 干净 + 脱敏 | `rag-evidence.test.ts:612`；`test_rag_config.py:206`；`test_rag_launcher.py` spawn 用例 | 强断言/弱行 | spawn 用例用假 Popen 断言 `cmd` 无 `SECRET123`、`env` 有；行字段为字面量。反例试验 B 已证数据驱动 |
| VC-014 | require 未用 → done + trace + marker | `rag-required.test.ts:228,244,259,274`；`test_rag_audit.py:509` | 强 | 假 pi 驱动 `workerModeActivate` 的 `agent_settled`；trace 行/marker/幂等实测；audit 侧队列保持 done |
| VC-015 | registry parity + 11 工具 + conductor 拒 | `rag-research-doc.test.ts:113,130`；`test_rag_research.py` | 强 | 跨语言逐项等序（解析 TS 源）+ `test_autopilot_l0.py` `git diff` 为空 + dispatch 拒绝无副作用 |
| VC-016 | 第 3 次拒 + 并发只放 1 | `rag-budget.test.ts:213,233` | 强 | fixture chat 计数 + `Promise.all` 真并发 + trace 行 |
| VC-017 | 心跳 ≤30s / 180s 存活 / watchdog | `rag-budget.test.ts:312`(L1) + `rag-e2e-slow.test.ts:227`(L2) | 强主体/弱子句 | L2 真跑 180s + trace `ms` 实算 + `process.exit` 未被调；`watchdog_enabled=true` 是代理证据（`[CHECKPOINT]` 属另一个定时器 + `resolveIdleMs` 值） |
| VC-018 | 六小节 + 引用可解析 | `rag-research-doc.test.ts:222,239,251,279` | 中（层声明过强） | 纯函数对测试自写文档；无任何 rag-research 任务产出文档的运行时证据（F-3） |
| VC-019 | 正负例退出码 + 扫描边界 + 归属 + 只读 | `test_rag_audit.py:263` | 强 | 文件系统快照前后一致；spec/design/非终态排除；`--out` 是唯一写 |
| VC-020 | role∪phase + “用了”=可核对引用 | `test_rag_audit.py:450`；`test_rag_phase.py:60,69,96,113,141`；`rag-required.test.ts:155,199` | 强 | 三个独立用例（role-only/phase-only/只有 call 无 citation）+ 写入侧与 audit 读取侧一致 |
| VC-021 | 降级标记 + 增量证据 | `rag-evidence.test.ts:653`；`test_rag_audit.py:486` | 强 | delta 断言（非全文件）；audit 只标记匹配调用 |
| VC-022 | 撕裂拒 spawn + 无关变更放行 | `test_rag_launcher.py:181` + 文件末尾 spawn 用例 | 强 | `_spawn` 真路径 + 假 Popen 断言未到达 + status=failed；健康/重启不入指纹；未启用 server 改动放行 |
| VC-023 | sync 字节一致 / 未启用移除 / activate 不写 | `test_rag_cli.py:278` | 中 | 前两子句强（sha256 对比）；第三子句是 `covered_by(T-04 VC-001)` 指针 + 源码结构扫描，**不是** activate 时序断言（作用域不完全同一，见 C-3） |
| VC-024 | 逐字段合并/数组替换/null 删除/origin | `rag-config.test.ts:168`；`test_rag_config.py:150` | 强 | 两侧同一 fixture 输入 |
| VC-025 | 累计预算拒 + 墙钟拒 chat 放 search | `rag-budget.test.ts:344,371` | 强 | fixture 计数 + trace `rag-budget-exceeded` 行 |
| VC-026 | 五类语法往返 | `rag-adapter.test.ts:62` | 强 | 五类输入 `roundTrips` 为实算 |
| VC-027 | 跨语言 golden/fingerprint/origin | `rag-parity.test.ts:269` | 强 | 与 **Python 生成**的 golden 比字节/指纹 + fixture 摘要；反例试验 A 翻指纹即红 |
| VC-028 | 逻辑名→线上名映射 + sources 合并 | `rag-toolmap.test.ts:288` | 强（具体名）/弱（6/6 计数） | 具体 wire 名（`graph_query`/`list_sources+list_collections`/`rag_search_multi_rounds`）从 `fixture.calls` 实读；`mapped_names=6/6` 由 `RAG_TOOL_MAP` 本身推出，属自证 |

小结：28 条中 20 条为强，5 条混合/弱，1 条伪覆盖（VC-008），1 条层声明过强（VC-018），1 条等价替代（VC-023）。无一条是“跑红跑绿都打印”的装饰行。


## B. 18 AC 实现落点

“只看代码这条 AC 是否成立”的口径：只读实现即可判定「成立 / 部分 / 不成立」；测试只作附加佐证。

| AC | 实现落点（file:line） | 只看代码 | 说明 / 缺口 |
|---|---|---|---|
| AC-001 | `rag/tools.ts:176-183`（enabled 空 → 返回 null）、`rag/task-dispatcher.ts:277-280`、`autopilot/dispatch.py:186-199` | 成立 | 注册与注入都是结构性分支，不靠运行时判断；budget 文件仅首次调用才建（`rag-budget.json` 不存在） |
| AC-002 | `rag/config.ts:291`（`mergeServerEntry`）、`config.ts:524`（`loadRagConfig`）、`mw_common.py:768`、`mw.py:1230` | 成立 | 项目层逐字段覆盖 + `origin` 逐字段；`mw rag list --json` 输出 `origin` |
| AC-003 | `rag/tools.ts:398-410`；`pm/ui-bridge.ts:1029`、`:1401` | 成立 | `loadRagConfig` 抛 `unknown-server` → 返回 `RAG config rejected dispatch (...)`，文案含 `unknown rag server` 与 server 名；两侧派发点都在创建 task.md 前 |
| AC-004 | `rag/tools.ts:134-…`（`RAG_BASE_TOOL_NAMES`）、`tools.ts:161`（`serverEnum`）、`tools.ts:226`（`registerBaseTools`）、`rag/adapter.ts:389`（`capabilityError`） | 成立 | 六工具固定，`rag_chat` 不在此注册；enum 由启用集生成；无图能力返回 `kind=capability` message 含 `no knowledge graph` |
| AC-005 | `rag/adapter.ts:155`（`loadPathRoots`）、`:194`（`resolveLocalPath`）、`:403`（`normalizeResults`）、`:114/127`（citation） | 成立 | 未配置 → `local_path=null, exists=false, meta.hint` 含 path_roots；引用语法左侧两段 server/source，右侧数字行号，中间全归 file_path |
| **AC-006** | `rag/adapter.ts:247`（`rewriteDefaults`，**无生产调用方**）、`config.ts:583/595`（同样仅测试用）、`tools.ts:515-526`（args 只来自 params）、`adapter.ts:313`（只在显式 true 时改走 multi） | **不成立** | 适配层并未为调研角色自动解析开关（agent 也不掌握角色）；只有 agent 显式传 `multi_rounds:true` 才会发 `rag_search_multi_rounds`。`task.md` 的 `[mw] Rewrite:` 行只是提示 agent，不是适配器行为（见 F-1） |
| AC-007 | `rag/tools.ts:199-223`（探活 + `[unreachable at session start]`）、`:461`（capability）、`:571`（`rag-unavailable`）、`budget.ts:242`（`Breaker`） | 部分 | Cli 仍注册并标注、快速 `connect`、3 连败熔断均在代码里；但 marker 与 `rag-unavailable` 两子句无测试（F-2） |
| AC-008 | `rag/tools.ts:545-570`（`rag_call`/`rag_fallback`/`rag-rewrite-degraded`）、`rag/evidence.ts`、`budget.ts:242`（熔断不计非传输类） | 成立 | 每次成功调用一行 `rag_call`，含 `server/tool/via/ms/results/mcp_tool`；兜底附加 `rag_fallback` |
| AC-009 | `launcher.py:90-105`（`_stripped_env`）、`:331-362`（`inject_rag_env`）；`mcp-client.ts` token/redact；`rag/evidence.ts:redactSecrets` | 成立 | token 值只存在于 env；已声明的 token_env 名从 worker env 剔除后只回填启用集 |
| AC-010 | `config.ts:607`（`requiredFor` 并集）、`worker/worker-mode.ts:536-552`（`emitRagRequiredMissing`）、`:1013-1023`（成功收尾调用）、`mw_common.py:845`（`_rag_required_for`） | 成立 | 并集无例外；未知 phase 回 `unknown`，`phases["unknown"]` 不存在 → 不报 required；只告警不阻断（成功路径 exitCode 仍为 0） |
| AC-011 | `worker/worker-mode.ts:63-78`（`TOOL_ALLOWLISTS[rag-research]`）、`shared/dispatch-models.ts:67,74`、`autopilot/dispatch.py:96-104` + `:391-398`（`conductor_dispatchable` 拒绝） | 成立 | 两侧 11 项逐项等序；conductor 拒派在写 task 前 |
| AC-012 | `rag/budget.ts:126-146`（`reserveChat` 同步递增 + persist）、`rag/tools.ts:478-500`（调用前预留） | 成立 | 并发场景只能一个拿到最后额度；拒绝不发起请求 |
| AC-013 | `rag/budget.ts:162/179`（累计/墙钟）、`budget.ts:267`（`withHeartbeat`）、`tools.ts:526`（包住整个 fan-out） | 成立 | 30s 心跳 + 累计预算 + 墙钟 70% 只拦 chat；完成度以 L2 实测背书 |
| AC-014 | `rag/research-doc.ts:26-28`（`RESEARCH_DOC_SECTIONS`）、`:57-70`（`splitResearchDocSections`）、`SKILL.md:38-56` | 成立（严格一致） | `SKILL.md` 六个标题与校验清单逐字相同（查询/结论/引用/未解决/快照/影响面）；但无运行时产出证据（F-3） |
| AC-015 | `mw.py:1820`（`_rag_audit_project`）、`:1887`（required 判定）、`mw_common.py:845`；`audit` 退出码 `:1957-1977` | 成立（含一处跨语言偏差） | 扫描边界只含 `<key>/rag/**/*.md` + 终态 worker `output.md`/`trace.log`；“用了”= 本地 `exists=true` 的可核对引用；role 回落与 TS 不一致（F-4） |
| AC-016 | `rag/adapter.ts:403-410`（meta 白名单包含 `rewrite_degraded`）、`rag/tools.ts:553`、`evidence.ts:100-102` | 成立 | `meta.rewrite_degraded===true` 才追加 `rag-rewrite-degraded`；正常服务不出现 |
| AC-017 | `mw.py:1152`（`_rag_install_skill`）、`:1186`（`_rag_remove_skill`）、`:1198`（`_cmd_rag_sync`） | 成立 | 启用→字节拷贝（先写临时后 `os.replace`）；未启用→删文件；扩展侧不引用安装路径（源码扫描兜底） |
| AC-018 | `rag/adapter.ts:272-280`（`RAG_TOOL_MAP` 数据表）、`:311`（`ragToolCalls`）、`:335`（`mergeToolResponses`，`merge:"sources"` 保留 source/collection 归属） | 成立 | `rag_graph`→`graph_query`、`rag_sources`→`list_sources`+`list_collections`、重写开→`rag_search_multi_rounds`；三个映射在表里，非逐工具硬编码 |

合计：**17/18 只看代码成立**；AC-006 不成立（运行时语义缺失），AC-007 部分（两子句无测试）。AC-010/AC-015 的 `required = role.require OR phase.require` 并集在 TS（`config.ts:607`）与 Python（`mw_common.py:845`）两侧一致；`phase` 缺失时 TS `evidencePhase` 回 `"unknown"` 且 `phases["unknown"]` 不存在 → 不报 required，Python audit 的 `phase=""` 同理不命中。


## C. 质检报告判定复核

### ① 有没有 AC/COV 行在代码与测试里都找不到支撑
- **AC-006 的运行时语义**：代码里只有死函数，测试里只有直调死函数 → **无支撑**（报告判 Q-AC-006 ✅ 充分，应予纠正）。
- **AC-007 的 `[unreachable at session start]` + `trace=rag-unavailable` 子句**：代码有（`tools.ts:221-223`/`evidence.ts`），测试无 → **测试无支撑**。
- **AC-014 “rag-research 任务结束后必须产出文档”**：validator 有，但无任何用例驱动真实 task 产出 → **运行时无支撑**（纯函数部分有）。
- COV 行 F1~F9 均有对应测试或 golden（逐条看过 `evidence/verify-run-2026-09-22.md` §1/§2 与测试文件）；未发现其它完全空支撑的 COV 行。F3 的“top_k/depth 边界”只有 schema 声明（`Type.Number({minimum:1,maximum:10})`）而没有越界拒绝的负例（工具层未做范围校验），属轻微缺口。

### ② 报告列为 ⚠️ 的两项（Q-X-03 / Q-X-06）是否低估；其余 ⚠️ 候选逐条表态
- **Q-X-03（worker 语法级 vs audit 存在性）**：认可 ⚠️。依据：`worker-mode.ts:536-552` 的 `used` 只看 `scanCitations(...).length>0`（语法级），`mw.py:1887-1905` 的 `used` 要求 `status=="ok"`（存在）。同一输入可能一边静默一边报警。**不是低估**。
- **Q-X-06（`both` 真实 cli 回落）**：⚠️ 判定正确但描述偏轻。实测已覆盖回落的**判定路径**（`rag-evidence.test.ts:458-476`，fixture reset → cli 赢）与写工具不兜底（`:528-548`）；未验证的是真实网络下的错误分类。且 `mcp-client.ts:classifyFetchFailure` **默认回 `connect`**（只有 AbortController 触发才回 `timeout`），比 design D-005 “可证未送达”的约束更宽（如 undici `UND_ERR_HEADERS_TIMEOUT` 不在 CONNECT_ERROR_CODES 也不在 message 片段表 → 会归 connect → 允许只读兜底）。对只读检索可接受，但应在报告里写清而不是笼统归入“真实服务未联调”。
- **写工具不回落（rag_feedback）**：实测覆盖，无需 ⚠️。
- **协议/超时分类在真实网络下的表现**：真 ⚠️（保留）。fixture 只能模拟 reset/500/drop，无法重现真实 DNS/TLS/中间盒行为。
- **`rag-research` conductor 被禁对 AC-011 的运行时影响**：无负面影响。AC-011 本身就是“conductor 侧派发必须被拒”（`dispatch.py:391-398`）；PM 路径（`dispatch-models.ts:74` 的 `DISPATCHABLE_TYPES`）仍允许 `/worker --type rag-research`。不构成 ⚠️。
- **阶段轴大小写精确匹配的静默失效**：应单列 ⚠️（报告只把它记在 R-5 债务里，未进 ⚠️ 计数）。依据：`config.ts:607`/`mw_common.py:845` 都是精确字典查找，`phases: {design: ...}` 遇上 `- Phase: DESIGN` 时 `require` 永不触发，且 worker 与 audit 会“一致地错”（都判不需）→ 无告警。应在“声明了但从未匹配到任何已观测阶段”时输出提示。

### ③ VC-023 的“等价覆盖”（第三子句靠 VC-001 的 `skill_file_unchanged=true`）作用域是否同一件事
**不同一**。VC-023 第三子句是“**pi 会话 activate 前后**该文件存在性一致”（activate 路径）；VC-001 的 `skill_file_unchanged=true` 来自 `rag-tools.test.ts:214-235`：它先手写一个 `skillPath`，调用 `registerRagTools` + `dispatchTask`（enabled=[]），再断言文件仍存在——覆盖的是**注册/dispatch 路径**，且只断言“仍存在”而非“字节未变”。`rag-tools.test.ts` 的第二个 `it`（`:239-`）确实跑了真实 harness 会话，但没在该会话里放/查 skill 文件。真正强的是 `test_rag_cli.py::test_extension_source_never_references_the_installed_skill`（源码级“扩展根本不引用安装路径”），它是**结构保证**，比时序断言更强，但**不是同一件事**。判定：从 ✅ 降为 ⚠️（结论可接受，记账不准确）。

### ④ VC-017 拆成 L1+L2 两行是否规避了原 VC 语义
**没有规避**。原 VC 语义的三个子句分别在：L1（`rag-budget.test.ts:312`，`pings` 实算、`RAG_HEARTBEAT_INTERVAL_MS===30000`）、L2（`rag-e2e-slow.test.ts:227`，`worker_alive`/`rag_call_ms` 实算）。两个子句均被覆盖。但 `watchdog_enabled=true` 只是**代理证据**：断言是 `trace` 含 `[CHECKPOINT]` + `resolveIdleMs()===60000`，而 `[CHECKPOINT]` 由 convergence-checkpoint 定时器（`worker-mode.ts:922-927`）写入，不是 idle 定时器（`:944-956`）的日志；idle 定时器本身是否 armed 未被直接断言。另：L1 用 20ms 注入间隔而非生产 30s，只能证明 helper 行为。判定：保留 ✅，但把 `watchdog_enabled` 标为弱子句（“配置值 + 相邻定时器存在”，非“idle 定时器已运行”）。

### 对比：报告的总汇
| 项 | 报告 | 复核 | 依据 |
|---|---|---|---|
| 总结论 | ✅ 通过（❌0、⚠️2） | **需修订** | 至少 1 条 AC 运行时语义缺失、1 条子句零测试、2~3 条证据层级/断言强度高估 |
| Q-AC-006 / Q-VC-008 | ✅ 充分 | **❌ 不成立 / 伪覆盖** | F-1 |
| Q-AC-007 / Q-VC-009 | ✅ 充分 | **⚠️** | F-2 |
| Q-AC-014 / Q-VC-018 | ✅ 充分 | **⚠️** | F-3 |
| Q-AC-015（role 回落） | ✅ 充分 | **⚠️** | F-4 |
| Q-VC-023 | ✅ 充分（等价覆盖） | **⚠️** | C-③ |
| Q-X-03 / Q-X-06 | ⚠️ 欠债 | 维持 ⚠️（Q-X-06 描述需修正） | C-② |
| 阶段轴大小写 | 未进 ⚠️（仅 R-5） | **应 ⚠️** | C-② |
| R-5/R-6 已记录 | — | 认可 | — |


## D. 文档/契约不一致

只列最实质的 8 条（其余为措辞/完整度问题，略）。

| # | 不一致 | 位置 | 影响 |
|---|---|---|---|
| D-1 | README 的 `mw rag` 用法缺必填 `--project`；`rag probe [--server X]` 的 `--server` 在 argparse 里**不存在** | `packages/multi-workers/README.md:272-275` vs `packages/multi-workers/mw.py:4617-4637` | 照 README 会直接 argparse 报错（exit 2）；四个子命令的 `--project` 均为 `required=True` |
| D-2 | `mw rag probe` argparse help 写 “diagnostics only, never a non-zero exit”，实际配置错误时 `return 1`；且退出码口径不统一（list/probe/sync = 1，audit = 2）而 README 完全不写退出码 | `mw.py:4623` vs `mw.py:1426-1428`、`:1957-1977`；`README.md:272-275`；design §4.1 只写了 audit 的 0/1/2 | 脚本无法用统一口径判定；help 与行为矛盾 |
| D-3 | README 映射表 `rag_search` 行写“重写开关为真→走 `rag_search_multi_rounds`（服务端 LLM 改写，结果不可复现 → trace 记 `rag-rewrite-degraded`）”，把 multi-rounds 与“降级”混为一事 | `README.md:295`；对照 `rag/adapter.ts:272-273,311` 与 `rag/tools.ts:553` | `rag-rewrite-degraded` 只在服务端 meta `rewrite_degraded=true`（改写**失败**）时写，与“开了多轮”方向相反 |
| D-4 | `MW_RAG_ENABLED` 由 launcher 注入但**无人读取**（仅测试断言存在）；launcher 注释声称 worker 侧扩展据此门控注册，与实现不符；env 文档未登记该变量 | `launcher.py:352-353`；`docs/environment-variables.md:90-103`（只登记三个）；全仓 `grep MW_RAG_ENABLED` 只命中 launcher + 两个测试 | 死变量 + 误导性注释；将来有人依赖该门控会失效 |
| D-5 | 文档声称的 `[unreachable at session start]` 降级行为已交付，但无测试验证 | `rag/tools.ts:221-223`、`README.md:300`、`CHANGELOG.md`（coding-agent）vs 测试零命中 | 与 F-2 同根：文档说已验，实际未验 |
| D-6 | design §7 的 VC-008 期望是 fixture 记录的**实际请求参数**，实现/测试都没有该观测点 | `design.md` §7 VC-008 vs `rag-adapter.test.ts:247-259` | 契约与实现差距（同 F-1），但作为“文档/契约 vs 实现”也成立 |
| D-7 | README 的 6 行映射表 vs `adapter.ts` 的 7 条 `RAG_TOOL_MAP`（少 `rag_chat`，与 AC-018 的“六个”一致但未说明） | `README.md:293-300` vs `rag/adapter.ts:272-280` | 6 行本身与六个基工具逐行一致；仅可读性/完整度问题 |
| D-8 | README `mw rag audit [--out FILE]` 未提 `--key` / `--json`（设计 §4.1 有），而 CI/脚本常用 `--json` | `README.md:274` vs `mw.py:4629-4637`、`design.md` §4.1 | 低；不影响行为 |

已逐项确认**无**问题的 env 契约：`MW_RAG_SERVERS_FILE` / `MW_RAG_SERVERS_HOME` / `MW_RAG_PYTHON` 三个变量在 `docs/environment-variables.md:99-101` 都有声明，且均在代码里真实读取（`rag/config.ts:33,35,210-216`；`mw_common.py:364-365,374-396`；`rag/cli-bridge.ts:34`）—— 任务 D 要求的“三个变量是否真被读”结论为**是**。


## 反例试验记录

全部试验均先备份到 `.tmp/backup/`，改的是**被测数据/fixture**（非源码、非测试代码），跑完立即还原并用 sha256 自检。

### 0. 基线复跑（先在还原态确认绿）
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-{parity,tools,adapter,transport,evidence,toolmap,config,budget,required,research-doc}.test.ts` → **Test Files 10 passed (10)；Tests 97 passed (97)**；与 `verify-run` §0 命令 1 的 97 一致。
- `cd packages/multi-workers && python -m pytest test_rag_{config,cli,launcher,audit,phase,research}.py -q` → **76 passed**。
- 基线 sha256：`rag-block.golden.md = 00f85e646e30d577f434c6e1967a704c65966163a01d1bf4de9630c9717d4035`；`test/fixtures/rag/machine-servers.yml = 99c745c0bd87e9a753a40460099994dfc5a21de348976d1c0e41cca6f108ff7c`。

### 试验 A（针对 VC-027 的 `golden_byte_match` / `fingerprint_match`）
- 动作：把 `packages/multi-workers/test/fixtures/rag-block.golden.md` 最后一位 hex 由 `0` 改成 `1`（`...56034950` → `...56034951`）；文件 sha256 变为 `ad976e90598a3cd75cff7b5c6c74bddbd00dbcca1deffb625d836e93ce7b9602`。
- 看到：`rag-parity.test.ts` → **3 failed / 4 passed**，失败点为 `sha256(GOLDEN_FILE) !== GOLDEN_SHA256`、`config.fingerprint !== goldenFingerprint`、`goldenByteMatch`；`[VERIFY] VC-027` 行**未被打出**（断言先抛）。`python -m pytest test_rag_config.py::RagConfigTest::test_golden_block_and_idempotent` → **1 failed**，diff 就是 `fingerprint=...34950` vs `...34951`。
- 结论：VC-027 的 golden 字节/指纹是一把真锁，不是装饰；fixture 漂移会让两侧同时变红。
- 还原：`cp .tmp/backup/rag-block.golden.md ...`，sha256 回到 `00f85e...`（已验证）。

### 试验 B（针对 VC-013 的 `secret_hits=0` / token 名断言）
- 动作：把 `packages/multi-workers/test/fixtures/rag/machine-servers.yml` 里的 `token_env: OVERCODE_MCP_TOKEN` 改为 `..._RENAMED`；sha256 变为 `943c93c7633fb63e89ebfd0c418f3d3f41f6059ed94b50cf85537b2ac2784eb8`。
- 看到：`python -m pytest test_rag_config.py -q` → **3 failed**：`test_vc013_token_env_names_only`（`{'OVERCODE_MCP_TOKEN_RENAMED'} != {'OVERCODE_MCP_TOKEN'}`）、`test_vc024_merge_matrix`（`mcp.token_env` 不等）、`test_golden_block_and_idempotent`（指纹随 token_env 名变化）。
- 结论：VC-013 的 token **名**（以及 VC-024 的字段合并、VC-027 的指纹）确实是读 fixture 的；`secret_hits=0` 不是常量装饰。
- 还原：`cp .tmp/backup/machine-servers.yml ...`，sha256 回到 `99c745...`（已验证）。

### 试验 C（VC-001 `probe_requests=0` 的计数源活性）
- 未改数据的手工反证：同文件 `rag-tools.test.ts` 的 VC-004 用例启用 A/B 后断言 `await runtime.ready` 并且 `rag-evidence` 的 fixture 计数会随调用增长；即 `fixture.calls` 是一个会动的真实计数器。因此 VC-001 的 `fixture.calls.length===0` 在 enabled=[] 下成立是有意义的（若 `registerRagTools` 真的探活，该断言必红）。未从外部注入数据（该用例的 `target.yml` 由测试自写，外部不可变），故只做此间接论证。

### 留痕自检
- 试验后：`git status --porcelain packages/multi-workers/test/fixtures/` 为空；两个 fixture 的 sha256 回到基线值。
- 临时脚本与备份目录：`.tmp/expA_patch.sh`、`.tmp/expB_patch.sh`、`.tmp/g*.sh`、`.tmp/backup/`（均为未跟踪临时文件，不影响仓库跟踪文件；不作为交付物）。


## 需执行才能判定

1. **`MW_RAG_SLOW=1 node .../vitest --run test/suite/rag-e2e-slow.test.ts` 的实时复跑**（本次未跑：单次 ~180s，任务要求只做定向测试）。verify-run 声称 `rag_call_ms=180004 / pings=5`；不跑就不能独立确认 VC-017 L2 的实参。（本次只静态核对了断言链与 watchdog 计时器的 arm 位置。）
2. **对真实 rag-mcp 服务发一次请求**（`mw rag probe` + 各工具一次），核对 `RAG_TOOL_MAP` 的 wire 名与返回结构；未做就仍有 R-1 风险。
3. **真实网络下的错误分类**：构造 DNS 失败 / TLS 失败 / undici `UND_ERR_HEADERS_TIMEOUT` 场景，确认 `mcp-client.ts:classifyFetchFailure` 的默认 `connect` 不会把“可能已送达”误归为可兜底（C-②）。
4. **仓根 `./test.sh` 与 `npm run check`**：本次未跑（硬约束禁止全量），无法独立复核 verify-run §0 命令 8/9 的 exit 0 与三个外部失败的归属。
5. **一次真实 rag-research 任务端到端**（PM 派发 → worker 落盘 `<key>/rag/<server>-<slug>.md` → `validateResearchDoc` 判 ok）：本次只验证了 validator 本身（F-3）。

## 未覆盖点

- **PM 窗口侧的注册面**：`pm/pm-orchestrator.ts:635` 调 `registerRagTools`（但**不**调 `applyRagTools`），无测试断言 PM 会话实际可用六个工具（VC-004 只测 unit 注册表）。
- **`rag_chat` 的 server enum**：VC-004 只循环六个基工具断言 enum，`rag_chat` 的 enum 未验。
- **多份调研文档**：`validateResearchDoc` 只判 `rag/` 下第一份 `<server>-<slug>.md`（`research-doc.ts:184-186`），R-4 已记录但未验。
- **K3 硬门禁**：本 key 显式不做（spec §1.4），`required` 只告警；本次不判定。
- **`rag_feedback` 的重复落盘/重复计费面**：D-005 已禁止自动兜底，fixture 已验“写工具不兜底”，但真机重试语义未验。
- **阶段轴大小写静默失效的运行现场**：无测试覆盖 `target.yml phases` 键与 `pm-state.md - Phase:` 值不同大小写的场景（C-②）；README 已写明需同大小写，但代码不会在你拼错时提醒。
- **`rag` 块的 `[mw] Rewrite:` 行与适配器实际行为不一致**：task.md 告诉 agent 默认 rewrite=true/false，但适配器不会自动应用（F-1），也没有测试核对“注入块声称的 rewrite 值”与“实际调用发出的工具名”一致。

