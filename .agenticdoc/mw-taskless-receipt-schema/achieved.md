# mw-taskless-receipt-schema

## 系统行为变化

`decision_receipt` 接受省略 `task_after` 或提供 `null`，两种都以无任务观察交给生命周期写入器。真实对象继续要求裁决绑定任务并通过已有观察检查。

RenderPerformance 的质量报告记录了正式 `dp-QG` PASS。失败的回执都提供了任务对象，而裁决未绑定任务。本机上一版编译产物的 schema 枚举 `decision_id` 与 `stage` 为顶层必填字段，本次增加了会话无法省略字段时的空值用法。

## 验收

AC-001 与 AC-002 通过窗口工具回归。测试读取注册后的序列化 schema，核对省略、空值和真实任务对象在运行时分别怎么处理，并核对写入器的原事件标识及新增模型请求数。完整 `npm run check` 在隔离副本通过。[验收记录](evidence/codex-pm/self/1795481955712030200-azv18871/result.json)

## 遗留

生产回执由持有裁决绑定的窗口接续。此次没有修改 RenderPerformance，也没有重问 QG 或推进该项目阶段。窗口重载会重建内存中的裁决绑定。
