# PM State: mw-dispatch-flow-fixes

## Section 1: Snapshot
- Key: mw-dispatch-flow-fixes
- Claim-Id: —
- Phase: DONE
- Updated: 2026-09-09 23:53
- Completed: 2026-09-09 23:53

## Section 2: Execution Log
- 2026-09-07 spec 草稿完成（立 key 窗口），research 留底 spec-run-artifacts-2026-09-07.md
- 2026-09-07 20:18 本窗口接手需求澄清：三个决策落定（全局默认 pi / 显式 claude 失败不降级 / mw_common 检测复用边界），AC-006~008 改写、AC-009 新增、§1/§2/§4/§5 同步，research 留底 spec-routing-decisions-2026-09-07.md
- 2026-09-07 20:35 澄清第二轮：决策 6/7（gate 仅评有未入队任务的 key / 播报单通道化），AC-010/011 新增，缺陷④入范围，research 留底 spec-docgate-summary-2026-09-07.md；为 agent-team-loop、mw-dispatch-reliability 补零调研声明 note（数据维护，消 gate 噪音）
- 2026-09-07 20:42 澄清第三轮：决策 7 修订——播报仅覆盖本窗口认领 key 的相关 worker（弃单一可更新播报面），AC-011 改写，research note 补修订记录
- 2026-09-07 20:43 用户确认 spec（Step 5 通过）→ AC 锁定（11 条）→ advance_phase design，进入 system-design 工作流
- 2026-09-07 20:58 design 调研完成（根因定位：update_index claim 不降级 + activeKey find-first + _index.md 分歧；留底 design-owner-key-root-cause / design-heartbeat-and-gate 两份）；design.md 生成（D-001~D-007、17 条 VC、AC→VC 覆盖 100%、mermaid 门禁 PASS）
- 2026-09-08 10:38 设计审核轮（用户两问）：确认心跳纯代码输出（非 LLM）；追加 D-008 心跳消费面（widget 活 monitor + 终态摘要统计），spec 追加 AC-012/013（编号顺延），VC-018/019，mermaid 门禁复检 PASS、覆盖复检 13/13
- 2026-09-08 10:52 设计确认（用户）：KDR A 章（D001~D008）、evidence-requirement.md（指纹 e02e3192ee50）写入；advance_phase plan；plan.md（S1~S5，5 stage）+ tasks/（T-01~T-11，全部含 ac_refs/vc_refs）生成；待用户确认后 advance execute 开始执行
- 2026-09-08 11:0x-12:31 执行 S1~S5：T-01~T-09 代码+测试全部一次通过（定向 vitest 60→61、pytest 8→11 新用例；T-03 框架 push d33e777）；T-10 全量回归（agent-team-loop 61/61 in-suite、python 112 passed、check 本 key 零错误；仓库其余失败均为环境性/他会话在途 ai models 改动，零交集）
- 2026-09-08 12:31 bundle 重建安装（doctor stale=False）；12:33 L2 阻塞（AC-008 字面落点 goal-autopilot 被 docs gate 拦截 + 存活窗口持有）→ 用户决策 9：改当前窗口认领 key 重放；spec/evidence-requirement/design 三处同步修订
- 2026-09-08 14:25-14:33 L2 实跑 PASS（VC-012 三项：落点 mw-dispatch-flow-fixes/workers/、14 心跳全间隔 30.0s≤60s、pi/timi 默认路由零人工干预；附 doctor worker_liveness alive 现场）；评审 worker 反馈处理（AC-001 精度修订、design §0/VC-012 同步、AC-005/008 注记）；evidence/runs/l2-rerun-2026-09-08.md 留底；advance verify
- 2026-09-08 15:05 quality-gate 全量：47 问题（13 Q-AC + 19 Q-VC + 11 Q-COV + 4 交叉）→ 46 充分 / 0 未通过 / 1 ⚠️（W-1：仓库整体 check 红为环境性/他会话在途改动，本 key 零交集零错误）；指纹重算为规范口径 95d6a253ba12；报告 evidence/quality-gate-report-2026-09-08.md；结论 ⚠️ 有条件通过，待用户确认 W-1 后可 done
- 2026-09-08 15:1x W-1 归因修正：复检确认 580 错误全部在 HEAD 已提交文件（579 test/examples 模型 ID 陈旧 + 1 src github-copilot.ts），与两会话未提交改动无关；报告已更新
- 2026-09-08 15:2x 用户三点反馈：①底部状态条不刷新（根因：旧 bundle 无每-tick 重绘——HEAD 的 startWorkerPollLoop(pi, workerStore) 无 widget 逻辑，系本会话未提交代码；修法=重装 bundle+重启窗口）②成果需自动回读（用户决策→AC-014 append）③全部并入本 key → T-12/T-13/T-14 + S6
- 2026-09-08 15:3x code-review-1 worker 派发（type: review，pi/timi，读 patch.diff 132KB/3058 行）：M1/M2/M3/M4 + m1-m4 + n1-n4 全清单产出，无 blocker；三条 clean-area 确认（additive-only、路由、gate 作用域）
- 2026-09-08 16:3x-17:5x S6 执行：T-12 八项修复（原子 claim 原语/restoreWatch 静默重绑/Z 后缀归一/gate 槽不烧/pm-key new 走 takeover/poll 句柄清理/删死代码/文档措辞）；T-13 框架对齐（host:pid claim ID + .mw/index.lock 共享锁 + Windows 死 pid 用 OpenProcess+GetExitCodeProcess 判定——实测 os.kill(pid,0) 对已终止 pid 仍成功）；T-14 终态自动回读（readOutputBody 全文注入，20k 截断指路）。回归：vitest 66/66（+5 新）、pytest 116（+4 新）、check 本 key 0 错误（全仓 580 与基线一致）；指纹重算 9c90fbb3e171（14 AC）；bundle 重建安装；框架仓提交推送
- 2026-09-09 用户验证反馈两项缺陷：①终态 summary 只显示不推进（dispatch→monitor 后中断，无 finish call→pm run 环节）②trace.log 只能测活无中间进度/状态/报错，worker.log 无内容 → 立项为 AC-015/AC-016 append（编号顺延），design 追加 D-010/D-011
- 2026-09-09 12:0x 执行 S7（AC-015/016）：①根因定位：displaySummary 无 triggerTurn → agent 空闲时消息只入栈不升 turn；worker.log 空因 agent_settled 内 process.exit(0) 截断 print-mode 待刷新输出②实现：deliverWorkerResult（sendMessage+triggerTurn+PM 循环指引）；worker-mode 成功路径不再 exit（print-mode 自然输出/退出），失败/超时保留 exit(1)+fs.writeSync(1) 状态行；trace 新增 [START]/[PHASE]/[TOOL]/[TOOL_ERR]/[TIMEOUT]/[ERROR]/[END] 行（时长由 [START]/[END] 承载，[HEARTBEAT] 格式不动）；readTaskProgress 统一解析，widget 运行行加 up elapsed + 最近 [TOOL] 动作，终态摘要时长优先 [START]→[END] 精确区间（队列行时间兜底）③回归：agent-team-loop vitest 73/73（+7 新）、check 本 key 0 错误（全仓 580 与基线一致，零交集）、biome 本 key 干净；bundle 重建安装（activate self-check OK）
- 2026-09-09 14:4x 方案 A 执行与复验（用户确认）：①`npm --prefix packages/coding-agent run build` 重建 dist（14:43，新代码含 finishSuccess/无 exitWithSuccess + ACTIVATION_FLAG 防护）②烟测 smoke-ac016b：task.md 落盘 → after-turn 扫描派发 → 项目级队列 → Python spawn → done 全链路 PASS；**worker.log 三段俱全（start/done 状态行 + 最终回复 SMOKE-OK-AC016B）—— AC-016 实机验证通过**；trace.log [START]/[END] elapsed=12s③裸 `pi -p` 4.1s 自然退出（原挂死）—— stale built-in 污染消除④附带发现：运行中 mw serve（8-28 启动）携带 9-5 前旧 launcher，任务体仍整体经 argv 进 `-p`（会话文件证实，worker 0 工具即答）；建议择机重启 serve 加载新 launcher（mw.py/mw_common.py 有另一会话未提交改动，需用户确认时机）⑤烟测脚本误写的 key 级队列行无人读取（WorkerStore 恒用项目根），已持锁清空⑥证据：evidence/runs/smoke-ac015-ac016-2026-09-09.md 更新
- 2026-09-09 21:05: 恢复复验轮（Round 3）：事故后会话日志重放恢复、bundle 字节一致、vitest 90/90、pytest 全绿、audit PASS、AC-016 dist 重建等价复验；achieved.md 落盘，advance done 收口
