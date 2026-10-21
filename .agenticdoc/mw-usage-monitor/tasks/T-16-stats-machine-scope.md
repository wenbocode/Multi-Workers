# T-16: 窗口面 `/mw stats` 默认机器级 + `--all-projects`（coding）

- Key: mw-usage-monitor
- type: coding
- 对应：spec §15（R21–R23 / AC-028–AC-030）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（本机级 usage 监控 = 框架可观测性面）。
- 现状：台账是机器级的（`~/.mw/usage/runs.jsonl` 收全部项目），CLI `mw stats` 默认不过滤 project；
  但窗口面 `statsMw`（`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:567`）
  走 `runMwCliRaw`（同文件 `:508`，它在 argv 尾部无条件追加 `--project=<control root>`），
  于是 `/mw stats` / `/mw stats --detail` 的 HTML 里 project 列只剩 `Multi-Workers`
  （实证：`~/.mw/usage/reports/usage-20261021-174136.html` 196 行全部 `H:\git\Multi-Workers`）。
  另一个真实 bug：窗口里显式写 `--project H:\git\E2Feature` 会被后追加的 `--project=<root>` 覆盖（argparse 后者胜）。
- `mw.py` 侧现状：`stats_p.add_argument("--project", ...)`（`packages/multi-workers/mw.py:10088`），
  `cmd_stats` 把 `args.project` 原样塞进 `filters`（`:9990` 附近），`usage._project_matches`（`usage.py:743`）做匹配。
- 已存在的窗口面契约测试：`packages/coding-agent/test/suite/mw-stats-surface.test.ts:124-165`
  现在断言「bare 也追加一次 `--project`」，本任务要把它改成新语义（AC-028）。

## 要求

1. **`mw.py`**：`stats` 子命令新增 `--all-projects`（`action="store_true"`）；`cmd_stats` 里
   `--all-projects` 与 `--project` 同时出现 → `print("mw stats: --all-projects conflicts with --project", file=sys.stderr)` 并 `return 2`；
   否则 `project_filter = None if args.all_projects else args.project`，把 `project_filter` 传给 `build_report(filters={...})`
   （不要改 `usage.py`）。
2. **`mw-runner.ts`**：`runMwCliRaw` 增加第 5 个参数 `scopeProject = true`；为 `false` 时 argv 里**不**追加 `--project=<projectDir>`。
   `statsMw` 改为 `runMwCliRaw("stats", projectDir, extraArgs, 180_000, false)`（保持 ok/error 包装与 180s 超时），
   并更新 docstring（说明「台账是机器级的，窗口面不再追加 control root；要收窄就显式传 `--project`」）。
   其它子命令的调用点行为不变（默认 `true`）。
3. **窗口面契约测试** `mw-stats-surface.test.ts`：
   - `statsMw(root, [])` → argv 严格等于 `["stats"]`，且 `projectArgs(argv)` 为空（AC-028）；
   - `statsMw(root, ["--since","24h","--source","pm"])` → 末尾无 `--project`；
   - `statsMw(root, ["--project","H:/x"])` → argv 里只有那一个 `--project`，没有追加 control root；
   - `/mw` dispatch 用例（`handler("stats", ctx)`）断言同步改成不带 `--project`。
4. **`test_stats_cli.py`**：新增两个用例——(a) `--all-projects` 与裸跑 `runs_total` 相等；
   (b) `--all-projects --project X` → rc=2 且 stderr 含 `conflicts with --project`（AC-029）。
   用现有 fixture 风格（临时 `MW_USAGE_DIR` + 合成台账），不要依赖本机真实台账。
5. **README**（`packages/multi-workers/README.md`，锚点插入/替换，禁止整文件写）：
   - `## 用量统计（mw stats）` 节里那句「runner 恒追加 `--project`，故窗口内默认只看当前 control root」改成新语义：
     窗口面与 CLI 一致是机器级；要收窄显式 `--project <dir>`（`--all-projects` 只是显式声明不过滤）。
   - flag 表 `--project` 行去掉「`/mw stats` 由 runner 追加当前 control root」的说法；补一行 `--all-projects`。
   - 顶部命令行清单（约 `README.md:86`）与正文 usage 行（约 `:97`）加上 `[--all-projects]`。
6. **CHANGELOG**（`packages/multi-workers/CHANGELOG.md`）：在 mw-usage-monitor 的 `### Added` bullet（含 `static HTML report` 那条）
   **末尾追加一句**（不新建 bullet）：窗口面 `/mw stats` 不再隐式追加 `--project`，改为机器级默认 + `--all-projects`。

## 写入允许面

- `packages/multi-workers/mw.py`（只改 stats 相关：argparse 的三个 add_argument 附近、`cmd_stats` 的校验段与 `filters` 那一行）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（`runMwCliRaw` / `runMwCli` / `statsMw` 及其 docstring）
- `packages/coding-agent/test/suite/mw-stats-surface.test.ts`
- `packages/multi-workers/test_stats_cli.py`
- `packages/multi-workers/README.md`（仅 `## 用量统计（mw stats）` 节 + 顶部命令行表）
- `packages/multi-workers/CHANGELOG.md`（仅该 bullet）
- `.agenticdoc/mw-usage-monitor/workers/um-t16-stats-machine-scope/report.md`

## 并发警告（必读）

`mw.py` / `README.md` / `CHANGELOG.md` / `mw-runner.ts` 工作区里有**其它会话未提交的改动**
（`mw decide` / claims / dispatch 相关，数千行）。只做**精确锚点**编辑（小 `oldText`）；
禁止 `write` 整文件、禁止格式化/重排；锚点匹配不到或多处匹配就停下汇报；不要 `git add/commit`。
自查：`git diff --numstat` 相对任务开始时，`mw.py` 增量应在 `+20/-2` 量级，`mw-runner.ts` `+20/-10` 量级。

## 写入禁止面

- `packages/multi-workers/usage.py`、`launcher.py`、`launcher_*`、任何 `test_usage.py`
- 其它 `packages/coding-agent/src/**`（除 `mw-runner.ts` 上述函数）、`packages/coding-agent/test/suite/**` 其它文件
- 禁止 `git add/commit/checkout/reset/clean/stash`、`npm install|ci|build`、全量 vitest/pytest

## 验收命令

```bash
cd packages/multi-workers
python -m pytest test_stats_cli.py test_usage.py -q
python mw.py stats --since 24h --json | Select-String 'runs_total'
python mw.py stats --since 24h --json --all-projects | Select-String 'runs_total'
python mw.py stats --all-projects --project H:/git/Multi-Workers
echo "exit=$LASTEXITCODE"

cd ../../packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mw-stats-surface.test.ts
```

期望：pytest 全绿；两次 `runs_total` 相同；冲突命令 rc=2 且 stderr 打印冲突提示；vitest 该文件全绿。

## 交付格式

- `output.md` 4 段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`
- 证据必须贴：5 条验收命令的真实输出（含 rc）、`git diff --numstat` 自查、`mw-runner.ts` 改动后的 `statsMw` 全文。

## 改动历史

- 2026-10-21 创建（PM）：窗口面 `/mw stats` 改机器级默认，补 `--all-projects`，修显式 `--project` 被覆盖的 bug。
