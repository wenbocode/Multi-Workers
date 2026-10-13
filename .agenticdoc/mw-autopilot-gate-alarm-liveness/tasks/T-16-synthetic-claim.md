# T-16 — 合成 claim：有工作但无 live claim 的 key 由 conductor 接管（AC-014 路线①）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-014
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D9；`spec.md` AC-014/**D-012/D-013（用户裁定路线①：合成 claim-id 接管，放弃 claim-free 派发）**；
      `evidence/research/design-drq4-auto-approve-20261013.md`（派发链 11 处 `dispatch.dispatch` 无一读 watch；真正阻断在状态机）、`workers/mwgal-t08-drq4-auto-approve/report.md`（AC-014 靶子清单 T-1…T-14）

## 上下文（含设计前必须确认的两条已核实事实）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守 ⇒ 派发不得以"有人 watch/接管"为前置）。
- **已核实事实 1**：**派发本身不依赖 watch** —— launcher 只读 `_workers.parallel` 的 pending 行（`packages/multi-workers/launcher.py:1856`、`:1899`），conductor 的 11 处 `dispatch.dispatch` 调用点**无一读 watch**；真正阻断在**状态机**（`autopilot/conductor.py:671 _stage_activation` 要求存在 `running` stage，check 在 `:682-683`）。
- **已核实事实 2**：**claim/owner 面确实会阻断**（C-35 运行期实证）—— 无 live claim 时 conductor **主动跳过**该 key（消息 `2 key(s) with work but stale owner evidence — claim-free repair skipped`）。owner 轴判定在 `packages/multi-workers/mw_common.py:2012 worker_owner_key`。
- 其它锚点：`_index.parallel` 行格式与解析器（自行定位，报告须给出 `path:line`）；`packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`（TS 侧索引读写）；`:70 _DISPATCH_SKIP_STATUSES`。
- **已知风险（必须绕开）**：全局队列 `_workers.parallel` 已发生过 **EPERM rename 半写** 事故；本卡**不得**引入第二个并发写者。

## 要求

1. **合成 claim 身份**：形如 `autopilot@<host>:<pid>`（须能与人工 claim 明确区分），写入既有 claim 轴（`worker_owner_key` 语义），**不新增文件格式**。
2. **生命周期三问必须回答并实现**：
   - **创建**：只对"**有工作但无 live claim**"的 key 创建（C-35 判据）；**不得**接管 idle 且无产物的 key（C-35 登记的另一半必须保持跳过）。
   - **续期**：必须有心跳/续期机制（给出周期与落点）。
   - **失效回收**：**必须与 T-13 已落的 serve 身份面交叉校验** —— serve 重启（pid 变）或进程消失 ⇒ 旧合成 claim 必须被判为**失效**（不得靠时间猜测；用 `serve.meta` 的 pid/`started_at_ms`）。回收时**不得**动人工 claim。
3. **与人工 `switch_key` 的移交与冲突**：人工接管**立即生效且优先**；人工持有期间合成 claim**不得抢回**；发生移交/冲突必须**留痕**（复用既有 timeline 事件名，不新造）。
4. **`_index.parallel` 呈现**：合成 claim 与人工 claim **在字段层面可区分**（不靠人读 pid）；**不得改变既有列数/顺序**、不得让既有解析器失败（含 TS 侧 `index-store.ts` 若它解析该轴）。
5. **单一写入方不变量**：每 key 的 claim 写入仍只有一条路径；不得因为本卡新增并发写者（EPERM 风险）。
6. **幂等与可重入**：重复 tick 不得重复创建/重复续期事件；合成 claim 存续期间不得因"无 watch"而反复跳过派发（这正是本条要修的症状）。
7. **回归测试**：① 无 live claim 有工作 ⇒ 合成 claim 建立且派发不再被跳过；② 续期生效、超期回收；③ 人工接管后合成 claim 让位且不抢回（含留痕）；④ serve pid 变 ⇒ 旧合成 claim 失效；⑤ index 呈现可区分 + 既有解析器兼容；⑥ idle 无产物 key ⇒ **仍跳过**（不误接管）。

## 写入允许面

- `packages/multi-workers/mw_common.py`（claim/owner 轴）
- `packages/multi-workers/autopilot/conductor.py`（claim 面接入；**不得动 T-12 stage-close、T-15 re-attest、T-14 blocker_class 已落区段**）
- `packages/multi-workers/autopilot/index_parallel.py` 或等价索引写入模块（自行定位）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`（仅当解析/呈现需要）
- 新增：`packages/multi-workers/test_mwgal_t16_synthetic_claim.py`
- 既有 Python 测试中因本卡行为必须更新的期望（逐条说明；不得改弱断言）

## 写入禁止面

- `_workers.parallel` 的写入路径（队列单写入方不变量）
- `packages/multi-workers/autopilot/gates.py`、`status-model.ts`（属 T-14）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/**`、`shared/change-ledger.ts`（属 T-17/T-17b）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/multi-workers`：`python -m pytest test_mwgal_t16_synthetic_claim.py test_mwgal_t15_reattest_confirm.py test_mwgal_t12_stage_close_auto.py -q`

## 改动历史

（填写：合成 claim 的字段形态、生命周期三问的实现落点、与 `switch_key` 的优先级实现、index 呈现方式、为何不需要新增写者。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
