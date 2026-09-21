# plan: mw-dispatch-role-escape

> 阶段: PLAN / 上游: spec.md（AC-001~011）、design.md（D-001~011）

## 执行顺序

1. **T-01 TS 派发门禁**（`shared/dispatch-models.ts` + `pm/ui-bridge.ts` + TS 测试）
   实现 D-001~D-007、D-009、D-010；覆盖 VC-001~VC-008、VC-010。
   T-01 是其余任务的依赖（T-02 的日志行文案与 T-03 的冒烟都基于它的产物）。
2. **T-02 Python launcher 观测行**（`launcher.py` + `test_dispatch_models.py`）
   实现 D-008 + role map parity 断言；覆盖 VC-009、VC-011。
3. **T-03 文档 + dist 重建 + 冒烟**（两包 CHANGELOG、mw README、`mw build --install`、tmux 冒烟）
   覆盖 AC-011、VC-012，并出 EXECUTE 阶段的证据归档。

## 顺序理由

- T-01 与 T-02 改的是不同语言的同一契约（task.md frontmatter + 日志），接口面只有
  `model-reason:` 键名与 `model-override` 行文案；先落 T-01 可让 T-02 的测试对照真实产物。
- T-03 必须在两者之后：dist 重建包含 T-01 的 TS 产物。

## 风险与回退

| 风险 | 缓解 |
|------|------|
| 新增校验误拦合法值（registry 无该 provider 条目） | design §4：无条目 → 跳过；单测覆盖该分支 |
| 新参数改变既有 frontmatter 字节 | VC-010 逐字节断言；省略参数时走原分支 |
| Python 观测行改动影响 spawn 行为 | 只加日志，不改 `effective`/`cmd` 构造；VC-009 断言 model 仍为显式值 |
| dist 重建需全局扩展安装权限 | 若失败则记录并降级为「源码 + 单测已验证，dist 待用户执行 `/mw build --install`」 |

## 完成判据（EXECUTE 出口）

- TS 目标用例全绿（新增 + 原 dispatch 用例）；Python 目标文件全绿；`npm run check` 0 error/0 warning/0 info。
- 未触碰基线外的既有失败（Windows 环境基线 89 项；本 key 不新增失败）。
- 文档三处更新；dist 重建后 tmux 冒烟通过（或按风险表记录的降级结论 + 用户确认）。
