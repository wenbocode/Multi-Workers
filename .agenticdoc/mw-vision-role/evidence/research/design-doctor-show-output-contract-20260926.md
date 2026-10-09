# RQ-D1: `mw model show` / `mw doctor` 派发行的 `images=` 能力列字节契约

## TL;DR
- `mw model show` **无 `--json`**（`mw.py:5137-5138` 只注册 `--project`），唯一输出面是 stdout 文本；每角色行两种形态（`mw.py:3222` / `mw.py:3234`）。
- 能力列数据必须先进 doctor 的 **JSON `dispatch` 段**：TS 渲染器只读 `report.dispatch`（`pm/ui-bridge.ts:1756`），拿不到 Python 文本；故 `_doctor_dispatch`（`mw_common.py:1256-1273`）是唯一真源，TS 侧需同步 3 处（`DoctorJson` 类型、渲染、fixture 可选字段）。
- 现有断言除 1 条外全是子串/键访问：内联列 `role=value images=<v>` 会打破 `agent-team-loop.test.ts:5029-5031`（1 条测试语料重冻）；行尾追加分组子句可零改断言（见结论 B）。
- 精确断点：`test_dispatch_models.py:473` 是 `== {"exists": False}` 字典精确相等——缺 `dispatch.yml` 时不得新增任何键（早退分支 `mw_common.py:1266-1267`）。
- AC-010 自相矛盾：`images=no` 若进 `summary.issues`，退出码必为 1（`mw_common.py:2186` → `mw.py:532`），与「三种情形退出码均为 0」冲突；只能落 `suggestions`（`mw_common.py:2123-2127` 有同族先例）或仅渲染在 `dispatch:` 行内。

## 决策问题
1. `mw model show` / `mw doctor` 现有字节格式与机器输出面各是什么？
2. 能力列的最小插入点在哪；哪些测试会红，是精确相等还是子串？
3. 「假 pi 探针」在现有 hermetic 范式下能否注入？
4. 这些文本面是否会被 PM agent 读到？

## 调研方法与出处
只读静态阅读 + 无副作用命令（byte-repr dump、grep/Select-String）：`packages/multi-workers/{mw.py,mw_common.py,test_dispatch_models.py,test_serve_doctor.py,test_doctor_autopilot.py}`、`packages/coding-agent/src/extensions/agent-team-loop/{pm/ui-bridge.ts,shared/mw-runner.ts}`、`packages/coding-agent/{test/extensions/agent-team-loop.test.ts,test/suite/rag-window.test.ts,src/modes/interactive/interactive-mode.ts,src/modes/rpc/rpc-mode.ts,src/core/extensions/runner.ts}`、`.agenticdoc/mw-vision-role/spec.md`。未跑 LLM/网络调用，未改源码/测试。

## 发现

### Q1 `mw model show` 逐字符格式（`mw.py:3136 cmd_model`，show 分支 `:3210-3235`，argparse `:5137-5138`）
- 头部：`config: {path}`；文件不存在时追加 ` (missing — nothing configured)`（`—`=U+2014，`:3213`）。
- `window model: {window or '(none recorded)'}`（`:3218`）。
- 已配置角色行：`{role}: {configured}`（`:3222`，无空格/无括号）。
- 未配置角色行：`{role}: (unset) → {effective} [{source}]`（`:3234`，`→`=U+2192）。
  - `effective = value or "(route default: glm-5.3 for pi+timi, gpt-5.6-sol for codex)"`（`:3233`，唯一硬编码兜底串）。
  - 此处 `entry_model=""`、`config_models={}`，故 `source` 只可能为 `window` 或 `default`（`mw_common.py:303-311`）；`main` 用 `task_type="coding"` 预览（`:3228`）。
- 机器输出面：**无**。`model show` 只有 `--project`，无 `--json` 分支/无 JSON 序列化；TS `/mw model show` 仅把 stdout 原样 `ctx.ui.notify`（`ui-bridge.ts:1980-1984`），无结构性承诺。

### Q2 doctor dispatch 段的 4 个输出面（原文）
1. JSON 段（真源）：`mw_common.py:1265-1273` 返回 `{"exists": bool, "models": {role: value}, "window_model": str, "error": str?}`；缺文件早退 `:1266-1267` 只返回 `{"exists": False}`；挂载 `:2178`；由 `mw.py:525-526` `json.dumps(report, indent=2)` 打印。TS 类型 `shared/mw-runner.ts:380-385`。
2. Python 文本行 `mw_common.py:2298-2308`：`dispatch: {roles}; window model {window}`；`roles = ", ".join(f"{role}={value}" for role,value in sorted(models.items()))`，空则 `"no roles set"`；`window` 空则 `"(none recorded)"`；错误分支 `dispatch: ERROR — {error}`（`:2302`，U+2014）。
3. summary suggestions `mw_common.py:2123-2127`：仅 `if dispatch.get("error")` 时追加 `f"dispatch.yml unusable ({err}) - model defaults are ignored; fix or remove .mw/dispatch.yml"`（注意是 ASCII `-`）；`issues` 中**没有** dispatch 项。
4. TS 文本行 `pm/ui-bridge.ts:1755-1766`：`派发模型: {roles}; 窗口模型 {window}`；`roles = Object.entries(models).map(([r,v]) => `${r}=${v}`).join("; ")`（**未排序**，与 Python `sorted()` 不逐字节对齐，且无 parity 测试锁）；空则 `"未设角色"`、window 空则 `"（未记录）"`；错误分支 `派发模型: 配置错误 — {error}`（`:1759`）。入口 `:2133-2139`（`doctorMw` → `ctx.ui.notify`）。

### Q3 断言清单与插入方案
`mw model show`（唯一调用点 `test_dispatch_models.py:454-464`，全部子串）：
- `:462-463` `assert "review: timi/glm-5.3-air" in out`；`assert "window model: claude/claude-sonnet-5" in out`
- `:464` `assert "coding: (unset)" in out and "[window]" in out`
→ 行尾追加 ` images=<v>` 两条仍命中；插到 `(unset)` 与 `[window]` 之间即打破。

doctor Python 文本（`test_dispatch_models.py:471-495`）：
- `:473` `assert report["dispatch"] == {"exists": False}`（字典精确相等，仅缺文件路径）
- `:475` `assert "dispatch:" not in text`（缺文件必须整行不存在）
- `:484` `assert "dispatch: coding=timi/glm-5.3" in text`（前缀子串，`;` 前必须有内容）
- `:486-495` 只断言 `issues`/`suggestions` 成员关系
doctor TS 文本（`agent-team-loop.test.ts:5013-5037`）：
- `:5024` `not.toContain("派发模型")`（`exists:false` 时整行不出现）
- `:5029-5031` `toContain("派发模型: coding=timi/glm-5.3; 窗口模型 claude/claude-sonnet-5")`（**含 `; ` 接合处的单一子串**；任何插在 `=timi/glm-5.3` 与 `;` 之间的列都会打破）
- `:5036` `toContain("派发模型: 配置错误 — dispatch.yml unreadable: boom")`（错误分支不动）
无 dispatch 行断言：`test_serve_doctor.py:413-436`（只断言 section 名 + `elapsed < 5`）、`:193/:435/:469` 只看 `workers:`/`pi_shell:` 行；`test_doctor_autopilot.py:88/101/116/224`、`test_mw_target.py:304`、`test_partition_dispatch.py:755`、`test_rag_cli.py:448`、`test/suite/rag-window.test.ts:284-390`（真子进程 doctor，只找 `rag: ` 行）均不碰 `dispatch:`。

最小改动方案：
- **A（推荐）内联列**：Python 文本行 roles 段改 `f"{role}={value} images={v}"`；TS 改 `` `${r}=${v} images=${cap}` ``；`mw model show` 行尾追加 ` images={v}`。代价：`agent-team-loop.test.ts:5029-5031` 重冻 1 条字面量（**测试语料重冻**：仅更新渲染期望、不放宽断言，与 spec-role-type-plumbing 记录的 `test_mwpp_collection_parity.py` 重冻同类，PM 点头即可）。
- **B（零改断言）行尾分组子句**：只允许插在 `... window model {window}` **之后**（Python `:2308` / TS `:1765` 行尾）：`; images=yes: <roles>; images=no: <roles>; images=unknown: <roles>`。注意 `; images=coding=yes` 这类写法**不含** AC-015 要求的字面量 `images=yes`。
- 两方案共同前提：`_doctor_dispatch` 只在 `models` 非空且无 `error` 时探测并写字段（守住 `:473`/`:475`/`:5024`）；`shared/mw-runner.ts:380-385` 加可选字段；`formatDoctorReport` 加读取渲染。

### Q4 hermetic 范式与「假 pi 探针」
- `test_serve_doctor.py:29-51` `_HERMETIC_CONFIG`（providers.json 用 `TEST_*` 凭证名）；`:54-56` `_TEST_CRED_VARS`；`:89-91` `no_test_creds` fixture 逐个 `monkeypatch.delenv`；`:95-96` `no_codex` 把 `mw_common.shutil.which` 打成 `None`；`:74-85` `_FakeProc.poll()` 恒 None。
- 两条通路：**in-process**（`mw.subprocess.Popen` monkeypatch，`:220/:240` 等）只覆盖 `cmd_serve`；**doctor 走真子进程**（`TestDoctorCli._run_doctor` `:403-413`），monkeypatch 不跨进程，唯一注入通道是 env（现用 `mw_common.AGENT_DIR_ENV`=`PI_CODING_AGENT_DIR`，`mw_common.py:1148`）。
- 仓库内无「PATH 注入假二进制」先例（全仓测试无 `setenv("PATH")`、无 fake shim；唯一二进制伪造是上面 in-process 的 `shutil.which` monkeypatch）。
- 结论：探针必须做成 `mw_common` 模块级函数（如 `probe_model_images(...) -> "yes"|"no"|None`）才可测。推荐在 **in-process** 用例里 `monkeypatch.setattr(mw_common, "probe_model_images", ...)` 后调 `mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)`（`test_dispatch_models.py:471-495` 已是此形态），一次覆盖 yes/no/skip 三支；真子进程 CLI 用例只能覆盖 skip 支（fixture 未配 `dispatch.yml`）。若要在子进程下覆盖 yes/no，需新增「pi 二进制 env 覆盖」或 PATH 沙箱（**新基础设施，无先例**，须 design 明示）。
- 性能契约：`doctor_report` docstring 承诺 "Local-only checks (no network), <5s"（`mw_common.py:2155-2157`），`test_serve_doctor.py:425` 断言 `elapsed < 5`——探针只在有配置角色时触发且需超时上限。

### Q5 是否进 PM agent 上下文
- **不进**。`/mw model show` 与 `/mw doctor` 走 `ctx.ui.notify`（`ui-bridge.ts:1981`、`:2137`）；interactive 实现 `notify → showExtensionNotify`（`interactive-mode.ts:2332`→`:2631`）只 `chatContainer.addChild(new Text(...))`（`showStatus` `:3380-3402`、`showError` `:4064-4068`、`showWarning` `:4070-4074`），**不写 sessionManager、不产生 conversation entry**。RPC 模式只发带外 `extension_ui_request`（`rpc-mode.ts:152-161`）；无 UI/`-p` 用 `noOpUIContext`（`core/extensions/runner.ts:235-239`）直接丢弃。
- **但可被动进入**：PM agent 用 `bash` 工具执行 `mw.py doctor` / `mw.py model show` 时 stdout 成为 tool result 进上下文；`formatDoctorReport` 全仓唯一消费点是 `ui-bridge.ts:2137`。→ AC-015 的「人可见」成立；「PM 自动感知能力缺口」不成立，须靠 AC-014 prompt 文本或 AC-016 auto-route。

## 结论 → 决策映射
- 插入点（数据流顺序）：`mw_common.py:1265-1273` JSON 段加能力字段 → `mw_common.py:2304-2308` 文本行 → `pm/ui-bridge.ts:1761-1765` TS 行 → `mw.py:3222/3234` show 行。
- 断言策略：默认 A（内联列 + 重冻 `agent-team-loop.test.ts:5029-5031`）；若 PM 要求零改断言则走 B（行尾分组子句，格式须含字面量 `images=yes`）。
- AC-010 退出码：能力不匹配**只能**进 `suggestions`（`mw_common.py:2123-2127` 同族先例）或 `dispatch:` 行内，绝不可进 `issues`（否则 `:2186`/`mw.py:532` 必然退出 1）。需 design 显式裁决。
- 测试：探针做成 `mw_common` 模块级函数 + in-process monkeypatch；子进程 CLI 只覆盖 skip 支；`_doctor_dispatch` 早退分支零新增键。
- 数据缺口：TS `Object.entries`（`ui-bridge.ts:1761`）与 Python `sorted()`（`mw_common.py:2305`）顺序不一致、且无 parity 测试锁；若要求两侧 dispatch 行逐字节一致须先修顺序（可另开）。

[VERIFY] `mw model show` 子解析器只注册 `--project`（`mw.py:5137-5138`），全仓无 model 子命令 `--json` 分支；唯一输出是 `print()` 文本
[VERIFY] `test_dispatch_models.py:473` 为 `assert report["dispatch"] == {"exists": False}`（字典精确相等），且 `_doctor_dispatch` 缺文件时在 `mw_common.py:1266-1267` 早退返回该单键字典
[VERIFY] `agent-team-loop.test.ts:5029-5031` 断言含接合处 `"...=timi/glm-5.3; 窗口模型 ..."` 的单一子串，任何前置列插入都会使其变红
[VERIFY] `ctx.ui.notify` 在 interactive 下只 addChild 到 `chatContainer`（`interactive-mode.ts:2631`、`:3380-3402`、`:4064-4074`）不写 session；RPC 走 `extension_ui_request`（`rpc-mode.ts:152-161`）
[VERIFY] doctor 退出码由 `report["summary"]["healthy"]` 决定（`mw_common.py:2186`、`mw.py:532`），而 `_doctor_issues` 的 dispatch 分支只产 suggestion（`mw_common.py:2123-2127`）