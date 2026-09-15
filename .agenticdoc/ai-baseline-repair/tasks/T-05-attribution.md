# T-05: 第二层归因报告

> Key: ai-baseline-repair | 依赖: 无（与 T-01~04 无耦合） | 模式: PM 直执

## 目标

D-007 / AC-007：87 失败（agent 2 + coding-agent core 85）的 A/B/C 归因 + 修/不修建议 + 用户决策留痕。

## 步骤

1. `git worktree add` 独立目录 ×2（origin/main、HEAD），`npm ci --ignore-scripts` + build + check + test
2. 三分类：A=未过 CI 栈引入（Linux 语义也败）/ B=Windows 环境缺口 / C=叠加；逐类清单 + 计数
3. `evidence/runs/attribution-2026-09-10.md`：分类 + 置信度注记（Windows 跑 Linux 语义偏差：路径/超时/信号）+ 建议表 + 用户决策区
4. `git worktree remove` 清理

## 验收

- [x] 报告含 A/B/C 分类、计数、建议表、用户决策区（VC-007）→ evidence/runs/attribution-2026-09-10.md
- [x] 主 worktree 未被污染（GC-A6；两个 scratch worktree 建在仓外 H:/git/，已完整清除，`git worktree list` 只剩主仓）
- [x] 用户决策前不修第二层（报告 §6 待勾选）
- [x] 基线口径修正：原「87 处」单位混杂（agent 的 2 是文件数）；严谨口径 = agent 13 + coding-agent 76 = 89 败（ai 修复连带修好 9 个）

## 验证状态

验收通过（2026-09-10）：分类结果 **B=58（65%）/ A'=26（29%）/ A=0**；关键取证 = upstream/main 同机 Windows 跑出 95 败（含 bash-close-hang-windows 字面命名测试），证明 B 类是上游同款 Windows 缺口；A' 全部对应上游 08-14 导入后的修复提交（09-01~09-10 密集）；安全检查 = model-runtime-cloudflare-compat 在 HEAD~1 已有 2 败、我的提交后 1 败（净修复 1，无新增破坏）
