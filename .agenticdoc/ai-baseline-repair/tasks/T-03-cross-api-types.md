# T-03: cross-api-thinking-history 8 处类型面修复

> Key: ai-baseline-repair | 依赖: 无 | 模式: PM 直执 | AC refs: AC-003 | VC refs: VC-001, VC-006

## 目标

D-003：fork 特有文件（无上游参照）按当前类型面修复，断言语义不删。

## 逐处方案

| 行 | 错误 | 修法 |
|---|---|---|
| 80 | TS2741 Model fixture 缺 baseUrl | fixture 补 `baseUrl`（及其他当前必填字段，按 Model 类型核对） |
| 114 | TS2322 `"end_turn"` 非法 | 按断言语境换 `"stop"`/`"toolUse"` |
| 134 | TS2367 `type === "stop"` 无重叠 | 终止事件改 `type === "done"` |
| 136 | TS2339 `.messages` on never | 随 134 修（done 事件 payload = `.message`） |
| 160/170/230/235 | TS2352 ResponseInputItem → Record 强转 | 经 `as unknown` 或按 union 窄化后取值 |

## 验收

- [x] tsgo 该文件 8 错全消（全仓归零）
- [x] diff 审阅注记：无断言删除——仅补 baseUrl 字段、end_turn→stop、stop 事件→done（payload .message）、4 处 cast 经 unknown、never-窄化重拓宽；断言目标值不变（VC-006）
- [x] biome 零告警

## 验证状态

验收通过（2026-09-10）：tsgo exit 0；cross-api 测试随套件 838 passed 全绿（不再单独 skip）
