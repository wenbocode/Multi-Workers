# 验证证据 — mw-decision-substitution（T-10 / W6 全量验证 + 度量复核）

- key: mw-decision-substitution · 卡片: `tasks/T-10-docs-verify.md` · 执行者: worker `ds-t10-docs-verify`
- 运行时间: 2026-10-20 16:55–17:12（本机 local，UTC+8）
- 本卡**只改文档**（`docs/decision-substitution.md`、`packages/multi-workers/README.md`、两个 CHANGELOG），
  无代码改动；因此下面所有失败都是**既有基线或其它会话在途改动**，逐条归类见 §3/§4。
- 证据目录：`.mw/runs/t10-pytest-20261020/`、`.mw/runs/t10-vitest-20261020/`、
  `.mw/runs/t10-vitest-runtime-20261020/`、`.mw/runs/t10-vitest-keysuites-20261020/`、
  `.mw/runs/t10-tsgo2-20261020/`（各含 `cmd.txt`/`run.log`/`marker.json`/`heartbeat.json`）。

## 1. 结论摘要

| 项 | 结果 | 与 PM 基线对比 |
| --- | --- | --- |
| Python 全量 `pytest -q` | `9 failed, 2728 passed, 10 deselected, 2 warnings in 513.94s` | 基线 `8 failed, 2729 passed`（496.72s）→ **+1 失败 / −1 通过**，新增那条是**测试间污染探测器**，单文件隔离跑 11 passed（§3） |
| TS 全量（`test/suite` + `agent-team-loop.test.ts`） | `Test Files 9 failed \| 147 passed \| 1 skipped (157)`；`Tests 19 failed \| 1837 passed \| 3 skipped (1859)`，278.60s | 基线 `18 failed \| 1838 passed` → **+1 失败**，新增那条是 `agent-session-runtime` 在并发负载下的 30s 超时（该文件隔离跑复现基线的 7 条，§4.2） |
| 本 key 新增/改动套件复跑 | **169 passed / 8 files / 0 failed**，4.13s | 全绿（卡片的 166 条基线因后续会话补测现为 169） |
| `tsgo --noEmit` | **rc=0**，5.0s，无输出 | 干净 |
| `biome check <本卡改动文件>` | `Checked 0 files`，rc=1（"No files were processed"） | 本卡只改 Markdown，biome 不处理 `.md`；**不是 lint 失败**（§6） |
| 度量基线复核（pi 会话 JSONL） | jev key 窗内 **5 条人工消息**，gap `13.60/6.66/2.33/50.37/20.27` min，**合计 93.222 min**，**中位 13.600 min** | 文档基线 93.3 min / 13.6 min → **一致**（93.3 = 逐条 1 位小数相加） |

## 2. 命令与「为什么不是 ./test.sh + npm run check」

卡片验收命令段（PM 已实测调整）明确：本机没有可用的 WSL，`./test.sh` 不可执行；`npm run check` 带
`biome check --write`，会改写其它会话的在途文件。因此按调整后的清单执行：

```bash
# 1) Python 全量
cd packages/multi-workers && python -m pytest -q

# 2) TS 全量（test/ 与 test/suite/，不含 e2e）
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite test/extensions/agent-team-loop.test.ts

# 3) 静态检查（无 --write）
node node_modules/@typescript/native-preview/bin/tsgo.js --noEmit      # 等于 npx tsgo --noEmit
npx biome check docs/decision-substitution.md packages/multi-workers/README.md \
                packages/multi-workers/CHANGELOG.md packages/coding-agent/CHANGELOG.md
```

两条长跑命令经 `mw run-detached` 后台执行（`rc`/`timed_out` 见各自 `marker.json`），未触发超时。

## 3. Python 全量（`packages/multi-workers`）

```text
cmd:    python -m pytest -q          (cwd=packages/multi-workers)
marker: rc=1  timed_out=false  wall_sec=520.1
tail:   9 failed, 2728 passed, 10 deselected, 2 warnings in 513.94s (0:08:33)
```

### 3.1 与基线对比

| | 失败 | 通过 | 墙钟 |
| --- | --- | --- | --- |
| PM 基线（2026-10-20，卡片记录） | 8 | 2729 | 496.72s |
| 本次 | 9 | 2728 | 513.94s |
| 差值 | **+1** | **−1** | +17.2s（同机并发跑 TS 全量，负载更高） |

### 3.2 逐条归因

基线 8 条**全部复现**（与卡片列出的名字逐字一致，属既有 Windows 环境基线，与 AGENTS.md 记录同类）：

| # | 失败用例 | 归因 |
| --- | --- | --- |
| 1 | `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` | 既有基线（Windows 路径/边界） |
| 2 | `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` | 既有基线 |
| 3 | `test_launcher.py::TestTaskTypeCallsiteWiring::test_bom_historical_books_read_through_both_callsites` | 既有基线（BOM 编码 + Windows） |
| 4 | `test_mwds_t10_dispatch_run_state.py::test_missing_run_json_dispatches_byte_identically` | 既有基线（其它 key 的字节基线漂移） |
| 5 | `test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge` | 既有基线（跨语言 parity，TS 侧在途改动） |
| 6 | `test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge` | 既有基线（同上） |
| 7 | `test_mwgal_t13_drift_identity.py::test_process_start_ms_probe` | 既有基线（进程启动毫秒探针） |
| 8 | `test_task_type_parity.py::test_bom_historical_books` | 既有基线（BOM + Windows） |

本次**新增**的 1 条：

| 失败用例 | 断言 | 归因（实测） |
| --- | --- | --- |
| `test_mw_console_guard.py::test_isolation_parent_process_subprocess_unpatched` | `subprocess.Popen.__init__.__name__ == "__init__"`，实得 `"patched"` | **全量运行内的测试间污染探测器**：某个前序用例把 `Popen.__init__` 打了补丁未复原。隔离复跑该文件：`python -m pytest test_mw_console_guard.py -q` → **11 passed in 0.63s**。属测试隔离/顺序问题（console-guard 面，另一 key 的在途工作），**与本卡的文档改动无因果关系**。 |

判据：本卡 `git status` 只有三个 `.md` 修改 + 一个新 `.md`；Python 侧无任何改动，不可能改变上述断言结果。

## 4. TS 全量（`packages/coding-agent`）

```text
cmd:    node ../../node_modules/vitest/dist/cli.js --run test/suite test/extensions/agent-team-loop.test.ts
marker: rc=1  timed_out=false  wall_sec=280.4
tail:   Test Files  9 failed | 147 passed | 1 skipped (157)
        Tests  19 failed | 1837 passed | 3 skipped (1859)
        Duration  278.60s (transform 59.91s, setup 0ms, import 245.98s, tests 667.31s)
```

### 4.1 与基线对比

| | 失败文件 | 失败用例 | 通过用例 |
| --- | --- | --- | --- |
| PM 基线（卡片记录） | 9 | 18 | 1838 |
| 本次 | 9 | 19 | 1837 |
| 差值 | 0 | **+1** | **−1** |

### 4.2 逐条归因（19 条，按类）

| 类 | 用例 | 条数 | 归因与判据 |
| --- | --- | --- | --- |
| Windows shell/path | `regressions/5109-exclude-tools.test.ts` ×2 | 2 | 本机默认 shell 是 `powershell` 而非 `bash`（实测 `expected ['powershell'] to deeply equal ['bash']`） |
| Windows shell/path | `regressions/3302-find-path-glob.test.ts` ×3 | 3 | `find` 的 path-glob 在 Windows 上返回空集 |
| Windows shell/path | `regressions/2791-fswatch-error-crash.test.ts` | 1 | 子进程加载 ESM 时 `ERR_UNSUPPORTED_ESM_URL_SCHEME`（`h:` 盘符路径） |
| Windows shell/path | `regressions/3592-no-builtin-tools-keeps-extension-tools.test.ts` | 1 | 同上（`powershell` vs `bash`） |
| Windows/timeout | `agent-session-runtime.test.ts` ×**8** | 8 | 30s 超时（`Error: Test timed out in 30000ms`）。**隔离复跑同文件：`7 failed \| 4 passed (11)`，274.87s** → 基线 7 条稳定复现，第 8 条是本次全量与 Python 全量并发时多溢出的一条超时（负载相关，非产品回归） |
| 其它会话在途改动 | `rag-tools.test.ts` | 1 | 期望工具集不含 `mw_run_detached`，实得含（另一会话在 `worker-mode.ts` 新增该工具） |
| 其它 key 卡片语料 | `mwds-t02-write-intent.test.ts` | 1 | AC-005a 语料回放 false positive（`qg-review-*` 等 19 条），属另一 key 的卡片语料，与本卡无关 |
| 未重建 bundle | `mwds-t23-cutover-recheck.test.ts` | 1 | 期望 bundle sha `975D4066…`，实得 `DB0147AD…`：需 `mw build --install` 重建（属用户放行后的步骤） |
| 既有锚点漂移 | `agent-team-loop.test.ts > T-17/B-1 anchor integrity` | 1 | 命中的是**另一个 key** 的文档锚点：`.agenticdoc/mw-guard-form-hardening/design.md worker/worker-mode.ts:747`；本卡文档未被该检查收集（它只扫 `spec.md`/`design.md`） |
| 合计 | | **19** | |

### 4.3 本 key 新增/改动套件复跑（全绿）

```text
cmd: node ../../node_modules/vitest/dist/cli.js --run \
       test/suite/decision-association.test.ts test/suite/decision-signoff.test.ts \
       test/suite/decision-tool.test.ts test/suite/dp2-narrow.test.ts \
       test/suite/dp3-answer.test.ts test/suite/triage-client-state.test.ts \
       test/suite/triage-dispatch.test.ts test/suite/xkey-gate-guard-coverage.test.ts
out: Test Files  8 passed (8)
     Tests  169 passed (169)
     Duration  4.13s
```

卡片记录的基线是 7 组共 166 条（35+30+13+31+21+17+19）；现测 169 条，多出的 3 条是这些文件后续被
其它会话/卡片补的用例，全部通过。

## 5. 静态检查

| 命令 | 结果 | 说明 |
| --- | --- | --- |
| `npx tsgo --noEmit`（首次） | `rc=127`，`spawn_failed=true` | `mw run-detached` 不经 shell，Windows 下无法直接执行 `npx.cmd`；命令形态问题，非代码问题 |
| `node node_modules/@typescript/native-preview/bin/tsgo.js --noEmit` | **rc=0**，5.0s，`run.log` 空 | 全仓类型检查干净（本卡无 TS 改动，此结论同时覆盖其它会话在途改动） |
| `npx biome check docs/decision-substitution.md packages/multi-workers/README.md packages/multi-workers/CHANGELOG.md packages/coding-agent/CHANGELOG.md` | `Checked 0 files in 6ms`，rc=1，提示 `No files were processed in the specified paths`（四条路径全部 "ignored"） | biome 2.3.5 不处理 Markdown；本卡改动的 4 个文件全是 `.md`，因此**没有可检目标**。这是「无适用文件」，不是 lint 报错（与 `npm run check` 里 biome 处理 TS/JS 的作用域不同） |

## 6. 度量基线复核（人工轮次 / 阻塞墙钟）

### 6.1 方法与来源

数据源：pi 会话 JSONL（PM 窗口）。目录 `C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\`
（1448 个文件），本次复核文件
`2026-10-15T06-30-17-079Z_01a13e41-1cf7-7714-a96b-011423325da6.jsonl`（5.49 MB，1756 条 entry，
首行 header `cwd: H:\git\Multi-Workers`）。方法与
`evidence/research/spec-decision-metrics-20261016.md` §Q1/Q2 一致：

- **人工消息** = `type == "message"` 且 `message.role == "user"`，并排除三类机器源：
  派发卡（正文含 `.agenticdoc/<key>/workers/<task>` 路径）、扩展注入提示（正文以 `[agent-team-loop]` /
  `[mw ` 开头）、非交互来源（`entry.source` 存在且不为 `interactive`）。
- **阻塞墙钟** = `t_{H} − t_prev`，`t_prev` = 该条人工消息之前最后一条非 user entry（assistant /
  toolResult / custom_message）的时间戳；时间戳是 entry 追加时刻（UTC ISO 毫秒）。
- **key 归属** = key 活跃窗（`pm-state.md` 的 `Started`/`Completed` + Process Log 尾巴）。
  jev key：local 2026-10-16 17:09 → 19:52，日志尾延至 21:2x ⇒ 取 UTC `2026-10-16T09:00Z … 14:00Z`。

一次性离线复算（不落脚本文件、不改代码；经 stdin 喂给 `python -`）。

### 6.2 复算数字

jev key 窗内（UTC 09:00–14:00）5 条人工消息：

| # | 时间 (UTC) | gap (min) | 内容（截断） |
| --- | --- | --- | --- |
| 1 | 09:05:58 | 13.600 | 路线B，不用当聊天，就跑决策，不需要 typesafe.ai 的账号… |
| 2 | 09:16:41 | 6.660 | D-1 是不是不需要了，jev 模型只做决策… |
| 3 | 09:20:12 | 2.330 | 按你推荐 |
| 4 | 12:43:24 | 50.365 | 起一个 review worker 来做 qg 和 review |
| 5 | 13:23:53 | 20.267 | 怎么测试呢，给我画个当前 jev 接入的流程图 |

- **合计 93.222 min = 5593 s**，**中位 13.600 min**（n=5）。
- 同一文件全量（2026-10-15 06:33 → 2026-10-20 07:14）：36 条人工消息，gap 合计 6853.1 min、
  中位 6.8 min —— 该数字被「跨夜/跨日空闲」（最长 3941 min）主导，**只能作量级参考**，不能当阻塞墙钟用。
  这正是 Q2 精度限制 1（blocked vs idle 不可分）的实证。

### 6.3 与文档基线的一致性

| | 人工消息数 | gap 合计 | 中位 |
| --- | --- | --- | --- |
| `spec-decision-metrics-20261016.md` §Q2 基线 | 5 | **93.3 min** | **13.6 min** |
| 本次复算 | 5 | **93.222 min**（5593 s） | **13.600 min** |
| 差异 | 0 | +0.078 min ≈ 5 s | 0 |

差异来源可完全解释：基线把逐条 gap 按 1 位小数相加（`13.6+6.7+2.3+50.4+20.3 = 93.3`），
本次用未舍入秒数求和（`93.222`）。**结论：基线 93.3 min / 中位 13.6 min 可复现。**

附带发现（不影响结论）：`2026-10-16` 全天该会话有 **10** 条人工消息，基线文档列的是 9 条 gap；
差额那条是 `03:40:26Z`（gap 723.65 min，从 10-15 夜间算起，属前一 key 的尾巴），基线按 key 窗
过滤时未计入，与本次口径一致（本次 key 窗同样不含它）。

## 7. 与基线总表

| 面 | 基线 | 本次 | 判定 |
| --- | --- | --- | --- |
| Python 失败 | 8 | 9 | +1（测试间污染探测器；单文件 11 passed） |
| Python 通过 | 2729 | 2728 | −1（同上） |
| TS 失败文件 | 9 | 9 | 持平 |
| TS 失败用例 | 18 | 19 | +1（`agent-session-runtime` 负载相关超时；隔离跑 7 条同基线） |
| TS 通过用例 | 1838 | 1837 | −1（同上） |
| 本 key 套件 | 166（7 组） | 169（8 文件全绿） | 全绿 |
| `tsgo --noEmit` | 干净 | rc=0 | 一致 |
| 度量基线 | 93.3 min / 13.6 min | 93.222 min / 13.600 min | 一致 |

## 8. 残留与未验证

1. **关闭态字节同构未在本卡重测**：本卡只改文档，未重跑「dp 全关 vs 未启用」的端到端 run（该证明在
   T-06/T-07b 的套件里，本次全量运行中全绿）。若要端到端证据，需要一次真实 run 事件 + 档案行对照。
2. **`mw build --install` 未执行**（用户放行后才做），因此 `mwds-t23-cutover-recheck` 的 bundle sha
   断言仍是本次唯一「本 key 相关但未收口」的失败项（另 18 条与本 key 无关）。
3. **`npm run check` 未跑**（卡片明确禁止：带 `biome --write`）。因此 `check:pinned-deps` /
   `check:ts-imports` / `check:shrinkwrap` / `browser-smoke` 未在本次覆盖范围内。
4. **`./test.sh` 未跑**（本机无 WSL，卡片已改口径）。Python + TS 两个全量命令是等价替代面，
   但 `test.sh` 里若有额外编排（例如串行顺序、环境变量归一），本次没有覆盖。
5. **度量口径的已知精度限制未消除**：blocked vs idle 不可分、`sendUserMessage` 型扩展提示靠前缀
   启发式过滤、多窗口并行时 per-key 归属只能近似（见 `spec-decision-metrics` §Q2 限制 1-3）。
   本次复核只证明「基线数字可复现」，不证明「93.3 min 全是阻塞时间」。
6. **`test_mw_console_guard` 的污染源未定位到具体用例**（属别的 key 的写面，本卡无权改）：只证明了
   「单文件隔离跑 11 passed」，未定位是哪个前序测试漏了 `Popen` 复原。
