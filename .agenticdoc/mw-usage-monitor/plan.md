# Plan: mw-usage-monitor

- Key: mw-usage-monitor · 2026-10-19
- 输入：`spec.md` v0.2（AC-001…AC-013）、`design.md`（§2 台账、§3 模块、§5 JSON 契约、§8 测试）
- 目标：本机 `~/.mw/usage/runs.jsonl` 台账 + `mw stats` CLI + `/mw stats` 窗口简报；pi/PM exact，claude exact，
  codex 显式未统计。

## 阶段与任务

| 阶段 | 任务 | 交付 | 依赖 | 并行 |
| --- | --- | --- | --- | --- |
| M1 口径内核 | T-01 `usage.py` + `test_usage.py` | 目录解析、台账 append/load、pi/claude 扫描、聚合、文本渲染 | — | 独占（其余都 import 它） |
| M2 生产端 | T-02 launcher 钩子 + `test_launcher_run_ledger.py` | start/end/spawn_failed/reconcile 事件、`--session-id` 分配 | T-01 | 与 T-03 并行 |
| M2 查询端 | T-03 `mw stats` + `test_stats_cli.py` | argparse + `cmd_stats` + dispatch | T-01 | 与 T-02 并行 |
| M3 窗口面 | T-04 `/mw stats` + vitest | mw-runner 包装 + ui-bridge 分支 + 描述/usage 行 | T-03 | 独占（改 TS 同两文件） |
| M4 收口 | T-05 文档 + 全量验证 | CHANGELOG/README、`npm run check`、pytest 全量、实机一条 worker 验证 | T-02..T-04 | 独占 |

## 里程碑判据

- **M1 完成**：`test_usage.py` 绿；`format_report_text` 与 design §6 固定样例逐字一致。
- **M2 完成**：`test_launcher_run_ledger.py` + `test_stats_cli.py` 绿；`mw stats` 在无台账时不报错。
- **M3 完成**：vitest 新用例绿；`/mw stats` 在实机窗口能出简报（重启 serve 后）。
- **M4 完成**：`npm run check` 全绿、`packages/multi-workers` 非 e2e pytest 与基线一致（8 个已知红不新增）、
  CHANGELOG/README 更新、**一次真实 worker 运行产生 exact 台账行 + 正确 token**（端到端）。

## 验证命令（固定）

```powershell
# 单测（各任务自带）
cd packages/multi-workers
python -m pytest test_usage.py test_stats_cli.py test_launcher_run_ledger.py -q

# 全量（M4，非 e2e）
cd H:\git\Multi-Workers
.\test.sh                      # 或按 AGENTS.md：packages/multi-workers 全量 pytest
# TS
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mw-stats-surface.test.ts

# 类型/规范（改完代码必跑）
cd H:\git\Multi-Workers
npm run check
```

## 端到端验收（M4，需用户同意重启 serve）

1. `/mw restart`（加载新 launcher）。
2. 派一张最小 research 卡（或复用本 key 的收尾任务）→ 观察 `~/.mw/usage/runs.jsonl` 出现 start/end 两行，
   `session_id` 形如 `mw-<key>-<pid>-<seq>`。
3. `mw stats --since 1d` 与 `/mw stats` 输出的该 run tokens 与手工扫对应会话一致。

## 风险与回滚

- 每任务独立可回滚（新文件为主；launcher/mw.py 改动为局部插入）。台账是新增文件，删除即回滚。
- 若 T-01 的口径与实测不符（例如 compaction usage 语义），改口径前先补证据，不静默调整。
