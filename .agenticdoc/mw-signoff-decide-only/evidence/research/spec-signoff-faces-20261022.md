# RQ1 证据：`signed_via` 词表与签收四张脸的读写面

- date: 2026-10-22
- key: mw-signoff-decide-only
- 任务：`RQ1-signoff-faces`（只读；未改任何源码）
- 扫描面：`packages/multi-workers/**`、`packages/coding-agent/src/**`、`packages/coding-agent/test/suite/**`、`.agents/skills/agentic-task/**`、`docs/**`、`packages/*/README.md`、`packages/*/CHANGELOG.md`；排除 `dist/**`、`*.map`、`node_modules`、`.agenticdoc/**`、`.tmp/**`
- 词表全量命中：15 个文件、134 行、174 处（`rg -l 'signed_via|SIGNED_VIA'` 于上述排除集）

结论先行：`signed_via` **不是门禁输入**，写完就只被"读来源/展示"使用；但 `decision_history.py` 里它是**历史来源分类的唯一人/机判据**，删值不会编译失败，会**改判**已有签收文件的 `source.value`（详见 §分类逻辑）。

## 读写点总表

### 生产者（写这个值）

| path:line | 值 | 角色 | 删除后影响 |
| --- | --- | --- | --- |
| `packages/multi-workers/decide_signoff.py:100` | `AUTO_SIGNED_VIA = ("auto-decide","auto-llm")` | 生产者（词表常量：允许在 agent 会话内写的面） | 收窄为 `("auto-decide",)`：无编译/类型错，`mw.py:3875` 对 `cli/tui/auto-llm` 不再开闸（该分支本身按 AC-008 要删） |
| `packages/multi-workers/decide_signoff.py:103` | `SIGNED_VIA_VALUES = ("auto-decide","auto-llm","cli","tui")` | 生产者（渲染/解析词表；同时被读取方与测试引用） | 收窄后不报错；`decision_history.py:2149` 开始对**旧文件**发 `unknown signed_via` 告警（见分类逻辑） |
| `packages/multi-workers/decide_signoff.py:523` + `:568-569` | `render(signed_via=...)` → 第 0 列 `signed_via: <值>` 行 | 生产者（最终落盘行） | `render()` **不校验词表**（无断言、无白名单，`:568` 只判真值），删词表不改变其行为：仍可写出任意字符串 → 属"静默降级"面 |
| `packages/multi-workers/decide_signoff.py:671` | `write_signoff(..., signed_via=...)` | 消费者（仅 `:685` 判别用，不落盘） | 删 `allow_agent_session`/拒绝逻辑后该形参失效（保留则成死参） |
| `packages/multi-workers/mw.py:3835-3849` | `_decide_sign_signed_via(text, signed_via)` 插入 `signed_via:` 行 | 生产者（辅助函数） | **孤儿**：全仓唯一调用点是 `packages/multi-workers/test_decide_signoff.py:681`，生产路径 0 调用 → 可整段删除，只需同步删该测试 |
| `packages/multi-workers/mw.py:4052` | `signed_via = "tui" if human_confirmed else "cli"` | 生产者（默认脸） | AC-006 后必须消除；否则即使词表收窄，`--conclusion` 路径仍写 `cli` |
| `packages/multi-workers/mw.py:4072` | `signed_via = "auto-decide"` | 生产者（jev 面，保留） | 无影响 |
| `packages/multi-workers/mw.py:4077` | `signed_via = "auto-llm"` | 生产者（调用方 LLM 回退面） | 删除点；连带 4 个测试（下文） |
| `packages/multi-workers/mw.py:4128` | `render(..., signed_via=signed_via)` | 生产者（传参） | 传参保留则值集合自然收窄 |
| `packages/multi-workers/mw.py:4164` | `_decide_sign_write(..., signed_via=signed_via)` | 生产者（传参） | 同上 |
| `packages/multi-workers/mw.py:4189` | `note=f"signed_via={signed_via}"`（`authority-change` 档案行） | 生产者（审计列，自由文本） | 全仓**无任何读取方**解析该 note（`rg 'signed_via='` 仅命中生产者与测试断言），删除不影响判定 |
| `packages/multi-workers/mw.py:4221` | `print(f"signed_via: {signed_via}")` | 生产者（stdout，人读） | 展示面，删值后只是不再打印这些值 |
| `packages/multi-workers/test_decide_sign_auto.py:577` / `:584` | `write_signoff(..., signed_via="cli")` / `"auto-llm"` | 测试生产者（断言闸门开口） | 见 §删除面 测试清单 |
| `packages/multi-workers/test_decide_signoff.py:352-358` | `parametrize("signed_via", list(SIGNED_VIA_VALUES))` | 测试生产者（参数化全部面） | 词表收窄后用例数静默变少（仍通过）→ **伪覆盖** |
| `packages/multi-workers/test_decide_signoff.py:374`、`:398/:405`、`:681` | `auto-llm` / `auto-decide` / `tui` | 测试生产者 | `:374`（render 不校验）收窄后仍通过；`:681` 依赖孤儿函数 |
| `packages/multi-workers/test_decision_history.py:311-333` | helper 默认 `signed_via="cli"`，`:331` 用 `AUTO_SIGNED_VIA` 决定 `allow_agent_session` | 测试生产者（造历史签收） | 默认值改不改都能跑；若删 `AUTO_SIGNED_VIA` 则 `:331` AttributeError |
| `packages/multi-workers/test_decision_history.py:818/:838/:867/:871/:1104/:1288/:1314/:1751/:1938` | 直接造 `cli` 签收（含裸写文本） | 测试生产者（遗留值场景） | 这些用例把 `cli` 当**读方输入**用，属于"旧文件"证据 |

### 消费者（读这个值做判断）

| path:line | 值 | 角色 | 删除后影响 |
| --- | --- | --- | --- |
| `packages/multi-workers/decide_signoff.py:684-692` | `hits = agent_session_vars()`；`auto = allow_agent_session and signed_via in AUTO_SIGNED_VIA`；否则 `raise SignoffError` | 消费者（agent 会话写入门） | AC-008 明确删除整段；删后 `write_signoff` 对所有面等价 |
| `packages/multi-workers/mw.py:3875-3878` | `if signed_via in decide_signoff.AUTO_SIGNED_VIA:` → `write_signoff(..., allow_agent_session=True, ...)` | 消费者（选写入通道） | AC-008 后与 `:3880` 合并为一条 `write_signoff(...)` |
| `packages/multi-workers/mw.py:3879-3880` | 非 human_confirmed → 无豁免写 | 消费者（拒绝路径） | 删除 |
| `packages/multi-workers/mw.py:3882-3885` | `--human-confirmed` 时临时 `pop` `AGENT_SESSION_ENV_VARS` | 消费者（旁路） | 删除（连同 `--human-confirmed`） |
| `packages/multi-workers/mw.py:1853-1854` | `_DP_AGENT_ENV_VARS = decide_signoff.AGENT_SESSION_ENV_VARS` | 消费者（**模块级**，`dp apply` 用，`:3221-3227`） | **不能删常量**：`mw.py` 导入即崩（见 §删除面） |
| `packages/multi-workers/decision_history.py:713` | `_CLOSED_SETS["signed_via"] = {"auto-decide","auto-llm","cli","tui"}` | 消费者（**第二份独立词表**：值不合法 → 置 None + `invalid_field`，`:1168-1173`） | 与 `:103` 漂移的源头；删值则旧文件 `signoff.signed_via=None` 与 `source=human` 自相矛盾 |
| `packages/multi-workers/decision_history.py:1704` | `_struct_text(builder.signoff.get("signed_via"), "signed_via")` → `stages["signoff"].detail` | 消费者（受 `:713` 约束的展示字段） | 词表删值后 detail 变 None → `test_decision_history.py:828/:1599/:1602` 断言失败 |
| `packages/multi-workers/decision_history.py:1768-1773` | `signed_via in ("cli","tui")` → `human_basis.append("signoff:signed_via=… (declared)")` | 消费者（**人来源分类**） | 删两个值后成死分支；旧文件 `source` 由 human 改判 system（见分类逻辑） |
| `packages/multi-workers/decision_history.py:1811-1812` | `signed_via in ("auto-decide","auto-llm")` → `system_basis` | 消费者（机来源分类） | `auto-decide` 半边保留；`auto-llm` 半边对旧文件仍有效 |
| `packages/multi-workers/decision_history.py:2148-2150` | `signed_via not in decide_signoff.SIGNED_VIA_VALUES` → warning | 消费者（告警） | 词表收窄后旧文件开始报警（不是失败；`snapshot.warnings`） |
| `packages/multi-workers/decision_history.py:2151-2162` | 写进 `parsed["signed_via"]` → 进 `record.signoff`（`:2055`） | 消费者（载体） | 值原样透传到 dashboard |
| `packages/multi-workers/decision_history.py:1815-1819` | 优先级 human > model > system > unknown | 消费者（最终裁决） | 决定"删 `:1772` 会改判"这一后果的中枢 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4884` | 硬拼 argv `--human-confirmed` | 消费者（窗口转发方，决定产物是 `tui`） | 若 Python 侧先删 flag 而此处不改 → argparse `unrecognized arguments`、exit 2（运行期失败，非类型错误） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4502`（类型）/ `:4614-4642`（解析）/ `:4861/:4866/:4876/:4884/:4892/:4898/:4903`（用 `parsed.conclusion`） | `{action:"sign"; conclusion: string; …}` | 消费者（唯一的类型级耦合面，与 `signed_via` 无关但与 `--conclusion` 同生共死） | 若窗口改成"无结论参数"，`conclusion` 字段删除 → `npm run check` 在这 7 处报类型错 |
| `packages/multi-workers/mw.py:3071` | `_dp_apply_parse` 只认 `(conclusion\|promote\|demote\|p0-open)` | **负证据**：`dp apply` 显式不读 `signed_via` | 无影响（这正是 `test_decide_signoff.py:667` 要钉住的不变量） |
| `packages/multi-workers/mw.py:3116` | `_dp_sign_key` 从**路径**取 key | **负证据**：不读签收内容 | 无影响 |

### 仅展示

| path:line | 值 | 角色 | 删除后影响 |
| --- | --- | --- | --- |
| `packages/multi-workers/decision_dashboard.js:719` | `["signed_via", missing(signoff.signed_via)]` | 仅展示（`missing()` 容 None） | 无影响；词表删值后该行显示为空 |
| `packages/multi-workers/decision_history.py:1958-1960` / `:2055` | 消毒后的 `signoff` 进 record | 展示数据源 | 无影响 |
| `packages/multi-workers/mw.py:4221` | stdout 一行 | 仅展示 | 无影响 |
| `docs/decision-substitution.md:443-445` | 描述 `signed_via: tui`/`cli`、且"不属于机器行词表，done 门禁与 dp apply 都不读" | 文档（结论与代码一致） | AC-009 需改写 |
| `docs/decision-substitution.md:417` | `AGENT_SESSION_ENV_VARS` 单一来源 | 文档 | AC-008/009 需改写 |
| `docs/decision-substitution.md:484-485` | "收尾门禁报…→ 人写签收文件（§5.2），再 dp apply" | 文档（把人写当规范动作） | AC-009 必须改写 |
| `packages/multi-workers/README.md:902-904` | `--human-confirmed` 例外 + `signed_via: tui`/`cli` | 文档 | AC-009 需改写 |
| `packages/multi-workers/README.md:923` | 转发 `… --human-confirmed` | 文档 | AC-009 需改写 |
| `packages/multi-workers/CHANGELOG.md:7`、`:18`；`packages/coding-agent/CHANGELOG.md:11` | history（W9 / FIX-Q 条目） | 文档（已发布/未发布记录） | 按仓库规则不得回改已发布条目；`[Unreleased]` 追加"移除"条目即可 |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4780`、`:4877`、`:5054` | 注释/提示文案 | 注释 | 注释漂移 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:573-580` | 注释解释 `--human-confirmed` | 注释 | 注释漂移 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts:299-310`（`:303`） | 守卫文案："auto-* 由 agent 会话写，cli/tui 由人写" | 注释/拒绝文案 | 文案需改，守卫行为不变 |
| `packages/coding-agent/test/suite/decide-command.test.ts:7-9`、`:111`、`:120`、`:215`、`:247`、`:284-292`、`:321` | 断言窗口 argv 含 `--human-confirmed` | 测试（仅展示/转发契约） | 见 §删除面 |
| `packages/coding-agent/test/suite/decision-signoff.test.ts`（`:5` 注释等） | 只测守卫路径，不读 `signed_via` | 测试 | 无影响 |

## 删除面

### 符号清单与失败类型

| 符号 | 定义 | 全部调用点 | 删除/收窄后的失败类型 |
| --- | --- | --- | --- |
| `decide_signoff.AUTO_SIGNED_VIA` | `decide_signoff.py:100` | 导出 `:57`；`decide_signoff.py:685`、`:690`；`mw.py:3875`；`test_decide_sign_auto.py:777`；`test_decision_history.py:331` | 收窄为 1 值：**无失败**（纯数据）。整体删除：`mw.py:3875` 在调用时 `AttributeError`（不是导入错）；`test_decision_history.py:331` 失败 |
| `decide_signoff.SIGNED_VIA_VALUES` | `:103` | 导出 `:61`；`decision_history.py:2149`；`test_decide_sign_auto.py:778`；`test_decide_signoff.py:352`；`test_decide_cli.py:970` | 收窄：**无失败**，`test_decide_signoff.py:353` 静默少跑参数。删除：`decision_history.py:2149` 在 `load_history` 时 `AttributeError`（整个 history/dashboard 面 500） |
| `decide_signoff.AGENT_SESSION_ENV_VARS` | `:91` | 导出 `:56`；`:662`；`mw.py:1854`（**模块级**）、`:3883`；`test_decide_sign_auto.py:53`；`test_decide_signoff.py:52`；`test_decision_history.py:328`、`:869` | **禁止删除**：`mw.py:1854` 是模块级赋值 → `mw.py` 导入期 `AttributeError`，整个 CLI 全挂（`dp apply` 仍在用 `:3221-3227`） |
| `decide_signoff.agent_session_vars()` | `:660` | 仅 `:684` | 随拒绝逻辑一起成孤儿；删除无失败（`__all__:65` 需同步） |
| `write_signoff(allow_agent_session=...)` | `:671`（形参） | 定义 `:665`；`mw.py:3876-3878`；`test_decision_history.py:332`；`test_decide_sign_auto.py:579-585`；`test_decide_signoff.py:397-406` | 删形参：上述 4 处 `TypeError: unexpected keyword argument`（运行期，非编译期）。按 AC-008 该形参连同拒绝分支一起消失，4 处调用需同时改 |
| `write_signoff(signed_via=...)` | `:671` | `mw.py:3877/3880/3887`；`test_decision_history.py:330/333`；`test_decide_sign_auto.py:577/584`；`test_decide_signoff.py:398/405` | 同上（`TypeError`）；保留则成为只供签名器用的死参 |
| `mw._decide_sign_write` | `mw.py:3852-3887` | `mw.py:4159-4166`；`test_decide_signoff.py:764`、`:769` | 删除：`mw.py:4159` 运行期 `NameError`；2 个测试失败。功能上应收敛为一次 `write_signoff` 调用（AC-008 的"同一路径"） |
| `mw._decide_sign_signed_via` | `mw.py:3835-3849` | **仅** `test_decide_signoff.py:681` | 删除：该测试 `AttributeError`；生产路径零影响（孤儿，已全仓确认） |
| argparse `--conclusion` | `mw.py:11752-11755` | 窗口 `ui-bridge.ts:4884`；文档 `:11738`、README 示例 | 删 flag：`ui-bridge.ts` 仍发 → argparse exit 2（**运行期**，不是类型错）。窗口侧若同时删 `ParsedDecideArgs` 的 `conclusion` 字段（`ui-bridge.ts:4502`），`npm run check` 才会在 `:4861/:4866/:4876/:4884/:4892/:4898/:4903` 报类型错 |
| argparse `--human-confirmed` | `mw.py:11766-11769` | `ui-bridge.ts:4884`；`test_decide_signoff.py:716/:737/:765`；`test_decide_sign_auto.py:169`；`test_decide_signoff.py:132`（fixture args） | 同上：先删 Python 后删 TS 会 exit 2；两边同删则只剩测试失败 |
| `mw.py:4052` 默认 `"tui"/"cli"` | 表达式 | `_decide_sign` | 不删则词表收窄形同虚设（仍会写出 `cli`）→ 属"静默降级 / 假收敛" |
| dist 产物 | `packages/coding-agent/dist/extensions/agent-team-loop/pm/ui-bridge.js:3840`（argv）、`:3835`（文案）、`shared/mw-runner.d.ts:277` | 生成物 | 不改源码则 dist 继续把 `--human-confirmed` 发给 Python；dist 是构建输出，需重新构建，`npm run check` 不覆盖（未验证入库策略） |

### 会失败的测试（逐条，含断言行）

| 测试 | 断言行 | 失败原因 |
| --- | --- | --- |
| `test_decide_sign_auto.py:776` | `:777` `AUTO_SIGNED_VIA == ("auto-decide","auto-llm")`；`:778` `SIGNED_VIA_VALUES == 四值` | 词表断言（AC-006 必须改写） |
| `test_decide_cli.py:969` | `:970-975` 四值元组 | 同上（AC-010 指定套件之一） |
| `test_decide_sign_auto.py:343`、`:361`、`:376`、`:392` | `machines["signed_via"] == "auto-llm"` + `decide_fallback`（`:355-358`、`:371`、`:387`、`:408`） | `auto-llm` 回退被删 → 行为断言失败（AC-005 要求"不产生 auto-llm 回退"） |
| `test_decide_sign_auto.py:413` | `:413-423` 无 jev 无 `--conclusion` → preview | AC-005 语义改变（jev 不可用 → exit 0，但不再有 `--conclusion` 面） |
| `test_decide_sign_auto.py:541` | `:551` `machines["signed_via"] == "cli"` | `cli` 面删除 |
| `test_decide_sign_auto.py:555` | `:573-575` agent 会话内 `--conclusion` 被拒（`SignoffError`） | 拒绝逻辑删除 → 不再抛 |
| `test_decide_sign_auto.py:569` | `:575-578` `allow_agent_session=True + signed_via="cli"` 抛；`:579-585` `auto-llm` 可写 | 两半都随 `AUTO_SIGNED_VIA`/`auto-llm` 消失 |
| `test_decide_signoff.py:699` | `:704-705` 默认 `signed_via: cli`、且不含 `tui` | 默认面改变 |
| `test_decide_signoff.py:708`、`:730`、`:744`、`:759` | `tui` 行 / `--human-confirmed` 豁免 / 唯一豁免 | 豁免删除 |
| `test_decide_signoff.py:667` | `:681` 调 `mw._decide_sign_signed_via(..., "tui")`、`:684`/`:691` 断言 `tui` | 孤儿函数删除（或 `tui` 词表删除后的语义变化） |
| `test_decision_history.py:797` | `:828` `stages["signoff"].detail == "cli"`；`:829` `source == "human"` | 仅当 `_CLOSED_SETS`(`:713`) 与 `:1772` 也删值 → detail=None / 断言失败 |
| `test_decision_history.py:856` | `:881` `by_key["mw-empty"].source.value == "human"`（**唯一**依据是 `signed_via=cli`） | 删 `:1772` 分支 → 落到 `_unknown_basis` |
| `test_decision_history.py:1801` | `:1819` `basis == ["archive.override","signoff:signed_via=cli (declared)"]` | 同上（`:1772` 分支） |
| `test_decision_history.py:1579` | `:1599` detail `auto-decide`；`:1602` detail `auto-llm` | 删 `:713` 的这两个值 → detail=None |
| `packages/coding-agent/test/suite/decide-command.test.ts:284` | `:292` argv 全等（含 `--human-confirmed`）、`:120`/`:215`/`:247` 计数 | 窗口 argv 契约改变（AC-007 要反向重写） |

### 静默降级（不报错、值不再出现但代码仍接受）

1. `decide_signoff.render()`（`:568`）对 `signed_via` 不做任何校验 → 任何调用方仍可写 `signed_via: cli`，词表收窄不设防。
2. `test_decide_signoff.py:352-360` 的参数化会随 `SIGNED_VIA_VALUES` 收缩而"少测但不红"。
3. `test_decide_signoff.py:365-378` 用 `signed_via="auto-llm"` 渲 `decide_fallback`，与词表无关 → 删值后继续通过。
4. `decision_history.py` 与 `decide_signoff.py` 是**两份独立词表**（`:713` vs `:103`）：只改一份即产生"读方接受、写方不再产生"或"写方留下、读方判非法"的漂移，两种都不会编译失败。
5. `mw.py:4189` 的 `note="signed_via=…"` 是自由文本档案列，删值后历史行仍带旧值，无读取方。
6. `ui-bridge.ts`/`mw-runner.ts`/`xkey-gate-guard.ts` 里的 `signed_via` 全在注释与提示文案里 → 不随 Python 改变而报错，只会文档漂移。
7. `decision_dashboard.js:719` 用 `missing()` 容 None → 词表删值后只是显示为空。

## 分类逻辑

`decision_history.py` 的裁决链（`_claims`，`:1750-1829`）：

- 人：`:1768-1773`，输入是 `builder.signoff`（**原始** `parse_signoff` 结果，不是消毒后的 record，`:1769-1771`）
- 机（模型）：`:1776-1802`（archive `available=true` 的 transport/model、`ledger.call-end`、lifecycle `answer_source`）
- 机（系统）：`:1805-1813`，其中 `:1807-1810` 把任意 `archive.authority-change.by=signoff:*` 记为 system；`:1811-1812` 把 `signed_via in ("auto-decide","auto-llm")` 记为 system
- 优先级：`:1815-1819` `human > model > system > unknown`

删除 `cli|tui` 后会出现两个**不同层面**的后果，必须分开决策：

1. **写方**（`decide_signoff.py:103`、`mw.py:4052`）收窄到 `("auto-decide",)`：新文件不再产生 `cli/tui/auto-llm`，`:1772`/`:1811` 对新文件不可达。**不需要新分支**。
2. **读方**（`decision_history.py:713`、`:1772`、`:1811`、`:2149`）若同步删值：磁盘上**已有**的 `sign-final.md` 不会被重写（`write_signoff` 只在 `mw decide sign` 时整文件替换，无迁移逻辑），于是：
   - `:1772` 删掉 → 旧人签文件的 `human_basis` 为空；`:1807-1810` 的 `signoff:*` 档案行把它改判成 `system`（`test_decision_history.py:828-829`、`:881`、`:1819` 会失败）。这不是"自然退化"，而是**语义翻转**（人签被读成机器签）。
   - `:713` 删掉 → `_sanitize_carrier`（`:1168-1173`）把旧值置 `None` 并记 `invalid_field`，但 `:1769-1771` 仍读原始值 → 同一条 record 出现 `signoff.signed_via=None` 且 `source=human` 的自相矛盾；同时 `:1704` 的 `stages["signoff"].detail` 变 None（`test_decision_history.py:828/:1599/:1602` 失败）。

**建议（不改语义的最小方案，无需新分支）**：把词表拆成"写方 / 读方"两层，而不是在一个常量里删值。

- 写方：`SIGNED_VIA_VALUES = ("auto-decide",)`（`:103`）+ `AUTO_SIGNED_VIA` 随 AC-008 一起消失（`:100` 与 `:685`）。
- 读方：`decision_history.py:713` 保留四值（或改成显式 `LEGACY_SIGNED_VIA = ("auto-llm","cli","tui")` 并注释"只读遗留值，写方不再产生"）；`:2149` 的告警判据同样基于"写方词表"，对遗留值不告警。
- `:1772` 与 `:1811-1812` 分支**保留**：它们是历史归档的唯一来源判据，属读者能力，不是待删的脸。
- 若产品上要求"旧人签也不该算人"：那是一次**显式语义变更**，需同时改 `:1772`、`:713`、`:2149`，并重写 `test_decision_history.py:828-829`、`:881`、`:1819`、`:1599-1602`，同时在 spec 里写明"历史人签降级为 system"。不是技术必需。

另：`decision_history.py:2149` 判据用的是 `decide_signoff.SIGNED_VIA_VALUES`（写方常量），`decision_history.py:713` 却是自己的字面量 —— 这两处的**唯一真源**问题在本次改造中应一并解决（否则同一次提交里很容易只改一处）。

## 结论

1. `signed_via` 对 `done` 门禁**零影响**：`advance_phase.py` 全文 0 次命中 `signed_via`（11 份副本同样 0），门禁只读 `conclusion:`/`counted_rows:`/`rows_sha256:` + `collect()` 重算 + `verdict()`（`advance_phase.py:39-41`、`:105-131`、`:271-340`）。
2. `mw decide dp apply` 也**不读**它：`_dp_apply_parse` 只认 4 个键（`mw.py:3071`）。
3. 因此它是**审计 + 来源分类字段**，唯一"做判断"的读点是 `decision_history.py:1772`（人）/`:1811`（机）——而那是事后报告，不是门禁。
4. 删除 `auto-llm|cli|tui` 不会产生任何编译/类型失败；Python 侧只有"运行期 `AttributeError`/`TypeError`"风险，全部来自**连带删除**（`AGENT_SESSION_ENV_VARS` 模块级、`write_signoff` 关键字、孤儿 `_decide_sign_signed_via`）。
5. 唯一的类型级失败面在窗口：删 `--conclusion` 后 `ParsedDecideArgs.conclusion`（`ui-bridge.ts:4502`）的 7 个使用点。
6. 两类"半死"风险：`render()` 不校验词表（静默仍可写旧值）；`decision_history` 有第二份词表（删一处即漂移）。
7. 建议：写方收窄到 `auto-decide`，读方保留遗留值；否则 3 个既有历史来源测试与 1 个"仅凭 cli 判 human"的测试会翻红，且历史人签被重读成 system。

## 证据

- 词表全量扫描（可复现）：
  - `rg -n 'signed_via|SIGNED_VIA' -g '!**/dist/**' -g '!**/*.map' -g '!**/node_modules/**' -g '!.agenticdoc/**' -g '!**/.tmp/**' --stats` → 174 matches / 134 lines / 15 files
  - 文件清单：`decide_signoff.py`、`mw.py`、`decision_history.py`、`decision_dashboard.js`、`ui-bridge.ts`、`mw-runner.ts`、`xkey-gate-guard.ts`、4 个 py 测试、`decide-command.test.ts`、`docs/decision-substitution.md`、2 个 README/CHANGELOG
- 门禁不读的负证据：`rg -c 'signed_via' .agents/skills/agentic-task/scripts/advance_phase.py` → 0；`Get-ChildItem -Recurse -Filter advance_phase.py` 的 11 份副本逐个计数均为 0
- 门禁实际输入：`advance_phase.py:37-41`（三个正则）、`:105-131`（`GATES["done"]` 三条签收规则）、`:271-340`（`_decision_signoff_problems` 只读 conclusion/counted_rows/rows_sha256 + `collect`/`verdict`）
- `dp apply` 不读：`mw.py:3058-3111`（`_dp_apply_parse`）、`:3071`（键白名单）
- 两份词表：`decide_signoff.py:100/:103` vs `decision_history.py:713`；告警判据 `decision_history.py:2149`
- 分类：`decision_history.py:1768-1773`（human）、`:1805-1813`（system）、`:1815-1819`（优先级）；原始值读取 `:1769-1771`；消毒在 `:1958-1960`
- 孤儿函数：`mw.py:3835` 定义，`rg '_decide_sign_signed_via'` 仅 `test_decide_signoff.py:681` 一处调用
- 窗口 argv：`ui-bridge.ts:4884`；类型：`:4502`；hasUI 拒绝：`:4821-4826`；preview argv：`:4730`；命令注册：`:5054-5059`
- 展示：`decision_dashboard.js:719`
- 本次未运行任何测试（只读任务、零代码改动）；上述失败预测来自逐条断言行阅读，属**静态推断**

## 残留与未验证

- **未执行** pytest/vitest：失败清单是断言级推断，不是实跑结果；实际红/绿需在实施阶段以 AC-010 的四套件验证。
- 未验证 `packages/coding-agent/dist/**` 是否被 CI 视为构建产物（是否需要在本次改动中重建/提交）；只确认 dist 里仍是旧 argv（`ui-bridge.js:3840`）。
- 未审计 `decision_dashboard_*.py` 测试是否对 `signoff.signed_via` 有夹具断言（`rg signed_via` 在这些文件 0 命中，故推断无），未逐文件通读。
- 未验证仓外消费者（其他项目/脚本）是否解析 `sign-final.md` 的 `signed_via` 行；仓库内已确认无。
- `.agenticdoc/**` 下的历史 key 记录也含该词，属归档数据，不在本次代码面内。
- `mw.py:1854` 模块级依赖的"导入即崩"结论基于 Python 语义与代码顺序（`decide_signoff` 在 `mw.py` 顶层 import），未实跑验证。
- 未验证 `decision_history.py:2149` 新增告警是否会让某个上游把 `snapshot.warnings` 当失败（只确认现有测试无"告警必须为空"的断言）。

## 上下文来源

- 任务卡：`.agenticdoc/mw-signoff-decide-only/workers/sdo-rq1-faces/task.md`、`.agenticdoc/mw-signoff-decide-only/tasks/RQ1-signoff-faces.md`（`card_sha256` 已由派发段钉住）
- 本 key 规格：`.agenticdoc/mw-signoff-decide-only/spec.md`（§2 已定设计、AC-001..AC-010，尤其 AC-005/AC-006/AC-008）
- PM 基线证据：`.agenticdoc/mw-signoff-decide-only/evidence/research/spec-scope-20261022.md`（四张脸分流点、preview 即写入缺陷、现存三份签收全为 `auto-decide`）
- 项目目标：`.agenticdoc/goal.md`（中低风险决策交给决策模型，而不是人）
- 源码：`packages/multi-workers/{decide_signoff.py,mw.py,decision_history.py,decision_dashboard.js}`、`packages/coding-agent/src/extensions/agent-team-loop/{pm/ui-bridge.ts,shared/mw-runner.ts,shared/xkey-gate-guard.ts}`、`.agents/skills/agentic-task/scripts/advance_phase.py`
- 测试：`packages/multi-workers/test_{decide_sign_auto,decide_signoff,decide_cli,decision_history}.py`、`packages/coding-agent/test/suite/{decide-command,decision-signoff}.test.ts`
- 文档：`docs/decision-substitution.md`、`packages/multi-workers/README.md`、两个包 `CHANGELOG.md`
