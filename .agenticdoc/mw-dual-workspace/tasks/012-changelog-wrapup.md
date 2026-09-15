# Task 012: CHANGELOG 与收尾材料

- Stage: S4
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，CHANGELOG ×2（coding-agent 追加 4 条 / multi-workers 新建）+ achieved.md 材料落盘，证据 evidence/runs/012-changelog-wrapup.md）
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009]
- vc_refs: []（文档收尾 task，无运行时断言；VC 覆盖由 001-011 证据账本承载，evidence-requirement.md 质检门禁复核）
- pattern_refs: []
- deps: [011]
- 预估: ~0.5h

## 交付物

- `packages/coding-agent/CHANGELOG.md` [Unreleased] → Added: dual workspace 模式（target.yml/target-config）、read-scope deny globs、profile 三节注入
- `packages/multi-workers/CHANGELOG.md` [Unreleased] → Added: `mw target` CLI、doctor 扩展（PyYAML 检查/toolchain 探测缓存）、launcher dual cwd、dispatch 注入
- `achieved.md` 前置材料（做了什么/收益达成/遗留什么——done 门禁必填项）

## 注意

- 只追加 [Unreleased] 现有节，不建重复节（AGENTS.md Changelog 规则）；读完整节后再追加
- 遗留项如实记录: P4 无 .gitignore 遍历限制（有界）、LongPathsEnabled 机器依赖、VCS/游戏 CI 后置（D-012）
- 不 commit（用户逐次决定）

## 验证方式

- vc_refs 为空的理由已注明；完成判定=CHANGELOG 两个包均含条目 + achieved.md 材料落盘
- 证据落盘: `evidence/runs/012-changelog-wrapup.md`（diff 摘录）
