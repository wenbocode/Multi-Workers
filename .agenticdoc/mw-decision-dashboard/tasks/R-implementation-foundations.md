# R 实现基础独立审查 T01 T02

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec `.agenticdoc/mw-decision-dashboard/spec.md:1`；design.md与evidence-requirement.md。
- 审代码 `packages/multi-workers/decision_wire.py:1`、`mw_common.py:2388`及T01/T02新增实现/专项测试（完整读）；两个worker report/verify-summary。

## 审计目标
独立审查真实实现符合设计/安全/并发/根隔离/TDD证据。重点：所有字符串元数据是否脱敏（report承认metadata secret前缀风险）、read cap固定尾窗对任意secret长/UTF8/latin1安全、行缩减hash/length一致、test sink symlink/realpath隔离、事件unknown keys丢弃与CLI闭集界区别、scope错误熔断是否仅警告一次却继续逐行等锁、owner锁恢复API可实施、默认根目标歧义、deadline实际测试充分性。模块约1500行是否有重复/不必要抽象或单调用helper（项目规则）；不给仅风格泛论。确认缺陷给path:line/触发/AC-VC/最小修正，PASS或CHANGES_REQUIRED。

## 要求
只读review，不改实现/测试/卡/文档，不运行付费网络/构建/服务；可读现有测试证据，必要只读命令。T03会改decision.py/backend，不与其写入争用。不得因后续未接线当本切片缺陷，但下游危险契约需指出。

## 未覆盖面声明
列完整已读与未覆盖面，真实HTTP/窗口/Jev未验不宣称达成。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-foundations/**`

## 写入禁止面
- 所有源/测试/其他任务与文档/配置/档案。

## 交付格式
report.md≤200行，P0/P1/P2精确证据、各项设计映射、未覆盖，最终摘要≤30行；不写外部evidence。
