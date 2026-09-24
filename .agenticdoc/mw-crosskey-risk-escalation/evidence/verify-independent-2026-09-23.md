# T-3 独立验证报告：mw-crosskey-risk-escalation（VC-001~004 复现 + 3 变异反例）

> 日期: 2026-09-23
> 执行者: worker `mwcre-t3-verify`（type: coding）
> 任务书: `tasks/T-3-VERIFY.md`；上游 spec AC-001~004 / design D-101~D-104、§7 VC 表
> 对照材料（未采信其断言，仅事后对照）: `workers/mwcre-t1-crosskey-escalation/output.md`

## 0. 结论（先行）

**0 FAIL。** 四个验收用例（VC-001~004）全部独立复现通过；三个变异反例（M-1/M-2/M-3）全部"改坏即红 → 整文件复原 → sha256 逐字节相同 → 复绿"；两条回归命令 0 failed / EXIT=0；`git status --short` 起止逐行相同（零残留）。

汇总 `[VERIFY]` 行（均为本报告 §2~§5 中命令原始输出的逐字摘录）：

```
[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0
[VERIFY] VC-002: undefined_alerts=0 empty_set_alerts=0
[VERIFY] VC-003: low_alerts=0 high_alerts=1 dup=0
[VERIFY] VC-004: watched_key_alerts=1 trigger_turn=true dup=0
[VERIFY] VC-004: head_alerts=1 current_alerts=1 text_byte_identical=true head_sha256=f2da612a675035d99a47a07cf3fcc9aee38bffc282ae6a2bf79c9e4fd221c362 current_sha256=f2da612a675035d99a47a07cf3fcc9aee38bffc282ae6a2bf79c9e4fd221c362
[VERIFY] M-1: H0=C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3 Hmut=F627A516C8681B7B2F66B91559585ABC227FC5E4C766CAF1A2355E90FE9BB656 red(vc001 alerts=0) H1==H0=true green(alerts=1)
[VERIFY] M-2: H0=C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3 Hmut=57F0E5699168C0FE3C4676FC50D9D301C0ECEFDECB09E653A4AC378072C1C9FA red(vc002 undefined=1 empty=1; existing-case 1 failed) H1==H0=true green(0/0; existing-case 1 passed)
[VERIFY] M-3: H0=C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3 Hmut=EF9F5ECADA88C919657DBB7D7082E88213C4340ADAE0A14AF906A53A4AF2175D red(vc002 undefined=1 empty=0) H1==H0=true green(0/0)
[VERIFY] REGRESSION: vitest 2 files 183 passed 0 failed EXIT=0; npm run check EXIT=0; git_status_start==git_status_end
```

## 1. 验证环境与独立性声明

| 项 | 值 |
|----|----|
| HEAD commit | `6254783b697a3cf2e031523fb41dc8c25b209968` |
| 被测文件（工作区，T-1 改造后） | `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`，39440 bytes，sha256 `C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3`（下称 **H0**，整个会话的复原锚点） |
| 改造前模板来源 | `git show HEAD:…/pm-orchestrator.ts`，38540 bytes，sha256 `F89F60C94BB56CA6B6945B520FBE94AF2944A87FC673CAA9ADFDE87260E5D357` |
| Node | v24.19.0（原生 type stripping，探针直接 import 仓库 `.ts` 源码，无构建步骤） |
| 探针位置 | 系统临时目录 `%TEMP%\mwcre-t3-verify\`（清单见 §7；仓库内零新增代码文件） |

独立性声明（对照任务书 §1"不复用 T-1 的断言结论"）：

1. 探针为本次新写（`probe.mts`），**不 import 任何测试套件代码**（不依赖 `agent-team-loop.test.ts` 的 `fakePi`/`queueRunning`/`mkdtemp`），夹具、fake pi、checkpoint 行数值（high: reads=91 writes=0 repeat_top=4；low: reads=12 writes=6）均为本探针自建，与套件夹具不同。
2. 不运行 T-1 新增的 3 个套件用例作为复现依据（它们仅在 §5 回归中作为"既有套件全绿"的整体计数出现）；VC 的 pass/fail 判据直接取自 spec AC-001~004 的文字。
3. T-1 的 output.md 仅在全部测量完成后打开对照，无任何数值预先采信。
4. 定时器策略：**真实定时器**（pollIntervalMs=40，两个 280ms 观察窗，同一 handle 贯穿两窗——去重集合 `escalated` 是 loop 实例内部状态，必须同一 handle 才能检验"第二窗不重复"）。
5. 探针退出码：全部期望成立 → 0；任一不成立 → 1（变异窗口的"红"以退出码 + 失败断言输出为准，非人工判读）。

## 2. VC-001~004 独立复现

命令（基线，变异前）：`node %TEMP%\mwcre-t3-verify\probe.mts all` → **EXIT=0**

### VC-001（AC-001：跨 key 已派发高风险 → 1 条 alert，含 owner key，triggerTurn）

夹具：临时根下 `_index.parallel` 有 `key-a`（active）；`key-b/workers/t-xkey/` running 行 + trace.log 含 `risk=high` checkpoint；`watch = { key: "key-a", dispatchedTaskKeys: new Set(["t-xkey"]) }`。

```
VC-001: cross-key dispatched high-risk worker wakes this window once
  [PASS] exactly 1 alert
  [PASS] alert text contains owner key key-b
  [PASS] alert text contains task name t-xkey
  [PASS] text contains risk=high
  [PASS] text contains reads= and writes=
  [PASS] text contains trace.log
  [PASS] text contains progress.md
  [PASS] triggerTurn=true on the alert
  [PASS] second window adds no duplicate
  [info] D-102 label 't-xkey'（owner key=key-b） present: true
[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0 pass=true
```

### VC-002（AC-002：跨 key 未派发 → 0 条；undefined 与空 Set 两形态）

夹具：同 VC-001 结构，task 为 `t-other`（key-b，risk=high），`dispatchedTaskKeys` 分别为不设置 / `new Set()`。

```
VC-002: cross-key workers this window never dispatched stay silent (both forms)
  [PASS] undefined dispatchedTaskKeys form: 0 alerts
  [PASS] empty Set form: 0 alerts
[VERIFY] VC-002: undefined_alerts=0 empty_set_alerts=0 pass=true
```

既有反例用例的独立重跑（任务书 VC-002 要求）：`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts -t "never wake this window"`（基线，变异前）：

```
 Test Files  1 passed (1)
      Tests  1 passed | 175 skipped (176)
```

### VC-003（AC-003：已派发 low 0 条；high 恰 1 条；第二 tick 不重复）

夹具：`key-b` 下 `t-calm`（risk=low）与 `t-alarm`（risk=high）均在 `dispatchedTaskKeys`。

```
VC-003: dispatched cross-key low stays silent; high delivers exactly once
  [PASS] exactly 1 alert total
  [PASS] low-risk dispatched task never delivers
  [PASS] high-risk dispatched task delivers exactly once
  [PASS] second window adds no duplicate
  [PASS] low stays silent through the second window too
[VERIFY] VC-003: low_alerts=0 high_alerts=1 dup=0 pass=true
```

### VC-004（AC-004：watched key 自身高风险 → 1 条、判据字段、triggerTurn、不重复）

夹具：`key-a` 下 `t-own`（risk=high）+ `t-fine`（risk=low），`watch = { key: "key-a" }`（无 dispatchedTaskKeys）。

```
VC-004: watched-key high-risk worker escalates once with unchanged semantics
  [PASS] exactly 1 alert
  [PASS] text contains 发散风险
  [PASS] text contains 't-own'
  [PASS] text contains risk=high
  [PASS] text contains reads=91 writes=0
  [PASS] text contains trace.log
  [PASS] text contains progress.md
  [PASS] low-risk sibling never delivers
  [info] alert bytes=533 sha256=dfde79bd61eb9196f77f8ca14197eb579e9320832fe863c5629351e1d2f8f1ae
  [PASS] triggerTurn=true
  [PASS] second window adds no duplicate
[VERIFY] VC-004: watched_key_alerts=1 trigger_turn=true dup=0 pass=true
```

## 3. VC-004 机械证据：watched key 路径文本逐字节不变

任务书要求：不得以"既有用例全绿"推得文本不变，必须用 `git show HEAD:…` 取改造前模板、与当前模板**在同一夹具下求值**后逐字节比较，且重做并保留脚本与输出。

### 3.1 方法（脚本 `%TEMP%\mwcre-t3-verify\vc004-bytes.mts`，全文见 §7.2）

1. `execFileSync("git", ["show", "HEAD:<orch-path>"], { cwd: repo })` 取改造前源码**原始字节**（Buffer 直读，不经 PowerShell 管道重编码；实测 `git show` 经 PowerShell `>` 重定向会被改写为 UTF-16，本方法绕开）。
2. **机械改写**相对 import 说明符为绝对 `file://` URL（正则 `(from\s+")(\.[^"]+)(")`，仅命中 import 行），写入 `%TEMP%\mwcre-t3-verify\head-pm-orchestrator-rewritten.mts`，然后 `import()` **完整的 HEAD 版 `startWorkerPollLoop`**——求值的是改造前的真实代码路径，不是人工转录的模板字符串。
3. 改写完整性另由 `check-rewrite.mts` 机械核对：rewritten 与 raw HEAD 逐行比较，**仅 17 行差异且全部是 import 说明符行**（行 3~18、46），其余 828 行逐字节相同。
4. 同一夹具（`key-a` watched、`t-own` risk=high、`t-fine` risk=low）先后驱动 HEAD 版 loop 与当前版 loop（各自独立 handle、独立 fake pi，文件零写入），捕获两侧 alert，`Buffer.equals` 逐字节比较。

### 3.2 命令与原始输出（最终态复跑，复原后的当前源码上）

`node %TEMP%\mwcre-t3-verify\vc004-bytes.mts` → **EXIT=0**

```
HEAD commit: 6254783b697a3cf2e031523fb41dc8c25b209968
HEAD packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts: bytes=38540 sha256=f89f60c94bb56ca6b6945b520fbe94af2944a87fc673caa9adfde87260e5d357
rewritten module: C:\Users\WENBOZ~1\AppData\Local\Temp\mwcre-t3-verify\head-pm-orchestrator-rewritten.mts (relative import specifiers rewritten: 17)
HEAD startWorkerPollLoop typeof: function
  [PASS] HEAD loop delivered exactly 1 alert
  [PASS] current loop delivered exactly 1 alert
  [PASS] HEAD low-risk sibling stayed silent
  [PASS] current low-risk sibling stayed silent
  [PASS] HEAD triggerTurn=true
  [PASS] current triggerTurn=true
  [PASS] watched-key alert text byte-identical (HEAD vs current, same fixture)
  [info] HEAD alert:    bytes=533 sha256=f2da612a675035d99a47a07cf3fcc9aee38bffc282ae6a2bf79c9e4fd221c362
  [info] current alert: bytes=533 sha256=f2da612a675035d99a47a07cf3fcc9aee38bffc282ae6a2bf79c9e4fd221c362
  [info] shared alert text: [mw] 发散风险：worker 't-own' 检查点 risk=high（elapsed 30m，reads=91 writes=0，phases=-，重复读 top=4）。机器判据仅供参考——请结合本 key 最全上下文判断：继续等待 / steer 收窄范围 / 终止并分拆重派 / PM 直执。证据：C:\Users\...\mwcre-t3-bx-PmDqvn\key-a\workers\t-own\trace.log（[CHECKPOINT] 行）与 C:\Users\...\mwcre-t3-bx-PmDqvn\key-a\workers\t-own\progress.md（自评行；无写工具角色另含框架机器行）。
[VERIFY] VC-004: head_alerts=1 current_alerts=1 text_byte_identical=true head_sha256=f2da612a675035d99a47a07cf3fcc9aee38bffc282ae6a2bf79c9e4fd221c362 current_sha256=f2da612a675035d99a47a07cf3fcc9aee38bffc282ae6a2bf79c9e4fd221c362 pass=true
```

说明：alert 文本内嵌夹具的绝对路径，故不同运行的绝对 sha256 不同（首轮运行为 `c848fb2b…`，两侧同样相等）；**判定只取同一夹具内 HEAD vs current 的相等性**，两轮运行均 `text_byte_identical=true`。文本中 `'t-own' `（名 + 尾随空格，无 owner 标注）即 D-102 设计的 watched-key 分支字节形态。

### 3.3 既有 2 个 AC-004 用例

包含在 §5 回归的 183 计数内（`-t "AC-004"` 覆盖 "poll loop wakes the PM once on a mid/high checkpoint (triggerTurn)…" 与 "diverging workers owned by other keys never wake this window"），零改动通过；alert 文本包含式断言未动（`git status` 见 §6，测试文件无本任务改动）。

## 4. 变异反例 M-1 / M-2 / M-3

流程（任务书 §4）：`H0` → 变异 → 探针/用例红 → **从备份整文件复原** → `H1 == H0` → 复绿。变异工具 `%TEMP%\mwcre-t3-verify\mutate.mts`（见 §7.3）：apply 前强制校验当前文件 sha == H0（杜绝叠加变异/漂移），替换串在文件中必须**恰出现一次**；restore 为整文件字节复制，随后校验 H1 == H0。

### 4.1 M-1：过滤改回只看 ownerKey（去掉 `owned` 支）

```diff
-				const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;
-				if (!watch.key || (ownerKey !== watch.key && !owned)) continue;
+				if (!watch.key || ownerKey !== watch.key) continue;
```

| 步骤 | 命令 | 输出 |
|------|------|------|
| H0 | `mutate.mts hash` | `C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3` |
| 变异 | `mutate.mts apply M-1` | `Hmut=F627A516C8681B7B2F66B91559585ABC227FC5E4C766CAF1A2355E90FE9BB656` |
| 红 | `probe.mts vc001` | **EXIT=1**：`[FAIL] exactly 1 alert — alerts=0` 等 4 项失败，`[VERIFY] VC-001: alerts=0 owner_in_text=false trigger_turn=false dup=0 pass=false`（异地已派发高风险不再投递） |
| 复原 | `mutate.mts restore` | `restored from backup: sha256=C261B903…`，`H1==H0: true`（EXIT=0） |
| 复绿 | `probe.mts vc001` | **EXIT=0**：`[VERIFY] VC-001: alerts=1 owner_in_text=true trigger_turn=true dup=0 pass=true` |

### 4.2 M-2：去掉 owner 与 owned 过滤（全局广播）

```diff
-				if (!watch.key || (ownerKey !== watch.key && !owned)) continue;
+				if (!watch.key) continue;
```

| 步骤 | 命令 | 输出 |
|------|------|------|
| H0 | 同上 | `C261B903…` |
| 变异 | `mutate.mts apply M-2` | `Hmut=57F0E5699168C0FE3C4676FC50D9D301C0ECEFDECB09E653A4AC378072C1C9FA` |
| 红（探针） | `probe.mts vc002` | **EXIT=1**：`[VERIFY] VC-002: undefined_alerts=1 empty_set_alerts=1 pass=false`（别键/未派发也投递） |
| 红（既有用例） | vitest `-t "never wake this window"` | **1 failed**：`AC-004: diverging workers owned by other keys never wake this window` — `AssertionError: expected [ Array(1) ] to have a length of +0 but got 1`（`Tests 1 failed | 175 skipped`，EXIT=1） |
| 复原 | `mutate.mts restore` | `sha256=C261B903…`，`H1==H0: true` |
| 复绿（探针） | `probe.mts vc002` | **EXIT=0**：`undefined_alerts=0 empty_set_alerts=0 pass=true` |
| 复绿（既有用例） | vitest `-t "never wake this window"` | `1 passed | 175 skipped`（EXIT=0） |

### 4.3 M-3：`?? false` 改 `?? true`（未定义视作已派发）

```diff
-				const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;
+				const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? true;
```

| 步骤 | 命令 | 输出 |
|------|------|------|
| H0 | 同上 | `C261B903…` |
| 变异 | `mutate.mts apply M-3` | `Hmut=EF9F5ECADA88C919657DBB7D7082E88213C4340ADAE0A14AF906A53A4AF2175D` |
| 红 | `probe.mts vc002` | **EXIT=1**：`[FAIL] undefined dispatchedTaskKeys form: 0 alerts — alerts=1`，`[VERIFY] VC-002: undefined_alerts=1 empty_set_alerts=0 pass=false`（`undefined` 形态误投递；显式空 Set 形态仍 0——`new Set().has()` 返回 false 不经 `??` 兜底，与设计 §5 边界一致） |
| 复原 | `mutate.mts restore` | `sha256=C261B903…`，`H1==H0: true` |
| 复绿 | `probe.mts vc002` | **EXIT=0**：`undefined_alerts=0 empty_set_alerts=0 pass=true` |

三个变异共用同一份备份 `%TEMP%\mwcre-t3-verify\pm-orchestrator.backup.ts`（sha256 = H0，`mutate.mts backup` 在任何变异前创建并落盘 `h0.txt`）；每次 restore 后均以 `H1 == H0` 校验字节级复原。

## 5. 回归（全部变异复原后的最终态）

1. `cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts`：

```
 Test Files  2 passed (2)
      Tests  183 passed (183)
   Start at  16:42:24
   Duration  3.53s (transform 350ms, setup 0ms, import 888ms, tests 2.84s, environment 0ms, …)
```

→ **0 failed，183 passed**，EXIT=0（`agent-team-loop.test.ts` 176 + `agent-team-loop-watch-aggregate.test.ts` 7；套件自身的 `[VERIFY] VC-001/002/003` 行亦在输出中出现，与本探针独立测得的数值一致）。

2. `cd H:/git/Multi-Workers; npm run check`：

```
> biome check --write --error-on-warnings . && npm run check:pinned-deps && npm run check:ts-imports
  && npm run check:shrinkwrap && npm run check:install-lock:coding-agent && tsgo --noEmit && npm run check:browser-smoke
Checked 1092 files in 567ms. No fixes applied.
…（pinned-deps / ts-imports / shrinkwrap up to date / install-lock up to date / browser-smoke）
```

→ **EXIT=0**。

3. 最终态复核：`mutate.mts verify` → `live sha256=C261B903… matches H0: true`；`probe.mts all` → EXIT=0（§2 四条 [VERIFY] 全绿）；`vc004-bytes.mts` → EXIT=0（§3.2）。

## 6. git status 起止逐行比对（零残留）

会话开始（任何写入/变异之前）：

```
 M .agenticdoc/_index.parallel
 M packages/coding-agent/CHANGELOG.md
 M packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
 M packages/coding-agent/test/extensions/agent-team-loop.test.ts
 M packages/multi-workers/autopilot/conductor.py
?? .agenticdoc/mw-crosskey-risk-escalation/
?? .tmp/
?? hello-world.txt
?? packages/coding-agent/Python/
```

会话结束（全部变异复原、回归跑完之后）：

```
 M .agenticdoc/_index.parallel
 M packages/coding-agent/CHANGELOG.md
 M packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
 M packages/coding-agent/test/extensions/agent-team-loop.test.ts
 M packages/multi-workers/autopilot/conductor.py
?? .agenticdoc/mw-crosskey-risk-escalation/
?? .tmp/
?? hello-world.txt
?? packages/coding-agent/Python/
```

**逐行相同**（10/10）。其中 `pm-orchestrator.ts` / `agent-team-loop.test.ts` 的 M 状态是 T-1 的既有未提交改动（本任务开始前已存在；本任务结束时 `pm-orchestrator.ts` sha256 仍为 H0，即 T-1 原样）；`_index.parallel`、`CHANGELOG.md`、`conductor.py`、`.tmp/`、`hello-world.txt`、`packages/coding-agent/Python/` 为其他会话痕迹，未触碰。本任务在仓库内仅新增本证据文件与 `workers/mwcre-t3-verify/output.md`（两者均位于已 untracked 的 `.agenticdoc/mw-crosskey-risk-escalation/` 之下，不改变 status 行集合）。未 commit、未跑 `mw build`、未改 `dist/**`、未改 Python、未改既有测试文件。

## 7. 保留的探针脚本与产物（系统临时目录 `%TEMP%\mwcre-t3-verify\`）

| 文件 | bytes | sha256 | 用途 |
|------|-------|--------|------|
| `probe.mts` | 11924 | `AAB2147616082F6662C96D866611837DF83FE4C8F7A5C306936EFDC526F857A1` | §2 VC-001~004 场景探针 |
| `vc004-bytes.mts` | 8215 | `D982A1F9DD494E320DE7D634251500171D1FD9794EB26BBF0800AE1873BF23D1` | §3 字节一致性探针（git show + import 改写 + 同夹具双求值） |
| `mutate.mts` | 4221 | `6B0531A831431175ABA07792740D76860C04DCDCFFB3E773ADF71EC9D83CEE24` | §4 变异 harness（H0 守卫 / 唯一性校验 / 整文件复原） |
| `check-rewrite.mts` | 1702 | `9B4B1E3DF3C2EA15A5513518FBA976C9406974B13938DED181F3AD8AD1E85EEC` | §3.1 改写完整性核对（仅 17 行 import 差异） |
| `analyze-head-imports.mts` | 1356 | `E0D411ADD604BE87F2B008E661ADB02AD755240AB9838A7A69E6118B2F26DAE3` | HEAD 源 import 面分析（改写正则的安全前提） |
| `head-pm-orchestrator.ts` | 38540 | `F89F60C94BB56CA6B6945B520FBE94AF2944A87FC673CAA9ADFDE87260E5D357` | `git show HEAD:…` 原始字节副本（= `git cat-file -s` 38540） |
| `head-pm-orchestrator-rewritten.mts` | 39866 | `EC8B464CE98E460744451F41848467D1559ABCE1F80267A9C8159E5EA95EA76E` | 改写后可 import 的 HEAD 模块 |
| `pm-orchestrator.backup.ts` | 39440 | `C261B903D218EF2D94C62A0956EA5FBB62BEA050710D1EEE80709CE7F16ECCC3` | 变异前整文件备份（= H0） |
| `h0.txt` | 65 | `604328700DB4DDAF6F8CEE84C4E63B031FD8EEE30E247A70829064812EF93387` | H0 记录 |
| `vc001-alert.txt` | 556 | `1B8C6244E99E93DEF53652EBFCAD6B19D82CFCC447C43C3D0BE218224E9FFA00` | VC-001 实测 alert 全文 |
| `vc004-current-alert.bytes.txt` | 533 | `DFDE79BD61EB9196F77F8CA14197EB579E9320832FE863C5629351E1D2F8F1AE` | §2 VC-004 实测 alert 原始字节 |
| `vc004-shared-fixture-alert.bytes.txt` | 533 | `F2DA612A675035D99A47A07CF3FCC9AEE38BFFC282AE6A2BF79C9E4FD221C362` | §3.2 同夹具下 HEAD=current 的 alert 原始字节 |

### 7.1 `probe.mts` 关键结构（全文见临时目录，sha256 见上表）

- 静态 import 仓库真实模块：`startWorkerPollLoop`（pm/pm-orchestrator.ts）、`WorkerStore` / `IndexStore` / `AckStore`（shared/*），file:// 绝对 URL。
- `makeFixture`：mkdtemp 根 + `_index.parallel` upsert `key-a` + `{key}/workers/{task}/` running 行（WorkerStore.upsert）+ 自建 `[CHECKPOINT]` trace 行。
- `runWatch`：`startWorkerPollLoop(fakePi, store, new AckStore(root), is, root, watch, {ctx: undefined}, 40)`，真实定时器两个 280ms 窗、同一 handle，返回两窗计数。
- fake pi：`sendMessage(m, opts)` 捕获 `content` 与 `options`（triggerTurn 断言来源）。

### 7.2 `vc004-bytes.mts` 关键结构

- `execFileSync("git", ["show", "HEAD:<rel>"], {cwd: REPO})` → 原始字节（Buffer）；`headSrc.replace(/(from\s+")(\.[^"]+)(")/g, …)` 机械改写 import 为 `pathToFileURL(path.resolve(orchDir, spec)).href`；写 `.mts` 后 `await import(pathToFileURL(tmpModule).href)`（运行期路径，动态 import 不可避免；仅临时探针，仓库源码仍全部顶层 import）。
- 同一夹具先后 `runLoop(headLoop)` / `runLoop(currentLoop)`，`Buffer.from(...).equals(...)` 逐字节比较，双侧各断言 1 条 alert、low 静默、triggerTurn=true。

### 7.3 `mutate.mts` 变异定义（唯一替换串，制表符缩进与源文件一致）

```
M-1: old = "\t\t\t\tconst owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;\n\t\t\t\tif (!watch.key || (ownerKey !== watch.key && !owned)) continue;"
     new = "\t\t\t\tif (!watch.key || ownerKey !== watch.key) continue;"
M-2: old = "\t\t\t\tif (!watch.key || (ownerKey !== watch.key && !owned)) continue;"
     new = "\t\t\t\tif (!watch.key) continue;"
M-3: old = "watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false"
     new = "watch.dispatchedTaskKeys?.has(entry.taskKey) ?? true"
```

## 8. 与 T-1 结论的对照（事后，不作为证据来源）

| 项 | T-1 自报 | T-3 独立测得 | 一致 |
|----|----------|--------------|------|
| VC-001 | alerts=1 owner_in_text=true trigger_turn=true dup=0 | 同左 | 是 |
| VC-002 | undefined_alerts=0 empty_set_alerts=0 | 同左 | 是 |
| VC-003 | low_alerts=0 high_alerts=1 dup=0 | 同左 | 是 |
| VC-004 | watched_key_alerts=1 + 一次性临时比对 text_byte_identical=true | 1 条 + 重做的机械比对 text_byte_identical=true（HEAD 与当前模板同夹具求值，533 字节全等） | 是 |
| 回归 | 183 passed / 0 failed；check EXIT=0 | 同左 | 是 |

## 9. 结论

mw-crosskey-risk-escalation T-1 的实现（D-101 过滤放宽 + D-102 异地 owner 文案）通过 T-3 独立验证：四个 VC 独立复现全绿、三个变异反例证明判据两支（`owned` 派发支、`?? false` 显式布尔化、owner 过滤）各自必要且被测试面覆盖、watched key 路径文本经机械求值逐字节不变、回归零失败、工作区零残留。**T-3 判定：PASS，无阻塞项。**
