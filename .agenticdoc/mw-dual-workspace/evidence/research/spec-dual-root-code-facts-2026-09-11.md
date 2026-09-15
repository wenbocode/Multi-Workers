# Research: 双工作区（控制根/目标根）现有代码事实核查（spec）

## 决策问题

支撑 spec §1 范围（双工作区模式可行性）、§2 约束（须保留的语义）、§4 风险（双根拆分的影响面）。

## 调研方法与出处

本会话（2026-09-11）对仓库源码的直接阅读，全部结论带文件:行号：

- `packages/coding-agent/src/extensions/agent-team-loop/shared/paths.ts`（全文 31 行）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:1-120`（工具白名单、预算）；`:470`（projectRoot）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:40-110`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts` / `phase-runner.ts:30-34` / `shared/heartbeat.ts:1-80`（rg 摘要）
- `packages/multi-workers/launcher.py:125,153,221,266,522-524`
- `packages/multi-workers/mw.py:88-100,106-109,188-333,512-516,661-688`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:100-180,195-330`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:588`
- `.agenticdoc/_project_log.md`（已完成 key 时间线）

## 发现

1. **单根假设是现状**：worker 侧 `worker-mode.ts:470` 为 `const projectRoot = process.cwd();`（注释明确 launcher 以 cwd=项目根派生，D-106 base）；PM 侧 `pm-orchestrator.ts:588` 同样 `process.cwd()`。`paths.ts` 的 `agenticdocRoot(projectDir)` 把 `.agenticdoc` 拼在 projectDir（=cwd）下。
2. **绝对路径传递已有先例**：`launcher.py:125/:153` 将 `PI_WORKER_TASK` 设为 task.md 的**绝对路径**，worker 侧按该绝对路径读取。控制根经环境变量传递与该机制同构。
3. **worker 派生参数**：`launcher.py:522-524` 以 list args（无 shell，AC-023）spawn，`cwd=project_dir`——双工作区模式下 cwd 即目标工程根的注入点。
4. **read-scope 已支持绝对 scope 条目**：`read-scope.ts` 的 `ReadScopeConfig.scope` 注释明确「project-root relative or absolute」；`normalizeForCompare` 相对 projectRoot 解析后 `realpathSync`（不存在尾部回退到最深存在祖先），win32 双侧小写比较。空 scope fail-closed。**deny globs 不存在**——现状只有 allow scope + fileCap/byteCap。
5. **协调层文件清单**（AC 扫描目标）：task.md、`trace.log`、`output.md`、`progress/phase-N.md`（`phase-runner.ts:34`）、heartbeat 为 trace.log 内 `[HEARTBEAT]` 行（30s 节奏，D-003）、`.agenticdoc/`、`.mw/`、`_workers.parallel`、`_index.parallel`。
6. **mw serve 生命周期按 project_dir 键控**：stop 请求文件 `.mw/mw.stop`（`mw.py:88-100`）、staleness 戳 `.mw/serve.meta`（`mw.py:106`），扩展侧 `mw-runner.ts` 的 `startMw/restartMw` spawn `mw.py start --project=<dir>`。双工作区下 serve 根应为控制工作区。
7. **git 操作已参数化**：`mw.py:512-516` `_git(args, cwd=...)` 走 `git -C`；sync/commit 流程（`mw.py:661-688`）对 dst repo 执行——目标 repo 绑定具备基础，但「双工作区下 dst 是谁」无既有语义，是待澄清项。
8. **工具白名单双侧同步护栏**：`worker-mode.ts:30-52` 的 `TOOL_ALLOWLISTS` 注释明确须与 `autopilot/dispatch.py` 的 REGISTRY 严格相等（entry order 含），由 T-17 L0 parity 测试锁定。
9. **历史坑点**（来自 `_project_log.md` 已完成 key）：
   - `mw-stale-builtin-fix`：过期 dist 双加载——bundle 发现/路径解析在引入第二根后有同类风险。
   - `mw-dispatch-reliability`：credential 失败隔离与 stale entry 清理为 dispatch 可用性基线。
   - AGENTS.md 记载 Windows 环境 89 例已知基线失败（13+76），回归判定须对照基线。

## 结论 → 决策映射

- 结论 1/3/5 → spec §1：双工作区 = 把「协调层文件根」与「工件层 cwd」拆开，影响面集中在 paths.ts、worker-mode.ts、launcher.py、pm-orchestrator.ts。
- 结论 2 → spec §2.4：控制根环境变量传递复用 PI_WORKER_TASK 同构机制，无新基础设施。
- 结论 4 → spec AC-006：deny globs 是新增能力（现有 read-scope 只有 allow+caps），deny 优先于 allow。
- 结论 6 → spec AC-009：serve 根绑定控制工作区，staleness 语义不变。
- 结论 7 → spec §4 待确认 4：git 子命令在双根下的目标 repo 语义留给 design 澄清。
- 结论 8 → spec §2.4：若后续扩展任务类型，须双侧同步（T-17 护栏已存在）。
- 结论 9 → spec §5 规避坑点。

## 补充核查（2026-09-11，spec 证据复查）

按 PM 证据复查要求（断言-证据对照 / 数字口径 / 内部一致性 / 可证伪性）的复核结果，均为本日直接阅读源码/测试：

- 出处增补：AGENTS.md（仓库根，项目指令）是「Windows 89 例环境基线（13 + 76，2026-09-10 分类）」的唯一出处——§发现 9 引用它但原出处清单漏列，现补记。
- goal check 测试存在（spec AC-008 前提成立）：packages/coding-agent/test/extensions/agent-team-loop.test.ts:379、:417（`[GOAL_CHECK] phase=1 goal_mtime=123.45` 断言）、:573（goalMtime 缺失时返回 0 单测）。
- serveStaleness 测试存在（spec AC-009 前提成立）：同文件 :635（fresh / stale / unknown / pid-file fallback 四分支）。
- read-scope 测试基线存在（spec AC-006 扩展落点）：packages/coding-agent/test/suite/autopilot-read-scope.test.ts（containment / caps / frontmatter 三个 describe 块）。
- read-scope 拦截工具集实测为 read / ls / find / grep 四类：worker-mode.ts:477-483 显式枚举判断；:105 的 READ_TOOLS（含 glob）仅用于 checkpoint 收敛信号计数，不参与 scope 拦截——spec §2.3 / AC-006 的工具枚举与实现一致。
- trace.log 写入为同步 fs.appendFileSync 逐行追加（output-writer.ts:78 / :89 / :211 / :223）——spec §2.2 性能断言的现状事实；跨盘单行追加延迟无实测数据，spec 已将该阈值标注「未实证」并写明取证方法。
