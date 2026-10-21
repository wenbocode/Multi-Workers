# Quality Gate Report: mw-usage-monitor

**时间**: 2026-10-21T18:40Z
**触发**: 结案前全量质检（用户确认验证完毕，推进 DONE）
**范围**: 全量（v0.1 核心 → v0.8 夹具折叠）

## 前置检查

| 检查项 | 结果 |
|--------|------|
| spec.md 存在 AC 编号 | ✅ AC-001…AC-033（§2–§16） |
| design.md 存在 | ✅（design D-1…D-7 + RQ 证据 5 份） |
| evidence 台账 | ✅ `evidence/verification-20261019.md`（V-1…V-9） |
| 任务卡与交付 | ✅ T-01…T-17 全部 done（worker 报告 + PM 复核） |
| 入库状态 | ✅ 5 次提交：`744e95b97` `4e419ba4f` `e6523ed14` `9bef2152b` `7bb436ea9`（+ 证据提交） |
| 提交树测试 | ✅ temp worktree 逐批复跑：59 → 74 → 110 → 91 → 95 passed |

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | launcher 每次 spawn 写 start、reap 写 end/spawn_failed | ✅ | `test_launcher_run_ledger.py`(17) + V-3 实机台账 | — |
| Q-AC-002 | 给定 session_id，`mw stats` 与手工扫描 Δ=0 | ✅ | V-2（独立脚本对账）、V-5（真实 e2e：calls 20 / in 30986 / out 13992 / cacheR 503040，Δ=0） | — |
| Q-AC-003 | `--since 7d` 输出四组分布 | ✅ | V-1 契约测试、V-9 真实 7d 输出（11 组） | — |
| Q-AC-004 | 每 run wall_s（孤儿行不算 0）、p50/p90、n<5 ⇒ `-` | ✅ | `test_usage.py` wall 用例、V-9（`(test fixtures) 14s / 26s*`） | — |
| Q-AC-005 | `source=pm` 可统计、可与 worker 分离、PM 跨天按消息 ts 分桶 | ✅ | V-1 用例、V-5（pm 会话行） | — |
| Q-AC-006 | `/mw stats` 在 pi 窗口输出简报，失败有可见错误 | ⚠️ | V-8b（bundle 内 `statsMw` = `runMwCli("stats", …, false)`，`mw-stats-surface.test.ts` 8 passed） | 窗口内实际按键回读需用户 `/reload` 后确认；CLI 与契约测试已覆盖 |
| Q-AC-007 | codex/claude 不可统计 ⇒ `unknown_cli` + token `-` | ✅ | `test_usage.py` attribution 用例；claude 分支按 `--session-id` 精确匹配 | — |
| Q-AC-008 | 输出无 cost/金额字段 | ✅ | `test_stats_cli.py` schema 断言（JSON 顶层键集合） | — |
| Q-AC-009 | 零回归 | ✅ | 提交树逐批复跑 multi-workers 全部相关测试（95 passed），TS `mw-stats-surface` 8 passed | 基线红（8 项非本 key）未变化 |
| Q-AC-010 | 文档同步、示例与实际一致 | ✅ | V-4、T-15（`BLOCK_MATCHES_REAL_OUTPUT` 逐字节比对）、T-17 README 锚点编辑 | — |
| Q-AC-011 | 会话 id 唯一性 `mw-<key>-<pid>-<seq>` | ✅ | `test_launcher_run_ledger.py`、V-5 实机 `mw-mw-usage-monitor-17812-1` | — |
| Q-AC-012 | `--since` 先 header 粗筛再全量解析（性能） | ✅ | `test_usage.py` header-only 用例；真实 7d 全量扫描 ~2.4s | — |
| Q-AC-013 | 无 usage 的会话 token `-`，不参与加总 | ✅ | `test_usage.py` 用例 | — |
| Q-AC-014 | `--until` 半开区间，窗外 run 全消失 | ✅ | `test_usage.py` + V-6（`--until 2020-01-01` rc=2 等边界） | — |
| Q-AC-015 | `--detail` 每行含 key/task/type/model/calls/四分量/wall/status | ✅ | V-6、V-8（真实文本输出，新增 project 列后仍一致） | — |
| Q-AC-016 | `runs[]` 字段名逐字一致；open_run 的 wall_s 为 null | ✅ | `test_usage.py` 字段集合断言 | — |
| Q-AC-017 | 窗口面 `/mw stats --detail` 可直接用（零 TS 改动） | ✅ | `test_stats_cli.py`（Python 侧参数即窗口面参数）、V-6 | — |
| Q-AC-018 | `--html` 生成单文件、无外链/脚本/CDN | ✅ | V-7（76352B，无 `http`/`<script`）、`test_usage.py` 8 个渲染用例 | — |
| Q-AC-019 | 默认打开、`--no-open`/env 抑制、失败 rc 不变 | ✅ | V-7（`--json` 不弹窗、warn 不改 rc）、T-11 用例 | — |
| Q-AC-020 | HTML 与文本同一 report、数值一致 | ✅ | 渲染器签名 `render_html(report)`；V-7 逐值比对 | — |
| Q-AC-021 | 台账字段 HTML 转义 | ✅ | `test_usage.py` 转义用例（含 `<`/`&` 注入） | — |
| Q-AC-022 | HTML 明细恒为窗口全量（不受 `--limit`） | ✅ | V-7（heading `· 189` = runs_total，无 `showing`）、T-12/T-13 用例 | — |
| Q-AC-023 | `include_all_runs=True` ⇒ `len(runs_all)==runs_total` | ✅ | `test_usage.py`、`test_stats_cli.py` | — |
| Q-AC-024 | `runs_all[:k]` 与 `limit=k` 的 `runs` 深比较相等 | ✅ | `test_usage.py` 深比较用例 | — |
| Q-AC-025 | worker 行 project = 台账 start.project；PM 行 = 会话 cwd | ✅ | V-8（真实台账 0 null、`title="H:\git\E2Feature"`） | — |
| Q-AC-026 | 文本 basename 列 + HTML `title` 全路径 | ✅ | V-8（表头顺序与单元格实测） | — |
| Q-AC-027 | `--project X` 过滤后每行（worker/PM）都匹配 X | ✅ | V-8（`--project E2Feature` 351 行，泄漏 0）、T-14 用例 | — |
| Q-AC-028 | `statsMw(root, [])` 的 argv 无 `--project`；显式只出现一次 | ✅ | V-8（vitest 8 passed，`project_appends=0`） | — |
| Q-AC-029 | `--all-projects` 与裸跑 `runs_total` 相同；冲突 rc=2 | ✅ | V-8（209/209、rc=2 冲突提示） | — |
| Q-AC-030 | 文本/HTML/JSON 三种输出 project 分布一致 | ✅ | V-8（HTML 210 行含 6 项目；文本/JSON 同分布） | — |
| Q-AC-031 | 夹具 cwd 折叠为单个 `(test fixtures)`（calls/runs 求和） | ✅ | V-9（38 runs / 49 calls）、T-17 用例 | — |
| Q-AC-032 | `runs[].project` 仍保留原始路径 | ✅ | V-9（`--project "(test fixtures)"` 明细为原始路径） | — |
| Q-AC-033 | 夹具过滤只选夹具；真实项目不带夹具 | ✅ | V-9（128 = 夹具 runs；E2Feature 泄漏 0） | — |

## 汇总

- **总问题数**: 33
- **通过（充分）**: 32（97%）
- **有条件通过（不足）**: 1（Q-AC-006：窗口内按键回读待 `/reload` 后确认；bundle 内容与契约测试已证）
- **未通过（无证据）**: 0

**质检结论**: ⚠️ 有条件通过（欠债 1 项：用户 reload 后的窗口内回读）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 |
|------|------|---------|------|
| Q-AC-006 | 窗口进程启动早于 bundle 更新，`/reload` 需用户触发 | 用户 `/reload` 后执行一次 `/mw stats --detail` 并确认输出 | 用户（非本 key 代码欠债） |

## 二次印证结论

- spec §16 的四条约束（临时根、`pi-runtime-*`、事实层不变、过滤方向）均有对应 Q-AC-031…033 覆盖。
- design D-1…D-7（token 只读 join、四分量、session-id 归因、`unknown_cli`、存储位置、无 rollup、墙钟不混算）在 V-1/V-2/V-5 中有对应用例或实机证据。
- 无「task 有 vc_refs 为空但 AC 有对应 VC」的遗漏绑定：本 key 的 AC 与 task 通过 spec §编号 + 任务卡「对应：spec §N」双向锚定。
