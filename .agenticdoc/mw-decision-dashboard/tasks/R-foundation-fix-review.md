# R 基础安全修复复审与联合证据核查

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement全文。
- `packages/multi-workers/decision_wire.py:225` scrub_tail_prefix、build_event/sanitize/append_event；`packages/multi-workers/mw_common.py:2808` lock_owner_state（实际行号按函数）。
- 完整读workers/dd-review-foundations/report.md、workers/dd-foundation-fixes/report.md及evidence/runs/T02b-foundation-fixes/verify-summary.md与原始RED/GREEN/650邻接日志；T03 report/review。

## 审计目标
逐一独立判定原P0-1/P1-1..4/P2-1/2/3/5 closed或open；读全基础模块与两专项测试，mw_common全部被改探针/锁/根段及旧_is_alive调用方。确认长secret三截断点与短尾/UTF8/latin1完整安全、锁失败停止等锁、realpath/evidence隔离、ACCESS_DENIED unknown且不改变历史布尔语义。
特别对sanitizer边界做反例：usage/policy任意mapping的键可能含实际secret，不是声明式schema标签；book_ref/header_names/id豁免是否有生产者闭集验证/可信来源，不能仅注释就保证无凭证。所有metadata字符串截断若不标识是否违反实际记录真实性；缺回调enum/error_class/source是否误omit。只提具体可触发问题，不为1字符通用安全剪裁泛扣泄漏。
核查177/118/650证据命令与实数及T03 23/33报告差异、旧时点/并行变更是否破坏证据可信度；联合回归包含实际传输API更改。可运行限定本地pytest（无外网），若无工具明确纯静态/在档日志来源，不能声称自己实测。

## 要求
只读审查，无源/测试/生产记录修改，不build/模型/外网/共享服务。PASS必须原5严重finding全关闭且无新增P0/P1；不能依赖worker自报“全部修复”。新P0/P1精确path:line/触发/后果/AC-VC/最小修复；P2分阻塞/下游契约。

## 未覆盖面声明
真实跨完整性Win32 ACCESS_DENIED、真实Linux EPERM、Jev、Windows junction/锁尾延迟/monitor尚未平台实测，明确不冒充通过。静态review不是全AC证明。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-foundation-fixes/**`

## 写入禁止面
- 所有代码/测试/配置/任务/相位/档案/其他worker。

## 交付格式
report≤180行，finding关闭表、结论PASS/CHANGES_REQUIRED、证据与新问题、剩余下游/平台欠项、上下文及未覆盖。摘要≤30行。
