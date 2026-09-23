# 达成报告: mw-task-scope-isolation

> Key: mw-task-scope-isolation
> 结案时间: 2026-09-23
> 状态: done

## 系统行为变化

worker 任务面从"项目级全局"变为"按窗口隔离"，PM 窗口看到什么、能动什么与底部 watch widget 同口径：

1. **`list_tasks` 默认只看本窗口**：`scope` 新增三档——`"mine"`（默认；本窗口 watch 的 key ∪ 本窗口本进程派发过的任务）、`"key"`（配合 `key:` 参数看单个 owner key）、`"all"`（原来的全项目视图，保留）。每行加上 owner 前缀：`<owner> :: <taskKey> | <status> | <cli>[ | model: m][ | acked]`，跨 key 列表从此可读。未知 scope、或 `scope:"key"` 缺 `key` → 返回文本错误，不静默降级为全局（fail-closed）。空结果的 `mine` 会给出 `switch_key` / `scope:"all"` 指引，并说明其它窗口的任务不会被列出。
2. **ack 收窄**：`ack_worker_result("all")` 与 `/mw ack all` 只覆盖本窗口拥有的行；显式指名别的 owner key 的行 → 拒绝，文案含该 owner key 与 `/pm-key switch <owner>` 指引，且**不写** `.agenticdoc/_workers.acked`。此前任何窗口的 `all` 都会把其它窗口未处理的 failed/needs-clarification 行一并标掉（侧车是项目级共享文件），属于静默清空别人的待处理清单。
3. **显式跨 key 派发仍属自己**：`dispatch_worker(key: ...)`（owner key ≠ watched key）在窗口 watch 状态上留一条进程内派发记录，因此该任务仍出现在 `mine` 里、也能被本窗口 ack。记录只在内存（每进程一份＝每窗口一份），不落盘、不共享，窗口重启后退化为纯 watched-key 口径（默认派发路径本就在 watched key 下）。

影响面（明确边界）：

- 只改 agent-team-loop 扩展的 PM 工具/命令面：`pm/ui-bridge.ts`（`PmWatchState`、`ownedByThisWindow`、`ackTasks`、`list_tasks`、dispatch 记账、`registerMwCommands` 签名）+ `pm/pm-orchestrator.ts` 一个调用点。
- **零 Python 改动、零文件格式改动**：不加 `_workers.parallel` 列、不拆 `_workers.acked`、不动 launcher/conductor；ack 写入仍持 `.mw/workers.lock`。
- 不改 watch widget 渲染（它本来就按 owner key 收窄）、不改 dispatch 路由/文档门禁/RAG 门禁。
- 行为变更有意为之（默认收窄 + 行格式 + ack 语义），已记 `packages/coding-agent/CHANGELOG.md` 的 Unreleased/Changed。
- 生效前提：`mw build --install` 已在 2026-09-23 17:18 完成（bundle 910,510 B / repo dist 同步重建），新窗口即生效，且已在真实进程验证（见下）。

## 真实验证（L2）

- 2026-09-23 17:19 `pi -p`（新进程、无 claim）调 `list_tasks` 默认 scope：返回 `No tasks found for this window (watched key: (none))` + `switch_key` / `scope: "all"` 指引，未列出本项目任何其它 key 的任务（含 `_scratch`）——AC-004 实机成立。
- 2026-09-23 17:20 `pi -p` 调 `list_tasks(scope:"all")`：返回 `mw-dispatch-reliability :: mw-dr-glm53 | done | pi | acked` 等行，owner 前缀与 acked 徽标均在线——AC-002/AC-011 实机成立。
- 两条路径均跑在重建后的 bundle/dist 上（grep 确认 `ownedByThisWindow`/`dispatchedTaskKeys` 同时存在于全局 bundle 与 repo dist）。

## 遗留

1. ~~未重建 bundle、未做实机目视~~ **已闭环**（2026-09-23 17:18 重建 + 17:19/17:20 两次真实进程验证，见上节）。
2. **多窗口并发实测未做**：两个窗口同时对同一批任务 ack 的真实竞争未跑（写入仍走既有 `.mw/workers.lock`，仅覆盖范围变窄）。要实测需两窗口 + 手工时序。
3. **派发记账跨窗口重启不保留**：窗口重启后 `mine` = watched key 口径；需要全局视野用 `scope:"all"`。若将来要求"重启后仍能列自己曾派发的任务"，需要落盘记账（新 key）。
4. **autopilot/conductor 侧仍是 any-key 读取**：`/autopilot monitor` 面板与 conductor 的内部扫描不受本 key 影响（有意保留系统级视野）。
