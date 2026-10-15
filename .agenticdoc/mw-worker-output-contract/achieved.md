# mw-worker-output-contract — achieved.md（结案）

- Key: `mw-worker-output-contract`；结案日期 2026-10-15；PM 直执收口。

## 系统行为变化

本 key 把 worker 的「输出契约」从仅有账本记录变成**强制的五切面可判体系**。每个切面的变化与影响面：

1. **写面（T-01/T-10）**：新增 `shared/write-surface.ts`（416 行）作为写范围判定的**单一实现**，`worker-mode.ts` 与 `pm/ui-bridge.ts` 删除本地 `matchesWriteScopeEntry`/`minimatch` 拷贝，shell 守卫与 `write_scope:` 信封解析收敛到同一函数。影响面：所有 coding/research/review worker 的 `bash`/`write` 越面拦截（`write-scope: blocked …`），允许面/禁止面解析统一。
2. **账本（T-02/T-11）**：`change-ledger.ts` 抽取器加固——标题判定改为 `HEADING_RE` 捕获级别、H1 拒绝、别名**锚定在标题/子句开头**（移除 `includes` 子串误拦），`extractLedgerBody` 不再把卡头当声明体。影响面：变更账本的误报/漏报收敛（T-11 后真实语料 `extra=[]`），杜绝「T-02 报告被自己的 H1 标题误判」类假 `exit=2`。
3. **检查点（T-04/T-12）**：检查点机器判据改用**同一份落盘写事件**派生 `landed`/`lastLandingAgeMs`/`progressDone`，mtime 未来漂移改**钳制**（`stat.mtimeMs > nowMs ⇒ 0`）消除非确定性。影响面：checkpoint 的 mid/high risk 触发不再依赖易碎解析，Windows NTFS mtime 前进问题消除。
4. **判定（T-05/T-13）**：settle 时按 H2 标题判定受判产物（`output-sections.ts` 的 `checkRecovery` + `output-writer.ts` 的候选集 `judgedProductFile`：report.md → report-<slug>.md → output.md）；缺实质段 ⇒ `exit=2`；机械段（`上下文来源`）白名单自动补齐；T-13 把自检回合条件改为「**已交付**」（与 `finishSuccess` 同谓词），未交付保持立即 `no-product` 裁决。影响面：受判 run 的 `exit=2` 语义可解释、可修复；reply-only 已交付 run 拿到一次修复回合。
5. **回读（T-03/T-06）**：`output.md` 按段渲染 + S2 段清单注入（TS 侧 T-13 起全角色含 coding），settle 摘要带 `[VERIFY]`/`[END]` 机器行。影响面：PM 回读可直接看到缺失段集合与自检状态（`recovery-gap missing=… selfcheck=…` trace 行）。

部署状态：`mw build --install --allow-dirty` → `mw doctor` `serve code: fresh` + `bundle stale: False`；AC-010(b) 新跑 **6 worker 全部 `exit=0`**（research/review/coding 各 2）。

## 遗留

1. **模型服务间歇性挂死**（D-016）：deepseek-v4-flash-0731 请求偶发不返回，worker 无请求超时、活动看门狗把心跳当活动。去向：**建议立新 key**（给 worker 模型请求加超时/重试），或至少在下一轮部署前人工观察。
2. **陈旧 run.json**：`woc-t13-selfcheck`/`-r2` 仍标 `running`（PM 终止的进程，服务未 reconcile）。去向：**接受不处理**（无实害），或随手清理。
3. **T-12 重放语义**（D-014）：`wjg-w12` 重放 `last_land` 83s→0s（钳制把钉住时刻的追加算作 landed；`risk` 不变 `low`）。去向：**接受不处理**（已注册为已知限制，无 epsilon 阈值以避免重引入非确定性）。
4. **3 处 biome format 错误**（D-014）：`worker-mode.ts` + `mwoc-w4-checkpoint-invariants.test.ts`。去向：**接受不处理**（闭包时 scoped `biome check --write` 仅限本 key 文件，未执行 —— 仓库规则禁止 repo 级）。
5. **卡面行号漂移**：ACB-V1 卡写 `worker-mode.ts:2584` 实际函数在 `:3645`（符号锚定无歧义）。去向：**记入 `_pitfalls.md`**（P-037：派发卡行号在长文件易漂移，用符号锚定）。
6. **语料 n 漂移**：AC-010(a) 语料 433→437→463→465→466 活漂移，4 个数绑定运行时刻。去向：**接受不处理**（不设硬闸，AC-010(b) 用新产物）。
7. **部署需手动 /reload**：`mw build --install` 已装 0.83.0 bundle（`serve code: fresh`、`bundle stale: False`），但已打开的 pi 窗口不会自动加载新扩展。去向：**部署时逐个窗口执行 `/reload`**（T-08 `output.md` 已列 16 个 node 进程即当前打开窗口，逐个 `/reload` 后新 bundle 生效）。

## AC 兑现位置索引

- AC-001（跨入口一致）：`test/suite/mwoc-w2-contract-judgment.test.ts`（40 例）、`mwoc-matrix-t07.test.ts`（8 例矩阵两入口一致）
- AC-003/004（判定/自检）：`worker/output-sections.ts`、`output-writer.ts`、`worker-mode.ts::settleOrSelfCheck`；测试 `mwoc-w2`、`dispatch-recovery-terminal:197`、`output-recovery-contract:301`
- AC-005/010(a)/010(c)/017（重放/语料/矩阵）：`evidence/woc-t07-*`（corpus/flip-disposition/baseline-diff/per-file）+ `mwoc-matrix-t07.test.ts`（25 例）
- AC-006（no-product 裁决）：`worker-mode.ts::finishSuccess`；测试 `mwds-t04:401`
- AC-010(b)（新产物全过）：`evidence/scripts/new-worker-exit-scan.py` + T-08 记录（6/6 exit=0）
- AC-014/015（候选集/账本）：`output-writer.ts::judgedProductFile`、`mwoc-matrix-t07`（slug/report+slug/output-only 三形态）
- AC-017（四段）：`mwoc-matrix-t07`（a/b/c/d 四段）

五切面（写面/账本/检查点/判定/回读）全部点名于「系统行为变化」。
