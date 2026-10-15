# plan — mw-worker-output-contract

- Key: `mw-worker-output-contract`
- Phase: PLAN（2026-10-14）
- 上游：`spec.md`（AC-001…AC-017，用户已锁定）+ `design.md`（含 §9 写面切分、§10 验证计划）

## 1. 阶段目标与出口条件

把 design 的五个切面拆成**可并行、写面互不重叠**的编码任务，每任务带：独占写面、验收命令、AC 映射、证据落点。

出口条件（进入 execute 后逐条兑现）：
1. `tasks/*.md` 卡片齐（编码卡含 写入允许面 / 写入禁止面 / 验收命令）。
2. 每个任务的验收命令在实现后**由 PM 亲自复跑**并记录输出。
3. AC-010(b)：交付后新跑 ≥6 个 worker（research/review/coding 各 ≥1）受判产物全 `exit=0`。
4. 基线区分：改动后同集合只允许「新增红 = 0」，HEAD 既存 5 红与 3 处预期内改动单独登记。

## 2. 并行性分析（先做，再拆）

**共享资源与冲突面**：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` 是**唯一的强冲突文件**（写面注册点 / 抽取器 / 检查点 / settle 四处）；其次是 `pm/ui-bridge.ts`（派发期判定 + 清单注入）。

**决策**：把 `pm/ui-bridge.ts` **整体划给 T-01**（派发期面同源），把 S2 清单模板的注入拆成 T-06（`autopilot/dispatch.py`，Python 侧，与 TS 无文件冲突）。`worker-mode.ts` 的四处**必须串行**，按依赖排序 T-02 → T-04 → T-05（T-04 依赖 T-02 的账本语义先落地）。

## 3. 任务分解

### 批次 A（并行，无同文件冲突）

| ID | 任务 | 独占写面 | AC | 依赖 |
|---|---|---|---|---|
| **T-01** | 写面单一真源：新增 `shared/write-surface.ts`（deny 表 + 路径域 + basename + 唯一谓词），把 `worker-file-tool.ts` / 壳层守卫 / `pm/ui-bridge.ts::judgeWriteTarget` 改成薄适配；`WORKER_FILE_NAME_RE` 迁址+再导出（**不放宽**）；`evidence/**` 双基准（project-root / keyDir）；`write_scope` 亦约束 `worker_file`；`worker_file` description 写明唯一通道 | `shared/write-surface.ts`(新)、`worker/worker-file-tool.ts`、`shared/deliverable-evidence.ts`、`pm/ui-bridge.ts`、`test/extensions/agent-team-loop-worker-file-tool.test.ts`、新增 `test/suite/mwoc-w1-write-surface.test.ts` | AC-006 / AC-007(a) / AC-016 | — |
| **T-03** | 回读推送域：`notified.add` 后移、C1/C3 拆分、`readbackDelivered` 未读计数、AC-012 取方案 B（widget 尾行 `N unread`）、AC-013 只渲染 widget 不发消息；探针 P4 断言改写 | `pm/pm-orchestrator.ts`、`test/suite/mwoc-t01-readback-delivery.test.ts`(新)、`evidence/readback-push-scope-repro-20261014.mts` | AC-011 / AC-012 / AC-013 | — |
| **T-06** | S2 清单注入（生产者侧）：`## 交付段契约（本角色）` 由 `_envelope_card_body` 渲染，门控 `card is not None` | `packages/multi-workers/autopilot/dispatch.py`、对应 pytest | AC-002 | — |

### 批次 B（`worker-mode.ts` 串行链，按序派）

| ID | 任务 | 独占写面 | AC | 依赖 |
|---|---|---|---|---|
| **T-02** | 账本抽取器加固：先剥数据区（here-string/heredoc）再词法；目标只取写动词目标位 + `verbatim` + 单命令字面量环境；未解析落 `[WRITE_UNRESOLVED]`；`unjudgeable` 由**有效**事件数派生；label 表 41 保留 + 新增 `net-file-api` | `shared/change-ledger.ts`、`worker/worker-mode.ts`（抽取器段 + 记账段）、`test/suite/mwoc-w3-ledger-*.test.ts`(新) | AC-008 / AC-017 | — |
| **T-04** | 检查点 `landed` 信号：`writes`/`uniq_targets` 语义不变；新增 `landed`/`lastLandingAgeMs`/`artifactPresent`/`progressDone`（源 = `parseWriteFileEvents`）；`computeRisk` 扩展（`landed === undefined` 时 write 角色逐字节不变）；`[CHECKPOINT]` 行尾追加可选字段（`shared/heartbeat.ts:84` 正则扩可选组） | `worker/worker-mode.ts`（检查点段）、`shared/heartbeat.ts`、`test/suite/mwoc-w4-checkpoint-invariants.test.ts`(新) | AC-009 | T-02 |
| **T-05** | 契约判定 + 候选集 + 补齐：H2 标题档判定（45 别名不变、正文不参与）；候选顺序 `report.md → report-<slug>.md`(mtime) `→ output.md` 且**同批改 `reportProduct` 第二入口**；I2 补齐写「判定将要读的文件」（幂等、纯 append、fail-closed）；I1 自检回合（`followUp`，每进程一次） | `worker/output-sections.ts`、`worker/output-writer.ts`、`worker/worker-mode.ts`（settle 段）、`test/suite/mwoc-w2-contract-*.test.ts`(新)、`test/suite/output-recovery-contract.test.ts`、`test/suite/dispatch-recovery-terminal.test.ts` | AC-001…AC-005 / AC-010 / AC-014 / AC-015 | T-04 |

### 批次 C（收口，必须在 A+B 之后）

| ID | 任务 | 独占写面 | AC | 依赖 |
|---|---|---|---|---|
| **T-07** | 跨任务矩阵用例补齐 + 基线区分脚本：AC-010(a) 语料复跑（`evidence/scripts/` 已有）、AC-005 重放（8 例 `mechanical-only` 取 3）、AC-017 四段判据、基线红清单对比 | `test/suite/mwoc-matrix-*.test.ts`(新)、`evidence/` | AC-005 / AC-010 / AC-017 | A+B |
| **T-08** | 部署与生效：`mw build --install --allow-dirty` →（仅当无 running worker）`mw stop` + `mw start` → `mw doctor` → 记录 `/reload` 人工步骤；AC-010(b) 新跑 ≥6 worker | `packages/*/dist/**`、`.mw/**`（构建产物，非源码） | AC-010(b) | T-07 |
| **T-09** | 结案：`achieved.md`（含 `## 系统行为变化` + `## 遗留`）、`evidence/quality-gate-report-*.md`、`_pitfalls.md`/`_framework-reflect.md` 回写（FW-001 状态更新、FW-009 修法落地记录） | `achieved.md`、`evidence/`、`.agenticdoc/_pitfalls.md`、`.agenticdoc/_framework-reflect.md` | 全 AC 勾销 | T-08 |

## 4. 派发顺序与批次

1. **批次 A 一次派 3 个**（T-01 / T-03 / T-06）—— 写面零重叠，可并行。
2. 批次 A 回读后派 **T-02**；T-02 验收通过再派 **T-04**；T-04 通过再派 **T-05**（三者在 `worker-mode.ts` 串行）。
3. 批次 C 按序 T-07 → T-08 → T-09。

## 5. 每任务的验收命令（示例，卡片内逐条细化）

- TS 侧：`node ../../node_modules/vitest/dist/cli.js --run test/suite/<file>`（包根 `packages/coding-agent`），**不跑全量 `./test.sh`**（P-032）。
- Python 侧：`python -m pytest -q packages/multi-workers/test_<file>.py`（从仓库根）。
- 全量静态检查：`npm run check`（改动后必跑，全量输出）。
- 基线区分：先跑 `evidence/.../baseline-vitest.json` 覆盖的 24 个文件，比对新增红 = 0。

## 6. 风险与回退

| 风险 | 回退 |
|---|---|
| `worker-mode.ts` 串行链上某任务失败 | 按「单次修复 + 双倍预算重派一次」；再失败转 PM 直执（不静默降级） |
| T-05 的补齐行为触碰既有 settle 用例 | 3 处已登记为「预期内」；若新增红超出这 3 处 ⇒ 停手上报 |
| 部署后 serve 与 bundle 不一致 | `mw doctor` 必须 `serve code: fresh` + `bundle stale: False`；否则回退上一 bundle 并重跑 |
| 多窗口 `ui-bridge.ts` 行号漂移 | 一律符号锚定；实现卡禁止按行号定位 |

## 7. 出口

批次 C 完成后：`achieved.md` + quality-gate report 落盘 → `advance_phase(verify)` → `advance_phase(done, --summary)`。人工步骤只剩「每个已打开的 pi 窗口 `/reload`」，在报告中显式列出。
