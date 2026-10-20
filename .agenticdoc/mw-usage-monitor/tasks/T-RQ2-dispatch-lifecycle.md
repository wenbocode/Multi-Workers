# T-RQ2: mw 派发链路元数据与墙钟时间点（research）

- Key: mw-usage-monitor
- type: research
- 写面：只读仓库与本机数据；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「一个 PM Agent 管理多个 Worker Agent 并行开发」「Worker 进程级隔离」）。
- 本 key 的需求决策（用户已定，**不要重新讨论**）：机器级台账 `~/.mw/usage/`；只报 tokens（不算钱）；响应时间只用低成本墙钟（worker 起止）；台账行字段含 project / key / task_key / type(role) / cli / model / session_id / pid / start / end / exit；pi 窗口有 `/mw stats` 简报。
- PM 已复核的既有事实（**不要重复发现**）：launcher 用 `subprocess.Popen` 列表参数、无 shell，`running_procs: dict[str, subprocess.Popen[bytes]]` 监督子进程并 `p.poll()` / `proc.returncode` 判定结束（`packages/multi-workers/launcher.py:2317`、`:2157`、`:2162`）；`.mw/dispatch.yml` 已有 `models:` 角色默认（coding/review/research/main）与 `fallback_models:`；`.agenticdoc/_autopilot/*.jsonl` 存 conductor 时间线事件；worker 自己的 `trace.log` 有 `[FLOW] … tool_call` 与 `[TOOL]` 行。

## 要求

1. **一次 worker 运行的全部可观测元数据**：谁在什么时候知道 `project / key / task_key / type / role / cli / model / provider 前缀 / pid / cwd / 启动时刻 / 结束时刻 / exit code / 是否 fallback 换模型 / 是否超时 / 是否崩溃被重派`。逐项给 `文件:行号` + 原文片段（launcher.py 的 spawn 与 reap、`_build_command`、模型解析链、timeout watchdog、fallback 重派路径都要覆盖）。
2. **台账写入钩子点**：在 launcher 里精确指出「spawn 成功后立刻写 start 行」「reap 时写 end 行（含异常/超时/被 kill 分支）」应插在哪个函数哪一行，说明该处能拿到的局部变量名；并说明 `mw serve` 的另一个 spawn 入口（如果存在第二条 spawn 路径，如 conductor 直执、repair、xkey apply 的子进程）是否也要覆盖，列出全部 spawn 调用点（`文件:行号`）。
3. **PM 窗口的派发记录缺失面**：PM 窗口通过 `/worker`（`pm/ui-bridge.ts`）手动派发时，会不会经过 launcher 的同一入口？有没有独立的派发路径需要单独打点？给 `文件:行号`。
4. **任务类型/角色的权威来源**：`type:`（coding/review/research/rag-research/vision）与 role 的映射表在何处（`packages/multi-workers/mw_common.py`？`dispatch-table.md`？），task.md 头部的 `type:`/`model:`/`timeout:` 解析函数在何处；模型解析优先级链（task.md `model:` > dispatch.yml role > `.mw/window-model` > 硬编码默认）在哪个函数实现（给行号）。台账应记录「最终生效模型」还是「请求模型 + 来源」，给结论与依据。
5. **现有日志/台账的可复用面**：`.mw/` 目录下现有哪些运行期文件（launcher.log、worker.log、queue 文件、proxy.log…），各自格式与保留策略；`autopilot/timeline.py` 与 `.agenticdoc/_autopilot/*.jsonl` 的事件 schema（字段名逐字）；判断哪些能直接当台账用、哪些会丢信息。
6. **并发与锁**：launcher 多 worker 并发写台账需要什么锁/追加模式（仓库内已有的 `.mw/*.lock`、`O_CREAT|O_EXCL`、`tmp+os.replace` 用法给 `文件:行号` 先例）；Windows 下追加写 JSONL 的已知坑（换行、编码、并发交错）。

## 唯一证据文件

`.agenticdoc/mw-usage-monitor/evidence/research/spec-rq2-dispatch-lifecycle-20261019.md`

用 `bash` + Python heredoc 直接写该路径（框架写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。**不得写其它任何文件**。

## 写入允许面

- `.agenticdoc/mw-usage-monitor/evidence/research/spec-rq2-dispatch-lifecycle-20261019.md`
- `.agenticdoc/mw-usage-monitor/workers/um-rq2-dispatch-lifecycle/**`（本任务目录：`report.md` 与框架 readback）

## 写入禁止面

- 仓库其它任何文件（含 `packages/**`、`.mw/**`、其它 key 目录）
- `~/.pi/**`、`~/.codex/**`、`~/.claude/**`

## 交付格式

- `## 0. 结论先行`（≤6 条，可直接被 spec 引用）→ `## 1…6` 逐问作答 → `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；未找到写「未找到（命令 + 输出）」，**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest。只读检索与 Python 只读扫描允许；临时文件放 `%TEMP%`。
