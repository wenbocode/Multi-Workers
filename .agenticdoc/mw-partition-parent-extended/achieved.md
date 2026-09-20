# Achieved: mw-partition-parent-extended

## 系统行为变化
- 修改功能：partition 模式的 parent 语义从「只读上下文」改为「分片工作区的扩展可写目录」——被切出单独开发的功能块就在 parent 内，worker（cwd = partition root）直接跨 partition + parent 开发，写 parent 是正常开发动作（无切出/复制/合并流程）。
- 读包含性：带 read_scope 的 partition 任务，parent root 默认并入允许集（Py conductor 派发时显式写入 frontmatter；worker 侧从 profile 块解析 union，覆盖 PM 窗口 TS 路径派发）——旧语义下有 scope 的任务读 parent 会被拦截。
- 防火墙次序不变：deny_globs 仍先于包含性生效，可对 parent 局部路径设防；空 read_scope 全拒形态不因 union 失效。
- 措辞：`mw partition set --parent` 报错与 help、task.md profile 块 parent 行（`Parent root (extended workspace, writable):`）均反映扩展区语义。
- 影响面：partition 模式任务的读权限默认集合；dual/single 与 cwd/撕裂校验/doctor/trace 写回语义零变化。

## 关键决策
- 双层执行点（Py 展开 + worker union）— 否决单层：TS 路径派发的任务会留下语义窟窿 / frontmatter 失去透明性。
- union 仅作用非空 scope — 否决 scope 非null 即并入：空 scope 是 fail-closed 全拒形态，不得凭空造包含集。
- `Parent root` 前缀解析兼容新旧标签 — 否决定长取行：升级时在途 task.md 不失效。

## 触达面
- `packages/multi-workers/autopilot/dispatch.py`（_expand_read_scope partition 分支）
- `packages/multi-workers/mw.py`（--parent 报错 + argparse help 措辞）
- `packages/multi-workers/mw_common.py`（render_partition_profile_md 标签）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts`（+parentRootFromTaskContent / +applyParentRootUnion）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（wiring union）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`（profile 标签）
- 测试：`test_partition_dispatch.py`、`test_mw_partition.py`、`test/fixtures/partition-profile-block.golden.md`、`test/suite/autopilot-read-scope.test.ts`、`test/extensions/agent-team-loop-profile-injection.test.ts`
- 构建产物：`packages/multi-workers/dist/extensions/agent-team-loop.js`（已重建；其中 exit 路径 try/catch hunk 经独立质检考证为已提交源码（44f30c338）的陈旧 dist 补齐，非未提交工作）

## 遗留
- `mw serve` 重启后 Py 侧变更（dispatch.py/mw_common.py）才在常驻进程生效（serve 内存中为旧模块；JS bundle 对新 spawn worker 即时生效）——用户择机重启，不立新 key。
- `npm run check` 全仓 tsgo 的 packages/ai 14 错误为并发 session kimi-coding WIP，非本 key 面，未触碰——去向：该 session 自行收敛。
- 无其他遗留。

## 沉淀
- Pattern：无（窄改，无新范式；read-scope 纯函数扩展沿用既有模式）
- 记忆更新：待 done 后询问（Hook 1）
