# T-01 — AC-003：`/worker` 跨 key 只读守卫前置 + 单点 `writeDispatchTaskMd`

- key: `mw-dispatch-settle-gates`｜AC: **AC-003**｜VC: **VC-009 / VC-010 / VC-011**｜波次 **1**｜链 1（`ui-bridge.ts`）首卡
- 角色: coding（read/write/edit/bash/find/grep/ls）
- **唯一允许改的路径**：① `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`；② 新建 `packages/coding-agent/test/suite/mwds-t01-worker-guard.test.ts`；③ 自身目录 `report.md`（`worker_file mode="write"`）
- 上游：`plan.md`（§4 契约 C3/C4、§5 证据要求、§6 运维约束）；`design.md` DD-13；`spec.md` AC-003

## 现状（先读代码确认，**以符号名为准**）
- 守卫 `foreignLiveClaimRefusal(indexStore, key)` 在 `ui-bridge.ts`（约 `:231`）；调用点仅 `:1333`（`dispatch_worker`）与 `:1698`（`advance_phase`）。
- `/worker` 命令注册约 `:1706-1714`，写盘链 ≈ `:1784` → `:1789-1794`（`planDispatchFrontmatter`）→ `:1813`（`workerTaskDir`）→ `:1814`（`mkdirSync`）→ `:1816`（`writeFileSync`）→ `:1819`（`dispatchTask`）⇒ **当前无守卫**。
- 拒绝文案（约 `:238-245`）自称覆盖 `/worker`：实现与文案不一致（缺口 G-c）。

## 必须实现
1. **守卫前置**：在 `workerTaskDir` 之前插入守卫（与 `:1333` **同一个函数**，不得复制判定逻辑）。他人 live claim 的 key ⇒ `ctx.ui.notify(<文案>, "warning")` + `return`，且**零副作用**：不得 `mkdir`、不得写 `task.md`、不得入队。
2. **单点化写盘**：抽出 `writeDispatchTaskMd(deps, {taskKey, type, body, frontmatter})`（契约 **C4**），返回 `{ok, path, injected}`；替换现有两处内联写盘（约 `:1411` 与 `:1816`），行为逐字等价（frontmatter 合并、目录创建、写盘顺序不变）。
3. **文案与守卫集合单一声明源**：导出常量（例 `CROSS_KEY_READ_ONLY_SURFACES = ["dispatch_worker", "/worker", "advance_phase"]`），文案模板与测试共用；测试断言"文案里列出的每个面都真的调用了守卫"。
4. 保留既有的 model-plan 前置（`planDispatchFrontmatter` 先判后写）与文档门（`dispatchDocGaps`）顺序，不得改变它们与守卫的相对次序语义（守卫仍在写盘前）。

## 反向用例（必须真跑并贴输出）
- (a) 本窗口自有 claim 的 key ⇒ 放行；(b) 无 live claim（未认领）⇒ 放行；(c) `_scratch` ⇒ 放行；(d) 拒绝后目录树快照不变（`taskDir` 不存在）。
- 不得影响：`dispatch_worker` / `advance_phase` 既有行为（同函数，回归覆盖）。

## 对照协议（`plan.md §5`，三组都要）
A 摘除守卫调用 ⇒ 拒绝对应用例转红；B 把守卫结果反转（始终放行）⇒ 拒绝用例转红；C 移除白名单/声明源中的 `/worker` ⇒ VC-011 转红。每组：sha256 → 逆改 → 跑测试（红）→ 还原 → 核对 sha256 → 再跑（绿），全部贴输出。

## 证据（写进 `report.md`）
```
[VERIFY] VC-009: refused=true side_effects=none taskdir_created=false queued=false
[VERIFY] VC-010: own=allow unclaimed=allow scratch=allow
[VERIFY] VC-011: declared_surfaces=3 guarded_sites=3
```
命令：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t01-worker-guard.test.ts`

## 禁止
不改 `pm-orchestrator.ts` / `worker-mode.ts` / 其他 `tasks/` 卡的文件；不改 `test/extensions/agent-team-loop.test.ts`（T-12 统一重锚）；不 `npm run build` / `mw build` / `mw build --install`；不跑全量 vitest / `./test.sh` / `npm run check`；不 commit / 不 `git add -A`；不动其他 key 的目录或进程。
