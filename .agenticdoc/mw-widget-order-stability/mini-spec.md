# Mini-Spec: mw-widget-order-stability

> Key: mw-widget-order-stability
> 创建时间: 2026-10-14
> 类型: trivial-fix 快路径（实施准入门禁放行件）
> 状态: draft

## 问题（现象 + 根因，带 file:line）

同一窗口同时存在 autopilot monitor 面板与 mw-watch 进度面板时，两者的上下位置每次都变。

根因在 pi core 的 `setExtensionWidget`：`packages/coding-agent/src/modes/interactive/interactive-mode.ts:2096-2132`

```
removeExisting(this.extensionWidgetsAbove);   // map.delete(key)
removeExisting(this.extensionWidgetsBelow);   // map.delete(key)
...
targetMap.set(key, component);                // 重新插入 = 追加到 map 末尾
```

JS `Map.set` 对**已存在键**不改迭代顺序，但这里每次刷新都先 `delete` 再 `set`，等于把该 widget 移到末尾。
两个面板都以约 4s 周期各自刷新（monitor: `autopilot/console.ts:682,751`；watch: `pm/ui-bridge.ts:893`），相位不同，
于是"谁最后刷新谁在下面"，相对顺序来回翻转。

## 修复

1. **保序替换（core）**：`setExtensionWidget` 在同一 placement 下重建既有 key 时，只 dispose 旧组件后
   `targetMap.set(key, component)`（不 `delete`），保留首次注册位置；仅在 `content === undefined`（清除）或
   placement 变化（key 出现在另一个 map）时才 `delete`。
2. **固定相对顺序（明确 monitor 在上）**：给 `ExtensionWidgetOptions` 增加可选 `order`（number，默认 0，
   ascending = 越靠上），渲染时按 `(order, 注册序)` 稳定排序；monitor 用 `order: 0`，watch 用 `order: 10`。
   未传 `order` 的既有调用方行为不变（注册序）。

## AC（可机械判定）

- AC-001: 当同一 key 被连续 `setWidget` 刷新 N(≥2) 次时，该 key 在目标 placement 的渲染序保持不变（无 delete+append）。
- AC-002: 当 monitor 与 watch 同处 `belowEditor` 时，渲染顺序恒为 monitor 在上，与两者刷新先后无关。
- AC-003: 当 `content === undefined` 或 placement 变化时，旧 placement 的组件被 dispose 且不再渲染。
- AC-004: 未传 `order` 的 widget 之间保持注册序（既有第三方扩展行为不变）。

## 写面

- `packages/coding-agent/src/modes/interactive/interactive-mode.ts`（core）
- `packages/coding-agent/src/core/extensions/types.ts`（`ExtensionWidgetOptions.order`）
- 调用方：`autopilot/console.ts`（monitor）、`pm/ui-bridge.ts`（watch）
- 测试：`packages/coding-agent/test/`（widget 排序用例）

## 验证

- 新增/修改测试：连续刷新保序 + monitor/watch 恒定顺序 + 清除/换 placement。
- `npm run check` 全量（无 error/warning/info）。
