# Design RQ-D5：dist 防复发锚点与脏树护栏设计（只读调研）

- key：`mw-autopilot-verify-cli`（design 期 RQ-D5；对应 spec §1.1.6 / AC-009(c)(d)）
- 日期：2026-09-26
- 快照：`HEAD = b0a30bc12`（工作树受检时仅有未跟踪 `.tmp/`、`hello-world.txt`、`packages/coding-agent/Python/`，**无 tracked 改动**）
- 性质：**只读调研**——未运行任何构建、未改任何项目文件；本文件是唯一写面。
- 引用约定：`mw.py` = `packages/multi-workers/mw.py`，`mw_common.py` = `packages/multi-workers/mw_common.py`；行号以本快照为准。
- 前置证据：`evidence/research/spec-dist-rebuild-20260926.md`（RQ-3）、`evidence/spec-dist-rebuild-performed-20260926.md`（`d52694cc4`）、spec `AC-009`。

---

## 0. 一句话结论

AC-009(c) 的锚点应落成 **update-env 的纯读内容判据（id=`repo-bundle`，layer=`machine`，`auto=True`）+ S1「先 `_build_bundle()` 再 `_deploy_bundle()`」**；内容判据用 **kind 集合（a）+ guard 行为标志（b）+ esbuild 模块路径注释集**，这三样足够覆盖本轮漂移且零误报；`packages/coding-agent/dist` 侧另有一条**免费且更强的通用判据**——tracked `*.map` 的 `sourcesContent` 逐字节比对（实测 236/237 源文件覆盖、40ms、在 `181a75332` 上确实为红）。AC-009(d) 的护栏应拦截 **编译输入路径**（`mw build`：`packages/coding-agent/src`；`mw bootstrap`：`packages/*/src`），用 `git status --porcelain -- <paths>` 子集而非 `git diff --quiet`，并提供 `--allow-dirty`。AC-009(a) 在本机可复现，但有一个**未登记的平台风险**：`npm run build` 的 `shx chmod +x dist/cli.js` 在 `core.fileMode=true` 的主机上会让 `git diff --exit-code` 因 **mode 位**而失败（本机 `core.filemode=false` 掩盖了它）。

---

## 1. Q1 — 锚点机制落点

### 1.1 check dict 形状与既有 A1/A2 的实现差异

- `_check_update_env(project_dir)`：`mw.py:4316-4507`。唯一的写入函数是内嵌的 `add(cid, layer, status, detail, fix="", *, auto=False)`：`mw.py:4322-4323`，
  形状 **`{"id","layer","status","detail","fix","auto"}`**。`status` 取值域（由 `summary` 与文本渲染决定）：`ok / stale / warn / info / skip`（`mw.py:4495-4500`、`_UPDATE_ENV_MARKS` `mw.py:4188`）；`summary.healthy = all(status in (ok,info,skip))`，即 `stale`/`warn` 都不 healthy。
- **A1（全局 bundle，mtime）**：`mw.py:4330-4344`
  - 判据来自 `mw_common._doctor_bundle()`（`mw_common.py:1978-2001`）：对象是**全局副本** `global_ext_dir()/agent-team-loop.js`（`mw_common.py:1637-1641`），比较 `max(源 mtime) > 全局副本 mtime`（`mw_common.py:1648-1651` 的 `_EXT_SRC_DIR`）；
  - doctor 侧的同一判据只是 **suggestion**（`mw_common.py:2044-2047`：`if report["bundle"].get("stale"): suggestions.append(...)`），不进 `issue`、不影响 `summary.healthy` 与退出码——所以只靠 doctor 的 mtime 判据永远挡不住陈旧内容。
  - `stale` → `add("bundle","machine","stale",…,"重建+全局重装 bundle…",auto=True)`（`mw.py:4339-4341`）；源不可比 → `info`（`mw.py:4336-4338`）；缺失 → `warn`（`mw.py:4332-4333`，注意 `warn` 不进 `_apply_update_env`，因为 `stale()` 只认 `status=="stale" and auto`，`mw.py:4518-4520`）。
- **A2（pi dist，mtime）**：`mw.py:4346-4360`
  - `_newest_file_mtime(packages/coding-agent/dist)` vs `_newest_file_mtime(packages/coding-agent/src)`，slack 2.0s（`mw.py:4350-4355`）；`stale` → `add("pi-dist","machine","stale",…,auto=True)`（`mw.py:4356-4358`）；缺目录 → `skip`（`mw.py:4360`）。
- 两者共同点：**都只看全局副本 / 产物目录的 mtime**，都不看 repo bundle。差异只在对象与 slack；A2 的 detail 自称"粗粒度启发式"。

### 1.2 A1b「repo bundle vs 源码」插在哪、layer 与 fix 文案

- **落点**：插在 A1 的 `else` 之后、A2 注释之前，即 **`mw.py:4344` 与 `mw.py:4346` 之间**。理由：`_format_update_env_text` 按 `layer` 变化插分隔行（`mw.py:4566-4573` 循环 + `"机器层"/"项目层"` 渲染），A1/A2 同属 `machine`，A1b 插在中间不改变分层渲染；渲染 `c['id']:<18`（`mw.py:4574`），`repo-bundle` 11 字符不溢出。
- **layer = `"machine"`**（与 A1/A2 一致；它描述的是**检出机**的 tracked 产物，不是某个项目的面）。**不要**用 `"project"`：`_apply_update_env` 不按 layer 分派，但文本会把 repo bundle 误渲染进"项目层"。
- **status**：`stale`（内容判据红）/ `ok` / `info`（源或产物缺失、非完整检出）/ `warn`（例如 bundle 存在但无法解析出任何 kind 结构——无法判定，不 block）。`stale` 必须 `auto=True`，否则 `_apply_update_env` 不会触发。
- **id = `repo-bundle`**（全局副本用 `bundle`，两者语义不同，不要复用 id：`_apply_update_env` 的 `by_id` 以 id 为键，`mw.py:4516`）。
- **detail 文案（建议）**：
  - stale：`repo bundle kind 集缺 {缺失项}；guard 标志缺 {缺失项}；模块集 {n}/{m}` （三者按实际差异拼）
  - ok：`repo bundle 与源码同步（kind {k} 项、guard 标志齐、模块 {m}/{m}）`
  - info：`repo bundle 或源码缺失，跳过内容比较`
- **fix 文案（建议）**：`"mw build（重建 repo bundle → 全局重装 → 重建 coding-agent dist），随后重启 pi 窗口"`，`auto=True`。

### 1.3 S1 的顺序修改与失败处理

现状 S1（`_apply_update_env` 全文 `mw.py:4509-4560`；本步 `mw.py:4522-4530`）

```
if stale("bundle") or stale("pi-dist"):
    rc = _deploy_bundle(no_dist=False)
```

问题（RQ-3 §3.2 已证）：`_deploy_bundle`（全文 `mw.py:3609-3632`）的 docstring 自称 "Install the **freshly built** bundle"（`mw.py:3610-3612`），但它只 `shutil.copy2(_bundle_path(), …)`（`mw.py:3614`）——**它假定调用方已重建**，而 `_apply_update_env` 从不调 `_build_bundle()`（全仓调用点只有 `mw.py:3636`（`cmd_build`）与 `mw.py:3788`（`cmd_setup --build`））。于是"陈旧 repo bundle → 拷到全局 + 刷新 mtime → 复查 healthy"= fail-open。

**建议改法**（同时闭合 A1b）：

```
needs = stale("repo-bundle") or stale("bundle") or stale("pi-dist")
if needs:
    ok, msg = _build_bundle()          # 无条件重建，恢复 _deploy_bundle 的调用契约
    if not ok:
        manual.append(f"bundle 重建失败: {msg} — 未部署（避免 fail-open）")
    else:
        rc = _deploy_bundle(no_dist=False)
        ...
```

- **build 失败 ⇒ 绝不 deploy**：这是本条的核心。否则"build 失败 + 旧 repo bundle 被 copy + mtime 刷新"正好复现要修的 fail-open。
- **为什么无条件 build 而不是"仅 A1b stale 时 build"**：`_deploy_bundle` 的另一个调用者 `cmd_build`（`mw.py:3635-3640`）总是先 build，S1 应当镜像该契约；且 A1（全局 mtime 旧）与 A2（dist 旧）单独 stale 时，repo bundle 未必是最新的（A1b 的内容判据若因 `info`/`warn` 未触发，就漏了）。代价是一次 esbuild（秒级），换掉一整类 fail-open，值得。
- **部分部署风险**：`_deploy_bundle` 先 copy 全局（`mw.py:3614-3616`）再 `_rebuild_pi_dist()`（`mw.py:3622-3631`）；dist 失败时全局已换、dist 未换 = 部分部署（RQ-3 R4）。
  - **建议**：把 `_rebuild_pi_dist()` 提到 copy 之前（`no_dist=False` 时先 rebuild，失败 `return 1`，成功再 copy + sidecar + update 命令）。效果：dist 失败时全局副本保持旧内容 → A1 复查仍 stale → 下次重试，**fail-closed**。
  - 兼容性：`test_mw_build.py:49-51`（`test_install_dist_failure_fails_the_build`）只断言 `rc==1` 与 stderr 文案，重排后仍绿；建议新增"dist 失败 ⇒ 全局副本未被写"的断言（见 Q5）。
  - 若认为重排出 scope：至少 S1 在 `rc!=0` 时打印 `manual` 说明"全局可能已换、dist 未换"，并在 UPDATE.md §5 登记该部分部署面。

---

## 2. Q2 — 内容判据怎么算（不跑构建）

前提：`_check_update_env` 的 docstring 明确 "Pure reads — no network, no side effects"（`mw.py:4317-4318`）；`doctor_report` 明确 "Local-only checks (no network), <5s"（`mw_common.py:2093-2095`）。所以 doctor/update-env 的判据必须便宜且只读；**任何写 tracked 文件的判据只能进测试/文档流程**。

### 2.1 候选 (a)：`GATE_KINDS` 字面量集合

- 源：`status-model.ts:505-512` `export const GATE_KINDS = ["stage-confirm","stage-close","stalled","budget-exhausted","goal-change","xkey-authorize"] as const;`
- repo bundle 实测：`var GATE_KINDS = [\n  "stage-confirm",\n … "xkey-authorize"\n];`（`dist/extensions/agent-team-loop.js`，esbuild 未压缩，把 `export const` 降为 `var`）
- coding-agent dist 实测：`export const GATE_KINDS = [\n    "stage-confirm", … \n];`（`dist/extensions/agent-team-loop/autopilot/status-model.js`，tsgo 保留 `export const` + 尾逗号）
- **可行性**：三处都可零构建解析。解析器要接受 `var|const|export const` 与可选尾逗号；锚定 `GATE_KINDS = [` 后只收集 `"…"` 字面量到 `]`。
- **成本**：约 20 行 Python，每处 <1ms（文件 923KB 一次读入）。
- **误报面**：低。C1 的"注释里的路径字符串"弱点在此**不适用**——注释里没有 `GATE_KINDS = [`；正则锚定赋值形式而不是裸字符串即可。
- **漏报面**：**只覆盖 kind 枚举**。新增 guard 逻辑、修 bug、改行为分支而 kind 不变时，完全看不见（Q3）。
- **结论**：**推荐**作为便宜判据的一部分（对应 AC-009(b) 前半）。

### 2.2 候选 (b)：guard 行为标志串

实测计数（`dist/extensions/agent-team-loop.js`，923479 B）：

| 串 | 出现 | 命中位置 |
|---|---|---|
| `xkey-authorize` | 1 | `GATE_KINDS` 数组元素（真实数据） |
| `xkey-gate-guard` | 3 | **1 处是路径注释** `// packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`；2 处是行为 reason `` `xkey-gate-guard: blocked …` ``（`xkey-gate-guard.ts:187`、`:229`） |
| `XKEY_GATE` | 2 | **1 处是环境变量名子串** `MW_XKEY_GATE_ROOT`；1 处是 trace 模板 `` `[XKEY_GATE] ${…} blocked tool=…` ``（`xkey-gate-guard.ts:208`） |

- **必须用带限定符的串**：`xkey-gate-guard: blocked`（含冒号空格）与 `[XKEY_GATE]`（含方括号）。裸 `xkey-gate-guard` / 裸 `XKEY_GATE` 会分别命中**路径注释**与**环境变量名**——正是 RQ-3 §4.2 C1 的弱点。
- **可行性**：两个 `in` 判断，零成本。
- **误报面**：低（guard reason 是用户可见行为串，压缩也不会删）。
- **漏报面**：①只钉住"这一特定功能"，不能证明注册链生效（字符串可能在死代码里）；②不覆盖该功能之外的漂移。
- **结论**：**推荐**作为组件（对应 AC-009(b) 后半），不可单独当锚点。

### 2.3 候选 (c)：干净树重建后 `git diff --exit-code`

- **可行性**：需要 node + npm + esbuild + tsgo（`_build_bundle` `mw.py:3516-3547`；`_rebuild_pi_dist` `mw.py:3550-3573`），**会写 tracked 文件**（repo bundle + coding-agent dist 953 文件），需要干净树，且不能是"纯读 <5s"。
- **误报面**：脏树（多会话）必然非空；工具链不确定性（见 Q6）；Linux mode 位。
- **漏报面**：对"产物是否由当前源码生成"是精确判据（无漏报）；但不覆盖孤儿产物（`npm run build` 无 clean，RQ-3 R5）。
- **结论**：**不能进 doctor/update-env**；作为 AC-009(a) 的测试/文档流程判据（Q5、Q6）。

### 2.4 额外发现（免费且更强的 dist 侧通用判据）：`sourcesContent` 比对

`packages/coding-agent/tsconfig.build.json` 继承 `tsconfig.base.json` 的 `sourceMap: true + declarationMap: true + inlineSources: true`（`tsconfig.base.json:14-17`）。因此每个 tracked `*.js.map` / `*.d.ts.map` **内嵌了对应 `.ts` 的完整源文本**，`sources` 是相对路径（与 cwd 无关）。

实测（本快照，工作树）：

- `dist/extensions/agent-team-loop/**`：`*.js.map` 41 个，`sourcesContent` 与磁盘源**逐字节相等 41/41，0 mismatch**。
- 整个 `packages/coding-agent/dist`：`*.map` 472 个，覆盖到的 `src` 目标是 **236/237**（唯一未覆盖者是 `src/utils/highlight-js-lib-index.d.ts`，纯声明、不 emit）；**0 mismatch**。
- 耗时：extension 子树 **9ms**，整个 dist **40ms**。

**它在历史漂移上是红的**（用 `git show` 读旧对象、不改文件）：

- `181a75332:packages/coding-agent/dist/extensions/agent-team-loop/autopilot/status-model.js.map` 的 `sourcesContent` != `181a75332:…/autopilot/status-model.ts`（旧 dist 内 **不含** `xkey-authorize`）；
- `181a75332:…/shared/xkey-gate-guard.js.map` **不存在**（源已新增 `xkey-gate-guard.ts`，dist 未编译）。

即这条判据**能复现本轮漂移的检出**，且比 (a) 强（逐字节内容，不只 kind）、比 (c) 便宜（40ms、只读）。建议落成 A2b（id 如 `pi-dist-content`，layer `machine`，`auto=True`），或先纳入 A1b 的 detail。

### 2.5 推荐组合

| 消费方 | 判据 | 理由 |
|---|---|---|
| doctor / update-env（便宜、只读） | (a) kind 集 + (b) guard 标志 + (c') 模块路径注释集（§3.2）+ dist `sourcesContent`（§2.4） | 全部纯读；<200ms；覆盖本轮漂移的两条（kind + 新模块） |
| 测试 / 文档流程 | (c) 干净树重建 + `git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist` | 唯一能证"产物 == 当前源码的构建"的判据 |
| 未来加固（可选） | M2 源哈希 manifest（§3.3） | 覆盖"kind 未变的非 kind 改动" |

**特别注意（问题点名）**：产物内匹配要区分"真实数据结构"与"注释里的路径字符串"。三条规则：①(a) 锚定 `GATE_KINDS = [` 赋值形式；②(b) 用带限定符的完整标志（`xkey-gate-guard: blocked` / `[XKEY_GATE]`）；③模块集判据锚定**行首** `// packages/…/*.ts` 注释（esbuild 的模块 banner），而不是任意位置子串。

---

## 3. Q3 — 漂移检测的失败面与更一般判据

### 3.1 kind 集合的失败面

**不能**发现"非 kind 的改动"。具体例子（都不改 `GATE_KINDS`）：

- 改 `isXkeyGatePath` 的路径解析/`~` 展开（`xkey-gate-guard.ts:129-142`）；
- 改 bash 写动词正则集合（`xkey-gate-guard.ts:150-165`）；
- 修 `recordXkeyGateBlockTrace` 的 best-effort 行为（`xkey-gate-guard.ts:196-213`）；
- 任何其它 41 个模块里的 bug fix。

这些场景下 A1b 报 ok，但全局/repo bundle 仍陈旧 → 同一个 fail-open 以更隐蔽的形式复发。因此 (a)+(b) 只能覆盖"本轮这一类（新增 kind + 新增模块 + 新 guard 标志）"，不是通用锚点。

### 3.2 便宜的通用化：esbuild 模块路径注释集

esbuild 非压缩输出会为每个被 bundle 的模块写一行行首注释 `// packages/<path>/<file>.ts`。实测 repo bundle：**45 条**，其中 **41 条正好等于 `packages/coding-agent/src/extensions/agent-team-loop/**` 的全部 41 个文件**（1:1），另 4 条是 `src/config.ts`、`src/utils/{child-process,paths,shell}.ts`（依赖闭包）。

- 判据：`{bundle 中 agent-team-loop/ 下的 path 注释}` == `{src 目录磁盘文件（相对路径归一化）}`。
- 成本：一次正则扫描 + 一次目录遍历（<10ms）。零构建改动。
- 覆盖：**新增/删除/改名源模块**（这正是 `181a75332` 漏掉 `xkey-gate-guard.ts` 的那半边）。不覆盖同文件内容改动。
- **推荐**纳入 A1b。

### 3.3 内容哈希 manifest（更一般的判据）与对抗面

| 方案 | 做法 | 成本 | 对抗面 |
|---|---|---|---|
| **M1 内嵌源清单** | 改 `_BUILD_NODE_SCRIPT`（`mw.py:3481-3508`）在 build 时 walk 源目录、`node:crypto` 算 sha256，经 esbuild `define`/`banner` 注入 bundle（如 `var MW_SOURCE_MANIFEST = {…}`）；doctor 重算源哈希比对 | 中（改 JS 构建脚本 + 解析注入结构） | 手工改 bundle 内容而不改源：检测不到（清单来自源）。若连清单一起手改：与直接 commit 无异，任何锚点都无解 |
| **M2 兄弟 manifest** | `_build_bundle` 额外写 `packages/multi-workers/dist/extensions/agent-team-loop.manifest.json`（每模块 sha256 + 期望产物 sha256），tracked 提交；doctor 重算源哈希比对 | 中低（新增 1 个 tracked 生成物 + 文档/提交纪律） | 同上 |
| **M3 mtime+size 清单** | 记录源文件 mtime+size | 低 | **拒绝**：`git clone`/`checkout` 会把 mtime 刷成"现在"，全新克隆必然误报；这正是 RQ-3 §3.3 已批判的 mtime 类判据 |
| **M4 模块路径注释集** | §3.2 | **极低** | 只覆盖增删模块 |

- **推荐**：短期 M4 + (a) + (b) + `sourcesContent`（覆盖 dist 侧全部内容漂移）；若要求"关掉非 kind 内容漂移"，再做 **M2**（不选 M1：把清单写进产物会让 bundle 不再是纯 esbuild 输出，自检/可复现更难读；M2 的 manifest 在 git diff 里可读，reviewer 能看到"哪个源文件动了"）。
- **必须写进设计的对抗边界**：manifest 只证"**源自 manifest 生成后未变**"，不证"**产物是源的构建**"。唯一能证后者的是 (c)（从 committed 源码重建 + `git diff`）。威胁模型是**意外漂移**（TS 改了忘重建），不是对手篡改；对篡改只能靠 (c) + 代码评审。
- **构建戳注意**：若要给 bundle 加版本戳，**只能用内容派生的哈希**（源哈希/产物哈希），**绝不能带时间戳**——否则两次构建不同，直接与 AC-009(a) 的 `git diff` 判据冲突。

---

## 4. Q4 — 脏树护栏

### 4.1 拒跑面（哪些路径）

先厘清每个命令实际编译/覆写什么：

| 命令 | 编译输入 | 覆写的 tracked 产物 |
|---|---|---|
| `mw build`（`cmd_build` `mw.py:3635-3647`，无 `--install`） | `packages/coding-agent/src/extensions/agent-team-loop/index.ts` 及其传递依赖（`_EXT_SRC_REL` `mw.py:3473-3475`；闭包含 `src/config.ts`、`src/utils/*.ts`） | `packages/multi-workers/dist/extensions/agent-team-loop.js`（1 文件） |
| `mw build --install` | 同上 **+** `packages/coding-agent/src/**`（tsgo 全量 emit，`tsconfig.build.json` `include: src/**/*.ts`） | 上一行 **+** `packages/coding-agent/dist/**`（953 tracked 文件）+ `copy-assets` 的 theme/assets/template/vendor |
| `mw setup --build`（`mw.py:3787-3792`） | 同 `mw build` | 同 `mw build`（只写 repo bundle；不再重建 dist） |
| `mw bootstrap` step 3（`mw.py:4050-4052`） | 子树全部 workspace 的 `src`（root build：tui→ai→agent→session-backends/sqlite-node→protocol→client→server→coding-agent） | **所有** `packages/*/dist` |

**推荐拒跑面**：

- `mw build` / `mw build --install` / `mw setup --build`：**输入路径 `packages/coding-agent/src`**（硬拦，这是"他人未提交 TS 被编进 tracked 产物"的唯一来源）+ **输出路径 `packages/coding-agent/dist` 与 `packages/multi-workers/dist`**（按 AC-009(d) 纳入；理由：另一会话可能已有未提交的 rebuild，本会话会覆写它）。
- `mw bootstrap` step 3：面放大到 **`packages/*/src` + `packages/*/dist` + `packages/session-backends/*/src,dist`**——因为它跑 root build，会写全部 workspace 的 dist。
- 不拦：`packages/coding-agent/examples/**`、`node_modules`、`.tmp`、`.agenticdoc`（与产物无关；`examples/extensions/with-deps` 虽在 workspaces 里但不参与 root build 链）。

### 4.2 如何判定"脏"

- **必须用 `git status --porcelain` 子集**，而不是 `git diff --quiet`：
  - `git diff --quiet -- <paths>` 只看**未暂存的 tracked 改动**，漏掉 **staged**（`M ` / `A `）与 **untracked**（`??`）；而 tsgo 的 `include: src/**/*.ts` 会编译**新增的未跟踪 `.ts`**，删除源文件留下的旧 dist 也是 untracked/孤儿问题来源。
  - 既有 `_git_dirty(repo)`（`mw.py:4249-4257`）用 `git status --porcelain` 但**没有路径过滤**，整仓调用（`mw.py:4366` 用于 framework checkout），不能复用。需新增 `_git_dirty_paths(repo, paths) -> list[str]`（约 6 行：`_git(["status","--porcelain","--untracked-files=all","--",*paths], cwd=repo)`，returncode != 0 视为"不可判定"）。
- **"不可判定"（无 git / 不是 git 仓库 / git 缺失）⇒ 跳过护栏并打印 info 行**（fail-open）。理由：没有 git 就没有"tracked 产物被误提交"的风险面；且 `test_mw_bootstrap.py` 的 fixture 仓库是 tmp 目录、**不是 git 仓**（`test_mw_bootstrap.py:52-96`），硬拦会把整套 bootstrap 测试打红。

### 4.3 多会话（共享 cwd）阈值与错误文案

多会话必然让工作树周期性变脏，护栏的价值与噪声需要权衡。**推荐阈值**：

1. **硬拦**：输入路径（`mw build` 的 `packages/coding-agent/src`；bootstrap 的 `packages/*/src`）有 tracked-modified/staged/deleted/untracked 改动。
2. **硬拦（按 AC-009(d)）**：输出路径（`packages/coding-agent/dist`、`packages/multi-workers/dist`）有改动。**但要在设计里显式记下退化选项**：若多会话下这条噪声过大（典型：另一会话刚 `/mw build` 但未 commit dist），把"仅 dist 脏、src 干净"降级为 **warn + 继续**（msg 提示"将覆写 N 个 dist 文件"），src 脏保持硬拦。
3. **绕过**：`--allow-dirty` 显式开关。src 干净时，一次 rebuild 的产物与磁盘一致，覆写 dist 无害；`--allow-dirty` 的真正语义是"我确认这些改动属于本会话 / 我愿意承担"。

**错误文案（建议，与既有 `[mw build] Error:` 风格一致，`sys.stderr`）**：

```
[mw build] Error: 工作树有未提交改动，构建会把它编进 tracked 产物（多会话共享 cwd 时多半属于别的会话）：
  M packages/coding-agent/src/extensions/agent-team-loop/index.ts
  ?? packages/coding-agent/src/extensions/agent-team-loop/new-mod.ts
  (共 N 处，上列前 5)
确认后重跑：mw build --install --allow-dirty
```

参数落点：`build_p.add_argument("--allow-dirty", dest="allow_dirty", action="store_true", …)`（`mw.py:4791-4797` 旁）；`bootstrap_p`（`mw.py:4773-4779`）同样加；`cmd_build` 里用 `getattr(args, "allow_dirty", False)` 以兼容既有 `SimpleNamespace`（`test_mw_build.py:16-17` 的 `_args` 目前没有该属性——见 Q5）。

### 4.4 `mw bootstrap` 是否要同一护栏

**要，但作用面不同**：

- bootstrap 的典型场景是"新机器 fresh clone"——此时树上必然干净，护栏不会挡正常流程；
- 但 bootstrap 是**可重跑**的（docstring `mw.py:3926-3966`），一次 `--fast` 之外的重跑在脏树上会写全部 `packages/*/dist`（污染面比 `mw build` 大得多）；
- 所以同一个 `--allow-dirty` + 更宽的路径集，复用同一个 `_git_dirty_paths` helper。
- 不新增 env 开关（`MW_BUILD_ALLOW_DIRTY` 之类）：绕过必须**显式、可见、进 shell 历史**，env 旁路不可追溯。

---

## 5. Q5 — 测试

### 5.1 `test_mw_build.py`（全 mock）能覆盖什么

现状（`test_mw_build.py`，4 用例，全 mock `_build_bundle`/`_rebuild_pi_dist`，无需 node/npm）：

- 可覆盖（新增断言，全 mock，快）：
  - **护栏拦截**：monkeypatch `_git_dirty_paths` 返回非空 → `cmd_build` rc=1、stderr 含错误文案、**`_build_bundle` 未被调用**、`_deploy_bundle` 未被调用（用记录 list 断言）。
  - **`--allow-dirty` 绕过**：返回非空时 rc=0 且 `_rebuild_pi_dist` 被调用。
  - **干净路径不拦**：`_git_dirty_paths` 返回 `[]` → 既有 4 用例保持绿；`_args` 必须补 `allow_dirty=False`（`test_mw_build.py:16-17`），否则 `args.allow_dirty` 属性访问报错——**这是新增 flag 的必改点**。
  - **`_deploy_bundle` 重排**：mock `_rebuild_pi_dist` 失败 → rc=1 且**全局副本未被写**（配合 §1.3 的 dist-before-copy 重排）。
- 不可覆盖：
  - `git status --porcelain` 的**真实解析与路径过滤**（fake repo 不是 git 仓）；
  - 任何产物内容/kind/标志断言；
  - 真实构建的确定性。

### 5.2 新增判据的可测形状

- **纯函数化**（可测、无 IO 语义）：
  - `_gate_kinds_from_source(path) -> set[str]`、`_gate_kinds_from_bundle(path) -> set[str]`（接受 `var|const|export const` + 尾逗号）；
  - `_bundle_module_paths(bundle_text) -> set[str]`（行首 `// packages/…/*.ts`）；
  - `_sourcemap_drift(dist_root, src_root) -> list[str]`（比对 `.map` 的 `sources`/`sourcesContent`）；
  - `_repo_bundle_anchor(repo_root) -> dict`（组合上述，返回 `{status, detail}`，供 `_check_update_env` 直接 `add(...)`）。
  - 测试形状：tmp 目录写 fixture 产物/源 → 断言集合差与 status。**必含反例**：文件内只有路径注释 `// packages/…/xkey-gate-guard.ts` 而无 `xkey-gate-guard: blocked` / `[XKEY_GATE]` ⇒ 必须报 stale（防 C1 回归）。
- **真实 git 的 helper 测试**（快，不是 e2e）：`test_update_env.py` 已有 tmp git fixture（`_git_init` `test_update_env.py:26-38`、`_make_framework_source` `:41-58`）；照此新建 tmp 仓，制造 modified / staged / untracked / 路径外改动，断言 `_git_dirty_paths` 只报目标路径。
- **`_check_update_env` 集成**（快，mock）：扩 `_world`（`test_update_env.py:230-256`，已 monkeypatch `mw._repo_root` 到 tmp repo-root）写入假 repo bundle + 假 `status-model.ts` → 断言 `repo-bundle` 的 `status`/`auto`；`_apply_update_env` 的 S1 顺序用 monkeypatch 记录 `["build","deploy"]`，build 失败时断言 `["build"]`（不 deploy）。
- **无构建的产物回归**（快，直接读 committed 产物）：断言 repo bundle 的 kind 集 == `status-model.ts` 源集、含 `xkey-gate-guard: blocked` 与 `[XKEY_GATE]`、模块集 == src 文件集；dist extension 子树的 `sourcesContent` 0 mismatch。这给 AC-009(b) 机器覆盖，且不需要 node。

### 5.3 必须真跑构建的断言（e2e / 慢测）

- AC-009(a)：干净树上 `python packages/multi-workers/mw.py build --install` → `git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist` 退出码 0。
- 确定性：连续两次 `_build_bundle()` 同 sha（可选：dist 侧同样对比）。
- 判据形状：新 marker（建议 `e2e_build`）写进 `packages/multi-workers/pytest.ini` 的 `markers=` 与 `addopts = -m "not e2e_real and not e2e_l2 and not e2e_build"`（现状 `pytest.ini` 只有 `e2e_real`/`e2e_l2`）。
- **skip 条件（能力型，不是平台型）**：
  - `shutil.which("node") is None or shutil.which("npm") is None` → `pytest.skip`；
  - 起始时 `git status --porcelain -- packages/coding-agent/src packages/coding-agent/dist` 非空 → `pytest.skip("dirty tree: another session is mid-edit")`（多会话正确性，而不是失败）；
  - **Windows 不需要额外 skip**：esbuild/tsgo 都原生跨平台，且主开发环境就是 Windows。唯一平台陷阱是 Linux 的 mode 位（Q6），由 `-c core.fileMode=false` 处理，不用 skip。
- 现实约束：`packages/multi-workers` 不是 npm workspace、CI 无 pytest 步骤（RQ-3 §6 已证）⇒ `e2e_build` 在 CI 也不会跑，它是**开发机证据门禁**；设计里要如实声明，不要把"CI 会挡"当护栏。

---

## 6. Q6 — AC-009(a) 的可复现流程与已知风险

### 6.1 判据与流程

```
# 前提：干净树（src 侧无未提交改动）
python -X utf8 packages/multi-workers/mw.py build --install
git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist
# 期望：退出码 0、无输出
```

含义：tracked 产物 == 从当前源码可复现的构建结果；配合全局副本 sha 相等（RQ-3 §4.2 C4）覆盖部署面。

### 6.2 已知风险（逐条实测/查证）

| # | 风险 | 实测/查证 | 影响面 | 处置 |
|---|---|---|---|---|
| A | **esbuild 非确定性** | esbuild **0.28.1 精确 pin**（root `package.json` devDependencies）；`_BUILD_NODE_SCRIPT` 未压缩、无 sourcemap（`mw.py:3481-3508`）；产物内**无绝对路径**（实测 grep 盘符路径（`\X:` 形态 / `C:/` / `\Users\`）全 0，仅 1 处是 `deny_globs:` 正则误命中）；45 条路径注释均为仓内相对路径 | 低 | 无需处置；`d52694cc4` 两次连续构建同 sha 已佐证 |
| B | **tsgo 非确定性** | `tsgo --version` = `7.0.0-dev.20260120.1`（preview）；`d52694cc4` 只验了 bundle sha，**未验 dist** | 中（未知） | 把它当**待实测项**：e2e 里连跑两次 build 比较 `git status`；若两次之间有 diff，则 AC-009(a) 只能写成"同机器同工具链下的期望"，不能当不变量 |
| C | **行尾噪声** | `.gitattributes:1-2` `* text=auto eol=lf`；实测 repo bundle `CRLF=0 / LF=23694`，`xkey-gate-guard.js` `CRLF=0` | 无 | 无需处置 |
| D | **copy-assets 的 mtime 噪声** | `npm run build` = `tsgo … && shx chmod +x … && npm run copy-assets`（`packages/coding-agent/package.json` scripts.build）；`cp` 只改内容不改 mtime 语义 | 无 | `git diff` 不看 mtime |
| E | **tsbuildinfo 噪声** | `tsconfig.build.json` 无 `incremental/composite`；实测无 `.tsbuildinfo`；`.gitignore:6` 亦忽略 | 无 | 无需处置 |
| F | **mode 位（未登记的真风险）** | `git ls-files -s` → `dist/cli.js`、`dist/rpc-entry.js` 都是 **100644**；而 build 脚本执行 `shx chmod +x dist/cli.js dist/rpc-entry.js`。本机 `git config core.filemode` = **false**（Windows 默认），所以现在 `git diff` 看不到；在 `core.fileMode=true` 的主机（Linux/macOS）上，构建后这两个文件变成 100755 → `git diff --exit-code` **非空** | 只在非 Windows 主机触发 | 判据命令统一带 `git -c core.fileMode=false`；若要彻底消除，需另立 key 处理 exec 位的提交/交叉平台语义（不在本 key） |
| G | **脏树** | 工作树受检时无 tracked 改动；多会话下不可保证 | 高（判据报告为红但其实"正确反映了脏源"） | AC-009(d) 护栏 + e2e 测试起始 skip-if-dirty |
| H | **孤儿产物** | `npm run build` 无 clean（`package.json` 只有独立 `clean`；RQ-3 R5）；被删源文件的旧 dist 仍 tracked 且内容不变 | 中 | AC-009(a) **不覆盖**；spec §1.4 已明确不做孤儿清理，设计里显式声明该判据的边界 |
| I | **bundle 非原子写** | esbuild 直接写 outfile；`shutil.copy2` 先截断再写（RQ-3 R2） | 并发读窗口 | 与本判据无关，但设计应登记（不属于本 key 范围） |

### 6.3 `d52694cc4` 的证据是否足够

- **足够的部分**：①它证明"**bundle 侧**在同一机器、同一工具链下连续两次构建 sha 相同（`1be95bba…`，923479 B）"；②它留下的 12 文件提交让本快照处于"产物 == 源码"的绿灯态（本 RQ 复验：dist extension 子树 `sourcesContent` 41/41 相等；repo bundle 模块集 41/41）。
- **不足的部分**：①**没有 dist 侧确定性证据**（tsgo preview，见风险 B）；②它是一次性对齐，不构成"未来漂移能被发现"的判据（RQ-3 §7 已定性）；③没有在非 Windows 主机上验过 mode 位（风险 F）。
- **结论**：`d52694cc4` 足以支撑"当前产物与源码同步"这一**事实**，不足以支撑 AC-009(a) 作为**可复现判据**。设计应要求：在干净树上跑一次完整流程并**记录退出码 + `git diff --stat` 为空**，同时记录工具链版本（node/esbuild/tsgo），并注明 mode 位处置；若要求更强证据，做"连续两次重建 + 两次之间 `git diff` 为空"（对 dist 侧的确定性才是真的证明）。

---

## 7. 推荐落地清单（design 定稿要点）

1. **新增锚点 A1b**（`mw.py` A1 之后、A2 之前，即 4344/4346 之间）：
   - `add("repo-bundle", "machine", status, detail, fix, auto=True)`；
   - 判据 = kind 集（§2.1）+ guard 标志 `xkey-gate-guard: blocked` / `[XKEY_GATE]`（§2.2）+ 模块路径注释集（§3.2）；`stale → auto=True`；
   - 全部为纯读、<200ms，符合 `_check_update_env` 的 docstring 契约。
2. **新增 dist 内容锚点 A2b（推荐，本 RQ 的最大增量）**：`sourcesContent` 逐字节比对（§2.4），覆盖整个 coding-agent dist 的内容级漂移，零构建、零新文件（40ms）。
3. **S1 改为先 build 再 deploy**（§1.3）：`_build_bundle()` 失败 ⇒ 不 deploy + manual note；无条件 build（镜像 `cmd_build` 契约）。
4. **`_deploy_bundle` 内部重排**（§1.3）：`no_dist=False` 时先 `_rebuild_pi_dist()`，成功后再 copy 全局；失败 ⇒ `return 1` 且全局不动（消除 R4 部分部署）。
5. **脏树护栏**（§4）：新 helper `_git_dirty_paths(repo, paths)`；`cmd_build`（含 `--allow-dirty`）、`mw setup --build`、`bootstrap` step 3 全部接入；输入路径硬拦、输出路径按 AC-009(d) 拦；非 git ⇒ 跳过。
6. **测试分层**（§5）：纯函数/mock/真 git fixture 走默认套件；真构建走新 `e2e_build` marker + 能力型 skip；新增"无构建产物回归"覆盖 AC-009(b)。
7. **文档**：`UPDATE.md` §1 增 A1b/A2b 行、§2 增 `--allow-dirty` 行、§5 登记 mode 位与孤儿产物两条边界；spec AC-009(a) 的判据命令补 `git -c core.fileMode=false`。

## 8. 未决 / 需 PM 决策

1. **AC-009(d) 的 dist 硬拦 vs warn**：多会话下"仅 dist 脏"是否降级为 warn（§4.3 退化选项 2）？本 RQ 建议先按 AC 硬拦，把它作为 observation 期若噪声过大再放宽。
2. **是否引入 M2 manifest**（§3.3）：关掉"非 kind 内容漂移"的完整方案；收益是通用性，代价是新增 tracked 生成物 + 提交纪律。若 AC 只要求覆盖本轮漂移，可只做 §2.1/§2.2/§3.2/§2.4。
3. **`_deploy_bundle` 重排是否纳入本 key**：它改的是既有行为（dist 失败时全局不再先被替换），需要确认是否有依赖"先装全局再报错"的既有流程。
4. **风险 F 的处置深度**：只在本 key 的判据命令里加 `-c core.fileMode=false`（最小），还是新立 key 处理 exec 位跨平台语义？