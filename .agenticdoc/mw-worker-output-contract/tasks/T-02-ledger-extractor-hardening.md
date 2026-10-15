# T-02 · 变更账本抽取器加固：先剥数据区再词法 + 正信号目标 + `[WRITE_UNRESOLVED]`（W3）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「工具白名单按任务类型」）——`trace.log` 的变更账本是 Worker↔PM 之间唯一的「写了什么」事实源；账本失真等于协调失真。
- 现状（**已确证，不要重复发现**）：唯一实现 = `worker/worker-mode.ts` 的 `extractBashWriteCandidates`（`worker/worker-mode.ts:1554`，41 个 pattern 标签；行号会漂移，**以符号为准**）。
  - **伪行最小复现 13 字符**；机制 = PowerShell here-string 打乱引号配对 + `->` 误当重定向 + 非 `verbatim` 目标被无条件记账（`worker/worker-mode.ts:2383-2385`）。
  - **遗漏分支**：`[System.IO.File]::WriteAllText` / `::AppendAllText`（RQ-1 的 122 条 bash 里 24 条）。
  - RQ-1 的 0 行是「遗漏分支 + 3 条真写被 here-string 正文里的 `--glob` 伪目标**误拦**」双重原因。
  - **危害面已升级**：4 个独立 worker（RQ-2 / RQ-3 / DR2 / DR3）在各自运行期都踩到同一误拦/误记（heredoc、`node -e`、脚本里的 `>`/`->`、`--glob`）⇒ 不只是「账本失真」，而是**误拦合法只读命令**。
  - `unjudgeable` 只是「零事件」派生布尔（一条乱码事件即可绕开）。
- 设计落点（`design.md` §5，三条**数据流**约束，不是再打正则补丁）：
  1. **先剥数据区再词法**：PowerShell here-string `@'…'@` 与 heredoc 体在词法分析**之前**剥离 ⇒ 正文里的 `>` / `->` 不再成为算符。
  2. **目标只取自写动词的目标位**，并经 `verbatim` + 「单命令字面量值环境」解析；未解析的目标**不写** `[WRITE_FILE]`。
  3. **未解析落新事件** `[WRITE_UNRESOLVED]`；`unjudgeable` 由「**有效**事件数为零」派生。
  配套：41 个 label **全保留**（守卫 miss 面），新增 `net-file-api`（四形态，现产 0 候选）；`BashWriteCandidate` 形状与 `ok` 公式**不变**。消费者 6 处全在 TS（`parseWriteFileEvents → diffLedger → readTerminalGaps → writeOutput/settle → PM readTerminalDetail`）⇒ **不动 Python**。
- 风险 R9（**硬约束**）：**不能只靠形状校验**。全仓磁盘文件名含空格/`+`/中文的 = 0，但 `.agenticdoc` 正文里反斜杠盘符路径出现在 382/1,720 行 ⇒ 加固必须是「**正信号**（来自写动词的已解析目标）+ 形状校验」的组合。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（**仅**抽取器段 + 记账段）
- `packages/coding-agent/test/suite/mwoc-w3-ledger-extractor.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`worker/worker-mode.ts` 的**检查点段**（归 T-04）与 **settle 段**（归 T-05）**一律只读**——本卡只改抽取器与记账两段，改前先确认这两段行号/符号边界并在证据里声明；`shared/heartbeat.ts`、`worker/output-*.ts`、`pm/**`、`packages/multi-workers/**` 只读。**禁止 `npm run check`**；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **剥离阶段独立可测**：新增「数据区剥离」函数（here-string `@'…'@` / heredoc 体），在词法前调用；用 AC-017(a) 的 13 / 55 / 319 / 336 字符四形态断言产出 **0** 行 `[WRITE_FILE]`。
2. **目标只取写动词目标位**：经 `verbatim` + 单命令字面量值环境解析；未解析**不写** `[WRITE_FILE]`，落 `[WRITE_UNRESOLVED]`。
3. **`net-file-api` 新分支**：`[System.IO.File]::WriteAllText` 与 `::AppendAllText` 各调用一次产出**恰好 1** 行事件（AC-017(b)）。
4. **41 个 label 全保留**；`BashWriteCandidate` 形状与 `ok` 公式不变；`shared/change-ledger.ts` 只加不删导出。
5. **`unjudgeable` 改由「有效事件数为零」派生**（AC-017(d)）；**现有 12 个 vitest 用例名下的断言不得回归**（先跑基线，逐用例名单入证）。
6. **AC-008**：以 `wfg-rq2-enforcement` / `wfg-rq3-safety` 的真实命令文本作夹具 ⇒ 产出 **0** 条伪 `[WRITE_FILE]`；以 `wfg-rq1-write-face-sources` 的写入形态（python heredoc 写 `evidence/**`）⇒ 0 条伪路径且**至少 1** 条 `unjudgeable` 记录。
7. **AC-017(c)**：含 `--glob`/`->`/反引号的 here-string 正文不再把真写命令判 deny ⇒ 对应 `[WRITE_SCOPE_SUMMARY]` 由 `allow=0 deny=3` 变为 `allow=2 deny=0`（判据已校正：第 3 条 `Write-Output a <term> --glob x` 无写 API，修后产 0 候选，故不计数）。原始数据：`wfg-rq1` 的 `trace.log:266/352/357`（target 均为 `--glob`）与 `:384 [WRITE_SCOPE_SUMMARY] allow=0 deny=3 allow-unknown=0`。
8. **不动记账的对外契约**：`[WRITE_FILE]` 行语法、`parseWriteFileEvents` 可解析性、Python 不消费这一事实都不变（新增的 `[WRITE_UNRESOLVED]` 是新行型，需在证据里声明其与既有消费者的兼容性）。
9. 开工前若发现 `worker-mode.ts` 正被第三方编辑（尤其是检查点/settle 段），停下并在「残留与未验证」报告。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑命令 + 原始输出**：四形态最小复现的 0 行输出、`net-file-api` 各 1 行输出、AC-008 两组夹具的前后对照、`unjudgeable` 派生前后对照、既有 12 个用例名单 + 改动后结果、`allow=0 deny=3 → allow=2 deny=0` 的重放输出。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w3-ledger-extractor.test.ts
node ../../node_modules/vitest/dist/cli.js --run <既有 change-ledger / checkpoint 相关套件，逐文件参数>
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

（HEAD 基线：`change-ledger` + `checkpoint` **22/22 全绿**、`mwds-t03` 63/63、`ledger` 家族 105/106（1 条既存红）、`agent-team-loop` 196/197（`:6381` 他 key 锚点）。列名单报基线，不要修既存红。）

## 改动历史

- 2026-10-14 spec 阶段 RQ-3：41 个 label 枚举、13 字符伪行最小复现、遗漏分支 `[System.IO.File]::*`、消费者 6 处全在 TS、`unjudgeable` 现状、形状校验只能作辅助（382/1,720 行会被误判）。新增 AC-017（含 2026-10-14 设计阶段对 (c) 的校正）与 R9。
- design 阶段 DR3：给出「先剥数据区再词法」「目标只取写动词目标位」「`[WRITE_UNRESOLVED]` + 有效事件数派生」三条数据流约束。
