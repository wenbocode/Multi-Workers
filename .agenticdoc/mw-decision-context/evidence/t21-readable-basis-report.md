# T21 人可读依据及 h-883f5768718d808aaea8 现场

## 已实施（源码，未部署）
- `decision_dashboard.js` 单写：默认依据解释记录来源及其证明范围；原始出处在关闭的「原始依据出处（按需查看）」中保留。未知来源不猜译；没有依据不补造。
- 对本次目标记录十节点及策略依据只读取证，**21/21 原始来源均有准确中文映射**，无未知来源占位。见 `t21-source-integrity.json`。这不代表21个事实或执行成功，只是21条来源说明。
- 行动为 `record / answer-returned` 时写「仅记录了模型返回，不代表 worker 已启动」。
- 仅当真实回执同时是 `rework / dispatch-refused` 时解释「派发被拒绝，需要处理派发阻塞；不代表模型答案被判错」。其它 reason 按原记录保留，不添加该记录未持久化的D003具体条件。
- 输入为空时继续保持业务材料视图，不加空依据占位。只有该输入实际带来源时才显示解释和关闭审计。
- 原始答案/动作/结果/时间不改；无生产ledger修复/回填，没有新增模型决策。

## 现场时间线（UTC 2026-10-23；北京时间对应10月24日01:17）
目标 decision_id: `dp1-dispatch-type:a489216a-d9a4-4f3c-a7d5-6fe41e5ca3ee`，key `mw-monitor-auto-restart`，task `monitor-restart-rq2-cli`。

| 时间 | 实际记录 | 含义 |
|---|---|---|
| 17:17:36.628 | lifecycle line14 record-start | PM发起类型判断 |
| 17:17:38.412 | line15 executed record / answer-returned | CLI记录了模型返回，不是worker运行 |
| 17:17:38.814 | line17 consumed research | PM收到了research答案 |
| 17:17:39.157 | line19 settled rework / dispatch-refused | 后续派发被拒绝，本轮未成功入队 |

本次存储的confidence **0.97**、min_confidence **0.7**；策略来源仍是建议路径，不拿超过阈值等同自动采纳或执行。

具体派发阻塞来自当时工具拒绝证据：卡未声明`写入允许面`、有1个同key worker在飞，D003守卫拒绝，Nothing was queued。RQ2 research卡只有唯一证据文件声明，不等于守卫可解析的write_face。另一key的pm-state明确保留RQ2未入队；只读 `list_tasks(scope=key)` 也只有RQ1 done/acked。PM后来直接源码调研，不改写这次拒绝或冒称RQ2 worker完成。

直接代码出处：
- `packages/multi-workers/mw.py:1257–1267`: run成功返回答案时写`executed action=record result=answer-returned`。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` `Dp1ConsumerStage` / `writeDp1Lifecycle` / `writeDp1DispatchFeedback:473–501`、派发失败分支:3368–3374：consumed只记接收；派发拒绝写settled rework/dispatch-refused，成功派发才写对应业务executed。
- 原卡 `.agenticdoc/mw-monitor-auto-restart/tasks/RQ2-cli.md`、该key的 `pm-state.md` 与历史拒绝工具结果（保留只读，不改其它key）。
- `t21-inspect-lifecycle.py` 仅输出闭集机器字段及时间；`t21-inspect-basis.py` 仅reader生成的来源/数字。均不读取本地凭证，不调用服务/模型。最初 `t21-inspect-record.py` 使用无redactor的公开读侧；selection被安全省略不能认定原始无答案。

## 验证及保留失败
- 新14项行为测试先RED **12F2P**，不是事后声称test-first；原始日志 `ui-recovery/t21-red-*`。
- GREEN首批：新14P、feedback10P、readable **1F43P**、contracts119P、startup11P。真实新回归是空input也出现依据占位；源码修复，不改旧测试。
- 新XSS断言后续加严为真正DOM快照 `pwned=False / imgCount=0`，不追认为初次RED的覆盖。
- GREEN2：新14P、readable44P、assets9P、playground13P；四文件exit0。
- 两批七个文件最新结果 **220P**，**不是同一连续全绿批次**。
- 额外workbench全文件 **16P1F**，`record_version`禁出现断言失败。基线/当前隔离对比各同一nodeid **1F**，均是该断言：T20已把detail.basis显示成原始文本，新T21仍在关闭审计内保留原文。该旧测试读取整个textContent而非默认可见文本，与本次默认中文/原始出处保留的约定未协调。未删原始出处去追绿、未修改卡外旧测试、**不称整个工作台测试通过**。证据 `t21-workbench-compare/{baseline,current}.stdout.log` / metadata；比较不修改原JS。
- 新测试覆盖key/role/dp/input/model/request/response/receipt/action来源、真实阈值来源、dispatch拒绝、未知/missing/XSS、非dispatch rework；shipped JS+合成实际writer/history→DOM，只有bootstrap POST及GET，storage0。实际用户浏览器未验收。
- 保护字节副本 **11,877 files** `npm run check`: **exit1 / 3warnings2infos**，同三处卡外mwoc TS文件；`formatter_changes=[] / original_changed_during_check=[]`，后续pinned/import/shrinkwrap/install-lock/tsgo/browser-smoke链未执行。完整日志 `t21-check/{stdout.log,stderr.log,metadata.json}`。

## 源码完整性与未覆盖面
- T21首写JS基线142930B SHA f7e2e19ee35eaa3e01ad2abf0c64d4585fddaae1f9b39d4650a93eaab5dbb90b。
- 现JS147903B SHA 2bca8a49b66702dc1d06493bee6d38be72b082b50713bb3875cd77d78f4cfd50，LF基线保持，差异仅7处卡内块（统一依据helper/调用点及两个准确结果说明），见 `t21-decision_dashboard.js.diff` / `t21-source-integrity.json`。
- 无共享monitor/serve起停、真实浏览器、模型/凭证发现、build/install/commit/框架/其它key/生产ledger操作。旧记录只读现场不改变历史。
- 下一步：协调旧workbench断言（默认可见文本与关闭审计分别验证）和三处卡外质量诊断；本key24AC/review、restart8AC与框架finalize许可、仅下拉case缺口仍未关闭。相位仍EXECUTE；本轮audit design/plan/tasks/execute PASS不是验收DONE。
