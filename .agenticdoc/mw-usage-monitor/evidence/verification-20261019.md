# 验证记录：mw-usage-monitor（2026-10-19）

PM 亲自执行的验证（不依赖 worker 自述），命令与真实输出。基线见 `_scratch/quality-gate-drift-guard-20260902.md`。

## V-1 单元/契约测试

```powershell
cd packages/multi-workers
python -m pytest test_usage.py test_stats_cli.py test_launcher_run_ledger.py -q
# 59 passed in 0.95s
```

（`test_usage.py` 30 / `test_stats_cli.py` 12 / `test_launcher_run_ledger.py` 17；
`test_stats_cli.py` 的 `GROUP_ROW_KEYS` 由 PM 补入 `wall_kind`——T-06 的写面外一行。）

TS 面（PM 复跑）：

```powershell
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mw-stats-surface.test.ts test/suite/rag-window.test.ts
# Test Files 2 passed (2) · Tests 26 passed (26)
```

## V-2 AC-002：真实数据 token 对账（独立脚本 vs mw stats）

独立脚本（不 import `usage.py`，只读扫描 `~/.pi/agent/sessions/**/*.jsonl`，窗口 = 最近 1 天，
按 entry `timestamp` 过滤，assistant = `type:"message" and message.role=="assistant"`，另计 `compaction`）：

```
{"sessions": 76, "calls": 6908, "entry_types": {"message": 6875, "compaction": 33},
 "tokens": {"input": 16350965, "output": 6058921, "cache_read": 787781888, "cache_write": 0}}
```

`python -X utf8 packages/multi-workers/mw.py stats --since 1d --json`：

```
{"calls": 6902, "tokens": {"input": 16348427, "output": 6053730, "cache_read": 786637568, "cache_write": 0},
 "runs": 103, "sources": {"worker": 27, "pm": 76}, "ledger": {"events": 54, "bad_lines": 0, "open_runs": 3}}
```

差异：calls 6 条（0.09%）、input 2,538（0.016%）、output 5,191（0.086%）、cacheRead 1,144,320（0.15%）。
两次扫描相隔数十秒，期间有 PM 会话持续写入；`--since` 锚点也相差数十秒。**判定：同窗口内口径一致（Δ 为时间偏移，
非记账偏差）**；`sessions`/PM runs 数量完全相同（76）。

注：PM 第一次尝试的独立脚本把 assistant 识别成 `type=="assistant"`（实际是 `type=="message"` +
`message.role=="assistant"`），只数到 33 条 compaction → 已修正脚本重跑。此坑来自 RQ1 §1 的 entry 类型表，
后续若有人二次实现扫描器需注意。

## V-3 AC-001/AC-011：台账形态（实机文件）

`~/.mw/usage/runs.jsonl`：54 events = 27 `start` / 24 `end` / 3 `spawn_failed`，`bad_lines=0`。

```
start: {"run_id":"20261019T105133Z-55976-2","key":"int-tests","task_key":"serve-t1","type":"coding",
        "role":"coding","cli":"pi","attribution":"exact","session_id":"mw-int-tests-55976-1",
        "model":"","model_source":"default","pid":22268}
end:   {"event":"end","run_id":"20261019T105133Z-55976-2","ts":"2026-10-19T10:51:34+00:00",
        "exit":0,"wall_s":1.004,"status":"done","reconciled":false}
```

`session_id` 形态与 AC-011 一致（`mw-<key>-<pid>-<seq>`），`end` 行不含 token（D-7）。

## V-4 文档一致性

- `packages/multi-workers/README.md:89-159` 的样例由 `usage.format_report_text` 实际渲染，含 `*` 脚注；
- `packages/multi-workers/CHANGELOG.md:102` 在 `[Unreleased] → ### Added` 内，无金额表述；
- 真实输出（`mw stats --since 1d`）与 README 样例同形：

```
by project
  Multi-Workers            calls 1014  in 2.74M  out 836k   cacheR 80.4M   cacheW 0   wall p50 8m22s p90 39h40m* n 16
  OverCode                 calls 291   in 814k   out 249k   cacheR 27M     cacheW 0   wall p50 -     p90 -      n 4

* = PM 会话跨度（header→末条），非 worker 墙钟
coverage: pi 92 runs (exact)
```

## 未验证（需用户批准的两个动作）

- **AC-006（`/mw stats` 在窗口可见）**：需要 `mw build`（或等价扩展打包步骤）把新 `ui-bridge`/`mw-runner`
  部署到全局扩展目录，再在本窗口 `/reload`。当前 dist/全局扩展仍是旧构建，窗口里还没有该子命令。
- **端到端 exact 归因（AC-002 的 worker 侧）**：需要 `/mw restart` 让 serve 用新 `launcher.py`，然后派一张
  最小任务，确认该 run 的 `session_id` 能在 `~/.pi/agent/sessions` 找到对应文件且 `mw stats` 的 token 与手工
  扫该文件一致。当前 27 条 worker 台账全部来自测试桩（1 秒 run，无会话文件），`wall_kind` 全为 `session`。
