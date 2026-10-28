# T11b DP观察测试功能闭环

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；本key spec.md AC004/008/010/011/012/017、design.md双页签观察流程。
- `packages/multi-workers/decision_playground.py:1` DecisionPlayground；`decision_monitor.py:1846` MonitorDeps/provider，按实际漂移定位；decision_dashboard.js:1 已交付历史UI。
- T06 report全文与T11a/T12a合并PASS report全文。T06 34P/274+skip，RED仅collection module absent不是行为RED；T11a历史已交付不破坏。
- 当前T08a仅mw/newtest，禁止本卡改mw；本卡独占monitor/assets和playground最小结果持久化，不与T08a争面。T06已终态ack。

## 要求
一次交付浏览器DP测试完整流程：GET /api/dps选择全部25DP，显示typed required/optional及预算/关闭/P0状态，scaffold book编辑、显式validate、显式人工observe submit、状态/独立test历史/详情/retry新id。沿用token内存/textContent/CSP，切页加载仅元数据和记录，不自动validate/凭证发现或模型发送。只有明确按钮提交会模型请求，不执行/排队/授权/生产记录写入。
合并monitor最小接线：MonitorDeps默认按control_root惰性唯一创建DecisionPlayground，不在import/看历史时解析auth；测试保留可注入provider。不创建多实例破坏busy/去重。provider busy映射409而非200，UI显式解释；rejected/unavailable/failed/record-failed诚实，不将HTTP200当成功。页面validate展示context_sent=false，不声称context原文发送。
提交当次回复与实际请求返回安全展示，submission id/call id/book ref精确关联，不猜最近call。T06答案目前不持久：只在playground允许的submission-end内保存经当次冻结known redactor安全化的结果投影与显式关联，使轮询/重开详情能读到当次答案；raw敏感字段不得另存。若不能在本写面安全实现报告精确阻塞不要伪造。保留wire/evidence单写者，calls/lifecycle额外命名属集中债不复制索引。
历史stats/warnings顺手显式展示（review非阻塞，不做大重构）。保留历史9场景，DP测试全部25契约遍历，未知/typed/夹带/secret/全局disabled/预算零发送，重复提交零增call、retry新id、busy409、失败不伪成功、start失败零调用、executor0/生产账字节不变。
先真实正确行为RED，再实现GREEN。完整分页读被编辑文件及依赖。真实loopback monitor+真实provider+本地HTTP backend fixture验证POST/attempt/capture/答案显式关联，Node DOM回放同测试捕获JSON；不以stub provider全绿代替联合链路。真实browser/Jev仍未授权，禁凭证访问工具，tmpHOME/auth/env隔离与读前spy。

## 写入允许面
- `packages/multi-workers/decision_monitor.py`（provider注入/409必要响应接线）
- `packages/multi-workers/decision_dashboard.html`
- `packages/multi-workers/decision_dashboard.js`
- `packages/multi-workers/decision_dashboard.css`
- `packages/multi-workers/decision_playground.py`（仅submission-end安全结果投影及明确id持久化，不改门/快照/发送流程）
- `packages/multi-workers/test_decision_dashboard_playground.py`（新联合HTTP/DOM测试）
- `.agenticdoc/mw-decision-dashboard/workers/dd-dp-test-closure/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T11b-*`

## 写入禁止面
mw/decision/points/book/wire/backends/既有测试/TS/生产凭证账本/依赖锁/dist/任务相位。

## 验收命令
包目录 `python -m pytest test_decision_dashboard_playground.py test_decision_playground.py test_decision_dashboard_assets.py test_decision_monitor.py -q`，真实loopback+Node DOM具名断言；root严格只读biome/check子步全日志。完整argv/cwd/UTC/exit/hash，明确非整跑npm check，禁全suite/build/commit/真实browser/Jev/共享serve。

## 改动历史
- PM吸收T06，按功能闭环合并provider注入、busy409、DP页签、必要安全结果记录，避免碎片任务。T08a独占mw并行。

## 交付格式
report最多140行，RED/GREEN/25DP/真实POST与业务执行0/生产hash/缺失诚实/UI HTTP+DOM边界/API/剩余阻塞，不能自报真实浏览器或整体17AC完成。
