# mini-spec: mw-console-title-clobber

> Key: mw-console-title-clobber
> 建立: 2026-10-11（用户报障：跑 `/mw` 的模型相关命令后，CLI 窗口标题变成 `pi`，不再是工作目录名）
> 型态：trivial-fix fast path（两侧各 1 处小改：mw 探针 spawn 隔离 + pi CLI 标题仅在自有 TTY 时设置）

## 目标

Windows 下 mw 的模型能力探针（`pi --list-models` 子进程）不再改写宿主 pi 窗口的控制台标题；
并从 clobber 源头收窄：**子进程 pi 在 stdout 被重定向时不再调用 `process.title`**（= SetConsoleTitleW），
即"不声明控制台所有权，就不改它的标题"。

## 依据（实测，2026-10-11）

1. **机制**：`packages/coding-agent/src/cli.ts:12` `process.title = APP_NAME`（"pi"）；Windows 上
   `process.title` 落到 `SetConsoleTitleW`。子进程继承宿主控制台 ⇒ 直接改掉宿主窗口标题；
   宿主 pi 的 OSC 标题只在 init / session 事件时重写，所以脏标题会一直留着。
2. **受控实验**（哨兵标题 + 同一命令 `pi --list-models` 三种 spawn 方式，同一控制台）：

   | spawn 方式 | before | after | 判定 |
   |---|---|---|---|
   | 继承控制台（当前 `mw_common._probe_model_rows`） | `SENTINEL-A` | `pi` | CLOBBERED |
   | `CREATE_NO_WINDOW` | `SENTINEL-B` | `SENTINEL-B` | safe |
   | `DETACHED_PROCESS\|CREATE_NEW_PROCESS_GROUP\|CREATE_NO_WINDOW` | `SENTINEL-C` | `SENTINEL-C` | safe |
3. **代码不对称（遗漏证据，非设计）**：同一仓库里其它 spawn 都已隔离——
   `launcher.py:1104`（派发 pi worker）、`mw.py:277`、`mw.py:438`（serve 启动）——
   只有 `mw_common.py:1450` 的探针没传 `creationflags`。
4. **触发面**（任何走到 `model_images()` 的路径）：`/mw model show`（`mw.py:3257` 已配置角色 + `:3272`
   未配置角色预览）、`/mw model set <role> <value>`（`:3183` vision 图像能力门禁）、
   `/mw doctor`（`mw_common._doctor_dispatch:1292`；PM 调 `mw doctor` 工具的回合同样命中）。
   注：`/mw mode show` 不是子命令（运行中的 bundle 子命令闭集无 `mode`，掉到 usage 提示、不触发探针）。
5. **pi 侧先例**：`interactive-mode.ts:1020-1024` 已为 npm 做过同类修补（"On Windows, npm can overwrite
   the shared console title … Restore Pi's title after the startup check."）——说明这是已知问题类。

## 范围

- **做**
  - `packages/multi-workers/mw_common.py::_probe_model_rows`：win32 上给探针 spawn 加
    `creationflags=subprocess.CREATE_NO_WINDOW`（对齐 `launcher.py:1104`）；非 win32 行为逐字不变。
  - `packages/coding-agent/src/cli.ts`：`process.title = APP_NAME` 仅在 `process.stdout.isTTY` 时设置
    （子进程/重定向场景不再改宿主控制台标题；交互与直接运行行为不变）。
  - 回归测试：Python 侧断言 spawn kwargs（该函数已有可注入的 `which`/`run` seam）。
- **不做**
  - `process.title` 的取值本身（仍是 `APP_NAME`）、`rpc-entry.ts` 的 `pi-rpc` 标题。
  - 其它 CLI（codex/claude）探针；`interactive-mode.ts` 的逐命令恢复（改动面更大：需在 core 事件层
    加钩子；本轮以"源头不让改"替代"事后恢复"，两者可并存，留待需要时另立 key）。
  - dist/bundle 重建（`/mw build` 由用户执行）；不新增 CHANGELOG 条目（无用户可见行为变化面之外的影响：
    仅"窗口标题不再被误改"）。

## 验收（AC / VC）

| 编号 | 判据 |
|---|---|
| AC-1 | win32 下 `_probe_model_rows` 的 spawn 携带 `creationflags = CREATE_NO_WINDOW`；非 win32 不携带（假 `run` seam 记录 kwargs 断言） |
| AC-2 | 端到端（哨兵标题，本机 win32）：`python packages/multi-workers/mw.py model show --project <repo>` 后标题**不变**；同一实验在修改前为 `pi`（负向对照） |
| AC-3 | pi 侧：`cli.ts` 的 `process.title` 赋值被 TTY 判定包裹；`node <source cli.ts> --list-models`（stdout 为管道）不再改标题，且有 TTY 的交互运行仍设标题（代码锚点 + 实测 + `npm run check` 全绿） |
| VC-1 | 两侧改动均为"最小面"：不加事件类型、不加配置项、不改 AC 之外的行为；`npm run check` 与相关 Python 测试全绿 |

## 证据

- `evidence/probe-flags-<date>.txt`：Python 回归测试原始输出（含 AC-1）。
- `evidence/e2e-sentinel-<date>.txt`：哨兵端到端原始输出（改前 CLOBBERED / 改后 safe，含 AC-2/AC-3）。
- `evidence/check-<date>.txt`：`npm run check` 全量输出。
- `evidence/quality-gate-report-<date>.md`：质检报告。

## 完成判据

AC-1 / AC-2 / AC-3 / VC-1 均有原始命令输出为证；不留未提交中间态（是否提交由用户决定）；
不做与 AC 无关的顺带改动（`interactive-mode.ts` 恢复路径明确列为范围外）。
