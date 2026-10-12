# 对抗审计报告 — mw-dispatch-settle-gates（代码面）

- 角色: `mds-qg-b-code-adversarial`（独立质量门，read-only，无 bash）｜type: review｜日期: 2026-10-11
- 审计对象: `packages/coding-agent/src/extensions/agent-team-loop/` + `packages/multi-workers/`（AC-003/T-01、AC-005a/T-02、AC-005b/T-03、AC-006/T-04、AC-010/T-05、AC-001/T-08、AC-002/T-09、AC-004/T-10 共 6 组落点）
- 方法: 全文通读 6 个落点源码 + 其依赖（read-scope.ts / paths.ts / index-store.ts / output-writer.ts / worker-file-tool.ts / deliverable-evidence.ts / output-sections.ts / launcher.py / roadmap.py）+ 7 个 mwds 测试文件 + spec/design/plan/pm-state/t12 收口证据。**未执行任何命令**（无 bash），所有判定为静态读码推演；凡需执行才能最终确认的一律标「未核（无 bash）」。
- 结论摘要: **6 个落点的正向机制（守卫存在、落位正确、方向性与文档一致、单点写盘、fail-open/closed 语义）经读码确认成立**；同时构造出 **11 项攻击，其中 8 项读码层面成立**（1 项部分成立、2 项为文档/口径反例），含 3 个高价值绕过（`bash -c` 包装脚本、AC-005a 扩展名白名单、框架 basename 白名单目录盲判）与 1 个方向性违约（变量化重定向产生**误拦**，违反 P1「漏放不误拦」承诺的另一半）。残留登记（P2 / R21-H）在 spec/design/plan/pm-state/t12 中如实，但 `achieved.md` 尚不存在（D-026 承诺的登记面未落盘）。

## ① 攻击结果表

| # | 攻击构造 | 代码依据（文件:行号） | 成功? | 影响面 |
|---|---|---|---|---|
| A1 | `bash -c 'echo x > .agenticdoc/<KEY>/pm-state.md'`（同族: `sh -c`、`zsh -c`、`powershell -Command "Set-Content …"`、`cmd /c "echo x > …"`、`perl -e`、`ruby -e`、`dd of=`、`awk '{print>"f"}'`、`install`、`rsync`、cmd 内建 `copy/move/del/md/rd/ren`） | worker-mode.ts:786-803（`inlineScriptArgument` 只认 python/python3/py/node 的 `-c`/`-e`）；:830-884（switch 无 `bash`/`sh`/`powershell`/`cmd`/`pwsh` 分支）；:733（SHELL_WRAPPER_COMMANDS 仅 sudo/env/command/nohup/time/nice/stdbuf/xargs）；:764（POWERSHELL_WRITE_COMMANDS 只匹配裸 cmdlet 名） | **成功（读码判定）** | AC-005b 全拒清单可被一个包装命令整体绕过。注意：`python -c` 被拦而 `bash -c` 不拦的不对称——对工具名就叫 bash 的 research 角色而言这是最廉价的一条绕过。属 P1「无法归类⇒放行」的声明边界内（spec AC-005b 列举的已知写模式不含 shell 包装器），但「python/node 一行脚本拦、bash -c 不拦」的不对称未被任何文档登记 |
| A2 | `T=$PWD/.agenticdoc/<KEY>/workers/<TASK>/report.md; echo x > $T`（变量/`$(…)` 重定向目标指向**允许面内**路径） | worker-mode.ts:821-824（重定向目标按**字面 token** 收集）；:959-963 + read-scope.ts:100-113（`normalizeForCompare` 把 `$T` 字面解析为 `<root>/$T`）⇒ rule=scope 拦截 | **成功（读码判定）** | **误拦方向**：合法写自身 taskDir 被 block。P1 契约明文「失败模式 = 漏放而非误拦」（spec AC-005b、t03 卡 6 条、mwds-t03 头注），此构造违反承诺的另一半；trace 会记一条假阳性 `[WRITE_SCOPE]` 审计行 |
| A3 | `把结论写入 config.toml`（或 `.env`、`Makefile`、`x.html`、`x.rs`——任何不在 13 扩展集内的路径）派给 `type: review` | ui-bridge.ts:1345-1346（`WRITE_INTENT_PATH_RE` 仅匹配 `md\|py\|ts\|tsx\|js\|json\|ya?ml\|log\|txt\|ps1\|sh`）；:1392-1421（无命中 ⇒ 无 violation）；:1444-1452（`judgeWriteIntent` 无命中 ⇒ ok=true，fail-open 放行派发） | **成功（读码判定）** | AC-005a 的 R22 空转形态原样复现：无 write/bash 角色拿到写外部路径的任务书，dispatch 期不拒，worker 空转后由 AC-006 兜成 NC。扩展名白名单在 spec/design **均未声明**（两者只写「写动词 + 路径 + ≤32 字符 + 5 护栏」）⇒ 这是实现自设的收窄，不属已声明取舍 |
| A4 | `唯一允许写入 ../other-key/workers/other-task/output.md`（Windows 形态 `C:\elsewhere\trace.log`）派给 `type: review` | ui-bridge.ts:1423-1431（`isWhitelistedWriteTarget` **先**按 basename 放行: :1426 `WORKER_FILE_NAME_RE.test(base)`、:1427 `FRAMEWORK_TASK_BASENAMES.includes(base)`，**后**才有目录解析 :1429-1432）⇒ 任何以 output.md/trace.log/task.md/run.json/worker.log/report.md/progress.md 结尾的路径无条件放行 | **成功（读码判定）** | AC-005a 派发期可满足性被路径形态绕过：写**他人任务目录**或任意绝对位置的框架同名文件不被拒。卡片 T-02 第 4 条只授权「框架自有文件名」入白名单（语义=本任务自身的框架文件），basename 无目录判是超出卡面的实现漂移；已登记的 R-T02-1（t12 §7 R3）只覆盖 output.md 是否入列的分歧，未覆盖目录盲判 |
| A5 | 另一窗口 live 持有 key `_tmp`；本窗口 `dispatch_worker(key: "_tmp")`。变体: `key: "../victim"` / `key: "."` | ui-bridge.ts:250（`startsWith("_")\|\|startsWith(".")` ⇒ 守卫直接 return null）；paths.ts:32-34（`workerTaskDir` = 裸 `path.join`，无形态/穿越校验） | **成功（读码判定）** | spec AC-003 反向用例只放行「自有 claim / 未认领 / `_scratch`」；实现把 `_`/`.` 前缀整体豁免 ⇒ live 外键注入（跨窗口派发 bug 原样回归）。`../victim` 形态更把 taskDir 写出 `.agenticdoc` 之外（越出协调根，守卫与 spec 均未设想） |
| A6 | Windows: 行 `mw-key` 被他人 live 持有，本窗口传 `key: "MW-KEY"` | index-store.ts:159-161（`findByKey` 精确字符串 `e.key === key`，无大小写折叠）+ Windows 文件系统大小写不敏感 ⇒ `.agenticdoc/MW-KEY/workers/` 物理上就是他人 `mw-key/workers/` | **成功（读码判定，仅 Windows）** | 同 A5：跨 key 写入且零告警。测试全部用精确大小写 key，未覆盖 |
| A7 | `_index.parallel` 无 active 行（如各窗口 quiet re-claim `activate:false` 后全 idle）+ `_index.md` 陈旧 `active: K` + K 行 claimId 为他人 live | ui-bridge.ts:82（`active?.key ?? readIndexMdActive(...)` 兜底不经守卫）；:1676（守卫仅在显式 key 分支调用 `if ((key ?? "").trim())`）；守卫注释自称「implicit path 永不触达外键」——只对 activeEntry() 分支为真 | **成功（读码判定，前置条件窄）** | 隐式路径跨 key 写入。resolveOwnerKeyWithSync 的降级只护 activeEntry() 分支，`readIndexMdActive` 兜底成了一条绕过守卫的隐式通道 |
| A8 | 任务书正文含一行字面 `type: coding`（示例/未围栏代码片段），frontmatter 仍是 `type: research` | worker-mode.ts:308-353（`parseTaskMd` 全文件扫描，顺序覆盖 ⇒ **最后一个** `type:` 行胜出 :333-335）；:1467-1477（bash 写面守卫注册条件 = `isShellRole(meta.type) && isWritelessRole(meta.type)`）⇒ type 翻成 coding 后守卫整体不注册 + 全量 write 工具 | **成功（读码判定）** | 一行正文文本即可关掉 AC-005b 守卫并升级工具集。`write_scope:` 同病（:386-411 正文行覆盖 header）：正文 `write_scope:` 空值 ⇒ 全部 bash 写被拦（DoS 方向误拦）。属 parseTaskMd 既有形态，但本 key 把安全性押在其上且未测试 |
| A9 | 无 run.json 的 writeless run，回复引用**运行前已存在**的 `evidence/research/old-2026.md`（任务书引导「复用旧报告结论」） | deliverable-evidence.ts:153-171（`findReferencedEvidence` 的 mtime≥started_at 反伪造轴仅在 `Number.isFinite(startedAtMs)` 时生效 :168；无 run.json ⇒ startedAt=undefined ⇒ 新鲜度轴关闭）⇒ 通道 2(c) 命中 ⇒ delivered | **成功（读码判定）** | AC-006 可被「引用旧证据」满足：exit 0/done、无 no-product 告警。语料 0/30 无此形态 ⇒ 28/2/0 校准未测过该轴。R-03/R4 只登记「artifacts 通道前瞻性弱」，未登记新鲜度轴随 run.json 缺失而失效 |
| A10 | pending gate + 0 非终态行 + **无 timeline**（conductor 从未跑）的同一 fixture：面板 vs doctor | monitor.ts:704+829（tickAgeMs=null ⇒ tickStale=false ⇒ 面板**打** BLOCKED_ON_HUMAN）vs mw_common.py:3117-3120（`_conductor_tick_fresh` 正向新鲜度 ⇒ 无 beat 即 False ⇒ doctor **不打**） | **部分成功（口径反例）** | spec AC-001「三轴口径与面板**同源**」在该角落两边结论相反。mw_common.py:3066-3068 注释显式声明该差异（I7 零扰动）为有意——属登记过的分歧，但 spec 字面「同源」被证伪；t12 seam-4 三个用例全部 `writeBeat`，恰好绕开此角落（t08 只测了 doctor 侧） |
| A11 | roadmap 把同一 key 声明在 stage 1（closed）与 stage 2（running）；该 key 的 pending gate 无 `stage` 字段 | conductor.py:2553-2557（按 `stage_of_key` 解析到 stage 1 ⇒ rank 2 ⇒ 抑制）；roadmap.py:477-483（`stage_of_key` setdefault「首次声明胜」）；roadmap.py:259-294（seen_keys **每 stage 独立** ⇒ 跨 stage 重复 key 不被 parse 拒绝） | **成功（读码判定）** | 活跃 stage 上的门被静默——抑制方向（丢提醒）而非漏放。spec「provably belongs to a terminal stage」在重复声明下并不成立，实现却按成立处理 |


## ② 证伪成功的项（最小复现读法）

以下 4 项为「推翻守卫/文档断言」的核心证据，各附静态复现链（无 bash，读码推演）：

**F-1（推翻 AC-005b「已知写模式 + 包装器覆盖」的完整性假设）**
1. `worker-mode.ts:821`：重定向提取仅识别 token.text **精确等于** `">"` 或 `">>"`。`echo x >| f` 的 token 序（:667-731 的 tokenizer 把 `>` 与 `|` 切成两个 operator，`\|` 不并入）= `echo`、`x`、`>`、`|`、`f`——`f` 落在 `|` 之后的命令位，commandName=`f` ⇒ 无任何 case 命中 ⇒ **零候选**。bash 的 noclobber 覆写形式 `>|` 整体漏放。
2. `bash -c '…'`：单引号体成为**一个 word**（:667-695 引号规则），commandName=`bash` ⇒ :830-884 switch 无此分支、:733 包装器集合无 bash、:786 只扫 python/node 的 `-c`/`-e` ⇒ 零候选。对工具名即 bash 的 research 角色是最短绕过。
3. `cp -t /evil/dir a b`（GNU 目标前置）: :835-841 取 `values[values.length-1]` 为目标 = 最后一个**源**，真实目标目录 `/evil/dir` 不被判。真实写越界、被提取目标却可能是 taskDir 内的源文件（放行）。
结论：P1「漏放」边界覆盖了「未归类命令」，但 `>|`、`bash -c`、`cp -t` 属于**已被分类路径上的漏放**（重定向/复制两类已知模式自身的形态漏洞），与 spec 列举的已知模式表存在差距。

**F-2（推翻 P1「失败模式 = 漏放而非误拦」的单向承诺）**
`T=<taskDir>/report.md; echo x > $T`：
- :821-824 将字面 `$T` 收为 redirect 目标；
- `checkBashWriteScopeTarget`（:959-963）调用 `normalizeForCompare(projectRoot, "$T")`（read-scope.ts:100-113，`path.resolve(root, "$T")`）= `<root>/$T`；
- :975 `!isSameOrUnder(taskDir, …)` ⇒ rule=scope **block**，trace 记 `[WRITE_SCOPE] … blocked … cmd=echo x > $T`。
真实写落在允许面内却被拦——这是 P1 契约明文排除的方向。spec AC-005b 的反向用例「写自身 taskDir 不得拦」只测了字面路径形态，未测变量形态。**未核（无 bash）**：未实际执行；推演依据 tokenizer/resolve 语义，确定性高。

**F-3（推翻 AC-005a 的扩展覆盖假设 + 白名单目录盲判）**
- 无命中方向：`把结论写入 config.toml` —— `WRITE_INTENT_PATH_RE`（ui-bridge.ts:1345-1346）不匹配 `.toml` ⇒ `collectWriteIntentHits`（:1392）零命中 ⇒ `judgeWriteIntent`（:1444-1452）`ok:true` 派发 ⇒ R22 空转形态回归。
- 白名单方向：`写入 ../other-key/workers/other-task/output.md` —— 路径 regex 命中（`\.{2}/` 前缀允许），`isWhitelistedWriteTarget`（:1423-1427）**先**看 basename（output.md ∈ FRAMEWORK_TASK_BASENAMES）直接 `return true`，:1429 的目录解析永远执行不到。写他人任务目录的不可满足任务书在派发期放行。
- 二者叠加：spec/design 均未声明扩展名白名单；卡片 T-02 第 4 条的「框架自有文件名」被实现成了无目录判的 basename 匹配。已登记的 R-T02-1 只覆盖 output.md 入列分歧，不覆盖目录盲判与扩展名缺口。

**F-4（推翻「文案=守卫集合」之外的隐性断言：隐式路径注释）**
`foreignLiveClaimRefusal` 的调用条件是 `if ((key ?? "").trim())`（ui-bridge.ts:1676，dispatch_worker）/ `resolveOwnerKeyWithSync` 后直接调用（/worker :2188 附近）。ui-bridge.ts:76-81 的注释声称「The implicit path never reaches here with a foreign key (resolveOwnerKeyWithSync degrades to _scratch)」——但降级仅发生在 `activeEntry()` 分支（:72-75）；:82 的 `readIndexMdActive` 兜底名不经任何守卫直接成为 ownerKey。该注释断言被 :82 自身证伪（构造见 A7）。

## ③ 方向性核对表

| 判据点 | 缺失/无法解析时朝哪边失败 | 代码依据 | 与文档一致性 |
|---|---|---|---|
| AC-006 交付判据缺 `run.json` | artifacts 通道死（`nonOutputArtifacts`→[]，deliverable-evidence.ts:180-184）；evidence 新鲜度轴关闭（:168）⇒ 偏 NC（artifact-only run）但对旧证据引用 fail-open（A9） | deliverable-evidence.ts:153-184 | artifacts 弱已登记（spec §2/§8 R-03、t12 §7 R4）；**新鲜度轴失效未登记** |
| launcher reap 缺 `run.json`/非终态 | 退出码 fallback（历史映射逐字不变） | launcher.py:376-396 | ✓ 文档化（DD-06/t07） |
| `dispatch.py` `read_run_status`=None | 放行派发（零回填） | dispatch.py:509-538 | ✓ 文档化+测试（VC-014） |
| `write_scope` 头缺省 | 默认面（taskDir+`<key>/evidence`），相对收窄 fail-open | worker-mode.ts:380-385, 959-975 | ✓ 文档化+t12 seam-1 测试 |
| `write_scope` 头空值 | `[]` ⇒ **一切 bash 写被拦**（含自身 taskDir） | worker-mode.ts:987-997 | ✓ 注释明写「fail-closed, mirroring read_scope」；但空值也拦自身 taskDir 这一半未单独测试（producer 永不产空值行，仅手工/正文注入可达，见 A8） |
| `write_scope` 条目无法匹配 | block（rule=write-scope） | worker-mode.ts:939-957 | ✓；垃圾条目形态未测 |
| `judgeWriteIntent` 无命中 | ok=true 放行（fail-open） | ui-bridge.ts:1444-1460 | ✓（与「只拒检测到的不可满足」一致）；但缺口面（A3/A4）超出已声明取舍 |
| T-09 stage 解析不到 / roadmap 缺失 / 未知 status / 悬空 stage 号 | **不抑制**（照常提醒） | conductor.py:2540-2557 | ✓ 文档化+测试（(c)(d)(f) 三向） |
| T-09 `stage_status`/`stage_of_key` 双参缺省 | 条件 4 永不触发（逐字旧行为） | conductor.py:2532-2534 | ✓（fail-open，D-015） |
| AC-001 轴 3（doctor）缺 timeline | not fresh ⇒ `blocked_on_human=false`（对告警 fail-closed） | mw_common.py:3117-3120 | 代码注释声明为有意（I7）；**spec「与面板同源」字面被证伪**（面板同角落 fail-open，A10） |
| `_blocked_on_human` 轴 2 解析 | 非 `_TERMINAL_STATUSES` 一律计 in-flight（pending 也算） | mw_common.py:2431-2436, 2440 | ✓ 与面板 `TERMINAL_WORKER_STATUSES` 镜像一致（status-model.ts:1341-1347） |
| AC-005b 拒绝清单 vs `write_scope` | 拒绝清单绝对优先，不可被 scope 放宽 | worker-mode.ts:923-937 → 959-986 | ✓ 文档化+测试（t03「cannot widen past the deny list」） |
| AC-010 读侧全占位 | undefined ⇒ 回落既有降级文案（done⇒""、NC⇒no output.md） | output-sections.ts:121-148; ui-bridge.ts readTerminalDetail | ✓ VC-043d 测试 |


## ④ seam（C1…C10）重复实现与漂移清单

| # | seam | 判定 | 依据 |
|---|---|---|---|
| 1 | **C2 消费端不存在**（漂移） | plan C2 明文「T-02 → T-03（消费端只 grep marker 判定『已注入』，不解析内容）」；grep 全扩展：`WRITE_SURFACE_MARKER` 仅出现于 `pm/ui-bridge.ts:1257-1258/:1348/:1492/:1496`（生产+幂等正则），**worker 侧无任何消费者** | 契约的机器消费半边未实现；marker 实际只服务 LLM 阅读 task.md。C2 的机器语义（「已注入」判定）无人调用——seam 声明与实现不符 |
| 2 | **两个 section 切分器**（drift 风险已具体化） | `deliverable-evidence.ts:121-142 sectionBodies`（逐行 `^##\s+` 锚定、不过滤 `---`）vs `output-sections.ts:66 SECTION_SPLIT_RE`（**无行首锚**，行中 `## ` 亦可成段；过滤水平线）。二者对「什么是一个 section」定义不同 | 已可指出两处分叉后果：(a) 行中 `` `## TL;DR` `` 引文在读侧成段（标题带尾渣，title 不匹配故无害但计数漂移）、oracle 侧不成段；(b) oracle 的段体含尾随 `---` 分隔线（isPlaceholderBody 全串比对失配——实际后果被「后续必有第二块」遮蔽，见 ⑤ 未覆盖 9）；(c) 无标题自由文本：oracle 计为单 body（deliverable-evidence.ts:144-150）、读侧返回 undefined ⇒ done 行 detail="" 而 settle 判 delivered |
| 3 | **C7 占位符归属漂移**（轻） | plan C7「占位符集集中在此模块导出（15 个）」；实际声明在 `deliverable-evidence.ts:63`（**16** 个字面量，头注写 15）、output-sections.ts:40 只是 re-export | 单一真相源保住了（无第二份清单，VC-043e parity 也锁了 oracle↔读侧），但「归属模块」与「计数」与 plan 有出入（t04 断言 size=16 与头注 15 自相矛盾，见 ⑤-1） |
| 4 | **C9 形参形态漂移**（轻） | plan C9：`pending_gate_reminders(gates, now, …, stage_status: dict\|None, stage_of_key: callable\|None)`；实现：`(pending, rows, reminder_counts, now, after_min, max_reminders, stage_status: dict[int,str]\|None, stage_of_key: dict[str,int]\|None)`（conductor.py:2522-2532） | `stage_of_key` 由 callable 变 dict；语义（缺省⇒不抑制）保真；t12 STAGE_PROBE/t09 测试按新形态调用 |
| 5 | **C5 落点漂移**（轻） | plan C5「置于 pm-orchestrator.ts」；实际在 `shared/deliverable-evidence.ts:187` | 签名一致、消费者（worker-mode finishSuccess、t12 seam-2、launcher 只读 run.json.status）一致；纯位置漂移 |
| 6 | C1（write_scope 渲染↔解析） | **无漂移** | ui-bridge.ts:1476-1478（单行逗号式）↔ worker-mode.ts:386-411（单行逗号 + 兼容块列表 + 空值 fail-closed）；t12 seam-1 双向 + 缺省/空值两形态实测 |
| 7 | C3（角色能力单一来源） | **无漂移** | `isShellRole/isWritelessRole` 只在 worker-mode.ts:126/133 声明，ui-bridge import（`import { isShellRole, isWritelessRole } from "../worker/worker-mode.ts"`）；Python 侧 REGISTRY parity 另有既有锁 |
| 8 | C4（单点写盘） | **无漂移** | `writeDispatchTaskMd` 1 定义（ui-bridge.ts:1539）+ 2 调用（:1794/:2251）；t01 断言源内 `fs.writeFileSync(taskMdPath` 仅剩 1 处（函数体内） |
| 9 | C6（alarm kind + trueRoot） | **无漂移** | `recordDispatchAlarm(meta.trueAgenticdocRoot, {kind:"no-product"})`（worker-mode.ts finishSuccess 内）；pm-orchestrator 值域+describe case 齐 |
| 10 | C8（doctor 字段↔后缀） | **无漂移**（A10 的轴 3 口径差另计） | mw_common.py:3193（字段）+ :3630（后缀 iff 字段为真）+ `_gates_text_alerted`:3227 |
| 11 | C10（read_run_status 复用） | **无漂移** | dispatch.py:520 单读一次；t10 monkeypatch 计数 1 |
| 12 | **hasProductEvidence vs hasDeliverableEvidence** | 有意并存（DD-07），非 drift | pm-orchestrator.ts:495-500 纯 existsSync 未动；t04 VC-029 判别性测试在 |

## ⑤ 空洞断言 / 未覆盖分支清单

**偏空洞的断言（2 条）**：
1. `mwds-t04` (c)：`expect(DELIVERABLE_PLACEHOLDERS.size).toBe(16)` —— 对实现自身常量的**计数**自证：成员可换可漂（换成同数另一串仍绿）；16 个字面量中只有 2 个（`(worker exited without writing output)`、`Process exited before…`）经 PLACEHOLDER_OUTPUT fixture 实际钉住。且该断言与 deliverable-evidence.ts:62 头注「15 placeholder/default strings」自相矛盾（实现即源头，头注陈旧）。
2. `mwds-t03` "extractBashWriteCandidates covers the required write patterns"：对每条命令只断 `targets.length > 0` + 4 条精确值钉（cp/mv/Set-Content/git clean）。断言面薄但 4 条精确钉可证伪，列「半空洞」。

（反例：t01 VC-011 的「文案=调用点」grep 源码断言可真实证伪（预 AC-003 缺口即会红）；t05 的 `independentLastSectionFirstLine` 刻意绕开被测实现自写参照——这两处**不空洞**。）

**未覆盖分支（文件:行号 + 形态）**：
1. `worker-mode.ts:821` —— `>|`（noclobber 覆写）、`<>`、`>&` 等重定向变体：tokenizer 切开后无 case（A1/F-1）。
2. `worker-mode.ts:733` —— SHELL_WRAPPER_COMMANDS 包装器后的命令位（`sudo rm`、`xargs rm`）无测试。
3. `worker-mode.ts:835-841` —— `cp -t`/`mv -t` 目标前置形态（提取错位，F-1.3）。
4. `worker-mode.ts:786-803` —— `bash -c`/`sh -c`/`powershell -Command`/`cmd /c`/`perl -e`/`ruby -e`/`dd of=`/`awk`/`install`/`rsync`/cmd 内建（`copy/move/del/md/rd/ren`）包装器（A1 主向量）。
5. `worker-mode.ts:821-824` + `:959-963` —— 变量 / `$(…)` 重定向目标的字面判定（A2 误拦方向）。
6. `worker-mode.ts:333-335` / `:386-411` —— 任务书**正文**行覆盖 frontmatter（`type:` 翻角色、`write_scope:` 空值 DoS）（A8）。
7. `ui-bridge.ts:250` —— `_`/`.` 前缀 live 外键（A5）；`paths.ts:32-34` 的 key/taskKey 形态零校验（`../` 穿越）。
8. `ui-bridge.ts:82` —— `readIndexMdActive` 隐式兜底不经守卫（A7）。
9. `deliverable-evidence.ts:121-142` vs `output-sections.ts:66` —— 行中 `## ` 成段差异、`---` 进 oracle 段体、无标题自由文本 oracle↔读侧分叉：t05 VC-043e parity 测试**显式跳过**无 `^##\s+(TL;DR\|Summary)\s*$` 的文件（`if (!/…/.test(text)) continue;`），恰好把分叉面排除在 parity 之外。
10. `deliverable-evidence.ts:168` —— run.json 缺失时反伪造轴关闭（A9）：t04 T3 用例全部先 `writeRunState`，无一测「无 run.json + 引用旧 evidence」。
11. `monitor.ts:704/829` vs `mw_common.py:3117-3120` —— 无 timeline 角落的面板/doctor 分叉（A10）：t12 seam-4 三用例全 `writeBeat`；t08 `test_b_no_timeline_means_not_blocked` 只测 doctor 侧。
12. `conductor.py:2553-2557` + `roadmap.py:477-483/259-294` —— 跨 stage 重复 key 声明 ⇒ 首声明（closed）胜出抑制活跃 stage 的门（A11）；t09 (c) 用的是无重复声明的 roadmap。
13. `index-store.ts:159-161` —— 大小写变体 key（A6，Windows）。
14. `ui-bridge.ts:1345-1346/:1402-1404` —— 扩展名集外路径、>32 字符间隔的漏放（A3）；t02 语料回放测的是「仓库里已存在的任务书」，不含这些构造。


## ⑥ 残留登记核对（攻击 5）+ 未核部分

### 6.1 AC-005b P2 与 R21-H 的登记现状

| 残留 | 登记处 | 判定 |
|---|---|---|
| P2（OS 级隔离）不在范围 | spec §2 非范围「P2（OS 级隔离）明确不在本 key 范围」；design §8 R-01「已知边界…P2 不在本 key」；t12 §7 R2「设计档位，保留」 | **如实** ✓ |
| P1 漏放边界 | spec AC-005b「精心构造的写仍可能漏放（失败模式 = 漏放而非误拦）」+ 全量命令入 trace；t03 卡 6 条 | **如实** ✓（但「误拦」方向被 A2 证伪——承诺的两半只守住了一半） |
| TS 守卫在 `mw build --install`（R21-H）前不生效 | plan.md 头部「R21-L 已生效…**R21-H 未做（TS bundle 仍未切换）**」；plan §6（禁 build）；design §8 R-05「本 key 改动在切换前均不生效」；pm-state D-015「TS 侧仍未切换（installed bundle 2026-10-10 11:40:42，R21-H 待批）⇒ 每次 dispatch 后仍必须跑队列归一化」；pm-state **D-026**「TS 侧守卫在 R21-H 完成前只能验到单测/套件级…**此项写入 achieved.md 的残留节，不得算作已上线**」 | **如实，但有一处缺口**：`achieved.md` 在整个 `.agenticdoc` **尚不存在**（repo 级 find = 0 命中；本 key 处于 VERIFY，D-045 把 achieved.md 排在本质量门之后）。即 D-026 承诺的登记面**未落盘**——没有文档把守卫表述为「已上线」（未见夸大），但承诺的残留账本还未兑现，PM 写 achieved.md 时必须带上 D-026 全文口径。另注：t12 §1 的 per-AC「PASS」表不带「运行期未生效」限定语，单读该表易误读为已交付（限定语在 pm-state/plan/design，不在该表内） |

### 6.2 未核部分与理由（无 bash）

1. **所有攻击构造均未实际执行**——角色无 bash，不能跑 vitest/pytest/节点探针。A1-A11 的判定全部来自对 tokenizer/正则/路径解析的静态推演；其中 tokenizer 行为（`>|` 切分、引号成词）与 `path.resolve` 语义确定性高，但**未运行验证**。凡落地前应先以最小脚本复跑（例如 `extractBashWriteCandidates("bash -c 'echo x > f'")` 应返回 `[]`）。
2. **未复跑任何测试**：7 个 mwds 套件与 3 个 Python t0{8,9,10} 的绿态取自报告记载 + 源码通读，未亲跑。
3. **未核对照脚本**：`evidence/scripts/mwds-controls.ps1` 的 31 控制组红→绿记录、各卡 sha256 冻结值、R21-L serve/launcher PID（122476/142424）——均只读登记文本，未复算。
4. **未核运行期活体**：installed bundle（dist/）与 src 的一致性、`mw doctor` 在真项目的输出、真实 worker 触发守卫的行为——R21-H 未做，恰是 D-026 登记的缺口，本审计无法补。
5. **A11 的前置条件**：跨 stage 重复 key 是否会被 `validate_roadmap`（roadmap.py:372+，仅读了 parse 半边）以依赖/一致性规则拒绝，未读全 `validate_roadmap`——若其拒绝重复 key，A11 降级为理论构造。**未核**。
6. **launcher.py 收割链其余部分**（`_reap_task_dirs`、orphan reconcile、mark_run_lost 的调用序）只读了 `_reap_status`/`_exit_to_status`，T-07 的其余接线未逐行复核（超出本卡 6 落点清单）。
7. **`mw.py cmd_doctor` 的 JSON 纯度**（stdout 无杂 print）依赖 t08 的 `json.loads(out)` 断言，未亲验。

## ⑦ 结论（按落点）

| 落点 | 判定 | 关键发现 |
|---|---|---|
| AC-003/T-01 | 正向机制成立（3 面 1 函数、零副作用、文案单一源、单点写盘），但守卫**入口面**有 3 个读码成立的洞 | A5（`_`/`.` 前缀豁免 + key 形态零校验）、A6（Windows 大小写）、A7（`readIndexMdActive` 隐式通道） |
| AC-005a/T-02 | 5 护栏 + 32 字符窗口 + 语料 0 FP 属实；但**判据面**两个实现自设收窄构成绕过 | A3（扩展名白名单未在 spec 声明）、A4（框架 basename 白名单无目录判，超出 R-T02-1 登记范围） |
| AC-005b/T-03 | 拒绝清单绝对优先、write_scope 交集、审计行、幂等注入全部成立；但已知模式表自身有形态漏洞 + 承诺的「不误拦」方向被击穿 | A1（`bash -c`/`>|`/`cp -t`）、A2（变量重定向误拦）、A8（parseTaskMd 正文覆盖） |
| AC-006/T-04 | 三级通道、折码、markOutcome/recordEnd、trueRoot 告警、hasProductEvidence 并存全部成立（t04 判别性测试在）；一个通道级缺口 | A9（无 run.json 时 evidence 新鲜度轴失效——未登记） |
| AC-010/T-05 | 末非占位块、settle 幂等、首匹配契约冻结、4 读点切换全部成立（含 parity 测试）；缺口在 parity 的**排除面** | ⑤-9（无标题/行中 `##`/`---` 三处分叉被 parity 跳过） |
| AC-001/T-08 | 三轴、零写盘、后缀 iff 字段全部成立（t08 覆盖完整、零写盘有树哈希实证）；「与面板同源」字面有一处口径反例 | A10（无 timeline 角落面板 true/doctor false；差异已在代码注释登记，但 spec 措辞未改、跨侧无测试） |
| AC-002/T-09 | 第 4 条件、两级解析、四级 fail-open、单一终态族（rank 消费，源码断言锁死）全部成立；一个重复声明角落 | A11（跨 stage 重复 key ⇒ 抑制活跃 stage 的门；前置条件待验） |
| AC-004/T-10 | 首查 run 状态、终态/running 双拒、None 零回填、单读、字节级惰性全部成立且测试最完备 | 无新发现（唯一备注：陈旧 `running` 永拒依赖 launcher 的 mark_run_lost 兜底，链条未逐行复核） |

**总评**：6 个落点的「文档所说的每一条」都真实存在且方向正确——这是本 key 的主要成果，未发现任何「文案写了没实现」的回归（AC-003 的原始缺口形态未复发）。对抗审计推翻的是**文档没说的部分**：判据面的实现自设收窄（A3/A4）、已知模式的形态漏洞与包装器不对称（A1）、误拦方向违约（A2）、守卫入口豁免（A5/A6/A7）、解析器正文覆盖（A8）、通道级缺口（A9）。其中 A1/A3/A4/A5 建议按优先级立卡：A1（把 shell 包装器纳入已知写模式或至少 `bash/sh/powershell/cmd` 的 `-c/-Command` 内联扫描）与 A5（守卫豁免收窄回 spec 的 `_scratch` + key/taskKey 形态校验）是两条回报最高的收口。


## 更正（报告头部计数，自查发现）

头部摘要写「11 项攻击，其中 8 项读码层面成立（1 项部分成立、2 项为文档/口径反例）」——**计数有误**。按 ① 表逐行复核实为：**11 项攻击 = 10 项读码层面成立（A1…A9、A11；其中 A6 仅 Windows、A7 前置条件窄、A2 为误拦方向而非漏放方向）+ 1 项部分成立（A10，属已在代码注释登记过的口径分歧反例）**。结论方向不受影响：成立项比头部所述**更多**而非更少。特此更正（对抗审计对自身引用同样适用重锚纪律）。
