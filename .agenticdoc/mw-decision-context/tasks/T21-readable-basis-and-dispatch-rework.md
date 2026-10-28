# T21 人可读依据与派发拒绝现场说明

## 上下文
- goal.md: `.agenticdoc/goal.md`，协作决策可追踪但不补造成功。
- 用户要求默认依据好理解，并还原 h-883f5768718d808aaea8 接收后 rework 的原因。
- 已只读还原：对应 dp1 / monitor-restart-rq2-cli，research0.97，记录阈值0.7；lifecycle:15 executed record/answer-returned、:17 consumed research、:19 settled rework/dispatch-refused。当时RQ2卡缺写入允许面且同key有在飞worker，未queued。
- 源码：packages/multi-workers/mw.py:1257–1267（answer-returned仅CLI记录动作）；packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:490–500（拒绝派发settled rework）、:3362–3387（dispatch失败分支）。历史卡 .agenticdoc/mw-monitor-auto-restart/tasks/RQ2-cli.md、pm-state.md 只读。

## 要求
- 默认依据解释“记录来源及证明范围”；原始来源字符串保留在关闭的审计详情，不把技术token当业务结论。
- 未识别依据不猜译；没有依据诚实未记录。建议/接收/record answer-returned不等业务执行或worker启动。
- 对已存 rework+dispatch-refused 给简短准确中文；不将具体D003条件补写到回执（该回执未持久化这些具体条件）。
- 先行为RED，后源码；实际记录只读；默认无真实凭证读取、决策API、共享服务/browser/build/install/commit操作。
- 并行分析：现场来源/DOM来源可只读并行，但worker会触发自动dp1，PM直接读取；JS单写+共享DOM测试串行。无worker派发。

## 写入允许面
- packages/multi-workers/decision_dashboard.js
- packages/multi-workers/test_decision_history_basis_ui.py
- 本key tasks/T21-readable-basis-and-dispatch-rework.md、evidence/t21-*、pm-state.md

## 写入禁止面
- 其它源码/旧测试/framework/config/任何生产历史/共享运行状态/凭证、其它key写入、外来dirty变更。

## 验收命令
- 隔离HOME/凭证环境，仅指定新DOM回归及既有readable/feedback/startup/history/contracts测试。
- npm run check 用字节保护副本，卡外诊断不擅修；保留原始日志。

## 交付格式
- 可读依据映射/unknown与missing/closed audit/XSS/0POST和0storage证据；现场时间线+直接出处；源码字节基线与未覆盖面。

## 改动历史
- 已还原现场并答复用户；单写JS与新14项DOM回归。RED12F2P→新14P，input空依据回归修源码。七文件最新220P，workbench16P1F（基线/当前隔离同一旧record_version断言均1F），卡外旧断言未改；保护check仍3warnings2infos exit1、无source/formatter变化。报告 evidence/t21-readable-basis-report.md，源码7处差异/LF保持，实际目标21条来源全映射。未部署、未整体验收DONE。
