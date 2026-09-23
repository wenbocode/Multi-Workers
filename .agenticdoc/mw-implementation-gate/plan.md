# Plan: mw-implementation-gate

> Key: mw-implementation-gate
> 创建时间: 2026-09-21

## 任务分解（实现类任务派发 worker 执行）

| # | 任务 | 产物 | 执行者 | 依赖 |
|---|------|------|--------|------|
| T1 | 实施门禁守卫模块 | `shared/implementation-gate.ts`：纯判定函数（isCodePath / claim 匹配 / mini 新鲜度 / bash 目标判定 / gateDecision）+ `registerImplementationGate(pi)` | worker（coding） | design |
| T2 | 注册接线 | `index.ts` activate() 双加载 flag 后、模式分支前 `registerImplementationGate(pi)` | worker（coding，与 T1 同 worker） | T1 |
| T3 | 守卫测试 | 纯函数单测 + `test/suite/` harness+faux provider 真实 tool_call 层（AC-001/002/004）；MW_IMPL_GATE_ROOT fixture | worker（coding） | T1,T2 |
| T4 | 框架 SKILL.md 触发词 | description 扩词 + 框架仓 commit+push + diff-installed clean（AC-005） | worker（coding，独立可并行） | - |
| T5 | 文档与声明 | CHANGELOG [Unreleased]（含部署生效面 D-8 声明）+ README 门禁节 | PM | T1,T2 |
| T6 | 验证与收尾 | 全量回归（./test.sh 或定向 suite）+ 真机验证 + quality-gate-report + achieved | PM | T3,T4,T5 |

## 顺序

T1+T2（同一 coding worker）∥ T4（独立 worker）→ T3（依赖 T1/T2 产物）→ T5/T6（PM 收尾）。

## 验证点

- T1/T2：`npm run check` 绿；T3 测试过（真实 tool_call 层，非纯函数）；
- T4：diff-installed.py clean + origin 同步；
- T6：AC-001~006 勾销（quality-gate-report）。
