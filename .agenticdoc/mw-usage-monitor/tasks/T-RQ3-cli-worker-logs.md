# T-RQ3: codex / claude CLI worker 的会话日志与 token 可统计性（research）

- Key: mw-usage-monitor
- type: research
- 写面：只读仓库与本机数据；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「Agent Team 协作框架：PM 管多个 Worker 并行」「mw 后台服务：LLM 代理 + 任务调度器」）。
- 本 key 的需求决策（用户已定，**不要重新讨论**）：机器级台账 `~/.mw/usage/`；只报 tokens（不算钱）；只用墙钟做响应时间；pi 窗口 `/mw stats` 简报；`source=worker|pm`。**范围按推荐：pi worker + PM 窗口是必须项；codex/claude CLI worker 只要能低成本读到就纳入（读不到就降级为"未统计"，不许猜）。**
- PM 已复核的既有事实（**不要重复发现**）：mw 的 worker CLI 有三类（`pi` / `claude` / `codex`，见 `.mw/dispatch.yml` 与 launcher 的 `_build_command`）；pi 侧 token 来自 `~/.pi/agent/sessions/**/*.jsonl` 的 assistant `usage`（已验证）；launcher 用 `Popen` 列表参数启动子进程并 supervise（`packages/multi-workers/launcher.py:2317`、`:2157`）。

## 要求

1. **本机是否存在 CLI 训练/运行日志**：分别查 `~/.codex/`（`sessions/`、`history`、`config.toml`）与 `~/.claude/`（`projects/**/*.jsonl`、`todos`、`statsig` 等），给出目录树、文件数、总字节、时间跨度（实测命令 + 输出）。若不存在，明确写「不存在」并说明 launcher 侧无从获得 token 的降级结论。
2. **日志 schema 与 token 字段**：逐项给出 codex 与 claude 日志里「每次模型调用」的记录形态与 token 字段名（如 `usage.input_tokens/output_tokens/cache_read_input_tokens`、`tokens_in/tokens_out`、`total_cost_usd`），给 2–3 条真实样本行（可脱敏截断）与解析后的数值；说明一条记录对应一次 API 调用还是一轮 agent turn，重试/子 agent 是否另起文件。
3. **归因方式**：能否把某个 codex/claude 会话文件确定地对应到 mw 的一次 worker 运行（可用信号：cwd、首条 user 消息里的 task_key/task.md 路径、文件创建时间落在 `[start,end]` 区间、CLI 的 session id 参数）。分别给出三种 CLI 是否支持固定 session id / 指定输出目录（`claude --session-id`、`codex exec --session`? 以本机实际 `--help` 输出为证据），以及不可靠时的保守策略。
4. **与 pi 侧的统一口径**：codex/claude 的 token 字段与 pi 的 `usage{input,output,cacheRead,cacheWrite,totalTokens}` 如何对齐（哪边缺 cache、哪边含 reasoning tokens、是否需要分别记账而不是强行合并）；给出一张对照表与「不可对齐项」清单。
5. **扫描成本**：统计「最近 7 天」codex/claude 日志的字节量与解析耗时（实测秒数）；与 pi sessions 的扫描成本比较，给出是否值得每次 `mw stats` 都扫、还是只扫台账已登记 session id 的建议。
6. **退路（必须写）**：若 CLI 日志不可用/不可归因，`mw stats` 应如何呈现（例如 `unknown_cli` 行、或在简报里显式写「codex/claude 未统计」），确保用户不会把不完整的统计当全量。

## 唯一证据文件

`.agenticdoc/mw-usage-monitor/evidence/research/spec-rq3-cli-worker-logs-20261019.md`

用 `bash` + Python heredoc 直接写该路径（框架写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。**不得写其它任何文件**。

## 写入允许面

- `.agenticdoc/mw-usage-monitor/evidence/research/spec-rq3-cli-worker-logs-20261019.md`
- `.agenticdoc/mw-usage-monitor/workers/um-rq3-cli-worker-logs/**`（本任务目录：`report.md` 与框架 readback）

## 写入禁止面

- 仓库其它任何文件（含 `packages/**`、`.mw/**`、其它 key 目录）
- `~/.pi/**`、`~/.codex/**`、`~/.claude/**`（只读解析）

## 交付格式

- `## 0. 结论先行`（≤6 条，可直接被 spec 引用）→ `## 1…6` 逐问作答 → `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据给 `文件:行号` 或「命令 + 真实输出片段」；未找到写「未找到（命令 + 输出）」，**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。

## 只读边界

不得修改仓库任何文件；不得修改 `~/.codex` / `~/.claude` / `~/.pi` 下任何文件（只读解析）；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest；禁止发起真实 LLM 调用（不要为了拿样本而跑 codex/claude/pi）。
