# Project Log — FeatureMigrator

> 追加型 / 不可变时间线。由 advance_phase.py done 追加。

| Completed | Commit | Key | 核心问题 | Supersedes |
|-----------|--------|-----|---------|------------|
| 2026-09-09 16:59 | 6273b27f9 | mw-worker-timeout-convergence | Worker watchdog redo: activity idle detection + per-task budget + convergence checkpoint with PM escalation + deadline steer; 87/87 tests, live smoke x2, quality gate PASS | — |
| 2026-09-09 23:53 | 357296d89 | mw-dispatch-flow-fixes | — | — |
| 2026-09-10 19:27 | fceae6eaf | mw-widget-terminal-lifecycle | Widget 三区渲染 + ack 通道/sidecar + 终态 detail 取源 + TL;DR 双保险 + 孤儿行 reconcile；TS 121/121 + Python 365 + bundle 冒烟 + 38/38 质检（review S1~S3 已修复） | — |
| 2026-09-10 19:32 | 5e8ecf39d | goal-autopilot | T-18 wrap-up: QG PASS (72/72), 18/18 tasks done | — |
| 2026-09-11 00:19 | 04bc69616 | ai-baseline-repair | AI baseline drift repair: tsgo 26->0 + check green + ai suite 838 passed (root fix = upstream generator mirror block); attribution B=58/A'=26/A=0 with user decisions recorded; prevention docs in README+AGENTS.md; QG 38/38 PASS | — |
| 2026-09-11 17:19 | 5fa74a900 | autopilot-monitor | — | — |
| 2026-09-17 17:00 | 477d8ace4 | mw-dual-workspace | 质检 PASS（用户确认接受 4 项 ⚠️ 欠债）；quality-gate-report-2026-09-11.md + achieved.md 落盘；check 0/0/0、回归基线 new-failures=0、audit_phase PASS | — |
| 2026-09-19 13:59 | 67e70a8c8 | mw-target-partition | mw-target-partition 完成：target.yml 单文件 v2（active 键 + dual/partition 模式块）新增 partition 模式——大项目子目标独立分片（parent 只读 + 独立分片根 = worker cwd + 命名 roots）；mw partition set/show/clear/on/off 命令族 + v1 一次性迁移（.bak）；/mw partition TS 转发；profile v2 注入（模式行+切换整体替换）+ launcher 撕裂校验 fail-closed；doctor partition-only 键 + 指纹缓存。改动面：mw_common.py/mw.py/launcher.py/autopilot-dispatch.py + target-config/task-dispatcher/ui-bridge/mw-runner + dist bundle；测试 Py 660 / TS 377 全绿、S0 golden 基线逐字节 MATCH（v1 零回归）、规则表 12 行 112 参数 case 双侧 parity、真实 spawn E2E（cwd=分片根+v2 注入+config-torn 负路径）。质检两轮（FAIL 4 BLOCKER→处置→复核 PASS）。 | — |
| 2026-09-19 18:41 | 67e70a8c8 | mw-worker-tree-kill | worker-mode.ts 4 个退出位点 + exit 安全网调用 killTrackedDetachedChildren（taskkill /T / kill(-pgid)），修复 watchdog 杀 worker 后 bash 子树孤儿化事故；+2 测试文件（5 单测 + 真实树 live），全链 mw 派发 smoke 零孤儿，质检 21/21 通过；dist 重建 + serve 已重启生效。 | — |
| 2026-09-20 16:07 | 44f30c338 | mw-partition-parent-extended | partition parent 语义修正：只读上下文 → 扩展可写工作区。Py 派发展开并入 parent root + TS worker 侧 profile 解析 union（双层，空 scope/deny-only 不回退，deny 先于包含性，写路径零拦截回归锁定），标签与 mw.py 文案去 read-only，golden parity 保持。触达 6 源文件 + 5 测试文件（dual/single 零修改）；Py 678/TS 44+188 全绿；PM 自查 + worker 独立质检双 PASS。取代 mw-target-partition spec §1.1/§1.4/§4 的只读定性（旧 key 归档不回改）。 | — |
