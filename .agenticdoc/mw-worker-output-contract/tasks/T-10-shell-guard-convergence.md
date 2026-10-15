# T-10 · 壳层守卫与 `write_scope` 解析收敛到写面单一真源（补 T-01 未覆盖的第三个适配层）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「工具白名单按任务类型」「Worker 进程级隔离」）——写面判定只允许有一个真源，否则派发期与运行期迟早再次分叉。
- 本卡是 **T-01 留下的缺口补齐**（T-01 的 `## 残留与未验证` 第 1、4 条）：`design.md` §3.1 明确列出**三个**适配层，T-01 只完成了两个。
  - 已完成：`pm/ui-bridge.ts::judgeWriteTarget`、`worker/worker-file-tool.ts` 都从新模块 `shared/write-surface.ts` 导入同一谓词 `judgeWriteTarget`（`shared/write-surface.ts:349`）；`WORKER_FILE_NAME_RE` 全仓单一定义（`shared/write-surface.ts:54`）。
  - **未完成（本卡范围）**：壳层守卫仍自带第二套路径域/形状判定 —— `worker/worker-mode.ts:1669 bashWriteDenyReason`、`worker/worker-mode.ts:1802 checkBashWriteScopeTarget`，以及它们在 `pi.on("tool_call")` 否决处理器里的调用点。
- 第二个未收敛点：`write_scope:` 有**两份解析实现** —— `worker/worker-mode.ts` 的 `parseTaskMeta` 自带一份，`shared/write-surface.ts:259 parseWriteScopeHeader`（T-01 新增，由 `worker-file-tool.ts` 装载）是第二份。T-01 在卡面写面内无法消除这个重复。
- AC-016 的硬判据包含「两处判定共用同一常量/谓词（**不得各写一份正则**）」。派发期 ↔ `worker_file` 通道已同源；本次要把**壳层 bash 通道**这个第三处也纳入，否则 AC-016 只有 2/3。
- **已知且必须保留的差异（DR1 裁决，不是 bug）**：bash 通道解析出的是**绝对路径**，`evidence/x.md` 这类 keyDir 相对写法在 shell 语义下会被解析成 cwd 相对 ⇒ shell 通道对该形态继续 **fail-closed**；`worker_file` 通道接受双基准。本卡要求把这个例外**逐例列出并测试锁住**，而不是抹平。
- 硬约束（不变量 I3）：`writes`/`uniq_targets` 计数语义、`TOOL_ALLOWLISTS` ↔ Python REGISTRY 的 parity 锁、`[WRITE_SCOPE_SUMMARY]` 的 `allow`/`deny`/`allow-unknown` 计数语义、`research` 角色的窄通道行为，全部**逐字不变**。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅**壳层守卫段：`bashWriteDenyReason` / `checkBashWriteScopeTarget` / `matchesWriteScopeEntry` 的路径域部分 / 它们的 `pi.on("tool_call")` 调用点 / `parseTaskMeta` 的 `write_scope` 行）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts`（**仅**为收敛新增/调整导出，如需要）
- `packages/coding-agent/test/suite/mwoc-w10-shell-guard-parity.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`worker/worker-mode.ts` 的**抽取器/记账段**（T-02，已完成）、**检查点段**（T-04）、**settle 段**（T-05）一律只读；`worker/output-*.ts`、`pm/**`、`shared/heartbeat.ts`、`shared/change-ledger.ts`、`packages/multi-workers/**` 只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。开工前 `git status` 复核 `worker-mode.ts`：若发现 T-04/T-05 的改动尚未落地或该文件正被第三方编辑，**停下报告**，不要回退或覆盖别人的行。

## 要求

1. **壳层守卫的允许面走单一真源**：`taskDir` + `<key>/evidence/**`（双基准、不限扩展名）的判定必须来自 `shared/write-surface.ts`；不得在 `worker-mode.ts` 里保留第二份路径域正则或形状表。
2. **刻意保留的 deny 分类必须逐条说明并测试**：`pm-state.md`、`workers/_workers*`、`_index.parallel`、其他 key / `.agenticdoc` 根、`packages/**`（仅 writeless 角色）、`.git/**` —— 这些是 **bash 通道专属的角色分类面**，不是 `pmWriteDenyReason` 的副本。在证据里给出「哪些与 `shared/write-surface.ts` 共用、哪些刻意保留 + 理由」，并用测试锁住每条的判定结果。
3. **`write_scope:` 解析单一实现**：`parseTaskMeta` 与 `worker-file-tool.ts` 的装载必须走同一个函数（保留 `parseWriteScopeHeader` 或反向收敛，二者取一并说明理由）。全仓该解析只允许一处实现。
4. **DR1 例外不抹平**：shell 通道对 keyDir 相对 `evidence/x.md` 继续 fail-closed；`worker_file` 通道接受。用测试逐例锁住两侧结论，并在报告里明确这是**设计裁决**而非缺陷。
5. **不变量 I3 不回归**（必须给原始输出）：`mwds-t03-bash-write-scope` **63/63**、`write-face-runtime` **18/18**、`mwds-t02-write-intent` **38/39**（1 条 HEAD 既存红 `wjg-qg-evidence-closure`）、`agent-team-loop-worker-file-tool` **7/9**（HEAD 2 红）、`change-ledger` **12/12**、`agent-team-loop` **196/197**（HEAD 1 红 `:6381` 他 key 锚点）。
6. **三面 parity 测试**（新建 `test/suite/mwoc-w10-shell-guard-parity.test.ts`）：构造同一 target 集合，分别过「派发期谓词 `judgeWriteTarget`」「`worker_file` 通道」「壳层守卫」，断言三面结论一致（DR1 例外逐例列出并断言两侧的**预期**差异）。含 3 类越界（`../..`、其他 key、仓库源码）在壳层面的 fail-closed 证据。
7. **`research` 行为逐字保持**：不要写 `if (type === "research")` 之类的豁免分支；用既有套件证明。
8. `git diff --stat` 收尾只应含允许面文件（工作区其它 session 与 T-02/T-04/T-05 的改动需在报告里区分）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令与原始输出**：三面 parity 逐例表（含 DR1 例外两侧结论）、共用/刻意保留的 deny 条目清单与理由、`write_scope:` 单实现证据（`rg` 输出）、六组既有套件的条数、新测试条数。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w10-shell-guard-parity.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/write-face-runtime.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t02-write-intent.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

## 改动历史

- 2026-10-14 T-01 完成（`woc-t01-write-surface`，13/13 新测试绿）：写面单源只落了 2/3 适配层 —— 卡面「写入禁止面」把 `worker/worker-mode.ts` 列为只读（`plan.md` T-01 独占清单不含它，`design.md` §9 把该文件划给串行链），worker 依卡停手并登记残留，未越面。
- PM 据此新建本卡（记 `pm-state.md` D-010）：`design.md` §3.1 的三个适配层必须全部收敛，否则 AC-016 的「不得各写一份正则」只完成 2/3。
- 串行依赖：本卡必须晚于 T-02（同一文件的抽取器/记账段）且与 T-04/T-05 串行；建议次序 T-02 → **T-10** → T-04 → T-05。
