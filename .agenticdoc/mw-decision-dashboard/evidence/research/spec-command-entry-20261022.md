# Research: 命令入口差异与 `unknown sub 'dp'` 根因（RQ-1）

> Key: mw-decision-dashboard · 窗口: dd-rq1-command · 日期: 2026-10-22
> 类型：只读调研（无代码修改、无配置修改、无服务重启、无真实模型调用）

## 1. 问题

用户反馈执行 `mw decide dp list` 得到 `unknown sub 'dp'`。需要确定：

1. 报错来自哪个入口（pi 窗口命令 / 终端 Python CLI / 其他）；
2. 各入口实际支持哪些子命令（支持范围）；
3. 根因是代码过期（stale serve / 扩展未 reload）还是功能缺口；
4. 需求范围（spec AC-001）与验证建议。

## 2. 方法与出处

| 动作 | 出处 |
| --- | --- |
| 读窗口 `/mw` 命令注册与分发 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4742-4755`（`registerCommand("mw")`）、`:4884-4890`（`decide` 分支） |
| 读窗口 decide 参数解析（全函数） | `ui-bridge.ts:4474-4533`（`DECIDE_USAGE` + `parseDecideArgs`） |
| 读窗口 decide 执行（全函数） | `ui-bridge.ts:4636-4720`（`runMwDecideCommand`）、`:4620-4626`（`decidePreviewArgs`） |
| 读窗口渲染 | `ui-bridge.ts:4557-4596`（`formatDecidePreview`）、`:4535-4555`（`parseDecidePreview`） |
| 读 Python decide 分发 | `packages/multi-workers/mw.py:4064-4095`（`cmd_decide`）、`:4018-4037`（`_decide_dp`） |
| 读 Python dp argparse | `mw.py:10913-10995`（`decide dp` 全部子parser） |
| 读 Python dp 实现 | `mw.py:1915-1955`（`_dp_list`）、`:1970-...`（`_dp_show`）、`:2118/2122/2149/2216/2335/2471/2778/3005`（on/off/set/refresh/check/export/verify/apply） |
| 读表路径与配置加载/缓存 | `packages/multi-workers/decision_points.py:1508-1533`（`_CONFIG_CACHE`）、`:1799-1843`（`load_points_config`） |
| 读窗口→Python 转发层 | `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:513-541`（`runMwCliRaw`）、`:543-553`（`runMwCli`）、`:573-578`（`decideMw`） |
| 读 serve staleness | `mw-runner.ts:288-330`（`serveStaleness`）、`ui-bridge.ts:4806-4814`（`/mw status`） |
| 读扩展注册与加载 | `packages/coding-agent/src/extensions/index.ts:2,7`；`~/.pi/agent/extensions/agent-team-loop.js`（+`.bak-20261021`）；`ui-bridge.ts:4756-4764`（`/mw build` 提示） |
| 读授权表防护 | `shared/xkey-gate-guard.ts:380`（`TABLE_WRITE_CLI_RE`）、`:451-470`（只读白名单注释+判定）、`test/suite/decision-signoff.test.ts:225-245` |
| 读 agent 会话判据 | `packages/multi-workers/decide_signoff.py:90`（`AGENT_SESSION_ENV_VARS`）、`mw.py:1748,3012-3016`（只有 `dp apply` 自查会话） |
| 现有窗口测试 | `packages/coding-agent/test/suite/decide-command.test.ts:138-171`（parse）、`:374-...`（dispatcher wiring）；本次实跑 12 passed |
| 现有 Python dp 测试 | `packages/multi-workers/test_decide_dp_cli.py:204,220,249,...`（dp list/show/on/off/set/refresh/check/apply） |
| 文档入口示例 | `docs/decision-substitution.md:151-162`、`packages/multi-workers/README.md:849`、`docs/decision-points.md:294-295` |
| 直接复现（只读） | `tsx -e "parseDecideArgs('dp list')"` → 见 §3.1 |
| 直接复现（只读列表） | `python packages/multi-workers/mw.py decide dp list --project .` → 25 行 + `25 decision point(s), enabled=10, orphaned=0, layer=OK` |

## 3. 发现

### 3.1 报错字符串只在窗口扩展里存在，且可直接复现

```
parseDecideArgs("dp list")        -> usage: "Usage: /mw decide show | sign <continue|narrow|revoke> [--reason <text>] [--allow-empty] [--key <key>] — unknown sub 'dp'"
parseDecideArgs("dp show <id>")   -> usage: 同 unknown sub 'dp'
parseDecideArgs("report --key k") -> usage: unknown sub 'report'
```

源码 `ui-bridge.ts:4494-4503`：只有 `""`/`show`/`sign` 三个分支，其余一律
`unknown sub '<sub>'`。该字符串在整个仓库只出现在 `ui-bridge.ts:4502`（另处是文档复述）。

反向排除：
- 终端里没有 `mw` 可执行文件（`Get-Command mw` 空；`packages/*/package.json` 无该 bin），
  裸 shell `mw decide dp list` 只会是 "command not found"；
- Python argparse 的未知子命令不会输出这个句式（argparse 会说 `invalid choice`），
  `_decide_dp` 的未知 action 是 `[mw decide dp] unknown action 'x'`（`mw.py:4034-4036`）；
- `runMwDecideCommand` 的 `hasUI !== true` 分支（`ui-bridge.ts:4649`）先于解析执行，
  所以该报错只能出现在**交互 TUI 窗口**里，不会来自 `-p`/rpc/headless。

### 3.2 支持范围（实测 + 源码）

窗口 `/mw decide`：
- 顶层：`""` / `show` → 一次只读 sign-off 预览；`sign <continue|narrow|revoke>` → 预览→`ctx.ui.confirm`→带 `--human-confirmed` 写入（`ui-bridge.ts:4643-4720`）。
- 覆盖度：Python `decide` 9 个顶层子命令中覆盖 2 个；`dp` 的 10 个动作覆盖 0 个。

Python `mw decide`（`python mw.py decide --help` 实测）：
`run | probe | show | set | ask | book | report | sign | dp`；
`dp` 下：`list | show | on | off | set | refresh | check | export | verify | apply`（`mw.py:10913-10995`）。

`dp list` 实测正常（25 个注册点，`enabled=10`，`layer=OK`），不需要 key。

### 3.3 同名不同义：窗口 `show` ≠ CLI `show`

- 窗口 `show` 实际执行 `mw decide sign --key <k> --json`（`ui-bridge.ts:4620-4626`），
  渲染的是某 key 的签收事实：`counted_rows/n_available/n_acted/n_escalated/engines/rows_sha256/p0_open/verdicts`（`ui-bridge.ts:4557-4596`）。
- Python `mw decide show` 打印的是 `.mw/decide.json` 生效配置 + 最近一条 evidence（`mw.py:1088-1100`）。

结论：现有窗口里 `show` 这个字已经被 sign-off 预览占用；看板/列表若要复用 `show`，必须先命名区分。

### 3.4 转发层已经存在，缺口只在参数解析与分支

`decideMw(projectDir, args)` = `runMwCli("decide", projectDir, args)`，最终
`spawnSync(python, [mwPy, "decide", ...args, "--project=<dir>"])`（`mw-runner.ts:513-553,573-578`）。
即窗口已经有"把 argv 尾巴原样交给 Python"的通道，只是 `parseDecideArgs` 把非 show/sign 的 sub
在 spawn 之前拒掉了。给 `dp` 加只读转发是**一个分支 + 参数白名单**的改动，不是新传输层。

注意两个附加约束（源码直接可证）：
1. `runMwDecideCommand` 在任何执行前先解析 key（`ui-bridge.ts:4658-4666`），
   `dp list` 与 key 无关，若走同一条路会被 "无法确定 key" 拦住 → 必须在 key 解析之前分流；
2. `runMwCliRaw` 会自动追加 `--project=<dir>`（`mw-runner.ts:527-529`），
   而 `dp` 的每个子 parser 都接受 `--project`（`mw.py:10920-10995`），转发兼容；
   `projectDir` 在 PM/交互窗口是 `process.cwd()`（`pm-orchestrator.ts:2919,2945`），
   与 `.mw/decide-points.json` 的解析基准一致（`decision_points.py:1516-1517`）。

### 3.5 授权表写入面的既有防护是"bash 工具层"的，不是窗口层的

- bash 工具：`TABLE_WRITE_CLI_RE` 直接拦 `mw decide dp on|off|set|apply`（`xkey-gate-guard.ts:380`），
  只读的 `dp list|show|check` 与 append-only 的 `dp refresh` 放行（`:451-470`，测试 `decision-signoff.test.ts:225-245`）。
- Python 层：只有 `dp apply` 自查 agent 会话并拒绝（`mw.py:3012-3016`）；
  `dp on/off/set` **没有**会话自查，它们的设计前提是"人在终端里敲"。
- 窗口环境实测：`PI_CODING_AGENT=true`、`AI_AGENT=pi`、`PI_WORKER_TASK=<task.md>`，
  正是 `AGENT_SESSION_ENV_VARS`（`decide_signoff.py:90`）判据。

因此：若把 `/mw decide dp <sub>` 整体透传，等于为 `dp on/off/set` 开了一条绕过 bash 守卫的
窗口写入路径，与 AC-010「机器不写授权表」和 spec §范围「不修改授权表或通过测试隐式扩大 DP 权限」冲突。

### 3.6 入口文档：文档只承诺 `python mw.py decide dp ...`

`docs/decision-substitution.md:151-162`、`README.md:849`、`docs/decision-points.md:294-295`
全部写 `python mw.py decide dp <sub> --project .`。仓库里没有 `mw` 可执行别名。
worker 窗口根本不注册 `/mw`（`registerMwCommands` 只在 `pm-orchestrator.ts:2945` 调用，
worker 分支走 `worker/worker-mode.ts`），所以在 worker 里唯一受支持入口就是 bash 工具里的
`python mw.py decide dp list --project <root>`（且被守卫明确放行）。

### 3.7 stale serve：与本次报错无关

- serve 是调度器/LLM 代理（`mw.py:271 cmd_serve`；`launcher.py` 全文无 `decision_points`/`decide` 引用），
  不持有 DP 表或 decide 结果。
- `dp list` 每次都是新进程，直接读 `<project>/.mw/decide-points.json`；
  `decision_points._CONFIG_CACHE` 只对**长生命周期进程**有意义（按 `(st_mtime_ns,st_size)` 失效，`decision_points.py:1508-1533`）。
- 窗口里的决策调用也是新进程 spawn（`mw.py decide run --request-file …`，`decision-tool.ts:453-482`）。
- `/mw status` 的 STALE CODE 是 `serveStaleness` 比较 "mw 源码 mtime vs serve 启动时间"（`mw-runner.ts:288-330`），
  与扩展代码无关。

所以：重启 serve 不可能修掉 `unknown sub 'dp'`，也不会改变任何 DP 读取结果。

### 3.8 扩展 reload：能解释"改了不生效"，不能解释本次报错

- 内置扩展在进程启动时由 `src/extensions/index.ts:2,7` 作为 inline factory 注册；
  全局 bundle 在 `~/.pi/agent/extensions/agent-team-loop.js`（本次 10:27:15，1,391,820 B，
  另有 `.bak-20261021`）。`/mw build` 的提示语就是 "Restart pi windows to load it"（`ui-bridge.ts:4761`）。
- git 时间线：窗口 `/mw decide`（show/sign）与 Python `dp` 家族在**同一个提交** `f2f20e922` 落地
  （`git log -S parseDecideArgs` / `-S def _decide_dp` 均指向该提交），提交信息里写的是
  "`/mw decide` CLI"——把窗口命令与 CLI 混称，是"以为窗口有 dp"的来源。功能缺口自首次发布即存在，**不是回归**。
- bundle 内容核对：当前 bundle 与 `.bak-20261021` 都只有 1 处 `unknown sub` + 1 处
  `decide show | sign` usage，即两个版本都是同样的 2 子命令面 → 陈旧 bundle 同样无法解释报错。
- `/reload` 会重载扩展目录里被自动发现的扩展（`docs/usage.md:57`、`docs/extensions.md:7`）；
  inline factory 是否连模块本身一起重新 import，本次未验证（见 §5）。

### 3.9 结论矩阵：三个"疑似原因"只有一个成立

| 候选原因 | 证据 | 判定 |
| --- | --- | --- |
| 窗口解析器缺 `dp` 分支 | `ui-bridge.ts:4494-4503` + 直接复现 + 单测 `decide-command.test.ts:138-171` | **成立（唯一根因）** |
| serve 代码过期 | serve 不参与 dp/decide；`dp list` 是新进程读文件（§3.7） | 不成立 |
| 扩展/bundle 过期 | 当前与上一版 bundle 同为 show\|sign；缺口自 `f2f20e922` 起存在（§3.8） | 不成立（只影响"修好之后何时生效"） |

## 4. 根因与不确定性

### 根因

`/mw decide` 的窗口参数解析器只实现了 `show`/`sign` 两个分支（`ui-bridge.ts:4494-4533`），
`dp` 落进 `unknown sub` 分支并在 spawn 之前被拒；而 Python CLI 侧 `mw decide dp *` 是完整实现
（`mw.py:4018-4037,10913-10995`）。窗口从未镜像 `dp` 家族——功能缺口，不是版本过期。
次级事实：窗口 `show` 的语义（key 级签收预览）与 CLI `show`（配置视图）不同名同义问题被混用。

### 不确定性（本证据不承诺）

1. `/reload` 是否重新 import 内置 inline factory 模块（因此无法承诺"改完 `/reload` 即生效"）；
   保守规则：重启窗口或 `mw build` 后重启。
2. 用户当时那个窗口跑的是 dev(tsx) / 全局 bundle / 已安装 dist 中哪一份——无法从本会话判定；
   三者现版本都是 2 子命令面，不改变根因。
3. 报错发生的窗口类型（PM 交互窗口 vs 普通交互窗口）：`hasUI` 分支证明是交互窗口，但两者都注册 `/mw`（`pmActivate` 覆盖 `PI_WORKER_TASK` 未设置的场景），无需区分。
4. 用户是否希望 `/mw decide dp list` 本身成为受支持入口——属需求决策，本证据只列范围与建议。
5. `dp export --write` 会重写 `packages/multi-workers/decide_registry.json`，`dp refresh` 会追加表行；
   两者虽不在 bash 守卫的写命令正则里，仍属写操作，是否允许从窗口触发需 spec 明确。

## 5. 结论 → spec 映射

| 结论 | 映射 |
| --- | --- |
| `unknown sub 'dp'` 来自窗口解析器，Python CLI 正常 | AC-001（受支持入口列出注册 DP 且不再返回 unknown sub 'dp'）；§1 目标1 |
| 窗口只覆盖 2/9 顶层子命令、0/10 dp 动作 | §1 "查明窗口入口与 CLI 入口差异，修复用户使用入口"；§5 坑点"窗口命令和 Python CLI 可能不一致" |
| `dp list|show|check` 是只读、无 key、新进程读表 | 可直接做成窗口转发（与 `rag`/`target`/`model` 同一模式，`ui-bridge.ts:4293-4307`），支撑 AC-001 |
| `dp on|off|set|apply` 只有 bash 守卫、且只有 apply 自查会话 | §范围"不修改授权表或通过测试隐式扩大 DP 权限"；AC-010 语义 |
| 窗口 `show` = key 签收预览，CLI `show` = 配置 | §3 AC-003/AC-002 的命名与数据源必须显式区分 |
| 决策数据全在文件（表 + `decisions.jsonl`），serve 不参与 | §0 GC-1 文件驱动；§4 "UI 载体"未决项：看板不需要 serve 依赖 |
| 缺口自首次提交即存在 | §5 "避免把 serve 重启当成所有入口修复"（已确认：重启无效） |

### 需求范围建议（供 spec 锁定，非本角色决策）

- R1 入口分层：`python mw.py decide dp ...` 作为唯一完整入口（worker 窗口只有这一条）；
  窗口补**只读**镜像 `dp list|show|check`（可选 `export`/离线 `verify`），输出原样显示，Python 单一来源。
- R2 写面不扩大：窗口对 `dp on|off|set|apply` 明确拒绝并提示终端命令（或要求独立人工确认），
  `sign` 保持现有 preview→confirm→`--human-confirmed` 路径，不做通用透传。
- R3 命名：看板/列表不得复用窗口 `show` 一词，避免继续混淆 key 签收预览与配置视图。
- R4 数据源：看板读文件（`.mw/decide-points.json`、`.agenticdoc/_autopilot/decisions.jsonl`）
  或 spawn CLI；不引入 serve 依赖，否则 stale serve 才第一次成为真实故障源。
- R5 位置：`dp` 分流必须放在 `runMwDecideCommand` 的 key 解析之前（否则 `dp list` 被 "无法确定 key" 拦住）。

### 验证建议

- V1 单测（零 spawn）：`parseDecideArgs("dp list")` → `dp` 形状；`parseDecideArgs("dp set ...")` → 拒绝；
  未知 sub 仍走 usage。扩 `test/suite/decide-command.test.ts:138`。
- V2 argv 断言：stub runner 断言恰好 `["dp","list"]`；用真实 `decideMw` 时 `--project=<dir>` 只追加一次
  （`mw-runner.ts:527-529`）。
- V3 守卫对偶测试：bash 工具里 `dp on|off|set|apply` 仍被拦（`decision-signoff.test.ts:225-245`），
  且窗口路径不提供等价写入；两个方向都要有断言。
- V4 输出一致性：窗口显示文本逐字等于 `python mw.py decide dp list --project <root>`
  （Python 渲染、窗口只显示，与 rag 的 VC-307 同一规则）。
- V5 生效方式：改完扩展后重启窗口再验证 usage 行；不得用 `/mw status` 的 STALE CODE 当作扩展是否生效的判据（§3.7/3.8）。
- V6 真实模型边界：`dp list/show/check` 全离线，可进自动化测试；`dp verify --live`、看板"真实 Jev 测试"
  属 AC-004 的人工触发路径，自动化测试不得隐式发起真实调用。
