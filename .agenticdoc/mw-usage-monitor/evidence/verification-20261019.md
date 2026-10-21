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

## V-5 端到端复核（2026-10-21，build + serve restart 之后）

前提：`mw build` 14:25 完成，全局扩展与 `packages/multi-workers/dist/extensions/agent-team-loop.js` sha256 一致
（`a2c4454cc95bfd1b`，1328455B，含 `/ stats /` 与 `statsMw`）；serve 于 15:59:14 重启（PID 4416，
`mw status` 报 `fresh`，`expected commit = actual commit = 744e95b97`）。

用一次真实派发做样本（card `.agenticdoc/mw-usage-monitor/tasks/T-07-e2e-ledger-smoke.md`，
task `um-t07-e2e-ledger-smoke`，type=research，worker 自述 30 次工具调用后 settled）：

1. **start 行**（`python mw.py stats --since 2h --json` 的台账源 `C:\Users\wenbozhou\.mw\usage\runs.jsonl`）：
   `{"event":"start","run_id":"20261021T080045Z-17812-2","source":"worker","project":"H:\\git\\Multi-Workers",
   "key":"mw-usage-monitor","task_key":"um-t07-e2e-ledger-smoke","type":"research","role":"research","cli":"pi",
   "attribution":"exact","session_id":"mw-mw-usage-monitor-17812-1",
   "model":"timi/deepseek-v4.1-flash","model_source":"config:research",...}`
2. **end 行**（同一 `run_id`，reap 时写入）：
   `{"event":"end","run_id":"20261021T080045Z-17812-2","ts":"2026-10-21T08:02:36+00:00","exit":0,
   "wall_s":110.751,"status":"done","reconciled":false}`
3. **exact 归因成立**：会话文件真实存在
   `~/.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-21T08-00-49-345Z_mw-mw-usage-monitor-17812-1.jsonl`
   （106839B），文件名里的 id 与台账 `session_id` 逐字相同 ⇒ 台账行 → 会话文件是一对一，不需要正文匹配。
4. **token 归因 Δ=0**（手扫该文件 vs `mw stats`）：

   | 项 | `usage.scan_pi_session` 手扫 | `mw stats --since 2h --key mw-usage-monitor` |
   | --- | --- | --- |
   | requests | 20 | calls 20 |
   | input | 30986 | 30986 |
   | output | 13992 | 13992 |
   | cache_read | 503040 | 503040 |
   | cache_write | 0 | 0 |

   该 key 组 `runs=1, n=1, wall_p50=null, wall_kind="none"`：单样本不报墙钟、也不拿 PM 跨度回填（T-06 规则生效）。
5. **墙钟来自真实 reap**：同窗口其它组 `wall_kind="run"`（例 `timi/deepseek-v4.1-flash` n=27，
   p50 439.063s / p90 1017.769s），不再是 PM 会话跨度；`coverage` = `[{cli: pi, runs: 48, attribution: "exact"}]`。
6. **台账体检**：341 events、`bad_lines=0`、`open_runs=9`（含正在跑的 worker），无写坏行。

### 仍未验证（1 项，需用户操作）

- **AC-006（`/mw stats` 在窗口可见）**：全局扩展已更新，但本窗口进程启动于 2026-10-16 11:51（PID 43712），
  早于 bundle 的 2026-10-21 14:25，需用户在窗口执行 `/reload` 才会加载带 `stats` 分支的扩展。
  窗口内可见性无法由工具侧触发，故保持未验证直至 `/reload` 后人工确认。

### 已知偏差（不影响 AC）

- 台账 `pid` 是 serve 侧记账 pid（`Popen` 的 `cmd.exe` 包裹层，本次 17236），真实 pi 进程是另一 pid
  （worker 自测 `node.exe 30696`）；`session_id` 里的 `17812` 是 python 进程 pid。三者语义不同但台账只用
  `session_id` 做归因，`pid` 仅作排障线索。
- T-07 卡片锚点 `mw.py:7016` 已陈旧（`cmd_stats` 现位于 `mw.py:9623`，`--since` 默认值在 `mw.py:9674`），
  是并发的 decide 代码插入导致的行号漂移，卡片文字未同步。

## V-6 v0.3 复核（2026-10-21，`--until` / `--detail` / `--limit`）

用户反馈「窗口只能看用量，看不到具体调用方」，PM 在 spec §11 增补 R7–R10 / AC-014–AC-017，两轮 worker 交付：

- T-08（`um-t08-usage-detail-until-r2`）：`usage.py` +344/−35、`test_usage.py` +378/−1。
  `_parse_bound` 统一 `--since`/`--until` 解析（同一份正则），`parse_until` 多接 `YYYY-MM-DDTHH:MM`；
  `load_runs(until=...)` 半开窗口；`build_report(until=, limit=20, detail=False)` 产出 `until`/`runs`/`runs_total`；
  文本首行 `usage <since> → <until> (<window>)`。
- T-09（`um-t09-stats-cli-detail`）：`mw.py` +35/−1（纯锚点插入）、`test_stats_cli.py` 修 3 红 + 7 类新用例、
  README 用量统计节、CHANGELOG 一条 bullet。零 TS 改动（窗口靠参数透传）。

PM 独立复核（非照抄 worker 报告）：

```
$ python -m pytest test_stats_cli.py test_usage.py -q   → 57 passed
$ python -m pytest test_launcher_run_ledger.py -q       → 17 passed
$ python mw.py stats --since 3h --detail --limit 4
  runs (newest first)
  showing 4 of 56 runs (--limit 0 for all)
    2026-10-21T16:18  parser-callee-qn          pcqn-design-rereview          review     timi/gpt-6.1-sol          calls 9   in 27     out 4.81k  cacheR 411k   cacheW 137k  wall -      running
    2026-10-21T16:17  mw-usage-monitor          um-t09-stats-cli-detail       coding     timi/deepseek-v4.1-flash  calls 57  in 68.4k  out 31.8k  cacheR 3.92M  cacheW 0     wall 5m27s  done
    2026-10-21T16:17  feature-ui-name-surfaces  ap-...-plan-writer-a1         phase-writer timi/deepseek-v4.1-flash calls 69  in 111k   out 29.6k  cacheR 7.18M  cacheW 0     wall -      running
    2026-10-21T16:13  feature-domain-assign-33  ap-...-plan-writer-a1         phase-writer timi/deepseek-v4.1-flash calls 45  in 104k   out 23.8k  cacheR 3.76M  cacheW 0     wall -      running
$ python mw.py stats --since 1d --json --limit 2   → runs 2, runs_total 229, "until" in report = True
$ python mw.py stats --since 7d --until 2020-01-01 → stderr "mw stats: --until must be after --since", rc=2
$ python mw.py stats --since 7d --until nope       → stderr "[mw stats] invalid --until 'nope'; use 7d / 24h / 30m / YYYY-MM-DD / YYYY-MM-DDTHH:MM", rc=2
```

结论：AC-014（上界半开窗口 + rc=2 语义）、AC-015（明细行含 key/task/type/model/四 token 分量/wall/status）、
AC-016（`open_run=true` ⇒ `wall_s=None` + `wall_kind="none"`，上面第 1/3/4 行的 `wall -`+`running` 即此语义）、
AC-017（零 TS 改动，窗口参数透传）均达成。仍未在 TUI 里手动敲一次 `/mw stats --detail`（窗口本窗口进程早于
bundle，需 `/reload`），属可见性验证而非功能缺口。

### 过程记录

- T-08 首卡因段落顺序（`## 改动历史` 在 `## 上下文` 之前）被派发器打乱，envelope 校验 1s 失败，未产生任何文件改动；
  按 T-03 的段落顺序重写后重派（r2）即成功。T-09 卡片同样先做了顺序修正。
- T-09 第一次运行 55s 后异常退出且无 `output.md`，serve 自动重派后成功；最终产物以复核结果为准。

## V-7 v0.4/v0.5 复核（2026-10-21，静态 HTML + 全量 run）

用户两轮追加：①「窗口可读性有限，做一次刷新后用静态 HTML 展示，`--detail` 后自动打开」；
②「都 html 了就把 run 都展示吧」。PM 写入 spec §12（v0.4 R11–R14 / AC-018–021）与 §13（v0.5 R15–R17 / AC-022–024），
三轮 worker 交付：T-10 渲染器、T-11 CLI（`--html` / `--no-open` / 自动打开）、T-12 全量 run 内核、
T-13 CLI 接线（`include_all_runs` + `--json` 不自动弹窗）。

PM 独立复核（真实命令，非照抄报告）：

```
$ python -m pytest test_stats_cli.py test_usage.py -q          → 83 passed
$ python mw.py stats --since 24h --detail --no-open
  → 文本末尾 `html: C:\Users\wenbozhou\.mw\usage\reports\usage-20261021-171913.html`
  → 该文件 76352B，标题 `<h2>runs (newest first) · 189</h2>`，明细 189 行 = runs_total 189，
     全篇无 `showing`、无 `http`、无 `<script`
$ python mw.py stats --since 2h --json --detail          （stderr 分离）
  → stdout 纯 JSON：11 键，无 `runs_all`，runs 20 / runs_total 72
  → stderr：`[mw stats] note: --json suppresses the full run table`（未弹浏览器）
```

语义分工（AC-022/AC-023/AC-024）：`--limit` 只截**文本**与 **JSON `runs[]`**；HTML 恒为窗口内全量，
数据来自同一批 run（`runs_all` 与 `runs` 同源同序），超过 2000 行时加 Ctrl+F 提示。
`render_html` 单文件自包含（内联 CSS、无外链/CDN/远程脚本），台账字段全部 HTML 转义。

### 强制偏差（PM 接受）

T-13 把 `test_stats_cli.py` 里 `test_cmd_stats_html_writes_self_contained_report` 的旧断言
`<h2>runs (newest first)</h2>` 收紧为 `<h2>runs (newest first) · 1</h2>` + 「无 `showing`」：
旧断言与 spec §13.2 R15 直接冲突（标题必须带总数），收紧后与 `test_usage.py` 的锁定一致，未削弱覆盖面。

### 数据新鲜度（回答用户第 1 问）

两次调用相隔 26 秒：`calls 4950 → 4953`、`output 3901549 → 3924382`（Δ +3 / +22833），`generated_at` 每次变化。
无 rollup/缓存：台账全量重读 + 按窗口重扫会话文件，运行中的 worker 反映最近一次落盘，`end` 行等 reap。

## V-8 v0.6 / v0.7 复核（2026-10-21）

### v0.6 `runs[].project`（T-14，提交 e6523ed14）

- `pytest test_usage.py test_stats_cli.py` → 89 passed（含 T-15 文档用例后 110 passed）。
- 真实台账：6h 窗口 HTML `107` 行、`project=null` 行 `0`；表头顺序 `<th>started_at</th><th>project</th>`，
  单元格 `<td title="H:\git\E2Feature">E2Feature</td>`（basename 文本 + 转义 title 全路径）。
- JSON 保留原始路径；与 `by project` 分组同源。
- 6h 窗口 project 分布：`E2Feature 63 / Multi-Workers 61 / FeatureMigrator 20 / OverCode 17 / UEMigrator 3 / tmp 若干`。

### v0.7 窗口面机器级（T-16，提交 9bef2152b）

复核动机：用户反馈「project 只剩一个 Multi-Workers 了」。定位：`mw-runner.ts:508 runMwCliRaw`
对所有子命令无条件追加 `--project=<control root>`；证据 `~/.mw/usage/reports/usage-20261021-174136.html`
196 行全部 `H:\git\Multi-Workers`，而同窗口 CLI 生成的 `usage-20261021-174311.html` 210 行含 6 个项目。

- `pytest test_stats_cli.py test_usage.py -q` → `91 passed`（提交树 temp worktree 复跑同样 91 passed）。
- `mw stats --since 24h --json` 与 `--all-projects` → `runs_total` 均 `209`（两次运行间隔 208→209，等值关系成立）。
- `mw stats --all-projects --project H:/git/Multi-Workers` → stderr `mw stats: --all-projects conflicts with --project`，rc=2。
- `vitest --run test/suite/mw-stats-surface.test.ts` → `8 passed`（bare spawn = `["stats"]`，`project_appends=0`）。
- 入库快照泄漏检查：`mw.py` 无 `cmd_decide/decide_p/decide_archive/dispatch_module`；README 无 `决策服务（mw decide）/claims 派发契约`；
  CHANGELOG 无 `decision substitution/claims block`；`mw-runner.ts` 无 `decideMw/DECIDE_CONCLUSIONS`。
- 未验证：窗口 bundle 未重建（`mw build --install` 因其它会话 WIP 反向 dirty 而拒绝；加 `--allow-dirty` 会把未提交的
  decide/triage 代码打进 bundle，留给用户决定），故 `/mw stats` 新语义需下次 build + `/reload` 才生效。
