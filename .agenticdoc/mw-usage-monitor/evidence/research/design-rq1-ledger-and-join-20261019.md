# Design-phase research: 台账/回填架构选型（design-rq1）

- Key: mw-usage-monitor · 2026-10-19 · 阶段：design
- 作用：为 `design.md` 的架构选型留底（spec 阶段证据见 `spec-rq1..rq4-*.md`，本文件只记**为什么这样选**）。

## D-A 捕获面：会话日志 vs LLM 代理

| 方案 | 结论 | 依据 |
| --- | --- | --- |
| 从 `proxy_multi.py` / `timi_proxy_cli` 抓 usage | **否决** | 代理只覆盖 claude/claude-cli/deepseek 端口路由；默认 worker 路由 timi 直连（`mw.py:351-354`、`:368-370`）；两处源码全文无 usage/token 钩子（`spec-rq4` §5） |
| 从 pi 会话 JSONL 抓 usage | **采用** | assistant message 必带 `usage`（287,310/287,310 条），compaction 也带（1,699 条），一条消息 = 一次 provider 响应、无重复 `(provider,responseId)`（`spec-rq1` §1） |
| 从 worker 的 trace.log 抓 | 否决为主源 | trace.log 只有 `[MODEL]/[END]` 元数据，无 token 计数（`spec-rq2` §5） |

收益：token 与墙钟来自两个天然权威（会话日志 / 台账），互不推导。

## D-B 归因：显式 session id vs 文本匹配

- 文本匹配（会话正文出现 task.md 路径）实测会误判 PM 会话（PM 会话里也会贴 task 路径）→ **否决**。
- 采用：launcher 显式分配 id（pi `mw-<key>-<pid>-<seq>`、claude `<uuid4>`），台账记 `session_id`；
  `mw-` 前缀即使台账丢失也能判 worker（`spec-rq1` §4、`spec-rq2` §1.4）。
- 否决的备选：`PI_CODING_AGENT_SESSION_DIR` 物理隔离 worker 会话目录（零 CLI 改动）——因自定义目录对其他窗口
  `/resume` 不可见（`spec-rq1` §3），会造成用户找不到 worker 会话；v1 不改目录。

## D-C 台账形态：两事件 append-only vs 单行更新

- 单行更新需要读改写 + 会因 launcher 崩溃停在 start（`spec-rq2` §5：launcher.log/conductor.log 每 serve 会话截断，
  queue 行 `updated_at` 被改写，均不可当台账）。
- 采用两事件（`start`/`end`/`spawn_failed`）+ `run_id` 配对：写入纯 append（无读改写），未结束运行可被查询面识别，
  并发写只需跨进程锁（`spec-rq4` §4 的 `archive_stale_entries` 形态）。

## D-D 存储路径：`~/.mw/usage/` + `MW_USAGE_DIR`

- `~/.agents/mw/usage/`（复用既有 `.agents` 机器级根）语义更干净，但用户已批 `~/.mw`，且改动面更小；
  范围歧义（`.mw` 项目级同名）用 `MW_USAGE_DIR` 显式解析助手 + 子目录 `usage/` 缓解（`spec-rq4` §3）。
- 否决裸 `expanduser("~/...")`：Windows 下读 `USERPROFILE` 不读 `HOME`，与 `machine_rag_servers_path` 序不一致且不可注入测试。

## D-E 聚合：查询时 join vs 落盘时回填 token

- 落盘时回填（launcher 结束时扫会话文件写 token）需要 launcher 依赖解析器与 deferred flush 时序，且会话文件可能
  在 end 之后仍被追加（compaction/续写）→ 会永久少记。
- 采用查询时 join（`design.md` §4）：台账只存元数据，`mw stats` 现扫窗口内会话。成本实测 7 天 2.9 s、
  全库 11.1 s、header 粗筛 0.54 s（`spec-rq1` §5）→ 可接受，且口径永远与磁盘一致。

## D-F 不做 rollup / 不做 doctor 段（v1）

- rollup 触发条件写进 `design.md` §9（>30 天窗或预计 >10 s），当前实测远低于阈值（`spec-rq1` §5）。
- doctor 是项目级诊断，台账是机器级 → 加 `usage` 段语义错位；`mw stats --json` 自带 `ledger` 健康字段（`spec-rq4` §6）。

## 未覆盖面

- 未做真实 worker 端到端（需重启 serve + 一次派发）；`design.md` §9 已列为 M4 验收项。
- claude 侧 `--session-id` + `-p` 组合的落盘文件名只有 `--help` 级证据（`spec-rq3` 未覆盖面声明），实现后需一次真实运行确认。
