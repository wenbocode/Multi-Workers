# R metadata键安全窄复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/016，design §9。
- `packages/multi-workers/decision_wire.py:829` _sanitize_metadata/_sanitize_mapping（函数定位）；`packages/multi-workers/decision_backends.py:268` _usage_from_body只读。
- workers/dd-review-foundation-fixes/report.md N-1/N-2；workers/dd-metadata-key-safety/report.md、evidence/runs/T02c-metadata-key-safety/verify-summary.md及日志/更正。

## 审计目标
独立确认N-1关闭：任意usage/policy键及嵌套容器、长键clip边界、无redactor、非字符串键、secret标签/脱敏碰撞/撞计数标签均不得泄漏已知凭证或覆盖成伪造计数。读取完整store与两安全测试、真实HTTP新增测试的响应/扫账/evidence是否真能命中旧缺陷；原call/attempt/scope/64KiB/depth契约不退化。304/113/25在档数字与实数、tsgo具名退出码/更正文件核实。聚焦本次diff行为，不重复提出已闭合原5严重项、也不把缺失metadata读成上游没给。

## 要求
PASS/CHANGES_REQUIRED，N-1关闭表；新增严重项给实际触发/path:line/AC/最小修复。无shell时明确静态核对旧日志不是自己实测。T07并行新history模块不在写审计面，不以缺后续生产者扣分。

## 未覆盖面声明
真实Jev/UI/跨进程/真实提权/全仓check未绿保留，不声称全AC。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-metadata-keys/**`

## 写入禁止面
- 所有源/测试/任务相位/生产记录/其他worker。

## 交付格式
report≤120行，结论/发现与关闭依据/证据核对/下游残留/上下文及未覆盖，摘要≤20行。
