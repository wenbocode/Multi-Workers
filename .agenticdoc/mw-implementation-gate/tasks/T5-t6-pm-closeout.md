# T5+T6: 文档声明与验证收尾（PM 侧）

- 状态: done（T5 PM；T6 PM 复跑 9/9 + 11/11 + check exit 0，quality-gate 6/6，key 推进 done）
- T5 范围: `packages/coding-agent/CHANGELOG.md` [Unreleased] Added（含部署生效面：`mw setup --build` + 重启窗口后生效，旧 bundle 进程重启前无门禁）+ README 门禁节。
- T5 结果: CHANGELOG 门禁条目已入（含非沙箱声明）；multi-workers README 新增「实施准入门禁」小节（三放行条件 + 审计 + 生效面）+ MW_IMPL_GATE_ROOT 环境变量行。
- T6 范围: 定向 suite 回归 + 真机验证（临时项目 fixture 实测 block/放行三态）+ quality-gate-report（AC-001~006 勾销）+ achieved.md。
- 验收: AC 全勾 + 回归零破坏。
