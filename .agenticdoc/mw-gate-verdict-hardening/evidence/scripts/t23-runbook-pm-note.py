import pathlib

p = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening/evidence/runs/runtime-cutover-runbook.md")
add = """

---

## 附：PM 现场复核更正（2026-10-10 19:20，实测）

上面 §0 的现状快照由 T-16 在 19:13 取数。PM 在 19:19 独立重取并更正三处：

| 项 | 原记录 | PM 实测（19:19） | 影响 |
|---|---|---|---|
| 全局 bundle mtime | 「10-10 10:53:02 旧构建」 | **2026-10-10 11:40:42**，952,453 B，sha256 `52187720D22D06DEE10FEE383981CD041FAD763BFB292B9B2BD7756D3A53FE0B` | 切换前**必须重取 mtime 与 sha256**；备份按 sha256 命名而不是 mtime |
| bundle 与 `b8bc115ff` 的关系 | 暗示「pre-fix 时代」 | 实测 bundle **含 `WORKER_COLS_MIN` / `WORKER_COLS_MAX`** ⇒ 它是 **post-`b8bc115ff`** 的构建（有 7..9 列容忍 + 9 列序列化）；且**不含本 key 任何标记**（`mw-queue:v2` / `run.json` / `blockedOnHuman` / `STALE PANEL` / `cross-key-read-only` / `contract-frozen` / `gate-reminder` / `l3-aborted` 命中均为 0） | 结论不变（**本 key 的改动都未生效**），但“旧构建”的**点**要说准：bundle 是“含 7..9 容忍、不含本 key 功能”的构建 |
| 仓内 dist bundle | `dist/extensions/agent-team-loop.js` 不存在 | 该**单文件**确实不存在；但 `packages/coding-agent/dist/extensions/agent-team-loop/` **是目录且存在**（`dist/extensions/` 下 `agent-team-loop/` 与 `llama/` 的 mtime 均为 2026-10-10 11:29:46，`dist/*.js` 为 11:40:46） | 切换产物 = `~/.pi/agent/extensions/agent-team-loop.js`（单文件安装副本）；`dist/**` 是构建中间物，别混为一谈 |

### §0.1「9 个 pre-10:53 窗口必须重启」——降级为**安全假设**（不是实测结论）

可实测的只有“窗口进程启动时刻”（表中 9 个 PID：80740 / 25704 / 50032 / 95236 / 30656 / 10604 / 18200 / 117296 / 136660）。
每个窗口加载的是**它启动时刻的安装副本**；安装副本在当前时刻 = 11:40:42，但**历史各时刻的安装副本内容不可考**（该文件无版本历史）。
因此：

- PID 117296（2026-10-09 15:58:48，早于 `b8bc115ff` 10-09 16:27）与 PID 136660（2026-10-09 20:40:14，晚于 `b8bc115ff` 但早于 10-10 11:40 的安装）**不能断言其解析器是否容忍 9 列**；
- **可执行的结论**：切换时**一律重启这 9 个窗口**（成本低、收益确定），而不是依据“它们一定是 pre-fix”来推断风险；
- 判定某窗口是否为风险源的正向证据只能是它自己的 `workers/*/trace.log`（该进程的读写轨迹）或它启动时安装副本的哈希 —— 两者都不可得时，按“全部重启”处理。
"""
p.write_text(p.read_text(encoding="utf-8").rstrip() + add + "\n", encoding="utf-8", newline="\n")
print("runbook bytes:", len(p.read_bytes()))
