# Achieved: mw-usage-monitor

机器级 usage（token / 墙钟）监控：`mw stats` CLI + `/mw stats` 窗口面 + 静态 HTML 报告。
从 v0.1（核心台账与四分量归因）迭代到 v0.8（夹具折叠），全部入库并验证。

## 交付物

| 面 | 产物 |
|----|------|
| 台账写入 | `launcher.py`：worker spawn 写 `start`、reap 写 `end`/`spawn_failed`，并分配 `mw-<key>-<pid>-<seq>` 会话 id；`~/.mw/usage/runs.jsonl` append-only，只存元数据 |
| 查询内核 | `usage.py`：`load_runs` / `build_report` / `format_report_text` / `render_html`；token 四分量从 pi/claude 会话日志**只读 join**，不复制、不落第二份 |
| CLI | `mw.py cmd_stats`：`--since/--until/--key/--type/--model/--project/--all-projects/--source/--detail/--limit/--html/--no-open/--json` |
| 窗口面 | `mw-runner.ts statsMw` + `ui-bridge.ts runMwStatsCommand`：薄包装，Python 单一解析/渲染方 |
| 文档 | `packages/multi-workers/README.md`「用量统计（mw stats）」节（flag 表、明细样例、数据落点）、CHANGELOG |

## 系统行为变化

- **新增 CLI 面**：`mw stats` 系列（详见 README）。机器级、跨项目，默认窗口 7d；`--detail` 追加逐 run 明细并同时生成 HTML 报告；`--json` 输出固定契约（无 cost/金额字段）。
- **新增窗口命令**：`/mw stats [<同参数>]`，输出文本简报；**默认机器级**（v0.7 起不再隐式追加 `--project=<control root>`，要收窄就显式 `--project`）。
- **台账副作用**：launcher 在每次派发/回收时写 `~/.mw/usage/runs.jsonl` 两行；文件只追加，靠 `runs.jsonl.lock` 互斥。分析/删除该文件会丢历史墙钟，不影响 token 事实（token 来自会话日志）。
- **HTML 报告**：每次调用在 `~/.mw/usage/reports/usage-YYYYMMDD-HHMMSS.html` 落一个新文件（从不覆盖），`--detail` 会调默认浏览器打开；`--no-open` / `MW_STATS_NO_OPEN=1` 关闭。页面是单文件自包含（内联 CSS，无外链/无脚本/CDN），台账字段全部转义。
- **归因口径**：worker 的 token 只按 launcher 分配的 session-id 归属（不做文本匹配）；codex/claude 无可用日志时 `attribution=unknown_cli`、token 显示 `-`；PM 会话按自身 span 统计，墙钟标注 `*`（不是 worker 墙钟）。
- **分组展示**：`by project` 把测试夹具 cwd（`%TEMP%` / `/tmp` / `/var/folders` / `C:\Windows\Temp` 之下，或 basename `pi-runtime-*`）折叠成一行 `(test fixtures)`；事实层（`runs[].project`、明细表）保持原始路径。
- **无破坏性变更**：`usage.py`/`mw stats` 是新文件/新子命令；`mw.py`、`mw-runner.ts`、README、CHANGELOG 的改动都是新增，未触碰既有子命令语义。

## 遗留

- **窗口 bundle 与 decide 的取舍**：为保证 `/mw stats` 新语义，全局扩展 bundle 是从 HEAD 构建安装的，未包含另一会话未提交的 `/mw decide` 代码。对方提交后需 `mw build --install` 重新打包；在此之前窗口内 `/mw` 的 decide 子命令不可用。去向：等对方 WIP 提交后重新 build（无需新 key）。
- **AC-006 的窗口内回读证据**：CLI 与 bundle 内容均已验证（bundle 内 `statsMw` 为机器级调用），但窗口内实际按键路径需用户 `/reload` 后确认一次。去向：用户 reload 后由本 key 之外的日常使用确认，不阻塞结案。
- **serve 版本滞后提示**：serve（PID 4416）启动早于本轮 mw 代码变更，`/mw restart` 后才用最新派发逻辑；与 usage 功能无关。去向：用户执行 `/mw restart`。
- **夹具判据不含 `fix` 组**：本机存在一个 basename 为 `fix` 的项目（非临时目录），按 R24 修约不折叠。去向：接受不处理（判据只认临时根与 `pi-runtime-` 前缀）。
- **`--project` 两侧 basename 互比的既有语义**：用夹具的完整原始路径过滤时，同 basename 的真实行也会命中（R26 只约束反方向）。去向：记入 `_pitfalls.md` 候选，本轮接受不处理。
