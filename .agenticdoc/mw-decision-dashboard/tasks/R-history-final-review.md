# R T07d 最终输出契约复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/016/design §9。
- `packages/multi-workers/decision_history.py:1` Snapshot/page/_output_filters/_scrub_output；`decision_monitor.py:1894` 默认load_history注入self.redactor/:1630 dict(page.filters)。
- workers/dd-history-final-contract/report.md全文与evidence/runs/T07d-history-final-contract/verify-summary.md、RED/import proof/GREEN/probe/diff/依赖hash；workers/dd-review-history-output/report.md原2P2/2P3。
- 框架status lost但PM查原PID81496同创建时点仍活，trace在reconcile06:18:21后仍写/heartbeat；不可当退出/崩溃，不新派代码写者，本审只读。并行变化须对照工件hash，不假称稳定HEAD。

## 审计目标
逐2P2/2P3关闭，filters全部known-secret输出omit+标记且原值筛选，page完整secret0/no callback诚实；invalid filter errors不echo；capture stored status/hash/len与output_omitted/byte_exact层次明确，UI需哪些新字段不误读；空键计数/raw属性契约。
RED6基线未修+最终测试/hash/import proof与实现前时序核对（不要仅副本回放替代实现前RED），213+1skip/342+1skip静态日志真实性。发现偏差明确。
报告称monitor未注入redactor与实际默认MonitorDeps.load_history:1894不符，须纠正：自定义history_loader替代可能不给回调与默认分开。filters_withheld/basis未转发确实，判具体UI诚实缺口与最小下游接线，不直接冒称secret泄漏。
只读允许安全无命令；必要源/test全文分页，不外网/真实Jev/服务/build/模型/源改。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-history-final/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告/真实生产/其他worker。

## 要求
PASS/CHANGES_REQUIRED，path:line/trigger/severity/minfix；原worker可能继续写仅读快照，风险明示，静态旧日志非本人重跑。不能直接恢复worker状态或kill。

## 未覆盖面声明
真实HTTP/browser/跨平台/真实secret/全仓check/进程失联根因不在审查闭合范围。

## 交付格式
report≤120行，关闭表/新finding/证据偏差/monitor接缝纠正/未覆盖，摘要≤25行。
