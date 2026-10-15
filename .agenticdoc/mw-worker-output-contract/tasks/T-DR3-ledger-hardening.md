# T-DR3: 变更账本抽取器加固设计（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「文件驱动的去中心化协调」「Worker 之间不直接通信」）。
- 本 key 的 spec（**已锁定**）：`.agenticdoc/mw-worker-output-contract/spec.md` —— §1.5 P4、§1.6 S5、§3 **AC-008 / AC-017**、§4 R9。
- 已确证的现状（**设计前提**）：抽取器唯一实现 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:1554`（41 个 pattern 标签）；伪行最小复现 **13 字符**；机制 = PowerShell here-string `@'…'@` 打乱引号配对 + `->` 被当重定向 + 非 `verbatim` 目标仍被 `:2383`–`:2385` 无条件记账；**遗漏分支** `[System.IO.File]::WriteAllText/AppendAllText`（RQ-1 的 122 条 bash 里 24 条）；**误拦**实例：here-string 正文里的 `--glob` 伪目标导致 `[WRITE_SCOPE_SUMMARY] allow=0 deny=3`；`unjudgeable` 现为「零事件」派生布尔；消费者 6 处全在 TS，Python 不消费；形状校验不能单独用（正文里 382/1720 行含反斜杠盘符路径）。
- spec 阶段研究证据（**必读**）：`evidence/research/spec-rq3-ledger-20261014.md`（41 标签全枚举、最小复现输入、消费者清单、12 个 vitest 文件）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`。

## 要求

1. **正信号定义**：什么样的事件才配写 `[WRITE_FILE]`（必须来自「写动词 + 已解析目标」）；给出判定伪码，并说明与「正文片段」的区别如何在实现上保证（数据流，而不是再补正则）。
2. **标签表的处置**：41 个标签哪些保留、哪些合并、哪些删除；`.NET API`（`WriteAllText`/`AppendAllText`/`Set-Content`/`Out-File`/`New-Item`）如何纳入；给出「新增/修改」清单。
3. **非 `verbatim` 目标的策略**：降级为 `unjudgeable` 事件 vs 忽略 vs 记账；给出 `change-ledger.ts:111`/`:123` 侧的兼容设计（新事件类型还是新字段）。
4. **`unjudgeable` 语义改造**：从「零事件」改为「**有效**事件为零」的精确判定；对下游 6 个消费者（`parseWriteFileEvents → diffLedger → readTerminalGaps → writeOutput/settle → PM readTerminalDetail`）逐个说明行为变化。
5. **误拦面（AC-005b 守卫）**：抽取器与守卫共用候选集的耦合点；如何做到「派生写入不被拦、越界写入仍被拦」；给出判据。
6. **AC-008 / AC-017 的测试形态**：AC-017 四段判据（最小复现产 0 行 / .NET API 各 1 行 / `allow=3 deny=0` / `unjudgeable` 由有效事件派生）各自的用例文件 + 夹具 + 断言；12 个既有 vitest 用例的影响面与不回归证明方式。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq3-ledger-hardening-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写同内容 `report.md`。

## 交付格式

- `## 0. 结论与标签处置表` → `## 1…N` 逐问 → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；命令 + 输出；禁止推测补齐。
- 末尾一行 `[VERIFY] …`；写出方法边界与未覆盖面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
