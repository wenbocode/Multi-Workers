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
