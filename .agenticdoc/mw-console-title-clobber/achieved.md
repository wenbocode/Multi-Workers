# Achieved: mw-console-title-clobber

- Key: mw-console-title-clobber
- 型态：trivial-fix fast path（两侧各 1 处小改 + 1 个 Python 回归测试；PM 直执，未派 worker）
- 结案：2026-10-11（本地 UTC+8）
- 来源：用户报障——跑 `/mw` 的模型相关命令后，pi 窗口标题变成 `pi`，不再是工作目录名

## 交付物

| 文件 | 改动 | 作用 |
|---|---|---|
| `packages/multi-workers/mw_common.py` | `+_probe_spawn_kwargs()`，`_probe_model_rows` 透传 `**_probe_spawn_kwargs()` | win32 上探针子进程 `pi --list-models` 用 `CREATE_NO_WINDOW` 隔离控制台（对齐 `launcher.py:1104`） |
| `packages/coding-agent/src/cli.ts` | `process.title = APP_NAME` 外包一层 `if (process.stdout.isTTY)` | 源头收窄：stdout 被重定向的子进程 pi 不再调用 `SetConsoleTitleW`，不会改宿主窗口标题 |
| `packages/multi-workers/test_common.py` | `+test_probe_child_isolated_from_the_parent_console` | AC-1 回归（win32/linux/darwin 三分支 + 真实 spawn 路径 kwargs 透传），并输出 `[VERIFY] AC-1` 机器判据行 |

## 系统行为变化

- **Windows 控制台标题不再被 mw 探针改写**：`/mw model show`、`/mw model set <role> <value>`、`/mw doctor`
  （以及 PM 调 `mw doctor` 工具的回合）此前会 spawn `pi --list-models`；该子进程继承宿主控制台，
  pi CLI 的 `process.title = APP_NAME`（Windows = `SetConsoleTitleW`）会把宿主窗口标题改成 `pi`，
  且 TUI 只在少数事件重写自己的 OSC 标题，脏标题因此长期留在窗口上。修后：探针子进程与控制台隔离，
  端到端实测标题不变（`evidence/e2e-sentinel-20261011.txt` 的 B / C 行）。
- **子进程 pi 不再声明宿主控制台所有权**：stdout 非 TTY（管道/文件——探针、worker spawn、RPC、`pi -p > file`）
  时不再设置 `process.title`。交互式运行（stdout 即终端）行为逐字不变；`rpc-entry.ts` 的 `pi-rpc` 未动。
- **影响面**：`packages/multi-workers`（1 函数 + 1 行透传 + 1 测试）与 `packages/coding-agent`（1 处 1 行包裹）。
  无 API/配置/事件面变化，未改 dist/CHANGELOG（D-002）。非 win32 行为不变（`_probe_spawn_kwargs` 返回 `{}`）。

## 证据（原始输出）

| 项 | 判据 | 证据 |
|---|---|---|
| AC-1 | win32 传 `CREATE_NO_WINDOW`（0x08000000）、linux/darwin 不传、真实 spawn 透传 | `evidence/probe-flags-20261011.txt`（`78 passed`，`[VERIFY] AC-1: probe_creationflags=134217728 platform=win32`） |
| AC-2 | 哨兵标题下 `mw model show` 不改标题；旧调用形态仍改（负向对照） | `evidence/e2e-sentinel-20261011.txt`（A CLOBBERED / B safe / C safe） |
| AC-3 | 改前 `cli.ts`（管道 stdout）会改标题、改后不改；临时对照拷贝已删除 | 同上（A' CLOBBERED / B' safe）；代码锚点 `cli.ts:12-20` |
| VC-1 | 最小面 + 全量检查全绿 | `evidence/check-20261011.txt`（`npm run check` exit=0，biome 1119 files 无改写） |
| 交叉 | CLI 相关既有测试无回归 | `evidence/ts-cli-tests-with-change-20261011.txt` vs `…-baseline-head-20261011.txt`（同一失败集） |
| 质检 | 收口前 5/5 充分 | `evidence/quality-gate-report-20261011.md` |

## 遗留

1. **`interactive-mode.ts` 的"事后恢复"路径未做**（D-001：需在 core 事件层加钩子，改动面大）→
   **去向：另立 key 时再做**。本轮以"源头不让改"（TTY 门）替代；若将来出现非 pi 的 clobber 者
   （npm / codex / claude 等 CLI 探针），该路径才需要。
2. **其它 CLI 探针（codex / claude）未审计**：它们同样可能设置控制台标题 → **去向：与第 1 项同批评估**。
3. **dist/bundle 未重建**：运行中的全局 bundle（`~/.pi/agent/extensions/agent-team-loop.js` 与 pi dist）
   仍是旧代码，本修复对**新起的 pi 进程**才生效 → **去向：用户执行 `/mw build` + `/mw restart`**（D-002）。
4. **`/mw mode show` 不存在**：运行中的 bundle 子命令闭集无 `mode`，该输入只触发 usage 提示（不进探针）。
   报障时的实际命令应为 `/mw model show` 或 `/mw doctor` → **去向：无需动作**（已在 mini-spec §依据 4 记录）。
5. **`test/package-command-paths.test.ts` 的 3 个失败**属环境基线（改前同样失败，已 A/B 存档）→
   **去向：无需动作**（不追与本 key 无关的基线红）。
