# RQ-2（mwgf-rq2-direction-contract）：worker bash 写面守卫的「方向契约」与反例语料

- Key: `mw-guard-form-hardening`｜阶段 SPEC｜角色 research（只读）｜基线 HEAD `ab546bb64`（2026-10-11）
- 目标产物：方向契约（可判定谓词）+ 反例语料（机器可读）+ 谓词落点 + 度量
- 结论一句话：**契约 = 「只有字面量（verbatim）目标参与判定；含展开语法的目标一律 allow-unknown + 审计行」；现行实现在 19 条 must-allow 语料上误拦 16 条，must-block 14 条零漏放。**

---

## 0. 方法与证据口径

- 「现实现判定」列**不是推演**：以 `node --input-type=module` 导入已构建的 `packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js`，
  直接调用其导出函数 `extractBashWriteCandidates` / `checkBashWriteScopeTarget`（源码同名函数：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:809` / `:959`）。
  逐一比对 dist 与 src 语义一致：`src:733 → dist:539`（`SHELL_WRAPPER_COMMANDS`）、`src:821 → dist:624`（`>`/`>>` 分支）、`src:960 → dist:786`、`src:975 → dist:800`。
- config 用本 worker 的真实条件（与运行期 `worker-mode.ts:1467-1475` 构造的 `BashWriteScopeConfig` 同形）：
  `projectRoot = H:\git\Multi-Workers`、`taskDir = H:\git\Multi-Workers\.agenticdoc\mw-guard-form-hardening\workers\mwgf-rq2-direction-contract`、
  `keyDir = H:\git\Multi-Workers\.agenticdoc\mw-guard-form-hardening`、`trueRoot = H:\git\Multi-Workers\.agenticdoc`、`writeScope = undefined`。
  `writeScope` 取 `undefined` 有实测依据：本 key 现有 5 份 task.md 全部是 hand-written research 任务书，**均无 `write_scope:` 头**（`Select-String -Pattern 'write_scope|^type:|^origin:'` 只命中 `type: research`）；
  注意 dispatch.py 生产的 shell 角色任务书会由 `pm/ui-bridge.ts:1489 renderDefaultWriteScope` 渲染该头，届时候走第三档（write-scope）判定，不影响本契约的分档逻辑。
- 守卫对 research 角色确实生效：`worker-mode.ts:1467`（`isShellRole && isWritelessRole`，helper 见 `:126`/`:133`）⇒ research 有 `bash` 无 `write/edit` ⇒ 激活。
  本次研究自身就被拦了 2 次（见 §5 C-1），是本契约问题的**现场复现**。
- 纪律：未修改任何源码/测试；未运行 vitest / `npm run check` / `npm run build` / `mw build`；除本 `report.md` 外未写任何路径。
- 「修复后判定」列是本报告谓词的**投影**（脚本内实现 `verbatim()` 后套用同一批 `checkBashWriteScopeTarget` 元语），不是修复后代码的实测，标注为 projection。

---

## 1. 交付物 ①：方向契约（可判定谓词）

### 1.1 词法前提：`verbatim(word)`

设 `word` 为提取器给出的**目标 token 文本**（`BashWriteCandidate.target`，`worker-mode.ts:621-627`）。定义

```
verbatim(word) := word 中不存在「在 shell 中会被展开/匹配」的语法成分
                  = 不存在 ①未展开的 $  ②未展开的反引号  ③词首未引用的 ~  ④未引用的 glob 元字符 (* ? [ {)
                其中「未引用」= 不在单引号内、且未被反斜杠转义
```

判定所需的引用/转义信息**在当前实现里已经丢失**（`tokenizeShellCommand` 在 `:667-731` 剥掉引号后只留 `{text, operator}`，`:659-664`），必须在提取阶段带上（见 §3 P-1/P-3）。
双引号**不**使 `$`/反引号变成字面量（双引号内仍展开），单引号与反斜杠转义则使其成为字面量。

补充约定（用于内联脚本捕获，`inlineScriptTargets`，`worker-mode.ts:~790-800`）：脚本内的目标来自正则捕获的引号字面量，
`verbatim = 捕获文本自身不含 $ / 反引号`。这样 `open(".git/config","w")` 仍走字面量档 ⇒ 维持现行 deny。

### 1.2 判定函数（三档 + deny 绝对优先）

```
V(config, raw, verbatim):
  if not verbatim(raw)                          -> { allow, verdict="allow-unknown" }        # 档③
  r = normalizeForCompare(config.projectRoot, raw)                                            # :960 / read-scope.ts:100
  if bashWriteDenyReason(config, r) != null     -> { deny, rule="deny" }                      # :923  ← deny 绝对优先
  if not (isSameOrUnder(taskDir,r) or isSameOrUnder(evidenceDir,r)) -> { deny, rule="scope" }  # :975
  if writeScope defined and not some(inWriteScope(r))               -> { deny, rule="write-scope" } # :985
  -> { allow }                                                                                # 档①
```

档位语义：
- **档①「可静态确定为允许面内」⇒ allow**：`raw` 字面量，解析后落在 `taskDir ∪ keyDir/evidence`（有 `write_scope:` 头时再交一次）。
- **档②「可静态确定为 deny 面内」⇒ deny，且绝对优先**：`raw` 字面量且解析后命中显式 deny 清单（`bashWriteDenyReason:923-937`：`pm-state.md` / `workers/_workers*` / `_index.parallel` / 其他 key 或 `.agenticdoc` 根 / `packages/**` / `.git/**`）
  或落在允许面之外（`rule=scope`，`rule=write-scope`）。显式清单只改变 **rule 令牌与严重度**，不改变判定结果 —— 因为该守卫本质是**允许面白名单**，「确定在面外」就已经是 deny。
- **档③「不可静态确定」⇒ allow + 审计行 `verdict=allow-unknown`**。含展开语法者解析出来的路径**不是 shell 实际写入的路径**，因此既不能定为 allow 也不能定为 deny。

### 1.3 deny 优先级与「不可确定」如何共存？（裁定）

**裁定：deny 是「只在 verbatim 域上有定义」的偏函数；档③ 不在 deny 的定义域内，因此二者不是竞争优先级，而是不相交的定义域。**

形式论证：`bashWriteDenyReason(config, r)` 的语义是「shell 最终写入的路径 r 落在 deny 面内」。`normalizeForCompare(projectRoot, raw)`（`read-scope.ts:100-114`）只对 `raw` 做**词法** `path.resolve` + realpath，
对含 `$X` 的 token 它给出的是「一个字面名为 `$X` 的目录」，与实际写入路径无关（这也是现状误拦的根因，spec A2 / `pm-state.md:?` 坐标 `:823/953/960/975`）。

**反证（为什么对档③判 deny 不是「从严」而是「猜测」）**——

```
命令：printf x > .agenticdoc/mw-dispatch-settle-gates/$X/pm-state.md
```
- 该 token 的字面前缀 `.agenticdoc/mw-dispatch-settle-gates/` **已落在 deny 面内**，实测现状判定 = `BLOCK(deny/denied:other key dir / .agenticdoc root)`（语料 F2）。
- 但取 `X=../mw-guard-form-hardening/evidence` 时，shell 实际写入
  `.agenticdoc/mw-guard-form-hardening/evidence/pm-state.md` —— **正好在允许面内**（`taskDir` 同 key 的 `evidenceDir`）。
- 即：对一个含变量的 token 判 deny，会被一条**合法展开**直接证伪。所以「字面前缀在 deny 面内」「字面后缀是 deny basename」都**不构成「可静态确定落在 deny 面」**，按 AC-001 的定义文字（「对**可静态确定且落在 deny 面**的目标必须拦」）不能 deny。

推论：deny 的绝对优先性仅在 verbatim 域内成立（域内 `deny` 先于 `scope`/`write-scope`/allow 求值，`worker-mode.ts:964 → :975 → :985`，顺序不变）；档③不与之争抢优先级。

### 1.4 `$X/pm-state.md` 的裁定

**裁定：放行（`verdict=allow-unknown`），不拦；审计行加一个非阻断的风险标注 `risk=deny-basename`。**

理由（三条，按权重）：
1. **AC-001 的定义文字直接否定 deny**：目标不可静态确定 ⇒ 既不满足「落在 deny 面」，也不满足其「可静态确定」前置条件。`pm-state.md` 只是**可见的字面后缀**，不是解析结果。
2. **basename 规则会引入新的误拦，方向违约**：deny 面的 `_workers*` 是**族匹配**（`bashWriteDenyReason:926-930`，`firstSegment.startsWith("_workers")`）——一条 `printf x > $T/_workers-notes.md`（写进自己 taskDir 的笔记）会被 basename 规则误拦。
3. **前缀规则已被 §1.3 的 witness 证伪**，而 basename 是比前缀更弱的证据。

因此「拦 `$X/pm-state.md`」在**可判定性**与**方向一致性**上都站不住；可判定性正是本 key 的地基（spec §0）。

**残余风险承担者（诚实归属）**：

| 承担者 | 是否真能兜住 `$X/pm-state.md` | 依据 |
|---|---|---|
| 事后审计（**主承担者，真实存在**） | 使漏放**可见、可计数**，但**不阻止**写入 | `appendBashWriteScopeTraceLine` `worker-mode.ts:1017-1032`（现仅在 block 时写，需按 §3 P-6 增加 allow-unknown 分支）；AC-007 要求 `allow_unknown_audited == allow_unknown_count` |
| `run.json` 身份（归因，非预防） | 事后可把越界写入归因到具体 run/task_key/owner_key/pid | `runState` 构造 `worker-mode.ts:1320-1344`；终态 `finishRun` 重采 artifacts `:1290-1298`；`shared/run-store.ts` |
| PM 侧守卫（**不承担此项**） | **不覆盖**运行期 bash 写入：`foreignLiveClaimRefusal`（`pm/ui-bridge.ts:247`）只管「本窗口能否 dispatch/advance 别的活 key」；`judgeWriteIntent`/`isWhitelistedWriteTarget`（`pm/ui-bridge.ts:1445`/`:1423`）明确只判**无 shell** 的 writeless 角色，shell 角色的写入被**委托回本守卫**（`judgeWriteIntent` 对 `isShellRole` 直接 `ok:true`） | `pm/ui-bridge.ts:1445-1446` 注释「a shell role (`research`) is handled by the AC-005b runtime guard instead」 |
| 进程级隔离 P2 | 唯一能**预防**的一层，本 key 明确出界 | `spec.md` §2 Out / §6 非目标 |

结论：残余风险 = 「含展开语法的跨 key 写入（F1/F2/F3）」**只能事后发现，不能事前阻止**；这是「不引入 shell 解释器」（`pm-state.md` D-003）与「无进程沙箱」（§6）的必然代价，必须在 spec 里显式登记（见 §4 `currently_blocked_unknown_flips=3`）。

---

## 2. 交付物 ②：反例语料（机器可读，36 条）

列定义：`id | class | expected | current（实测） | post_fix（本契约投影） | extracted_target | 依据 | command`。
`依据` 编码：`E<行>` = 提取器（redirect 分支 `worker-mode.ts:821-825`；tee `:831-834`；cp/mv `:835-841`；rm/mkdir/touch/truncate `:842-848`；sed -i `:849-855`；git `:856-863`；curl -o `:864-873`；wget -O `:874-883`；inline python/node `:884-893`；powershell `:894-911`），
`D` = 显式 deny 清单 `:923-937`（子规则：`:925` pm-state.md｜`:926-930` workers/_workers*｜`:931` _index.parallel｜`:932-934` 其他 key/.agenticdoc 根｜`:935` packages/**｜`:936` .git/**），
`V960` = `normalizeForCompare`（`worker-mode.ts:960`）、`V975` = 允许面判定（`:975`）、`V985` = write_scope（`:985`）、`V964` = deny 分支（`:964`）、`V996` = 兜底 allow（`:996`）。

```
id  class  expected       current(=实测)                        post_fix(投影)  extracted_target                                                        basis              command
M1  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/report.md                                                            E823+V960,V975     printf x > $T/report.md
M2  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/report.md                                                            E823+V960,V975     printf x > "$T/report.md"
M3  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   ${T}/x.md                                                               E823+V960,V975     printf x > ${T}/x.md
M4  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $UNSET/x.md                                                             E823+V960,V975     printf x > $UNSET/x.md
M5  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $                                                                       E823+V960,V975     printf x > $(dirname $0)/x.md
M6  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   `dirname                                                                E823+V960,V975     printf x > `dirname $0`/x.md
M7  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/*.md                                                                 E823+V960,V975     printf x > $T/*.md
M8  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   ~/x.md                                                                  E823+V960,V975     printf x > ~/x.md
M9  allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/$FILE.md                                                             E823+V960,V975     printf x > "$T/$FILE.md"
M10 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/report-$                                                             E823+V960,V975     printf x > $T/report-$(date +%s).md
M11 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/report.md                                                            E831-834+V960,V975  echo x | tee $T/report.md
M12 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/../mwgf-rq2-direction-contract/report.md                              E823+V960,V975     printf x > $T/../mwgf-rq2-direction-contract/report.md
M13 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T                                                                      E823+V960,V975     T=.agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/report.md; echo x > $T
M14 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $null                                                                   E823+V960,V975     Get-Content a.txt > $null
M15 allow  allow          ALLOW                               ALLOW           .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/report.md                                     V960,V975(+996)    printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/report.md
M16 allow  allow          ALLOW                               ALLOW           .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../mwgf-rq2-direction-contract/progress.md        V960,V975(+996)    printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../mwgf-rq2-direction-contract/progress.md
M17 allow  allow          ALLOW                               ALLOW           .agenticdoc/mw-guard-form-hardening/evidence/x.json                                                                           V960,V975(+996)    printf x > .agenticdoc/mw-guard-form-hardening/evidence/x.json
M18 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   $T/pm-state.md                                                          E823+V960,V975     printf x > $T/pm-state.md
M19 allow  allow-unknown  BLOCK(scope/outside-allowed-surface)  ALLOW-UNKNOWN   *.md                                                                    E823+V960,V975     printf x > *.md
B1  deny   deny           BLOCK(deny/denied:other key dir / .agenticdoc root)  DENY(deny)      .agenticdoc/mw-dispatch-settle-gates/pm-state.md                                        E823+D932-934+V964  printf x > .agenticdoc/mw-dispatch-settle-gates/pm-state.md
B2  deny   deny           BLOCK(scope/outside-allowed-surface)                 DENY(scope)     ../other-key/workers/x/report.md                                                        E823+V960,V975      printf x >> ../other-key/workers/x/report.md
B3  deny   deny           BLOCK(deny/denied:packages/**)                       DENY(deny)      packages/coding-agent/src/a.ts                                                          E823+D935+V964      printf x > packages/coding-agent/src/a.ts
B4  deny   deny           BLOCK(deny/denied:.git/**)                           DENY(deny)      .git/config                                                                             E823+D936+V964      printf x > .git/config
B5  deny   deny           BLOCK(scope/outside-allowed-surface)                 DENY(scope)     report.md                                                                               E823+V960,V975      printf x > report.md
B6  deny   deny           BLOCK(deny/denied:workers/_workers*)                 DENY(deny)      .agenticdoc/mw-guard-form-hardening/workers/_workers.parallel                           E823+D926-930+V964  printf x > .agenticdoc/mw-guard-form-hardening/workers/_workers.parallel
B7  deny   deny           BLOCK(deny/denied:_index.parallel)                   DENY(deny)      .agenticdoc/_index.parallel                                                             E823+D931+V964      printf x > .agenticdoc/_index.parallel
B8  deny   deny           BLOCK(deny/denied:other key dir / .agenticdoc root)  DENY(deny)      .agenticdoc/mw-dispatch-settle-gates/workers/other/report.md                            E823+D932-934+V964  printf x > .agenticdoc/mw-dispatch-settle-gates/workers/other/report.md
B9  deny   deny           BLOCK(deny/denied:other key dir / .agenticdoc root)  DENY(deny)      .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../../mw-dispatch-settle-gates/pm-state.md  E823+D932-934+V964  printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../../mw-dispatch-settle-gates/pm-state.md
B10 deny   deny           BLOCK(scope/outside-allowed-surface)                 DENY(scope)     /tmp/evil.md                                                                            E823+V960,V975      printf x > /tmp/evil.md
B11 deny   deny           BLOCK(scope/outside-allowed-surface)                 DENY(scope)     ../../foo.txt                                                                           E823+V960,V975      printf x > ../../foo.txt
B12 deny   deny           BLOCK(scope/outside-allowed-surface)                 DENY(scope)     $T/report.md                                                                            E823+V960,V975      printf x > '$T/report.md'
B13 deny   deny           BLOCK(scope/outside-allowed-surface)                 DENY(scope)     $T/report.md                                                                            E823+V960,V975      printf x > \$T/report.md
B14 deny   deny           BLOCK(deny/denied:pm-state.md)                       DENY(deny)      .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../pm-state.md  E823+D925+V964      printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../pm-state.md
F1  cost   deny-today/allow-unknown-after  BLOCK(scope/outside-allowed-surface)          ALLOW-UNKNOWN  $X/pm-state.md                                                    E823+V960,V975      printf x > $X/pm-state.md
F2  cost   deny-today/allow-unknown-after  BLOCK(deny/denied:other key dir / .agenticdoc root)  ALLOW-UNKNOWN  .agenticdoc/mw-dispatch-settle-gates/$X/pm-state.md          E823+D932-934+V964  printf x > .agenticdoc/mw-dispatch-settle-gates/$X/pm-state.md
F3  cost   deny-today/allow-unknown-after  BLOCK(scope/outside-allowed-surface)          ALLOW-UNKNOWN  $T/../../mw-dispatch-settle-gates/pm-state.md                     E823+V960,V975      printf x > "$T/../../mw-dispatch-settle-gates/pm-state.md"
```

class 说明：`M` = must-allow（19 条，≥12 达标，覆盖任务书点名的 `$T`/引号/`${}`/未设变量/命令替换/反引号/glob/`~`/相对/`..` 形态）；`B` = must-block（14 条，≥6 达标，覆盖任务书点名的 4 条 + 10 条加固）；`F` = **契约代价条**（现状拦、契约后 allow-unknown，见 §4 与 §6，**不计入 must-block**）。

复现脚本（只读，不改仓库；`verbatim()` 是本契约谓词的实现，`checkBashWriteScopeTarget` 是现状实现）：

```js
// node --input-type=module   (stdin)
import path from "node:path";
import { extractBashWriteCandidates, checkBashWriteScopeTarget } from
  "file:///H:/git/Multi-Workers/packages/coding-agent/dist/extensions/agent-team-loop/worker/worker-mode.js";
const projectRoot = path.resolve("H:/git/Multi-Workers");
const keyDir  = path.join(projectRoot, ".agenticdoc", "mw-guard-form-hardening");
const taskDir = path.join(keyDir, "workers", "mwgf-rq2-direction-contract");
const cfg = { projectRoot, taskDir, keyDir, trueRoot: path.join(projectRoot, ".agenticdoc"), writeScope: undefined };
const GLOB = /[*?[{]/;
function verbatim(raw, quote) {           // quote: plain | dq | sq | esc | script
  if (quote === "sq" || quote === "esc") return true;
  if (raw.includes("$") || raw.includes("`")) return false;
  if (quote === "dq" || quote === "script") return false;
  if (/^~/.test(raw)) return false;
  return !GLOB.test(raw);
}
for (const [id, quote, cmd] of CORPUS) { /* CORPUS = 上表 36 行 */ }
```

---

## 3. 交付物 ③：谓词落点（文件:行号 + 现状摘录 + 目标语义）

全部落点在 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`。**注意：本契约需要「引用/转义」信息，而该信息在当前实现的 token 化阶段就被丢掉了** —— 因此 P-1/P-3 是**必需项**，不是优化项（证据：B12 `'$T/report.md'`、B13 `\$T/report.md` 现状被判 deny；若按「含 `$` 即视作不确定」的偷懒实现，这两条会变成 allow-unknown，**must-block 直接漏放 2 条**）。

| # | 位置 | 现状摘录 | 目标语义 |
|---|---|---|---|
| P-1 | `:659-664` `interface ShellToken { text: string; operator: boolean; }` | token 只带文本与算子标记，引号/转义信息在扫描中丢失 | 增 `verbatim: boolean`（或 `singleQuotedSpans`），由扫描器在词整流时判定 |
| P-2 | `:621-627` `export interface BashWriteCandidate { target: string; pattern: string; }` | 候选只有原始文本 | 增 `verbatim: boolean`；`add()`（`:812-816`）加同名形参 |
| P-3 | `:667-731` `tokenizeShellCommand` | 单引号段（`:677-686`）与反斜杠转义（`:692-697`）被**静默消解**；`flush()`（`:670-676`）不传引用状态 | 单引号段/反斜杠转义 ⇒ 该字符不构成「活展开」；未引用的 `$`、反引号、词首 `~`、glob 元字符 ⇒ `verbatim=false`；`flush()` 把标记写进 `ShellToken` |
| P-4 | `:796-807` `inlineScriptTargets` + `:889` 调用点 | 捕获组直接成候选，无引用上下文 | `verbatim = !/[$\`]/.test(captured)`（保守：保留 `open(".git/config","w")` 现行的 deny，不产生新漏放） |
| P-5 | `:959-1002` `checkBashWriteScopeTarget`，具体插入点 `:960` 之前 | `const target = normalizeForCompare(config.projectRoot, rawTarget);` 无条件执行 | 前置 `if (!verbatim(rawTarget)) return { allowed: true, rule: "allow-unknown", detail: "target-not-statically-determinable", risk?, target: rawTarget };`；`:629` `BashWriteScopeRule` 增 `"allow-unknown"`；`:647-657` `BashWriteScopeVerdict` 增可选 `risk?: "deny-basename"`（`basename ∈ {pm-state.md}` 或匹配 `_workers*` 时置位，仅审计用，不改判定） |
| P-6 | `:1477-1497` `pi.on("tool_call", ...)` 循环（`:1483-1486`） | `if (verdict.allowed) continue;` —— 放行即静默返回，无审计 | 对 `verdict.rule === "allow-unknown"` 先写 `appendBashWriteScopeTraceLine`（`blocked=false`）再 `continue`；`:1017-1032` 行格式改为 `[WRITE_SCOPE] <ts> write-scope blocked=<true\|false> rule=<rule> detail=<detail> [risk=<risk>] pattern=<pattern> target=<target> cmd=<summary>`（保留 `write-scope` 令牌以满足 AC-005b；`blocked` 独立成字段使审计读者能区分） |

**不该改的（保持逐字节不变）**：`bashWriteDenyReason`（`:923-937`）的 6 条 deny 子规则、允许面判定（`:975`）、`matchesWriteScopeEntry`（`:939-955`）、`normalizeForCompare` 调用（`:960` 的**实参**）、`SHELL_WRAPPER_COMMANDS`（`:733`）、`NULL_WRITE_TARGETS`（`:753-761`）、`INLINE_WRITE_PATTERNS`（`:775-784`）、`POWERSHELL_WRITE_COMMANDS`（`:764-773`）、各 `case` 的命令名集合。

**为什么这是「收窄匹配而非放宽」**（三点，逐条可核）：
1. **提取面不动**：没有新增命令名、算子、正则分支或包装器（`:733/:753-761/:764-773/:775-784` 全等）；识别到的写入形态集合与现状**逐条相同**（语料 36 条的 `extracted_target` 列即为提取面清单）。
2. **deny 谓词的定义域收窄**：从「每一个被提取的候选」（现状：`:960` 无条件解析）收窄为「verbatim 候选」。谓词**语义**不变（同一 `normalizeForCompare`、同一 deny 清单、同一允许面、同一 write_scope），只是**不再对无法解析的输入断言判定**。
3. **断言的资格收窄**：守卫停止对一类**判定可被合法展开证伪**的输入发判定（§1.3 的 F2 witness：现状 deny 一条实际写入允许面的命令），这正是 AC-001 的「可静态确定」前置条件。副作用方向：block ↓、audit ↑、**新增 allow 全部落在 verbatim 之外**；语料内 14 条 must-block 修复前后均 0 漏放。

---

## 4. 交付物 ④：度量

| 指标 | 值 | 说明 |
|---|---|---|
| `corpus_total` | 36 | 19 must-allow + 14 must-block + 3 contract-cost |
| `corpus_must_allow` | 19 | 逐条见 §2（M1–M19） |
| `corpus_must_block` | 14 | 逐条见 §2（B1–B14） |
| `currently_blocked_false_positives` | **16** | M1–M14 + M18 + M19，逐条列出见下表 |
| `currently_allowed_must_allow` | 3 | M15、M16、M17（唯一的三条字面量路径） |
| `must_block_currently_allowed`（漏放） | **0** | 14/14 现状已拦 —— 契约不得使其回退 |
| `currently_blocked_unknown_flips`（契约代价） | **3** | F1、F2、F3（现状拦 → 契约后 allow-unknown） |
| `projected_allow_determined` | 3 | M15–M17 |
| `projected_allow_unknown` | 19 | M1–M14、M18、M19 + F1–F3（AC-007 要求逐条有审计行） |
| `projected_deny` | 14 | B1–B14 |
| `deny_count`（现状口径，语料内） | 14 | 其中 `rule=deny` 8 条、`rule=scope` 6 条 |
| `must_block_would_leak_if_quoting_ignored` | **2**（推导） | B12 `'$T/report.md'`、B13 `\$T/report.md`：把「含 `$`」直接当未知 ⇒ `DENY(scope)` → `ALLOW-UNKNOWN`；这是 P-1/P-3 必需性的直接证据 |

`currently_blocked_false_positives=16` 逐条：

| id | 命令 | 现状判定（实测） |
|---|---|---|
| M1 | `printf x > $T/report.md` | `BLOCK(scope/outside-allowed-surface)` |
| M2 | `printf x > "$T/report.md"` | 同上 |
| M3 | `printf x > ${T}/x.md` | 同上 |
| M4 | `printf x > $UNSET/x.md` | 同上 |
| M5 | `printf x > $(dirname $0)/x.md` | 同上（提取到的目标是 `$`，命令替换被算子切碎） |
| M6 | ``printf x > `dirname $0`/x.md`` | 同上（提取到 `` `dirname ``） |
| M7 | `printf x > $T/*.md` | 同上 |
| M8 | `printf x > ~/x.md` | 同上 |
| M9 | `printf x > "$T/$FILE.md"` | 同上 |
| M10 | `printf x > $T/report-$(date +%s).md` | 同上（提取到 `$T/report-$`） |
| M11 | `echo x \| tee $T/report.md` | 同上（tee 分支 `:831-834` 同样只拿字面量） |
| M12 | `printf x > $T/../mwgf-rq2-direction-contract/report.md` | 同上 |
| M13 | `T=<taskDir>/report.md; echo x > $T`（QG-B A2 原始形态） | 同上 |
| M14 | `Get-Content a.txt > $null` | 同上（**本 session 实测发生 2 次**，见 §5 C-1） |
| M18 | `printf x > $T/pm-state.md` | 同上（basename 撞 deny 清单名字，但目标在自身 taskDir） |
| M19 | `printf x > *.md` | 同上（glob 策略条：仅当采纳「glob 不作静态分析」的裁定 R-3 才计入） |

---

## 5. 附带发现（均带坐标）

- **C-1（现场复现，实证）**：研究期间本 worker 自己的 bash 调用被拦 2 次，命令里都含 PowerShell 的 `2>$null`：
  `[WRITE_SCOPE] 2026-10-11T15:20:51.772Z write-scope blocked rule=scope detail=outside-allowed-surface pattern=redirect target=$null ...`（`trace.log:56`）
  与 `... 15:21:33.893Z ... target=$null ...`（`trace.log:63`）。
  根因：`NULL_WRITE_TARGETS`（`worker-mode.ts:753-761`）只登记了 `nul`/`/nul`，**没有 PowerShell 的 `$null`**，因此 `> $null` 被当普通重定向目标解析 → `<root>/$null` → `:975` 判面外。
  save 与泄漏都为零的系统级收益：误拦一次就是一次 `[TOOL_ERR]` + 一次工作返工。修复有两条互补路径：本契约（`$null` 含 `$` ⇒ allow-unknown，误拦消失但每次留审计行）或 **C-2**。
- **C-2（可选伴生改动，明确标注为提取面改动）**：`NULL_WRITE_TARGETS`（`:753-761`）加一项 `"$null"`（`:814` 已 `toLowerCase()` 比较）。方向仍是**收窄**（少提取一个目标）。若不做，`2>$null` 会从「误拦」变成「每次一条 allow-unknown 审计行」，在高频 PowerShell 习惯下审计噪声显著。
- **C-3（glob 裁定，需 spec 显式采纳）**：本报告把「含未引用 glob 元字符」一并归入档③（allow-unknown），因此 M19 `> *.md` 从现状拦变为 allow-unknown。若 PM 想收紧，可做**可判定的 glob 目录前缀分析**（glob 不跨 `/`，故 `DIR/prefix*` 的落点恒在 `DIR` 内）：expansion-free 前缀在允许面内 ⇒ allow、明确在面外 ⇒ deny。**但不建议**：中段 glob（`.../../*/x.md`，`*` 可匹配 `_workers.parallel` 也可匹配自身 taskKey）会让该规则本身变回不可判定，收益（拦 `> *.md` 这类项目根写入，无跨 key 损害）远小于新增分支的误拦风险。故 R-3 采纳「glob 一律档③」。
- **C-4（引用信息丢失，强制项）**：`BashWriteCandidate` 只有一个 `target: string`（`:621-627`），单引号/转义/双引号三种语义在提取后**不可区分**（B12/B13 vs M1/M2 的目标文本逐字节相同）。契约要实现「verbatim ⇒ 判定」就必须在 P-1/P-3 补齐该信息，否则必漏放 2 条 must-block。
- **C-5（旁证）**：字面量路径的 `..` 归约现状already正确（M16 = `ALLOW`，M15/M17 均 `ALLOW`），说明「字面量档」的语义在现状实现中已经是契约要的形态 —— 本契约只补上「不确定档」，不需重写解析层。

---

## 6. 未验证 / 残留 / 勘误

- **未验证**：修复后代码的实际判定（本报告 `post_fix` 列是谓词投影，不是实测）；`write_scope:` 头存在时第三档（`:985`）在 verbatim/档③ 划分下的组合行为（本 key 无带该头的任务书；推导上是「档③ 不进入该分支」，但未跑测）；dist 与 src 在**其他**函数上的字节级一致性（只逐点核对了 §0 列出的 4 处）。
- **残留（本 key 之后仍存在）**：F1/F2/F3 三类「含展开语法的跨 key 写入」在 worker 进程内**不可事前阻止**，只能靠 §1.4 的审计行事后发现；真正的预防需要 P2 进程级隔离（`spec.md` §2 Out）。
- **代价登记（供 spec 决策）**：采纳本契约会让 F2（`.agenticdoc/<other-key>/$X/pm-state.md`）从「现状拦」变为「审计后放行」。请 PM 在 design/spec 中显式写下这条方向代价（AC-001 已经用「可静态确定」前置条件为其背书），并确认 AC-007 的 `allow_unknown_audited == allow_unknown_count` 覆盖 F 类。
- **勘误**：§1.3 中「spec A2 / `pm-state.md:?`」的坐标占位应读作 **`spec.md` §6 表 A2 行**（坐标 `worker/worker-mode.ts:823/953/960/975`）+ `spec.md` §1 表 A2 行；本报告 §0 已给出经复测的具体行号（`:821-825`、`:960`、`:975`）。

---

## 7. 交付物 ② 的规范形（canonical，JSON Lines，36 行）

上表 §2 为可读版；本块为**逐字节规范形**，即复现脚本的输入语料（`{id,class,expect,current,post_fix,target,basis,cmd}`；`current` 为现状**实测**值 `deny:<rule>/<detail>` 或 `allow`；`basis` 见 §2 的 `E*/D*/V*` 编码）。

```json
{"id":"M1","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/report.md","basis":"E823+V960,V975","cmd":"printf x > $T/report.md"}
{"id":"M2","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/report.md","basis":"E823+V960,V975","cmd":"printf x > \"$T/report.md\""}
{"id":"M3","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"${T}/x.md","basis":"E823+V960,V975","cmd":"printf x > ${T}/x.md"}
{"id":"M4","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$UNSET/x.md","basis":"E823+V960,V975","cmd":"printf x > $UNSET/x.md"}
{"id":"M5","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$","basis":"E823+V960,V975","cmd":"printf x > $(dirname $0)/x.md"}
{"id":"M6","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"`dirname","basis":"E823+V960,V975","cmd":"printf x > `dirname $0`/x.md"}
{"id":"M7","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/*.md","basis":"E823+V960,V975","cmd":"printf x > $T/*.md"}
{"id":"M8","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"~/x.md","basis":"E823+V960,V975","cmd":"printf x > ~/x.md"}
{"id":"M9","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/$FILE.md","basis":"E823+V960,V975","cmd":"printf x > \"$T/$FILE.md\""}
{"id":"M10","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/report-$","basis":"E823+V960,V975","cmd":"printf x > $T/report-$(date +%s).md"}
{"id":"M11","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/report.md","basis":"E831-834+V960,V975","cmd":"echo x | tee $T/report.md"}
{"id":"M12","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/../mwgf-rq2-direction-contract/report.md","basis":"E823+V960,V975","cmd":"printf x > $T/../mwgf-rq2-direction-contract/report.md"}
{"id":"M13","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T","basis":"E823+V960,V975","cmd":"T=.agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/report.md; echo x > $T"}
{"id":"M14","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$null","basis":"E823+V960,V975","cmd":"Get-Content a.txt > $null"}
{"id":"M15","class":"must-allow","expect":"allow","current":"allow","post_fix":"allow","target":".agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/report.md","basis":"V960,V975(+996)","cmd":"printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/report.md"}
{"id":"M16","class":"must-allow","expect":"allow","current":"allow","post_fix":"allow","target":".agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../mwgf-rq2-direction-contract/progress.md","basis":"V960,V975(+996)","cmd":"printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../mwgf-rq2-direction-contract/progress.md"}
{"id":"M17","class":"must-allow","expect":"allow","current":"allow","post_fix":"allow","target":".agenticdoc/mw-guard-form-hardening/evidence/x.json","basis":"V960,V975(+996)","cmd":"printf x > .agenticdoc/mw-guard-form-hardening/evidence/x.json"}
{"id":"M18","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/pm-state.md","basis":"E823+V960,V975","cmd":"printf x > $T/pm-state.md"}
{"id":"M19","class":"must-allow","expect":"allow-unknown","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"*.md","basis":"E823+V960,V975","cmd":"printf x > *.md"}
{"id":"B1","class":"must-block","expect":"deny","current":"deny:deny/denied:other key dir / .agenticdoc root","post_fix":"deny:deny","target":".agenticdoc/mw-dispatch-settle-gates/pm-state.md","basis":"E823+D932-934+V964","cmd":"printf x > .agenticdoc/mw-dispatch-settle-gates/pm-state.md"}
{"id":"B2","class":"must-block","expect":"deny","current":"deny:scope/outside-allowed-surface","post_fix":"deny:scope","target":"../other-key/workers/x/report.md","basis":"E823+V960,V975","cmd":"printf x >> ../other-key/workers/x/report.md"}
{"id":"B3","class":"must-block","expect":"deny","current":"deny:deny/denied:packages/**","post_fix":"deny:deny","target":"packages/coding-agent/src/a.ts","basis":"E823+D935+V964","cmd":"printf x > packages/coding-agent/src/a.ts"}
{"id":"B4","class":"must-block","expect":"deny","current":"deny:deny/denied:.git/**","post_fix":"deny:deny","target":".git/config","basis":"E823+D936+V964","cmd":"printf x > .git/config"}
{"id":"B5","class":"must-block","expect":"deny","current":"deny:scope/outside-allowed-surface","post_fix":"deny:scope","target":"report.md","basis":"E823+V960,V975","cmd":"printf x > report.md"}
{"id":"B6","class":"must-block","expect":"deny","current":"deny:deny/denied:workers/_workers*","post_fix":"deny:deny","target":".agenticdoc/mw-guard-form-hardening/workers/_workers.parallel","basis":"E823+D926-930+V964","cmd":"printf x > .agenticdoc/mw-guard-form-hardening/workers/_workers.parallel"}
{"id":"B7","class":"must-block","expect":"deny","current":"deny:deny/denied:_index.parallel","post_fix":"deny:deny","target":".agenticdoc/_index.parallel","basis":"E823+D931+V964","cmd":"printf x > .agenticdoc/_index.parallel"}
{"id":"B8","class":"must-block","expect":"deny","current":"deny:deny/denied:other key dir / .agenticdoc root","post_fix":"deny:deny","target":".agenticdoc/mw-dispatch-settle-gates/workers/other/report.md","basis":"E823+D932-934+V964","cmd":"printf x > .agenticdoc/mw-dispatch-settle-gates/workers/other/report.md"}
{"id":"B9","class":"must-block","expect":"deny","current":"deny:deny/denied:other key dir / .agenticdoc root","post_fix":"deny:deny","target":".agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../../mw-dispatch-settle-gates/pm-state.md","basis":"E823+D932-934+V964","cmd":"printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../../mw-dispatch-settle-gates/pm-state.md"}
{"id":"B10","class":"must-block","expect":"deny","current":"deny:scope/outside-allowed-surface","post_fix":"deny:scope","target":"/tmp/evil.md","basis":"E823+V960,V975","cmd":"printf x > /tmp/evil.md"}
{"id":"B11","class":"must-block","expect":"deny","current":"deny:scope/outside-allowed-surface","post_fix":"deny:scope","target":"../../foo.txt","basis":"E823+V960,V975","cmd":"printf x > ../../foo.txt"}
{"id":"B12","class":"must-block","expect":"deny","current":"deny:scope/outside-allowed-surface","post_fix":"deny:scope","target":"$T/report.md","basis":"E823+V960,V975","cmd":"printf x > '$T/report.md'"}
{"id":"B13","class":"must-block","expect":"deny","current":"deny:scope/outside-allowed-surface","post_fix":"deny:scope","target":"$T/report.md","basis":"E823+V960,V975","cmd":"printf x > \\$T/report.md"}
{"id":"B14","class":"must-block","expect":"deny","current":"deny:deny/denied:pm-state.md","post_fix":"deny:deny","target":".agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../pm-state.md","basis":"E823+D925+V964","cmd":"printf x > .agenticdoc/mw-guard-form-hardening/workers/mwgf-rq2-direction-contract/../../pm-state.md"}
{"id":"F1","class":"contract-cost","expect":"allow-unknown-after","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$X/pm-state.md","basis":"E823+V960,V975","cmd":"printf x > $X/pm-state.md"}
{"id":"F2","class":"contract-cost","expect":"allow-unknown-after","current":"deny:deny/denied:other key dir / .agenticdoc root","post_fix":"allow-unknown","target":".agenticdoc/mw-dispatch-settle-gates/$X/pm-state.md","basis":"E823+D932-934+V964","cmd":"printf x > .agenticdoc/mw-dispatch-settle-gates/$X/pm-state.md"}
{"id":"F3","class":"contract-cost","expect":"allow-unknown-after","current":"deny:scope/outside-allowed-surface","post_fix":"allow-unknown","target":"$T/../../mw-dispatch-settle-gates/pm-state.md","basis":"E823+V960,V975","cmd":"printf x > \"$T/../../mw-dispatch-settle-gates/pm-state.md\""}
```

---

## 8. 一句话答复 PM 的三个必答点

1. **方向契约**：`verbatim ⇒ 三档判定（允许面 allow / deny 面或面外 deny，deny 绝对优先）；非 verbatim ⇒ allow-unknown + 审计行`（§1.1–1.2）。
2. **deny × 不可确定**：不相交定义域，deny 只在 verbatim 域内绝对优先；对非 verbatim 判 deny 会被合法展开证伪（§1.3 witness，F2）。`$X/pm-state.md` = **放**（allow-unknown，加 `risk=deny-basename` 审计标注）；残余风险由**事后审计**（主）+ **run.json 身份归因**承担，PM 侧守卫**不覆盖**运行期 bash 写入，真正的预防属 P2 出界（§1.4 表）。
3. **度量**：`corpus_must_allow=19`、`corpus_must_block=14`、`currently_blocked_false_positives=16`（逐条 §4）、`must_block_currently_allowed=0`、契约代价 `currently_blocked_unknown_flips=3`（F1–F3）。
