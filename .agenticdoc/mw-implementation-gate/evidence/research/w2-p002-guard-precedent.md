# Research: P-002 protected-config-guard 先例调研（design 前置，W2）

> Key: mw-implementation-gate | Worker: w2-p002-guard-precedent | 日期: 2026-09-21
> 类型: design 前置调研（spec §2.4 集成依赖 / §5 可复用资产：「P-002 守卫先例实现方式待调研后复用其模式」）

## 决策问题

mw-implementation-gate 的 design 需要确定「无 active key claim → 拦截 write/edit 代码路径」的实现形态。P-002（2026-09-15 事故 → 同日 mw-protected-config-guard 落地）是本仓唯一已投产的工具层硬拦截先例：它拦在哪一层、判定读什么状态、违规时做什么、哪些部分可直接复用、哪些缺口是本 key 必须补的。

## 调研方法与出处

通读全文（非检索片段拼结论），行号经 grep 复核；另做了一次活体探测（见 Q4-4）：

- key 留档：`.agenticdoc/mw-protected-config-guard/`（仅 mini-spec.md 4646 B + pm-state.md 136 B；无 spec.md / design.md / achieved.md / evidence/ —— 该 key 走 pm mini fast path 直做，无 plan/tasks，Result 节自记 AC 验证结果）
- 坑点台账：`.agenticdoc/_pitfalls.md:15-23`（P-002 条目全文）
- TS 守卫主体：`packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts`（全文）
- 注册点：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:3,30,34-40,42-46`
- pi core 拦截语义：`packages/coding-agent/src/core/extensions/types.ts:898-916,1071-1075,1236`；`packages/coding-agent/src/core/agent-session.ts:479-501`；`packages/coding-agent/src/core/extensions/runner.ts:932-951`
- Python 镜像：`packages/multi-workers/mw_common.py:429-504`（守卫四符号）、`:505-527`（settings.json 政策例外注释）、`:545-548`（_write_pi_settings）、`:577` 起（ensure_pi_shell_path）
- 测试：`packages/coding-agent/test/extensions/agent-team-loop-protected-config.test.ts`（全文）；`packages/multi-workers/test_protected_config.py`（全文）
- 姊妹先例（同为 tool_call 硬拦截）：`packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-guard.ts:117-124`
- 全仓 grep 反证：mw.py / autopilot/ / launcher.py 无 protected-config 逻辑；`assert_not_protected_agent_config` 除定义（mw_common.py:487）与测试外零引用

## 发现

### Q1. 守卫在哪一层

两层实现，主拦截在 pi 扩展 tool_call 钩子（非 mw CLI 检查、非 launcher env、非纯文档约束）：

- TS 主守卫（真拦截）：`protected-config.ts:247-276` 的 `registerProtectedConfigGuard(pi)` 注册 `pi.on("tool_call")`；注册点 `index.ts:40`，位于双加载防重入 flag（index.ts:8-27 注释、:30 flag）之后、PM/Worker 模式分支（index.ts:42-46）之前 → PM / Worker / 普通交互窗口三模式全覆盖，同进程双 bundle 不会重复注册监听。
- Python 镜像（advisory，未接线）：`mw_common.py:441-504` 提供 `PROTECTED_AGENT_CONFIG_FILES`（:441）/ `agent_config_dir`（:452）/ `is_protected_agent_config`（:464）/ `assert_not_protected_agent_config`（:487）+ `ProtectedConfigError`（:482）；docstring 自述「guard for any future framework write path」——当前无任何生产调用点。
- 拦截力来自 pi core（未改 core）：`agent-session.ts:480-485` 把扩展 handler 挂进 `agent.beforeToolCall`；`runner.ts:946-949` 任一 handler 返回 block:true 即短路返回；返回类型契约 `types.ts:1071-1075`（`{block?: boolean, reason?: string}`）。

### Q2. 机制：拦什么、怎么判、违规做什么

- 拦截对象：toolName 为 `write` / `edit`（判 `event.input.path`）与 `bash`（判 `event.input.command`）（protected-config.ts:249-274）；读类工具一律放行。
- 判定状态源：只读 env 与 OS（`PI_CODING_AGENT_DIR`、`PI_WORKER_TASK`、homedir、cwd），不读任何项目文件——自包含，无 .agenticdoc 依赖。保护集 = agentDir（env 覆盖优先，默认 ~/.pi/agent；resolveAgentDir :95-100 镜像 core getAgentDir——standalone esbuild bundle 不得 import core config，故镜像常量而非引用，:45-49 注释）下 auth.json / models.json / settings.json / oauth.json 四文件（PROTECTED_CONFIG_FILES :43）+ agentDir 本身（rm -rf 语义）。
- write/edit 判定（isProtectedConfigPath :111-116）：按工具同款语义解析（cwd 相对、`~` 展开、win32 折叠）后与保护集做精确等值比较——非前缀匹配，`~/.pi/agent-alt/`、`.pi/agents` 等不命中。
- bash 判定（checkProtectedBashCommand :191-218）：文本级启发式，fail-closed。三步：① 展开引用拼写（`$HOME` / `${HOME}` / `%USERPROFILE%` / `$env:USERPROFILE` / $PI_CODING_AGENT_DIR 各形式 + 词首 `~`，expandCommandReferences :121-133）；② 匹配保护路径片段（边界正则 `(?![\w-])` 防相邻目录名误命中；相对 .pi/agent 仅在命令先 `cd ~` 后视为命中，protectedReferences :146-158）；③ 扫写类结构：写动词 21 词（rm/mv/cp/tee/touch/dd/install/truncate 等，:162）、PowerShell 写 cmdlet 9 个（:164）、`sed -i`（:166）、`find -delete/-exec`（:167）、重定向目标（:169，目标侧单独判——保护路径做读侧、重定向到别处放行）、内联代码写（`python -c` / `node -e` + 写标记，:172-174，覆盖字符串拼接组装路径的场景）。引用命中 + 任一写结构 → block，即使引用只是读侧（宁可误拒，agent 重跑纯读命令即恢复）。
- 违规动作：① 返回 `{block: true, reason}`——reason = 事实说明 + GUARD_EXPLANATION（:51-56：为什么拦 + 正确做法：关窗口改 / `pi /login`）；② worker 模式（`PI_WORKER_TASK` 存在）向任务目录 trace.log 追加 `[PROTECTED_CONFIG] <ISO时间> blocked tool=… target=…` 一行（recordProtectedBlockTrace :224-241，best-effort：落日志失败绝不影响拦截本身；无 worker env 时 no-op）。
- 无覆盖例外设计：「会话活着即证明 runtime 在跑，拦截无条件，无 agent 侧覆盖开关」（:18-21 注释）；`pi /login` 等 core 用户主动流程与终端人工操作明确不在范围（pitfalls P-002 规则 2）。

### Q3. 可直接复用于实施准入门禁的部分

1. 整套骨架可直接套用：`shared/` 独立模块、纯判定函数与注册函数分离导出（判定可脱离 pi 单测）、`registerXxxGuard(pi)` 在 index.ts activate() 双加载 flag 后、模式分支前注册——三模式覆盖与防重复注册语义原样成立。
2. 拦截原语存在且够用：`tool_call` → `{block, reason}`（agent-session.ts:480 / runner.ts:946 / types.ts:1071）。spec §4 风险第一条（「pi Extension API 可能没有 tool-call 前拦截点」）可关闭。AC-001 要求的「错误消息含建 key 指引」即 GUARD_EXPLANATION 模式（为什么拦 + 怎么办）。
3. 路径判定工具链：tilde 展开 + cwd 解析 + win32 折叠 + 边界正则——门禁的「代码路径匹配」复用同一套路径规范化即可。
4. 审计模式：recordProtectedBlockTrace 的「追加写一行带 ISO 时间戳的结构化标记、失败不影响拦截」正是 AC-003 mini 审计与 PM watch 可见性需要的形态（标记改 `[GATE]`，并去掉仅 worker 模式限制，见 Q4-6）。
5. handler 内可读项目文件的先例：pm-state-guard.ts:117-124 在 tool_call handler 里 readFileSync 读 pm-state.md 现值做内容级判定 → 门禁在 handler 里只读 `_index.parallel` 判 active key 无技术障碍（P-002「只读判定」约束天然满足）。
6. 注释即文档的纪律：模块头 incident 复盘、每个正则的误伤/漏拦边界注释、镜像 core 常量而非 import（bundle 约束）——门禁模块应同规格。

### Q4. 缺口与局限（门禁必须补）

1. 测试只测纯函数，未测注册接线：vitest 11 例全部针对 5 个纯函数导出（describe 见 test 文件 :25/:34/:41/:62/:125——resolveAgentDir / protectedConfigPaths / isProtectedConfigPath / checkProtectedBashCommand / recordProtectedBlockTrace），没有任何测试构造 mock pi 或经真实工具调用层验证 `registerProtectedConfigGuard` 对 `event.input.path` / `event.input.command` 的取值与 block 返回。接线对工具 input schema 的耦合（字段改名则纯函数测试仍绿而守卫失效）恰是 ue-toolchain 教训（spec §5：「守卫测试必须在真实工具调用层验证，不能只测纯函数」）——AC-006 指定 test/suite/ + harness + faux provider 正是补此缺口。（补注：本调研的活体探测经真实 tool_call 层实证了注册接线在当前版本有效——见 Q4-4；但不替代自动化回归。）
2. Python 侧纯 advisory，零生产调用点：`assert_not_protected_agent_config` 仅定义（mw_common.py:487）+ 测试引用，无框架写路径真正调它。门禁若需 mw 脚本侧对等约束，不能复制「提供符号不接线」的做法。
3. 政策例外无审计：`ensure_pi_shell_path(fix=True)` 写 settings.json（_write_pi_settings mw_common.py:545-548、ensure_pi_shell_path :577 起），刻意不走 assert，依据仅是 mw_common.py:505-527 的注释（「仅显式用户命令 mw setup / doctor --fix、普通终端上下文」）——豁免有明示上下文但无审计痕迹。门禁的 mini fast path（AC-003、KDR「mini 须留审计」）必须做成「显式声明 + 必留痕」，不能照抄此例。
4. bash 启发式的误报与漏报（本调研活体实测命中一次误报）：守卫自述「not a sandbox」（:30-33）。实测两类边界——
   - 误报（实测，机制已用对照实验定位）：用 `python -c` 撰写本调研文档时被拦。机制：文档正文引用了 $PI_CODING_AGENT_DIR（带 $ 的拼写）——bash 判定第①步把它展开折叠成 agentDir 绝对路径，构成「保护引用」；同文引用的 `sed -i` / `find -delete/-exec` / `rm` 等词 + 真实写入用的 `open(...,'w')` 构成写结构 → 引用+结构同时命中 → block（理由列出 write verb / sed -i / find -delete/-exec / inline code write）。真实目标只是 .agenticdoc 下的普通文档。对照实验：同一保护引用、无写结构的命令放行；保护引用 + 文档文本里的 `sed -i` 即被拦。启示：凡 payload 内嵌「保护路径拼写 + 写结构词」的合法写操作（写文档、写测试用例）都会误报；门禁若复用此启发式拦 bash 写代码路径，「写代码相关文档」的合法场景会撞同类误报——design 必须定范围（如 write/edit 硬拦 + bash 兜底收窄）。两次被拦均在 trace.log 留下 `[PROTECTED_CONFIG]` 行（本会话即 worker 模式，实时可观测）。
   - 漏报（代码走查）：`pathlib` 的 `write_text` / `write_bytes`、`[IO.File]::WriteAllText` 不在内联写标记表（:174 只列 quoted w/a、writefile/write_file、unlink、rmsync、rmtree、os.remove/os.rename、shutil.move/copy、truncate(、appendfile、`open(...,'w')`）；预写脚本文件执行（`python x.py`——INLINE_CODE_RE :172 只匹配 -c/-e/--eval/heredoc）、base64 解码管道、`perl -i` / `awk -i inplace` / `gsed` 亦不覆盖。
5. 覆盖依赖扩展安装与 bundle 新鲜度：守卫只活在 agent-team-loop 内——vanilla pi 窗口 / 未装扩展的其他项目无保护；生效条件是 `mw setup --build` 重建 dist + 重启窗口（mini-spec Result 节），旧 bundle 进程在重建后仍无守卫直到重启。门禁有同样的部署生效面，验收与 CHANGELOG 需如实声明。
6. 审计仅 worker 模式落盘：`[PROTECTED_CONFIG]` 行仅 `PI_WORKER_TASK` 存在时写；PM / 交互窗口的 block 只有返回给模型的 reason，无持久记录。门禁审计（AC-003）不能依赖 worker env。
7. no-override 哲学需按门禁目的调整：P-002「无任何 agent 侧覆盖」对凭据文件正确（不存在合法的会话内修改场景）；门禁必须有带审计的 mini 出口（spec §2.3「不能静默放行」），即「fail-closed 判定 + 显式声明式豁免 + 豁免即留痕」三件套，而非照搬 no-override。

## 结论 → 可复用模式与缺口

可复用模式（design 直接采纳）：`shared/` 守卫模块（纯判定 + register 分离导出）→ index.ts activate() 双加载 flag 后、模式分支前注册 → `tool_call` 对 write/edit 返回 `{block, reason}`，reason 内嵌「为什么拦 + 建 key / mini 指引」→ 追加写审计行（ISO 时间戳 + 结构化标记，失败不影响拦截）→ 判定只读文件系统（门禁读 `_index.parallel`）→ 路径判定复用 tilde/cwd/win32 折叠 + 边界正则。拦截原语经 core 源码 + P-002 落地 + 本调研活体探测三重证实，spec §4 风险第一条关闭。

缺口（design 必须补）：① 测试走真实工具调用层（AC-006 的 harness + faux provider；P-002 的纯函数测试是反面教材）；② 审计不能仅 worker 模式；③ mini fast path 须「显式声明 + 必留痕」，不学 no-override 也不学 shellPath 例外的无审计豁免；④ bash 写代码路径是否入范围需 design 定案——启发式有实测误报（保护路径拼写 + 写结构词即可触发）与已知漏报（write_text / 预写脚本 / perl -i 等），若复用须收窄或接受「write/edit 硬拦 + bash 启发式兜底」的分层；⑤ Python 侧若要约束须真接线调用点，不能只提供符号；⑥ 部署生效面（build + 重启窗口）在验收与 CHANGELOG 如实声明。