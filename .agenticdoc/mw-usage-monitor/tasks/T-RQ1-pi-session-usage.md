# T-RQ1: pi 会话 usage 全貌与 worker/PM 精确归因（research）

- Key: mw-usage-monitor
- type: research
- 写面：只读仓库与本机数据；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「mw 后台服务：LLM 代理 + 任务调度器」「文件驱动的去中心化协调」；本次新增「本机 token/耗时监控」是框架可观测性面）。
- 本 key 的需求决策（用户已定，**不要重新讨论**）：机器级存储 `~/.mw/usage/`；只统计 tokens（不算钱）；响应时间只用低成本墙钟；pi 窗口要有 `/mw stats` 简报；台账行带 `source=worker|pm`。
- PM 已复核的既有事实（**不要重复发现**，只在此基础上深挖）：
  - pi 会话落在 `~/.pi/agent/sessions/<项目slug>/*.jsonl`，本机现有 4065 个文件；首行是 `{"type":"session","version":3,"id":...,"cwd":...}`。
  - assistant 消息记录带 `model`、`provider`、`usage{input,output,cacheRead,cacheWrite,totalTokens,cost,cacheWrite1h}` 与 `timestamp`（实测样本 `2026-10-16T03-51-18-331Z_01a142d5-ec3b-747d-b5a8-25ec12206686.jsonl`，`stopReason=toolUse`）。
  - pi CLI 有 `--session` / `--session-id` / `--session-dir`（`packages/coding-agent/src/cli/args.ts:108`、`:110`、`:114`），并有环境变量 `PI_CODING_AGENT_SESSION_DIR`（`packages/coding-agent/src/config.ts`，`ENV_SESSION_DIR`）。
  - 现在没有任何 `mw usage/stats/monitor` 命令；worker 会话与 PM 会话混在同一 sessions 目录（靠正文里出现 task.md 路径归因会误判，PM 已实测误判）。

## 要求

1. **会话 JSONL 完整 schema**：所有 `type` 取值及其含义；`usage` 出现在哪些记录上（是否只有 assistant 消息）；一条 assistant 消息是否可能聚合多次重试（`api`/`responseId`/`rawStopReason` 的作用）；`usage.cost` 在各 provider（timi / anthropic / openai-codex / zai）下的实际取值；`cacheWrite1h` 是否总为 0。给 `packages/coding-agent/src/**` 里写这些字段的 `文件:行号` 与原文。
2. **多版本兼容**：本机 4065 个会话里存在哪些 `version`；不同版本字段差异（尤其 `usage` 是否曾叫别的名字/少字段）；给出实测统计（Python 扫一遍，按 version 计数 + 缺 usage 的 assistant 消息数）。
3. **`--session-id` / `--session-dir` / 环境变量语义**：指定后落盘文件名规则（是否仍是 `<timestamp>_<id>.jsonl`）、目录不在默认 sessions 根时是否仍可被 `/resume` 发现、id 是否强校验（`assertValidSessionId` 允许的字符集）、`--session <x>` 接受 id 还是路径、与 `PI_CODING_AGENT_SESSION_DIR` 的优先级。给出 `文件:行号` 与必要的实测（可在一个临时目录跑 `pi --session-dir <tmp> -p "say ok"`，**只读仓库，临时目录放 %TEMP%**；若耗时或需凭据则跳过实测并写明未验证）。
4. **worker vs PM 的确定性识别方案**：现有数据里是否已有可用信号（会话首行 `cwd`、`env`、argv、`PI_WORKER_TASK` 是否被记录进会话）；若没有，给出「launcher 为每个 worker 显式分配 session id 并记入台账」的具体接口建议（哪个函数、传什么参数、如何避免与 PM 默认目录冲突、孤儿/崩溃时如何处理）。**这是 spec 的关键输入，请给出可直接落地的参数形态**。
5. **扫描成本实测**：本机 sessions 总字节数、单文件大小分布；用 Python 扫「最近 7 天」全部会话并汇总 usage 的耗时（给命令与实测秒数）；据此说明 `mw stats --since 7d` 按需扫描是否可行，以及是否必须 rollup 缓存（给阈值建议）。
6. **PM 窗口会话的可统计性**：PM 会话（无 dispatch 记录）能否同样按 model/tokens/墙钟统计；如果能，靠什么字段界定一次「PM 会话」（首行到末行时间差？`type:session` 的 timestamp？轮次记录？）。

## 唯一证据文件

`.agenticdoc/mw-usage-monitor/evidence/research/spec-rq1-pi-session-usage-20261019.md`

用 `bash` + Python heredoc 直接写该路径（框架写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。**不得写其它任何文件**。

## 交付格式

- `## 0. 结论先行`（≤6 条，可直接被 spec 引用）→ `## 1…6` 逐问作答 → `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；数字给实测命令与输出；未找到写「未找到（命令 + 输出）」，**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`（框架按整篇别名子串判定，缺段会被判 needs-clarification）。

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest（本机墙钟无超时，实测会挂死）。只读命令与 Python 只读扫描允许；临时文件放 `%TEMP%`。
