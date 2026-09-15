# PM State: ai-baseline-repair

## Section 1: Snapshot
- Key: ai-baseline-repair
- Claim-Id: WENBOZHOU-PC4:88348
- Phase: DONE
- Updated: 2026-09-11 00:19
- Completed: 2026-09-11 00:19
- 下一步行动（重启恢复锚点）: ①✅spec（8 AC + 指纹 541028221b8a）→②✅design→③✅plan/tasks→④✅execute T-01~T-04（tsgo 26→0、check 绿、ai 套件 838 过；代码已提交 04bc69616，17 文件 +316/−78）→⑤✅T-05 归因（worktree×2 取证：B=58 Windows 缺口 / A'=26 上游已修 / A=0，报告 evidence/runs/attribution-2026-09-10.md，工作区已清理）→⑥⏳verify：等用户 §6 三项决策 → /review + /quality-gate → advance done

## Section 2: Task Status

| Task | 依赖 | 代码状态 | 验证状态 |
|------|------|---------|---------|
| T-01 src+单点类型修 | — | 完成（D-001/004/005） | 验收通过：tsgo 26→23→0 |
| T-02 model ID 重定向 | 无 | 完成（含根修转向：generator 镜像块 +37） | 验收通过：check/套件全绿 |
| T-03 cross-api 8 处 | 无 | 完成 | 验收通过：8 错消、无断言删除 |
| T-04 验证链+预防文档 | T-01/02/03 | 完成（17 文件含 README/CHANGELOG） | 验收通过：8VC 全绿 |
| T-05 第二层归因 | 无 | 完成（B=58/A'=26/A=0 + 决策区） | 验收通过：报告+决策区落盘 |

## Section 3: Key Decisions

- 2026-09-10: 第二层（agent 2 + coding-agent 85）按用户决策纳入本 key 为**归因交付物**（AC-007），修复与否待报告 + 用户决策，不擅自扩范围
- 2026-09-10: 归因取证方法 = git worktree 独立目录复现（GC-A6），CI 历史因无 gh/token 不可直接查，报告须标注 Windows 跑 Linux 语义的置信度

## Section 4: Hypothesis Queue

- H-1: origin/main（导入前）自洽绿——worktree 取证验证（AC-007 ①）
- H-2: packages/ai 8 运行时失败与 TS2345 同根（model registry 断言漂移）——AC-006 逐个留痕验证
- H-3: coding-agent core 85 失败大头为 B 类（Windows 环境缺口：超时/command 解析），少量 C 类叠加——AC-007 ② 分类验证

## Section 5: Worker Coordination

（无在飞 worker；本 key 派发待 plan 后）

## Section 6: Goal Alignment Log

- 2026-09-10: goal.md mtime 记录（Worker phase 完成时照抄）：见 .agenticdoc/goal.md；本 key 对齐「提交门禁可用性」（spec §0）

## Section 7: Process Log

- 2026-09-10 19:28: update_index claim 创建 key（ClaimId WENBOZHOU-PC4:88348）
- 2026-09-10 19:35: spec.md + 调研留底落盘；指纹 541028221b8a（canonical 管道当场实算留痕，防上个 key 的口径丢失问题复发）；pm-state Section 1-7 初始化
- 2026-09-10 20:0x: design→plan→tasks→execute 连续推进（门禁两次拦截：feedforward 节名实为「可复用资产」「需规避坑点」，补节后过；design 调研留底补 evidence/research/design-forensics-2026-09-10.md）
- 2026-09-10 20:4x: T-01~T-04 完成验收：tsgo 26→0、npm run check exit 0、ai 套件 838 passed/0 failed（基线 7~8 failed）、扩展域 123/123、Python 367 passed；关键转向=镜像 upstream generator 的 workers-ai→gateway 镜像块（根修 compat 层目录门禁依赖），T-02 初版删块/fixture 全部回滚；README 预防节 + CHANGELOG 3 条落盘；上游镜像跳过清单留档（qwen-token-plan-individual ×6、copilot-oauth 整文件重写、empty-tools 注释）
- 2026-09-10 21:3x: 提交 04bc69616 fix(ai) 17 文件 +316/−78（其他会话先行提交 8a063f4d9/2adc788a4，无冲突）；T-05 取证完成：mw-attr-head@04bc69616 vs mw-attr-upstream@08dc60bc5 各自 npm ci+build+hydrate 后同机跑 agent+coding-agent 全套；agent 13 败（12 双败+1 上游已修）、coding-agent 76 败（46 双败+25 HEAD 独有→全部对应上游 09 月修复提交）；基线口径修正 87→89（单位混杂+ai 修复连带-9）；upstream 侧 95 败含字面 Windows 命名测试=B 类铁证；model-runtime-cloudflare-compat 安全检查（HEAD~1 2 败→HEAD 1 败）；worktree 已清除
- 2026-09-10 22:5x: 用户三项决策执行完毕（B 类暂不修+文档化 → AGENTS.md Windows 89 败基线注记；A' 类规划 forward-port key；基线口径入档）
- 2026-09-10 23:0x: verify 完成——review：LGTM（0 S1/S2，S3 观察 4 项留痕，evidence/runs/review-2026-09-10.md）；quality-gate：前置门 7/7 + AC 8 + VC 9 + 覆盖/交叉 3，38/38 全过 VERDICT: PASS（evidence/quality-gate-report-2026-09-10T2250.md）；本行含 gate 关键词：PASS
