# Research: 决策工作台最小UI/API、单次DAG与四离线case (RQ-D3)

范围：只读设计研究。未改源码、未跑测试/服务/浏览器、未调用模型、未读真实凭证。
锁定需求 `.agenticdoc/mw-decision-context/spec.md` §1.5/§1.6/§2.2，AC-011~019。目标 `.agenticdoc/goal.md:1`。
下文「事实」=静态源码阅读；「建议」=未实现提案；无任何浏览器可见性或真机结论。

## 1. 事实（路径:行 + 符号）

| # | 事实 | 出处 |
|---|---|---|
| F1 | 独立 Chromium `--app=` 窗口，独立 profile，URL 为 `http://127.0.0.1:<port>/#boot=<一次性code>`；spawn 只证明进程启动，不证明窗口可见 | `decision_monitor.py:2549 window_url`、`:2586 build_chromium_argv`、`:2602 launch_app_window`、`:2569 detect_browser` |
| F2 | 仅监听 127.0.0.1；路由闭集三分角色 control/public/page；POST 需精确 Origin，Sec-Fetch-Site 闭集；body 256KiB；CSP `script-src 'self'`、`form-action 'none'`（不许内联脚本/内联事件属性/外部框架） | `decision_monitor.py:81 HOST`、`:90 BODY_LIMIT_BYTES`、`:113 SEC_FETCH_SITE_ALLOWED`、`:1314-1327 _match_route`、`:1455 require_origin`、`:1522 _security_headers`、`:118 _CSP` |
| F3 | 现有历史 API：`GET /api/history` 只收 key/dp/source/status/scope/limit/offset，未知参数 400；返回 records/total/filters/stats/warnings/redaction；`GET /api/history/<opaque>` 详情只认 `h-[0-9a-f]{20}` 句柄 | `decision_monitor.py:1596 _act_history`、`:1641 _act_history_detail`、`decision_history.py:186 OPAQUE_ID_PATTERN` |
| F4 | 历史折叠：`HistoryRecord` 已有 key/task/dp/status/stages/call_counts/usage/capture_status/calls/archive/gates/redaction；`status` 只有 pending/ok/rework/rollback/inconclusive/unknown，由 archive settle outcome 决定 | `decision_history.py:350 HistoryRecord`、`:158 STATUSES`、`:1892 _record_status` |
| F5 | 主表当前 13 列（时间/key-task/DP/类型/状态/来源/actor/answer_source/阶段/调用/usage/capture/详情），key 与 DP 是自由文本 input；详情是页面底部 `#detail-panel` 区块，非弹窗 | `decision_dashboard.html:20-58`、`decision_dashboard.js:318 renderRecordRow`、`:762 renderDetail` |
| F6 | 捕获对象逐字段标注 `byte_exact/redactions/truncated/read_capped/text_omitted/decode_errors`；attempt 行已含 `request`/`response` 与 `not_recorded`（request/response/http_status/latency/usage） | `decision_wire.py:330-372 Capture`、`decision_history.py:1360-1410 _fold_calls` |
| F7 | 输入 `book-snapshot` 事件本身带 `book`，但历史折叠只保留 book_ref/book_version，正文被丢弃 | `decision_wire.py:197 book-snapshot 字段`、`decision_history.py:1732-1746 _build_stages` |
| F8 | 发起角色无独立字段：`actor` 只有 `{kind: human/system/unknown, id}`；历史记录没有 role 字段 | `decision_wire.py:1085 _actor_of`、`decision_history.py:160 ACTOR_KINDS`、`:350 HistoryRecord` |
| F9 | `retry_of` 只存在于 submission-start/end；production decision 事件无通用 retry 字段，历史 payload 也不输出 retry 关联 | `decision_wire.py:194 submission-* 字段`、`decision_wire.py:147-197 _KIND_FIELDS`、`decision_history.py:350` |
| F10 | 测试页：scaffold/validate/submit/submission/history 均走 playground provider；history 列表把 request/response 正文替换为 `output_omitted:true`；submit 是唯一可达模型的路径 | `decision_playground.py:537 scaffold`、`:689 validate`、`:716 submit`、`:925 submission`、`:934 history`、`:957 _history_record` |
| F11 | 页面/API 三层分离已成立：静态资产免 token（`/`、`/app.css`、`/app.js`），page token 经一次性 boot code 换取；页面打开/切换/筛选零模型调用 | `decision_monitor.py:171-190 load_static_assets`、`:452 TokenStore`、`.agenticdoc/mw-decision-dashboard/evidence/runs/T11b-dp-test-closure/notes.md` §1/§3 |
| F12 | T11b 明确未验收：真实浏览器可见性、真实 Jev 端到端均「待接入」；DOM 跑的是 Node shim 回放，模型端是 loopback HTTP fixture | 同上 notes.md §5、`api-routes.txt` |

## 2. 两个方案（+1 个否决项）

**方案 A（推荐）原地扩展同一条读链**：在 `decision_history` 折叠结果上新增一个纯投影块 `workbench`（状态四值、业务摘要/答案、单次 DAG 十节点、retry 链接、facets），路由仍走 `/api/history*`；新增唯一只读路由 `GET /api/test/cases`；DOM 改成 5 列表格 + 详情弹窗（DAG 页签 / 日志结构页签）+ 测试页 4-case 选择器。

**方案 B 新开一层只读工作台 API**：新模块 `decision_workbench.py` + `/api/workbench/records`、`/api/workbench/records/<opaque>`、`/api/workbench/facets` + 新 `workbench.js` 资产与新面板，旧 `/api/history*` 与旧页面保持不动。

| | A 原地扩展 | B 新 API 层 |
|---|---|---|
| pros | 单一 reader/单一 redactor/单一 opaque 句柄与 token 角色；无第二写者；状态与 DAG 只有一份推导；改动集中在 4 个既有文件 + case 目录 | 与旧 dashboard 资产/DOM 契约解耦；新功能可独立失败回退；旧测试不改即可全绿 |
| cons | `decision_history.py`(108KB)/`dashboard.js`(77KB) 继续变胖；旧 DOM 断言（#filter-key 文本输入、13 列）必须有意更新；fold 每页多做一次投影 | 两套序列化必须各自过 known-secret/裁剪策略，容易一处漏脱敏；两套 status/DAG 推导必然漂移；新增路由/资产/测试面更大；读者要同时理解两条链路 |
| 结论 | 推荐 A：靠 `workbench` 投影函数隔离新增逻辑，风险低于复制一条读链 | 否决 |

**否决项 C**：浏览器端用现有 record 字段自行拼 DAG/状态。facets 在分页下不完整、客户端无 redactor、且属于「重建原文/推断链路」，直接违背 AC-013/016。

## 3. 推荐最小改动清单（方案 A）

| 面 | 改动 | 不动 |
|---|---|---|
| 读侧投影 | `decision_history._workbench_view(record, detail)`：`status_view`、`business`、`retry`、`dag`、`dag_available`；`HistoryPage` 增 `facets{keys,dps,truncated,basis}`（按当前 scope 从完整 snapshot 取，分页不影响） | 现有 `status` 字段保留，只进日志弹窗，不再当主状态 |
| 主表 | 列改为 key/task、问题或摘要、DP、选择结果、状态；key 与 DP 改 `<select>`（首项「全部」），状态下拉四值；保留分页/limit | 删除列≠删除字段：技术字段全在弹窗 |
| 详情 | `<dialog>`/等价覆盖层作为「决策详情」，内部两页签：单次 DAG（10 节点，可点节点）与日志结构（现有 summary/claims/stages/calls/usage/capture/archive/gates/redaction 原样搬入） | 不改 opaque 句柄、不加新详情路由 |
| 旧记录 | `dag_available=false` 时 DAG 页签显示「旧数据无状态，不展开 DAG」，`[data-testid=record-dag-open]` 渲染 0 个；日志结构仍可读 | 不按 key/时间补链 |
| 测试页 | 新增「离线 case」选择（仅 4 DP）+「载入 case」+「校验」+「显式观察提交」；载入=GET 只读，0 模型调用 | scaffold/validate/submit/retry 对 25 DP 全部保留 |
| 路由 | 仅加 `GET /api/test/cases`（page 角色，可选 `dp` 参数，闭集 4 个 id） | 不加写入路由、不加第二 sink |

## 4. 文本线框（静态设计稿，未在浏览器渲染）

```
┌ 决策工作台 ─ mw decide monitor ───────────────────────────── 127.0.0.1:PORT ┐
│ key ▾[全部|mw-decision-context|…]  dp ▾[全部|dp1…|dp2…|…]                  │
│ 状态 ▾[全部|处理中|处理完成|失败|旧数据无状态]  [刷新]  显示 1-50 / 共 N（快照）│
│ key / task          问题或摘要            DP          选择结果      状态      │
│ mw-decision-context dp2 检查点 4 选 1     dp2-check…  收窄任务      处理完成  │
│  T14 / (无 task)     自评：完成 3 剩余 2                 (narrow)   +已接收/已行动│
│ mw-old              dp1 三选一            dp1-disp…    coding      旧数据无状态│
└─────────────────────────────────────────────────────────────────────────────┘
```

```
┌ 决策详情 · dp2-checkpoint-split · h-3f9c… ──────────────────────── [关闭] ┐
│ 单次 DAG：[key] → [角色] → [dp] → [输入] → [decide处理] → [API请求]        │
│           → [决策模型] → [返回结果] → [接收签收] → [行动反馈]              │
│ 节点详情（API 请求 · attempt 1/2 · 未记录 attempt 2）：                    │
│   POST /v1/decisions · http_status=200 · capture=partial                  │
│   ```json  实际捕获正文（脱敏 3 处；truncated=false；byte_exact=false）    │
│   { … }                                                                   │
│   ```                                                                     │
├ 日志结构 ─────────────────────────────────────────────────────────────────┤
│ 来源/actor/answer_source/阶段/调用/usage/capture/脱敏/archive/gates（只读）│
└───────────────────────────────────────────────────────────────────────────┘
```

```
┌ DP 测试（观察隔离） ───────────────────────────────────────────────────────┐
│ [dp1 ▾][dp2 ▾][dp3 ▾][dp25 ▾]  [载入离线 case（只读文件，0 模型调用）]     │
│ 决策本（JSON，可编辑）：[ textarea ]   [校验（不发模型）]                 │
│ [显式观察提交（会真实调用模型一次）] [用新 id 重试上一次]                  │
│ 测试身份：scope=test · observe_only=true · 行动=模拟未执行                 │
│ 单次 DAG（同正式工作台）· 日志结构                                          │
└───────────────────────────────────────────────────────────────────────────┘
```

## 5. 新旧数据、缺失、零发送、脱敏的呈现规则

- 主状态四值映射（推导归 RQ2；UI 只渲染）：处理中=`in_progress`、处理完成=`completed`、失败=`failed`、旧数据无状态=`legacy_none`。旧 `status`（pending/ok/…）只在日志弹窗显示为「旧状态字段」。
- 「未记录」标签专用于 `null`/字段缺席；不补 0、不补空串、不按 key 猜。
- 零发送：`zero_call=true` 或 `actual_http_attempts=0` 时显式「本次未发送（zero_call）」；计数未采集显示「未记录（未采集调用台账）」，不显示 0。
- 脱敏/截断：capture `redactions>0` 或 `byte_exact=false` → 「脱敏 N 处」；`truncated` → 「截断」；`text_omitted` → 「正文被策略省略（不重建）」；`output_omitted`（测试历史列表）→ 「列表省略正文，详见单条提交」。
- 模型返回≠接收≠行动：返回节点有内容只说明模型返回；接收签收/行动反馈两节点在未记录对应事实时保持「未记录」，状态仍可是「处理中」。测试页行动节点固定「模拟（未执行）」，禁止出现「已签收/已执行」。
- 旧记录：只显示已有历史与日志；DAG 入口 0 个；不显示推断的角色/输入/接收。

## 6. 接口建议（字段名是提案，PM 与 RQ1/RQ2 对齐后定稿）

1. `record.workbench`（`HistoryRecord._payload` 增补，list 精简 / detail 全量）：
   - `status_view {state, label, basis[]}`；`basis` 只列真实来源（`archive.settle`/`ledger.*`/`signoff.write`）。
   - `business {question{text,basis:"registry:<dp>"}, summary{text,source}|null, answer{value,label,basis}|null}`；复用 archive `note/reason/answer`，无则不填。
   - `retry {prior_opaque, next_opaque[], basis}`；只从事件记录取，不按 key/时间匹配。
   - `dag {legacy:bool, nodes:[{id,label,state,basis,detail}]}`，10 节点固定顺序；`detail` 仅在 detail 视图带捕获正文。
   - `dag_available:bool`（list 视图；旧记录=false）。
   - 来源映射：1 key=`record.key`+task；2 角色=新记录字段（现仅有 actor.kind/id，需 RQ2 补 writer，否则「未记录」）；3 dp；4 输入=`book-snapshot.book` 投影（见下）；5 decide处理=decision_id/scope/transport；6 API请求=`calls[].attempts[].request`；7 决策模型=`calls[].model/transport/confidence/usage`；8 返回结果=`attempts[].response` + archive `answer`（分别标注来源）；9 接收签收=RQ2 事件；10 行动反馈=RQ2 事件 + signoff。
2. 读侧补 `book-snapshot.book` 投影（detail only，过 sanitizer 与脱敏/裁剪标记）；否则输入节点只能显示 book_ref/版本 + 「正文见请求捕获」。不重建、不美化摘要。
3. `HistoryPage.facets {keys[], dps[], truncated, basis:"snapshot"}`（当前 scope 内去重排序，截断显式标注）；`GET /api/history` 响应加该键，不新增 facets 路由。
4. `GET /api/test/cases[?dp=]`（page 角色，GET 同源，无写）：闭集 `CASE_IDS=(dp1-dispatch-type, dp2-checkpoint-split, dp3-worker-clarify, dp25-signoff-conclusion)`，文件固定映射 `packages/multi-workers/decide_cases/<dp>.json`（按 id 查表，不扫目录、不收路径）；返回 `{cases:[{dp,title,note,book,sha256,bytes}]}`。case 文件外壳 `{case_version,dp,title,note,book}`，**服务端只把 `book` 交给 validate/submit**，`note/title` 永不出现在 HTTP 载荷。
5. validate/submit 响应增 `book_sha256`（canonical JSON），用于证明「编辑后的内容就是发送的内容」；现有 `state_digest` 保留。
6. 事件协议不新增：DAG 只读 `decision_wire` 既有事件与 RQ2 定义的生命周期/反馈字段；节点 9/10 的名字/写入点由 RQ2 定，本文不自造 sink、kind 或第二写者。

## 7. 四份离线 case 内容草案（首批仅 4 份，不删其它 21 DP 能力）

生成方式：离线生成器（建议 `packages/multi-workers/scripts/build_decide_cases.py`，输入字面量表 + `decision_book.scaffold_book`）产出并提交 JSON；测试重跑生成器比对（drift guard）。字段名沿用 RQ1 定稿的新契约，`notes.evidence` 由生成器填真实来源，不手填旧审计模板。

```
dp1-dispatch-type  book.state（无 requested_type/risk，不预选）
  task_goal: "为 mw decide monitor 增加旧记录只读筛选，不重构页面"
  task_requirements: ["只读，不写 archive/signoff/authority", "不新增第二套事件协议", "不改其它 21 个 DP 契约"]
  task_deliverables: ["evidence/research/design-workbench-cases-20261022.md", "worker report.md"]
```

```
dp2-checkpoint-split  book.state（原文优先；仅明显异常才附机器计数）
  original_task: {goal:"旧记录只读筛选+四状态主表", requirements:[…], deliverables:[…]}
  self_eval: {completed:"status_view 投影与旧记录判定完成", remaining:"facets 下拉未接",
              blockers:"DP 角色字段无 writer", attempted:"改过 2 版 DAG 映射",
              elapsed_minutes:35, remaining_minutes:25}
  anomaly: {writes:4, uniq_targets:2, repeat_top:1}   # 明显异常才附，非固定指标
```

```
dp3-worker-clarify  book.state（先有问题，再有候选；Jev 不生成文本）
  question: "旧记录详情里能否展示该 key 已有的 signoff 记录来佐证状态？"
  background: {task_goal:"…", current_state:"详情弹窗已列日志结构，无 signoff 摘录",
               why_decision:"是否展示影响用户对旧数据的解读", constraints_impact:"只读、不得推断链路"}
  candidates: [{id:"A", action:"展示已有 signoff 记录（只读）", explanation:"事实可查，不改写"},
               {id:"B", action:"不展示，标未记录", explanation:"最保守，零推断"}]
```

```
dp25-signoff-conclusion  book.state（已验证/未验证分列，不以计数代替证据）
  delivery_goal: "AC-011~016 在工作台可用"
  acceptance: ["四状态主表", "单次 DAG 十节点", "旧记录无 DAG", "重试精确关联"]
  completed: ["workbench 投影", "facets 下拉", "旧记录判定", "四 case 载入/校验"]
  evidence: {verified:["test_decision_history 投影用例"], unverified:["真实浏览器可见性","真实 Jev 选择"]}
  open_items: [{item:"dp25 签收写失败展示", impact:"需 RQ2 的失败码与重试幂等结论"}]
```

## 8. 生产/观察隔离与下游认领

- 隔离：上述全部为读侧投影 + 现有 page token；测试记录仍 scope=test、observe_only=true，不写 production archive/signoff/triage，不调模型（除显式提交）；测试 DAG 行动节点固定「模拟（未执行）」。
- 下游认领（writer/reader/测试）：

| 变更 | writer | reader | 测试边界/验证层 |
|---|---|---|---|
| `workbench` 投影、facets | `decision_history` fold | `/api/history*`、主表/弹窗 | `test_decision_history.py`（L1）；`test_decision_dashboard_assets.py` DOM shim（L2） |
| `book-snapshot.book` 投影 | 同上（只读 event） | 输入节点 | 同上（L1/L2） |
| `/api/test/cases` + case 文件 | 离线生成器（提交 JSON） | 测试页 | `test_decision_dashboard_playground.py`（L1/L2/L3 loopback） |
| 编辑→载荷证明 `book_sha256` | validate/submit 响应 | 测试页/测试 | `test_decision_dashboard_playground.py`（L3 真实 HTTP 载荷断言） |
| 角色/接收/行动/重试/四状态推导 | RQ2 producers/events | DAG 节点 2/9/10、状态列 | 归 RQ2；未接线前 UI 必须显示「未记录」 |
| 四 DP 新契约字段/选项标签 | RQ1 registry/producers | case 文件、主表「问题」列 | `test_decision_dashboard_contracts.py`、`test_decision_points.py` |

- 验证层分列：L1 Python fold/unit、L2 Node DOM shim 回放、L3 loopback HTTP fixture（真实 `TimiDecisionsBackend`）、L4 真实 Chromium 窗口、L5 真实 Jev。本轮只做静态设计；L1–L5 **均未执行**。局部绿不累计成 AC 完成。
- 需同步更新的既有 DOM 断言（有意变更，非回归）：`test_decision_dashboard_assets.py:881-889` 的 `#filter-key/#filter-dp` setValue 场景需改为 select 选择，且 shim 需支持 select 动作；详情从 `#detail-panel` 区块改弹窗时保留 `#detail-body`/`#detail-close` 句柄或同步改断言。

## 9. 未决与风险

1. 角色、接收签收、行动反馈、retry 关联当前都没有可读字段（F8/F9）；若 RQ2 不补 writer，AC-012/014 只能显示「未记录」，DAG 十节点是空壳。
2. 四状态来自 RQ2 的推导；「处理完成」= 单次决策处理结束还是 key 结束，UI 不自行判断。
3. 输入节点正文被历史折叠丢弃（F7），需读侧投影；若 PM 决定不做，则输入节点降级为 book_ref/版本。
4. 「问题或摘要」在记录里没有业务文本；当前只能显示 registry 固定问题 + archive note/reason，是否要求 producer 写摘要需 PM 决策（会扩大 RQ1/RQ2 字段面）。
5. case 可直接校验取决于 RQ1 新契约最终字段与 `check_book` 规则；生成器需在其落地后重跑，4/4 validate 是目标不是既成事实。
6. facets 从完整 snapshot 计算，无性能 SLA（spec §2.3）；大项目下需实测再定上限，不预先引入字节/条数上限。
7. 真实浏览器窗口与真实 Jev 未验证；T11b notes §5 的「待接入」不得被本轮文本线框改写为已验收。
