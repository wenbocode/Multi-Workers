# RQ-3 报告 — PM 派发期「写意图」判据的路径解析与目标集（A3 + A4）

- 任务：`.agenticdoc/mw-guard-form-hardening/workers/mwgf-rq3-path-resolution/task.md`
- phase：SPEC（只读研究）。未修改任何源码/测试；仓库内唯一写入 = 本 report.md。
- 方法：所有度量用一个只读 Node 脚本（从 stdin 喂入，脚本体与输出见附录），导入真实模块 `pm/ui-bridge.ts` 的 `collectWriteIntentHits` / `isWhitelistedWriteTarget` / `WRITE_INTENT_VERBS` 与 `worker/worker-mode.ts` 的 `isWritelessRole` / `isShellRole`；语料 = 仓库真实 `.agenticdoc/**/workers/*/task.md`。
- 未运行 vitest / npm run check / build（PM 负责）。

## 0. 结论摘要

1. **A3 成立，实测 5/5 全漏**：`写入 config.toml|Makefile|.env|x.html|x.rs` 五条在现实现下 `hits=0`（fail-open）。根因两处：`:1345-1346` 的扩展名枚举，以及 `:1406` 的 `pm.index !== 0` 锚定——verb 后第一个词不是「已知扩展名路径」时，**整条 clause 被放弃**，即使后面还有真实路径（实测样本 `Output: write your report to H:\...\report.md` 就是这种漏法）。
2. **A4 成立**：`isWhitelistedWriteTarget`（`:1423-1430`）先在 `:1426-1427` 用 basename 白名单 `return true`，`path.resolve` 目录比较在 `:1428-1430`，顺序颠倒。实测 `../other-key/workers/other-task/output.md` 与 `.agenticdoc/other-key/workers/other-task/output.md` 都 `= true`（放行）。
3. **目标集轴可行**：改为「允许面（本 taskDir）+ 路径形状判定 + 未识别即拒（仅限形状 token）」后，在真实 26 本 writeless-non-shell 语料上命中数 2 → 13，而**违规集一字不变**（仍是同一条已知真阳，假阳性 0）⇒ 覆盖面提高且不恶化。度量见 §5。
4. **「未识别即拒」必须限定在「形状像路径」的 token 上**：对裸 token 也一律拒的严格变体会在本语料引入 9/26 本（35%）假阳性（`your` / `design` / `mcp` / `side` / `surface` / `message_update` 等散文词）。若坚持要连裸 `Makefile` 也拦，代价是 deny-name 表（有限集合）或这 35% 假阳性。
5. **5 样例**：纯形状变体 4/5（`Makefile` 漏），+ deny-name 表 ⇒ **5/5**。
6. **Windows**：本机 `fs.realpathSync` **不做大小写归一**（实测 `PACKAGE.JSON` 原样返回）⇒ win32 必须大小写不敏感比较，应直接复用 `worker/read-scope.ts:89 isSameOrUnder` 与 `:100 normalizeForCompare`，而不是在 `ui-bridge.ts:1428-1430` 手搓 `path.resolve` 字符串比较。盘符相对 `C:foo`、UNC、`\\?\`、ADS、尾点/尾空格全部落在「拒绝」侧（fail-closed，方向安全），只产生假阳性风险，不产生漏放。
7. **同类误报佐证**：运行期 bash 写面守卫（`worker-mode.ts:667 tokenizeShellCommand`）在 PowerShell here-string 里被一个单引号 desync 后，把 JS 里的 `>` 当成 shell 重定向，以 `gapLen` 为「写入目标」报 `[rule=scope]` 拒绝（最小复现见 §7）。这就是「词法猜形状」的误报形态，§2.3 的反例控制正是针对它。

## 1. 现实现（对照基线）

| 位置 | 内容 |
| --- | --- |
| `pm/ui-bridge.ts:1266-1281` | `WRITE_INTENT_VERBS`（16 个动词，中英混合） |
| `:1299` | `WRITE_INTENT_PATH_WINDOW = 32` |
| `:1303` | `FRAMEWORK_TASK_BASENAMES = [task.md, trace.log, output.md, run.json, worker.log]` |
| `:1305-1337` | 5 个 allow-guard 的词表：negation（10）/ read-marker（19） |
| `:1338` | PM 归因（6 个，**仅中文**：`pm 会`/`由 pm`/`pm 收录`/`框架会`/`交给 pm`/`pm 将在`） |
| `:1339-1343` | 引号对 `"` `'` `「」` |
| `:1344` | 英文动词集合（`write`/`save`/`create`/`append`/`output to`/`into`） |
| `:1345-1346` | `WRITE_INTENT_PATH_RE` = 盘符/相对前缀 + `[A-Za-z0-9_.…]` + **扩展名枚举** `md|py|ts|tsx|js|json|ya?ml|log|txt|ps1|sh` |
| `:1392-1416` | `collectWriteIntentHits`：去 fenced code → 按行 → 按 `。；！？;` 切 clause → 逐 verb → gap → `WRITE_INTENT_PATH_RE.exec(after.slice(gapLen))` 且 **`pm.index !== 0` 即放弃**（`:1405-1406`）→ 5 guard → push + break |
| `:1423-1431` | `isWhitelistedWriteTarget`：`\\`→`/`、取 basename → `WORKER_FILE_NAME_RE.test(base)` **return true** → `FRAMEWORK_TASK_BASENAMES.includes(base)` **return true** → `path.resolve(projectRoot, pathToken)` 与 `path.resolve(taskDir)` 纯字符串（大小写敏感）前缀比较 |
| `:1444-1461` | `judgeWriteIntent`：仅对 `isWritelessRole && !isShellRole` 生效；`allowForeignWrite` 短路 |
| `worker/worker-file-tool.ts:41` | `WORKER_FILE_NAME_RE = /^(?:progress\.md\|report\.md\|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/` |

现实现的两处漏放方向（fail-open）：
- **A3**：`hits` 由扩展名枚举决定 ⇒ 枚举外扩展名 = 完全不判（不是「判为安全」，是「没看见」）。
- **A4**：basename 命中即放行 ⇒ 任何目录下的 `output.md`/`report.md`/`task.md`/`trace.log`/`run.json`/`worker.log` 都放行，包括其它 key。

实测（脚本 1 输出）：
```
写入 config.toml               -> hits=[] 
写入 Makefile                  -> hits=[]
写入 .env                      -> hits=[]
写入 x.html                    -> hits=[]
写入 x.rs                      -> hits=[]
写入 .agenticdoc/_index.parallel          -> hits=[]   # 现实现也漏（扩展名 .parallel 不在枚举）
写入 .agenticdoc/_workers.parallel        -> hits=[]
写入 .git/config                          -> hits=[]   # 无扩展名
写入 .agenticdoc/<key>/pm-state.md        -> hits=[...] whitelisted=false
写入 packages/coding-agent/src/x.ts       -> hits=[...] whitelisted=false
写入 ../other-key/workers/other-task/output.md -> hits=[...] whitelisted=true   # A4 放行
```

## 2. 目标集轴设计：放弃扩展名白名单，改「禁止面 + 未识别即拒」

### 2.1 判据必须覆盖的禁止面（仓库真实结构取证）

关键观察：**允许面只有一个**（本任务的 `<taskDir>`，加上框架自己的 `output.md` 回写通道），所以「禁止面」不需要枚举——枚举永远不全。正确形态是「不在允许面内就拒」+ 少量**优先级 deny 前缀**（用于理由文案、以及将来 `write_scope:` 放宽时的兜底，与 AC-005b 的 deny-first 顺序对齐：`worker-mode.ts:923-934` + `:959-998`）。

| 禁止面 | 真实证据（只读实测） | 现实现 | 新轴 |
| --- | --- | --- | --- |
| `.agenticdoc/<key>/pm-state.md` | 55 个 key 中 45 个有 `pm-state.md`（`rg --files -g pm-state.md .agenticdoc`）；`mw-gate-verdict-hardening/` 下内容为 `evidence/ tasks/ workers/ achieved.md design.md evidence-requirement.md key-decision.md plan.md pm-state.md spec.md` | 拦得住（`.md` 在枚举内 + basename 不在白名单） | 拦（不在允许面） |
| `<key>/workers/_workers*` | `.agenticdoc/_workers.parallel`、`_workers.acked`、`_workers.stale.parallel`、`mw-dispatch-flow-fixes/_workers.parallel`（共 4 个 `_workers*`） | **漏**（扩展名 `.parallel`/`.acked` 不在枚举） | 拦 |
| `.agenticdoc/_index.parallel` / `_index.md` | 根目录有 `_index.parallel`、`_index.md`、`_impl_gate.log`、`_pitfalls.md`、`_project_log.md`、`_arch_snapshot.md`、`goal.md` | **漏**（`.parallel` 等不在枚举） | 拦 |
| 其它 key（`.agenticdoc/<other-key>/**`） | 55 个 key、305 个 `task.md` | **部分漏**：`…/workers/other-task/output.md` 被 A4 放行 | 拦（目录比较先于 basename） |
| 本 key 但非 taskDir：`<key>/evidence/**`、`<key>/spec.md`、`<key>/tasks/**` | 同上目录清单 | 拦（不在 taskDir） | 拦（writeless 角色只有 `worker_file`，写不进 `evidence`；**不要**照 AC-005b 把 `<key>/evidence` 并为允许面，否则现测试 `truePositive.length===1` 会红，见 §5） |
| `packages/**` | `packages/` 下 11 个包（agent, ai, client, coding-agent, evals, multi-workers, protocol, server, session-backends, tui） | 拦（若扩展名在枚举内） | 拦 |
| `.git/**` | `.git/` | **漏**（无扩展名） | 拦 |
| `.mw/**` | `.mw/dispatch.yml`、`mw.pid`、`mw.log`、`proxy.log`、`conductor.log`、`launcher-beat.<pid>`×19、`window-model/` | 拦 `.yml`，漏无扩展名者 | 拦 |
| 工程根散落文件 | `AGENTS.md CONTRIBUTING.md LICENSE README.md SECURITY.md biome.json package.json package-lock.json tsconfig.json tsconfig.base.json vitest.base.ts test.sh pi-test.bat pi-test.ps1 pi-test.sh hello-world.txt tui-plan.md context-autosave-*.md .npmrc .gitattributes .gitignore`；目录 `docs/ scripts/ node_modules/ tmp/ .tmp/ .agents/ .pi/ .claude/ .codex-fix/ .github/ .husky/ .pytest_cache/ .agentic-framework/ .agenticTask/ .mw/` | 部分（枚举内外混杂） | 拦 |
| 任务自己新建的其它名字（`Makefile`/`Dockerfile`/`x.rs` 等） | 本仓库根目录当前**没有** `Makefile`（`ls` 实测） | **漏** | 见 §2.4 |

补充证据：**本 key 的 `evidence/` 也不该放过**——AC-005b 运行期守卫把 `<key>/evidence` 算作 shell 角色的允许面（`worker-mode.ts:961-968`），但派发期谓词面对的 writeless 角色没有 bash，只有 `worker_file`（写面 = taskDir）。实测把 `<key>/evidence` 并入允许面会让语料违规数从 1 变 0（那条已知真阳正是 `<key>/evidence/quality-gate-report-*.md`），与现测试断言冲突。

### 2.2 去掉扩展名白名单后如何发现路径 token

推荐算法（伪代码，不写实现）：

```
命中 verb（复用 :1399-1404 的 verb + gap 逻辑，window 仍 32）
→ 关键改动 A3-1：在 verb 之后、gap 窗口内的剩余 clause 里「向前扫描第一个路径形状 token」
   而不是只取第一个词、也不要求 pm.index === 0
→ 关键改动 A3-2：token 形状判定取代扩展名枚举
     looksLikePathToken(t) =
        含 "/" 或 "\\"                       # 有目录成分
     || /^\.[A-Za-z0-9_]/                    # 点前导：.env / .gitignore / ./
     || /\.[A-Za-z0-9]{1,8}$/                # 「扩展形状」，不枚举具体扩展
     || fs.existsSync(path.resolve(projectRoot, t))   # 无扩展名但真实存在（Makefile/README）
     || t.includes(":")                      # 盘符或 ADS，可疑面（见 §3）
     且 必须有字母数字（纯标点如 "/" 不是候选）
→ 保留 5 个 allow-guard（:1305-1342）
→ 判定：
     deny 前缀优先（pm-state.md / workers/_workers* / _index.parallel / .agenticdoc 下非本 key / packages/** / .git/**）
     → isSameOrUnder(normalize(taskDir), token) ⇒ allow
     → 裸 token（无目录成分）且 ∈ WORKER_FILE_NAME_RE | FRAMEWORK_TASK_BASENAMES ⇒ allow（框架通道）
     → looksLikePathToken ⇒ refuse
     → 否则不判（非路径）
```

要点：
- 用「形状」而不是「扩展名表」：`config.toml`/`x.rs`/`x.html` 命中 `\.[A-Za-z0-9]{1,8}$`；不需要维护扩展名清单，也不会因为新语言/新配置文件类型而重新 fail-open。
- 用「向前扫描第一个形状 token」而不是「第一个词必须匹配」：修掉 `:1406` 的整条放弃（实测漏放：`Output: write your report to H:\...\report.md` 与 `PM will write your output verbatim to \`…evidence/quality-gate-report-<timestamp>.md\``）。
- 允许面判定必须在 basename 判定**之前**（修 A4）；basename 白名单只在「裸 token（不含 `/`、`\`）」时生效。

### 2.3 误报如何控制（反例清单，含真实语料实测）

| 反例 | 形状判定结果 | 判据（避免误报） | 本语料实测 |
| --- | --- | --- | --- |
| `1.2.3`（版本号） | `\.[A-Za-z0-9]{1,8}$` 命中 ⇒ 会误拒 | 加 `^\d+(\.\d+)+$` ⇒ 非路径 | 0 例 |
| `e.g.` / `i.e.` / `etc.` | 剥尾点后为 `e.g`，扩展形状仍命中 ⇒ 会误拒（尾点本身不命中） | 缩写停用表（大小写不敏感）。**不能用「扩展名白名单」修**，那是回到 A3 | 0 例 |
| `foo.bar`（点分标识符） | 扩展形状命中 ⇒ 会误拒 | 无本地判据：与真实文件形状不可区分。只有 existsSync（存在且在允许面内 ⇒ allow，否则拒）或人工 `allow_foreign_write` | 0 例 |
| `your` / `design` / `mcp` / `side` / `surface` / `message_update`（真实语料 6 个裸词） | 裸词（无分隔符、无扩展形状、不存在）⇒ **不作为候选**，不参与拒判 | 「未识别即拒」只作用于形状 token | 实测出现在 9 本 task.md 中；若裸词也拒 ⇒ 9/26 本（35%）假阳性，见 §5 |
| `README`（无扩展名、可能不存在） | 存在 ⇒ 在允许面外 ⇒ 拒（对的）；不存在 ⇒ 不判（可能漏） | 与 `Makefile` 同族 | 0 例 |
| `-pattern`（`known-write-pattern` 的 markdown 上下文）、`/`（来自 `` `process.stdout.write`/`print` ``） | `-pattern` 是裸词 ⇒ 非候选；`/` 含分隔符 ⇒ 形状命中 ⇒ 会误拒 | 必须有字母数字 ⇒ 纯标点非候选；另建议补 **inline-code guard（反引号 span）** | 各 1 例 |

### 2.4 可行性判定

- **「形状 token 的未识别即拒」可行**：成本已量化（§5），在 26 本 writeless 语料上假阳性增量 = 0。
- **「无扩展名裸文件名的未识别即拒」不可行**：裸词与散文词在词法上不可区分，一律 fail-closed 的代价是 35% 假阳性。只能：deny-name 表（`Makefile makefile GNUmakefile Dockerfile Containerfile Rakefile Gemfile Procfile Vagrantfile Justfile Brewfile`）+ `existsSync`（文件已存在时兜住）。残余：**新建的、名字不在表里、且当前不存在的**裸文件名（例如 `Justfile` 变体、项目自造 `Taskfile`）仍漏。这是把 `Makefile` 类样例拦下的唯一代价路径，建议接受（deny-name 表可随审计增长）。
- 另需要补的 guard（与 A3 无关但同族）：① inline-code（反引号 span）——`process.stdout.write` 这类行内代码会产出 token `/`；② 英文 PM 归因（`PM will write`）——`:1338` 只有中文形态，语料里已有 `PM will write your output verbatim to …` 一例被当成 worker 写指令。

## 3. 5 个漏放样例逐条判定（QG-B 原样例）

| 样例 | 现实现命中数 | 纯形状变体（V-A） | +deny-name（V-C） | 依据 |
| --- | --- | --- | --- | --- |
| `config.toml` | 0（漏） | **拦** | 拦 | `\.[A-Za-z0-9]{1,8}$` 命中；resolve 到 `<projectRoot>/config.toml`，不在 taskDir |
| `Makefile` | 0（漏） | **仍漏**（无分隔符、无点、无扩展形状、本仓库根目录无此文件 ⇒ `existsSync` 不命中） | **拦** | deny-name 表；若目标仓库根真有 `Makefile`，纯形状变体的 `existsSync` 也能兜住 |
| `.env` | 0（漏） | **拦** | 拦 | `^\.[A-Za-z0-9_]` 点前导 |
| `x.html` | 0（漏） | **拦** | 拦 | 扩展形状 |
| `x.rs` | 0（漏） | **拦** | 拦 | 扩展形状 |

⇒ **`leak_caught = 4/5`（纯形状）**，**`5/5`（+deny-name）**。若改用 §2.4 的严格变体（裸词也拒）也是 5/5，但代价是 §5 的 9 本假阳性。现实现为 **0/5**。

## 4. Windows 路径归一的判定边界（交付物 3）

实测环境：Node v24.19.0 / Windows（`process.platform === "win32"`，`path.sep === "\\"`）。探针脚本 3（附录 C）。

| 要素 | 实测 | 可否静态判定 | 建议处理 | 残余风险 |
| --- | --- | --- | --- | --- |
| `path.resolve`：`..`/`.`/混合分隔符/重复分隔符 | `packages/../package.json` → `H:\git\Multi-Workers\package.json`；`.//package.json` 同上；`AGENTS.md/..` → repo 根 | 可 | 第一步统一 `path.resolve(projectRoot, token)`（win32 同时接受 `\` 与 `/`） | 无 |
| 大小写不敏感比较 | `PACKAGE.JSON` → realpath 原样返回（stat 成功 4268B）；`H:/GIT/MULTI-WORKERS/package.json` → `H:\GIT\MULTI-WORKERS\package.json`；`h:/GIT/multi-workers/PACKAGE.JSON` → 原样。⇒ **realpath 不归一大小写，也不归一盘符大小写** | 可 | 必须两侧 `toLowerCase()`（直接复用 `worker/read-scope.ts:89 isSameOrUnder`，它就是 win32 小写比较） | 无（比较层解决）。但 `ui-bridge.ts:1428-1430` 现在是大小写敏感的字符串前缀比较：allow 方向误拒、deny 方向（若用前缀 deny）可被大小写绕过 |
| 盘符相对 `C:foo.md`、`C:foo\bar.md` | resolve → `C:\foo.md`（按 Node 的 per-drive cwd，即 `=C:` 环境态）；realpath/stat `ENOENT` | 可判「不在允许面 ⇒ 拒」 | 单列规则 id（如 `win32-drive-relative`），不要用「不存在」当理由 | 真实指向由 worker 进程同盘 cwd 决定，PM 无法静态得知；只会造成假阳性（安全方向） |
| UNC `\\server\share\x.md`、`//server/share/x.md` | resolve 均归一为 `\\server\share\x.md`；realpath `ENOENT`（未访问） | 可 | 不在允许面 ⇒ 拒 | 共享映射到允许面内（如 `\\localhost\C$…`）⇒ 假阳性 |
| `\\?\` 长路径前缀 | `\\?\H:\…\package.json` 与 `//?/H:/…`：realpathSync `EISDIR`，statSync 成功（4268B）⇒ `normalizeForCompare` 的最深存在祖先链失败，退化为词法串 | 可（fail-closed） | 不在允许面 ⇒ 拒；无需特判 | 合法 `\\?\` 引用被误拒（假阳性） |
| 尾点 / 尾空格 | `package.json.`、`package.json `：realpathSync 与 statSync **均 ENOENT**（本 Node/Windows 不剥 Win32 尾点尾空格） | 可 | 形状判定前剥尾点尾空格（与 Win32 CreateFile 语义一致），并写进 reason | 无漏放（无论 OS 剥不剥，`…/report.md.` 都落在 taskDir 内）；第三方工具若剥除则指向同一文件，语义一致；仅假阳性 |
| ADS（`::$DATA`） | `package.json::$DATA`：realpath 返回原串，stat = 4268（= 基文件大小）⇒ 指向同一文件的数据流 | 可 | token 含 `:` 且不匹配 `^[A-Za-z]:[\\/]` ⇒ 拒（规则 `win32-ads`） | 无漏放（同文件）；Win32 文件名本身不允许 `:`，误拒面极小 |
| junction / symlink | `realpathSync` 解析；`read-scope.ts:100-114` 已含「最深存在祖先回接」。实测 `.agenticdoc`/`packages`/`.mw`/`.agents`/`docs`/`scripts`（深度 3，跳过 node_modules/.git）**0 个 reparse point** ⇒ 当前 realpath 是空操作 | 可（fs 调用） | 派发期沿用 `normalizeForCompare`，与运行期 `worker-mode.ts:959 checkBashWriteScopeTarget` 语义一致 | 失败模式（ENOENT/EACCES/EISDIR）全部退化为词法 ⇒ allow 方向 fail-closed。残余：TOCTOU（派发后 symlink 被改）+ 只读一次 realpath；AC-005b 运行期守卫会在写入时再判 |
| 非 ASCII 文件名（`写入 报告.md`） | token 字符集是 ASCII（`[A-Za-z0-9_.\\/~:-]`），中文名扫不到 | **未验证**（本轮未构造样本） | 改成「按空白/引号/中文标点切词 → 剥标点 → 形状判定」：`报告.md` 会命中扩展形状，`报告` 仍不可判 | 中文裸文件名漏放（与 A3 同族的新缺口，建议单列） |

结论：**判定边界可以收敛到「`path.resolve` + realpath（含最深存在祖先）+ win32 小写 + 段边界前缀比较」四步**，这与 `worker/read-scope.ts:89-114` 的既有实现逐字一致，不需要新造规则；所有 Win32 怪癖都落在「拒绝」侧，风险只有假阳性。派发期是否需要 fs：**建议需要**（只是只读 `realpathSync`），否则派发期与运行期的 allow 面会不一致；若要零 fs，可退化为纯词法 `path.resolve`（当前语料 0 symlink，代价为 0；残余是未来 junction 场景的假阳性/假阴性）。

## 5. 回归不恶化：语料度量与预期数值（交付物 5）

语料与算法（与 `test/suite/mwds-t02-write-intent.test.ts` 对齐）：
- 测试的扫描器 `findCorpusTaskMds`（`:69-92`）等价于 `.agenticdoc/<key>/workers/<taskKey>/task.md` 单层遍历；本仓库实测：55 个 key、**305** 个 `task.md`、`type:` 属于 `isWritelessRole && !isShellRole` 的 **26 本**（测试断言 `books.length >= 24`，`:261`）。
- 我在只读脚本里**逐字复刻**了 `collectWriteIntentHits`（同一套 verb 表、gap 窗口、扩展名正则、5 个 guard；guard 词表从源码文本按 UTF-8 读出，避免 shell 编码损坏），并做了**忠实性自检**：26 本书上与真实 `collectWriteIntentHits` 的命中序列（verb+path）**逐条一致，mismatches=0**。因此下表的新轴数值可信。
- 新轴原型参数：允许面 = 本 taskDir（`normalizeForCompare` + win32 小写 + 段边界）；裸 token ∈ `WORKER_FILE_NAME_RE` 或 `FRAMEWORK_TASK_BASENAMES` ⇒ allow；`PUNCT`（无字母数字）⇒ 非候选；其余形状 token 在允许面外 ⇒ 违规。

| 轴 | 命中数 | 命中文件 | 违规数 | 违规任务 | 假阳性 | 现测试断言（`:251-263`） |
| --- | --- | --- | --- | --- | --- | --- |
| CURRENT（现实现） | 2 | 2 | 1 | 1（`mwg-qg-review-20261010`） | **0** | `falsePositives=[]` ✓ / `truePositive.length===1` ✓ |
| HYP-A（形状 token，不拒裸散文词） | **13** | 10 | 1 | 1（同一条真阳） | **0** | 同上，**两断言仍成立**（`hits` 从 2 变 13 只影响 console.log） |
| HYP-B-extra（裸 token 也 fail-closed） | 13 | 10 | 11 | 10 | **10**（9 本，35%） | `falsePositives=[]` **会红** |

- HYP-A 的违规明细（唯一一条，= 已知真阳，与现实现逐字相同）：
  `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-qg-review-20261010/task.md :: .agenticdoc/mw-gate-verdict-hardening/evidence/quality-gate-report-review-20261010.md`
  （注意：这条在「taskDir 允许面」下是违规；若允许面并入 `<key>/evidence` 则变 0 违规 ⇒ `truePositive.length===1` 断言会红。**不要并入**，见 §2.1。）
- HYP-A 新增的 12 条命中全部良性：1 条裸 `output.md`（框架通道，第 5 步 allow）、1 条 `/`（行内代码 `process.stdout.write`，PUNCT 非候选）、10 条裸散文词（`your`×2、`design`×2、`mcp`×2、`side`、`surface`、`message_update`、`-pattern`，非候选）。
- HYP-B 的 10 条假阳性明细（token → 文件）：`your` → `msc-qg-quality-gate`、`fmr-review-spec-design`；`side` → `code-review-1`；`-pattern` → `mds-qg-b-code-adversarial`；`design` → `mwg-qg-review-20261010`、`mwg-qg2b-code-adversarial`；`surface` → `mwg-qg2b-code-adversarial`；`mcp` → `mw-rag-integration-design-critique`、`mw-rag-integration-design-review`；`message_update` → `mw-rag-integration-ref-verify`。

**PM 运行时期望值**（seed 测试 `packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`）：
- 现状运行应打印 `[VERIFY] VC-015: corpus=305 read_only_books=26 hit_files=2 hits=2 false_positives=0 violations=1 unique_true_positive=true`（`corpus=` 会随新 task.md 增长；`hits=2`/`false_positives=0` 是 RQ 记录值，本次复现一致）。
- 新轴（HYP-A）落地后应为 `hits=13 false_positives=0 violations=1 unique_true_positive=true`（只要不把 `<key>/evidence` 并入允许面）。测试断言本身**不需要改**（只断言 FP=0 与 TP=1），但若别处有「命中数」断言或 golden 文本，需要同步为 13。
- 若采用 HYP-B，`false_positives` 会变成 10 ⇒ 测试红；这就是「裸词也 fail-closed」不可接受的量化依据。

## 6. 谓词形态建议（交付物 4，不写实现）

新 `isWhitelistedWriteTarget` 判定顺序（fail-closed，deny 优先）：

```
normalized = normalizeForCompare(projectRoot, token)        // resolve + realpath(最深存在祖先) + win32 小写比较
1) deny 前缀（最高优先级，永不被 write_scope / allow_foreign_write 之外的东西放宽）
   pm-state.md | <key>/workers/_workers* | .agenticdoc/_index.parallel
   | .agenticdoc 下非本 key 的路径 | packages/** | .git/**            -> refuse(rule=deny)
2) isSameOrUnder(normalize(taskDir), normalized)                       -> allow
3) token 无目录成分（不含 "/" 或 "\"）
   且 (WORKER_FILE_NAME_RE.test(token) || FRAMEWORK_TASK_BASENAMES.includes(token))
                                                                       -> allow（框架通道）
4) looksLikePathToken(token)（§2.2 的形状判定，纯标点除外）             -> refuse(rule=scope)
5) 否则                                                                -> 不判（非路径）
```

关键点：
- **目录解析先于 basename**（修 A4）：第 3 步只在「裸 token」时生效，`../other-key/…/output.md`、`<other-key>/workers/x/report.md`、`.agenticdoc/other/evidence/task.md` 都不再命中 basename 白名单。
- **形状判定取代扩展名枚举**（修 A3）：第 4 步不枚举扩展名。
- token 发现侧：`WRITE_INTENT_PATH_RE` 的替代方案 = 「verb + gap 窗口内向前扫描第一个形状 token」+ 形状函数 `looksLikePathToken`；同时删掉 `:1406` 的 `pm.index !== 0` 整条放弃语义。建议顺手把 `inline-code`（反引号 span）与英文 PM 归因（`PM will write`）补进 guard 族。
- deny 前缀与 AC-005b（`worker-mode.ts:923-934`）保持同一张表、同一优先级，避免派发期与运行期判定不一致。

正例（3）：
1. `写入 .agenticdoc/<key>/workers/<task>/report.md` → 第 2 步 allow（在 taskDir 内，扩展名任意）。
2. `写到 output.md`（裸名，框架回写通道）→ 第 3 步 allow。
3. `追加 progress.md`、`worker_file file="report-<slug>.md"` → 第 3 步 allow。

反例（3）：
1. `写到 ../other-key/workers/other-task/output.md` → 含目录成分，第 3 步不适用；第 2 步不在 taskDir ⇒ **refuse**（修 A4 的关键用例；现实现 `= true` 放行）。
2. `写入 packages/coding-agent/src/x.ts` → 第 1 步 deny（`packages/**`）。
3. `写到 .agenticdoc/other-key/evidence/x.md` → 第 1 步 deny（`.agenticdoc` 下非本 key）。

A3 类反例（现实现漏、新轴拦）：`写入 config.toml`、`写到 x.rs`（第 4 步）；`写入 .agenticdoc/_index.parallel`（第 1 步）。

## 7. 顺带实测的同类误报（佐证「词法猜形状」的风险）

- 运行期 bash 写面守卫的 tokenizer（`worker-mode.ts:667 tokenizeShellCommand`，注释自称 quote-aware）在 PowerShell here-string 里被**单个单引号 desync** 后，把 JS 代码里的 `>` 当成 shell 重定向，取下一个 token 当作写入目标，交给 `:959 checkBashWriteScopeTarget` 报 `[rule=scope]` 拒绝。最小复现与输出见附录 A：`gapLen` 被当成「被写入的路径」。
- `>` / `=>` 出现在**引号配对成功**的上下文里则不会被判（实测 `2 > 1` 正常执行）⇒ 该误报是「引号态推算 + 运算符切分」的共同产物，与 RQ-3 的 token 发现是同一族问题。
- 同一守卫还把**未展开的环境变量**当字面量路径：本任务中我原本想 `Set-Content "$env:TEMP\rq3-probe.mjs"`，被报 `write-scope: blocked bash write to $env:TEMP\rq3-probe.mjs`（rule=scope）。最终所有脚本改走 stdin，仓库无临时文件残留。

## 附录 A：bash 守卫误报最小复现（脚本与输出）

```powershell
$s = @'
const re = /["']/g;
if (2 > gapLen) console.log("x");
'@; $s | node --input-type=module -
```
输出：
```
write-scope: blocked bash write to gapLen: outside the worker write surface [rule=scope]; allowed: H:\git\Multi-Workers\.agenticdoc\mw-guard-form-hardening\workers\mwgf-rq3-path-resolution or H:\git\Multi-Workers\.agenticdoc\mw-guard-form-hardening\evidence
```
（对照组 `node -e "console.log(2 > 1)"` 与「引号配平的 here-string」都正常执行。）

## 附录 B：脚本 1（5 样例 + A4 白名单探针）与输出

```js
import { collectWriteIntentHits, isWhitelistedWriteTarget, WRITE_INTENT_VERBS } from "file:///H:/git/Multi-Workers/packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts";
const PROJECT = "H:\\git\\Multi-Workers";
const TASK_DIR = "H:\\git\\Multi-Workers\\.agenticdoc\\mw-guard-form-hardening\\workers\\mwgf-rq3-path-resolution";
const W = WRITE_INTENT_VERBS[2];           // "写入"（从模块取，避免 shell 编码损坏）
const esc = (o) => JSON.stringify(o).replace(/[^\x20-\x7e]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
const targets = ["config.toml","Makefile",".env","x.html","x.rs",".agenticdoc/_index.parallel",".agenticdoc/_workers.parallel",".agenticdoc/<key>/pm-state.md",".agenticdoc/other-key/workers/other-task/output.md","packages/coding-agent/src/x.ts","AGENTS.md",".git/config",".mw/dispatch.yml","../other-key/workers/other-task/output.md"];
for (const t of targets) {
  const hits = collectWriteIntentHits(W + " " + t);
  console.log(esc({t, hits: hits.map(h=>h.path), wl: hits.map(h=>isWhitelistedWriteTarget(h.path,{taskDir:TASK_DIR,projectRoot:PROJECT}))}));
}
```
输出：
```
{"t":"config.toml","hits":[],"wl":[]}
{"t":"Makefile","hits":[],"wl":[]}
{"t":".env","hits":[],"wl":[]}
{"t":"x.html","hits":[],"wl":[]}
{"t":"x.rs","hits":[],"wl":[]}
{"t":".agenticdoc/_index.parallel","hits":[],"wl":[]}
{"t":".agenticdoc/_workers.parallel","hits":[],"wl":[]}
{"t":".agenticdoc/<key>/pm-state.md","hits":[".agenticdoc/<key>/pm-state.md"],"wl":[false]}   # 实际用的是 mw-guard-form-hardening
{"t":".agenticdoc/other-key/workers/other-task/output.md","hits":[".agenticdoc/other-key/workers/other-task/output.md"],"wl":[true]}
{"t":"packages/coding-agent/src/x.ts","hits":["packages/coding-agent/src/x.ts"],"wl":[false]}
{"t":"AGENTS.md","hits":["AGENTS.md"],"wl":[false]}
{"t":".git/config","hits":[],"wl":[]}
{"t":".mw/dispatch.yml","hits":[".mw/dispatch.yml"],"wl":[false]}
{"t":"../other-key/workers/other-task/output.md","hits":["../other-key/workers/other-task/output.md"],"wl":[true]}
```

## 附录 C：脚本 3（Windows 归一探针）与输出

```js
import * as fs from "node:fs"; import * as path from "node:path";
const REPO = "H:\\git\\Multi-Workers";
for (const c of ["package.json","package.json.","package.json ","package.json::$DATA","package.json/.","AGENTS.md/..","PACKAGE.JSON","packages/../package.json",".//package.json","//?/H:/git/Multi-Workers/package.json","\\\\?\\H:\\git\\Multi-Workers\\package.json","C:package.json","constructor:foo"]) {
  let rp = null, err = null, st = null;
  try { rp = fs.realpathSync(path.resolve(REPO, c)); } catch (e) { err = e.code; }
  try { st = fs.statSync(path.resolve(REPO, c)).size; } catch (e) { st = e.code; }
  console.log(JSON.stringify({ c, resolved: path.resolve(REPO, c), realpath: rp, realpathErr: err, stat: st }));
}
```
输出（节选，编码为 JSON 转义后的可读形式）：
```
package.json            resolved=H:\git\Multi-Workers\package.json            realpath=同上           err=null  stat=4268
package.json.           resolved=…\package.json.                              realpath=null          err=ENOENT stat=ENOENT
package.json            (尾空格)                                              realpath=null          err=ENOENT stat=ENOENT
package.json::$DATA     resolved=…\package.json::$DATA                        realpath=原串           err=null  stat=4268
PACKAGE.JSON            resolved=…\PACKAGE.JSON                               realpath=原串(不归一)    err=null  stat=4268
H:/GIT/MULTI-WORKERS/package.json                                             realpath=H:\GIT\MULTI-WORKERS\package.json
h:/GIT/multi-workers/PACKAGE.JSON                                             realpath=原串(不归一)
Packages/coding-agent/package.json                                            realpath=…\Packages\coding-agent\package.json
packages/../package.json                                                      realpath=H:\git\Multi-Workers\package.json
AGENTS.md/..                                                                  realpath=H:\git\Multi-Workers
\\?\H:\git\Multi-Workers\package.json                                         realpath=null err=EISDIR stat=4268
//?/H:/git/Multi-Workers/package.json                                         realpath=null err=EISDIR stat=4268
C:package.json                                                                resolved=C:\package.json realpath=null err=ENOENT
symlink/junction 扫描（.agenticdoc/packages/.mw/.agents/docs/scripts，深度3，跳过 node_modules/.git）= 0
```

## 附录 D：脚本 2（语料度量：CURRENT / HYP-A / HYP-B）与输出

脚本要点：guard 词表与 clause 分隔符从源码文本按 UTF-8 读出（避免 PowerShell→node stdin 的编码损坏）；先用原扩展名正则做忠实性自检，再切新轴。入口为 `$s | node --input-type=module -`（无仓库临时文件）。

```js
import * as fs from "node:fs";
import * as path from "node:path";
import { collectWriteIntentHits, isWhitelistedWriteTarget, WRITE_INTENT_VERBS } from "file:///H:/git/Multi-Workers/packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { isWritelessRole, isShellRole } from "file:///H:/git/Multi-Workers/packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts";
const REPO = "H:\\git\\Multi-Workers";
const SRC = REPO + "\\packages\\coding-agent\\src\\extensions\\agent-team-loop\\pm\\ui-bridge.ts";
const src = fs.readFileSync(SRC, "utf8");
function arr(n) { const at = src.indexOf("const " + n); const open = src.indexOf("[", at); const close = src.indexOf("];", open);
  const body = src.slice(open + 1, close); const out = []; const reStr = /(["'])((?:\\.|(?!\1)[\s\S])*)\1/g; let x;
  while ((x = reStr.exec(body)) !== null) out.push(x[2].replace(/\\(.)/g, "$1")); return out; }
const NEG = arr("WRITE_INTENT_NEGATIONS"), READ = arr("WRITE_INTENT_READ_MARKERS"), PMA = arr("WRITE_INTENT_PM_ATTRIBUTIONS");
const ENG = new Set(arr("WRITE_INTENT_ENGLISH_VERBS"));
const flat = arr("WRITE_INTENT_QUOTE_PAIRS"); const QP = [];
for (let i = 0; i < flat.length; i += 2) QP.push([flat[i], flat[i + 1]]);
const SEP = new RegExp("[" + /line\.split\(\/\[([\s\S]*?)\]\/\)/.exec(src)[1] + "]");   // clause 分隔符（避免手打中文）
const WINDOW = 32;
const ORIG_RE = /(?:[A-Za-z]:[\\/]|\.{1,2}\/)?[A-Za-z0-9_.][A-Za-z0-9_./-]*\.(?:md|py|ts|tsx|js|json|ya?ml|log|txt|ps1|sh)\b/;
const WIDE_RE = /^[A-Za-z0-9_.\\/~:-]+/;                                               // 新轴：不再枚举扩展名
const FRAMEWORK = ["task.md","trace.log","output.md","run.json","worker.log"];
const WORKER_RE = /^(?:progress\.md|report\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\.md)$/;
const DENY_NAME = ["Makefile","makefile","GNUmakefile","Dockerfile","Containerfile","Rakefile","Gemfile","Procfile","Vagrantfile","Justfile","Brewfile"];
function findVerb(clause, verb) { const low = clause.toLowerCase(); const needle = verb.toLowerCase();
  if (ENG.has(needle)) { const re = new RegExp("(?<![A-Za-z0-9_])" + needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![A-Za-z0-9_])"); const m = re.exec(low); return m ? m.index : -1; }
  return low.indexOf(needle); }
function inQ(clause, token) { const at = clause.indexOf(token); if (at === -1) return false;
  for (const pair of QP) { let st = clause.indexOf(pair[0]);
    while (st !== -1 && st < at) { const en = clause.indexOf(pair[1], st + 1); if (en === -1) break; if (at + token.length <= en) return true; st = clause.indexOf(pair[0], st + 1); } } return false; }
function collect(text, re, wide) { const body = text.replace(/```[\s\S]*?```/g, ""); const hits = [];
  for (const line of body.split(/\r?\n/)) for (const clause of line.split(SEP)) { const low = clause.toLowerCase();
    for (const verb of WRITE_INTENT_VERBS) { const pos = findVerb(clause, verb); if (pos < 0) continue;
      const after = clause.slice(pos + verb.length); const gap = /^\s*[`"']?\s*/.exec(after); const gapLen = gap ? gap[0].length : 0;
      if (WINDOW < gapLen) continue; const pm = re.exec(after.slice(gapLen)); if (!pm || pm.index !== 0) continue;
      let token = pm[0]; if (wide) { token = token.replace(/[.]+$/, ""); if (token.length === 0) continue; }
      const before = low.slice(Math.max(0, pos - 20), pos);
      if (NEG.some(n => before.includes(n))) continue;
      if (READ.some(r => low.includes(r))) continue;
      if (PMA.some(a => low.includes(a))) continue;
      if (inQ(clause, token)) continue;
      hits.push({ verb, path: token, clause: clause.trim() }); break; } } return hits; }
const IS_WIN32 = process.platform === "win32";
function norm(p) { const abs = path.resolve(REPO, p); let cur = abs; const tail = [];
  for (;;) { try { return path.join(fs.realpathSync(cur), ...tail); } catch {}
    const parent = path.dirname(cur); if (parent === cur) return abs; tail.unshift(path.basename(cur)); cur = parent; } }
function under(a, c) { const x = IS_WIN32 ? a.toLowerCase() : a; const y = IS_WIN32 ? c.toLowerCase() : c; return y === x || y.startsWith(x + path.sep); }
function inside(td, t) { return under(norm(td), norm(t)); }
function shape(t) { if (!/[A-Za-z0-9]/.test(t)) return "PUNCT";
  if (/[\\/]/.test(t)) return "SEP"; if (/^\.[A-Za-z0-9_]/.test(t)) return "DOTLEAD";
  if (/\.[A-Za-z0-9]{1,8}$/.test(t)) return "EXT"; if (DENY_NAME.includes(t)) return "DENYNAME";
  if (fs.existsSync(path.resolve(REPO, t))) return "EXISTS"; if (t.includes(":")) return "COLON"; return "BARE"; }
// corpus
const root = path.join(REPO, ".agenticdoc"); const books = [];
for (const key of fs.readdirSync(root)) { const workers = path.join(root, key, "workers"); let tks;
  try { tks = fs.readdirSync(workers); } catch { continue; }
  for (const tk of tks) { const f = path.join(workers, tk, "task.md"); if (!fs.existsSync(f)) continue;
    const text = fs.readFileSync(f, "utf8"); const type = /^type:\s*(\S+)\s*$/m.exec(text)?.[1] ?? "";
    if (isWritelessRole(type) && !isShellRole(type)) books.push({ file: f, text, taskDir: path.join(workers, tk) }); } }
// self-check：新轴脚本必须能复现真实 collectWriteIntentHits
let mism = 0;
for (const b of books) { const real = collectWriteIntentHits(b.text); const mine = collect(b.text, ORIG_RE, false);
  const same = real.length === mine.length && real.every((x, i) => x.path === mine[i].path && x.verb === mine[i].verb);
  if (!same) mism += 1; }
console.log("SELF-CHECK books=" + books.length + " mismatches=" + mism);
const cur = [], hypA = [], hypB = [];
for (const b of books) { const rel = path.relative(REPO, b.file);
  for (const h of collect(b.text, ORIG_RE, false)) if (!isWhitelistedWriteTarget(h.path, { taskDir: b.taskDir, projectRoot: REPO })) cur.push({ f: rel, t: h.path, sh: shape(h.path) });
  for (const h of collect(b.text, WIDE_RE, true)) {
    if (inside(b.taskDir, h.path)) continue;
    const bare = !/[\\/]/.test(h.path);
    if (bare && (FRAMEWORK.includes(h.path) || WORKER_RE.test(h.path))) continue;
    const sh = shape(h.path);
    if (sh === "PUNCT") continue;
    (sh === "BARE" ? hypB : hypA).push({ f: rel, t: h.path, sh }); } }
function stats(tag, rows) { console.log(tag + " rows=" + rows.length + " files=" + new Set(rows.map(r=>r.f)).size +
  " tasks=" + new Set(rows.map(r=>path.basename(path.dirname(r.f)))).size + " " + JSON.stringify(rows.map(r=>r.f + " :: " + r.t + " [" + r.sh + "]"))); }
stats("CURRENT", cur); stats("HYP-A", hypA); stats("HYP-B-extra", hypB);
let wh = 0; for (const b of books) wh += collect(b.text, WIDE_RE, true).length;
console.log("WIDE_total_hits=" + wh + " books=" + books.length);
console.log("hits_current=" + (function(){ let n=0; for (const b of books) n += collectWriteIntentHits(b.text).length; return n; })());
```

输出：
```
SELF-CHECK books=26 mismatches=0
CURRENT rows=1 files=1 tasks=1 [".agenticdoc\mw-gate-verdict-hardening\workers\mwg-qg-review-20261010\task.md :: .agenticdoc/mw-gate-verdict-hardening/evidence/quality-gate-report-review-20261010.md [SEP]"]
HYP-A rows=1 files=1 tasks=1 [同上]
HYP-B-extra rows=10 files=9 tasks=9 [".agenticdoc\mw-autopilot-slot-capacity\workers\msc-qg-quality-gate\task.md :: your [BARE]",".agenticdoc\mw-dispatch-flow-fixes\workers\code-review-1\task.md :: side [BARE]",".agenticdoc\mw-dispatch-settle-gates\workers\mds-qg-b-code-adversarial\task.md :: -pattern [BARE]",".agenticdoc\mw-gate-verdict-hardening\workers\mwg-qg-review-20261010\task.md :: design [BARE]",".agenticdoc\mw-gate-verdict-hardening\workers\mwg-qg2b-code-adversarial\task.md :: surface [BARE]",".agenticdoc\mw-gate-verdict-hardening\workers\mwg-qg2b-code-adversarial\task.md :: design [BARE]",".agenticdoc\mw-l3-fail-marker-forms\workers\fmr-review-spec-design\task.md :: your [BARE]",".agenticdoc\mw-rag-integration\workers\mw-rag-integration-design-critique\task.md :: mcp [BARE]",".agenticdoc\mw-rag-integration\workers\mw-rag-integration-design-review\task.md :: mcp [BARE]",".agenticdoc\mw-rag-integration\workers\mw-rag-integration-ref-verify\task.md :: message_update [BARE]"]
WIDE_total_hits=13 books=26
hits_current=2
```

## 附录 E：5 样例在新轴下的形状判定（脚本 2 的样例分支输出）

```
{"sample":"config.toml","current_hits":0,"wide_token":"config.toml","shape":"EXT","outside_surface":true,"V_A_refuse":true}
{"sample":"Makefile","current_hits":0,"wide_token":"Makefile","shape":"DENYNAME","outside_surface":true,"V_A_refuse":true}   # V_A 含 deny-name 表；纯形状变体为 false，见 §3
{"sample":".env","current_hits":0,"wide_token":".env","shape":"DOTLEAD","outside_surface":true,"V_A_refuse":true}
{"sample":"x.html","current_hits":0,"wide_token":"x.html","shape":"EXT","outside_surface":true,"V_A_refuse":true}
{"sample":"x.rs","current_hits":0,"wide_token":"x.rs","shape":"EXT","outside_surface":true,"V_A_refuse":true}
```

## 附录 F：未验证项

1. 非 ASCII（中文）文件名的 token 发现与判定：本轮未构造样本，未验证。
2. 尾点/尾空格的**写入**侧行为（CreateFile 是否剥除）：只读环境下无法验证；只测了 read 侧（realpath/stat 均 ENOENT）。
3. UNC / `\\?\` 目标是否真实可达（无远端共享可测）：只测了 resolve/realpath 的失败模式。
4. HYP-A 落地后的测试实跑数值：PM 负责运行；本报告的 13/1/0 来自同算法只读复现（自检 mismatches=0）。
5. `allow_foreign_write` 与 `write_scope:` 放宽后 deny 前缀是否仍绝对优先：本报告只给设计建议（对齐 AC-005b 的 deny-first），未实现、未测。

### 补充实测（§7 追加，报告成文后再次触发）

```powershell
git ls-files --error-unmatch <path> 2>$null        # PowerShell 的 null 重定向
```
输出：
```
write-scope: blocked bash write to $null: outside the worker write surface [rule=scope]; allowed: H:\git\Multi-Workers\.agenticdoc\mw-guard-form-hardening\workers\mwgf-rq3-path-resolution or H:\git\Multi-Workers\.agenticdoc\mw-guard-form-hardening\evidence
```
即 PowerShell 的 `2>$null`（丢弃 stderr）也被当作「写入 `$null`」拒绝——与 §7 的「未展开变量当字面量路径」「`>` 在引号态推算出错时被当重定向」同族。这也再次说明：**token 发现环节的误报控制（形状判定 + 非候选豁免）比判定环节的严格性更重要**（新轴若把这类 `\$null`/`<fd>` 形式当路径，会立刻产生假阳性；因此建议显式豁免 `2>`/`1>`/`&>`/`>NUL`/`$null` 等 fd/null 形式）。
