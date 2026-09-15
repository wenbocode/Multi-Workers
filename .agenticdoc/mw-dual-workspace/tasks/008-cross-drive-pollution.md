# Task 008: 跨盘零污染集成用例

- Stage: S4
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，双跑：无 env skip 可见 + 真实 F:/E:/ 全链 target-tree-hits=0；真卷零泄漏；check exit=0，证据 evidence/runs/008-cross-drive-pollution.md）
- ac_refs: [AC-002]
- vc_refs: [VC-003]
- pattern_refs: []
- deps: [005, 006, 007]
- 预估: ~1.5h

## 交付物

- 跨盘集成用例（位置按现有惯例定: 双根端到端归 multi-workers pytest 或 coding-agent test/suite，执行期看哪侧 fixture 更顺）
- 门控: 读 env `MW_TEST_CROSS_DRIVE_ROOTS`（如 `"F:/;E:/"`），解析出 ≥2 个不同卷才执行；缺失则 skip 且输出标注 skip 原因（D-009）

## AC 摘录（spec.md §3）

- AC-002: 目标树零新增框架文件——.agenticdoc/.mw/_workers.parallel/_index.parallel/trace.log/output.md/phase-*.md 在目标树计数=0，控制工作区齐全

## 用例流程

1. fixture: 双卷临时目录（来自 env 指定卷）作 game/engine + 控制工作区
2. 写最小 target.yml（dual）→ dispatch 最小 worker 任务 → 等待完成
3. 扫描 game 树 + engine 树: 上述文件模式计数=0
4. 断言控制工作区: trace.log/output.md/_workers.parallel 等齐全

## 验证方式（VC 断言）

- VC-003: `[VERIFY] VC-003: target-tree-hits=0 control-files=complete`
- 双跑: 本机真实跨盘（F:/E:）一次 + 无 env 的 CI 模拟一次（skip 原因可见）
- 证据落盘: `evidence/runs/008-cross-drive-pollution.md`

## 依赖与阻塞

- 依赖 005（双根执行）、006（dispatch 注入）、007（profile 渲染）——全链就绪才有意义。
