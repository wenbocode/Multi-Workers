# R 历史读侧实现审查

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement全文。
- `packages/multi-workers/decision_history.py:1` 全模块；`packages/multi-workers/test_decision_history.py:1`；workers/dd-history-fold/report.md及evidence/runs/T07-history-fold/verify-summary.md/原始日志。
- T02c已独立PASS，原T07残留“复审未PASS”是旧时点。T05在产，T10新服务并行，均不修改history。

## 审计目标
完整读1588行history与23测试和实际archive/signoff/gate/schema接口。核查真实来源：authority human不是人、人工前缀身份是否可靠、sign/refresh/自动签收分列、采用不等消费执行、旧缺失unknown/inferred/pending；显式call/decision/submission关联不猜最近；opaque id/根归属/跨key/test隔离、恶意symlink/key或gate路径是否外根读取；坏行/半行/未知schema不崩溃；多源时间排序/authority dp级挂接是否误称决策授权。
特别旧archive/signoff/gate自由文本未经二次脱敏就as_dict输出：HTML转义不防凭证，spec所有正文/元数据/失败输出脱敏，实际known secret漏到API/DOM是具体缺陷；写侧历史无脱敏保证不能仅注释推责任。metadata缺失/剪裁不冒充原文/0。审明gate-only记录缺口对spec全历史覆盖、1588行23测试是否足够。准确核验RED是实际行为缺失还是skeleton自证、3变异覆盖什么、生产hash隔离是否测正确面。

## 要求
PASS/CHANGES_REQUIRED，P0/P1/P2给path:line/真实触发/AC-VC/后果/最小修复。只读，不跑外网/付费/服务/build；无shell时声明静态+旧日志，不自称实测。后续producer未接线不是自动扣分，但不安全输出契约必须报告。

## 未覆盖面声明
真实Jev/browser/HTTP消费者/T08/T09未实现，不声称全AC，未审T05/T10在产。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-history/**`

## 写入禁止面
- 所有代码/测试/档案/任务相位/其他worker。

## 交付格式
report≤180行，结论/Findings/证据/下游与未覆盖/上下文；摘要≤30行。
