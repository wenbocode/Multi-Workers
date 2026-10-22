# Plan — mw-decision-substitution

> 相位 PLAN · 依据 design.md（D-001..D-022）+ spec rev3（AC-001..015）· 2026-10-20

## 0. 执行原则

1. **先关后开**：每一波先证明"关闭态逐字节同构"，再实现开启态。任何一波的关闭态不成立即停止。
2. **契约先行**：§2 冻结接口已定，任务卡只允许在冻结契约内实现；要改契约必须回到 design 改 D-xxx。
3. **每波自带测试**：不写"后面补测试"，波次交付即含测试且波内跑绿。
4. **并行边界**：`W1 ∥ W2 ∥ W3` → `W4 ∥ W5` → `W6`。同波内两个 coding 任务不得落同一文件（见各卡写入面）。
5. **禁止提交**：worker 一律不 commit；提交由用户在收尾时决定。

## 1. 任务清单

| 编号 | 波次 | 任务 | 角色 | 写入面（关键文件） | 依赖 |
| --- | --- | --- | --- | --- | --- |
| T-01 | W1 | 注册表 + `decide_for` 11 步 + 配置表读侧（8 层降级 + 热重载） | coding | `packages/multi-workers/decision_points.py`（新建） | — |
| T-02 | W1 | `mw decide dp` 指令族（list/show/on/off/set/refresh/check）+ P0 flag + apply 骨架 | coding | `packages/multi-workers/mw.py`（仅 `dp` 子命令段） | T-01 |
| T-03 | W2 | 档案写入器 `decide_archive.py`（4 类行 + 链 + 幂等 + fold） | coding | `packages/multi-workers/decide_archive.py`（新建）、`test_decide_archive.py` | — |
| T-04 | W1+W2 | Python 测试套（注册表/控制流/配置/档案） | coding | `test_decision_points.py`、`test_decide_archive.py`（新建） | T-01..T-03 |
| T-05 | W3 | `triage-client.ts` 改造：dpId 入参、≤2000B、`input-incomplete`、digest 回传 | coding | `pm/triage-client.ts` | 契约（§2.6） |
| T-06 | W3 | `ask_decision` 工具 + 注册接线 + 反重试熔断 | coding | `pm/decision-tool.ts`（新建）、`index.ts` | T-05 |
| T-07 | W3 | TS 测试：stdin 字节 L2 断言、四模式、失败矩阵 | coding | `test/suite/decision-tool.test.ts`（新建） | T-05/T-06 |
| T-08 | W4 | dp3 插入（`finishSuccess` 内 `:3664`/`:3671` 之间）+ `nc_raw`/`nc_human` | coding | `worker/worker-mode.ts` | T-02/T-06 |
| T-09 | W4 | dp2 收窄（只允许 narrow）+ checkpoint 结构化输入 | coding | `pm/pm-orchestrator.ts` | T-02/T-06 |
| T-10 | W5 | `decision:` 头行（仅 `acted=true`）+ settle 追加（6 终态映射 + 幂等） | coding | `pm/ui-bridge.ts`、`pm/pm-orchestrator.ts` | T-03 |
| T-11 | W5 | 报告生成（advance_phase 挂点）+ `sign-final.md` 门禁两条 + `dp apply` + 写守卫 | coding | `mw.py`、`xkey-gate-guard.ts`、`advance_phase.py` | T-02/T-03 |
| T-12 | W6 | 文档 + CHANGELOG + 全量验证 + 度量基线复核 | coding | `README.md`、`CHANGELOG.md`、`docs/decision-substitution.md`（新建）、`evidence/runs/` | 全部 |

**注意写入面冲突**：T-02 与 T-11 都改 `mw.py` 但不同区段（`dp` 子命令 vs `apply`/门禁挂点），必须**串行**（T-11 在 T-02 之后）。T-09 与 T-10 都改 `pm-orchestrator.ts` → 串行。

## 2. 验收策略

| 层 | 命令 | 通过标准 |
| --- | --- | --- |
| Python 单测 | `cd packages/multi-workers && node ../../node_modules/vitest/dist/cli.js --run` | 新增全绿；既有 137 不回归 |
| Python 全量 | `./test.sh`（仓库根） | 零新增失败（Windows 基线 8 failed 不变） |
| TS 单测 | `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-tool.test.ts` | 全绿 |
| 类型/格式 | `npm run check` | 零 error / warning / info |
| 关闭态同构 | 手工：`dp` 全关跑一次派发，比对 run.json/output.md/trace.log 与基线 | 逐字节一致 |
| 端到端 | 开 `dp3` 跑一次真实 worker，制造一次可自答澄清 | 产生 `decide` 行 + `[mw dp3-answer]` steer + worker 继续执行 |

## 3. 里程碑

| 里程碑 | 内容 | 判据 |
| --- | --- | --- |
| M1（W1+W2） | 决策骨架可跑：配置表 + 注册表 + 档案 | `dp list` 24 项；`dp check` 干净；档案链可校验 |
| M2（W3） | 输入面与工具可用 | TS 测试绿；stdin 字节无 L2 |
| M3（W4） | 两个最高频点接入 | 关闭态同构；开启态各一次真实自答 |
| M4（W5） | 留痕闭环 | 报告自动生成；缺签收门禁 fail；`dp apply` 生效 |
| M5（W6） | 收尾 | 全量验证 + 文档 + 度量基线 |

## 4. 风险与回退

| 风险 | 触发信号 | 回退动作 |
| --- | --- | --- |
| W4 破坏 worker 终态 | 关闭态不同构 / NC 四面不一致 | `dp off dp3`；revert W4 提交 |
| 档案链在并发下断 | `dp check` 报 chain_breaks > 0 | 降级为"只 append 不校验"，修锁后恢复 |
| 2KB 上限频繁拒发 | 报告 `input-incomplete` 占比高 | 提高上限需改 spec（走修订流程） |
| 写守卫误伤人 | 人执行 `dp on` 被拦 | 守卫只在 agent 会话注册（`PI_CODING_AGENT`） |
| 契约变更 | 实现中发现冻结接口不够用 | 停手 → 回 design 改 D-xxx → 重新排波次 |

## 5. 预算与节奏

- 波次并行上限：3 个 coding worker（W1/W2/W3）；W4/W5 各 2 个（受文件冲突约束实际 T-09/T-10 串行）。
- 每张卡超时 40m，含验收命令；连续 2 次 wall timeout 则改派 `timi/gpt-6.1-sol`（T-19 前的已知 fallback）。
- 每波结束 PM 复跑该波验收命令，不复跑不算完成。

## 6. 与 goal.md 的对齐

本计划只增"决策替换"能力，不改 goal.md 的目标锚点机制（`goal.ts` / `_goal_gate_install` 属另一 key，禁碰）。所有 dp 的默认值都偏向保守（P1/P0 默认关），确保第一阶段不会在无人知情的情况下改变项目行为。


## 7. 修订 2 波次（签收交给模型 + decide_prepare 改名）

| 编号 | 波次 | 任务 | 写入面（关键） | 依赖 |
| --- | --- | --- | --- | --- |
| W9 | R2-1 | 签收自动化：`signoff` 配置、`dp25-signoff-conclusion`、`mw decide sign` auto 流程、`done` 门禁 disable 豁免、guard 文案与允许面、测试 | `decision.py`、`decide_signoff.py`、`decision_points.py`、`decide_registry.json`、`mw.py`、`advance_phase.py`、`shared/xkey-gate-guard.ts`、签收/注册表测试 | — |
| W10 | R2-1 | worker 改名：`decision` → `decide_prepare`（类型/角色/词表/白名单/镜像/文档）、role 级模型可配 | `mw_common.py`、`autopilot/dispatch.py`、`worker-mode.ts`、`shared/dispatch-card.ts`、`shared/dispatch-models.ts`、`ui-bridge.ts`、`.mw/dispatch.yml`、派发/镜像测试 | — |

并行边界：W9 与 W10 无可写文件重叠；CHANGELOG 与 `docs/decision-points.md` 的最终渲染由 PM 收口时统一做。
