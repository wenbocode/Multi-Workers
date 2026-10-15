# T-DR6：验证策略与测试矩阵设计（design / research）

- Key: `mw-worker-output-contract` ／ worker: `woc-dr6-verification-matrix` ／ 卡: `.agenticdoc/mw-worker-output-contract/tasks/T-DR6-verification-matrix.md`
- 测量快照：2026-10-14 11:43–11:52（本机本地时间）；仓库工作树含**其他并行会话**的未提交改动（§2.1 逐文件列出）。
- 方法边界：**只读仓库**（未修改任何仓库文件；写面仅本任务目录 + `<key>/evidence/**`）。实跑 24 个 vitest 文件（558 用例，per-test JSON 落 `workers/woc-dr6-verification-matrix/baseline-vitest.json`）、1 个 pytest 文件（15 用例）、2 个只读语料统计脚本（输出落 `evidence/`）。禁止项全部未执行：`npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、全量 `./test.sh`。

## 结论

1. **AC-001…AC-017 全部可映射到现有测试文件**；只有 5 条 AC（AC-004 的自检回合、AC-011/012/013 的回读域、AC-015 的候选集、AC-006 的 evidence 通道）需要**新增测试文件**，其余是在既有文件上补用例或改断言。逐条矩阵见 §0.1 / §1。
2. **HEAD 既存红在本批实测中不止卡面写的 2 类**：24 个相关 vitest 文件 = 558 用例、**5 个既存红**（worker-file-tool 2、agent-team-loop 1 个 anchor integrity、mwds-t02 1 个语料 replay、mwds-t23 1 个 bundle sha）。后两者卡面基线**未列**，其中 `agent-team-loop.test.ts` 那条与交付无关（另一 key 的陈旧 `file:line` 引用 + 行号漂移）。区分办法见 §2。
3. **AC-010(a) 已固化为可复跑脚本**：`evidence/scripts/recovery-contract-corpus-stats.py` + 输出 `evidence/recovery-contract-corpus-stats-20261014.txt`。本次快照 n=**437**（语料是活的，PM 测时 433、RQ-1 测时 423）：整篇别名 **152/437=34.8%**、单词边界变体 148/437=33.9%、只认标题 **37/437=8.5%**（H2）、41/437=9.4%（H2/H3）；`alias_ok → heading_fail` **111** 例。PM 的 145/433 与 RQ-1 的 142/423 落在同一定义带内，差异是**语料时点 + 别名边界口径**，不是矛盾。
4. **AC-010(c) 的 111 例已逐条分类**：`evidence/recovery-contract-flip-disposition-20261014.txt` —— 仅缺 `上下文来源`（S3 机械补齐可救回）**8 例**，其余 **103 例**缺实质段（S1+S3 仍失败）。这直接证明「历史语料通过率不得当判据」。
5. **AC-010(b) 的可执行方案**见 §3：PM 在部署后派 ≥6 个（建议 9 个，3/3/3）worker，判据由独立脚本只读 `run.json`/`[END]` 得出，本 key 的结论不作为证据。
6. **部署序列**（§5）：`mw build --install --allow-dirty` → 确认**无 running worker** → `mw stop` + `mw start` → `mw doctor`；每个已打开 pi 窗口 `/reload` 是**人工步骤**，用固定表格记录窗口 id / 时间 / 版本。
7. **回归锁**（§6）：`agent-team-loop.test.ts:2052-2085`（断言 `:2079`）、`mwds-t04-deliverable.test.ts:154/171/184`（report.md 通道优先级 3 例）、worker-file-tool 既有 7 例、change-ledger+checkpoint 22 例、mwds-t03 63 例、其余 24 文件基线。

## 0. 结论与矩阵

### 0.1 AC → 测试矩阵（总表）

「实跑」列：`绿` = 本次已实跑且通过；`红(既存)` = 本次已实跑且**改动前**即失败；`新` = 需实现后新增用例（本次无法实跑）。

| AC | 判据要点 | 测试文件（既有 / 新增） | 夹具 | 断言要点 | 实跑 |
|---|---|---|---|---|---|
| AC-001 | 标题存在性判定 + 8 例矩阵 | `test/suite/output-recovery-contract.test.ts:98-141`（`checkRecovery (AC-003)`）扩 8 例 | `:52-84` 的真标题 fixture | 8 行表逐例 `{text, expectedMissing}`；`仅正文含别名` 判 missing；`标题用别名`/`重复`/`引用块内` 各 1 例 | 绿（现有 13 例） |
| AC-002 | settle 回读列出**全部**缺失段名 + exit=2 例数 | `output-recovery-contract.test.ts:144-200`、`test/suite/dispatch-recovery-terminal.test.ts:161-203` | `makeFixture(type)` + `COMPLETE_RESEARCH`/`MISSING_CONTEXT_SOURCES` | `## Questions` 首行严格等于 `missing section(s): <精确列表>`；`run.exit===2` 计数 == 期望表 | 绿（30 例合计） |
| AC-003 | 启动前 `task.md` 含契约段清单（可复制标题） | `test/suite/mwds-t02-write-intent.test.ts:480-531`（`AC-005a contract section (VC-019)`）扩清单断言；真任务侧另见 §3 | `applyWriteSurfaceContract`/`writeDispatchTaskMd` | 幂等定点 + 每个必需段出现一次 `## <段名>`；≥2 个真实 research/review `task.md` 命中 2/2（后置） | 绿（局部）/ 真实 2 例新 |
| AC-004 | settle 前一次结构化缺口 + 可解析 trace；补一轮后 exit=0 | 新 `test/suite/mwoc-t03-settle-selfcheck.test.ts`（harness + faux provider）；插入点 `worker/worker-mode.ts:2806-2822`（I1） | `test/suite/harness.ts` + `dispatch-recovery-terminal.test.ts` 的 `startWorker/settle` | `sendUserMessage` 只发一次 followUp 且点名缺段；trace 落一行新 `[FLOW] settle-selfcheck missing=…|ok`；第二拍 settle `exit=0` | 新 |
| AC-005 | 判定**之前**自动补齐 `上下文来源`；内容落最终文件；3 例重放 exit 2→0 | `output-recovery-contract.test.ts` + `dispatch-recovery-terminal.test.ts:399-430` 扩；插入点 `worker-mode.ts:2713-2720`（I2） | `MISSING_CONTEXT_SOURCES` + task.md `card_path`/`card_sha256` | `run.json.exit===0`；受判文件（`report.md` 优先）含 `## 上下文来源` 且含 card 路径 + ≥1 来源；判前内存文本 == 落盘字节 | 新（3 例重放受 §8.1 阻断） |
| AC-006 | `worker_file` 接受 `<key>/evidence/**`；越界 fail-closed + trace；basename 白名单 3/3 | `test/extensions/agent-team-loop-worker-file-tool.test.ts:127-330`；新 `test/suite/mwoc-t04-worker-file-evidence.test.ts` | `writeWorkerFile`/`registerWorkerFileTool`；`REJECTED_FILES` 12 值 | evidence 深层路径 `ok=true` + `[WRITE_FILE]` 1 行；`../..`/其他 key/`packages/**` 各拒绝且 0 文件 0 建目录；既有 basename 12 拒 + 3 通过 | 红(既存) 2 例（:177/:285），另 7 绿 |
| AC-007 | 文案层级 + 3/3 走对通道 | 同上 worker-file-tool 文件 + `mwds-t02:480-531`（卡面）+ `agent-team-loop-checkpoint-wiring.test.ts:311-340`（activeTools） | activeTools 快照 | (a) `write` 错误不再产生：writeless active set 含 `worker_file` 且不含 `write`；(b) 3 例真实形态 `worker_file` 调用 `ok=true`；pi 核心文本不可改（`packages/agent/src/agent-loop.ts:611`） | 新（a/b 后置） |
| AC-008 | rq2/rq3 命令产 0 伪 `[WRITE_FILE]`；rq1 形态产 0 伪路径 + ≥1 `unjudgeable` | `test/suite/change-ledger.test.ts:170-230`（producer）扩；`test/suite/mwds-t03-bash-write-scope.test.ts:429/874/1644-1720` | RQ-3 缓存命令：`workers/woc-rq3-ledger/{rq2-cmd,rq3-cmd,rq1-allbash}.json`（需拷进 `test/fixtures/`） | 抽取候选 0 条（rq2/rq3）；rq1 形态 0 伪路径且 trace 出现 ≥1 `unjudgeable` 事件；`[WRITE_SCOPE_SUMMARY]` 记录一致 | 绿（既有抽取器矩阵） |
| AC-009 | 已落盘 writeless `risk≠mid`；零落盘 `≥mid`；idle/墙钟 3 例不变 | `test/extensions/agent-team-loop.test.ts:3983-4430`（`AC-004 computeRisk` `:4061`）、`:4467-4640`（watchdog 集成）、`agent-team-loop-checkpoint-wiring.test.ts:193-279` | `wjg-w12` 形态 trace（`[WRITE_FILE]`=4 / `worker_file`=4 / 37,149 B 产物） | 两场景各 1 例 `[CHECKPOINT] … risk=`；3 例不变：正常活跃 `low/不变`、真挂死仍 idle-kill、预算尾段仍 wall/steer | 绿（22 例合计 + 196） |
| AC-010(a) | 两档通过率 + 命令落 `evidence/` | `evidence/scripts/recovery-contract-corpus-stats.py`；输出 `evidence/recovery-contract-corpus-stats-20261014.txt` | `.agenticdoc/**/workers/*/task.md`（header `type:`）+ `report.md`→`output.md` | 打印 n / 别名两变体 / 标题两变体 / flip 计数 / 逐文件 FLIP 列表 | 绿（本次 n=437） |
| AC-010(b) | 新跑 ≥6 worker 受判产物全 `exit=0` | 新 `test/suite/mwoc-t05-new-worker-exit.test.ts`（读真实产物，**非** faux）+ 脚本 `evidence/scripts/new-worker-exit-scan.py` | 部署后新派 9 个 worker（3/3/3）的 `run.json`/`trace.log` | 每例 `report.md` 非空（保证被 `judgeRecovery` 覆盖）且 `status==done`、`exit==0`、`[END] exit=0` | 新（后置，见 §3） |
| AC-010(c) | 111 例逐条处置 | `evidence/recovery-contract-flip-disposition-20261014.txt`（脚本内联于证据 §4） | 同 (a) 语料 | 逐条 `missing=` + `class=mechanical-only|substantive`；总数 111 / 8 / 103 | 绿（本次快照） |
| AC-011 | P3 补推恰好 1 次；P1/P2/P5/P6 不变；P4 改写；`:2079` 不回归 | 新 `test/suite/mwoc-t01-readback-delivery-scope.test.ts`；既有 `agent-team-loop.test.ts:2052-2085` | `fakePi`/`fakeUiCtx`/`vi.useFakeTimers()`；`queueTask` `:1970` | P2 `pushed(b1)==false` 且此窗 0 投递；P3 `count(b1)==1`；P4 **去掉** `step4===1` 绝对值（§1 AC-011）；C3（`!watch.key`）仍记账仍静默 | 绿（既有锁）/ 新（P3/P4） |
| AC-012 | 开窗即终态行：补推 1 次 或 显示未处理计数（机械判据写死在用例） | 同上新文件 + `test/suite/mwgal-t10-state-surface.test.ts:33/545/568`（widget 捕获） | 同上 | 二选一的用例必须有确定期望值；模块注释说明 `notified`（投递记账）与 `ackStore`（处理记账）分工 | 新 |
| AC-013 | 无 watch key 时出现未回读条数 N（N>0 出现、N=0 不出现） | 同上新文件（断言 widget 行或消息含 N） | `fakeUiCtx` 捕 `setWidget` | `N>0 → 出现`；`N=0 → 不出现`；不跨 key 广播不变 | 新（当前无该 surface） |
| AC-014 | 更正 `output-sections.ts:19-20` 误引 + FW-001 修法 5 | 无单测可表达；验收 = 两条 `git grep` + 既有 anchor 测试 `agent-team-loop.test.ts:6329-6383` | 文档文本 | `grep -n '99.4' worker/output-sections.ts` 命中改为真实出处（`shared/dispatch-card.ts:19-20` / 卡片语料 `file:line`）；`_framework-reflect.md` FW-001 同改 | 部分（FW-001 已改；源码注释待改） |
| AC-015 | `report-<slug>.md` 候选集与白名单对齐（纳入 or 移除）；既有优先级 3 例不回归 | `test/suite/mwds-t04-deliverable.test.ts:153-212`（通道顺序 b/c/d）+ `change-ledger.test.ts:196` + worker-file-tool 白名单 | `findNonEmptyReport`（`shared/deliverable-evidence.ts:105`）已认 `report-<slug>.md`；`agentProductText`（`output-writer.ts:140-147`）不认 | 选定方案后：受判文本来源 = `report-<slug>.md` 或白名单移除；3 例优先级断言逐字不变 | 绿（3 例） |
| AC-016 | 派发期与运行期同源；evidence 声明可满足；越界 3/3 拒 | `test/suite/mwds-t02-write-intent.test.ts:566-582`（`:580-582` 翻 true）、`:694`（deny 表）、`test/suite/mwds-t03-bash-write-scope.test.ts:189-231` | `isWhitelistedWriteTarget`/`judgeWriteTarget`/`checkBashWriteScopeTarget` | 1 research + 1 review 卡声明 `evidence/**` 判可满足；二审共用同一谓词（不得各写正则）；`../..`/其他 key/`packages/**` 3/3 拒 | 红(既存) 1 例（`:345` 语料 replay） |
| AC-017 | 四段：0 伪行 / .NET 各 1 行 / allow=3 deny=0 / `unjudgeable` 由有效事件派生 + 12 用例不回归 | `mwds-t03-bash-write-scope.test.ts:429/874/1644/1487/1535`；`change-ledger.test.ts` 全文件；新 .NET 分支用例 | 13/55/319/336 字符最小输入；`[System.IO.File]::WriteAllText/AppendAllText` | (a) 4 形态各 0 行 `[WRITE_FILE]`；(b) 两 API 各**恰好 1** 行；(c) `[WRITE_SCOPE_SUMMARY]` 由 `allow=0 deny=3` → `allow=3 deny=0`；(d) 乱码事件不再绕开 `unjudgeable` | 绿（既有 63 + 22 + 106） |

### 0.2 与卡面基线的差异（必须记录）

卡面给的前提是 `worker-file-tool 7/9`、`mwds-t02 38/39`、`change-ledger+checkpoint 22/22`、`mwds-t03 63/63`。本次实测**全部复现**，并新增发现两条卡面未列的既存红（§2.1）。因此验收的「不回归」基线必须用 §2.2 的**按用例名**差分，不能用聚合计数。

## 1. AC→测试矩阵（逐条细化）

只列每条 AC 的**反向对照**（当前实现必然失败的用例）与文件:行号；没有反向对照的「修好了」不算证据。

- **AC-001 / AC-002**：现有 `checkRecovery` fixture（`output-recovery-contract.test.ts:52-84`）全部是真标题，所以既有 13 例**不会翻转**（RQ-1 §6.1 结论，本次实跑 17 例全绿于 `output-recovery-contract.test.ts`）。反向对照必须新增：「仅正文含别名而无标题 ⇒ missing」——当前实现 `includes` 必然判 ok，新规则判 missing。`dispatch-recovery-terminal.test.ts:162`（缺段翻转）与 `:178`（完整报告 done）在 S1 下会因补齐/判定改变而改变期望，实现时必须成对改 fixture。
- **AC-003**：清单文本的单一来源应是 `pm/ui-bridge.ts` 的 `renderWriteSurfaceContract`（RQ-2 B5，工作树行号 `:1784-1801`）；测试复用 `mwds-t02:480-531` 的幂等定点断言。真实 2 例（research/review）只能在 AC-010(b) 窗口里取，**不能**用本次的 `task.md`（本卡不含契约段清单，正是要修的点）。
- **AC-004**：I1 位置 `worker-mode.ts:2806-2822`；复用生产路径已有的 settle 内 `sendUserMessage(..., {deliverAs:\"followUp\"})`（`:2817`、`:2848`）。反向对照：不实现时缺段任务没有第二轮、直接 `exit=2`。
- **AC-005**：I2 必须早于 `readTerminalGaps`（`:2740`）且早于 `hasDeliverableEvidence`（`:2720`）；「判定与产物一致」的机械证明是：读回盘上受判文件字节，复跑同一判定函数得到 `ok=true`。**阻断**：AC-005 要的 3 个「补录前前缀」在盘上不存在（RQ-1 未找到清单 #6：6 实例的 `output.md` 已被 PM byte-pure 补录；原文只在 `_framework-reflect.md` FW-001 的记录尺寸里），必须由 PM 提供这 3 段前缀字节作为 fixture，否则该条只能做到 2 例（QG 缺 1 段 + W-12 缺 5 段的可由盘上「删掉补录段」重建，W-15 同法）。
- **AC-006 / AC-007**：`worker-file-tool.test.ts:177/:285` 是 HEAD 既存红（目录快照不含 `trace.log`，见 §2.1），实现时必须先修这 2 例（把 `trace.log` 计入快照）再谈 evidence 通道；否则「既有 7 例不回归」无从判定。AC-007 的「文案」层不可落在 pi 核心（`packages/agent/src/agent-loop.ts:611`），只能落扩展可改面（`worker-file-tool.ts:91-100`）+ 卡面（`ui-bridge.ts:1787`）。
- **AC-008 / AC-017**：抽取器唯一实现 `worker-mode.ts:1554`；伪行最小复现 13 字符（RQ-3 §2.3）。反向对照用 RQ-3 已缓存的三份真实命令 JSON（`workers/woc-rq3-ledger/`），实现时应拷到 `packages/coding-agent/test/fixtures/` 以保持测试 hermetic。`unjudgeable` 现在是「零事件」派生布尔（`shared/change-ledger.ts:875-877`），乱码事件即可绕开；AC-017(d) 的判据必须改成「有效事件数为零」。
- **AC-009**：`computeRisk` 三支 `worker-mode.ts:283-286`；writeless 的 `writes=0` 恒真是**入参缺陷**（`READ_TOOLS`/`WRITE_TOOLS` `:260-262` 不含 `worker_file`）。不变量证明：idle 段只读 `lastActivityAt`（`:2591-2624`）、墙钟只读 `budgetMs`（`:2650-2654`），与 `risk` 无耦合；3 例验证复用现存 `agent-team-loop.test.ts:4512-4640`。
- **AC-010**：见 §3 与 §4。
- **AC-011 / AC-012 / AC-013**：P4 断言债的 diff 是 `step4 === 1 && had(\"b2\")` → `had(\"b2\")`（或 `step4 === step3 + 1`，探针 `:101`）。硬约束：`notified.add` 不能朴素后移到整条门禁之后——`:2079`（`agent-team-loop.test.ts`）要求 `!watch.key` 期间终态行在之后接管时**不得复活**。AC-013 的「未回读计数」surface 当前**不存在**（RQ-5 未找到 #3），是新增面。
- **AC-014**：`worker/output-sections.ts:19-20` 原文：`and the historical corpus is the / measured proof that strictness misfires (99.4% / 87.2%).`；真实出处 = `shared/dispatch-card.ts:19-20`（信封）+ `mw-dispatch-card-gate` 的 `spec-card-format-corpus-20261012.md:281`（301/345）与 `spec-dispatch-input-format-20261012.md:142`（341/343）。验收只能 `grep` + anchor 测试。
- **AC-015**：`findNonEmptyReport`（`shared/deliverable-evidence.ts:105-118`）**已**认 `report-<slug>.md`，而 `agentProductText`（`worker/output-writer.ts:140-147`）只读 `report.md`/`output.md` —— 这是「同一产物两套读法」的现存缺口；`reportProduct` 判定（`worker-mode.ts:2734-2739`）也只看 `report.md`。
- **AC-016**：当前 `judgeWriteTarget`（工作树 `pm/ui-bridge.ts:1707-1722`）允许面 = deny 表 → own taskDir → 无目录成分白名单 basename → shape 拒绝；**无 `<key>/evidence` 面**，而运行期 `checkBashWriteScopeTarget`（`worker-mode.ts:1625-1646`）允许 `taskDir + <key>/evidence` ⇒ 两处判定相反。`shared/write-face.ts` 已存在（**另一并行会话的未跟踪文件**，`git status` 显示 `??`），实现的单一谓词落点应在 `shared/`，且不得反向 import `worker-file-tool.ts`/`worker-mode.ts`/`ui-bridge.ts`（RQ-2 A14）。

## 2. 基线红区分办法

### 2.1 实测基线（24 个 vitest 文件 / 558 用例）

命令（包根 `packages/coding-agent`；`--reporter=json --outputFile` 落本任务目录）：

```
node ../../node_modules/vitest/dist/cli.js --run --reporter=json \
  --outputFile=../../.agenticdoc/mw-worker-output-contract/workers/woc-dr6-verification-matrix/baseline-vitest.json \
  test/suite/output-recovery-contract.test.ts test/suite/dispatch-recovery-terminal.test.ts \
  test/suite/change-ledger.test.ts test/suite/mwds-t02-write-intent.test.ts \
  test/suite/mwds-t03-bash-write-scope.test.ts test/suite/mwds-t04-deliverable.test.ts \
  test/suite/mwds-t05-output-sections.test.ts test/suite/mwds-t06-output-informativeness.test.ts \
  test/suite/mwds-t12-regression.test.ts test/suite/mwds-t21-write-intent-soundness.test.ts \
  test/suite/mwds-t23-cutover-recheck.test.ts test/suite/mwds-t25-version-and-dotless.test.ts \
  test/suite/mwds-t26-closeout-verify.test.ts test/suite/mwgal-t17-ledger-role-aware.test.ts \
  test/suite/mwgal-t17b-ledger-infra-writes.test.ts test/suite/mwgal-t17c-ledger-unresolvable.test.ts \
  test/suite/mwgal-t21-qg-fixes.test.ts test/suite/rag-research-doc.test.ts \
  test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-worker-file-tool.test.ts \
  test/extensions/agent-team-loop-checkpoint-wiring.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts \
  test/suite/autopilot-protocol.test.ts test/suite/mwgal-t10-state-surface.test.ts
```

输出（per-test 汇总，`baseline-vitest.json`）：`files 24 / tests 558 / not-passed 5`。5 个既存红：

| # | 文件:行 | 用例全名 | 失败要点 |
|---|---|---|---|
| 1 | `test/extensions/agent-team-loop-worker-file-tool.test.ts:177` | `writeWorkerFile (VC-005) VC-005: appends progress.md after a sentinel …` | 目录快照多出 `trace.log`（`[WRITE_FILE]` 事件副作用） |
| 2 | `…worker-file-tool.test.ts:285` | `size and slug limits enforces the slug length boundary (41 allowed, 42 rejected)` | 同上，快照多 `trace.log` |
| 3 | `test/extensions/agent-team-loop.test.ts:6381` | `T-17/B-1 anchor integrity (VC-MWGF-038 / AC-011) every spec.md / design.md file:line reference …` | `unresolved = [mw-guard-form-hardening/design.md worker/worker-mode.ts:747 ×2]`（另一 key 的陈旧引用 + 行号漂移） |
| 4 | `test/suite/mwds-t02-write-intent.test.ts:345` | `AC-005a corpus replay (VC-015) the writeless-without-shell corpus yields 0 false positives` | `falsePositives = [wjg-qg-evidence-closure]`（P2 的现场：声明写自己 key 的 `evidence/*.md`） |
| 5 | `test/suite/mwds-t23-cutover-recheck.test.ts:295` | `T-23 requirement 4 — same-source bundle sha expectation the card names the expected bundle sha256` | `digest 9544D8A4…` ≠ `EXPECTED_BUNDLE_SHA 975D4066…`（其他会话重建过 bundle） |

单文件复跑命令与结果（供复核）：

| 命令（包根） | 结果 |
|---|---|
| `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts` | `Tests 2 failed | 7 passed (9)` |
| `… --run test/suite/mwds-t02-write-intent.test.ts` | `Tests 1 failed | 38 passed (39)`；`[VERIFY] VC-015: corpus=448 … false_positives=1 violations=2` |
| `… --run test/suite/change-ledger.test.ts test/extensions/agent-team-loop-checkpoint-wiring.test.ts` | `Tests 22 passed (22)` |
| `… --run test/suite/mwds-t03-bash-write-scope.test.ts` | `Tests 63 passed (63)`；`[FORMS] total=79 covered=79 missing=0` |
| `… --run test/suite/output-recovery-contract.test.ts test/suite/dispatch-recovery-terminal.test.ts` | `Tests 30 passed (30)` |
| `… --run test/suite/mwds-t04-deliverable.test.ts test/suite/mwds-t05-output-sections.test.ts test/suite/mwds-t12-regression.test.ts test/suite/mwds-t06-output-informativeness.test.ts` | `Tests 50 passed (50)` |
| `… --run test/extensions/agent-team-loop.test.ts` | `Tests 1 failed | 196 passed (197)`（唯一失败 = 上表 #3） |
| `… --run test/suite/mwds-t21… test/suite/mwds-t25… test/suite/mwds-t26… test/suite/mwds-t23… test/suite/mwgal-t17… t17b t17c t21-qg` | `Tests 1 failed | 105 passed (106)`（唯一失败 = 上表 #5） |
| `cd packages/multi-workers && python -m pytest -q test_mwds_t07_reap_productfirst.py` | `15 passed` |

### 2.2 「HEAD 既存红」vs「本次引入红」的验收命令序列

`git stash` 被卡面禁止，替代办法按强度分三层，**必须三层都记**：

1. **先记工作树脏面**（写面允许本任务目录）：
   ```
   git status --porcelain -- packages/coding-agent/src packages/coding-agent/test > <taskdir>/status-before.txt
   git diff --stat HEAD -- packages/coding-agent/src packages/coding-agent/test > <taskdir>/diff-before.txt
   ```
   本次实测脏面（他会话；范围 packages/coding-agent/src 与 test）：`M autopilot/console.ts`、`M index.ts`、`M pm/ui-bridge.ts`、`M shared/implementation-gate.ts`、`M test/suite/autopilot-monitor.test.ts`、`M test/suite/dispatch-recovery-terminal.test.ts`、`M test/suite/mwds-t21-write-intent-soundness.test.ts`、`M test/suite/mwds-t23-cutover-recheck.test.ts`、`?? shared/{bash-segments,worktree-junction-guard,write-face}.ts`、`?? test/suite/{agent-team-loop-bash-segments,worktree-junction-guard-*,write-face}.test.ts`。
   ⇒ `worker/*.ts` 与 `shared/change-ledger.ts` **clean**：这些实现的测试结果**就是** HEAD 结果；`dispatch-recovery-terminal.test.ts`/`mwds-t21`/`mwds-t23`/`ui-bridge.ts` **dirty**：其当前结果不能当 HEAD 结果。
2. **按用例名差分（主判据）**：改动前跑 §2.1 的 JSON 基线，改动后用同一条命令写 `after-vitest.json`，然后
   ```
   python <taskdir>/diff-vitest.py baseline-vitest.json after-vitest.json
   ```
   （脚本最小实现：按 `assertionResults[].fullName` 建集合，打印 `new_failures`/`fixed`/`still_failing`）。**本次引入红 = `new_failures`**；`still_failing` 是既存红。禁止用「总失败数变化」判断。
3. **真 HEAD 对照（仅对 dirty 文件）**：`git archive HEAD <path> | tar -x -C <tmpdir>`（只读仓库、不写 `.git`，等价 stash 的替代），在 `<tmpdir>` 里软链/复制 `node_modules` 后单跑该文件；比较 HEAD 版与工作树版的 per-test 结果。若 `git archive` 不可用，退到 `git show HEAD:<path> > <tmp>` 做文本比对，并声明「未取得 HEAD 运行基线」。

### 2.3 为什么禁止用聚合计数

- 语料类用例是**非封闭**的：`mwds-t02:345` 的 `corpus=` 从 RQ-2 的 434 涨到本次 448（另有 key 在并行派 worker）；`AC-010(a)` 的 judged 语料本次 437（PM 测时 433、RQ-1 测时 423）。任何以「通过率/失败数」为闸的写法都会因语料漂移而假红/假绿。
- `dispatch-recovery-terminal.test.ts:391` 一类的用例读**真实磁盘存在性**（AC-004 ledger 组，他会话新增的 `src/z.ts` 存在性前置），属环境敏感。

## 3. AC-010(b)：「本 key 交付后新跑的 ≥6 个 worker 受判产物全 exit=0」

### 3.1 前置

1. `mw build --install --allow-dirty` 完成 + serve 重启 + 每个 pi 窗口 `/reload`（§5）。
2. **冻结判据脚本**：先落 `evidence/scripts/new-worker-exit-scan.py`，记录 sha256；派 worker 之后不得再改脚本（防自证）。
3. 记录窗口身份与时间：`PI_CODING_AGENT_VERSION`（或 `/mw doctor` 的 `bundle`/`serve_code` 行）+ 派发开始 iso 时间 `T0`。

### 3.2 派发矩阵（建议 9 个 = research/review/coding 各 3，满足「≥6 覆盖三类」并留余量）

- 用 PM 模式窗口的 `dispatch_worker` 工具（或 `/worker`）；每个任务 `task.md` 必须带 header `type:`（`coding|review|research`）。
- **强制每个任务写 `report.md`**（`worker_file` 或壳层），且内容含本类型契约段标题：
  - research/review：`## 结论` / `## 证据` / `## 残留与未验证` / `## 上下文来源`（review 另加 `## 未覆盖面声明`）。
  - coding：额外 `## 改动清单`。
  - 理由（必须写进任务书）：`judgeRecovery` 只在 `isWritelessRole(type) || reportProduct` 时生效（`worker-mode.ts:2740-2745`；`reportProduct` = `report.md` 非空，`:2734-2739`）。research/review 恒判；coding **不写 report.md 就不判**，拿到的 `exit=0` 是空洞满足。强制 `report.md` 使 9/9 都走受判路径。
- 任务内容用本 key 低风险主题（如「审计某文件的行号引用」「跑 X 单测并报告结果」），避免 worker 真改仓库源码；research/review 天然 writeless，coding 只允许改任务目录/evidence（或改一个 doc）。
- 若某任务需要写 `<key>/evidence/**`，正好顺带验证 AC-006；但**受判产物是 `report.md`**，不要只写 evidence。

### 3.3 产物收集（每个 worker）

```
.agenticdoc/<key>/workers/<task-key>/
  run.json     # status / exit / task_key / run_id / artifacts
  trace.log    # [START] / [TOOL] / [FLOW] / [END] exit=<n>
  task.md      # header type:
  report.md    # 受判产物（必须非空）
  output.md    # 框架落盘，含 ## TL;DR/Summary/[Questions]
```

判据（全部机器可读，**不看本 key 的结论**）：

1. `run.json.status == "done"` 且 `run.json.exit == 0`（`RunState` 见 `shared/run-store.ts:36-52`）。
2. `trace.log` 最后一条 `[END] … exit=0`（正则 `mw_common._END_LINE_RE`；Python 侧 reap 同源）。
3. `report.md` 非空，且在**新标题判定**下 `missingSections == []`（跑 `recovery-contract-corpus-stats` 同源逻辑，或实现后的判定函数）。
4. research/review 的 `output.md` 不含 `## Recovery Gaps` / `## Ledger Unjudgeable`（缺段/账本不可判的产物段）。
5. `task.md` 含契约段清单（AC-003）。

### 3.4 独立扫描脚本（落点：`evidence/scripts/new-worker-exit-scan.py`）

接口：`--key mw-worker-output-contract --since <iso> [--assert] [--json]`。行为：枚举 `<root>/<key>/workers/*/run.json`，筛 `started_at >= since`，读 `task.md` header `type:`，要求 `report.md` 非空；打印 `task_key type status exit end_exit report_bytes`；`--assert` 模式下任一不满足即 exit 1。**脚本本身先于派发落盘并记 sha256**。

### 3.5 避免自评偏差（硬要求）

- 判据执行者 = §3.4 脚本（只读 `run.json`/`trace.log`/`report.md`），**不是**本 key 的分析文本，也**不是** PM 的转述。
- 证据只收**原始文件 + sha256**（`run.json`、末条 `[END]` 行、`report.md` 字节数），不收「本 key 报告里的统计」。
- 采样窗必须 `started_at >= T0`（部署后），排除历史 worker；`--since` 使这不可绕过。
- 若某例失败，必须原样记录并计入，不得剔除；失败原因分类（缺段/账本/超时/真挂死）写进报告。

## 4. AC-010(a)：复跑脚本与输出

- **落点**：`evidence/scripts/recovery-contract-corpus-stats.py`（脚本，本次新建）+ `evidence/recovery-contract-corpus-stats-20261014.txt`（输出）+ `evidence/recovery-contract-flip-disposition-20261014.txt`（AC-010(c) 逐条处置）。
- **可复跑命令**（仓库根）：
  ```
  python .agenticdoc/mw-worker-output-contract/evidence/scripts/recovery-contract-corpus-stats.py --flips
  ```
- **口径**（写进脚本 docstring，避免再争议）：
  - 语料 = `.agenticdoc/**/workers/*/task.md` 且 header 有 `type:`；受判文本 = 非空 `report.md`，否则非空 `output.md`（与 `agentProductText` 同序）。
  - 段表 = base4（结论/证据/残留与未验证/上下文来源）+ coding `改动清单` / review `未覆盖面声明`；别名表 = `worker/output-sections.ts:46-53` 全 45 条。
  - tier A = 现行整篇 `includes`；tier A2 = ASCII 别名加词边界；tier B = `## ` 标题行包含别名；tier B2 = `## `/`### ` 标题行包含别名。
- **本次实测输出**（脚本 stdout）：
  ```
  judged targets: n=437
  type distribution: {'review': 30, 'coding': 278, 'research': 128, 'vision': 1}
  tier A alias substring (current checkRecovery, includes): 152/437 = 34.8%
  tier A2 alias word-boundary variant:                     148/437 = 33.9%
  tier B heading H2 contains:                              37/437 = 8.5%
  tier B2 heading H2/H3 contains:                          41/437 = 9.4%
  flip alias-pass to H2/H3-heading-fail:                   111/437 = 25.4%
  heading-tier missing frequency: 上下文来源=362/437, 残留与未验证=311/437, 证据=124/437, 结论=86/437, 改动清单=72/437, 未覆盖面声明=22/437
  ```
- **与 PM/RQ-1 数字的对照**：PM 145/433=33.5% / 35/433=8.1%（11:2x）；RQ-1 142/423=33.6% / 29/423=6.9%。差异全部来自 (i) 语料时点（423 → 433 → 437，只增不减）与 (ii) 别名/标题的边界口径（tier A 34.8% vs A2 33.9%；tier B 8.5% vs B2 9.4%）。**结论同向**：标题档远低于整篇档，`S1` 单独上线会显著压低历史通过率 ⇒ 不得以历史语料通过率当判据（AC-010 已按此重写）。
- **AC-010(c)**：`evidence/recovery-contract-flip-disposition-20261014.txt` 逐条给出 `missing=` 与 `class=`；本次快照 = 111 例中 **8 例仅缺 `上下文来源`**（S3 机械补齐可救回）、**103 例缺实质段**（S1+S3 仍失败）。该文件同时是「历史产物生产于旧契约年代、不可作新契约判据」的量化证据。

## 5. 部署与生效验收序列

### 5.1 命令序列

工作目录任意（`mw.py` 路径自解析、cwd 无关）。`<mw> = packages/multi-workers/mw.py`。

```
# 0) 记录脏面（--allow-dirty 需要人工确认）
git status --porcelain -- packages/coding-agent/src > <evidence>/deploy-status-before.txt

# 1) 重建 bundle + 装全局 + 重建 npm-link 的 dist
python <mw> build --install --allow-dirty
#   期望：built + self-check OK (activate) version=0.83.0
#         [mw build] bundle: packages/multi-workers/dist/extensions/agent-team-loop.js
#         [mw build] installed globally: ~/.pi/agent/extensions/agent-team-loop.js
#         [mw build] Restart open pi windows to load the new bundle and dist.
#   注意：不加 --allow-dirty 时，只要 packages/coding-agent/src 有未提交改动就会**拒绝**（多会话共享 cwd 时多半属于别的会话）。

# 2) 重启 serve 前必须确认无 running worker
python <mw> doctor --json > <evidence>/doctor-before.json
python -c "import json;d=json.load(open('<evidence>/doctor-before.json',encoding='utf-8'));print(d['worker_liveness'])"
#   判据：worker_liveness == []（doctor 只列 status=running 且带心跳的行，mw_common.py:2471-2505）。
#   若非空：等待其终态，禁止重启（重启会打断在跑 worker）。

# 3) 重启 serve
python <mw> stop        # 优雅停，最多等 30s
python <mw> start       # 后台新 PID
python <mw> status      # [mw status] running (PID …) + serve code: <fresh>

# 4) 全链诊断
python <mw> doctor      # exit 0 = healthy
python <mw> doctor --json > <evidence>/doctor-after.json
#   检查：service.running=true；serve_code.verdict != drift；bundle ok；queue 无孤儿。
```

- `mw build --install` 的 dist 重建**先于**全局 bundle 拷贝（`_deploy_bundle` 注释：失败则不动全局，fail-closed）；若只想快速装扩展可用 `--no-dist`，但**本 key 改了 `src`，必须重建 dist**，因此不要加 `--no-dist`。
- bundle sha 会变（`mwds-t23:295` 那条既存红即因此），验收时应把新 sha 写进证据，而不是让它保持绿。

### 5.2 `/reload` 人工步骤的记录格式

每个**已打开**的 pi 窗口都要 `/reload`（扩展 bundle 与 dist 在进程内已缓存；`index.ts:13-22` 注释明确 `/new`、`/resume`、`/fork`、`/reload` 会重建 runtime 并重跑 `activate()`）。记录表（落到 `evidence/deploy-reload-log-<date>.md`）：

| 窗口 id（PID / 会话） | 角色 | `/reload` 时间 | reload 结果 | `/mw status` 或 `/mw doctor` 版本行 | 备注 |
|---|---|---|---|---|---|
| e.g. `WENBOZHOU-PC4:162452` | PM | 2026-10-14T… | ok | version=0.83.0 | 新旧 bundle 双载会触发工具冲突，reload 后应无 |

判定：reload 后执行 `/mw doctor`（或 `/mw status`），其 `bundle`/`serve_code` 行与 §5.1 第 1 步输出的版本/sha 一致；worker 窗口另跑 `/reload` 后再派发（AC-010(b) 的 T0 在全部 reload 之后）。

### 5.3 失败回退

- 若 `mw build` self-check 失败：全局 bundle 未被覆盖（dist 也先失败），旧版本仍可用；修 `src` 后重跑。
- 若 serve 重启后 `serve_code.verdict = drift`：`serve.meta` 与代码树不一致 ⇒ 重新 `mw build --install` 并再次重启（先确认无 running worker）。
- 若 reload 后扩展未生效：检查 `~/.pi/agent/extensions/agent-team-loop.js` mtime 是否等于本次 build 时间；双载保护（`__agentTeamLoopActivated`）在 `session_shutdown` 才释放，`/reload` 走的是 session 替换路径，若仍无效则 `/new`。

## 6. 回归锁清单

### 6.1 必须保持通过（改动前后同一用例名）

| 锁 | 文件:行 / 用例 | 关联 AC | 命令 |
|---|---|---|---|
| L1 | `test/extensions/agent-team-loop.test.ts:2052` `stays silent without a watched key and for tasks under other keys`（断言 `:2079`「`watch.key = key-a` 后 `messages === []`」） | AC-011(d) | 单跑该文件 |
| L2 | `test/suite/mwds-t04-deliverable.test.ts:154/:171/:184`「通道顺序 b/c/d」3 例（`report.md` 0 字节 → output 通道；placeholder-only → none；machine-line-only → output） | AC-015 | 单跑该文件 |
| L3 | `test/extensions/agent-team-loop-worker-file-tool.test.ts` 既有 7 例（`:128/:151/:189/:221/:239/:258/:292/:310` 中除 `:177/:285` 两条） | AC-006/007 | 单跑该文件，必须 `7 passed` + 已知 2 红 |
| L4 | `test/suite/change-ledger.test.ts` + `test/extensions/agent-team-loop-checkpoint-wiring.test.ts` = 22 例 | AC-008/009/017 | 两文件一起跑 |
| L5 | `test/suite/mwds-t03-bash-write-scope.test.ts` 63 例（含 `:429` 抽取器表、`:874` verbatim 契约、`:1644` heredoc、`:1023` 审计汇总） | AC-016/017 | 单跑 |
| L6 | `test/suite/mwds-t02-write-intent.test.ts` 38 例（除语料 replay `:345`） | AC-007/016 | 单跑，允许 1 条既存红 |
| L7 | `test/suite/output-recovery-contract.test.ts` + `test/suite/dispatch-recovery-terminal.test.ts`（30 例） | AC-001/002/005/015 | 两文件一起跑 |
| L8 | ledger 家族 8 文件 106 例：`mwds-t21-write-intent-soundness`、`mwds-t23-cutover-recheck`、`mwds-t25`、`mwds-t26`、`mwgal-t17`、`t17b`、`t17c`、`t21-qg` | AC-008/017 | 一起跑，允许 1 条既存红 |
| L9 | `test/suite/mwgal-t10-state-surface.test.ts`、`test/extensions/agent-team-loop-watch-aggregate.test.ts`、`test/suite/autopilot-protocol.test.ts`、`test/suite/mwds-t12-regression.test.ts` | AC-011/012/013 lock + C/W parity | 一起跑 |
| L10 | `packages/multi-workers/test_mwds_t07_reap_productfirst.py` 15 例（exit→status 映射，AC-010(b) 的 Python 半边） | AC-010(b) | `python -m pytest -q test_mwds_t07_reap_productfirst.py` |

### 6.2 已知既存红（**不阻断**本次交付，但不得新增）

`agent-team-loop-worker-file-tool.test.ts:177/:285`（trace.log 计入快照后应变绿）、`agent-team-loop.test.ts:6381`（他 key 文档 anchor）、`mwds-t02:345`（P2 现场，AC-016 应使其变绿）、`mwds-t23:295`（bundle sha，部署后自然改变，应更新期望值）。

### 6.3 命令汇总

```
# 完整基线（24 文件，per-test JSON）
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run --reporter=json \
  --outputFile=../../.agenticdoc/mw-worker-output-contract/workers/woc-dr6-verification-matrix/after-vitest.json \
  <§2.1 的 24 个路径>
# 逐用例差分（本次引入红 = new_failures）
python ../../.agenticdoc/mw-worker-output-contract/workers/woc-dr6-verification-matrix/diff-vitest.py \
  baseline-vitest.json after-vitest.json
# pytest 半边
cd packages/multi-workers && python -m pytest -q test_mwds_t07_reap_productfirst.py
```

禁止：全量 `./test.sh`（P-032：无墙钟超时，实测 7h14m 挂死）；`npm run build`；`npm install|ci`；`git stash|checkout|reset|clean`。

## 7. 语料非封闭性与验收纪律

1. 任何语料计数都必须带 **n + 时间戳 + 脚本 sha**；跨时点比数字无意义（本次 437、PM 433、RQ-1 423）。
2. 语料类用例只允许断言**集合内容**（如 `falsePositives === []`、`extra === []`）或**自洽关系**（`deny = 实际 deny 数`），禁止断言计数上界/下界。
3. `AC-010(b)` 是唯一「新产物」判据；历史产物（AC-010 a/c）只作背景与分类，不作闸。

## 证据

- 实跑命令与结果：§2.1（9 条命令，逐字结果）；per-test 原始 JSON：`workers/woc-dr6-verification-matrix/baseline-vitest.json`（24 文件 / 558 用例 / 5 not-passed）。
- 语料脚本与输出：`evidence/scripts/recovery-contract-corpus-stats.py`、`evidence/recovery-contract-corpus-stats-20261014.txt`（120 行，含 111 条 FLIP）、`evidence/recovery-contract-flip-disposition-20261014.txt`（113 行，`class counts: {'substantive': 103, 'mechanical-only': 8}`）。
- 源码锚点（本次逐条读过）：`worker/output-sections.ts:19-20/30/34-37/46-53/87-91`；`worker/output-writer.ts:140-147/202-203/257-259`；`worker/worker-mode.ts:260-262/283-286/1554/1625-1646/2383-2385/2713-2746/2806-2822`；`worker/worker-file-tool.ts:42/91-100/104-106`；`shared/change-ledger.ts:875-877`；`shared/deliverable-evidence.ts:105-118`；`pm/ui-bridge.ts`（工作树 `:1698-1740`、`judgeWriteTarget` `:1707`）；`packages/agent/src/agent-loop.ts:611`；`packages/multi-workers/mw.py:4702-4730/4618-4652/6556-6566`；`mw_common.py:2327-2332/2471-2505`。
- 既有测试锚点：`agent-team-loop.test.ts:1999/2022/2052-2085/3983-4640/6329-6383`；`mwds-t04-deliverable.test.ts:153-212`；`dispatch-recovery-terminal.test.ts:161-203/285-430`；`output-recovery-contract.test.ts:98-200`；`worker-file-tool.test.ts:127-330`；`change-ledger.test.ts:65-230`；`checkpoint-wiring.test.ts:193-470`；`mwds-t02:305-345/480-531/566-582`；`mwds-t03:173-231/429/874/1023-1110/1644-1760`。

## 残留与未验证

1. **AC-005 的 3 例重放受阻**：补录前前缀不在盘上（RQ-1 未找到 #6）。需 PM 提供 3 段前缀字节才能满足「3/3」。否则最多可重建 2 例（QG/W-12 删补录段）。
2. **AC-010(b) 未跑**：需要部署 + 真实派发，本任务为只读 design 阶段，不能实跑；§3 给的是方案与判据。
3. **AC-004/011/012/013/015/016/017 的新用例均未实跑**（实现后才存在）；本次只确认了既有锁与基线红。
4. **`mw build --install` 与 serve 重启未实跑**（禁止 `npm run build`；重启会打断其他会话的 running worker）。§5 命令来自源码（`mw.py:4702/4618/539/483`）与 `mw_common.py` 的结构，未做端到端演练。
5. **`git archive` HEAD 对照未实跑**（需要临时目录与 node_modules 链接）；§2.2 第 3 层是设计，不是实测。
6. **tier 口径未定稿**：AC-010(a) 的两档到底是 tier A/B 还是 A2/B2 需 design 定；本次四种口径的数值都已记录，PM 145/35 与 RQ-1 142/29 都在带内。
7. **`report.md` 优先级 3 例的口径**：卡面未点名文件；本报告按 `mwds-t04-deliverable.test.ts:153-212` 的「通道顺序 b/c/d」3 例解释，并把 `dispatch-recovery-terminal.test.ts` 的 report.md 用例一并列入 L7，故锁集合是**超集**（更安全）。

## 上下文来源

- 卡：`.agenticdoc/mw-worker-output-contract/tasks/T-DR6-verification-matrix.md`；dispatch card `mw-dispatch-card: v1`（task.md 内）。
- spec（已锁定 AC-001…AC-017）：`.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P1-P6、§1.6 S1-S6、§2.3、§2.4、§3、§4 R1-R9）。
- 兄弟 design 卡（避免重叠）：`tasks/T-DR1-write-face-channel.md`、`T-DR2-contract-judgment.md`、`T-DR3-ledger-hardening.md`、`T-DR4-checkpoint-invariants.md`、`T-DR5-readback-delivery.md`。
- spec 阶段研究证据：`evidence/research/spec-rq1-contract-corpus-20261014.md`（判定链/别名表/语料）、`spec-rq2-write-face-20261014.md`（写面三层 + 34 改动点）、`spec-rq3-ledger-20261014.md`（抽取器 41 标签 + 最小复现 + 12 测试文件）、`spec-rq4-checkpoint-settle-20261014.md`（检查点链 + I1/I2）、`spec-rq5-readback-push-20261014.md`（13 分支 + 探针断言）。
- 目标锚点：`.agenticdoc/goal.md`；门禁参考：`.agents/skills/agentic-task/references/workflow-quality-gate.md`。
- 本轮实测产物：`workers/woc-dr6-verification-matrix/{baseline-vitest.json,explore-stats.py}`；`evidence/scripts/recovery-contract-corpus-stats.py`；`evidence/{recovery-contract-corpus-stats-20261014.txt,recovery-contract-flip-disposition-20261014.txt}`。

## 未覆盖面声明

- **未实现任何代码**：本卡是 design 阶段 research；§1 的新用例只是落点与断言设计，未编写、未运行。
- **未跑全量套件**（禁止 `./test.sh`）；未跑 `npm run check`；未跑 `npm run build`；未跑 `mw build`/`mw doctor`/serve 重启。
- **未覆盖 pytest 全量**：只跑 `test_mwds_t07_reap_productfirst.py`；其余 `test_*.py`（launcher/conductor/verdict 等）未跑，pytest 侧账本相关用例按 RQ-3 结论为「不存在」。
- **未覆盖 `dist/` 行为差异**：所有 vitest 走 `src`（vitest 直接 import ts）；`packages/coding-agent/dist/**` 与 `packages/multi-workers/dist/extensions/agent-team-loop.js` 未做逐字节等价核对。
- **未做多窗口 / 真实 provider / 真派发端到端**：AC-010(b)、AC-003 的真实 2 例、AC-007 的真实通道选择都属后置。
- **未核 `pm/ui-bridge.ts` 行号稳定性**：该文件在他会话脏树中（`git status` 显示 M），本报告以函数名锚定（`judgeWriteTarget`、`renderWriteSurfaceContract`），行号为当时快照。

[VERIFY] vitest_files=24 vitest_tests=558 vitest_preexisting_reds=5 (worker-file-tool:177,:285; agent-team-loop:6381; mwds-t02:345; mwds-t23:295); green_baselines=change-ledger+checkpoint=22/22 mwds-t03=63/63 t04+t05+t06+t12=50/50 output-recovery+dispatch-terminal=30/30 agent-team-loop=196/197 t21..t21-qg=105/106; pytest_reap=15/15; corpus_snapshot_n=437 alias_substring=152(34.8%) alias_boundary=148(33.9%) heading_h2=37(8.5%) heading_h23=41(9.4%) flips=111 mechanical_only=8 substantive=103; ac_new_test_files=5 (mwoc-t01-readback, mwoc-t03-settle-selfcheck, mwoc-t04-worker-file-evidence, mwoc-t05-new-worker-exit, + diff-vitest.py); deploy_cmds=5 (build --install --allow-dirty, doctor --json, stop, start, doctor); reload_step=manual-per-window; repo_files_modified_by_this_worker=0

### 附：本次落盘的验证辅助脚本（供复核与复用）

- evidence/scripts/recovery-contract-corpus-stats.py：AC-010(a) 两档统计；实跑输出 evidence/recovery-contract-corpus-stats-20261014.txt（120 行，含 111 条 FLIP）。
- evidence/scripts/new-worker-exit-scan.py：AC-010(b) 独立判据扫描器（只读 run.json / task.md / report.md / trace.log）。本次自检式实跑（--root .agenticdoc --key mw-worker-output-contract --since 2000-01-01T00:00:00）：11 个本 key worker 中 9 个 done/exit=0、2 个仍 running，coverage_ok=false（本 key 全为 research，缺 review/coding）—— 正说明 AC-010(b) 必须新派三类 worker，不能用本 key 已有产物顶替。
- workers/woc-dr6-verification-matrix/diff-vitest.py：§2.2 的按用例名差分脚本；自比对实跑 NEW FAILURES = 0 / STILL FAILING = 5（5 即 §2.1 的既存红集合）。
