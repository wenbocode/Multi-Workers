# RQ3 — 窗口 `/mw decide sign` 的 TS 面与测试面

> 只读研究。全部断言带 `path:line`；实测命令与输出见 §2.5 / §7。所有行号取当前工作树
> （`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 为未提交状态，行号以磁盘为准）。

## 0 摘要

1. `runMwDecideCommand` 共 14 个出口；删 `hasUI` 门与确认框后，**4 个出口消失**（4821/4864/4879 + 无可执行路径的穷尽守卫不变），另有 1 个出口（成功行 4902）必须**拆成两个**：`exit 0` 不再等于"已签收"。
2. 卡面要求的 write argv `["sign","--key",k,"--auto"]` 在**当前 Python 上不签收**：`--auto` 只把 `signoff: auto` 写进 `.mw/decide.json` 然后 `return 0`（`mw.py:4036-4041`，已实测）。窗口照抄会谎报成功并顺手改项目配置。
3. `decision-signoff.test.ts` **不测** `/mw decide`（它测 `tool_call` 写守卫），文件内没有一条 `hasUI` / `--human-confirmed` 断言；`/mw decide` 的 12 条用例在 `test/suite/decide-command.test.ts`。本报告两处都给映射。
4. `xkey-gate-guard` 结构上拦不到窗口转发：它只订阅 `pi.on("tool_call")`（`xkey-gate-guard.ts:530-560`），而窗口走 `decideMw` → `spawnSync`（`mw-runner.ts:513-533`），不产生 tool_call。改造后**无需放宽**；反而必须保持 sign-final 写守卫不变。
5. `ctx.hasUI` 在 headless 下是 `false`（`types.ts:316` `hasUI: boolean`；`runner.ts:442-444` 返回 `uiContext !== noOpUIContext`），**不是 `undefined`**；`!== true` 与 `!ctx.hasUI` 等价，多出来的只是对"手工构造 ctx 漏字段"的防御。
6. 隐藏坑：print 模式下 `ctx.ui.notify` 是空函数（`runner.ts:235-239` + `runner.ts:686-688`），删掉 `hasUI` 门之后窗口在 `-p` / worker 里**静默执行**。AC-007 若要求可见输出，必须显式决定输出通道（§6.3）。

---

## 1 `runMwDecideCommand` 分支树（每个 `return` 一行）

函数体 `ui-bridge.ts:4793-4907`。

| # | 行 | 条件 | 动作 | 改后命运 |
|---|---|---|---|---|
| 1 | 4800-4803 | `parsed.action === "usage"` | `notify(parsed.error,"warning")`; return | **保留**（文本随 `DECIDE_USAGE` 变，见 §5） |
| 2 | 4809-4812 | `decideForwardArgs(parsed) !== null`（`dp list\|show\|export`、`monitor`） | `await forwardDecideReadOnly(...)`; return | **不动**。不经 `hasUI`、不需要 key，改造与它无关（T12a/AC-017 的封闭 argv 仍是安全边界） |
| 3 | 4817-4820 | 穷尽守卫（非 `show`/`sign`） | `notify(DECIDE_USAGE,"warning")`; return | **保留**（编译期收窄用的 fail-closed，不是活分支） |
| 4 | 4821-4827 | `ctx.hasUI !== true` | notify("需要交互 TUI…","warning"); return | **删除**（AC-007）。注意文案本身也是错的：rpc 有 UI 上下文（`rpc-mode.ts:321-322`），真正被拒的只有 print/json/worker |
| 5 | 4829-4832 | key 解析不出来 | notify(`${DECIDE_USAGE} — 无法确定 key…`); return | **保留**，措辞收紧为"--key 必需"：窗口恒传 `--project=<repo root>`（§2.4），Python 在这种情况下**拒绝猜 key**（`mw.py:3745-3747`） |
| 6 | 4836-4842 | 预览 runner 抛错 | notify("预览失败: …","error"); return | **保留**原样（spawn 级 bug 不外抛） |
| 7 | 4843-4846 | `!preview.ok` | notify("预览失败: …","error"); return | **保留**；语义扩展为"Python exit 2 = facts 读不出来"，与写入面的判据拒绝分开 |
| 8 | 4848-4851 | `parseDecidePreview()` 返回 null | notify("预览输出不是 JSON…"+尾部); return | **保留**（`tailLines` 尾 6 行，`DECIDE_ERROR_TAIL_LINES` :4669） |
| 9 | 4853-4859 | `parsed.action === "show"` | notify(`formatDecidePreview` + "preview only…","info"); return | **保留**；文案改写：删掉 `/mw decide sign <continue\|narrow\|revoke>` 提示（结论不再由调用方给） |
| 10 | 4864-4870 | 该 conclusion 的 `verdicts[c]` 不过 | notify("未通过机器行判据，未弹确认框、零写入…","error"); return | **删除**。新流程里 conclusion 在写入前**未知**（模型给），逐结论前置拒绝不可实现；判据只能由 Python 在写调用里执行（`mw.py:4100-4118`） |
| 11 | 4879-4882 | `ctx.ui.confirm === false` | notify("cancelled, nothing written","info"); return | **删除**（对话框整体移除） |
| 12 | 4890-4896 | 写入 runner 抛错 | notify("…写入失败: …","error"); return | **保留**，去掉 `${parsed.conclusion}` 插值 |
| 13 | 4897-4900 | `!written.ok` | notify("…写入失败: …","error"); return | **保留**；语义扩展为"Python 退出 2"的三类原因：判据拒绝 / `signoff: disable` / 配置非法（`mw.py:4044-4049`、`4104-4118`） |
| 14 | 4902-4907 | 成功（函数尾，隐式返回） | notify(`已签收 … → wrote …`,"info") | **必须拆分**（见 §1.1）：`exit 0` 有三条互斥含义，`written.ok` 不能当"签了"用 |

无 `return` 但会消失/改写的中间步骤：`allowEmpty` 读取（4833）、`writeArgs` 组装（4884-4886）、`facts/sha` 为确认框准备的插值（4872-4873）。

### 1.1 出口 14 为什么必须拆

Python 在**新流程里仍然会有 "exit 0 且什么都没写" 的合法路径**（AC-005：jev 不可用 / `signoff: disable` / 无决策行）。实测（§2.5）输出：

```
signoff=auto but no conclusion available (decide unavailable (.mw/decide.json missing or enabled=false)); ...
```
exit 0，零写入。现有窗口只判 `written.ok`，会打印"已签收"。新成功分支需要两段：

- 输出匹配 `/^wrote (.+)$/m`（`mw.py:4216` 的行格式）→ `已签收 <key>（conclusion/signed_via 从输出或 `--json` 载荷取）→ <path>`；
- `ok === true` 但无 `wrote` 行（或 `--json` 下 `path === null`）→ `未签收：<Python 的第一行原因>`，级别 `info`，不声称写入。

---

## 2 改造后的 argv 设计

### 2.1 preview（最终字面量）

```ts
// ui-bridge.ts:4730 decidePreviewArgs 改造后
function decidePreviewArgs(key: string): string[] {
	return ["sign", "--key", key, "--dry-run", "--json"];
}
```

实际 spawn（`decideMw` 追加 `--project`）：

```
<python> <mw.py> decide sign --key <key> --dry-run --json --project=<projectDir>
```

`--dry-run` 是**新增的必需项**：现 argv（`ui-bridge.ts:4730-4734`，`["sign","--key",k,"--json"]`）没有它，jev 可用时 `_decide_sign` 会真的走 auto 流并**写 sign-final.md**（`mw.py:4050-4061` → `4066-4081` → `4159+`）。spec §5 的坑点条目与 RQ1/AC-003 指的是同一处。

### 2.2 write（最终字面量）

```ts
// 卡面形态（要求 --auto 不带结论）
const writeArgs = ["sign", "--key", key, "--auto"];

// 建议形态：同语义 + 机器可判「到底写没写」
const writeArgs = ["sign", "--key", key, "--auto", "--json"];
```

实际 spawn：

```
<python> <mw.py> decide sign --key <key> --auto --project=<projectDir>          # 或再带 --json
```

**永不出现**：`--conclusion`、`--human-confirmed`、`--allow-empty`、`--reason`、`--project`。
两个前置条件见 §2.5（P1/P2），不满足时这两个字面量都是错的。

### 2.3 各个 flag 的去留

| flag | 去留 | 依据 / 理由 |
|---|---|---|
| `--key` | **保留，且由"可选"升为"必需"** | 窗口恒以 `--project=<repo root>` 调；`_decide_sign_key` 只在 `project_dir.parent.name == ".agenticdoc"` 时能推断 key，否则 exit 2（`mw.py:3738-3747`）。仍保留 `--key` > `watch.key` 的优先级（`ui-bridge.ts:4828`）与出口 5 |
| `--dry-run` | **新增到 preview** | AC-003；当前 preview 完全没有它（`ui-bridge.ts:4730`）。同时是"preview 绝不写文件"的唯一硬保证 |
| `--json` | **两面都保留** | preview 解析 `facts`/`verdicts`（`ui-bridge.ts:4678-4697`）；write 用它拿 `path`/`conclusion`，避免靠文本猜（`mw.py:4200-4214`） |
| `--auto` | **写入面加**（卡面要求） | 语义 = "本次按 auto 流签"。⚠ 当前实现只在 `--conclusion` 同时存在时继续（§2.5 P1），且会持久化 `signoff`（P2） |
| `--conclusion` | **删** | spec §2 / AC-006：调用方不再提供结论。涉及 `DECIDE_CONCLUSIONS`（4486）、`ParsedDecideArgs`（4503）、`parseDecideArgs` 的结论校验（4613-4620）、`writeArgs`（4884）、成功/失败文案（4866/4892/4898） |
| `--human-confirmed` | **删** | AC-006 / AC-008。它是 `write_signoff` agent-session 拒绝的豁免旗标（`decide_signoff.py:675-691`、`mw.py:3875-3889`），豁免本身要删 |
| `--allow-empty` | **从窗口面删** | verdict 只在 `conclusion == "continue"` 时生效（`mw.py:4106-4108`）。新流程里调用方不知道结论，无条件带它等于允许模型在 N=0 时签 `continue`（正是 `continue` 判据要拦的）。保留为 CLI 人工逃生口由 RQ1 决定 |
| `--reason` | **从窗口面删** | 理由会被 `render()` 写进 `sign-final.md` 的 `reason:` 行（`decide_signoff.py:551-559`），绑在一个模型做出的结论上，是审计误导。CLI 面去留归 RQ1 |
| `--project` | **窗口绝不显式传** | 由 `decideMw` 追加（§2.4）。argparse 取**最后一个**同名选项，窗口再传一个会静默改目标目录 —— `mw-runner.ts:508-511` 对 `stats` 记过同一个坑 |

### 2.4 `decideMw` 自动追加 `--project=<control root>` 的机制

- `mw-runner.ts:513-533` `runMwCliRaw(sub, projectDir, args, timeoutMs, scopeProject = true)`：
  `:522` `const argv = scopeProject ? [mwPy, sub, ...args, \`--project=${projectDir}\`] : [mwPy, sub, ...args];`
- `mw-runner.ts:543-554` `runMwCli` 把上者折成 `{ok, output|error}`（`code 0` 才算 ok）。
- `mw-runner.ts:580-582` `decideMw(projectDir, args) { return runMwCli("decide", projectDir, args); }` —— 未传 `scopeProject`，故**恒为 true**（`statsMw` 是唯一 false 的例子，`:594-596`）。
- 落在 Python：`--project` 决定 key_dir（`mw.py:3745` `decide_signoff.key_dir(project_dir, key)`），`_agenticdoc_root` 兼容 repo 根 / `.agenticdoc` / key 目录三种入参（`decide_signoff.py:138-145`），`control_dir = key_dir.parent.parent`（`mw.py:4024`）才是 `.mw/decide.json` 的所在。窗口的 `projectDir` 就是 repo 根（`pm-orchestrator.ts:2919` `process.cwd()`）。

### 2.5 Python 侧前置依赖（阻塞项，实测）

**P1 — `--auto` 不带结论当前不签收。** `mw.py:4036-4041`：

```python
if mode_flag is not None:
    code = _decide_sign_persist_mode(control_dir, mode_flag, dry_run=dry_run, as_json=as_json)
    if code != 0 or conclusion is None:
        return code          # ← --auto 且无 --conclusion 在此返回
```

实测（临时项目，只有 `.agenticdoc/k-test/`）：

```
$ python packages/multi-workers/mw.py decide sign --key k-test --auto --project <tmp>
signoff: auto (wrote <tmp>/.mw/decide.json)
---exit=0
文件：<tmp>/.mw/decide.json      ← 唯一产物，sign-final.md 不存在
```

结论：卡面 write argv 在**当前代码**上会 (a) 谎报"已签收"，(b) 顺手把项目配置改成 `signoff: auto`。修法二选一：Python 侧让 `--auto` 持久化后**继续**走 auto 流（`4050` 之后不再因 `conclusion is None` 返回）；或窗口改传 `["sign","--key",key]`，把"用什么模式"完全交给 `.mw/decide.json`（与 AC-004 的文字一致）。

**P2 — `--auto` 会覆盖 `signoff: disable`。** `mw.py:4050` `signoff = mode_flag if mode_flag is not None else cfg.signoff`，`3905-3949` 把模式落盘。spec §2 说 `disable` 是"唯一的显式关闭面"，窗口无条件带 `--auto` 会把它复位。要么把 `--auto` 改成"本次强制、不落盘"，要么窗口不带 `--auto`。

**P3 — `--dry-run` 必须在 `auto_conclusion()` 之前短路。** 现在 dry-run 判定在 `mw.py:4131`，而模型调用在 `4066-4081`，因此：

- `--dry-run` **仍会花一次模型调用**并往 `decisions.jsonl` 追加一条 dp25 `kind=decide` 行（`intent="answer"` 同样归档：`decision_points.py:5054-5069`）。argparse help 写的 "write nothing (no archive row either)"（`mw.py:11770-11772`）与实现不符。
- jev 可用时 `--dry-run --json` 打到 `4131-4148`，输出的 JSON **没有 `verdicts`**（只有 `conclusion/ok/problems/facts/path`），窗口的逐结论渲染会静默退化成"reported none"（`ui-bridge.ts:4709-4712`）。

建议插入点（`mw.py:4056-4057` 之后、`if auto_flow and signoff == SIGNOFF_DISABLE` 之前）：

```python
if dry_run:
    return _decide_sign_preview(facts, key, allow_empty, as_json)
```

这样 dry-run 不碰模型、不落盘、恒有 `verdicts`，正是 AC-003 要的形状；同时 `--auto --dry-run --json` 也不会再返回配置 JSON（实测当前返回 `{"path": ".../.mw/decide.json","signoff":"auto","written":false}`，窗口会把它当 facts 全 0 的预览）。

**已实测通过的部分**（jev 未配置 → 走 `_decide_sign_preview`）：

```
$ python .../mw.py decide sign --key k-test --dry-run --json --project <tmp>
{ "conclusion": null, "ok": null, "problems": [], "facts": {...counted_rows: 0...},
  "path": null,
  "verdicts": { "continue": {"ok": false, "problems": ["N=0: no decide row ..."]},
                "narrow": {"ok": true, "problems": []}, "revoke": {"ok": true, "problems": []} } }
---exit=0      ← 目录零新增文件（无 _autopilot/、无 .mw/、无 sign-final.md）
```

即：argv 形状与"零写入 + 带 verdicts"在 jev 不可用路径上成立，缺的只是 jev 可用路径（P3）。

---

## 3 `decision-signoff.test.ts` 用例表

**前提纠正**：该文件（`packages/coding-agent/test/suite/decision-signoff.test.ts`，12 例）覆盖的是 `evidence/review/sign-final.md` 的 **`tool_call` 写守卫**（`xkey-gate-guard.ts` 的 `registerDecisionSignoffGuard`），文件内**没有** `hasUI`、`--human-confirmed`、`runMwDecideCommand` 的任何断言。改造对它的影响只有"允许列表要补上新 argv"与注释去人化，**没有一条需要删除**。

| # | describe / it（原文） | 断言要点 | 判定 | 改写方向 |
|---|---|---|---|---|
| 1 | matcher › `blocks the fixed sign-off name and the table in every spelling` | `isDecisionSignoffPath` 对绝对/相对/`./`/反斜杠/裸 fragment 全 true | **保留** | 无 |
| 2 | matcher › `does NOT hit lookalikes or the advice channel (decision-review-*.md)` | `.bak`/`sign-final2.md`/`decide-points.json.bak`/`""` 全 false | **保留** | 无 |
| 3 | matcher › `refuses both sign-off landing spots on the write channel and keeps deep products writable (FIX-F parity)` | `evidence/sign-final.md` 两个落点 true；`evidence/research/evidence/sign-final.md` false | **保留** | 无（新增 `worker_file` 通道后仍必须保持这条 parity） |
| 4 | matcher › `judges the writeless-role (worker_file) sign-off target ... (QG MAJOR-4)` | `isDecisionSignoffEvidenceTarget` 两落点 true，其余 evidence 产物 false | **保留** | 无 |
| 5 | matcher › `verdicts on bash commands: writes and the table CLI refused, reads allowed` | 10 条写命令 prohibited；13 条读/只读 CLI 放行 | **改写** | `allowed` 增两条：`mw decide sign --key k --auto`、`mw decide sign --key k --dry-run --json`。这是 AC-007 依赖的回归（证明 `TABLE_WRITE_CLI_RE` 的"sign 缺席"仍然成立）。`blocked` 全部保留 |
| 6 | dispatch › `refuses write/edit of sign-final.md and decide-points.json, leaves them byte-identical, and traces each refusal` | 3 次 tool_call 全 block + 文件字节不变 + 3 条 trace | **保留** | 无。语义更强了：文件现在由模型决定写入，agent 手写就是伪造模型结论 |
| 7 | dispatch › `lets the machine-generated decision-review-*.md be written (advice channel)` | 建议通道可写、零 trace | **保留** | 无 |
| 8 | dispatch › `refuses a worker_file write of the fixed sign-off name in both landing spots and lands nothing (QG MAJOR-4)` | 2 次 worker_file block，trace 里含相对/绝对 target | **保留** | 无 |
| 9 | dispatch › `still lets a writeless role write its own evidence products through worker_file (no over-blocking)` | `evidence/review/review-notes.md`、`evidence/research/notes.md` 可写 | **保留** | 无 |
| 10 | dispatch › `refuses a bash write of the sign-off and a `mw decide dp` write command, never executing them` | `echo > sign-final.md`、`mw decide dp off` 双 block，`executedBashCommands === []` | **保留** | 无（`dp on/off/set/apply` 仍是人工权限，spec §4 明确不放开） |
| 11 | dispatch › `keeps reads and read-only dp commands working (no over-blocking)` | read 两条 + `mw decide dp list` 通过且真执行 | **改写** | 追加一条 `bash: mw decide sign --key k --auto`，断言 `prohibited=false` 且进入 `executedBashCommands`（与 #5 互为纯/集成两层） |
| 12 | wiring › `activate() wires the guard into the tool_call path: a dispatched self-signing write is refused and traced` | 真 `activate()` 下 write+bash 双 block、2 条 trace、文件不变 | **保留** | 无 |
| — | 文件头注释 `:1-27` | "the human answer channel" / "a human must not write" | **改写** | 去人化：签收凭据 = "决策模型参与过的证据"，守卫理由 = "agent 不能绕过判据/sha/authority-change 行"，不是"人签" |

### 3.1 真正带 `hasUI` / `--human-confirmed` 的文件（同批必须改）

`packages/coding-agent/test/suite/decide-command.test.ts`（12 例）：

| # | it（原文） | 判定 | 改写方向 |
|---|---|---|---|
| D1 | `accepts the six documented shapes and rejects the four malformed ones` | **改写** | `sign continue --reason … --allow-empty --key k` 变 usage；形状收敛为 `show` / `sign [--key k]` / `dp …` / `monitor` |
| D2 | `hasUI=false notifies a warning and never calls the runner` | **删除** | 反向替换为 AC-007：`hasUI=false` 时 **要** spawn（stub runner 命中两次：preview + write），且 `confirms === []`、argv 不含 `--human-confirmed` |
| D3 | `forwards \`sign --key <k> --json\` and renders the facts without writing` | **改写** | 期望 argv 加 `--dry-run`；其余 facts 渲染断言保留 |
| D4 | `a failing preview verdict notifies the problems, no confirm, no write argv` | **删除** | 逐结论前置拒绝已不存在（§1 出口 10） |
| D5 | `a top-level problems list is honoured the same way (older preview shape)` | **删除** | 同上；旧形状兼容层不要保留 |
| D6 | `cancelling writes nothing and notifies \`cancelled, nothing written\`` | **删除** | 无对话框 |
| D7 | `confirming forwards the exact write argv with --human-confirmed` | **改写** | 改成"无条件转发一次写入 + 无确认框 + 无 `--human-confirmed`"，断言 `calls === [preview, writeArgs]` 且 `writeArgs === ["sign","--key","k","--auto"]` |
| D8 | `the reason/allowEmpty variant keeps the flag order and previews with --allow-empty` | **删除** | 两个 flag 都退出窗口面（§2.3） |
| D9 | `a write failure notifies Python's text at error level and never throws` | **改写** | 错误文本换成 Python 的新词表（判据拒绝 / `signoff: disable` / 配置非法），断言"不抛 + error 级 + 文本透传" |
| D10 | `a preview that is not JSON notifies the raw tail instead of guessing` | **保留** | 无 |
| D11 | `without --key and without a watched key it is a usage error and spawns nothing` | **保留** | 无（措辞可强调 `--key` 现在必需） |
| D12 | `the registered /mw command routes \`decide\` and the usage line documents it` | **改写** | usage 断言改新 `DECIDE_USAGE`；"用 hasUI=false 证路由"的手法失效（现在会 spawn），改为注入 stub runner 或断言 argv 形状；`startsWith("Usage: /mw decide show | sign")` 建议保持不变以减少抖动 |

另有一条隐性断言：`decision-dashboard-command.test.ts:217` `expect(parseDecideArgs("sign narrow --reason x").action).toBe("sign")` —— 结论参数删除后必须改（改成 `parseDecideArgs("sign --key x")`）。

---

## 4 `xkey-gate-guard` 对 `sign-final.md` 的写保护与窗口转发

### 4.1 规则

- 注册：`index.ts:60` `registerDecisionSignoffGuard(pi)`（`index.ts:7` import；紧跟 `registerXkeyGateGuard`（`:51`），全模式生效）。
- 处理器 `xkey-gate-guard.ts:530-560`，**唯一输入是 `pi.on("tool_call")` 事件**：
  - `toolName ∈ {write, edit}` → `event.input.path` → `isDecisionSignoffPath()`（`:391-398`，fragment 命中 `evidence/review/sign-final.md`、`.mw/decide-points.json`，剩余 basename 交给落点规则）；
  - `toolName === "bash"` → `event.input.command` → `checkDecisionSignoffBashCommand()`（`:464-497`）；
  - `toolName === "worker_file"` → `event.input.file` → `isDecisionSignoffEvidenceTarget()`（`:412-430`）。
- bash 的两条独立触发：`refs`（引用了受保护路径）**且**有写构造（重定向/`Set-Content`/`sed -i`/`find -delete`/inline write），或 `TABLE_WRITE_CLI_RE`（`:368` `/\bmw(?:\.py)?\b[^\n;&|]*\bdecide\s+dp\s+(?:on|off|set|apply)\b/i`）。`decide sign` **故意不在**该正则里（`:365-367` 注释：它是 sanctioned writer）。

### 4.2 窗口转发是否被拦

**不会，两重原因**：

1. **结构上不可见**：`registerMwCommands` 的 `decide` 分支（`ui-bridge.ts:5050-5058`）→ `runMwDecideCommand` → `decideMw`（`mw-runner.ts:580-582`）→ `spawnSync`（`mw-runner.ts:523-526`）。整条链路在扩展进程内，**不经过 bash 工具**，所以 `tool_call` 事件根本不产生。模块自己的注释也承认这是应用层守卫而非沙箱（`xkey-gate-guard.ts:331-334`）。
2. **即便 agent 用 bash 跑也一样放行**：命令里没有受保护路径 → `refs` 空；`decide sign` 不匹配 `TABLE_WRITE_CLI_RE` → `cliWrite` false → `prohibited: false`（`:473-476`）。

### 4.3 真正会拦窗口的是另一层（env，而非路径）

`decide_signoff.write_signoff` 用 `AGENT_SESSION_ENV_VARS` 判定"是否在 agent 会话内"（`decide_signoff.py:662-665`、`675-691`），而 `spawnSync` 未传 `env`（`mw-runner.ts:523-526`）→ **继承** worker/PM 的环境变量。这就是 `--human-confirmed` 存在的全部理由：`mw.py:3879-3889` 在写文件期间 pop 这些变量。

→ 改造后这层随 AC-008 一起删除（`signed_via` 词表只剩 `auto-decide`，`AUTO_SIGNED_VIA` 变成单值），窗口不再需要任何豁免旗标。

### 4.4 是否需要同步放宽守卫

**不需要放宽，任何放宽都是错的**：

- `sign-final.md` 的 `write`/`edit`/redirect/`worker_file` 守卫必须原样保留 —— 新流程里文件代表**模型**的结论，agent 手写比"人签时代"更严重（绕过 verdict / `rows_sha256` / authority-change 行）。
- `.mw/decide-points.json` 与 `mw decide dp on|off|set|apply` 继续拦（spec §4 明确不放开授权表）。
- 唯一要改的是**说明文字**：`DECISION_GUARD_EXPLANATION`（`xkey-gate-guard.ts:356-365`）写着 "the auto-* faces from an agent session, the cli/tui faces from a human"，AC-006 后没有 cli/tui 面，也不再需要人在终端；同文件 `:300-303`、`:312-316`、`:365-367`、`:460-463` 的注释同理。这些文本会出现在 block reason 里，属用户可见字符串。

---

## 5 需同步修改的注册与文案字符串

注册面位置：`ui-bridge.ts:4909` `registerMwCommands` / `:4917` `pi.registerCommand("mw", …)` / `:4918` `description: MW_COMMAND_DESCRIPTION`（`:4294-4295`，只是枚举 `… / decide / …`，**不用改**）/ `decide` 分支 `:5050-5058` / 兜底 usage `:5108`。

| 位置 | 现文本（要点） | 处理 |
|---|---|---|
| `:4486` `DECIDE_CONCLUSIONS` | `["continue","narrow","revoke"]` | **删除**（含 `:4484-4485` 注释） |
| `:4491-4493` `DECIDE_USAGE` | `Usage: /mw decide show \| sign <continue\|narrow\|revoke> [--reason <text>] [--allow-empty] [--key <key>]` + 只读行 | **改写**为 `Usage: /mw decide show \| sign [--key <key>]`，第二行（`dp list\|show <id>\|export \| monitor (read-only, no key needed)`）**保持原文**（T12a 测试对它断言，`decision-dashboard-command.test.ts:210-213`） |
| `:4500-4508` `ParsedDecideArgs` | `sign` 变体带 `conclusion/reason/allowEmpty` | 收敛为 `{ action: "sign"; key?: string }` |
| `:4558-4643` `parseDecideArgs` | 结论校验 `:4613-4620`、`--reason/--allow-empty` 解析 `:4621-4640` | 删结论与两个 flag；只留 `--key`（含"flag 无值"拒绝） |
| `:4730-4735` `decidePreviewArgs` | `["sign","--key",k,"--json"]` + 条件 `--allow-empty` | 改为 `["sign","--key",k,"--dry-run","--json"]`，去掉 `allowEmpty` 形参 |
| `:4773-4792` 函数 docstring | 4 条 guard rail，含 "asks ctx.ui.confirm"、"`--human-confirmed`（signed_via: tui）" | 重写为 3 条：只读面先分流 / key 必需 / Python 是唯一判据且窗口永不提供结论 |
| `:4821-4827` | "`/mw decide 需要交互 TUI（headless / -p / rpc 一律拒）…`" | **整段删除** |
| `:4853-4858` show 提示 | `… /mw decide sign <continue\|narrow\|revoke> 才写` | 改为 "`/mw decide sign 触发决策模型判定并写入（无确认框）`" |
| `:4864-4870` 判据拒绝 | `未通过机器行判据，未弹确认框、零写入` | **整段删除** |
| `:4874-4878` confirm | `确认签收 … / 确认后写入 …（signed_via: tui）` | **整段删除** |
| `:4880` | `cancelled, nothing written` | **删除** |
| `:4884-4886` `writeArgs` | `["sign","--key",k,"--conclusion",c,"--human-confirmed"]` + reason/allow-empty | 改为 §2.2 字面量 |
| `:4892` / `:4898` | `mw decide sign ${parsed.conclusion} 写入失败…` | 去掉 conclusion 插值，保留 Python 原文透传 |
| `:4902-4906` 成功提示 | `已签收 <key>（<conclusion>）→ …；… key 目录存在 decision-scope.md 时 …检查现在可以推进` | 按 §1.1 拆两条；`signed_via: auto-decide` 从 Python 输出取；**删掉 `decision-scope.md` 那段**（RQ2 让该标记彻底惰性） |
| `:5050-5058` 注册分支注释 | "`sign` 先预览、asks ctx.ui.confirm and only then writes with the --human-confirmed exemption (recorded as signed_via: tui)" | 重写为"转发 auto 流，无对话框、无豁免旗标" |
| `:5108` 兜底 usage | `… \| decide show\|sign <continue\|narrow\|revoke> [--reason <text>] [--allow-empty] [--key <k>] \| decide dp …` | 改为 `| decide show|sign [--key <k>] |`，其余子命令不动 |
| `mw-runner.ts:572-579` `decideMw` 注释 | "`/mw decide sign` adds the `--human-confirmed` exemption after its own confirm dialog" | 重写为"窗口只转发 `sign [--dry-run\|--auto]`；结论、判据、豁免全在 Python" |
| `xkey-gate-guard.ts:356-365` `DECISION_GUARD_EXPLANATION` | "… the auto-* faces from an agent session, the cli/tui faces from a human …" | 去人化（用户可见，进 block reason） |

跨面（**不在本卡**、避免重复）：Python 侧 help/epilog `mw.py:11726-11746`（描述里仍写 `--conclusion` / `auto-llm` / `cli|tui`）、`11752-11775`（`--conclusion`、`--human-confirmed` 的 help）；文档 `docs/decision-substitution.md:430-444`、`packages/multi-workers/README.md:903-916`（AC-009）。

---

## 6 `ctx.hasUI` 在 headless 下是什么

### 6.1 类型与取值

- `packages/coding-agent/src/core/extensions/types.ts:315-316`：
  `/** Whether dialog-capable UI is available (true in TUI and RPC modes) */` `hasUI: boolean;`
  → **必填 `boolean`，不可为 `undefined`**（另一处同名 `:537` 属 `ProjectTrustContext`）。
- `core/extensions/runner.ts:442-444`：`hasUI(): boolean { return this.uiContext !== noOpUIContext; }`，配合 `:433-435` `setUIContext(uiContext?, mode = "print") { this.uiContext = uiContext ?? noOpUIContext; … }`。
- `runner.ts:683-688`：命令上下文的 `get hasUI()` 就是转发上面这个方法。

各模式实测取值：

| 模式 | 绑定 | `hasUI` |
|---|---|---|
| 交互 TUI | `interactive-mode.ts:1975`、`:2338` `hasUI: true` | `true` |
| RPC | `rpc-mode.ts:321-322` `uiContext: createExtensionUIContext()`、`mode: "rpc"` | `true`（对话框走 JSON 桥） |
| print / `-p` / worker | `print-mode.ts:76-78` `bindExtensions({ mode: "print", … })`，**无 `uiContext`** | `false` |
| JSON 事件流 | 同上，`mode: "json"` | `false` |

### 6.2 `!== true` 的含义

因为类型是必填 `boolean`、运行期由 `!== noOpUIContext` 计算，`ctx.hasUI !== true` **恒等于** `!ctx.hasUI`。它唯一多出来的是"若某个手工构造的 ctx（测试 fake / 旧宿主）给出 `undefined` 也拒绝"的防御性；对本仓库的真实运行路径没有额外语义。

因此该门实际拒绝的集合 = `{print, json, worker}`（**不含 rpc**，`ui-bridge.ts:4823` 的文案把 rpc 列进去是错的）。删掉它不影响任何类型收窄（后面没有任何 `if (ctx.hasUI)` 依赖），只影响 §6.3。

### 6.3 删门后的输出通道缺口（AC-007 的隐含要求）

print/json 模式下 `ctx.ui.notify` 是空实现：`runner.ts:235-239` `noOpUIContext = { …, notify: () => {}, … }`，而 `ctx.ui` 直接返回它（`runner.ts:681-684`）。`ExtensionCommandContext` 另外**没有** `sendMessage`/`print`（`types.ts:356-390`；只有 `ReplacedSessionContext` 有，见 `:397-407`）。

→ 只删 `hasUI` 门，`/mw decide sign` 在 `-p`/worker 里会**静默执行**（文件写了，但没有任何输出）。若 AC-007 要"正常工作"包含可观察结果，必须显式加一条输出通道；最小做法是本地 `emit(ctx, text, level)`：`ctx.ui.notify(...)`，并在 `!ctx.hasUI` 时 `process.stderr.write("[mw decide] …\n")`（**stderr** 而非 stdout，避免污染 `--mode json` 的 stdout 事件流）。仓库内目前无此先例（`grep process.stderr.write` 在 agent-team-loop 下 0 命中）；同类命令（`autopilot/console.ts:660-670`）在 headless 只是"降级为无输出 notify"。这是 AC-007 需要 PM 裁定的一点，不是纯实现细节。

---

## 最小改动面

1. `ui-bridge.ts` `decidePreviewArgs`（:4730）：加 `--dry-run`，去掉 `allowEmpty` 形参。
2. `ui-bridge.ts` `parseDecideArgs`（:4558）/ `ParsedDecideArgs`（:4500）/ `DECIDE_CONCLUSIONS`（:4486）：删结论、`--reason`、`--allow-empty`，留 `--key`。
3. `ui-bridge.ts` `runMwDecideCommand`（:4793）：删 hasUI 门（4821-4827）、逐结论前置拒绝（4864-4870）、confirm 段（4874-4882）；写 argv 改 `["sign","--key",k,"--auto"]`；成功分支按 `wrote`/`path` 拆"已签收 / 未签收"。
4. `ui-bridge.ts` `DECIDE_USAGE`（:4491）+ `/mw` 兜底 usage（:5108）+ `decide` 分支注释（:5050-5058）。
5. `mw-runner.ts` `decideMw` 注释（:572-579）。
6. `xkey-gate-guard.ts` `DECISION_GUARD_EXPLANATION`（:356-365）与 :300-316 注释（守卫逻辑本身不动）。
7. `test/suite/decision-signoff.test.ts` 允许列表 +2 条（:196-224）、文件头注释（:1-27）。
8. `test/suite/decide-command.test.ts`（12 例：删 5、改 4、留 3）+ `decision-dashboard-command.test.ts:217`。

---

## 结论

- 分支面：14 个出口中删 3 个（hasUI 门、逐结论前置拒绝、confirm 取消），成功出口必须拆成"已签收 / 未签收"，因为 Python 在新流程里仍有合法的 `exit 0 零写入`（AC-005）。
- argv：preview = `sign --key <k> --dry-run --json`；write = `sign --key <k> --auto`（可加 `--json`）。`--key` 必需，`--project` 由 `decideMw` 追加（mw-runner.ts:522），其余 flag 全部退出窗口面。
- 但 write argv 在**当前 Python 上不签收**（`--auto` 只落配置就 return），必须与 Python 卡（P1，且 P2 的 `disable` 覆盖问题）一起改；preview 的 `--dry-run` 也必须在 `auto_conclusion()` 之前短路（P3），否则 preview 会调模型、写档案行、且缺 `verdicts`。
- 测试面：`decision-signoff.test.ts` 无一条需删（只补允许列表 + 注释）；真正要删/改的 12 例在 `decide-command.test.ts`。
- 守卫面：`xkey-gate-guard` 拦不到窗口转发（只订阅 tool_call），无需放宽；真正拦窗口的是 `write_signoff` 的 env 判定，随 AC-008 删除。唯一要动的守卫代码是用户可见的说明文字。
- `ctx.hasUI` 是必填 `boolean`，headless 为 `false`；`!== true` 与 `!ctx.hasUI` 等价；删门后 headless 静默（notify 空实现），AC-007 的输出通道需 PM 裁定。

## 证据

- 代码读证：`ui-bridge.ts:4484-4907`、`:4909-4918`、`:5050-5058`、`:5108`；`mw-runner.ts:513-533`、`:543-554`、`:572-582`；`xkey-gate-guard.ts:290-560`；`index.ts:51-60`；`types.ts:310-350`、`:356-390`；`runner.ts:235-239`、`:433-444`、`:676-690`；`print-mode.ts:76-78`；`interactive-mode.ts:1975`、`:2338`；`rpc-mode.ts:321-322`；`mw.py:3729-3747`、`:3852-3889`、`:3892-3949`、`:4032-4051`、`:4056-4081`、`:4100-4153`、`:4159-4218`、`:11726-11775`；`decide_signoff.py:98-103`、`:138-174`、`:287-311`、`:382-442`、`:662-691`；`decision_points.py:5050-5069`。
- 运行实测（§2.5）：`mw.py decide sign --key k-test --dry-run --json --project <tmp>` → exit 0、含三结论 `verdicts`、目录零新增；`… --auto --project <tmp>` → exit 0、只写 `.mw/decide.json`、无 `sign-final.md`；`… --auto --dry-run --json` → 返回配置 JSON（无 facts/verdicts）；`… --key k-test`（无 flag）→ exit 0 + "signoff=auto but no conclusion available"。临时目录已清理。
- 未跑 TypeScript 测试（只读任务，未改代码）。

## 残留与未验证

1. **write argv 的最终形态依赖 Python 卡**：P1（`--auto` 是否继续签名）与 P2（`--auto` 是否允许覆盖 `signoff: disable`）是设计选择，不在 RQ3 权限内。若 P1 不修，窗口必须改用 `["sign","--key",k]`。
2. **nev 可用路径的 preview 未实测**（本机无 jev 凭证）：`--dry-run` 在 jev 可用时"调模型 + 缺 verdicts"是代码读证（`mw.py:4066-4081` → `4131-4148`、`decision_points.py:5054-5069`），未跑真实决策。P3 的修法（dry-run 短路）未验证输出差异。
3. **AC-007 的输出通道未定**：headless notify 为空实现，是否加 stderr 兜底需 PM 裁定；本报告给了最小方案，未改代码。
4. **未验证 `--json` 写入面**（§2.2 建议形态）：`path` 语义依赖 P1 之后 Python 的输出契约，当前 `--auto` 早返回导致拿不到签名载荷。
5. `decision-dashboard-command.test.ts` 只核了 `:217` 一处受结论删除影响的断言，未逐条重审该文件的 20+ 例。

## 上下文来源

- 卡片：`.agenticdoc/mw-signoff-decide-only/tasks/RQ3-tui-surface.md`（task.md 同内容）。
- 设计：`.agenticdoc/mw-signoff-decide-only/spec.md` §2（已定设计）、§3（AC-003/004/005/006/007/008）、§5（坑点）。
- 兄弟卡：`RQ1-signoff-faces.md`（`signed_via` 词表删除面）、`RQ2-gate-structure.md`（门禁无条件化）、`RQ4-archive-scan.md`（档案行判据）。
- 历史：commit `f2f20e922`（jev 决策 + per-key 签收，引入 `--auto`/`--dry-run` 与 auto 流）、`FIX-Q`（引入确认框 + `--human-confirmed`，`docs/decision-substitution.md:430-444`）。

---

勘误：上文 `## 残留与未验证` 第 2 条的「nev 可用路径」应为「jev 可用路径」（该段其余位置均写作 jev）。
