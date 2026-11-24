# mw-dp-receipt-continuation

## 系统行为变化

- T-01 pi PM 回执入口把字段解析交给宿主。参数有错时返回一个含责任方、字段和动作的 `next`，可辨认的原事件继续传递。
- T-02 现任 PM 从本项目账本核对原 key、创建事实、已接受的正式裁决和事件，恢复回执绑定。项目、key、角色或事件冲突时拒绝写入。账本仍由原生命周期写入器维护。
- T-03 确认无写入的字段拒绝使用写入器的诊断。效果未知先按原事件查询。首次无进展计零，原样重交不增加计数，连续三次无进展暂停该回执，纠正后可继续。

## 验收

Codex PM 在最终源码上运行了 84 项窗口和 158 项 Python 定向回归，一项跳过。完整 `npm run check` 在隔离副本通过。原 RenderPerformance PASS 通过三个不同 PM 认领完成隔离回放，依次得到拒绝、写入和重复。原正式裁决数保持一条，原事件只有一条执行回执。[定向验收](evidence/codex-pm/self/1795488382623016700-jxup09fo/result.json) [隔离回放](evidence/render-receipt-replay.json)

## 遗留

源码已验收。全局发布和 RenderPerformance 生产窗口的续接待进行。
