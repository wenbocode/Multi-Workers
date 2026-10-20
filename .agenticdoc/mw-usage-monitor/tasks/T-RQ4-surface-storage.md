# T-RQ4: `mw stats` 命令面、`/mw stats` 窗口转发与机器级存储约定（research）

- Key: mw-usage-monitor
- type: research
- 写面：只读仓库与本机数据；只写唯一证据文件 + 本任务目录 `report.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行」「agent-team-loop 扩展（TS）：PM 模式 + Worker 模式」「不修改 pi 核心：所有功能通过 Extension API 实现」）。
- 本 key 的需求决策（用户已定，**不要重新讨论**）：机器级台账 `~/.mw/usage/`（如仓库已有更合适的机器级目录约定，指出并给依据）；只报 tokens（不算钱）；只用墙钟；pi 窗口要有 `/mw stats` 简报（另有 CLI `mw stats`，支持 `--since/--key/--type/--model/--json` 之类过滤，具体形态你给建议）。
- PM 已复核的既有事实（**不要重复发现**）：`packages/multi-workers/mw.py` 用 argparse 子命令（`serve/start/target/model/init/pull-agentictask/push-agentictask/setup/build/...`），现在**没有** usage/stats/monitor 子命令；pi 窗口的 `/mw` 命令在 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 注册并转发到 mw.py；`.mw/` 是项目运行期目录（含 `dispatch.yml`、`launcher.log`、`worker.log`、`proxy.log`）。

## 已知起点坐标（只是起点，**不得以此为界**）

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:167`（`/mw` 子命令/键切换转发面的现有实现起点）
- `packages/multi-workers/mw.py:5195`（`_global_ext_dir`，机器级路径助手先例）
- `packages/multi-workers/mw.py:282`（`proxy_log = open(mw_dir / "proxy.log", "a", ...)`，项目运行期文件写法先例）

## 要求

1. **`/mw` 子命令注册与转发全貌**：`ui-bridge.ts` 里命令分发结构（switch/表驱动？）、参数如何透传给 mw.py、如何拿 stdout 回显（notify 还是面板）、失败与 stderr 如何呈现；给 `文件:行号` + 现有子命令（如 `/mw model show`、`/mw doctor`）的完整调用链作为可复制模板。指出新增 `/mw stats` 需要改的最小文件集。
2. **CLI 子命令落位**：`mw stats` 应加在 `packages/multi-workers/mw.py` 的哪个位置（argparse 结构 `文件:行号`），输出格式约定（人读表格 vs `--json`），以及现有命令里「表格/JSON 双输出」的最好先例（给 `文件:行号`，说明其列宽/对齐实现，避免自造）。
3. **机器级目录约定**：仓库里除 `~/.pi/agent`（protected）外已有哪些**机器级**路径常量/助手（`mw_common.global_ext_dir`、`.mw-py-path`、`~/.agents/rag-servers.yml` 等），逐项给 `文件:行号`；判断 `~/.mw/usage/` 是否与现有约定冲突（会不会被误当项目目录、Windows 下 `~/.mw` 与 `%USERPROFILE%\.mw` 的解析、`expanduser` 用法先例）。若认为应换成别的机器级位置，给理由与替代路径。
4. **追加写与并发安全先例**：仓库内 JSONL/JSON 追加与原子写既有实现（`tmp+os.replace`、`O_CREAT|O_EXCL` 锁、`fcntl`/msvcrt 缺失时的做法），逐项 `文件:行号`；给出「多个 launcher 并发 append 同一 JSONL」的推荐写法（含 Windows 换行/编码坑），以及 rollup 文件（`rollup-YYYY-MM-DD.json`）的安全重写方式。
5. **汇总口径与呈现建议**：基于已有数据形态，给出 `mw stats` 默认简报的最小列集（按模型 / 按任务类型 / 按 key / 按项目 各一行组），以及「墙钟」该用哪些分位数、样本不足时如何标注；不要发明新指标名，优先复用仓库既有术语（如 `tokens in/out/cache`、`wall`、`p50/p90`）。附 1 个**样例输出**（纯文本示意，标注为样例）。
6. **测试落位**：新增 `mw stats` 的 pytest 测试应放哪个文件/命名风格（列举 2–3 个同类先例 `文件:行号`）；`/mw stats` 的 TS 侧是否已有可测入口（vitest 用 `ui-bridge` 现有测试？给路径）；以及是否需要在 `mw doctor` 里加一个 `usage` 段（给 doctor 段注册点 `文件:行号`，并说明加与不加的取舍）。

## 唯一证据文件

`.agenticdoc/mw-usage-monitor/evidence/research/spec-rq4-surface-storage-20261019.md`

用 `bash` + Python heredoc 直接写该路径（框架写面允许 `<key>/evidence/**`）；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。**不得写其它任何文件**。

## 写入允许面

- `.agenticdoc/mw-usage-monitor/evidence/research/spec-rq4-surface-storage-20261019.md`
- `.agenticdoc/mw-usage-monitor/workers/um-rq4-surface-storage/**`（本任务目录：`report.md` 与框架 readback）

## 写入禁止面

- 仓库其它任何文件（含 `packages/**`、`.mw/**`、其它 key 目录）
- `~/.pi/**`、`~/.codex/**`、`~/.claude/**`；不得启停 `mw serve`

## 交付格式

- `## 0. 结论先行`（≤6 条，可直接被 spec 引用）→ `## 1…6` 逐问作答 → `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；未找到写「未找到（命令 + 输出）」，**禁止推测补齐**。
- 末尾一行 `[VERIFY] <数值> …`。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。

## 只读边界

不得修改仓库任何文件；禁止 `npm install|ci`、`npm run build`、`git checkout|reset|clean|stash`、全量 pytest/vitest；不得启动/停止 mw serve、不得写 `~/.pi`。只读检索与 Python 只读脚本允许；临时文件放 `%TEMP%`。
