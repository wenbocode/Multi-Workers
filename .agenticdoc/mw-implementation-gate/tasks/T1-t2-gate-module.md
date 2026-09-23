# T1+T2: implementation-gate 守卫模块与注册

- 状态: done（worker t1t2-gate-module，16m）
- 范围: `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts`（纯判定 + register）+ `index.ts` 注册（双加载 flag 后、模式分支前）。
- 规格: design.md D-1~D-6（三层门禁 / 三条件放行 / 代码路径定义 / reason 文本 / 审计）。
- 验收: `npm run check` 绿；模块可脱离 pi 单测（纯函数导出）。
- 结果: `shared/implementation-gate.ts` 新增 738 行（纯判定 + register，自包含仅类型导入，镜像 protected-config 骨架）；index.ts +13 行（:51 注册，双加载 flag 后、模式分支前）。npm run check 全绿；protected-config 回归 11/11；69 项临时行为验证（覆盖 AC-001~004 + W2 误报模式 + fail-closed + 新鲜度衰减，用后即删）。PM 复核：注册点、gateDecision 三条件语义、模块头 D-1~D-4 文档均符合 design。
