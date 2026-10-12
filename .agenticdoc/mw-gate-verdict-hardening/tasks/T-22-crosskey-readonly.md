# T-22: AC-024 跨 key 只读（读全局 / 写限定）

- 波次: **3** · 依赖: —（与 T-17/T-19 同批；同写 `ui-bridge.ts` 的 T-09 在此之后）
- 写面（独占）: `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（仅新增守卫 + 工具描述；**不得改读面逻辑**）
- AC: **AC-024**（并修订 AC-019② 的反向用例）· VC: **VC-036 / VC-037 / VC-038**
- 基线: `776b82d7f`

## 问题（用户反馈 2026-10-10）

作用域收窄（T-19）解决了"PM 自动派发翻动全项目队列"，但**写侧仍有两个跨 key 入口**没有任何守卫：

1. `dispatch_worker`（`ui-bridge.ts`）——`resolveOwnerKeyWithSync` 里 `if (explicitKey) return explicitKey;`（**显式 key 直通，无告警无校验**）⇒ 任何窗口都能把 worker 写进别人的 key 目录 + 共享队列。
2. `advance_phase`（`ui-bridge.ts registerAdvancePhaseTool`）——对任意 key 直接 `runAgenticScript(advance_phase.py)` ⇒ 会改写**别人 key 的** `pm-state.md` 与 `_index.parallel` 行。

用户原话（设计意图）："一个更合理的设计是 pm 可以看其它 key 的 workers 和状态，但不能有改、重新派发等操作，也就是只读。"

## 交付

1. 新增导出 `foreignLiveClaimRefusal(indexStore, key): string | null` + 常量 `CROSS_KEY_READ_ONLY = "cross-key-read-only"`：
   - 判据 = `_index.parallel` 行的 `claimState(claimId, self) === "held-live"`（**与 `takeOverKey` 的 force 判据同源**，避免两套活性口径）；
   - 放行（返回 null）：`_scratch`、`_`/`.` 前缀、**index 中无行**（未认领新 key = 建 key 流程）、`claimId == self`；
   - 拒绝文本含固定码 `[cross-key-read-only]`、被拒理由（owner claim）、**允许什么**（`list_tasks` all/key、`mw_status`、`mw doctor`、面板）、**正确下一步**（`switch_key`）。
2. `dispatch_worker` 守卫：**仅当调用方显式传了 `key`** 时评估（隐式路径已由 `resolveOwnerKeyWithSync` 退化到 `_scratch` 并告警），位置在 `ragCheck` / 目录创建 / `dispatchTask` **之前** ⇒ 拒绝 = 零副作用。
3. `advance_phase` 守卫：`registerAdvancePhaseTool` 增加 `indexStore` 参数（3 个调用点同步：`pm-orchestrator.ts:773`、`agent-team-loop.test.ts` ×2），守卫在 `runAgenticScript` **之前** ⇒ 拒绝 = 脚本不执行。
4. 工具描述声明只读语义（`dispatch_worker` / `advance_phase` / `list_tasks`），顺带修正 `dispatch_worker` 描述里过期的 `.agenticdoc/<task_key>/task.md` 路径。
5. **读面零改动**：`list_tasks` 的 `scope:"all"` / `scope:"key"` 分支一字不动（有反向用例钉住）。

## 契约（冻结）

- 拒绝必须**先于任何副作用**：不建 task 目录、不写队列行、不写 `_workers.parallel`、不执行 gate 脚本。
- 固定码字符串 `cross-key-read-only` 是机器接口（测试与未来 doctor/告警可引），不得改字。
- **不得**为了"隔离"而限制读；`list_tasks` / `mw_status` / `mw doctor` / 面板对任意 key 保持可用。
- 可写面边界必须包含"未认领的新 key"（否则 PM 无法开新 key）。
- 不新增配置键、不新增事件类型、不动 gate schema。

## [VERIFY]

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts
```

实测（2026-10-10，基线 `776b82d7f`）：

```
Test Files  1 passed (1) / Tests  4 passed (4)      # worker-crosskey-readonly.test.ts
Test Files 18 passed (18) / Tests 368 passed | 1 skipped (369)   # 所有导入 ui-bridge/worker-store/pm-orchestrator 的测试文件
npm run check → 通过（biome/tsgo/shrinkwrap/install-lock/import 规则）
```

- VC-036：同一窗口 `list_tasks scope:"all"` 与 `scope:"key"` **能读** foreign-live key 的行；`dispatch_worker(key=…)` 返回 `[cross-key-read-only]`。
- VC-037：拒绝时零副作用（task 目录不存在、`store.readAll()` 为空、`_workers.parallel` 不存在）；`advance_phase` 拒绝时 stub 脚本的 `RAN` 标记文件不存在。
- VC-038：未认领新 key（`mw-new`）与自有 claim key（`claimId == windowClaimId()`）**派发成功**。

## 非空洞对照

脚本：`evidence/scripts/t22-controls.ps1`（字节安全 UTF-8 读写，跑完还原）

| 控制 | 变异 | 结果 |
|---|---|---|
| A | 删除 `dispatch_worker` 的显式 key 守卫 | **2 failed / 2 passed** |
| B | 删除 `advance_phase` 守卫 | **1 failed / 3 passed** |
| C | `foreignLiveClaimRefusal` 恒返回 null | **3 failed / 1 passed** |
| D | 破坏 `list_tasks scope:"all"` 全局读路径 | **1 failed / 3 passed**（反向用例抓得住） |

## 已知残余（诚实记录）

1. 裸 `bash` 直跑 `python advance_phase.py <他人 key> done` 可绕开工具层（AgenticTask 是外部仓；与 G3 的已知残余同源）。
2. 异主机 claim 一律保守判 live；同主机 claim 依 PID 存活判 live/stale —— 僵死 claim 判 `held-stale` ⇒ 放行（有意：防永久锁死）。
3. `dispatch_worker` 未显式传 `key` 时的 `_scratch` 退化是**既有**行为，本卡不改。

## 回执

写入 `evidence/runs/t-22-crosskey-readonly-report.md`（PM 直执，故直接落 evidence），并把控制脚本归档到 `evidence/scripts/`。
