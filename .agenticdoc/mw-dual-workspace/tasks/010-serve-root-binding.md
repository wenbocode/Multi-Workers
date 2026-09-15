# Task 010: serve 根绑定断言

- Stage: S4
- 代码状态: 代码完成（零代码改动，纯用例锁定，符合预期）
- 验证状态: 验证通过（2026-09-11，4/4 + 全量 402 + serve 重启冒烟记录，证据 evidence/runs/010-serve-root-binding.md）
- ac_refs: [AC-009]
- vc_refs: [VC-015]
- pattern_refs: []
- deps: [005]
- 预估: ~1h

## 交付物

- serve 测试扩展（`packages/multi-workers/test_serve_meta.py` 相关）: dual 模式下 PID 文件/serve.meta/stop 请求端点/serve 日志的路径前缀=控制根 `.mw/`
- 手动冒烟步骤记录（含 mw serve 重启提示——当前运行实例需重启才加载新代码，staleness 机制会提示）

## AC 摘录（spec.md §3）

- AC-009: mw serve 的 PID/meta/stop/日志全部锚定控制工作区 `.mw/`，不因 dual 模式漂移到目标工程

## 实现要点

- 预期零代码改动（serve 以 --project=控制工作区启动，路径天然锚定）——本 task 价值是用例锁定该不变量，防未来回归
- 若断言失败则说明存在真实漂移，按 debug 流程处理而非改断言

## 验证方式（VC 断言）

- VC-015: `[VERIFY] VC-015: serve-meta-prefix=control-mw`
- 证据落盘: `evidence/runs/010-serve-root-binding.md`

## 依赖与阻塞

- 依赖 005（双根链路就绪）。与 008/009 无依赖关系，可并行。
