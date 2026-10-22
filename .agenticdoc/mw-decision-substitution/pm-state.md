# PM State: mw-decision-substitution

## 1. Snapshot
- Key: mw-decision-substitution
- Claim-Id: WENBOZHOU-PC4:53592
- Phase: DONE
- Next Action: 实现全部完成，`check_gate(key, "done")` = True。签收已交给决策模型：`mw decide sign --project .agenticdoc/mw-decision-substitution`（无参数 = auto）→ `dp25-signoff-conclusion`（P2 默认开）→ jev 答 `narrow`（confidence=0.7，source=api），`signed_via: auto-decide`，`evidence/review/sign-final.md` + `authority-change` 行已落。残留待用户裁定/放话：① `narrow` 的执行面（是否按结论收窄 dp1/dp3 的 mode 或降级为 suggest）；② 21 个未接线 dp 是否补 `REQUIRED_STATE_FIELDS`；③ `ask_decision` 对 dp1/2/3 恒 `input-incomplete`（D-044）；④ 提交（`feat(multi-workers)` / `feat(coding-agent)` / `feat(ai)` + `docs`）；⑤ `dist/**` 重建（当前 bundle 早于 W5b-W11）；⑥ guard 文案与 `mw decide sign` 放行需 rebuild 后才在运行期生效
- deps: `mw-jev-provider-integration`（DONE，作为**决策底座**：`decision.py` / `decision_backends.py` / `mw decide` CLI / DP-1 单点接线 / 证据行）
- Started: 2026-10-19 17:38
- Updated: 2026-10-21 23:41
- Completed: 2026-10-21 23:41

## 2. Task Status

| 波次 | 任务 | 角色 | 状态 | 收口结论 |
| --- | --- | --- | --- | --- |
| SPEC | RQ-1 决策点普查 | research | done | 29.5KB：24 个决策点入表（14 必需 + 10 新增），带 path:line / 等人四型 / 可逆性 / 档位；needs-clarification **42/242=17.4%** 最高频；CHECKPOINT mid/high 60 条；gate 本仓 0 次；`auto_gate_mode(off/shadow/live)` 为最可复制先例 |
| SPEC | RQ-2 pi 交互面 | research | done | 20.8KB：**确认面可被 `tool_call` 钩子接管**（`agent-session.ts:480` → `agent-loop.ts:636` block）；`ask_decision` 工具返回值为最安全回灌（伪造 user 消息排除）；`input` 事件带 `source` 可实时判"人已开口"；`context` 钩子每 LLM 调用必跑 ⇒ 禁放 5s 决策 |
| SPEC | RQ-4 结构化输入 | research | done | 22KB：20 项字段盘点（`runner.error_kind`/rollback 字段**不存在**）；8 类决策最小充分字段表；三级敏感度 + 8 条机读规则；体积 16KB→**≤2KB**；9 个校验点；`isinstance(state, str)` 兼容旧调用；**锚点纠错：DP-1 state 组装实际在 `pm/ui-bridge.ts:1429-1436`（不是 :241-247）** |
| SPEC | RQ-3 授权与审计 | research | done | 26.4KB：两级状态机（`level` × `points[dp].state`）；独立快照 `.mw/decide-authority.json`；4 类行档案 + `prev_sha` 链；`decision_id` 幂等；6 种终态结算映射；done 门禁只加两条现成规则 |
| SPEC | spec.md 定稿 | pm | done | rev3 13.3KB+；AC-001..015；含可复用资产与需规避坑点两节 |
| DESIGN | D1 dp 注册表 + 配置表 + 指令族 | research | done | 42.7KB：`DecisionPoint` 9+1 字段（P0 必填 `p0_consequences`）；`decide_for` 11 步；enabled=false 在 `_encode_state` 前返回（FakeBackend.calls==0 可测）；8 层降级；`(st_mtime_ns, st_size)` 双签名热重载；`dp` 挂 `decide_sub`（`mw.py:7508`）；refresh 无变化不写文件 |
| DESIGN | D2 决策档案写入器 + fold | research | done | 35.7KB：6 函数骨架；seq=链尾+1；锁内含尺寸复核；半行尾保留；幂等抛 `DecisionArchiveDuplicate`→exit 2；4 类行字段矩阵；对账键 `evidence_line+evidence_sha`；PM 裁定 S0-S3 全采纳 |
| DESIGN | D3 dp3 三切 + dp2 执行面 | research | done | 32KB：插入点=finishSuccess 内 exitCode 判定(:3664) 与 writeOutputGuarded(:3671) 之间；3c 四级匹配 Jaccard>=0.6；注入=sendUserMessage(followUp)+`[mw dp3-answer]` 前缀；nc_raw/nc_human 双指标；dp2 auto 仅允许收窄，拆/直执必须人；五条不变量各配检查法 |
| DESIGN | D4 ask_decision 工具 + tool_call 钩子 | research | done | 93 calls：`pi.registerTool` + TypeBox；失败必须 throw（`AgentToolResult` 无 `isError`）；工具只 worker 分支注册、经 `activeToolsForType` 全角色追加（不进 `TOOL_ALLOWLISTS`）；**锚点纠错：`agent-loop.ts:636-641` 在 `packages/agent/src`**；钩子同步快、Python 往返放 tool execute；反重试=reason 给出路 + turn 级熔断 |
| DESIGN | D5 关联 + 报告 + 签收门禁 + apply 护栏 | research | done | 30.6KB：头行注入 `ui-bridge.ts:2282`；settle 点 `pm-orchestrator.ts:1691-1745`；**发现 spec §7.2 的 `content_match` glob 写法不可行**（`is_file()` 恒 False）→ 改固定名 `sign-final.md`；写守卫须另注册（`:666-687` 只是审计计数器） |
| DESIGN | D6 结构化输入 + 脱敏 + digest | research | done | 实测字节：dp1 706B / 最坏 1397/580/1363B < 2000；digest 改 Python 单点算 + 响应回传（TS 零哈希），测试向量 `d428504f067a5092` Python+Node 双侧一致；证明现分隔符会漂移；d3/d2/d1 必需字段 13/14/12 项 |
| DESIGN | design.md | pm | done | 12KB，D-001..D-022；§0 并行性分析 + 冻结接口 + 6 波次 + 测试矩阵 |
| SPEC | RQ-5 度量 | research | done | 16.3KB：人工轮次/墙钟**今天可离线测**（pi 会话 JSONL）；三比率算法；6 个最小埋点 E1-E6；Wilson 95% 下界判据 |
| SPEC | spec.md 草稿（已写，含 AC-001..013） | pm | draft | 待 RQ 回填后定稿 |

## 2.1 目标（本 key，2026-10-16 用户重定义）

jev 是**决策模型**，目标不是"提供建议"，而是**替换掉中低风险的人工决策**（省掉人出现与等待的墙钟时间）。交付三件事：

1. **决策点抽象**：框架里所有"现在会去找人"的位置全部抽象为 dp（代码注册表），按 P0/P1/P2 落位。
2. **配置表授权**：`.mw/decide-points.json` 是唯一权威；P2 默认开、P1/P0 默认关；人可指令改或直接改文件，改完即生效；LLM 只能建议。
3. **决策留痕与 review**：决策档案 + 结果关联 + phase 末报告 + key 收尾强制签收。

## 2.2 相位推进记录

| 相位 | 结果 | 证据 |
| --- | --- | --- |
| SPEC | 通过（rev3，AC-001..015） | `spec.md`；5 束 spec 调研 |
| DESIGN | 通过 | `design.md`（D-001..D-022）；6 束设计调研 `evidence/research/design-*.md` |
| PLAN | 通过 | `plan.md`（T-01..T-10、并行序 `W1 ∥ W2 ∥ W3 → W4 ∥ W5 → W6`） |
| TASKS | 通过 | `tasks/T-01..T-10*.md`（含写入允许面/禁止面/验收命令/种子） |
| EXECUTE | 进行中（T-01..T-10 全部 done 并经 PM 独立复跑；含衍生卡 T-01b/T-02b/T-02c/T-04b/T-04c/T-04d/T-05/T-07b/T-08/T-08b/T-08c/T-09b；QG 三轮收口 → FIX-A..F 全部落地） | `quality-gate-report-20261020.md`（一轮 35.7KB）+ `…c.md`/`…d.md`（窄卡）+ `…b.md`（宽卡重跑，27.5KB，**PASS 6/6 关闭**）；全量基线 Python 8F/2729P、TS 18F/1838P；本 key 9 个 TS 套件 **192 passed**；`tsgo --noEmit` rc=0 |

## 3. Evidence Ledger

| 项 | 路径 | 结论 |
| --- | --- | --- |
| RQ-1 | `evidence/research/spec-decision-inventory-20261016.md` | **done** 29.5KB（24 点表 / 频次实测 / 委派先例 / 6 类 P0 红线） |
| RQ-2 | `evidence/research/spec-pi-interaction-surface-20261016.md` | **done** 20.8KB（钩子能力表 / 三接触面可行形态 / 每-turn 钩子禁区） |
| RQ-3 | `evidence/research/spec-authority-audit-model-20261016.md` | **done** 26.4KB（状态机 / 档案 schema / 结算映射 / gate 两条规则） |
| spec 定稿 | `spec.md` | 12.5KB；AC-001..AC-014；RQ-1..RQ-5 全部回填 |
| RQ-4 | `evidence/research/spec-structured-input-contract-20261016.md` | **done** 22KB（字段盘点 / 最小充分字段 / 三级脱敏 / ≤2KB schema 草案 / 9 校验点） |
| RQ-5 | `evidence/research/spec-decision-metrics-20261016.md` | **done** 16.3KB（可测性 / 三算法 / 基线 / 埋点集 E1-E6） |
| D1 | `evidence/research/design-registry-config-20261019.md` | **done** 42.7KB（注册表字段 / 11 步控制流 / 8 层降级 / 热重载 / dp 指令族 / refresh） |
| D2 | `evidence/research/design-decision-archive-20261019.md` | **done** 35.7KB（写入器骨架 / seq+链 / 幂等 / 字段矩阵 / fold / 对账） |
| D3 | `evidence/research/design-dp3-dp2-execution-20261019.md` | **done** 32KB（插入点 / 三切判定 / 注入形态 / 降级 / dp2 收窄 / 五不变量） |
| D4 | `evidence/research/design-ask-tool-hook-20261019.md` | **done**（工具注册 / 返回契约 / 拦截 / 四模式 / 分层 / 失败矩阵） |
| D5 | `evidence/research/design-association-report-signoff-20261019.md` | running |
| D6 | `evidence/research/design-input-redaction-20261019.md` | **done**（28 行字段表 / 实测字节 / Python 单点 digest / L2 双防线 / 拒发分工） |
| 底座 | `.agenticdoc/mw-jev-provider-integration/{achieved.md,docs/jev-integration-flow-and-usage.md}` | DONE：契约/三后端/CLI/doctor/DP-1 旁路；137 Python + 21 TS |
| QG 复审 | `evidence/quality-gate-report-20261020.md` | **PASS-WITH-FINDINGS**（35.7KB）：AC 12 covered / 3 partial / 0 missing；0 blocker + 4 major + 9 minor + 3 nit；单一权威排查 4 处读表（1 权威 + 3 镜像）；测试有效性抽样 5 处（1 处反面样本）；契约抽查 D-011/012/014/021/028/030/041 |
| QG-2C | `evidence/quality-gate-report-20261020c.md` | **PASS-WITH-FINDINGS**（15.7KB）：MAJOR-1 关闭（无读表/无 mode→acted/四键只取子进程）、MINOR-5 关闭（`input-oversize` 本属七值集合，是对齐不是加宽）、MAJOR-2 部分关闭（必填字段 dp1 13/dp2 14/dp3 12 逐项对齐，但 dp1/2/3 经工具恒 `input-incomplete`）；**纠正 PM 两处前提错误**：AC-012 实为 dp refresh、《FIX-D》卡的「`input-oversize` 非 Python 成员」前提错 |
| QG-2D | `evidence/quality-gate-report-20261020d.md` | **NOT-CLOSED**：MAJOR-3 残留 `worker-mode.ts:4933` 子进程 mode 缺失回退本地 policy；MAJOR-4 残留 `xkey-gate-guard.ts:383` `lastIndexOf("evidence")` 误拒 `evidence/research/evidence/sign-final.md`；MINOR-1 静态关闭（三态齐备）；AC 矩阵维持 12/3/0。PM 已独立复现两条 |
| FIX-E | `workers/ds-fix-e-mode-deeppath/report.md` | **done**（3m，68 calls）：dp3 spawn 路径 `childMode = payload.mode` + 非 `auto`/`suggest` → `escalate("unavailable","3a","decision mode missing")`；签收守卫改 `indexOf("evidence")`；新增 2 用例（dp3-answer 20→21、xkey-gate-guard-coverage 11→12）；PM 复跑三套件 **44 passed**、`tsgo --noEmit` rc=0、biome rc=0；顺带修复 CHANGELOG 5 处历史 em-dash mojibake |
| QG-2B（宽卡重跑） | `evidence/quality-gate-report-20261020b.md` | **PASS**（27.5KB，98 calls / 29m，glm-5.3）：一轮 6 条发现 **6/6 关闭**（含 FIX-E 对 2D 两条残留的收口）；AC 矩阵维持 12/3/0；修复批次无新 D-036 违约/fail-open/跨层漂移；残留 7 条（字段集无 Python 执行锁、`ask_decision` 三 dp 不可答属设计、doc §3 措辞、写通道落位不对称、MINOR-7/8/9 维持、cp936 事故无独立字节基线） |
| FIX-F | `workers/ds-fix-f-signoff-parity/report.md` | **done**（2m，53 calls）：`isDecisionSignoffPath` 委派 `isDecisionSignoffEvidenceTarget`（四通道两落位一致拒，深层产物仍放行）+ bash ref 闸补根落位；doc §3 补分歧闸（`triage_type === 实际 type`）；用例 48 passed（xkey 12→13、decision-signoff 11→12）；PM 复跑三套件 48 passed + 全套件 union **192 passed**、`tsgo --noEmit` rc=0 |
| FIX-G | `workers/ds-fix-g-box-type/report.md` | **done**（4m，60 calls）：`box` 成为可作答自由文本类型（`ANSWERABLE_TYPES` 加 `box`、`_b2_input_schema` → string 1..600、`_validate_answers`/B3 `_decode_answers` 同分支）；`_unsupported_types(questions_map(dp3)) == []`（前为 `['clarifying_answer']`）；PM 复跑 `test_decide_backends.py` **50 passed** + cli 61 passed；**真实调用** dp3 `available=true` 6.4s（`fact` 0.85） |
| 官方契约核对 | `H:\tmp\ts-api.md`（`https://docs.typesafe.ai/api/system-one.md`，2026-10-20 抓取） | **PM 直执**：Jev 唯一端点 `POST https://api.typesafe.ai/v1/systemone`；question `type ∈ {noul,choice,score,box}`，**无自由文本类型**；`box` = 图像定位框（答案 `{top,bottom,left,right}` 归一化坐标，需 `TypeSafe-Danger-Zone-Images: true` + 图像 `assets`）；`score` 答案是**浮点**（示例 `1.7`）并带 `legend`/`probabilities`；`noul` 是概率（`0.98`）不是布尔。→ **FIX-G 的 box 自由文本实现与契约相反** |
| FIX-H | `workers/ds-fix-h-jev-contract/report.md` | **done**（5m，67 calls）：`ANSWERABLE_TYPES` 回 `('choice','score','noul')`；`box` 改为独立原因 `box-requires-image`（凭据/HTTP 之前拒绝、零 HTTP）；`score` 接受浮点；B3 `_decode_answers` 按官方形状解析并映射内部 `{value,confidence}`（choice 校验 criteria 键、noul 概率 0..1、box 显式 unsupported、`type` 缺失/不一致 → `answer type mismatch for <qid>`）；PM 复跑 **58 + 61 passed**，并追加 `decision.py` 的 `REASON_BOX_REQUIRES_IMAGE`（否则客户端归一成 `upstream-error`）→ 四套件 **188 passed**；真实 CLI 探针 `reason="box-requires-image"`、`attempts=1`、`latency_ms=0`、`acted=false` |
| FIX-I | `workers/ds-fix-i-dp3-native/report.md` | **done**（6m，79 calls，报 BLOCKED-partial）：`_validate_question` 支持 `dynamic_choices`（仅 choice、非空 state 键、与静态 choices 互斥）；dp3 → `answer_kind`(choice) + `answerable`(noul) + `candidate`(choice/`dynamic_choices=local_candidates`)，dp8 → `scope_decision` + `scope_reason`(choice)；`REQUIRED_STATE_FIELDS[dp3]` 加 `local_candidates`；新增 `dynamic_choices_value_error`/`dynamic_choice_labels`/`resolve_dynamic_choices`；B2/B3 用渲染集合（enum/criteria/成员校验）；不可渲染 → `input-incomplete` 零 HTTP。**卡外遗回 PM 收口**（见 FIX-I-PM 行） |
| FIX-I-PM（PM 直执） | 无（PM 编辑 `decision.py` / `decision_points.py` / 3 个测试文件） | **done**：① `decision.py:_validate_input` 接受 `dynamic_choices`（与静态 `choices` 互斥）；② `decision_points._value_fits` 接受渲染 id 集合 + `score` 接受浮点 + `noul` 限 0..1；`_unusable_answer` 透传 `resolve_dynamic_choices(questions, state)`；③ 三份测试 fixture 改为新题集（dp3 state 带 `local_candidates: c1`、`answerable` 0.9、`candidate` c1）。**并发发现并修复 B2/B3 契约分叉**：B2 的 `_describe_questions`/`_b2_input_schema`/`_validate_answers` 仍把 `noul` 当布尔，与 B3 的概率口径相反 → 统一为概率 0..1（并算上 FIX-H 的 `score` 浮点）。复跑：五文件 **211 passed**；全量 `pytest` **2769 passed / 8 failed**（同基线名单） |
| FIX-J | `workers/ds-fix-j-dp3-candidates/report.md` | **done**（8m，107 calls）：`DP3_QUESTIONS_VERSION` → `q-fcbd3847`、`DP3_ANSWERABLE_MIN=0.5`、`DP3_CANDIDATE_LIMIT=5`；新增 `dp3CandidateTokens`/`buildDp3Candidates`/`dp3CandidateLine`/`resolveDp3CandidateAnswer`/`parseDp3Probability`；`buildDp3State` 带 `local_candidates`（发送集合==校验集合）；3a 三条拒绝分类 + 本地合成 `answer`（本地行 ≤200 字符 + `(<relpath>:<line>)`）+ `DP3_CITATION_RE` 捕获；`[DECIDE]` 冻结行格式未动。复跑：tsgo rc=0、biome clean、dp3-answer **30 passed**、四套件 **102 passed**；PM 复跑五套件 **132 passed** |
| FIX-K | `workers/ds-fix-k-timi-systemone/report.md` | **done**（3m，70 calls）：新增 `packages/ai/src/api/typesafe-systemone.ts`（`POST {baseUrl}/v1/systemone`、Bearer、body 只 `{model,state,questions}`、一次性 JSON、`answers` 作文本、usage 映射、非 2xx 带状态码）；`timi.ts` 仅对 `jev-latest` 覆写 `api: "typesafe-systemone"`（目录数据未改，留待目录刷新）。PM 复跑 `test/typesafe-systemone.test.ts` **6 passed** |
| stand-in 端到端（PM 直执） | `H:\tmp\mwds-jev\req-dp3-candidates.json` | **实测**：`mw decide run --dp dp3-worker-clarify` → `available=true`、`answer_kind=fact` / `answerable=0.9` / `candidate=c3`、5996ms、`acted=false`。**engine 仍是 `timi/glm-5.3-flashx`（stand-in），不是 jev** |
| FIX-L | `workers/ds-fix-l-timi-decisions-only/report.md` | **done**（6m/60 calls）：`TimiDecisionsBackend` 成为唯一传输（`/v1/decisions`、`jev-latest`、裸 timi key、body 仅三键），`LLMTransitionalBackend`/`LLMProxyAnthropicBackend`/`DirectSystemOneBackend` 与 `TYPESAFE_*`/`TOOL_NAME`/`ANTHROPIC_VERSION` 全删；旧 transport 值 → `entry-unavailable`（detail `unknown decision transport <x>`，零 HTTP）；`test_decide_backends.py` 55 + `test_decide.py` 70 passed；`dir()` 只剩 `DecisionBackend`/`TimiDecisionsBackend` |
| FIX-N | `workers/ds-fix-n-timi-decisions-api/report.md` | **done**（2m/43 calls）：`packages/ai/src/api/timi-decisions.ts` 新建（`${baseUrl}/v1/decisions`、`authorization: apiKey` 无 Bearer、契约头注释按 `jev接入.md`），`providers/timi.ts` 只对 `jev-latest` 路由到 `timi-decisions`；PM 删掉两个过期 `typesafe-systemone.*` 后 `tsgo --noEmit` rc=0、`test/timi-decisions.test.ts` 6 passed |
| FIX-M | `workers/ds-fix-m-decide-ask/report.md` | **done**（10m/110 calls）：`mw decide ask`（`--state/--state-file/--noul/--noul-criteria/--choice/--score/--model/--json/--project`）走 `DecisionClient.decide` legacy 路径，人类三列表格 + `--json`，失败 exit 2 原样上抛；`test_decide_cli.py` 从 29 errors 修到 41 passed（含 12 条 ask 用例），README decide 段 rebase 到 `timi-decisions`/`jev-latest`；残留：`usage` 恒 `null`（冻结响应不带 token 数） |
| FIX-O | `workers/ds-fix-o2-registry-instructions/report.md` | **done**（3m/58 calls）：dp1/dp2/dp3/dp8 共 8 题补真实 `instructions`、7 个静态 `choice` 补 `labels`、`dp3.answerable` 补 `criteria{true,false}`；`_questions_version` 改为只 hash `id/type/choices/dynamic_choices`，24 个 dp 版本号逐字未变（dp3 仍 `q-fcbd3847`）；`test_decision_points.py` 72 + `test_decide_backends.py` 57 passed；PM 复跑六套件 **278 passed**、全量 `pytest packages/multi-workers` **2767 passed / 8 failed**（同基线名单） |
| jev 真调用（PM 直执） | `H:\tmp\mwds-jev\req-dp3-fresh.json`、`H:\tmp\mwds-jev\req-dp3-candidates.json` | **实测 2026-10-21**：①`mw decide ask` → HTTP 200、1192ms、`urgent 0.88` / `dept billing 0.97`（probs 0.98/0.02/0.00）/ `frustration 1.01`；②dp3 新请求 → `candidate=c2`（0.97，probs c2 0.98）命中正确文件、`answer_kind=fact`（0.46~0.56）、`answerable=0.11~0.40` → 3a 按设计拒答上抛（`escalated_reason=low-confidence`，legacy `reason` 映射为 `bad-response`，见 `mw.py:858`）；③旧请求同链路 `answer_kind` 置信由 0.13 升到 0.45~0.49（FIX-O 补文本后），`candidate` 恒 0.79~0.84 |
| FIX-P | `workers/ds-fix-p-signoff-command-gate/report.md` | **done（含 1 项 PM 收口）**（9m/111 calls）：`decide_signoff.py`（`collect`/`verdict`/`render`/`parse_signoff`/`write_signoff`，538 行）+ `mw decide sign`（preview / `--conclusion` / `--reason` / `--allow-empty` / `--dry-run` / `--json` / `--key`）+ done 门禁 `decision_signoff`（仅 `decision-scope.md` 生效，重算 `rows_sha256`，`continue` 需 N≥1 且每行真 jev）；四份 `advance_phase.py` 同 sha `d507101d4b66`；`test_decide_signoff.py` 37 例 + 八套件 **389 passed**；PM 补 CHANGELOG 条目（write_face 头漏项，worker 未绕护栏）、写 `decision-scope.md` 标记、在本仓真跑一条 jev 决策行（seq 25）并验证 done 门禁按预期只缺 sign-final |
| FIX-Q | `workers/ds-fix-q-mw-decide-sign/report.md` | **done（PM 收口 2 项）**（7m/96 calls）：Python 侧 `--human-confirmed`（只在这一次写入期间隐会话探测变量，`finally` 恢复）+ `signed_via: cli|tui` 机器行 + preview `--json` 增 `verdicts`；TS 侧 `decideMw`、`parseDecideArgs`/`formatDecidePreview`/`runMwDecideCommand`（hasUI 强制、verdict 不过不弹框、确认后才写）、`/mw` dispatcher + usage；`test_decide_signoff.py` 8 例、`test/suite/decide-command.test.ts` 12 例。PM 复跑九套件 **397 passed**、vitest 12 passed、`tsgo --noEmit` rc=0；PM 补 multi-workers CHANGELOG 条目；并用临时项目实证豁免：会话内无 flag → `refusing inside an agent session` 零写入，带 flag → 写入且 `signed_via: tui` + 档案 `by=signoff:continue`，临时 key 的 done 门禁签收项 0 失败；同时实证 engine 校验（`confidence_source` 缺失的行被判 `engine mismatch at seq N`）。残留：worker 把等价逻辑放在 `mw.py` 的 `_decide_sign_signed_via`/`_decide_sign_write`（卡片原想改 `decide_signoff.py`，被 write_face 头挡），行为与产物逐字节一致，已在 pm-state 记为可接受偏差 |
| FIX-R + D-CFG | `workers/ds-fix-r-decision-typing/report.md`、`workers/ds-d-cfg-registry-export/report.md` | **done**（4m/52 calls + 6m/88 calls）：FIX-R 把 `DecisionClient.decide` 的入参变成真类型（`DecisionState` 联合 + `Mapping[str, QuestionSpec]`，TypedDict/Literal），并新增两条 fail-loud（noul `criteria` 必须恰好 `{true,false}`、`choice` 同时给 `labels`+`dynamic_choices` 直接拒），`test_decide.py` 70→77；D-CFG 新增 `decision_points.registry_snapshot()` → `packages/multi-workers/decide_registry.json`（24 points + 手工 `wiring`，wired=3）+ `mw decide dp export [--json|--write]`（重生成保留 wiring，坏文件拒写）+ 31 例漂移守卫。PM 复跑：`test_decide*` 294 passed、`test_decide_registry_export+dp_cli` 63 passed、`export` 打印 `24 3`；PM 补 CHANGELOG FIX-R 条目、写 `docs/decision-points.md`（§3 总表由配置渲染）、从 `docs/decision-substitution.md` 与 README 互链 |
| W1-W4 | `workers/ds-w1-token-caps/report.md`、`ds-w2-py-rename`、`ds-w3-ts-rename`、`ds-w4-config-verify/report.md` | **done**：W1 state 收紧到 `Mapping|str|Sequence[str]` + 32k/64k token 双闸（`_estimate_tokens` 保守估算，`max_state_bytes` 缺省 0=关）；W2/W3 state 字段去缩写（`v`→`schema_version`=2、`dp`→`decision_point`、`scope.ext`→`scope.file_extensions`、`progress.elapsed_min/budget_min`→`…_minutes`），Python 与 TS 两侧无别名、无重写；W4 配置自描述（每 dp 自带 `wired/trigger/adopted_at/wiring_note`，`required_state_fields` 变 `{name,type,description}`，schema=2，顶层 wiring 合并）+ `mw decide dp verify [--live]` + `set/show` 认识新键 + Python↔TS 必填字段 parity 测试（顺带补上 TS dp3 缺的 `local_candidates`）。PM 收口：补 CHANGELOG（worker 被 write_face 拦）、修正 `risk_source`/`task_type` 字段描述与 TS 枚举一致、重算 `decide_registry.json`；复跑 `dp verify` **24 ok / 0 fail**、`dp verify --live` **24/24 available=true, jev-latest, 0.77-1.36s**（证据 `evidence/runs/jev-live-20261021/dp-verify-live.txt`）、pytest 212 passed + 301 passed 回归、`tsgo --noEmit` rc=0；重写 `docs/decision-points.md`（§3 表格与新配置同源、新增 §8 契约验证）|
| W5b-W8 | `tasks/W5-per-dp-policy-knobs.md`、`W6-context-to-decide-model.md`、`W7-decision-book-check.md`、`W8-decision-worker-type.md` | **done**：W5b per-dp 旋钮（min_confidence/max_questions/timeout_s，三层生效 + 档案 `policy` 回显，PM 补 `decide_archive` 列）；W6 context 槽位（task_excerpt/change_summary/candidate_snippets/artifact_status/error_excerpt）+ 注册表生成 TS 字段清单 + `assertStateMatchesRegistry`；W7 决策本（`book new` 按注册表生成骨架/`book check` 七类失败码封闭键集合/`--book` 先验后发零 HTTP）；W8 `decision` worker 类型（词表/角色/卡片四项判据/allow-send 门/写面收窄/`mw dispatch check`）。PM 收口：统一 W6/W7 的槽位口径（`error`→`error_excerpt` 1500、`change_summary` 800，`decision_context` 为唯一权威）、补 5 处镜像锁（dispatch-card 词表+extras、dispatch-models、`/mw model set` 角色表、dispatch_worker 类型描述、三个 frozen 快照）、在 `mw.py` 注册 `dispatch check`（worke 写面外）。复跑：decision 相关 Python 226 passed、TS 6 suite 152 passed；`output-sections.ts` 被另一个 live 窗口（claim-driven-review）改到半途有语法错，`tsgo` 全局不可用（非本 key 引入）|
| W9-W11 | `tasks/W9-sign-auto.md`、`W10-decide-prepare-rename.md`、`W11-signoff-dp-p2.md` | **done**（用户裁定 D）：W9 签收交给决策模型 —— `.mw/decide.json` 增 `signoff: auto|disable`（缺省 auto，非法值 `signoff_error` 不拖垮主链路）、`mw decide sign` 无参即自动流程（disable 不写文件且 `done` 豁免 / auto 走 `dp25-signoff-conclusion`（`signed_via: auto-decide`）/ 回落 LLM 推断（`auto-llm` + `decide_fallback`））、`write_signoff` 只对 `auto-*` 放行 agent 会话、`xkey-gate-guard` 文案与放行面更新、顺手修 `config_sha_after` 64→16 hex 既有 bug；W10 `decision` worker 改名 `decide_prepare`（判据码与写面不变，不留别名）+ role 级模型 `.mw/dispatch.yml models.decide_prepare=timi/gpt-6.1-sol`；W11 把 dp25 由 P1 改 P2（注册表铁律只有 P2 默认开）+ 无副作用回显 executor，让默认路径真走 jev。PM 收口：`test_decide_dp_cli` 24→派生计数、`pm/decision-tool.ts` 补 dp25 两个 id 枚举、两包 CHANGELOG、design D-070a/D-071a。实测：`mw decide sign` → `conclusion: narrow`（confidence=0.7 api）→ `signed_via: auto-decide`；`check_gate(done)` True |
| 第二轮 A+3 | `spec.md` §14（AC-016..020）、`design.md` §8（D-048..058）、`tasks/W5`/`W6`/`W7` | 用户裁定 per-dp 配置做 A（只 `min_confidence`/`max_questions`/`timeout_s`，不做 model/transport），并要求补：①把工程环境里真正有用的上下文传进 decide model（context 槽位 + 截断 + 来源 + 脱敏，嵌在 state 内不新增线上字段）；②worker/PM 如何正确书写决策本（格式、位置、禁占位符/禁预期答案、证据引用）；③决策本验收（`mw decide book check` 七类失败码 + `ask/run --book` 先验后发零 HTTP）。PM 已写 spec/design/三张卡，W5 先跑，W6/W7 待 W5 收口后并行 |

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions

- **DS-1 授权分级（用户 2026-10-16 裁定）= 三档**：`disable`（全关，零行为变化）/ `enable`（**默认**，仅 P2 可 binding，P1 只建议）/ `advance`（P1+P2 可 binding）。**P0 永久人工**（写死在 policy + 代码硬拒）：不可逆操作、凭据/权限配置、对外通信、花钱、删除他人工作、用户已明确表态的事（人的 override 优先级最高）。
- **DS-2 review 节奏 = 按推荐**：每个 phase 末**自动**生成决策 review 报告；每个 key 收尾**强制签收**（`continue` / `narrow` / `revoke`，结论写回授权配置）。
- **DS-3 jev 不替代 pi 破坏性操作确认 = 按推荐**：先不做；需先证明扩展能拦 tool call，排最后一项。**【RQ-2 已证明技术上可行】**（`tool_call` 钩子可 block + reason），不做是**政策选择**而非能力限制。
- **DS-6 不做 shadow（用户裁定 B 方案）**：advisory 样本被锚定污染（PM 看到建议必然趋同），不作晋升依据；晋升由签收人工驱动；快照预留 `mode` 字段以便将来加。
- **DS-9 唯配置论（用户裁定）**：配置表 `.mw/decide-points.json` 是唯一授权权威；**P2 默认开，P1/P0 默认关**；LLM 遇到卡点只能**建议**打开配置，开关永远由人执行；代码不得内置绕过配置的旁路。
- **DS-10 决策全部抽象为 dp（用户裁定）**：每个 dp 在注册表有唯一条目（id/tier/默认值/问题集/输入构造/执行器），调用点只允许 `decide_for(dp_id)`；未知 dp 拒绝。
- **DS-11 dp 可指令刷新（用户裁定）**：`mw decide dp refresh` 从注册表单向同步配置表（只增缺失行、不动已有开关值、孤儿行标 orphaned、幂等）；配置改动无需重启（按 mtime 重读）。
- **DS-12 P0 可被配置打开（用户裁定“按推荐”）**：`dp on <P0> --i-understand-p0` 二次确认 + 档案 `by=human:p0-confirm` + 签收必列已开 P0；不保留隐形硬拒。
- **DS-13 配置表加 `mode` 列（用户裁定“按推荐”）**：`auto`/`suggest`；建议 P1 首次开启先 `suggest` 跑一个 phase 再转 `auto`（用一列代替 shadow）。
- **OPEN-1/OPEN-2 已关闭**（2026-10-19 用户“按你推荐”）。
- **DS-7 执行面定档（RQ-2 实测）**：① 回灌通道 = **工具返回值**（最安全、全审计）；伪造 user 消息**排除**（会污染"人已表态"检测）；系统注入仅用于长期政策。② 拦截点 = 扩展 `tool_call` 钩子（headless 也生效）。③ 禁挂点：`context` 钩子每 LLM 调用必跑，**永不**放同步决策。
- **DS-8 优先级重排（RQ-1 频次×单次成本）**：① needs-clarification 预消化（17.4%）→ ② gate shadow 常开 → ③ checkpoint PM 自治 → ④ DP-1 弱输入 → ⑤ release readiness → ⑥ QG override。6 类 P0 红线永不替换。
- **DS-4 失败处置 = 按推荐**：不可用 / 低置信 / 超授权面 → 一律**上抛人**；**禁止任何默认动作**。
- **DS-5 立项方式 = 新起 key**：`mw-jev-provider-integration` 保留 DONE 作底座；本 key `deps` 指向它。

## 6. Turn End Records
*(empty)*

## 7. Process Log

- 2026-10-16 22:05 用户重定义目标：jev 是决策模型，要替换中低风险人工决策的时间；要求 (1) 明确 jev 与 PM/worker/pi 的交互 (2) 抽象所有需要人决策的行为 (3) 决策留痕 + 阶段末人工 review (4) 补充必有项。PM 产出需求分析草案（14 类决策点分级 / 三接触面 / decision record / 10 条必备项 / 5 个待裁定问题）；用户裁定授权三档 `disable|enable|advance`（默认 enable=P2），其余按推荐。本 key 立项，进入 SPEC 并行调研。
- 2026-10-19 5 束 RQ 全部回收并 ack；PM 判定 shadow 有价值（盲测），修订 spec 为“两级授权（档位 × 点状态）+ shadow”。
- 2026-10-19 用户追问 shadow 的必要性 → 展开 B 方案（不做 shadow、签收驱动）→ 用户再追问“自动降级是什么 / 回到核心目标” → PM 给出四问判据 + 24 点三档落位 + dp3 三切。
- 2026-10-19 用户四条新裁定：①代码上把决策都抽象成 dp ②授权用配置表（指令改或直接改文件）③唯配置论（P2 默认开、其余需配置、LLM 只能建议）④dp 可指令刷新。PM 据此重写 spec 定稿 rev2（删两级状态机与 shadow，改配置表驱动，新增 DS-9/10/11 + OPEN-1/2，AC 重写为 AC-001..014）。
- 2026-10-19 用户“按你推荐”：OPEN-1 → DS-12（P0 可开但需 `--i-understand-p0` + 留痕 + 签收必列）；OPEN-2 → DS-13（加 `mode` 列）。spec rev3 定稿（AC-001..015）；准备 advance spec→design。
- 2026-10-20 QG 一轮 PASS-WITH-FINDINGS 后派 FIX-A..D 四卡并行，PM 逐张独立复跑（9 套件 188 passed，Python 2729 passed）。
- 2026-10-20 QG-2 宽卡（`ds-qg-review-2`，`timi/gpt-6.1-sol`）连续 3 次 `stream closed before response.completed`，实测上下文 209.8k–214.2k > 模型 200k 窗口，launcher 按 P-049 降级到 glm-5.3。根因：`_checkCompaction` 只在回合结束（`agent-session.ts:1098`）与发 prompt 前（`:1209`）评估，工具循环迭代之间不评估（阈值 183,616 在 12:04:24 的 197,092 已越线但当时 `stopReason=toolUse`）。改为拆两张窄卡（写入上下文纪律：单次读 ≤200 行、禁整读 4000+ 行文件、全程 ≤120k）后同一模型两次均跑完。
- 2026-10-20 QG-2C / 2D 并行回收：2C 关闭 MAJOR-1 与 MINOR-5、部分关闭 MAJOR-2（dp1/2/3 工具恒 `input-incomplete`，留 D-044 取向待定），并纠正 PM 两处前提错误（AC-012 实为 dp refresh；`input-oversize` 本属 Python 七值集合）；2D 判 NOT-CLOSED（`worker-mode.ts:4933` mode 回退、`xkey-gate-guard.ts:383` 深路径误拒），PM 逐条复现后派 FIX-E 收口。
- 2026-10-20 FIX-E done：dp3 spawn 路径改 fail-loud（不回退本地配置）、签收守卫改首个 `evidence` 段判定；PM 复跑 dp3-answer 21 / xkey-gate-guard-coverage 12 / decision-signoff 11 = **44 passed**，`tsgo --noEmit` rc=0。
- 2026-10-20 QG-2B 宽卡（`ds-qg-review-2` 重跑成功，glm-5.3）判 **PASS**：一轮 6 条发现全部关闭、AC 矩阵 12/3/0 无翻转、修复批次无新 D-036 违约/fail-open/漂移；新增两条残留（写通道落位不对称、doc §3 采纳条件表述不完整）→ FIX-F。
- 2026-10-20 FIX-F done：`isDecisionSignoffPath` 委派 `isDecisionSignoffEvidenceTarget`（四通道两落位一致拒、深层产物仍放行）+ bash ref 闸覆盖根落位 + doc §3 补分歧闸；PM 复跑 xkey-gate-guard-coverage 13 / decision-signoff 12 / decision-tool 23 = **48 passed**，全套件 union **192 passed**，`tsgo --noEmit` rc=0。
- 2026-10-20 用户要求“看到 jev 真正在做决策”。PM 在临时项目 `H:\tmp\mwds-jev` 打开决策服务后实测：dp1 `available=true`（coding/mid 0.9, 5.1s），**dp3 `available=false reason=unsupported-question-type`** —— 根因 `ANSWERABLE_TYPES=("choice","score","noul")` 不含注册表里的 `box`（`decision_points.py:370`/`:423`），因此 dp3 旗舰路径在生产中永远上抛人（21 个用例全绿是因为 stub 了 runner）。→ FIX-G。
- 2026-10-20 FIX-G done：`box` 可作答；PM 复跑 `test_decide_backends.py` **50 passed** + cli **61 passed**，真实 dp3 调用 `available=true`（fact 0.85, 6.4s）；同一 dp+key 重复调用不重复落档案（D-032 幂等，换唯一 key 后 `seq=3` 正常新增）。**新发现**：3a 要求答案带 `path:line` 引用，但 `state` ≤2000B 且不含文件内容，模型无法给出引用 → 3a 实际仍会 `unavailable` 上抛；待用户定取向（本地检索喂型号 / 放宽引用 / 先只跑 3c）。
- 2026-10-20 用户驳回两条前提：①「`sign-final.md` 要人手写」不在设计里，且质疑“我签收了什么”；②「jev 不可用」不接受——jev 有自己的专用端点（只做问答、不做生成），拿别的模型跑通不算。PM 核对官方 OpenAPI 后确认：`box` 是图像定位题、Jev 无自由文本题型、`score` 是浮点 → **FIX-G 方向错误**，派 FIX-H 撤销。
- 2026-10-20 FIX-H done + PM 追加：`decision.py` 新增 `REASON_BOX_REQUIRES_IMAGE` 并进 `REASON_CODES`（9 值），真实 CLI 探针 `reason="box-requires-image"`、零 HTTP、`acted=false`；四套件 **188 passed**（backends 58 / cli 61 / core+archive 69）。design.md 记 **D-046**（box 语义 + 浮点 score + 契约出处）。
- 2026-10-20 PM 对「jev 真不可用」的取证（全部实测，仓内零可修点）：① 本机无 typesafe 凭据（`~/.pi/agent/auth.json` 仅 `timi`/`zai-coding-cn`，env 无 `TYPESAFE_API_KEY`），裸连 `api.typesafe.ai` **403**（边缘拒绝，网络可达）；② timiai llmproxy 侧 `/v1/systemone`、`/systemone`、`/v1/decide` 等 20+ 路径全 **404**，`/v1/messages` 严格拒收 `state`/`questions`（400 `unknown_fields`），`/responses` 回 `Unmapped LLM provider for this endpoint`，`jev-latest` 在 `/v1/messages` **持续 429**（90s 复测仍 429）→ 统一鉴权路线不可行，B2 的 glm 只能算 stand-in。**结论：要么给 typesafe key 走 B3 `direct-systemone`，要么接受 stand-in 但不得称其为 jev。**
- 2026-10-20 用户追问“timi provider 是不是没实现 jev 的 api”：核实成立 —— `timi.ts` 21 行只有 `anthropic-messages`/`openai-responses`，`generate-models.ts:724-736` 把 jev-latest 声明为 anthropic-messages，所以调用被当聊天请求发出（必然 429）。→ FIX-K 补 `typesafe-systemone`（D-047）。
- 2026-10-20 用户裁定 “3a 要改成 choice/nuol” → FIX-I（Python 注册表/后端）+ FIX-J（TS 消费）并行，契约：`answer_kind`(choice) + `answerable`(noul) + `candidate`(choice，动态候选)；引用与文本一律本地取，模型不造句。
- 2026-10-20 FIX-I/J/K 三卡并行回收，PM 收口 FIX-I 的卡外缺口（`decision.py:_validate_input` 的 dynamic_choices、`_value_fits`/`_unusable_answer` 的渲染集合、三份测试 fixture），并发现 B2/B3 的 `noul` 契约分叉（B2 当布尔、B3 当概率）并统一为概率 0..1。全量 Python **2769 passed / 8 baseline failed**；TS `tsgo --noEmit` rc=0，五套件 **132 passed**。
- 2026-10-20 stand-in 端到端实测：`req-dp3-candidates.json` → `mw decide run --dp dp3-worker-clarify` 得 `answer_kind=fact` / `answerable=0.9` / `candidate=c3`（5996ms，`acted=false`）。**引擎仍是 glm-5.3-flashx，不是 jev**；用户要的“jev 真在做决策”仍卡在凭据/网关两扇门外。
- 2026-10-21 用户两条裁定：①决策流必须接 `timi/jev-latest`（不是 typesafe），`timi/glm-5.3-flashx` 从决策流里彻底移除（无 fallback、无备选），重读 `jev接入.md`；②要一个 `mw decide` 接口给人真跑 jev。PM 按文档实测：真入口是 `POST /v1/decisions`（裸 timi key），此前 404/429 全是打错路径（`/v1/systemone`、`/v1/messages`）。派 FIX-L（Python 传输收敛）+ FIX-N（`packages/ai` api）并行，两者互不重叠；FIX-M（`mw decide ask`）等 FIX-L 落地后才发（消费其 transport 常量）
- 2026-10-21 FIX-L/N 回收：决策流只剩 `timi-decisions`/`jev-latest`，glm 与 typesafe 代码路径、常量、旧 probe 行全部删除，旧配置值 fail loud 而非回退；`packages/ai` 侧 api 改名 `timi-decisions` 并改裸 key。PM 删掉两个过期 `typesafe-systemone.*` 文件（worker 写面外）后 `tsgo --noEmit` rc=0、6 passed
- 2026-10-21 FIX-M 回收：`mw decide ask` 落地（三列表格 + `--json` + 失败原样上抛 exit 2），`test_decide_cli.py` 从 29 errors 修到 41 passed。PM 用真 jev 实跑：200/1192ms，`noul 0.88`、`choice billing 0.97`、`score 1.01` —— **这是 jev 第一次真正在为本仓做决策**
- 2026-10-21 dp3 真往返暴露质量问题：`candidate=c3/c2` 置信 0.79~0.97 但 `answer_kind` 只有 0.13，低于 0.7 阈值 → 上抛。根因是注册表没有问题文本（payload 里是占位 instruction）→ 派 FIX-O 给 dp1/dp2/dp3/dp8 补 `instructions`/`labels`/`noul criteria`（第一版卡缺 `## 验收命令` 被派发门禁拒，重写结构后重派为 `ds-fix-o2`）；PM 同时修 `decision_backends.py:398` 过时 docstring
- 2026-10-21 FIX-O 回收后复测：`answer_kind` 置信 0.13 → 0.45~0.56，`candidate` 在「答案确实在材料里」的请求上以 0.97 选中正确文件；但 `answerable` 仅 0.11~0.40（state 只给文件名、不给内容），3a 按设计拒答上抛——行为正确，改进项记录为「候选条目带文件首行摘要」。另注：`mw.py:858` 把 `low-confidence`/`input-incomplete` 映射到 legacy `bad-response`（TS 侧已改用 `escalated_reason`，仅兼容用）

- 2026-10-21 用户裁定签收取向 = (a)+(b)，并追问「不 build 能不能生效」「真 jev 的测试用例长什么样」。PM 产出`evidence/runs/jev-live-20261021/`（run.py + 两例真实请求/响应 + transcript.md 九步链路 + 不 build 生效面表），顺手抓到并修复 `_choice_criteria` 重建丢失调用方 `criteria` 的真 bug（200-with-error 的成因），`test_decide_backends.py` 59 passed；派 FIX-P 实现 (a)+(b)
- 2026-10-21 FIX-P 回收（needs-clarification 仅因 CHANGELOG 不在 write_face 头）：PM 补 CHANGELOG、写 `decision-scope.md`、本仓 `decide set` + `dp refresh`（24 行，authority-change 入档）、跑一条真 jev 决策（seq 25，engine 三元组合格，`verdict continue: ok`）；done 门禁实测只报三条 sign-final 缺失（含新的 `decision_signoff`），签收后即可推进
- 2026-10-21 用户裁定签收入口进 `/mw`（方案 B：确认对话框 + `--human-confirmed` 豁免，接受 tamper-evidence 而非 tamper-proof），派 FIX-Q；worker 因 write_face 头漏项把等价逻辑落在 `mw.py`，PM 补 CHANGELOG 并实测：会话内无 flag 拒写、有 flag 写入且 `signed_via: tui`、档案 `by=signoff:continue`、临时 key 的门禁签收项全过；**仍待用户放行 `mw build --install`** 才能在 TUI 看到 `/mw decide`
- 2026-10-21 用户三问（DecisionClient 契约 / 全部 dp 说明 / 传给 jev 的上下文）→ 派 FIX-R（类型）+ D-CFG（注册表导出成固定配置）+ 4 个 research（dp 清单）；PM 写 `docs/decision-points.md`，§3 表格由 `decide_registry.json` 渲染；实测 dp1 triage 在两次派发上真跑（conf 1.00/0.83 与 1.00/0.92，`confidence_source=api`）
- 2026-10-21 用户四点（state 三形态/每 dp 必能解析并送 jev/配置要说明接入且字段不许缩写/64k+32k token 上限）→ W1-W4 四卡全落地；PM 跑 `dp verify --live` 证明 24 个 dp 都能真发到 jev 并被回答
- 2026-10-21 W6 终态 needs-clarification 的定性：ledger gaps: unrecorded write(s): shared/decide-registry.generated.ts 不是 worker 越界，而是该文件由 scripts/gen_decide_registry_ts.py 以脚本方式生成（不经 write 工具），台账没记到。PM 复跑 python scripts/gen_decide_registry_ts.py --check rc=0、	est_decide_registry_ts_lock.py 5 例通过，按脚本产物接受。
