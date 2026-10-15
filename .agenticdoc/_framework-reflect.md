# 框架层反思台账（framework reflect backlog）

> 用途：记录**框架/工具层**的缺陷与摩擦（不是 agent 行为教训——那类进 `_pitfalls.md`，也不是业务缺陷——那类进各 key 的 `spec.md`）。每条都要给出可定位的证据坐标、当前手工兜底、以及**框架层**的修复建议，供后续专门的 key 批量修。
> 维护：PM 在收口/遇到摩擦时追加；条目只增不改（结论变化时新增条目并互相引用）。
> 派发目标：见文末「派发建议」。`_pitfalls.md` 里的 P-026/P-028/P-030 是本台账 FW-003/FW-004 的**行为侧兜底**，两者应互引。

## 目录

| ID | 一句话 | 影响面 | 来源 key | 状态 |
|---|---|---|---|---|
| FW-001 | 恢复契约按「整篇别名子串」判定，review/writeless 角色缺一段即 `needs-clarification`（上下文缺失就是这一类） | 所有 key 的 review/research 收口 | mw-worktree-junction-guard（`wjg-qg-evidence-closure`） | 未修 |
| FW-002 | review 角色的运行期写面忽略卡片指定的唯一产物路径，必须 PM 手工提升 | 所有 key 的 review 交付 | 同上 | 未修 |
| FW-003 | 崩溃检测器为「活着但还没写 output.md」的 worker 生成伪 `failed` 行，污染回读/重试判断 | 所有 key 的回读 | 同上（W-08 20 块、W-09 6 块） | 未修 |
| FW-004 | 派发卡信封的两道静默门槛只在派发时拒绝（type 专属项须在 `## ` 标题体内；seed 须含字面 `name.ext:NNN`） | 所有 key 的派发 | 同上（本 key 4 次拒发） | 未修 |
| FW-005 | 恢复契约段结构与「报告式」结构不一致，同一份审计要写两套结构，易顾此失彼 | 所有 key 的 review/research 报告 | 同上 | 未修 |
| FW-006 | review 审计默认只做「引用闭包」，**没有负空间/工件清单与危害面全量清单**能力，其单个 ✅ 易被当成全域保证 | 所有 key 的 review 审计结论 | mw-worktree-junction-guard（QG 报告 → 追加 W-12 才补上） | 未修 |
| FW-007 | 发散检查点判据对 writeless 角色失真（`writes=0` / `uniq_targets=0` 恒成立，`worker_file` 写入不计入），会把**已落盘完成**的审计报成 risk=mid | 所有 review/research 角色的阻塞判断 | mw-worktree-junction-guard（W-12 误报 risk=mid） | 未修 |
| FW-008 | 全量 `./test.sh` 无墙钟超时，本机 Windows 上可无输出挂死（实测 7h14m、子进程 22.9s CPU），且卡住时不指明是哪个文件 | 所有 key 的收口测试对照 | mw-worktree-junction-guard（收口期 PM 实跑） | 未修 |
| FW-009 | `[WRITE_FILE]` 变更账本对「壳层写入」既误报（把命令正文里的片段记成写过的文件）又漏报（真写了但 0 行） | 所有 key 的变更历史/证据强度判断（含 FW-007 建议的修法） | mw-write-face-guard（rq1 漏报 + rq2/rq3 误报） | 未修 → **已修（2026-10-15，T-11 标题锚定 + T-10 壳层事件表）** |

---

## FW-001 恢复契约用「整篇别名子串」判定段是否齐全 —— 上下文缺失即由此产生（2026-10-14，mw-worktree-junction-guard / `wjg-qg-evidence-closure`）

- **现象**：`wjg-qg-evidence-closure`（type: review）实质工作完整（AC-001..013 全 ✅、16/16 反假证据抽样相符、报告 23 KB 六段），却以 `status: needs-clarification`、`exit: 2` 收尾，回读文本为
  `recovery-incomplete: missing section(s): 上下文来源`。
  其 `output.md`（回读前 3,266 B）只有澄清模板四段：`## TL;DR` / `## Summary` / `## Questions` / `## Recovery Gaps` —— 它自己的 `## Recovery Gaps` 段就自述「缺失段：上下文来源」，所以那句正是它自报的原文。
- **机制**：恢复契约对**每个角色**要求 4 个基础段（review 另加 1 个），判定是 `containsAlias` 对**整篇文本（标题或正文）做子串匹配**、词汇上 fail-open、结论上 fail-closed：某一段的别名一个都没出现 ⇒ 记为 missing ⇒ `exitCode = 2`。
  - 本例里 4 个基础段中有 3 个是被**正文措辞**顺带命中的（`TL;DR`/`Summary` → 「结论」别名；正文提到「证据…」→ 「证据」；「遗留/未验证」类措辞 → 「残留与未验证」），review 额外段「未覆盖面声明」也被正文「未覆盖/缺口」命中 —— 唯一零命中的是 `上下文来源`（它整篇没写输入来源清单）。
- **证据坐标**：
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts`（`RECOVERY_SECTIONS = ["结论","证据","残留与未验证","上下文来源"]`、`RECOVERY_TYPE_SECTIONS.review = ["未覆盖面声明"]`、别名表 `RECOVERY_SECTION_ALIASES`（`上下文来源: ["上下文来源","来源清单","sources","references","参考","读取","阅读清单","context sources"]`）、`containsAlias` 用 `haystack.includes(alias)`）。
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2745`（`exitCode: 0 | 2 = evidence.delivered && gaps.ok ? 0 : 2`）、`worker-mode.ts:2776`（`questions: recovery-incomplete: ${gapsReason}`）。
  - 实例坐标：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-qg-evidence-closure/run.json`（`status: "needs-clarification"`, `exit: 2`）、`workers/wjg-qg-evidence-closure/output.md`（PM 补录前 3,266 B → 补录后 4,945 B，sha `7f168d9b…` → `1723f24e…`）。
- **影响**：
  1. 实质完成的审计被标成 needs-clarification，PM 必须手工 `PM-补录` 才能 ack（本 key 已做，属**形式性补录**，不是重做工作）。
  2. 判定偏粗：正文任意一句含「证据」就满足该段 ⇒ 真缺失也可能被别名误判为满足（fail-open 的反向风险）；反之，一段没有任何别名命中就会被记缺，即使内容其实在报告文件里。
  3. 判定发生在 **settle 之后**，worker 在收尾前无法自查，重做只能靠 PM 手工补录（或整轮重派，代价高）。
- **当前兜底**：PM-补录（byte-pure append + 前缀校验 + 新旧 sha 记录），并把「本角色 `output.md` 必带 `结论/证据/残留与未验证/上下文来源`(+型别额外项)」写进卡面「交付格式」。行为侧规则记 `_pitfalls.md` P-026 邻近条目。
- **框架层修复建议（按性价比排序）**：
  1. **判定改为按标题结构**：只认 `## <section>` 或 `## <别名>` 的**标题**文本（别名表可照用），不再对整篇正文做子串匹配 —— 保留「词汇 fail-open、结论 fail-closed」，但把「结构」也变成契约。
  2. **前置告知**：在 worker 启动提示 / `task.md` 注入「本角色 `output.md` 必带 N 段」清单，避免 settle 才发现。
  3. **settle 前自检**：writer 写 `output.md` 时若缺段，把结构化缺口返回给 agent 让其补段再 settle；或框架**自动插入** `## 上下文来源` 桩（框架本来就掌握 task.md 的输入清单与 worker 读过的文件，可自动填来源清单）。
  4. **澄清模板与契约对齐**：`## TL;DR / ## Summary / ## Questions / ## Recovery Gaps` 这套模板本身应含 `## 上下文来源`（或让模板与契约段名一一映射）。
  5. **验收方式**：把这 5 点写成框架侧的单测（缺段 ⇒ exit 2 且缺哪段报哪段；有标题但正文空 ⇒ 仍算缺；正文含别名但无标题 ⇒ 按新规则算缺），并保留历史语料回归。**更正（2026-10-14，`mw-worker-output-contract` RQ-1）**：本契约**没有** 99.4%/87.2% 的语料统计 —— 那两个数字属 `mw-dispatch-card-gate` 的**派发卡信封**（派发输入 341/343 不合规 = 99.4%，出处 `evidence/research/spec-dispatch-input-format-20261012.md:142`；卡片 301/345 不合规 = 87.2%，出处 `spec-card-format-corpus-20261012.md:281`）。本契约的实测为：整篇别名通过 145/433 = 33.5%、只认标题 35/433 = 8.1%（110 例 `alias_ok→heading_fail`），详见 `mw-worker-output-contract/evidence/research/spec-rq1-contract-corpus-20261014.md`。
- **第三次实例（2026-10-14，`wjg-w12-negative-space-audit`，比前两次更硬）**：这次卡面「交付格式」**和**派单描述都显式写出了 `output.md` 必带五段（`结论`/`证据`/`残留与未验证`/`上下文来源`/`未覆盖面声明`），结果仍是
  `recovery-incomplete: missing section(s): 结论, 证据, 残留与未验证, 上下文来源, 未覆盖面声明` —— **五段全缺**。
  该 `output.md`（914 B）里只有澄清模板四段（`## TL;DR` / `## Summary` / `## Questions` / `## Recovery Gaps`），实质 37 KB 内容全在报告文件里；且 TL;DR/Summary 正文带 `</think>` 残片（模型输出的残留标记被原样写入产物）。
  两点结论：① **卡面侧告知不足以修复本项** —— 即使 PM 把契约段写进卡面与派单描述，worker 仍不产出契约段，因此修法 2（前置告知）与 3（settle 前自检/自动插桩）中，**3 升级为必做**，且应在 writer 层而非提示层实现；② 附带发现：settle 时把带 `</think>` 残片的模型输出原样落盘且不报错，值得同一 key 一并处理（产物污染与"内容是否可信"判定）。
  第三次实例的 PM 兜底同前：byte-pure 补录五段（914 B → 约 5.9 KB），前缀校验 + 新旧 sha 记录。
- **第四次~第六次实例（2026-10-14，另一窗口的 `mw-write-face-guard`，单次 3/5 命中 —— 本项迄今最高频复现）**：该 key 一批 5 个 research worker 中 3 个以 `exit=2` / `status=needs-clarification` 收尾，回读原文 `recovery-incomplete: missing section(s): 残留与未验证, 上下文来源`（`wfg-rq2-enforcement`、`wfg-rq3-safety`）与仅缺 `上下文来源`（`wfg-rq-d2-runtime-guard`）。三者 `output.md` 均为澄清模板四段（2,658 / 3,745 / 2,907 B），而实质产物已落盘：`evidence/research/spec-write-face-enforcement-20261014.md` 32,053 B、`spec-write-face-safety-20261014.md` 44,793 B、`design-runtime-guard-20261014.md` 30,724 B。
  该窗口 PM 的兜底与本文档同源：三个任务目录的 `report.md` 现标题为 `# wfg-rq2-enforcement — report（PM 补录，收口 recovery-incomplete）`，正文补 `## 残留与未验证` / `## 上下文来源`（4,105 / 4,145 / 4,476 B）—— 即 **byte-pure 补录这一手工兜底被独立地重新发明了一遍**，说明它是当前事实标准而非本 key 特例。
  另注：三张卡的 `## 交付格式` 都写了产物与结构要求（`交付格式` 命中 ✓），**第五次确认「卡面侧告知不足以修复本项」**（前四次：QG / W-12 / W-15 / W-16 旁证）。
  证据坐标：`.agenticdoc/mw-write-face-guard/workers/<task>/run.json`（`status`/`exit`）、同目录 `output.md` 首行 `<!-- mw-run: <task>@<ts> status=needs-clarification -->`、同目录 `report.md`（补录后）、`evidence/research/*.md`（产物）。
- **第七次实例的成因链更正（2026-10-14，RQ-1 + PM 复核）**：本条的现象描述里「判定针对 `output.md`」**不准确**——受判文本是 `agentProductText()`（`worker/output-writer.ts:140-145`：**优先 `report.md`**，其次 `output.md`，再退回 settle summary），判定函数是 `checkRecovery`（`worker/output-sections.ts:87`，整篇 `toLowerCase()` + `includes`，标题不参与），调用点只有两处（`worker-mode.ts:2740` settle、`output-writer.ts:257-259` writer 默认），`exitCode` 在 `worker-mode.ts:2746`。这也解释了为什么「把契约段写进卡面/派单描述」无效：卡面从不决定受判文本，而 worker 的 `report.md`/`output.md` 都不含机械段。
  另：宽档判据的注释依据（`output-sections.ts:19-20` 引 99.4%/87.2%）系**跨契约误引**，见上一段的更正。

- **状态**：**已闭合（2026-10-15，`mw-worker-output-contract` T-11/T-05/T-13 落地）**。修法：① 判定改按**标题结构**（`h2Headings` + 围栏/引用块排除；别名表照用）；② 前置告知（S2 段清单注入：T-06 Python 侧 + T-13 TS 侧全角色含 coding）；③ settle 前自检（T-13 自检回合，已交付条件）；⑤ 框架侧单测（`mwoc-w2` 40 例、`mwoc-matrix-t07` 25 例、T-07 基线 558 例 NEW FAILURES=0）。AC-014 的「另一契约数字误引」已由 `output-sections.ts` 注释更正。

## FW-002 review 角色的运行期写面忽略卡片指定的唯一产物路径（2026-10-14，同 key）

- **现象**：卡片 `tasks/T-QG-evidence-closure.md` 指定唯一产物为 `.agenticdoc/mw-worktree-junction-guard/evidence/quality-gate-report-20261013.md`，但 worker 自述其运行期写面「只允许在本任务目录写 `progress.md | report.md | report-<slug>.md`」，于是全文写到 `workers/wjg-qg-evidence-closure/report-quality-gate-report-20261013.md`，并在报告头部写「产物路径偏差声明 …… 请 PM 将本文件原样提升/复制到 evidence 路径」。
- **机制修正（2026-10-14，`mw-write-face-guard` 5 个 worker 复核后）**：本条的表述「运行期写面忽略卡片路径」**不准确**。实测两处写面并不一致：
  - **壳层写面（宽）**：`worker-mode.ts:723` / `:1604` / `:1624` / `:2199` 明示默认写面 = `taskDir + <key>/evidence/**`（再由任务 `write_scope:` 头收窄）—— 即 `evidence/**` **是被允许的**；
  - **`worker_file`（窄）**：`worker-file-tool.ts:42` 的 `WORKER_FILE_NAME_RE` 只认 `progress.md | report.md | report-<slug>.md` 且强制落在任务目录（`:63` 失败即 `file name not allowed`）。
  而 **research/review 角色的工具面里没有 `write`**（`[TOOL_ERR] … write Tool write not found` 在 `wfg-rq-d1`、`wfg-rq2`、`wfg-rq3` 三个 worker 的 trace 里各出现一次）⇒ 想按卡片把产物写到 `evidence/**`，**唯一可用通道是壳层**（PowerShell here-string + python heredoc）。
  于是同一批同型卡片下行为分裂：`wfg-rq1/rq2/rq3/rq-d2` 用壳层直接写了 `evidence/research/*.md`（mtime 落在各自 run 窗口内），`wfg-rq-d1` 退回任务目录 `report.md`（41,612 B）并由 PM 原样提升（`evidence/research/design-glob-intersection-20261014.md` 同 41,612 B、同 sha `8E4B5A418D99512B`）。
  对本 key 的自我纠正：`tasks/T-W12` / `T-W15` 卡面写的「产物写本任务目录 `report-*.md`，PM 提升」**是照抄了 QG worker 的自述、把可用面写窄了**；对**有 `bash` 的角色**这句并无必要（应直接写「产物用 `write`/壳层写 `<key>/evidence/**`」），对**只有 `worker_file` 的角色**才是必需。
  精确修法（替代原文建议 ①）：让 `worker_file` 接受 `<key>/evidence/**` 下的路径（或给 writeless 角色一个「路径域受限的 write」），并在 `Tool write not found` 的错误文案里点出 `worker_file` 这一替代通道。
- **证据坐标**：`workers/wjg-qg-evidence-closure/report-quality-gate-report-20261013.md`（23,252 B，sha256 `271ACF9F94EEBE68…`）→ PM 提升为 `evidence/quality-gate-report-20261013.md`（同 sha、同字节数）。
- **影响**：每个 review/research key 都要人工搬运一次；「卡片要求路径 vs 框架允许路径」不一致会消耗 worker token 去解释，且产物在工件里出现两份路径（后续引用容易分歧）。
- **当前兜底**：卡面直接写「产物写本任务目录 `report-*.md`，PM 负责提升到 `<evidence 路径>`」——本 key 已按此写卡（`tasks/T-W12-negative-space-audit.md`）。
- **框架层修复建议**：① 派发时把卡片声明的产物路径并入写面白名单（至少允许 `.agenticdoc/<key>/evidence/**`）；② 或由框架在 settle 时把 `report-*.md` **自动提升**到卡片声明路径并记录 sha；③ 报错/回读里明确写出「本角色允许的写面」。
- **状态**：未修。

## FW-003 崩溃检测器为「活着但还没写 output.md」的 worker 生成伪 `failed` 行（2026-10-14，同 key 两次观测）

- **现象**：同一个 run 的回读里穿插多条 `(worker exited without writing output)`、`status=failed` 块，而 `run.json` 实际是 `status: done`。
  - W-08：单次 run 内 **20** 个伪块（另有 `(28s)` 头部）。
  - W-09：单次 run 内 **6** 个伪块，时间 `16:54:59 / 16:55:03 / 16:56:13 / 16:56:27 / 16:58:41 / 16:59:44`，而 `run_id = wjg-w09-tree-watch-doctor@2026-10-13T16:50:59.685Z`、`status: done`、58 tool calls。
  - 注意第一条伪块还带了 `缺失段：结论、证据、残留与未验证、上下文来源、改动清单`（即 settle 时机早于 `output.md` 落盘）。
- **影响**：按回读文本判断会误判失败并触发重试；重试会**丢掉已完成的 run**、并可能造成并发写。PM 必须先去读 `run.json` 才能分辨真假。
- **当前兜底**：`_pitfalls.md` P-028 —— 「同一 run 窗口内 ≥2 个 `failed/exited without writing output` 块 = 伪噪声，以 `run.json` 为准；不据此自动重试」。本 key W-08/W-09 均按此处理。
- **框架层修复建议**：① 仅在「进程已退出 **且** `output.md` 仍缺失（或 run 窗口已关闭）」时才落 `failed` 行，同窗口内的中间态不发通知；② 回读文本统一带 `status=` 前缀（现在只在 done 时带）；③ `run.json.status` 声明为唯一事实源，widget 与回读都以它为准。
- **边界条件（2026-10-14，`mw-write-face-guard` 反向对照）**：该 key 目录**全树 0 次** `exited without writing output`（5 个 worker 的 `worker.log` 与整目录递归计数均为 0），而本 key 同一形态曾出现 20 / 6 / 17 块。
  ⇒ 本项**不是普遍现象**，与「某 worker 必然产生伪块」无关，更像与**回读被渲染的时刻**相关（PM 侧回读窗口在 worker 仍运行时取快照）。修法建议 ① 的方向不变，但复现条件需要单独定位（何时取快照、是否只在 `status=running` 期间渲染）。
- **状态**：未修。

## FW-004 派发卡信封的两道静默门槛只在派发时拒绝（2026-10-14，同 key 4 次拒发）

- **现象**：
  1. `missing=[审计目标]`：review 型的专属项写在了 `## 上下文` 的散句里，而渲染只带 `## 上下文` / `## 要求` / `## 交付格式` + **带正文的额外 `## ` 标题** ⇒ 视为缺失。
  2. `missing=[seed:path:line]`：把路径与行号写成两个反引号片段（`` `foo.ts` … `:123` ``）⇒ seed 正则要求**同一 token** 的 `name.ext:NNN`，判为无种子。
  3. 同类：coding 型的 `写入允许面/写入禁止面/验收命令/改动历史` 若只在前言里提过、没进 `## ` 标题体，同样拒发。
- **证据坐标**：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1880-1930`（`renderCardSeedSections`：只取 `## 上下文` / `## 要求` / `## 交付格式` + 带正文的额外标题）；拒发文本 `dispatch refused: card '…' is not a complete dispatch envelope (missing=[…])`（本 key 两次）；`_pitfalls.md` P-026「派发卡两道静默门槛」。
- **影响**：写卡—派发往返成本；规则只存在于报错文本里，worker/PM 无法在本地自查，且拒发虽零副作用但消耗一轮。
- **当前兜底**：P-026 三条规则 + 本 key 卡面自查（每张卡都带 `## 写入允许面` / `## 写入禁止面` / `## 验收命令` / `## 改动历史`，且 seed 用字面 `path.ext:NNN`）。
- **框架层修复建议**：① 提供**离线校验**入口（如 `mw task lint <card>` 或派发 dry-run `--check`），零副作用列出 missing；② 报错文本附**最小可抄修法**（缺哪个 heading 就给一段标题块）；③ seed 判定放宽为「同段内 `path.ext` 与 `:NNN` 相邻出现」也可接受（当前必须同 token，人写卡极易踩）；④ 在 `task.md` 渲染结果里回显「框架实际看到的信封字段」，让 PM 一眼看出漏了什么。
- **状态**：未修。

## FW-005 恢复契约段结构 vs「报告式」结构两套并存（2026-10-14，同 key）

- **现象**：卡面「交付格式」要求报告含 `结论/证据/残留与未验证/上下文来源`(+`未覆盖面声明`)，而该 worker 的报告用了另一套更贴合审计的段名（`问题清单与核查结果 / 抽样复核机器证据 / 汇总 / 未通过问题行动计划 / 二次印证结论`）；结果报告满足了我的卡面要求，`output.md` 却不满足框架契约。
- **影响**：worker 要同时满足两套结构，容易顾此失彼（本次正是「报告满足了、`output.md` 没满足」）；也让人误判「它没按卡片交付」。
- **框架层修复建议**：① 明确分工并在 worker 提示里写清：**报告文件结构 = 卡片自由**，**`output.md` = 契约结构**；② 或允许 `output.md` 的某段写成「指向报告 + 输入清单」的一行，而判定只看标题存在性。
- **状态**：未修。

---

## FW-006 review 审计的方法面缺失：只做引用闭包，没有负空间/工件清单枚举（2026-10-14，同 key）

- **现象**：`wjg-qg-evidence-closure` 给出 13/13 ✅、16/16 反假证据抽样相符、0 ⚠️ / 0 ❌。但复核其**方法**可见：它的入口是「卡片给的文件清单 + 各证据文件自称的 `file:line`」，做的是**引用闭包**核对（坐标与内容是否相符），**不是**以仓库为入口的负空间枚举。它在 `design.md:295`（§6.1 动作 (3)）上抓到 F-02 等 5 项，靠的是「设计正文条款 × 代码」的启发式比对 —— 也就是说方法有效但**有边界**：卡片没列、证据没提、条款没写的东西，它不会去找。
  为了补这一块，收口期不得不**追加一轮独立审计**（W-12，卡 `tasks/T-W12-negative-space-audit.md`）：先按 AC/决策独立推导「该存在什么工件」，再与仓库求差集（该有而没有 / 有而无人引用），并做**危害面全量清单**（全仓所有能到达穿透式删除的路径，逐条三态：守住 / 明确不在覆盖面且有理由 / 未守住）。
- **证据坐标**：
  - 该 worker 的方法与其自述输入：`evidence/quality-gate-report-20261013.md` 的「输入清单」段与 `## 问题清单与核查结果`（坐标与内容一致性核对）。
  - 卡片 `tasks/T-QG-evidence-closure.md` 的「审计目标」1–5 条：闭合判定 / 反假证据抽样 / 反向对照完备性 / 决策-实现一致性 / 漏项扫描 —— **没有一条**要求工件清单差集或危害面全量枚举；「未覆盖面声明」只声明了**工具面**（不能执行命令），**没有**声明**方法边界**（引用闭包）。
  - 缺口存在的直接证据：本 key 在收口期追加了 W-12（同一 key、同一被审对象、方法正交的第二份审计）。
  - 能力并非不存在：review 角色工具面含 `find` / `ls` / `grep`，做差集的能力是有的 —— 缺的是「要求」与「默认动作」。
- **影响**：
  1. 单个 ✅ 会被 PM 与用户读成「全域保证」，而它实际只在**引用闭包范围**内成立 —— 这正是本次用户追问「能保证全吗」的直接原因。
  2. 真正的漏项（该有而没有的工件、没人提名的危害路径）只能靠事后追加一轮审计才发现，收口被推后一轮，且这份补审的成本没人预算。
  3. 报告里「未覆盖面声明」承载了「工具限制」的含义，但**不承载方法限制**，读者容易把两者混为一谈（以为「不能执行」是唯一缺口）。
- **当前兜底**：PM 在写 review 卡时**显式要求**方法面：① 先建先验工件清单、再读证据；② 差集两类（该有而没有 / 有而无人引用）；③ 危害面（或覆盖面）全量清单与该清单的三态；④ 禁止以证据自述为准；⑤ 报告与 `output.md` 必须声明**方法边界**。本 key 的 `tasks/T-W12-negative-space-audit.md` 即此形态，可作为模板。
- **框架层修复建议**：
  1. **review 型卡片的模板内置「方法」段**：把「引用闭包 / 负空间差集 / 危害面或覆盖面全量清单 / 反假抽样」列为可选项并要求逐项打勾，未做的项必须在报告里显式声明「未做」。
  2. **报告模板强制「方法边界声明」**：`## 未覆盖面声明` 必须分别写清**工具边界**（能不能执行命令）与**方法边界**（本次用的是哪种审计方法、没覆盖哪一类），两者不得混写。
  3. **把能力变成默认动作**：review worker 的默认流程里加一步「以仓库为入口的枚举」（例如 `git ls-files --untracked` 得到全量文件集，与 AC 推导出的必需工件集求差集），并把两个差集计数写进报告末行。
  4. **结论措辞约束**：要求 review 报告的 ✅ 必须带**限定语**（例：「在引用闭包范围内充分」），避免被下游当作全域保证；`achieved.md` / `_project_log.md` 引用该 ✅ 时保留限定语。
  5. **验收**：新建 review 卡若未声明方法与未覆盖面，框架在派发时提示（与 FW-004 的离线校验同一入口）。
- **状态**：未修。

---

## FW-007 检查点发散判据对 writeless 角色失真 —— 已完成的审计被判 risk=mid（2026-10-14，同 key，W-12）

- **现象**：`wjg-w12-negative-space-audit` 的检查点输出
  `[CHECKPOINT] elapsed=1800s reads=111 writes=0 uniq_targets=0 repeat_top=16 risk=mid`，触发「发散风险」提示（继续等待 / steer 收窄 / 终止分拆 / PM 直执）。
  而实际状态是**已完成**：该 worker 的唯一产物 `report-negative-space-audit-20261013.md`（37,149 B）在 `17:32:12` 落盘（trace 的 `[WRITE_FILE]` 行），`progress.md` 已写「## 完成记录（2026-10-14）」并列出 27 项先验清单、危害面 29 条、新发现 N-01..N-06。它当时只是在收尾（写 `output.md` 前的 settle 窗）。
- **机制**：① review/research 是 writeless 角色，写文件只能经 `worker_file` 工具，而该事件**不计入** `writes` 计数 ⇒ `writes=0`、`uniq_targets=0` **恒成立**，与是否落盘无关；② `reads` 高、`repeat_top` 高是**审计广度**的正常特征（同一大文件分段重读、跨文件对照），不是打转；③ 判据没有参考「最近一次 `[WRITE_FILE]` 距现在多久」与「产物是否已存在」。
- **证据坐标**：`workers/wjg-w12-negative-space-audit/trace.log`（`[CHECKPOINT]` 行 + 其前的 `[WRITE_FILE] …report-negative-space-audit-20261013.md`、`[WRITE_FILE] …progress.md`）、同目录 `progress.md`（「## 完成记录」）、`run.json`（`status: running` 至 settle）。
- **影响**：PM 若按机器判据**终止并分拆**，会丢掉一份已完成的 37 KB 审计（重派成本 + 结论可能不一致）；若 `steer 收窄`，则会打断收尾。这正是本 key 差点发生的事（本轮人工判断为「继续等待」）。
- **当前兜底**：与 P-028 同族 —— 判据冲突时先读 `progress.md` 的「完成记录」与 trace 的 `[WRITE_FILE]` 行，再决定；不因 `writes=0` 而重派/终止。
- **框架层修复建议**：① 对 writeless 角色改用「`[WRITE_FILE]` 事件或产物存在性」判定是否已落盘，`writes` 计数不参与；② 检查点输出附「最近 `[WRITE_FILE]` 时间 + 产物名」与「距上次落盘时长」，让 PM 一眼判断是否在收尾；③ risk 判据不要把 `uniq_targets`/`repeat_top` 单独当发散证据（审计类任务天然重复读）；④ 若维持现判据，至少把 `risk` 文案里注明「writeless 角色的 `writes=0` 可忽略」。
- **未复现 + 修法风险（2026-10-14，`mw-write-face-guard`）**：该 key 5 个 worker 的 trace **全部 0 条 `[CHECKPOINT]`**（run 时长 7~8 分钟量级，未到 30 分钟检查点），故本条未复现。
  但本轮拿到一条对本条**修法**的反证：建议 ① 「改用 `[WRITE_FILE]` 事件或产物存在性判定是否已落盘」所需的 `[WRITE_FILE]` 事件本身不可信 —— 见新增 FW-009（同一批 worker 里既误报又漏报）。采纳建议 ① 前必须先修 FW-009，否则会把「账本乱码」当成「已落盘」。
- **状态**：未修。

## FW-008 全量 `./test.sh` 没有墙钟超时：卡住时既不退出也不指明卡在哪（2026-10-14，mw-worktree-junction-guard 收口）

- **现象**：收口跑全量非 e2e 套件，**7h14m** 后才判明是挂死而非慢：wrapper 进程 CPU=0，其 bash 子进程 fork 的 `vitest --run`（包级全量、无文件参数）7 小时只烧 **22.9s CPU**，输出文件自启动后第 15 分钟起再无更新（末行只剩一段点进度与 `[VERIFY] VC-021` 行）。**没有任何超时、也没有任何提示是哪个测试文件卡住**；只能靠 PM 手工看 mtime + CPU 才能判定。
- **证据坐标**：`test.sh`（隔离 HOME/USERPROFILE/TMP/TEMP/XDG/GIT_CONFIG_*、`PI_NO_LOCAL_LLM=1`、临时根 `/tmp/pi-test.*` 带所有权检查的清理）+ `package.json` 的 `"test": "npm run test:scripts && npm run test --workspaces --if-present"`；本次输出样本 `$TEMP\wjg-testsh.out`（46,700 B，mtime 00:44:06）；卡住进程 `vitest.mjs --run`（PID 36124，启动 00:30:13，CPU 22.9s）。
- **当前手工兜底**：`_pitfalls.md` **P-032**（按包跑、套墙钟超时、按进程树终止、定向套件替代全量对照）。
- **框架层修复建议**：① `test.sh` 给每个 workspace 的 vitest 调用套墙钟超时（git-bash `timeout`／PowerShell job + `Wait-Process -Timeout`），超时即非零退出并打印最后一条 reporter 行；② 用 `--reporter=verbose`（或在套件级打心跳行）让"最后启动的文件"可读，避免只知道卡在某包；③ 支持 `./test.sh --packages <pkg>` / `--files <list>` 的定向模式，使收口对照不必裸跑全量；④ 超时时把子进程树一起终止（本次需手工 wrapper→bash→vitest 三层）。
- **状态**：未修。

---

---

## FW-009 `[WRITE_FILE]` 变更账本对壳层写入既误报又漏报（2026-10-14，mw-write-face-guard 5 个 worker 复核）

- **现象**：同一批只有 `bash` 的 writeless research worker，其 `trace.log` 的变更行两个方向同时失真：
  - **误报**：`wfg-rq2-enforcement` 连落两行 `[WRITE_FILE]`，其路径值分别是「反引号 + `:1175`」与「反引号 + `:1184`」（原文形如 `path=` 紧跟一个反引号再跟 `:1175`）；`wfg-rq3-safety` 连落两行 `, .agenticdoc/_aut + opilot)`。这些值不是路径，而是这两条命令**正文里的片段**（它们的命令是多行 PowerShell here-string：`$py = @' … '@` 后再 `$code | python -`），紧邻其上的 `[WRITE_SCOPE] … blocked=false rule=allow-unknown detail=target-not-statically-determinable pattern=redirect target=`（target 为空）表明抽取器已判「不可静态确定」，却仍然把这些碎片落成了「写过的文件」。
  - **漏报**：`wfg-rq1-write-face-sources`（trace 工具面 `bash, ls, read`，无 `write`）**0 条 `[WRITE_FILE]`**，但它实际落盘了 `evidence/research/spec-write-face-sources-20261014.md`（50,544 B，mtime 01:22:21 落在其 run 窗口内）。零行 ⇒ 账本认为它什么都没写。
- **机制**：`worker-mode.ts:2368-2388` 在 `tool_execution_end` 时把 `pendingWriteTargets`（`write`/`edit` 的路径参数）与 `pendingBashWrites`（壳层抽取器给出的目标）逐条 `appendWriteFileEvent(tracePath, repoRelativePath(t))`（`shared/change-ledger.ts:116,123`，行格式 `[WRITE_FILE] path=<p>`，读取正则 `change-ledger.ts:135` 为锚定式，本身没错）。两个来源都没有**形状校验**（不排除 `:1175` 这类坐标、含空格/`+` 的碎片），也没有把「经解释器（python/node heredoc）写入」识别为不可判定（框架在别处已有 `unjudgeable` 概念，见 `worker-mode.ts:2758`）。
- **影响**：
  1. **FW-007 的建议 ① 不能直接采纳**：以 `[WRITE_FILE]` 判定「是否已落盘」会把乱码当落地、把真落地当零写入。
  2. **证据强度被高估**：PM 侧「trace 有 `[WRITE_FILE]` 行 ⇒ 确实写盘」这类推理对 writeless 角色不成立（本 key W-15 的「证据强度不足」项由此得到一个具体实例）。
  3. 变更历史（`改动历史` / change ledger）恰好在**没有 `write` 工具的角色类**上最不可信 —— 而这类角色正是审计/调研产物最多的一类。
- **当前兜底**：以**产物文件存在性 + mtime 落在 run 窗口内**为准，不以 `[WRITE_FILE]` 行数为准（本轮即按此复核 `mw-write-face-guard` 的证据文件归属）。
- **框架层修复建议**：① 壳层抽取器的目标只在**重定向目标位**取值，并对候选做形状校验（须形如路径：非 `:`/数字开头、无空格与 `+`、可被 `path.resolve` 且非空）；② 经 `python -`/`node -e`/heredoc 之类「解释器写入」的命令，落一条显式的 `unjudgeable` 事件（而非静默丢弃或乱猜），使账本能区分「没写」与「看不清」；③ `write` 工具不在该角色工具面时，`[TOOL_ERR] … Tool write not found` 的文案应点出可用替代通道（`worker_file` 或壳层），减少无效往返（本批 3 个 worker 各有 1 次这种无效调用）。
- **状态**：未修。

---
## 派发建议（供后续框架层 key 领取）

| 条目 | 建议归属 key | 理由 |
|---|---|---|
| FW-001、FW-002、FW-005 | 新 key `mw-worker-recovery-contract`（spec 级：worker 输出契约与产物路径） | 三者都在 `worker/output-sections.ts` / `worker-mode.ts` / `pm/ui-bridge.ts` 同一写入面，且都需要历史语料回归 |
| FW-006 | 新 key `mw-worker-recovery-contract`（若拆分则独立为 `mw-review-audit-method`） | 与 FW-001/FW-002/FW-005 同属「worker 角色契约」写入面（`worker/output-sections.ts`、`worker-mode.ts`、`pm/ui-bridge.ts` 的卡面模板），且都需要历史语料回归 |
| FW-003、FW-004 | 既有 key `mw-dispatch-reliability`（本仓已有该 key 目录，index 侧 idle） | 回读真伪判定与派发卡校验都属于 dispatch 可靠性面 |
| FW-008 | 新 key `mw-test-runner-hygiene`（或并入仓库测试入口面） | `test.sh` / `package.json` 测试入口的超时、卡点定位与定向模式，与 dispatch 逻辑无关 |
| FW-009 | 并入 `mw-write-face-guard` 之后的「写入面」key（与 FW-002 同一写入面：`worker-file-tool.ts` / `worker-mode.ts` 壳层抽取器 / `change-ledger.ts`） | 三者共享同一写面与账本代码，且 FW-007 的修法依赖本条先修 |

> 本文件由 `mw-worktree-junction-guard` 收口期 PM 建立（2026-10-14）。`_pitfalls.md` P-026/P-028/P-030 是本台账 FW-003/FW-004 的行为侧兜底。
> 2026-10-14 复核批（`mw-write-face-guard` 5 个 worker，另一窗口在同一时段独立运行）：FW-001 新增第 4~6 次实例（单批 3/5 命中，迄今最高频）、FW-002 机制修正、FW-003/FW-007 记为未复现（含边界条件）、新增 **FW-009**。复核所用的旁证均为只读（`run.json` / `output.md` / `report.md` / `trace.log` / 产物文件字节与 mtime），未改动该 key 任何文件。
