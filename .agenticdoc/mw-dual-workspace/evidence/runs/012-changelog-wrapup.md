# Evidence Run: 012-changelog-wrapup

- Date: 2026-09-11T23:00:00+08:00
- Task: 012-changelog-wrapup（S4）
- vc_refs 为空的理由：文档收尾 task，无运行时断言；VC 覆盖由 001-011 证据账本承载

## 交付物

1. `packages/coding-agent/CHANGELOG.md` [Unreleased] → Added 节尾追加 4 条（既有节内追加，未建重复节；Fixed 节内历史 Added/Changed 混排为既有状态，未动）：
   - dual-workspace worker 支持（target.yml / target-config.ts / 零污染 / 失败关闭校验）
   - deny_globs frontmatter 上下文防火墙（双基准 / deny 优先 / 目录自匹配 / deny-only）
   - TS dispatch 时 profile 三节注入（含 fail-closed、幂等、任务级覆盖尊重、逐任务隔离）
   - controlRootFromTaskPath 显式化
2. `packages/multi-workers/CHANGELOG.md` 新建（该包此前无 CHANGELOG，首次成文）：[Unreleased] Added 4 条——dual-workspace 配置层与 CLI、dispatch deny_globs 注入、launcher dual cwd、doctor target 检查
3. `.agenticdoc/mw-dual-workspace/achieved.md` 前置材料：做了什么（S1-S4 四段）、收益达成（9 AC → 证据表，测试资产统计）、遗留什么（P4 无 .gitignore 有界限制 / LongPathsEnabled 机器依赖 / VCS-CI 后置 D-012 / 口径外测试观察 / CHANGELOG 未 commit）

## 遗留项如实记录核对

- P4 无 .gitignore 遍历限制（有界）✓（D-004 已知限制）
- LongPathsEnabled 机器依赖 ✓（D-008）
- VCS/游戏 CI 后置 ✓（D-012）
- 未 commit ✓（待用户逐次决定）

## 完成判定

- coding-agent CHANGELOG [Unreleased] 含 dual workspace/deny globs/profile 注入条目 ✓
- multi-workers CHANGELOG 含 mw target/doctor/launcher dual cwd/dispatch 注入条目 ✓
- achieved.md 材料落盘 ✓
