# RQ-N1 取证：等价实现盘点——现有仓库是否已有"执行前拦截 `git worktree remove` / junction 感知删除"的机制

- key: `mw-worktree-junction-guard` · worker: `wjg-n1-equivalent-guard` · type: research · 卡片: `tasks/T-N1-equivalent-guard.md`
- 采集时刻: **2026-10-13 (UTC+8)**；HEAD = `55be3d960`（`fix(coding-agent): rebuild the agent-team-loop dist bundle...`）
- 方法: **只读**。结构化源码通读 + `Select-String` 计数 + 于 `node --experimental-strip-types` 下**直接 import 生产源码纯函数**并喂入事故命令，取得逐条 `[VERIFY]` 判定；`dist/` 产物与全局安装 bundle 做 SHA256 比对。
- 唯一写入物 = 本文件（见 §7 只读合规声明）。

---

## 0. 结论先行（TL;DR）

**G1（执行前拦截 `git worktree remove`）不冗余。** 当前仓库**没有任何**门禁把 `git worktree remove [--force] <path>` 识别为写/删动词；对该命令的逐门判定**全部为"不命中"**，且给出三条可复算的一手证据：

1. **6 个 `tool_call` 处理器**是全仓唯一的执行前门禁接缝（`packages/coding-agent/src` 共 6 处 `pi.on("tool_call")`）；其中 3 个（protected-config / xkey / implementation-gate）是**树白名单**（只保护 `~/.pi/agent/*.json`、`.agenticdoc/_autopilot/**`、`<root>/packages/**`），另外 2 个是 worker-mode 的 read-scope（只读）与 **bash write-scope**（唯一"分类 bash 写动词"的门禁），第 6 个是 pm-state（只 write/edit）。
2. 唯一会分类 bash 写动词的 **bash write-scope guard** 的 `git` 分支只认 `checkout|apply|clean|restore` 4 个子命令（`worker/worker-mode.ts:1501-1507`），**`worktree` 不在内**；`extractBashWriteCandidates("git worktree remove --force ...")` 实测返回 `[]`（零候选 → 不阻断）。
3. 即便把 `worktree` 加进该子命令集，事故原命令 `git worktree remove --force "$env:TEMP\qg-head"` 仍会**漏过**：目标含 `$env:TEMP` 活展开 → `verbatim=false` → 命中 `allow-unknown` 的 **fail-open** 分支（`worker-mode.ts:1606-1625`，实测 `{"allowed":true,"rule":"allow-unknown"}`）。

**重叠面（3 条）**：G1 应复用（a）`protected-config.ts:247` 的 `tool_call` block 骨架与 fail-closed 语义；（b）`worker/read-scope.ts:100` `normalizeForCompare`（realpath → junction/symlink 感知）；（c）`worker-mode.ts` bash write-scope 的"目标抽取 → 判定 → trace 审计"管线（G1 的自然宿主是它的 `git` 分支）。

**空缺面（5 条）**：见 §2.3——git 子命令词表缺 `worktree`（含 `remove`/`prune`/`add`）；非 verbatim 目标 fail-open；门禁只对 `research` 角色安装（coding/repair/vision/phase-writer/fallback 等 `bash`+`write` 角色**无任何** bash 写面门禁）；implementation-gate 的 `WRITE_VERBS` 无 `git`；pi core 对命令内容零校验。

**副产品修正**：卡片称"`mw.py` 里 grep `worktree` = 0 命中"——**实测为 2 命中**（`mw.py:5335`、`mw.py:5360`，均属 `.git`/`commondir` 只读解析，与删除无关）。结论不变（无 `mw worktree` 子命令），但计数须更正。

---

## 1. 逐门穷举（`文件:行号` + 判定逻辑 + 对 `git worktree remove --force <path>` 是否命中）

命令基线（事故原文，取自 `.agenticdoc/mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md` §AC-001）：

```text
cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" 2>&1 | Out-String; "RC=$LASTEXITCODE"; git worktree list
```

### 1.1 protected-config guard（跨窗口配置）

- 注册: `packages/coding-agent/src/extensions/agent-team-loop/index.ts:42` → `registerProtectedConfigGuard(pi)`
- 实现: `shared/protected-config.ts:247` `registerProtectedConfigGuard`
- bash 判定: `:191` `checkProtectedBashCommand` — **两步 fail-closed**：先要求扫描文本含受保护路径引用（`protectedReferences`，`:139`）
  ```ts
  const refs = protectedReferences(scan, agentDir);
  ...
  if (refs.length === 0 && !(inline && bareFragment)) return { prohibited: false };
  ```
  再要求命令含写构造（`:162`，19 个词的 `WRITE_VERB_RE`）：
  ```ts
  const WRITE_VERB_RE =
    /\b(rm|rmdir|rd|del|erase|mv|move|ren|rename|cp|copy|rsync|install|dd|tee|shred|truncate|touch|chmod|chown|ln)\b/i;
  ```
- 对事故命令: **不命中（两重都不满足）**。① 目标 `$env:TEMP\qg-head` 不是受保护路径（`auth/models/settings/oauth.json` 或 agent 目录，`:43`）；② `git worktree remove` **不含任何 `WRITE_VERB_RE` 词**（`remove` 不匹配 `\brm\b`）。
- 实测（喂入完整事故命令，含 `2>&1 |`）：
  ```
  [VERIFY] protected.checkProtectedBashCommand = {"prohibited":false}
  ```
- 附加实测（即便目标是受保护目录也不命中，暴露"写动词正则"而非"语义动词"的本质）：
  ```
  [VERIFY] protected-on-home-agent-dir = {"prohibited":false}   # git worktree remove --force <home>/.pi/agent
  ```
- 计数: `WRITE_VERB_RE` 19 个 alternation；该 guard 的 `pi.on("tool_call")` = 1 处。

### 1.2 xkey gate-dir guard（`_autopilot/**`）

- 注册: `index.ts:49` → `registerXkeyGateGuard(pi)`
- 实现: `shared/xkey-gate-guard.ts:253`
- bash 判定: `:195` `checkXkeyGateBashCommand`；引用片段 `:68` `AUTOPILOT_DIR_FRAGMENT = ".agenticdoc/_autopilot"`，写动词正则 `:167`（与 1.1 同形，19 词）。
- 对事故命令: **不命中**。命令无 `_autopilot` 引用 → `refs.length === 0` 即返回 `{prohibited:false}`（`:207`）。
- 实测：`[VERIFY] xkey.checkXkeyGateBashCommand = {"prohibited":false}`

### 1.3 implementation-gate（`write/edit` + bash 代码路径；含 key-claim 门禁与 mini-spec 快速通道）

- 注册: `index.ts:59` → `registerImplementationGate(pi)`；实现 `shared/implementation-gate.ts:760`。
- bash 分支: `:612` `checkBashWriteTarget`；写动词集 **只有 5 个**（`:79`）：
  ```ts
  const WRITE_VERBS = new Set(["tee", "cp", "mv", "rm", "sed"]);
  ```
  抽取逻辑（`:630`）：
  ```ts
  if (argv.length > 0 && WRITE_VERBS.has(verb)) {
    for (const target of verbTargets(verb, argv.slice(1), dir)) {
      if (isCodePathAbs(resolveToken(dir, target), root)) hits.push(target);
    }
  }
  ```
- 判定入口 `:686` `gateDecision`：非 `write|edit|bash` → `not-gated-tool`；bash 无写目标 → `{blocked:false, basis:"no-code-path-target"}`。
- 代码路径定义 `:143-153`：`<root>/packages/` 下、扩展名 `.ts/.tsx/.js/.cjs/.mjs/.py`、排除 `node_modules/dist/.tmp` 段。
- 自述缺口（原文 `:24-27`）：`"Not a sandbox: python -c inline writes, pre-written script execution, find -delete/-exec, tar, PowerShell cmdlets, and env-var path spellings are known misses, accepted as legacy gaps."` —— `git worktree remove` 属同类 legacy miss（既非 5 个写动词，也不在 `git` 词表内）。
- **key-claim 门禁**（`:218` `hasActiveKeyClaim`）：要求 `.agenticdoc/_index.parallel` 有 `status=active` 且 `ClaimId == host:pid` 的行；**mini-spec 快速通道**（`:240` `findFreshMiniSpec`，窗口 `:72` `MINI_SPEC_FRESH_MS = 24h`）。二者都是**通过条件**，只在"已判定为 code-path 写"之后才被求值（`:712-726`）——事故命令连第 1 步都没进，这两个条件**不可达**。
- 对事故命令: **不命中**。实测：
  ```
  [VERIFY] implgate.checkBashWriteTarget = []
  [VERIFY] implgate.gateDecision = {"blocked":false,"basis":"no-code-path-target"}
  ```
- 计数: 全 src 内 `WRITE_VERBS` 出现 2 处（定义与消费各 1）。

### 1.4 worker-mode bash write-scope guard（**唯一会分类 bash 写动词的门禁**）

- 安装条件: `worker/worker-mode.ts:2203`
  ```ts
  const bashWriteScopeConfig: BashWriteScopeConfig | undefined =
    isShellRole(meta.type) && isWritelessRole(meta.type) ? {...} : undefined;
  ```
  处理器 `:2218`；实测 `roles research shell=true writeless=true coding shell=true writeless=false` → **今天只有 `research` 角色安装本 guard**（`TOOL_ALLOWLISTS`，`:74`；`research: ["read","find","grep","ls","bash"]`）。
- 目标抽取: `:1554` `extractBashWriteCandidates` → `:1501` 的 `case "git"`：
  ```ts
  case "git": {
    const sub = operandTokens[0]?.text.toLowerCase();
    if (sub !== "checkout" && sub !== "apply" && sub !== "clean" && sub !== "restore") break;
  ```
  `worktree` 不在 4 个词内 → `break` → **零候选**。
- 判定: `:1606` `checkBashWriteScopeTarget`；非 verbatim → fail-open（`:1610-1625`）：
  ```ts
  if (!verbatim) { ... return { allowed: true, rule: "allow-unknown", detail: "target-not-statically-determinable", ... }; }
  ```
  deny 列表 `:1568` `bashWriteDenyReason`（`pm-state.md` / `workers/_workers*` / `_index.parallel` / 其它 key / `packages/**` / `.git/**`）。
- 对事故命令: **不命中（且为双重不命中）**。实测（7 组，`|` 分隔 `target|pattern|verbatim`）：
  ```
  [VERIFY] E1 incident cmd            = []
  [VERIFY] E2 literal abs worktree    = []
  [VERIFY] E3 in-repo worktree remove = []
  [VERIFY] E4 git clean -fdx          = [".|git clean|verbatim=true"]
  [VERIFY] E5 git checkout packages/foo.ts = ["packages/foo.ts|git checkout|verbatim=true"]
  [VERIFY] E6 cmd rmdir junction      = []
  [VERIFY] E7 cp var target           = ["$env:TEMP/foo.txt|cp|verbatim=false"]
  [VERIFY] V packages literal = {"allowed":false,"rule":"deny","detail":"denied:packages/**"}
  [VERIFY] V C-tmp literal    = {"allowed":false,"rule":"scope","detail":"outside-allowed-surface","target":"C:/tmp/wt"}
  [VERIFY] V var non-verbatim = {"allowed":true,"rule":"allow-unknown","detail":"target-not-statically-determinable","target":"$env:TEMP/qg-head"}
  ```
  即：`git clean -fdx` / `git checkout` **被覆盖**（同族对照），而 `git worktree remove`、`cmd /c rmdir` **零覆盖**；含变量目标时连已覆盖动词也 fail-open。
- 审计: `:1695` `appendBashWriteScopeTraceLine`（`[WRITE_SCOPE] ... write-scope ...`），断言计数 `:1680`。
- 计数: `git` 子命令词表 = 4（`checkout/apply/clean/restore`）。

### 1.5 worker-mode read-scope guard（只读；提供 junction 感知路径归一化）

- 安装: `worker-mode.ts:2165`（`read/ls/find/grep`）。
- 归一化: `worker/read-scope.ts:100` `normalizeForCompare`：
  ```ts
  for (;;) {
    try { return path.join(fs.realpathSync(cur), ...tail); }
    catch { ... tail.unshift(path.basename(cur)); cur = parent; }
  }
  ```
- 对事故命令: **不命中**（read 门禁不拦截 bash 写/删）。**价值**：这是全仓唯一把 junction 折叠进比较的生产实现，G1 的路径解析应复用它（先例见本 key 的 `design-guard-path-resolution-20261013.md`）。
- 注: 2026-10-11 的先行扫描（`.agenticdoc/mw-guard-form-hardening/evidence/research/spec-path-resolution-20261011.md`）记录仓内（`.agenticdoc/packages/.mw/.agents/docs/scripts` + 3 层，除 `node_modules/.git`）**0 个 reparse point** —— 与本卡"仓库当前无活雷、但删除工具会穿透"的设定一致。

### 1.6 pm-state guard（`write/edit` 接口行）

- 注册: `pm/pm-orchestrator.ts:1632`；实现 `shared/pm-state-guard.ts:117`。
- 判定: `:118` 只处理 `toolName === "write" || "edit"`，检查 `- Phase:` / `- Claim-Id:`（`:23`）。
- 对事故命令: **不命中**（bash 不进入；注释 `:112-116` 自述 "bash-based edits (sed/echo) are not intercepted"）。

### 1.7 `worker_file` 窄写通道

- 实现: `worker/worker-file-tool.ts:87`；basename 白名单 `:42`（`progress.md|report.md|report-<slug>.md`），无路径解析。
- 安装: `worker-mode.ts:2131` `if (!hasWriteTools) registerWorkerFileTool(...)`。
- 对事故命令: **不命中/不适用** —— 它是**新增工具**，不拦截 `bash`；对 research 角色它是唯一被允许的写通道，而 bash 另由 1.4 覆盖（1.4 已证不覆盖 `git worktree`）。

### 1.8 `mw-write-surface` / `write_scope:` 任务头（dispatch card 写面）

- 生产: `pm/ui-bridge.ts:1392-1393` `WRITE_SURFACE_MARKER` / `..._END`；消费: `worker-mode.ts:337-355`（`writeSurfaceMarkerState`），`shared/task-frontmatter.ts` 解析 `write_scope:`。
- 语义: 它是**规划期声明的写面**，运行时由 1.4 的 bash write-scope guard 与 read-scope 消费；`write_scope:` 只做**收窄**、不能放宽 deny 列表（实测见本 key 的 `spec-guard-and-mw-seams-20261009.md` 及 `mwds-t03` 测试）。
- 对事故命令: **不命中** —— 声明面本身不执行判定；判定者是 1.4，而 1.4 对 `git worktree` 零覆盖。

### 1.9 mw launcher / Python 侧 pre-flight

- `packages/multi-workers/mw.py`：`worktree` **2 命中**（`mw.py:5335` `_resolve_git_dir` 注释 "linked worktree"、`mw.py:5360` `_common_git_dir` 注释 "linked worktrees"；两处均为**只读 `.git` 文件/commondir 解析**，用于 run 身份/漂移比对，不涉及删除）。`junction` 1 命中（`mw.py:4979` `_pi_link_target_ok` 的 `realpath` 注释）。**无 `mw worktree` 子命令**（`add_parser` 全表见 `mw.py:6263-6620`，无 worktree）。
- `launcher.py`：`worktree` 0 命中。pre-flight 有 3 类，但都与命令内容无关：
  - 任务位置契约 `launcher.py:484` `_validate_task_path`（只校验 `<project>/.agenticdoc/{key}/workers/<task_key>/task.md`）；
  - dispatch envelope 门禁 `launcher.py:1173` `_envelope_refusal` + 卡面分类器 `:612-700`（`write_scope` 作为卡面字段被识别，`:621`）——**看的是卡文本，不是运行时命令**；
  - config-torn / envelope-skew 拒绝（`:1615`、`:1633` 附近）。
- `mw_common.py`：`worktree` 0 命中；`junction` 1 命中（`:4025` `_tc_normalize_root` 的 `realpath` 注释）。`assert_not_protected_agent_config`（`:1333`）只保护 agent 配置。
- `autopilot/*.py`：`worktree` 0 命中；`reparse` 1 命中（`conductor.py:3387` "zero write, zero reparse" —— **语义是"不重新解析"的幂等注释，非 NTFS reparse point**，属假阳性）。
- 对事故命令: **不命中**。无删除门禁，无 `mw worktree` 命令。

### 1.10 pi core 的 tool 校验

- 执行前接缝: `core/agent-session.ts:482-499` `beforeToolCall` → `runner.emitToolCall`；阻断语义 `core/extensions/runner.ts:944-959`（任一 handler 返回 `{block:true}` 即短路返回，工具不执行）。
- bash 工具自身: `core/tools/bash.ts`（524 行）**无任何危险命令校验**；仅 `resolveTimeoutMs`（`:27`）做超时参数校验。`Select-String 'DANGEROUS|deny|forbid|blocklist|guard'` = 0 命中。
- 计数: 全 src `pi.on("tool_call")` = **6 处**（`implementation-gate.ts:761`、`pm-state-guard.ts:118`、`protected-config.ts:249`、`xkey-gate-guard.ts:255`、`worker-mode.ts:2165`、`worker-mode.ts:2218`）。**核心不提供内容级校验，全部安全语义由扩展承担**。
- 对事故命令: **不命中**（无核心层校验；6 个 handler 的判定见 1.1-1.6，全不命中）。

### 1.11 git hooks 面

- `.git/hooks/` 可执行（非 `.sample`）hook = **4 个**：`post-checkout`、`post-commit`、`post-merge`、`pre-push`，内容全部是 git-lfs 转发（例：`command -v git-lfs ...; git lfs post-commit "$@"`）。**无 `pre-commit`**（仅 `pre-commit.sample`）。
- `.husky/pre-commit` 存在，但 `core.hooksPath` **未设置**（`git config --get core.hooksPath` → 空，exit=1），且 `.husky/_` 不存在 → **husky 未接线，pre-commit 不生效**。
- git 自身**没有 worktree 钩子**：`git help hooks` 输出含 `worktree` 0 命中；`git worktree remove` 不会触发任何 hook。
- 对事故命令: **不命中**（无可用拦截点）。

### 1.12 `.mw/` pre-flight 脚本

- `.mw/` 内容: `dispatch.yml`（角色→模型）、`window-model`、`serve.meta`、`launcher-beat.<pid>`（心跳）、`mw.pid`、各类 `.log`、以及被 Python 读取的 `.mw/*.lock`。**无任何 pre-flight 校验脚本**被调用；launcher 的 pre-flight 全在 Python 进程内（见 1.9）。
- 对事故命令: **不命中**。

---

## 2. 判定：G1 与既有机制是否冗余

### 2.1 结论

**不冗余。** `git worktree remove [--force]` 在 §1 的 12 道门中命中 = **0**。既有机制覆盖的是**另外三类目标**：跨窗口配置（1.1）、autopilot 状态（1.2）、`packages/**` 代码路径（1.3），外加一个**只对 research 生效、且不认 `git worktree`** 的 bash 写面门禁（1.4）。

### 2.2 重叠面（G1 应复用，避免造第二套）

| # | 重叠项 | 位置 | 复用方式 |
|---|---|---|---|
| O-1 | `tool_call` block 骨架 + fail-closed 拒绝文案 + 注册位置 | `shared/protected-config.ts:247-274`；`index.ts:42/49/59` | G1 注册在第 4 个 guard 位（worker-mode 之前），沿用 `{block:true, reason}` 与 `recordXxxBlockTrace` 形状 |
| O-2 | junction 感知路径归一化 | `worker/read-scope.ts:100-114` `normalizeForCompare` | G1 删除前解析 worktree 路径/其内部 junction 目标时直接调用，不新增 realpath 实现（避免第三条归一化实现造成 drift；先行结论见 `design-target-axis-20261011.md`） |
| O-3 | "提取写目标 → 判定 → trace 审计"管线 | `worker/worker-mode.ts:1501-1507`（`git` 分支）、`:1554`、`:1606`、`:1695` | G1 的最小改动面是**扩展该 `git` 分支的子命令词表 + 加一条"含 junction 的树拒绝直删"判定**，审计沿用 `[WRITE_SCOPE]` 行 |

### 2.3 空缺面（既有机制的洞）

| # | 空缺 | 证据 | 对事故的影响 |
|---|---|---|---|
| G-1 | bash 写动词词表不认 `git` / `worktree` | `implementation-gate.ts:79`（5 词）；`worker-mode.ts:1503`（4 子命令） | 事故命令零命中 |
| G-2 | 含活展开（`$env:TEMP`）的目标 fail-open | `worker-mode.ts:1610-1625`；实测 `V var non-verbatim → allow-unknown` | 即便 G-1 补齐，原命令仍会漏 |
| G-3 | bash write-scope **只对 `research` 安装** | `worker-mode.ts:2203`；实测 coding `writeless=false` | coding/repair/vision/phase-writer/fallback 角色的 `git worktree remove` 无任何写面门禁 |
| G-4 | implementation-gate 只看 `<root>/packages/**` 代码路径，且 `git` 非写动词 | `implementation-gate.ts:79/143-153/630` | 仓内 worktree（如事故里的 `.tmp-t13-wt`）删除也不受 code-path 门禁 |
| G-5 | pi core 与 git hooks 均无命令内容校验/钩子 | `core/tools/bash.ts`（0 命中）；`git help hooks`（worktree 0 命中） | 无兜底 |

> G-2 的含义很重要：**G1 不能只做"文本抽取 + 目标白名单"**，否则与 1.4 同病（变量路径 fail-open）。G1 的可靠形态必须是"对 `git worktree remove` 这类**穿透语义命令**做结构判定 + 执行前探针/拒绝"，而不是仅解析路径字面量。建议在 design 阶段作为 G1 的硬约束写入。

### 2.4 可复算证明（G1 不冗余的最小证明）

```text
# 1) 唯一分类 bash 写动词的生产函数，对事故命令返回空
[VERIFY] E1 incident cmd = []                       # extractBashWriteCandidates
# 2) 唯一可能抓到它的门禁判定为放行
[VERIFY] implgate.gateDecision = {"blocked":false,"basis":"no-code-path-target"}
[VERIFY] protected.checkProtectedBashCommand = {"prohibited":false}
[VERIFY] xkey.checkXkeyGateBashCommand = {"prohibited":false}
# 3) 对照组：同族的另一条 git 写命令是被覆盖的 -> 证明"抽取器本身工作，只是不认 worktree"
[VERIFY] E4 git clean -fdx = [".|git clean|verbatim=true"]
[VERIFY] E5 git checkout packages/foo.ts = ["packages/foo.ts|git checkout|verbatim=true"]
```

---

## 3. 双加载 / 产物漂移检查

- **bundle 来源唯一**：`packages/multi-workers/build-extension.sh` 用 esbuild 把 `packages/coding-agent/src/extensions/agent-team-loop/index.ts` 打成 `packages/multi-workers/dist/extensions/agent-team-loop.js`（`mw.py:4423` `_BUNDLE_REL` 指向同一路径）——**产物无独立逻辑**。
- **全局安装 = 本地产物，逐字节相同**：
  ```
  [VERIFY] dist bundle sha   = 3EB5B81EA0FB2461C1060C8848829DCCC0A7E07759A9359F84D2FABA9BE9E33E
  [VERIFY] global bundle sha = 3EB5B81EA0FB2461C1060C8848829DCCC0A7E07759A9359F84D2FABA9BE9E33E
  [VERIFY] same = True   (both 1,115,336 bytes, mtime 2026-10-13 22:17:57)
  ```
- **无未合并进 src 的等价实现 / 更早的 junction/删除保护**：
  ```
  [VERIFY] dist bundle: worktree=0  reparse=0  RemoveDirectory=0  IO_REPARSE=0
  [VERIFY] dist bundle git 分支仍为 4 子命令: line 18725  if (sub !== "checkout" && sub !== "apply" && sub !== "clean" && sub !== "restore") break;
  ```
  唯一与删除相关的正则在 bundle 中出现 4 处：`worker-mode` 的 inline 写模式（`:18323/:18327`，`os.remove|unlink|rmdir`、`fs.rmSync|rmdir` 等）与两份 `WRITE_VERB_RE`（`:28318` protected-config、`:28455` xkey）——**均与 src 一一对应**，非隐藏实现。
- **全局扩展目录仅一份 agent-team-loop**：`~/.pi/agent/extensions/` 下 5 个文件（`agent-team-loop.js`、`agentic-status.ts`、`agentictask-update.ts`、`goal.ts`、`.mw-py-path`），对 `worktree|reparse` **全部 0 命中**。
- **无双加载**：项目本地 `.pi/extensions/` 只有 `import-repro.ts / prompt-url-widget.ts / redraws.ts / tps.ts`，**无 `agent-team-loop.js`**（`mw.py:4806-4814` 的 "GLOBAL WINS" 逻辑会删除冗余本地副本）；`index.ts:28-35` 另有 `__agentTeamLoopActivated` 进程级双加载护栏。

**结论：不存在"dist 里有、src 里没有"的 junction/删除保护实现。**（`dist/**` 里的 `junction`/`worktree` 命中全部是文档注释：`target-config.js:78/80`、`read-scope.js:12/42`、`footer-data-provider.d.ts:8`。）

---

## 4. 残留与未验证

1. **未做端到端运行验证**：本条只对纯函数（`extractBashWriteCandidates` / `checkBashWriteScopeTarget` / `checkBashWriteTarget` / `gateDecision` / `checkProtectedBashCommand` / `checkXkeyGateBashCommand`）做了 `[VERIFY]` 实测；**未**在真实 pi 会话里跑过 research worker 的 `tool_call` 端到端（避免写入工作树）。判定是按 `worker-mode.ts:2218-2260` 的消费顺序从纯函数结果推出的，路径上无分支依赖未验证状态。
2. **未验证 `.agenticdoc/_index.parallel` 当前内容**是否会让 implementation-gate 在 `MW_IMPL_GATE_ROOT` 下走到 claim/mini 分支——与本 RQ 无关（事故命令连 bash 目标抽取都不产生）。
3. **`mw.py` 计数更正**：卡片"`mw.py` grep `worktree` = 0 命中"与实测 2 命中不符；两处均为只读解析，不改变"无 `mw worktree` 子命令"的结论。**建议 PM 以本文件为准更新卡片事实。**
4. **`conductor.py:3387` 的 `reparse`** 是"re-parse（重新解析）"的假阳性，**不是** NTFS reparse point；已排除。
5. **未覆盖其他工作树形态**：本 RQ 只判定"仓库当前源码/产物/hooks 是否存在等价机制"，**不**判定"G1 应拦截哪些 `git worktree` 子命令边界"（`add`/`prune`/`remove` 全量语义属 design 阶段）；`design-registry-and-worktree-cli-20261013.md`（T-D2）已给出 `mw worktree rm|add` 的注册位置与 reparse 实测，可直接对接。

---

## 5. 附带观察（不作为结论，供 PM 参考）

- 采集中我以 research worker 身份运行的一次 `node` 自测命令被 **bash write-scope guard 真实阻断**（`write-scope: blocked bash write to ... [rule=scope]; allowed: ...`），说明该 guard 在 research 角色下**确实生效**——进一步坐实"机制在，但不认 `git worktree`"。
- 另一次引用 `~/.pi/agent` 路径 + 写动词文本的 `Select-String` 命令被 **protected-config guard 真实阻断**，坐实 1.1 的 fail-closed（引用 + 写构造即拒，即使引用只是 read side）。

---

## 6. 未覆盖面声明

本条**未**评估：
- `git worktree remove` 之外的其他 junction 穿透删除路径（如第三方工具、`robocopy /MIR`、PowerShell 外部脚本）——属 T-N2/N3 或 design；
- G1 的最终形态（工具层 guard vs `mw worktree` CLI vs doctor 检查）与性能/兼容成本——属 design（T-D1/D2/D3）；
- 非 Windows 平台语义（junction 仅 NTFS；本卡全部判定在 Windows 宿主上取得）。

---

## 7. 只读合规声明

- 未修改 `packages/**`、`.git/**`、`.mw/**`、`pm-state.md`、`_workers.parallel`、`_index.parallel` 或任何其他 key 的文件；未执行任何 git 写操作（`worktree remove`/`prune`/`add`/`checkout`/`reset`/`clean` 均未运行）。
- 取证脚本通过 `node -e` 的 base64 payload 内联执行（`eval(Buffer.from(process.argv[1],'base64').toString())`），**未落盘任何脚本文件**；`node --experimental-strip-types` 直接 `import()` 生产 `.ts` 源码，模块顶层无副作用（纯函数导出）。
- 唯一写入物 = 本文件 `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq1-equivalent-guard-20261013.md`。
- 对 `.pi/agent/extensions`、`.agenticdoc/**` 仅 `Get-ChildItem` / `Select-String` 读取。

## 上下文来源

（PM 补录：worker 交付内容完整；本节按证据语料规范补齐来源清单。清单取自本文件各节实际引用，不改动任何上文原文。）

| 文件 | 行 | 用途 |
|---|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts` | `:100-200`、`:244`、`:249` | 判定入口与 bash 文本扫描；`WRITE_VERB_RE`/`POWERSHELL_WRITE_RE`/`SED_IN_PLACE_RE`/`FIND_WRITE_RE`/`REDIRECT_RE`/`INLINE_*` 六类写构造 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts` | `:248`、`:253`、`:255` | 判定入口与注册（`_autopilot/**` 引用才拦） |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts` | `:79`、`:218`、`:240`、`:612`、`:686`、`:756`、`:761` | `WRITE_VERBS` 词表、key-claim/mini-spec 通过条件、`checkBashWriteTarget`、`gateDecision`、注册点 |
| `packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-guard.ts` | `:118` | 只拦 `write/edit` 改 `pm-state.md` |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` | `:1044`、`:1501-1507`、`:1602`、`:1616`、`:2196-2210`、`:2165`、`:2218` | `case "git"` 子命令词表、`allow-unknown` fail-open、write-scope 仅对 shell+writeless 角色安装、两个 `tool_call` 注册点 |
| `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts` | `:100` | `normalizeForCompare` 的 junction 归一化（重叠面 #2） |
| `packages/coding-agent/src/core/tools/bash.ts` | 全文 | pi core 对 bash 命令**零校验**（1.10 结论的依据） |
| `packages/multi-workers/launcher.py` | envelope / `write_scope` 校验段 | dispatch 期卡片校验，非运行期门 |
| `packages/multi-workers/mw.py` | `:5335`、`:5360` | **2 处 `worktree` 命中**（只读 `.git`/`commondir` 解析的 docstring）——修正卡片种子里"0 命中"的说法；"无 `mw worktree` 子命令"的结论不变 |
| `packages/multi-workers/dist/extensions/agent-team-loop.js` + 全局 `~/.pi/agent/extensions/agent-team-loop.js` | SHA256 对比 | 双加载/漂移检查：两者全等（`3EB5B81E…E33E`），无未合并进 src 的实现 |
| `.git/hooks/` | 4 个可执行 hook | 全部为 git-lfs（`post-checkout`/`post-commit`/`post-merge`/`pre-push`），无 worktree 相关拦截 |
| `.mw/` | 目录清单 | 无 pre-flight 脚本 |
| 全 src | `pi.on("tool_call")` 计数 | 恰好 **6** 处（本文件 §1 的门禁全集） |

PM 复核（2026-10-13，一手复看）：全 src 的 `pi.on("tool_call")` 确为 **6** 处 —— `implementation-gate.ts:761`、`pm-state-guard.ts:118`、`protected-config.ts:249`、`xkey-gate-guard.ts:255`、`worker-mode.ts:2165`（read-scope）、`worker-mode.ts:2218`（bash write-scope）；`mw.py` 的 `worktree` 命中确为 2 处（`:5335`、`:5360`，均为 docstring，**接受本文件的修正**）；`.git/hooks` 确为 4 个 git-lfs hook；证据文件 25,070 B / 290 行、sha256 = `6B8FB515809BEEDE820EDA4528F1D1275B6BB437D7B91D6C31AA86A3C70629C0`。以下为 worker 实测、PM 未复算：12 道门的逐门 verdict 矩阵、`extractBashWriteCandidates` 返回 `[]` 的实测、`allow-unknown` 的 fail-open 轨迹、dist 与全局 bundle 的 sha 对比。

> PM 附注（与本文件的误拦讨论相关）：PM 自己的一条**只读**扫描命令被 `protected-config` 拦下，reason = 引用 cross-window config + "write verb"。定因后 trigger 是命令行里的日期格式字面量 `'yyyy-MM-dd HH:mm'` —— `WRITE_VERB_RE`（`protected-config.ts:162`）含 `dd`，`\bdd\b` 在 `yyyy-MM-dd` 里成词命中。这说明"词界 + 动词表"的文本判定在格式化字符串上仍会误拦（与 G1 的 AC-003 误拦面同类），可作为 G1 设计时"按命令结构判定、不按词表宽匹配"的反面例。
