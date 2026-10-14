# Pitfalls — 坑点台账

> 项目级记忆文档之一（pm-mind Hook 2：spec 生成前必读，§5「需规避坑点」取源；同一坑点跨 key 复现时升级 [高危]）。

## P-001 PowerShell 文本管道损坏无 BOM UTF-8 文件（2026-09-11，mw-dual-workspace）

- 现象：`.agenticdoc/mw-dual-workspace/spec.md` 全文中文变 mojibake；`_index.parallel` 7 处 `—` 变 `鈥?`。
- 根因：Windows PowerShell 5.1 的 `Get-Content -Raw` 对无 BOM 的 UTF-8 文件按系统 ANSI 代码页（cp936/GBK）解码，`[System.IO.File]::WriteAllText` 再按 UTF-8 回写——双重编码；GBK 解码遇无效序列按 best-fit 替换为 `?`，部分字节不可逆丢失（`—` 的第三字节 0x94 丢失后无法机械反解）。
- 硬规则（规避）：
  1. 对 `.agenticdoc/` 及一切 UTF-8 文本的程序化改写：一律用 edit 工具，或 Python 显式 `encoding="utf-8"`（字节级 `read_bytes`/`write_bytes` 最稳）。
  2. 禁止 PS `Get-Content`/`Set-Content`/`WriteAllText` 对无 BOM UTF-8 文件做读-改-写往返；控制台输出的乱码与文件真实损坏不可区分，须用 read 工具（正确解码）判定。
  3. 修复手段备忘：确定性 mojibake（如 `—`→`鈥?`）可字节级反向替换；全文损坏从完整修改历史重建（mw-dual-workspace spec.md 即此法恢复，0 内容损失）。
- 关联：mw-dual-workspace spec 锁定时间戳插入时触发（2026-09-11 15:01），同轮已修复并验证（read 工具抽查 + mojibake 检索 0 命中 + audit PASS）。

## P-002 会话内修改跨窗口共享配置文件（2026-09-15，mw-protected-config-guard 前置事故）
- 现象：所有 pi 窗口报 `Error: Provider is not configured: timi`，多个窗口死机；`~/.pi/agent/auth.json` 被运行中的会话清掉（只剩 timi 条目，其余凭据一并丢失）。
- 根因：auth.json 是所有窗口共享的活跃凭据存储（AuthStorage 按文件 revision 热重载）——任何会话内 write/edit/bash 直接改它，等于在其它窗口脚下抽掉凭据；会话工具层此前无任何防护。
- 硬规则（规避）：
  1. 运行期间绝不在会话内修改 `~/.pi/agent/` 下的 auth.json / models.json / settings.json / oauth.json（及 agentDir 本身）。agent-team-loop 扩展已在 tool_call 层硬拦截（`shared/protected-config.ts`，PM/Worker/交互三模式全覆盖）；mw 框架 Python 侧同规则（`mw_common.assert_not_protected_agent_config`）。
  2. 需要改凭据：关闭 pi 窗口后在普通终端编辑，或用 `pi /login`（core 流程，不在拦截范围）。
  3. 读不受限；worker 模式被拦截时向任务 trace.log 落 `[PROTECTED_CONFIG]` 行（PM watch 实时可见）。
- 关联：2026-09-15 事故（全窗口凭据丢失，多窗口死机）；guard 落地与验证见 mw-protected-config-guard/mini-spec.md。

## P-003 `open(p, "w")` 先截断后求值——写/改文件静默清零（2026-09-21，PM 自身缺陷登记 #50）

- 现象：PM 用 `io.open(p, "w")` 改脚本时，内层表达式（替换/序列化）抛错 → 文件已被截断成 0 B；而空 .py 文件 `py_compile` 仍通过 ⇒ 复验一度「静默成功」。
- 根因：Python `open(path, "w")` 在 open 时立即截断文件，而 `f.write(expr)` 的实参在截断之后才求值；表达式抛异常时文件已是 0 B。空文件是合法空模块，只看 `py_compile`/退出码的复验无法发现内容丢失（假阳性）。
- 硬规则（规避）：
  1. 程序化改写一律「先算后写」：把最终内容完整算进变量，再 `pathlib.Path.write_text(content, encoding="utf-8")` —— 实参先求值再开文件，异常时原文件不动。框架生产代码已全部此风格（advance_phase.py / update_index.py / conductor.py 等，2026-09-21 审计确认）。
  2. 需要防半写/并发读时用「临时文件 + `os.replace` 原子改名」（`mw_common._write_workers_file`、mw.py `_atomic_write_yml` 即此法；autopilot/dispatch.py 队列写入已于 2026-09-21 对齐，序列化生成器不再在截断后求值）。
  3. ad-hoc 一次性脚本同样遵守；确实要原地改且无版本控制兑底时，先 `shutil.copy2` 备份。
  4. 复验禁止只看 `py_compile` / 退出码：必须断言文件非空 + 关键内容锚点（grep 关键行）。
- 关联：PM 自身缺陷登记 #47~#52（2026-09-21，另一窗口引述；登记原文不在本仓）；#50 为本条来源，涉事脚本已由当事 PM 重写。

## P-004 POSIX 式词法分析在 Windows 路径上丢反斜杠——路径检查静默漏拦（2026-09-21，mw-implementation-gate T3）

- 现象：门禁 bash 词法器把 `echo x > H:\repo\packages\x\mw.py`（Windows 主平台主拼写形态，引号外/双引号内均同）词法化为 `H:repopackagesx.mw.py`——全部反斜杠被当作 POSIX 转义丢弃 → 路径判定不命中 → **不拦截**。单引号与正斜杠拼写正常，唯反斜杠形态被漏。探针确认后才改代码（先证后修）。
- 根因：POSIX shell 语义里反斜杠是转义符，但 Windows PowerShell/cmd 的路径分隔符也是反斜杠——对两者共享的命令文本做「POSIX 转义处理」会把路径打散。真实 POSIX 规则其实是：引号外反斜杠只转义元字符（引号/空白/`;&|<>()`/`$`/反引号），双引号内仅转义 `` $ ` " \ `` 换行，其余一律字面保留（`echo a\b` 打出 `a\b`）。
- 硬规则（规避）：
  1. 任何「解析命令文本提取路径/目标」的检查器：反斜杠按真实 POSIX 转义集处理（仅元字符），Windows 反斜杠路径自然字面保留；禁止笼统「反斜杠 = 转义下一个字符」。
  2. 必拿三种拼写形态做回归：无引号反斜杠、双引号反斜杠、正斜杠（单引号另测）；本仓先例：`implementation-gate.ts` 的 `BACKSLASH_ESCAPES_UNQUOTED` / `BACKSLASH_ESCAPES_DOUBLE_QUOTED` 两常量 + 13 必中/10 必避回归探针。
  3. 检查器缺陷往往在「漏拦侧」静默：写测试时必须含正反例双向（漏拦例 + 误拦例），只测拦截例会全绿而漏洞仍在。
- 关联：mw-implementation-gate T3（worker 发现并修复，`parseBashSegments` 最小改 + 修复回归探针用后删）；protected-config 词法器同型逻辑但未受影响（11/11 回归），若后续发现同类形态需同步检查。

## P-005 跨语言契约字段"只有读者没有写者"——审计与单测全绿，生产永不触发（2026-09-22，mw-rag-integration T-10/T-14）
- 现象：task.md 的 `phase:` 头被两侧**解析**（`pm/task-dispatcher.ts`、`mw.py` 的 `mw rag audit`），却**没有任何写入方**（TS 的 `dispatch_worker` 只写 `type:`/`model:`，Python 的 `render_task_md` 只写 `type:`/`model:`/`origin:`/`loop:`/`attempt:`/`read_scope`/`deny_globs`）。后果：`target.yml` 的 `phases.<X>.require` 在生产中永不触发，`required = role.require OR phase.require` 的阶段半边是空壳——而单元测试因为**手写 fixture 里的 `phase:` 行**依然全绿（AC-015 / VC-020 假通过）。
- 根因：契约字段的读侧先落地并被测试覆盖，写侧被默认为"另有人做"；fixture 手写该字段，恰好绕过了"生产路径是否真的会产生它"这一唯一能暴露缺口的断言。
- 硬规则（规避）：
  1. 引入或依赖任何新字段时三问：**谁写它、谁读它、不写时会发生什么**；答不出就不算接完。
  2. 写侧接线优先做成"**未知/缺省 → 零字节变化**"（mw-rag-integration 的 `phase=""` 与不传输出逐字节相同），这样新增字段不会让既有产物与既有测试抖动，也让缺口暴露在明确的开关上。
  3. 端到端断言里至少要有一条**由真实生产路径产生该字段**的用例（不是手写 fixture），否则测试证明的是"解析器能读"，不是"字段会存在"。
- 关联：mw-rag-integration T-10（audit 侧实现并主动上报"`phase:` 无既有约定"）→ T-14（两侧写入 + worker 读取 + 末态发射）；同轮还修掉"VC-014 的 TS 面无人认领"（T-09 备好发射函数但无调用方）——同一类缺口。

## P-006 绿灯用例的日志通道可能是关闭的——证据行"看起来跑了但看不见"（2026-09-22，mw-rag-integration T-02/T-12）
- 现象：worker 在绿灯用例里用 `console.log("[VERIFY] ...")` 输出验证证据，命令退出码 0、用例全过，但**证据行在输出里根本不存在**（vitest 配置 `silent: "passed-only"` 会吞掉通过用例的控制台日志）——验证者若只信退出码，就会把"没有证据"当成"验证通过"。
- 根因：测试框架的默认静默策略 + 证据通道（stdout）与断言通道（退出码）分离；失败用例才会打印日志，而这类证据恰恰只在成功时才需要被看到。
- 硬规则（规避）：
  1. 本仓 TS 证据行一律 `process.stdout.write("[VERIFY] ...\n")`；Python 侧 `print` 需 `pytest -q -s` 才可见。
  2. 任务模板里写死"证据行必须出现在必跑命令的原始输出中"，并把它列进完成判据（mw-rag-integration 已写进 T-05/T-11 的任务文件）。
  3. 任何"我给证据了"的汇报，复验时必须**在原始输出里 grep 到该行**，而不是只看退出码或 worker 的转述。
- 关联：mw-rag-integration T-02 与 T-12 各踩一次（后者由 PM 直修 `console.log` → `process.stdout.write`）。

## P-007 review 角色的唯一交付通道是"最后一条消息"——长报告 = 单点故障（2026-09-22，mw-rag-integration 质检复核）
- 现象：`type=review` 的 worker（allowlist `read/find/grep/ls`，**无 write**）读完 39 个文件 + 11 次 grep 后，在输出最终长报告时 provider 流中断（`worker.log`：`done exit=0` + `stream closed before response.completed`）。队列把它标成 `failed`，而 `output.md` 只剩 272 B 框架模板（"Task completed. Tools used: ..."）——**分析全部白做，且看起来像"跑过了"**。
- 根因：审查类任务没有落盘手段，整份结论必须挤在**一条最终消息**里；消息越长，流中断的概率越高，且中断后**没有任何中间产物**可抢救。对比 coding worker：可以边查边 `write`，中断也只丢最后一段。
- 硬规则（规避）：
  1. 派 review/research 任务时必须在提示里给**硬输出预算**（如 ≤ 90 行）并规定**先结论与 findings、后表格**（截断时损失最小）。
  2. 审查面大时**拆成多个小 review 任务**（一个任务一个结论集），不要指望一次输出一份完整报告。
  3. 看到 review worker `failed` + `output.md` 是模板时，先看 `worker.log` 是否 `done exit=0` + `stream closed`：**任务其实做完了，只是结论没落地**，重派时要缩小输出面而不是重跑一遍。
  4. 若要落地长报告，改用 `coding` 任务类型（有 write）并明确"只写审查报告、不改被审代码"。
- 实测口径（2026-09-22，本仓 review 型 worker）：**12 次 review 任务里 8 次没交出结论**（4 次 `stream closed before response.completed` + 3 次无内容即 settle + 1 次模型侧空转），同一时段 coding 型 worker 14/14 正常交付。**缩小最终消息（≤80 行）也不能消除**该失败（`mw-rag-qg-review-b` 仍中断）—— 根因是「无落盘通道」而非「输出太长」。
- 采用口径：审查任务改派 **coding 类型 + 只允许写一份报告文件**（骨架先落盘、分节 `edit` 填充），保留审查独立性与对抗性（不同 worker、可跑定向测试做反例试验），同时让结论有落盘通道。review 类型只用于「结论很短、丢失可接受」的场景。
- 关联：mw-rag-integration（T-11 也是同一类失败的下游：重型验证 + 长报告挤在一个任务里，22 分钟后流空转）；重派拆分为 `mw-rag-qg-review-a`（A+B，≤90 行）/`mw-rag-qg-review-b`（C+D，≤80 行）后按此规则执行。

## P-008 删掉函数后，文档里的流程图/结构图会静默过期——mermaid 门禁只查语法不查语义（2026-09-22，mw-rag-integration-fix T-19/T-20）

- 现象：T-19 把 `resolveForRole`/`resolveForPhase` 删除、收敛成 `resolveDefaults`，源码与测试都干净
  （`rg` 零命中、全套件绿、`npm run check` exit 0），但 `design.md` §2 的 mermaid 流程图里仍然写着
  `role 解析 resolveForRole` / `phase 解析 resolveForPhase`——**图在描述一份已经不存在的实现**。
  `check_mermaid.py` 照旧 `PASS: 0 error(s)`，因为节点文本只是字符串，语法没坏。
- 为什么危险：结构图/流程图是后来者理解实现的第一入口（也是复核报告 A 节的取证对象）。语法门禁通过
  会让人误以为文档同步了；实际上语义漂移**没有任何守卫**，只能靠人 grep。
- 规避：
  1. 删除/重命名导出函数时，除源码与调用点外，把 **docs/design/plan 里的符号名**也纳入 grep 范围
     （`rg -n "<symbol>" .agenticdoc packages/*/README.md packages/coding-agent/docs/`），零命中才算删干净。
  2. 结构图里的节点文本尽量写**职责**（"声明值：role > phase > default_server"）而不是**函数名**；
     函数名适合放正文的 `file:line`，流程图写职责才不随重构腐烂。
  3. 写表行追加注记时不要手改字符串工具：本次 PM 用 python 追加 D-107 注记时吞掉了行尾换行，
     导致该决策行与下一行 `| D-108 | ...` 粘连成一个 6 格行、表格渲染错乱。追加表格行的正确做法是
     **在行尾 `|` 之前插入**，并在写回后断言 `l.count("|") == 表头列数 + 1`。
- 关联：mw-rag-integration-fix design D-107/D-109；同源教训见 P-005（"只有读者没有写者"）——
  两者都是"静态检查全绿但语义已错"的家族。

## P-009 失败只记一行自由文本、没有预算也没有门禁 = 无界空转（2026-09-22，mw-autopilot-stall-feedback）

- 现象：E2Feature 的 conductor 在 `feature-params-service` 上每 4s 调一次 `advance_phase.py` 并失败，
  **2242 次 / 2h35m** 全程只往 `timeline.jsonl` 写两行（`advance ... exit=1` + `config "advance ... failed: <错误文本>"`），
  既无连续失败计数、无退避、无门禁、无状态上报。同一日更早还有 design→plan **3891 次 / 4h25m**
  与 spec→design 14 次。整条 Stage 1 因为一个 key 的依赖阻塞静默停摆（心跳正常，看起来"在跑"）。
- 根因：重试路径只把"失败"当成日志事件，**没有把它当成一个需要收敛的状态**；且错误文本是自然语言字段，
  没有分类，人/面板无法机械判定"这是接口漂移还是门禁未过"。
- 硬规则（规避）：
  1. 任何周期性重试回路必须有**有界的失败判据**（连续同 `(key, edge)` 失败数 ≥ 阀值）→ 升级（门禁 + 冻结），并在单测里锁定"达阀值后不再重试"。
  2. 失败事件必须带**机读分类**（本次：`interface-drift` / `gate-blocked` / `timeout-env` / `other`），人类可读原文另存一个事件，不要二者合一。
  3. 门禁问句里承诺的处置必须**都实现**：`stalled` 门禁写了"人工介入后重试"，但代码只消费了 `reject`（→ closed-legacy），`approve` 是 no-op——问句在骗人，人工批了也不会恢复。
  4. worker 崩溃≠裁决失败：`output.md` 缺失时不要推断为 `below`（本次 6 秒 403 被当成"L3 below 2 rounds"，
     还因此派了一个对着空报告做修复的 repair worker）。
- 关联：E2Feature 现场 `feature-params-service`（pm-state.md Phase 行被 worker 写成 `EXECUTE（括注）`
  导致 `advance_phase.py` 解析失败）；框架侧接口漂移另见 mw-autopilot-advance-root（`d106bcfb2`）。

## P-010 用 Python 文本模式给源码打补丁会整体翻转换行（Windows LF→CRLF），biome 随即想重排整文件（2026-09-23，mw-rag-window-parity）

- 现象：`pathlib.Path(p).read_text()` + `write_text()` 改一行后，`npx biome check <file>` 报
  「Formatter would have printed the following content」并打印**整个文件**的 diff（exit 1），看起来像格式全乱。
- 根因：`read_text` 默认 universal newlines（`\r\n`→`\n`），`write_text` 默认 `newline=None` 在 Windows 上把 `\n` 写回 `\r\n`；
  仓库标准是 LF，于是整文件换行被翻，biome 认为每一行都要改（未被 `--write` 时就是报错）。
- 规避（硬约束）：
  1. 用脚本打补丁时一律 `write_text(text, encoding="utf-8", newline="\n")`（读取用 `read_text(encoding="utf-8")` 无妨，写回必须显式 `newline`）；
  2. 或直接 `read_bytes().replace(b"\r\n", b"\n")` 复原后再验；补丁后**立刻**跑一次 `git diff --stat` 或字节级 `CRLF` 计数自检；
  3. 判断依据：`<file> CRLF=<n> LF-only=<m>`，源码仓库应 `CRLF=0`（`.md` 记忆文档可能是 CRLF，追加时按主导换行写）。
- 关联：本坑与 P-005/P-006 同类——「只改一处」的操作却产生了全局 diff，评审与后续 worker 都会误判改动面。

## P-011 claim 身份双写分叉——按 pm-state 判活会误判抢占（2026-09-23，mw-worker-visibility-gate）

- 现象：同一个 key 的 claim 身份在两处出现且值不同：`_index.parallel` 的 Claim 列是 `WENBOZHOU-PC3:<pi 窗口 pid>`，`<key>/pm-state.md` 的 `- Claim-Id:` 却是 `WENBOZHOU-PC3:<python pid>`；`audit_phase` 不报 drift，看上去像无事。
- 根因：两个写入者各自取 pid——框架的 `update_index.py claim` 写 `now_claim_id()`（短命 python 进程的 `host:os.getpid()`）到两处，而 `switch_key` 重写索引行时用 `windowClaimId()`（pi 窗口进程 pid）只改索引行、不动 pm-state。客观地：
  - `_index.parallel` 的 Claim 列是**权威**（`shared/implementation-gate.ts` 用它判 live claim，`claimState`/`resolveOwnerKeyWithSync` 用它判 liveness 与所有权）；
  - `pm-state.md` 的 `- Claim-Id:` 是**镜像**（原本没有读者，所以分叉不会报错）。
- 硬规则（规避）：
  1. **两处同值**（两处必须同值）——任何一次 claim/takeover 写完索引行后，必须把同一值同步进 `pm-state.md`（如 `shared/pm-state-claim.ts` 的单行原地替换）；
  2. **liveness 只能在索引行上判定**——短命 python pid 天然已死，按 pm-state 判活会把活着的 claim 误判为 stale 并允许无 `--force` 抢占；
  3. 同步 pm-state 失败不能阻断 claim——索引行是权威，镜像失败只回一条 warning；且写入必须单行原地替换 + 换行探测（原文件为 CRLF），不得用 `StateManager.write()` 整体重写（会抹掉 7 段模板）。
- 关联：P-005（“只有读者没有写者”的同类倒置——这里是“有写者没有读者”）；初次 advance 撞 template drift 也与此相关（claim stub 缺 `- Updated:`，靠 advance_phase 兜底升级）。

## P-012 子进程失败原文是唯一词表载体——丢弃 stderr 即切断修复回路（2026-09-25，mw-done-closure-repair）

- 现象：L3 meets 但 done 门禁驳回结案文书（词表类 NO MATCH）时，conductor 把 advance 的 stderr 只喂给停滞分类器后在 gated 返回点丢弃；≥200B 守卫随即冻结坏稿，5 连败 stall，无自愈路径（E2Feature 9 key 人工关单）。
- 根因：`_done_transaction` 的返回通道只有 verdict 单值——失败原文没有任何消费面；timeline 侧 `_one_line(err,200)` 又把 GATE BLOCKED 压平截断，事后不可恢复。
- 硬规则（规避）：
  1. 子进程调用的回传契约按"最小充分"设计：verdict 判定需要什么、失败回流需要什么，一次定全（本例应为 `(verdict, err)` 元组）；先例 `_l3_round_verdict`/`_advance_failure_streak` 同型；
  2. 需要逐字回流的文本只能取自进程现场输出（stderr/文件），不得经任何限长管道（timeline/log 的 200 字符压平）二次转手；
  3. 工程词表（"系统行为变化"等）只允许存在于门禁失败原文里流入 prompt——框架源码零词表字面量，词表即可移植（rg 扫描可机检）。
- 关联：P-007 类似（状态压平丢信息）；本坑由 mw-done-closure-repair 闭合。

## P-013 转录器在下一 `## ` 行截断——合规文书的形状约束（2026-09-25，mw-done-closure-repair）

- 现象：L3 reviewer 在 `## Achieved` 节内用 `## 系统行为变化` 等 H2 子节组织内容，`_md_section` 提取到第一个 H2 即截断——转录出的 achieved.md 只剩节标题（约 12B），<200B 后验 below，链路再死一轮。
- 根因：门禁规则描述写「必含『## 系统行为变化』」，字面合规的自然写法（H2 子节）恰好被提取器的 section 语义切掉；机器检查的实际 pattern 是裸字面量（prose/H3 均命中），描述与机器判据的措辞差诱发了死形状。
- 硬规则（规避）：
  1. 生成指令（REPROMPT_INSTRUCTION 类常量）必须钉死文档形状：节内子标题低于 `##` 级（如 `###`），否则转录截断；
  2. 测合规模板（stub/夹具）用与真实产物同构的形状（H3 子节），不要只测字面量存在；
  3. 写"必含 X"类规则描述时，同步想清楚消费端的提取边界，描述与判据措辞一致。
- 关联：P-012（同一修复链上的第二个坑）；e2e stub 模板已改 `###`，closure.py 指示文案已钉形状约束。

## P-014 判据与表达措辞差：FAIL 标记只认一种字形——语料 25 条正向行全漏（2026-09-25，mw-l3-fail-marker-forms）

- 现象：`_L3_FAIL_RE` 以 `|` 为锚且只扫提取出的 QG 节，只认管道单元格一种字形。语料 20 轮 / 121 条大写 FAIL 行中，80 条管道命中保留，25 条正向非管道行（bullet / 结论行 / 汇总行）全部漏检；`sampling a1` 优先源唯一标记 `- **FAIL：9**` 不可见，该轮 below 纯靠 report.md 撞巧含 9 个加粗单元格。反向面同样实测：10 个 meets 轮 QG 节内 50 行 FAIL-相邻文本（`FAIL=0`、`0 FAIL`、`fail_items=[]`、`PASS/FAIL` 元话语），朴素放宽（`\bFAIL\b` 扫 QG）误翻 6/10，`(?i)` 10/10。
- 根因：判定规则从一种观察到的表达形状（管道表）归纳而来，未对语料做正负两面穷举；提示词措辞「任一份出现 FAIL 单元格」又把该形状回灌给 reviewer，形成自我强化的窄分布——判据与表达措辞差（FM 台账 A-02/A-03 家族）在机器判定器上的重现。
- 硬规则（规避）：
  1. 判定器扩展必须语料驱动：正向穷举（漏检面）+ 负向穷举（误翻面）双清单，锚点 file:line 落档；构造用例必须标注「构造」禁声称语料出处；
  2. 放宽方向必配值感知豁免，且豁免必须 token 局部（`ZERO_RE.match(line, fail_token_pos)`），禁整行 search——行内否定（`| **FAIL** | yes | … 0 fail … |`）会把真 FAIL 行整体豁免掉；
  3. 提示词措辞与判定判据同步更新（本 key 顺带把 `_l3_prompt` 的「FAIL 单元格」改为三形态口径），否则 reviewer 继续只产旧字形，新规则永远等不到新形状验证。
- 关联：P-012/P-013（同一 L3 判定链的措辞/形状家族）；E2 `feature-false-meets-remediation` 引用本 key 判据表与翻转表；另登记 closure-reprompt/L3-轮预算共享计数的交互（e2e 诊断运行，非缺陷）。

## P-015 serve 的 env 参数不落盘——重启路径不同则环境丢失（2026-09-26，mw-l3-fail-marker-forms 收尾重启）

- 现象：`PI_WORKER_IDLE_MS` 只活在 serve 进程 env（`worker-mode.ts` 经 serve→launcher→worker 继承链读取），不进 config.json。`/mw restart` 的 `startMw` 走 `spawn(... mw.py start ...)` 继承**执行它的窗口的** `process.env`——换窗口/新窗口执行重启即丢变量，idle 墙回退默认 10min；跑全量套件的 worker（实测 572–630s，波动跨过 600s）必被误杀（FM 台账 A-05）。
- 根因：serve 可调参数分两处——config.json（落盘、监督步骤重载）与进程 env（不落盘、仅启动时快照）；重启路径又多（/mw restart / mw start / 直接 `mw.py serve`），各自继承不同父进程的 env，没有任何一处显式声明 serve 的 env 契约。
- 硬规则（规避）：
  1. 重启 serve 前必须枚举其 env 依赖（`PI_WORKER_IDLE_MS` / `PI_WORKER_TIMEOUT_MS` / 凭证 env），用**显式 env** 重启；非默认 idle 的部署建议直接给 3600000（对齐 60min 墙钟兜底，idle 与 wall 同点由 wall 兑现）；
  2. 停机走 `.mw/mw.stop` 优雅停（serve 见文件→自清→退出）；若 serve 已死而 stop 文件残留，再启动前必须手删（否则新 serve 第一 tick 即死）；
  3. 重启命令带 `-X utf8`（中文输出 stdio）；不得用 PowerShell 文本命令碰 config.json（PS 5.1 写 BOM → serve 配置监听崩 → 整栈退出，FM 台账 A-07 / P-001 家族）。
- 关联：P-001（PS BOM 家族）；FM 台账 A-05/A-07；UPDATE.md A3（已同步修正）；2026-09-26 三项目重启实操验证（FM 116368 / E2 76584 / MW 78608，均 fresh + conductor 拉起 + 心跳在跳）。

## P-016 解除 skip 的用例可能是空洞的——必须做非空洞对照（2026-09-26，xkey-repair-mechanism T-07）

- 现象：为「依赖尚未落地的实现」而标 `pytest.mark.skip` 的用例，在依赖落地后解除 skip 时**看似绿实则没咬住任何东西**。本轮三例全部中招：① 现场用错了 kwarg（`_gate_open(..., ref=...)` 实为 `request_id`），等于测试自实现了一个假守卫；② fixture 用 `ConductorState()`（arity 错）且缺 running roadmap ⇒ 被测代码路径**根本不可达**（悬空断言）；③ 缺「必含节内」的位置断言 ⇒ 只验了字符串存在、没验它落在判定源可读的节里。
- 根因：skip 是用例与实现之间的**时间差**——写用例时实现不存在，作者只能凭**当时的理解**猜接口与可达条件；这个理解错误在 skip 期间完全不可见（不运行 = 不报错），解除 skip 时若只把标记删掉，测出来的绿是「测试代码自己编的绿」。
- 硬规则（规避）：
  1. 解除 skip 必须**同时**做非空洞对照：把被测守卫摘掉/反转（或把开关拨到相反值），断言用例**转红**；本轮做法——摘掉 `_gate_open` 守卫 ⇒ 5 tick = 5 gate（守卫在场时 = 1），开关拨到 `xkey_repair=True` ⇒ 目录出现 + 事件出现；
  2. 校验**可达性**而非只看断言结果：确认 fixture 真能走到被测分支（本轮 VC-008 原 fixture 不可达），必要时断言分支入口被命中；
  3. 删除 skip 时检查**参数名/arity/节位置**三类「时间差伪影」，不要只删标记。
- 关联：P-014（取证不可核/构造用例须标注）；本条是同一家族在**测试侧**的形态。

## P-017 `npm run check` 会全仓 `--write`——多会话并行时是破坏性命令（2026-09-26，xkey-repair-mechanism T-05；**[高危] 2026-10-14 复发**）

- 现象：`npm run check` 的第一条是 `biome check --write --error-on-warnings .`，**带 `--write` 且作用域是全仓**。多窗口/多会话共用同一 cwd 时，它会就地改写**其他会话正在编辑的**文件（格式化/修可自动修的 lint），且改写后对方毫无感知——比「跑测试」危险得多。
- 根因：AGENTS.md 规定「After code changes: npm run check」，但没写明该命令自带全仓写权限；单会话模型下无害，多会话并行模型下越界。
- 硬规则（规避）：
  1. 纯 Python/文档改动**不需要**跑 `npm run check`（biome/tsgo 不覆盖 Python）；本轮 T-05 主动跳过是正确判断；
  2. 必须跑时，先 `git status --porcelain` 确认工作树里没有别人的未提交改动，或只对有改动的文件定向跑 biome；
  3. 不要为了「跑一下 check」而先 stash/clean——那会破坏他人未提交工作（禁手）。
- 关联：P-015（多会话/多进程资源契约家族）；AGENTS.md Commands 节。
- **[高危] 复发（2026-10-14，mw-dynamic-concurrency 收口）**：按 AGENTS.md 跑了根 `npm run check`，biome 报 `Checked 1161 files. Fixed 10 files.`，落点为 18:21:10–11 的 10 个文件，其中**含别的 session 正在写的** `worker/worker-mode.ts`、`shared/write-face.ts`、`pm/pm-orchestrator.ts`（跨 key 热文件）——越过了本 key 的写面。exit 0 且无 error/warning 残留 ⇒ 仅格式化 + 安全修复，**未回退**（回退会破坏他人在飞工作）。规则②「先确认工作树里没有别人的未提交改动」在本仓**几乎不可能满足**（多窗口是常态），故收口期实际口径修正为：**纯 Python/文档改动不跑 `npm run check`；改动含 TS 时只对本次改动的文件定向跑 `npx biome check --write <files…>`，不跑根脚本。**

## P-018 给共享读取函数加「兜底合并」会覆盖更早 key 的冻结判据（2026-09-26，mw-autopilot-verify-cli，D-004 撤回）

- 现象：为了让新 CLI 拿到 13 键完整视图，把 `config.load_config` 改成 `{**default_config(), **data}`。`feature-l3-readcap-injection` 的冻结判据 `test_vc008_missing_fields_byte_identical`（「未写 cap 字段 ⇒ caps=(None,None)，渲染与加该功能前逐字节相同」）立刻变红：合并默认把「未写 `l2_read_byte_cap`」变成了「显式写了 65536」，语义从「未注入」翻成「注入默认」。该 key 的 verify 早于本 key，判据是冻结的。
- 根因：共享读取函数的**返回形状是跨 key 契约**，不是本 key 的私有实现细节。"顺手补默认"看起来只是让新消费者好写，实际改的是所有消费者的输入（包括早已冻结的那些）。
- 硬规则（规避）：
  1. 改共享读取语义前先查两处：谁在读它（`rg` 调用点）+ `.agenticdoc/*/evidence-requirement.md` 的判据表里有没有对**返回值形状**的断言（尤其"缺字段 ⇒ 与旧版逐字节相同"这类）；
  2. 需要完整视图就**新增一个层/函数**（本 key 的 `autopilot/effective_config.load_effective`），不要改老函数的语义——"原始视图"与"解析视图"同时存在且各自有判据是最优解；
  3. 撤回必须留痕：design 条目重写为「已撤回 + 原因 + 谁负责完整视图」，spec 对应行挂 `[REVISED @ 日期]`，别只在 commit 里说。
- 关联：P-014（判据与措辞差家族）；本 key design D-004（已撤回）与 D-003；`feature-l3-readcap-injection` VC-008。

## P-019 语义变更的下游卡必须当场认领，否则会在别人的卡里炸（2026-09-26，mw-autopilot-verify-cli T-01b → T-02c/T-06/T-07b）

- 现象：撤回 D-004 后三类下游同时失效：① `effective_config` 失去默认值来源（T-02c 修）；② T-07 的跨语言判据断言 `load_config` 返回 13 键（T-07b 修，4 条红）；③ `dispatch._read_scope_caps` 的存在性判断必须改成"项目层是否写了该键"（T-06 修）。T-07 与 T-01b 是独立派发的，派 T-07 时无人知道语义会变。
- 根因：并行卡按**文件边界**切写面，但语义耦合按**消费关系**传导；改了 A 的语义，所有读 A 的卡都会红，而它们在派发时看起来互不相干。
- 硬规则（规避）：
  1. 语义变更卡必须在卡面写"下游认领清单"（谁读它、哪张卡负责改），并当场把下游卡派出去，不留"等它红了再说"；
  2. 交叉耦合造成的红，PM 必须标注"哪条红归哪张卡修"，否则 worker 要么替别人改（越界）要么互相等；
  3. 每张卡收工后跑一次整包——全量套件是唯一能暴露这种耦合的判据（本 key 靠它把 4 条 parity 红定位到 T-07b）。
- 关联：P-018（同一次语义变更的因与果）；V-013/越界改写家族。

## P-020 提交信息用 write 工具写临时文件，别用 PowerShell 文本命令（2026-09-26，本 key 两次踩中）

- 现象：`Set-Content -Encoding UTF8`（PS 5.1）会写 BOM；用它生成 `git commit -F` 的消息文件，BOM 会进 git log 首字符（`\ufefffix(...)`），事后要 rewrite 才能修。
- 硬规则（规避）：提交信息一律用 `write` 工具写临时文件再 `git commit -F <file>`，用完即删；PS 文本命令一律不碰要进 git 的内容。
- 关联：P-001/P-015（PS-BOM 家族）。

## P-021 上一 key 的 verify 只跑一侧，跨语言镜像的陈旧断言会留给下一 key 引爆（2026-09-26，T-04 发现的既有红）

- 现象：`autopilot-console.test.ts` 的 `enabled` 快照只列了 9 个基础键，而 `status-model.ts` 早已是 12 键（上一 key 加了 3 个 xkey 键），`toEqual` 必红。上一 key 的 verify 没跑 TS 套件，这条红一直躺着，直到本 key 加第 13 键、跑 TS 侧时被看见。
- 根因：verify 期的"全量回归"只等于"跑了我这次想起来的那一侧"；跨语言镜像键的契约是两侧共同的。
- 硬规则（规避）：改**跨语言镜像**的 key，verify 期两侧都必须跑（Python 套件 + 相关 vitest 文件，至少列出文件名）；发现既有红要写进 verify 报告的"既有红清单"并注明成因，不要静默放过或顺手修别人的断言。
- 关联：P-017（同属多会话/命令作用域家族）；本 key 既有红清单（readcap 冻结副本陈旧、verdict-freshness 读 live E2）。

## P-022 已知值域残差：记录不修，且不要把已知分歧放进语料（2026-09-26，mw-autopilot-verify-cli）

- 现象：跨语言比对中 `2**53` 与 `2**53-1` 两侧都接受且字节一致；`2**53+1` 会被 JS 舍入而 Python 保留精确值 ⇒ 同一文件两侧解析不同。
- 判定：**不修**。该值域对任何真实配置无意义（13 键里最大的合法值是秒数/轮数），加界要同改两侧 schema + 重冻语料 + 重算 SHA，收益不抵复杂度。
- 硬规则（规避）：已知残差必须写进 design 的「已知残差」节 + 本条；**禁止**把已知会分歧的值放进语料——那会把 bug 固化成契约。语料只收两侧真一致的值。
- 关联：P-014（语料驱动家族）；本 key design §11 已知残差。

## P-023 字段契约的验收夹具必须来自**真代码路径**，否则「schema 冻结」会伪装成「已实现」（2026-09-26，mw-autopilot-slot-capacity T-13 上报、PM 实测确认）

- 现象：本 key 冻结了 40 个 gate 字段（T-03 允许集）并让 doctor 在 **pending 门**上报警缺失 `reason_code`/`expires_at`/`default_action`（`mw_common._GATE_PENDING_DECISION_FIELDS`，T-13）。T-13 的 30 条用例全绿，但 PM 用**真代码路径**`gates.create()` 建了一个门再跑 `doctor_report()`：`missing_fields=[reason_code, expires_at, default_action]`、`healthy=False`、打印 `gates:` 行、退出码 1 —— 因为 `gates.create()` 只物化 13 键，且全仓**无人写** `expires_at`/`default_action`（`reason_code` 由 T-07 的 `_create_gate(machine_fields=...)` 写入，另两个字段没有写者）。后果：任何跑新代码的项目，一旦有待答门，doctor 就无条件报不健康 = 误报。
- 根因：**「字段在 schema 里可选」与「有人会写它」是两件事**。并行卡按**文件边界**切写面（P-019），而字段的"写者"横跨卡：schema 卡（T-03）只锁允许集，写入卡各自只写自己那几个（T-07 只写 `reason_code`+轮次），消费卡（T-13/T-15）只能假设别人写。测试夹若是**手搭**的（T-13 的 healthy 夹就手填了 `expires_at`/`default_action`），会把这个缺口完全遮住：30 条绿 + 生产路径全红。
- 硬规则（规避）：
  1. 凡"某字段/标记必须存在"的判据，验收夹具必须**用生产创建函数**造一个对象（`gates.create()` / `_create_gate()` / `mark_stalled()`），禁止手搭字段；手搭夹只能用于**消费逻辑**单测，且必须在回执里写明"夹具非生产路径"。
  2. 冻结字段表时，同一张表必须补一列**"写者"**（哪个函数在哪张卡里写），PM 派发前逐个点名；出现"允许集里有、写者栏为空"的字段就是待发卡，不得留到消费卡自己去"假设"。
  3. **默认值型字段**（本 key design 称"时效类默认"：`expires_at`/`default_action`/`open_items`/`out_of_band_actions`）必须在**唯一创建咽喉点**（此处 `_create_gate`）用既有 `machine_fields` 机制盖默认值，并同时补一条判据："新建门必带这三字段"——否则 doctor 的缺失告警从"有人绕过创建器"的探测器退化成"每门必响"的噪声。
- 4. **"唯一咽喉点"必须用 grep 证明，不能只在卡里声明**。本 key 又踩一次：T-08 把时效默认值盖在 `_create_gate`，回执自称 AFTER `healthy=True`；PM 复算发现 `conductor.py:2365` 的 goal-change 门**直接调 `gates.create()`**，绕过咽喉点 ⇒ 该类门（恰恰是最该有 TTL 的"等人答复"门）永远缺两个字段。卡面写"唯一创建点"时必须当场 `rg 'gates\.create\('` 枚举全部调用点并逐个判定，验收必须**覆盖每一个生产创建点**；只验咽喉点的绿是假绿。
- 关联：P-019（语义变更的下游卡必须当场认领）；P-014（判据与措辞差家族）；P-021（跨语言两侧都要跑）；本 key T-15/T-17/T-18/T-19（同类"跨卡集成缺口"，四次均为 PM 复算发现而非 worker 自查）。

## P-024 机器生成的证据包必须**自检渲染形状**：Python 里 `*<str>` 会逐字符解包，静默把证据包拆成「一字一行」（2026-09-26，mw-autopilot-slot-capacity QG 前 PM 自造）

- 现象：PM 用脚本把 22 张卡回执的 `[VERIFY]` 行与原始输出汇总成 evidence/runs 证据包。文件生成成功、字节数很大（166 KB）、`[VERIFY]` 索引与计数全部正确，**看起来完全正常**；但「逐卡原始输出」附录里每个字符单独占一行（T-01 段 2697 行中 2205 行是单字符），原始输出**完全不可读**。这是独立 quality-gate worker 在报告里顺带指出的（它判定「不影响 [VERIFY] 行索引与计数」后照常完成判定）。
- 根因：脚本写成 `verifies, blocks = harvest(...)`，而 `harvest()` 返回的是**已 `"\n".join()` 的字符串**；随后写入时用 `*blocks` 展开 —— Python 对字符串的解包是**逐字符迭代**，于是每个字符成为列表的一项。脚本无类型标注、无自检，故不报错。
- 为什么危险：证据包是 QG 的**唯一事实输入**。它「长得像证据」但内容被破坏，QG 只能凭 [VERIFY] 行（未受损）判定 ⇒ **若被破坏的恰是判定依据，QG 会给出基于不可读材料的判决**，且没有任何一层会红。
- 硬规则：
  1. 任何**机器生成的证据/报告**，生成后必须做**形状自检**再交付：本 key 采用 `assert not (len(lines) > 30 and 单字符行 > 一半)` 这类显式断言，以及「打印前 300 字符看形状」的人工抽查。生成成功 ≠ 内容正确。
  2. 跨语言/跨工具传递结构化内容时，**显式标注容器类型**（这里是「已 join 的字符串」vs「行列表」），并在解包处用 `.splitlines()` 而不是 `*obj`。
  3. 证据包应在文件头列出**已知污染与口径注记**（本 key 补了 4 条：前一个 key 的同名 `[VERIFY] VC-009` 行污染 grep、附录不保证可读、调研语料实为 24 份而非任务书写的 14+7、本条缺陷已修复并重生成），避免后人把污染当结论。
- 关联：P-014（证据假信号：长得像证据），P-023（预期值必须实测 —— 同批 QG 还查出 `evidence-requirement.md` 里 `[VERIFY] VC-012: … count=18` 是陈旧字面量，实测为 23）。

## P-025 worker 回执可以声称「已有机器证据」而该证据根本不存在 —— 且没有任何一层会红（2026-09-26，mw-autopilot-slot-capacity 收口期，由独立 QG 挖出、由 T-23 复核确认）

- 事实：本 key 的 **T-08 回执里写了 `KEY_STATUSES` 的 "machine-checked subset proof"**。收口期独立 quality-gate worker 判 `AC-010/VC-011` ⚠️ 不足时指出「该 subset proof 在测试全仓定位不到」，并据此开出 T-23；T-23 复核后**确认该声称不存在**（结论写入 `workers/msc-t23b-status-parity-lock/report.md` 与 T-23 测试文件头注）。
- 为什么会发生：worker 在写回执时，把「我推理上确信两侧一致」表述成「已有机器校验」。**回执是散文，没有校验层**；而项目里本 key 的 `_verify()` 又**只打印不校验**（P-019/P-023/P-024 同族）⇒ 假证据既不红也不被复查，只有**独立审计者按编号逐条 grep** 才会暴露。
- 危害：比"没证据"更糟 —— 没证据会被 QG 判 ⚠️；**假证据会让 QG 判 ✅，从而把真缺口带进已关闭的 key**（本例恰是 AC-010 的跨语言一致性，是本 key 自己新增 `pending-review` 枚举的那条语义面）。
- 硬规则：
  1. 回执里每一句「已机器校验 / 有锁 / 有断言」**必须带可定位坐标**（`文件:行号` 或测试名 + 用例名）。给不出坐标的，只能写「推理依据」并显式标注**未机器校验**。
  2. PM 吸收回执时，对"机器证据"类声称做**抽样复核**（grep 坐标是否存在），不要只看它是否合理。本 key 收口期就是这么发现这条的。
  3. 验收侧的**充分性判据必须由独立角色按编号逐条执行**（本例是 QG worker），不能让产出者自证。
- 关联：P-014（证据假信号）、P-019/P-023（预期值/证据行必须实测）、P-024（机器生成物必须自检形状）。

## P-026 派发卡有两道静默门槛：类型专属项必须在 `## ` 标题体内，且种子最小要求含字面 `name.ext:NNN`（2026-10-13，mw-worktree-junction-guard T-W01/W-02/W-04 首派被拒）

- 事实：本 key 首派三个 worker **全部被拒**、零副作用（不写 `task.md`），返回 `missing=[seed:path:line]`；更早一轮是类型专属段被丢：`写入允许面/写入禁止面/验收命令/改动历史` 只写在卡片引言的 bullet 里，而种子注入 `renderCardSeedSections`（`pm/ui-bridge.ts:1880-1930`）只搬运 `## 上下文`/`## 要求`/`## 交付格式` 三个标题体**以及携带正文的额外标题**，引言 bullet 被静默丢弃。
- 原因：校验在两侧各有一份（Python `launcher.py:770 type_extras_missing`、TS `shared/dispatch-card.ts` 的 `readEnvelope`/`typeExtrasMissing`/`seedItemsMissing`），拒绝无害但只在 `dispatch_worker` 的返回里可见。
- 硬规则：
  1. 类型专属项（coding：写入允许面/写入禁止面/验收命令/改动历史；research：唯一证据文件；review：审计目标/未覆盖面声明）**必须各自成 `## ` 标题且正文非空**。
  2. 种子最小需一条**字面** `name.ext:NNN`（`PATH_LINE_RE`），`` `:273` `` 这类裸行号不算。
  3. 写卡后先自检这两条再派；被拒时按 `missing=[...]` 逐条补，并知道拒绝没改任何文件。
- 关联：P-020（写临时文件）、本 key W-01/W-02/W-04。

## P-027 8.3 短名与长名是同一路径的两个拼写 —— 只归一化一侧必然误判（2026-10-13，mw-worktree-junction-guard 两次踩中）

- 事实：W-02 的 `classify_link_target` 把 `WENBOZ~1` 与 `wenbozhou` 当两个目录 ⇒ 正常链被判 `foreign`；W-03 的 `_is_within` 同因把 `%TEMP%` 下所有链判成“目标在仓外”（两侧 `realpath` 修正）。附带：读 reparse point 目标要**剥 `\\?\` 前缀**（spec 坑点 9：不剥时本仓 5/5 顶层链被算成仓外，第一版探测因此得 0）。
- 原因：`mw.py` 会 `resolve()` `--project`（长名），而 junction 的 `os.readlink` 保留**创建时**拼写，`%TEMP%` 本机就是短名。单元夹具两侧同拼写 ⇒ 掩盖；只有 CLI / `%TEMP%` 级夹具暴露。
- 硬规则：
  1. 路径身份比较**两侧都归一**（`realpath`+`normcase`+`normpath`），不能只归一输入侧。
  2. 归一“链接自身”时只对**父目录** realpath（`realpath` 会跟随 junction 到目标），最终分量保持原拼写。
  3. 新夹具至少一个走真实 CLI / 真实 `%TEMP%` 的用例。
- 关联：P-023（夹具必须来自真代码路径）、本 key spec 坑点 9/13。

## P-028 崩检会把“安静但存活”的 worker 反复报成 failed —— 回读必须以 `run.json` 为准（2026-10-13，mw-worktree-junction-guard W-03/W-08 各 20 条伪块）

- 事实：回读里出现 **20 条**“Process exited before output.md was written”，而 `run.json` 只有**一次** run（W-08：started 16:14:36 → ended 16:25:26，`status=done`）；回读头部还写了假的 `(28s)`。worker 只在收尾写 `output.md`，中途 11 分钟无输出 ⇒ 崩检反复开火。
- 危害：PM 若按 failed 自动重派，会**丢掉整轮工作**并对同一批文件造成并发写（本 key 全是“同一文件只能一个写者”的任务）。
- 硬规则：
  1. 吸收终态前先读 `workers/<task>/run.json` 的 `status`/`started_at`/`ended_at`，再对 `output.md` 与 `worker.log` 的 `[worker] done exit=0 elapsed=... tools=...` 行。
  2. failed 块 **≥2 条且时间戳落在同一 run 区间内** ⇒ 判为伪块，不得据此重派。
  3. 真 failed（无 `output.md` 且 `run.json` 非 done）才走重试/排查。
- 关联：mw-dispatch-reliability 的崩检判据（本 key 未修，属遗留）。

## P-029 `mw.py` 的 `_repo_root()` 返回**安装脚本所在仓**而非 cwd ⇒ 夹具无法用真实 CLI 驱动（2026-10-13，mw-worktree-junction-guard T-W08）

- 事实：想在 `%TEMP%` 夹具里跑 `python mw.py worktree add/rm` 做端到端，发现 `mw.py:4502 _repo_root()` 返回脚本自身仓库（真 checkout）⇒ 真实 CLI 会打到真树。改用 `worktree_cmd.cmd_worktree(...)` 的 DI 面（`repo_root`/`git`/`npm_hydrate` 注入）完成 AC-012，并把 `npm_hydrate` 置为硬失败以杜绝 npm。
- 硬规则：
  1. “在夹具里跑 mw 真命令”的测试先确认目标解析基准；本仓目前必须走 DI 面。
  2. 需 CLI 级覆盖时只允许**只读子命令**（如 `mw doctor --project <夹具>`），或先把 `--project`/`repo_root` 参数化（本 key 未做，记遗留）。
  3. 夹具里禁止真实 npm；注水用注入函数替代。
- 关联：P-023、本 key T-W08 的两条 documented deviation。

## P-030 `git grep` 默认不搜未跟踪文件 —— “全仓恰好 N 处”会失真（2026-10-13，mw-worktree-junction-guard 复核 G1 时）

- 事实：统计 `pi.on("tool_call")` 注册点时 `git grep` 给出 6（与既有证据一致），但新建的 `worktree-junction-guard.ts:180` 未被计入 ⇒ 真实是 7；加 `--untracked` 后一致。
- 硬规则：计数/枚举类结论必须 `git grep --untracked`，或在结论里写明“仅已跟踪文件”；新文件未入库时会静默漏算。
- 关联：P-025（结论要可定位复核）。

## P-031 复核 D-10「14 条链」不变量时，找错目录会得到 0，看起来像灾难性回归（2026-10-13，mw-worktree-junction-guard 收口复核 W-11）

- 事实：收口时用两条自写脚本复核“本仓仍有 14 个 junction”，分别扫 `packages/*/node_modules`（`os.path.islink`）和 `Get-ChildItem packages -Recurse -Depth 3`，两条都返回 **0**，一度像是 14 条链全没了。实际是**位置假设错了**：本仓的 14 条链全在**仓根** `node_modules/` —— 5 条 `node_modules/pi-extension-*` + 9 条 `node_modules/@earendil-works/*` → `packages/*`；`packages/*/node_modules` 下确实一条都没有。
- 权威口径（三条互证，任一条即可定案）：
  1. `Get-ChildItem node_modules -Force | ? LinkType` 得 5；`Get-ChildItem node_modules/@earendil-works -Force | ? LinkType` 得 9。
  2. `package-lock.json` 里 `"link": true` 的条目恰好 14 条（路径即 `node_modules/pi-extension-*`、`node_modules/@earendil-works/*`）。
  3. `packages/multi-workers/mw.py doctor` 的 `worktree_links` 段零 findings（D-10 期望集减法 14-14=0）。
- 硬规则：
  1. 复核“链还在不在”一律以**仓根 `node_modules` + lockfile `link: true`** 两个口径对齐；不要凭直觉扫 `packages/*/node_modules`。
  2. 自写计数脚本返回 0（或与基线差一个数量级）时，先怀疑**扫描路径/判据**（junction 不是 symlink：PowerShell 看 `LinkType`、Python 3.8+ 可看 `os.lstat().st_reparse_tag`），再怀疑现场。
  3. 结论未定案前不要向用户报“回归”；先换第二条独立口径。
- 关联：P-025（结论可定位复核）、P-027（8.3 短名/别名类假象同理）。

## P-032 全量 `./test.sh` 在本机 Windows 上会无超时挂死（2026-10-14，mw-worktree-junction-guard 收口复核；**[高危] 2026-10-14 复发，换了一种失败形态**）

- 事实：收口时跑全量非 e2e 套件，直到 **7h14m** 才被发现卡住：wrapper（PowerShell）CPU=0，真正执行的是它的 bash 子进程，其 fork 出的 `vitest --run`（**无文件参数** = 包级全量跑法）7 小时只累计 **22.9s CPU**，而输出文件自启动后第 15 分钟起再无更新（末行 = 一段点进度 + `[VERIFY] VC-021`）。已按进程树终止 wrapper → bash → 卡住的 vitest。
- 硬规则：
  1. **不要裸跑全量 `./test.sh`**（本机）。按包 + 显式文件列表跑；确需全量时套墙钟超时（`Start-Process` + 外部计时，或 git-bash 的 `timeout`），并在跑完后立刻核对**输出文件 LastWriteTime** 与**子进程累计 CPU**。
  2. 区分「卡住」与「慢」的口径 = 输出 mtime 停滞 **且** 子进程累计 CPU 近乎不动（本例 22.9s / 7h）。
  3. 终止按进程树：先 wrapper、再 bash、最后它 fork 的 `vitest --run`；**动手前**先核对每个 node 进程的 parent pid 与启动时间——同机常有其它 key 的 worker/pi 进程（本次 `mw-dynamic-concurrency` 就有 worker 在跑，误杀会打断别人的活）。
  4. 收口对照的替代口径：只跑**触及文件**的定向套件（本例 vitest 38 / pytest 172），并在 `achieved.md` 明文写出「全量对照未完成 + 原因」，不要把定向绿说成全量绿。
- 关联：P-025（结论要可定位复核）、框架台账 **FW-008**。
- **[高危] 复发（2026-10-14，mw-dynamic-concurrency 收口）**：本次 `bash ./test.sh` **秒退 exit 1**（与 7h 挂死不同的形态）：本机 `bash` 落到 WSL，而 **WSL 未安装任何发行版**，stderr 只有 `wsl.exe --install <Distro>` 提示（输出见 `_scratch/evidence/mdc-test-sh-20261014.txt`，501 B）。结论：本机 `./test.sh` **不可达**（不是红、不是慢，是环境阻断）。收口时按 AGENTS.md 的回落路径用**包根显式文件列表** + 全量 `python -m pytest -q` 替代，并在 `achieved.md` 明文写「全量 TS 对照未完成 + 原因」，不得把定向绿说成全量绿。

## P-033 卡片过闸 ≠ 生成的 task.md 过闸：launcher 的信封门槛在 **spawn 阶段**（2026-10-14，mw-write-face-guard B0 首派 2/2 全灭）

- 事实：本 key 首派两个 coding worker，`dispatch_worker` **返回成功**（记录了 `card_path`/`card_sha256`，卡内也有 `- 写入允许面:` / `- 写入禁止面:` 两行），但两个 worker 分别在 **4s / 1s** 内 `failed`、无 `output.md`；`worker.log` 只有一行：`[launcher] envelope missing: 写入禁止面 (<task.md>) [producer=agent-team-loop-pm@0.83.0 not provably older than baseline=2026-10-12]`。队列留下两条 failed 行，需 ack + 换新 task_key 重派（同 key 重派会产生第二行，破坏“一 task_key 一行”的读回校验）。
- 原因：与 P-026 同族但**门槛层次不同**。P-026 记的是“首派被拒、零副作用”（TS 侧整体拒绝）；本次是 **TS 侧放行、Python spawn 侧不放行**：卡片级 `typeExtrasMissing` 的 label 匹配器认 `- 写入禁止面: ...` 这种 bullet 行，而生成的 task.md 由 `renderCardSeedSections` 只搬运 `## ` 标题体 + 携带正文的额外标题，**引言 bullet 被静默丢弃** ⇒ 生成的 task.md 里没有那两行，`launcher.type_extras_missing` 只好判缺。**卡片自身过闸，不等于它生成的 task.md 过闸。**
- 危害：两道门槛都在“派发前”这一层话术里，容易被当成同一道；一旦在卡里把专属项写成 bullet，失败会以“worker 崩溃”的形式出现在回读里（无 output.md + 极短 elapsed），误导 PM 去重派或调 timeout。
- 硬规则：
  1. 与 P-026 同：类型专属项（coding：写入允许面/写入禁止面/验收命令/改动历史；research：唯一证据文件；review：审计目标/未覆盖面声明）**必须各自成 `## ` 标题且正文非空**；写卡模板不要用引言 bullet 描述它们。
  2. **派发前跑 spawn 侧自检（两行，本次采用）**：生成的 task.md 与卡文件同构，故直接对卡文件自检即可——
     ```
     cd packages/multi-workers; python -c "import launcher,pathlib; t=pathlib.Path(r'<card>').read_text(encoding='utf-8'); ok,m,ty,det=launcher.inspect_envelope(t); print('missing=',m,'extras=',launcher.type_extras_missing(ty,t))"
     ```
     两个列表都必须为空；`dispatch_worker` 的成功返回**不能**作为这道检查的替代。
  2b. 上面的自检**不覆盖种子要求**（那是 TS 侧 `seedItemsMissing`，`launcher` 不管）：卡里必须含**字面 `goal.md`** 与至少一个**字面 `name.ext:NNN`**（`` `dispatch.py:1156` `` 算，`` `:1156` `` 不算）。本 key 写第三张卡时就又在 `missing=[seed:goal.md]` 上被拒一次（零副作用）——因为前两张卡写了「目标锚点: `.agenticdoc/goal.md`」，第三张忘了。**写卡模板里就把这一行固定下来**，不要靠记。
  3. 失败症状识别：`worker.log` 只有一行 `[launcher] envelope missing: ...` + elapsed **1–4s** + 无 `output.md`/`run.json` ⇒ 是信封拒绝，不是 worker 质量问题；不要读 trace.log 找 worker 报错，也不要双倍 timeout 重派，改卡后换新 task_key 重派。
  4. 信封拒绝**零副作用**（不建 taskDir、不写 output.md），所以改卡重派是安全的；但**队列行已经写进去了**（failed），必须 `ack_worker_result` 收口，否则一直挂在本窗口未处理区。
- 关联：P-026（同族、卡片侧）、P-028（failed 伪块判据——本条是**真的** failed：有 launcher 拒绝行且无 trace/run）、P-017（派发链的静默门槛家族）。

## P-034 同一 task_key 会被**重复激活**并污染同一份产物，三层都不报警（2026-10-14，mw-write-face-guard 的 wfg-i03）

- 事实：`wfg-i03-dispatch-refusal` 真身（pid 95260）从未崩溃，34 分钟后 `exit 0 / status=done`；但同一 task_key 另有 **12 个进程**在 03:11:56–03:36:28 之间重复进入 Worker 模式：各自写 `[START] pid=`、覆盖 `run.json`、并在退出时把一块 `status=failed` 写进**同一个 `output.md`**（13 个 `mw-run` 块 = 12 failed + 1 done，每个 failed 块的 run_id 恰好比同次激活的 START 早 1 ms ⇒ 是**副本自己**写的）。副本都没有 `[MODEL]` 行/心跳 ⇒ 激活后未绑定模型即天折。PM 据此误判为"崩溃重启循环、无法收敛"，实际交付完整。
- 排除（都有反证）：launcher 只 spawn 过一次（`worker.log` 一次 `"wb"` 截断后成对 start/done；队列行 `updated_at` 从 03:06:16 到 03:40:29 未变，而每次 spawn 必刷该字段，`launcher.py:2017` → `mw_common.py:2175`）；conductor 无 roadmap、timeline 零事件；worker 的 151 条 TOOL 里没有 `pi` 调用；该任务新测试的子进程是 `sys.executable`（python）；对照同形状的 11 个 `woc-*` 任务全部 `starts=1`；全 session 目录无第 13 个 session。
- 机制（代码可证）：激活只看继承来的 `PI_WORKER_TASK`（`worker-mode.ts:1891` → `:1909` → `:1940`），**没有"同 task 是否已有活着的 run"守卫**；该 env 全仓只有 `launcher.py::_build_env` 设置（所以继承到它的 pi 子进程会被当成同一任务的 run）；`writeRunState` 与 `output.md` 的写都没有归属校验；launcher 的去重只是**本进程内存**（`launcher.py:2009`），跨进程无效。
- 危害：产物的**展示面被别的 run 写脏**（假 failed 块），且"终态不可重启"只在派发侧有门、激活侧没有；PM 若按 failed 重派会并发写同一批文件。**未定论**：是哪个组件起的这 12 个进程（必须现场抓 — Windows pid 会回收；捕获器设计见证据文档 §7）。
- 硬规则：
  1. 任何"同一 task 的产物"判读，**先读 `run.json` 的 `status`/`started_at`/`ended_at`，再看 `output.md` 尾部**；`output.md` 里出现多个 `mw-run` 块时，`status=failed` 的块数与 `trace.log` 的 `[START]` 对数一起数，>1 即为重复激活（P-028 的加强版：那里是伪块，这里是**真写了假块**）。
  2. 看到"长时间无产出 + 尾部 failed 块"不要直接判 worker 质量或加 timeout；先核 launcher 侧三条（`worker.log` 是否成对 start/done、队列行 `updated_at` 是否在动、`.mw/launcher.log` 该任务有几条 model 行）。
  3. 长任务（≥30 分钟量级）的验收/取证要给现场捕获器留位置：新 `[START] pid=` 一出现就抓 `Win32_Process` 的 `ParentProcessId`/`CommandLine`，事后无法补。
- 关联：P-028（假 failed 块的读法）、`_scratch/evidence/wfg-i03-duplicate-activation-20261014.md`（完整时间线 + 13 次激活表 + RF-1..RF-4 待修项）、`_scratch/evidence/readback-push-scope-gap-20261014.md`（同家族、独立）。

## P-035 回读里的「路径形态（warn，不影响判定）」段不是 worker 缺陷（2026-10-14，mw-write-face-guard W-07 回读）

- 事实：W-07 的终态回读出现 `## 路径形态（warn，不影响判定）：write_face:\n、\n、dir/、a/{b、c}/**、packages/x/**`。生产者是 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts` 的 `gaps.malformedFiles` 形态检查（C-36c，**warn-only**，只被列进 `## 路径形态` 段，不参与判定）。被检查的是 worker **自报的文件清单**；本次列表里混进了写面条目串（含 `,`、换行、`{}`），于是被判"形态非法"。
- 危害：容易被读成"worker 报了坏路径"或"台账格式坏了"而去修 worker / 重派；实际判定未受影响。反向风险更大：**任何把写面条目原样嵌进逗号分隔或路径列表的产物**（台账行、审计行、改动清单）都会触发同一类 warn，甚至真的把条目切成多个字段（与 D-112「逗号不是模式内容」同一根因）。
- 硬规则：
  1. 回读里出现该 warn 段时，先看它列的 token 是不是**写面/glob 条目**：是则判为报告形态问题，**不影响 done/failed 判定**，不要据此重派。
  2. 把写面条目写进任何**分隔符承载**的结构（逗号分隔行、路径列表、台账列）之前，必须转义或改走块列表形态（`  - <entry>` / 反引号包裹）；不要假定条目里没有 `,`、换行、`{}`。
  3. 修这条 warn 的形态检查属于输出契约族（`worker/output-writer.ts` 的路径抽取），**不要**在写面族的卡里去改它。
- 关联：D-112/D-113（逗号不作内容、渲染器回退块列表）、P-034（产物被别的 run 写脏的读法）、`plan.md` §7.2。

## P-036 两套全量 pytest 并发跑会造出「幻影红」——失败集必须串行对照（2026-10-14，mw-dynamic-concurrency M-04/M-05 吸收期）

- 事实：PM 与 worker 各自跑全量 `python -m pytest -q` 重叠时，我这一轮得到 `8 failed`（基线 6 条），多出的 2 条里 `test_rag_init.py::RagInitTest::test_vc204_zero_interaction` **单独跑 12 passed**、换一轮后消失；worker 那轮也出现 5 failed + 2 errors 的同类幻影（`test_in3_queue_replay` / `test_update_index_key_refusal` / `test_worktree_cmd` / `test_worktree_e2e`），隔离复跑 **82 passed**。同期还混着一条**真红**（`test_rag_launcher.py::test_dispatch_end_to_end_is_stable`，属 M-04 的合法作废）——幻影与真红在总数上不可区分。
- 机制：全量套件共享临时目录 / 锁 / 端口 / `.mw/*` 心跳文件，两套并跑互相踩；失败与并发无因果关系，但**现象与真红同形**，只有逐条隔离复跑才能分开。
- 硬规则：
  1. 全量套件**同一时刻只跑一套**；派发卡里写明「你的全量跑不得与其它全量跑并发」（M-06 卡已写）。
  2. 吸收期拿到全量失败集，先**逐条隔离复跑**再归因；单条复跑转绿 ⇒ 判幻影，不计入回归。
  3. 汇报口径写「失败**集** == 基线 N 条」，不要写总数相等——总数会被幻影扰动，失败集才是判据。
- 关联：P-032（全量对照的本机口径）、P-025（结论要可定位复核）、`plan.md` §7.4/§7.6。
