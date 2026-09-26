# Design RQ-D3：边界强制与应用路径 + 验证执行路径的设计面

- Key: xkey-repair-mechanism / Phase: DESIGN（research RQ-D3，服务 D-005 / D-006 / D-007）
- 日期: 2026-09-26
- 产出: 本文件为唯一写入；未改 FM 树、未改本仓任何其它文件、未 commit、未跑写状态命令
- 行号口径: 当前 HEAD（dirty 树）实测 1-based 行号。**注意** Q3/Q4 的 FM 语料文件是**混合换行**（见 §4.2），同一内容在不同工具下报出的行号不同（实测 Python 行号 :220 vs PowerShell `Get-Content` :209）——这正是 Q4 的结论之一
- 实验脚本: 只写到系统 temp（`%TEMP%\q3_ast_probe.py` / `q3_failmodes.py` / `q3_regex_probe.py` / `q4_eol_probe.py` / `q4_crlf_runs.py`），运行后删除；FM 全程只读
- 检索工具: `Select-String`（PowerShell）+ `Get-Content` 编号 + `python -X utf8`（字节级行/换行校验）；已知 PowerShell 管道损坏 UTF-8 显示（P-001），故关键字节判断一律走 Python

## 决策问题

服务三个设计决策（design.md 将记录为 D-005/D-006/D-007）：

- **D-005 修复应用路径**：**(a) worker 直接写 + 写后校验 + 快照回滚** vs **(b) worker 只产提案，conductor 前置校验后应用（零残留）**
- **D-006 冻结块定位**：启发式（fail_line → 同文件冻结常量块）vs 显式冻结面声明 vs 混合
- **D-007 验证执行路径**：谁跑定向复跑与全量对照（框架现无套件执行能力，RQ-1 Q4 已证实）

必须回答 Q1–Q5（应用路径 (a) 可行性 / 应用路径 (b) 所需原语 / 冻结块定位静态实验 / 行集合 diff 计算口径 / 验证执行路径两选型）。

## 调研方法与出处

- **只读检索**：全包扫 `packages/multi-workers/**/*.py` 与 `packages/coding-agent/src/extensions/agent-team-loop/**/*.ts`；FM 语料读 `E:\CLI_workspace\FeatureMigrator\.agenticdoc\**`（只读）。
- **Q1 逐字引用**：`worker-mode.ts`、`implementation-gate.ts`、`protected-config.ts`、`dispatch.py`、`mw_common.py`（第 1 节逐个给 file:line）。
- **Q3 静态实验**：读 FM 语料 + 全文读 `tests/test_hitl_channel.py`（827 行）；用 `ast` 模块做「失败行 → (file, test_id) → 测试函数 → 模块级常量 → 常量定义行范围」的机械化推演；另用 10 个人造变体枚举失败模式。
- **关键否证检索（均实测）**：
  - `rollback|revert|restore|snapshot` in `packages/multi-workers/*.py,autopilot/*.py` → 唯一生产侧命中是 `mw.py:2794-2805`（v1→v2 迁移的 **pre-write `.bak` 备份**），**无回滚执行路径**（见 §1.7）
  - `difflib|unified_diff|SequenceMatcher` 全仓 `.py`（排除 node_modules/.tmp/dist）→ **仅 1 处测试显示用** `test/test_target_baseline.py:218`，**无生产侧 diff/行集合比较器**（见 §4.3）
  - `old_sha|new_sha|old_bytes|edit_spec|patch_spec|line_range|start_line|end_line` 全仓 `.py/.ts` → **0 个「行级编辑规格」先例**（命中均为 `[START]/[END]` 心跳行与 `ROTATE_THRESHOLD_BYTES`，见 §2.3/§4.3）
  - `subprocess.(run|Popen)` in `autopilot/*.py` → 仅 `advance.py:92,181` 与 `conductor.py:1705`（三处都是**固定框架脚本**调用，无通用命令执行器，见 §5.2）

## 发现

### Q1 应用路径 (a) 的可行性：worker 侧对 `write/edit/bash` **零路径强制**

#### 1.1 worker-mode 的 `tool_call` 拦截只覆盖 read 系（逐字）

文件 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`，拦截器 **:758-768**：

```
758: 	if (readScopeConfig) {
759: 		const projectRoot = process.cwd(); // launcher spawns workers with cwd = project root (D-106 base)
760: 		pi.on("tool_call", (event) => {
761: 			if (
762: 				event.toolName !== "read" &&
763: 				event.toolName !== "ls" &&
764: 				event.toolName !== "find" &&
765: 				event.toolName !== "grep"
766: 			) {
767: 				return undefined;
768: 			}
```

（任务书引的 `:763-772` 即本段的 tool-name 判定行；精确区间为 **:760-768**，整个处理器 :758-787 只做 read scope + `deny_globs`。）

- `worker-mode.ts` 全文只有一处 `tool_call`（:763）；`:825-840` 的 `tool_execution_start/end` 只写 trace 行（`appendTrace`，:838），不拦截。
- `WRITE_TOOLS`（:181）只是收敛检查点的信号统计（`computeRisk` :202-206），不是写面守卫。
- 结论：worker 的写工具面 = 该 type 的 allowlist（`TOOL_ALLOWLISTS.coding/phase-writer/repair` 均含 `write/edit/bash`，:53/:62/:65），**没有任何按路径的写拦截**。

#### 1.2 implementation-gate 对 `PI_WORKER_TASK` 是无条件预授权（逐字）

文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts`：

```
714: 	const workerTask = env[ENV_WORKER_TASK];
715: 	if (typeof workerTask === "string" && workerTask !== "") {
716: 		return { blocked: false, basis: "worker-env", target: targets[0] };
717: 	}
```

（任务书引的 `:752-760` 实为 `:714-717` 的 pass 分支；`:758-772` 是注册器 `registerImplementationGate`。）

注册器 **:758-772** 确实拦 `write/edit/bash`：

```
759: 	pi.on("tool_call", (event) => {
760: 		if (event.toolName !== "write" && event.toolName !== "edit" && event.toolName !== "bash") {
761: 			return undefined;
762: 		}
763: 		const decision = gateDecision(event.toolName, event.input, process.env);
```

但 `gateDecision` 的 pass 语义（模块头 :42-52）第一条就是 `PI_WORKER_TASK` 存在即放行——**不带任何路径条件**。即派发 worker（含受限修复 worker）**天然通过**这道门。

#### 1.3 implementation-gate 的代码路径集合只认 `<root>/packages/`，FM 上根本不触发

`:145-152` 的 `isCodePathAbs` 只匹配 `<root>/packages/` 下（`:74` `PACKAGES_DIR = "packages"`、`:75` 扩展名白名单），`:140` 的 `codePathRel` 前缀硬编码 `/packages/`：

```
140: 	const prefix = `${toForwardSlashes(fold(path.normalize(root)))}/${PACKAGES_DIR}/`;
141: 	if (!target.startsWith(prefix)) return undefined;
```

- `<root>` = `MW_IMPL_GATE_ROOT` 或 `process.cwd()`（:120-133）。修复 worker 在 FM 项目内运行 ⇒ root = FM 根。
- **实测**：`Test-Path 'E:\CLI_workspace\FeatureMigrator\packages'` → `False`（FM 无 `packages/` 树）。
- 目标文件 `tests/test_hitl_channel.py` 也不在 `packages/` 下 ⇒ `isCodePath` 恒假 ⇒ `gateDecision` 在 :707 返回 `{blocked:false, basis:"not-a-code-path"}`。
- 结论：**即便去掉 `PI_WORKER_TASK` 预授权，FM 的 `tests/**` 也不在 gate 的代码路径集合里**——(a) 路径上连"代码文件闸门"都不存在，更无行级边界。

#### 1.4 唯一按路径的写拦截 = `protected-config.ts`，且只保护 pi 配置集合

`shared/protected-config.ts:247-267`（`registerProtectedConfigGuard`）拦 `write/edit` 的**路径相等**判定（`:252` → `isProtectedConfigPath` `:111-116`，集合 = `auth.json/models.json/settings.json/oauth.json`，`:43`），bash 侧是 `checkProtectedBashCommand:191` 的「受保护路径引用 + 写构造」fail-closed 扫描。它是**常量路径集合**，不是行集合，也不覆盖项目源文件。与 RQ-3 结论一致（`protected-config.ts` 需改造）。

#### 1.5 Python 侧同名守卫也只保护 agent 配置

`packages/multi-workers/mw_common.py:1184` `assert_not_protected_agent_config`（:1161 `is_protected_agent_config`）——同样是 pi 配置集合，且注释写明"for any future framework write path"。无通用写面守卫。

#### 1.6 派发通道没有 write_scope 参数

`packages/multi-workers/autopilot/dispatch.py:399-412` 的 `dispatch(...)` 签名只有 `read_scope` / `deny_globs`（**读面**），无 `write_scope`；`_CODING_TOOLS`（:51）含 `write/edit/bash`，`repair`/`phase-writer` 都直接用全套（:79/:91）。conductor 的修复派发 `conductor.py:1645-1660` 也只传 prompt + `read_scope`。

#### 1.7 「快照 → 校验 → 回滚」先例：**只有"快照 + 校验"，没有"回滚"**

| 先例 | 形状 | 是前置还是事后 | 有无回滚 |
|---|---|---|---|
| `autopilot/closure.py:159` `overwrite_authorized(marker, current_bytes, failure_lines)` | 三条件：marker 存在 ∧ `sha256(current_bytes)` 等于 marker 里记的 sha ∧ 记录的失败行含 `achieved.md`（逐字，`closure.py:159-194`） | **前置授权**（批准"覆盖"这个动作） | 无（拒绝即不写） |
| `closure.py:105/123/151` | marker 读写删；`:129` "hash is computed over the exact current `achieved.md` bytes"；`:146-148` tmp + `os.replace` 原子写 | 前置快照（内容寻址），**EOL 敏感**（raw bytes，不做 `\r\n` 归一） | 无 |
| FM `repair_r1_frozen_recheck.py`（`.agenticdoc/cli-run-state-and-events/evidence/runs/`） | 12 条冻结件 sha256 逐条比对 + 22 契约文件聚合 sha + `git status --porcelain` 改动集 ∩ 冻结集 == 空（输出 `repair-r1-frozen-recheck-20260925.txt` §1/§3/SUMMARY） | **事后校验** | **无回滚**（坏就报 `problems` 退出 1，文件保持被改状态） |
| `mw.py:2794-2805` v1→v2 迁移 | 迁移前把原文件复制成 `target.yml.bak`（`:2799`，且 `:2797-2803` 备份本身也走 tmp+`os.replace`） | **前置备份** | 无自动恢复（`.bak` 只留档，需人工/脚本） |
| `test_autopilot_closure.py:65` `_snapshot(dir)` | 测试内 `{name: read_bytes()}` 前后比较，断言"无残留" | 测试断言 | 无（测试专用 helper，非生产件） |

**判定**：仓内**不存在**「快照 → 越界检测 → 自动回滚」的生产先例。走 (a) 必须**新建三个原语**：运行前字节快照、事后行集合 diff、越界 `os.replace` 回滚。

#### 1.8 (a) 的零残留可行性判定

- **可做到，但成本与新风险都落在"回滚"上**：(a) 的写面在 worker 进程内是**不可枚举的**——bash 工具可 `python -c "open(...).write(...)"`、可 `>` 重定向、可写任意路径；implementation-gate 的 bash 兜底只认 `tee/cp/mv/rm/sed` 的 file operand 与重定向 target（模块头 :24-26 明确列出"known misses：python -c inline writes / pre-written script execution / find -delete/-exec / tar / PowerShell cmdlets"），且在 FM 上整个 gate 不触发（§1.3）。
- 因此 (a) 的快照面必须是**「声明边界文件集 + 更宽的受保护集（整个 key 写面/契约面）」**，而不是"所有可能被写路径"。快照代价 = 受保护集字节量（FM 契约面 22 文件 + 冻结件 12 条，量可控；但"全仓"不可控）。
- **结论**：(a) 只有配上「运行前快照 + 事后 `git status`/行集合 diff + 越界回滚」才满足 AC-005，且回滚是**事后补救**——越界窗口内文件已被污染（其它并行 key 可能读到中间态）。**推荐 (b)（见结论映射 D-005）**。

### Q2 应用路径 (b) 的可行性：conductor 侧「校验后应用」需要什么原语

#### 2.1 原子写原语：**现成、多处、形状一致**（tmp + `os.replace`）

| 位置 | 函数 | 形状 |
|---|---|---|
| `autopilot/closure.py:123-148` | `write_bad_draft_marker` | 固定名 tmp → `os.replace`；UTF-8 + `newline="\n"` |
| `autopilot/gates.py:198-203` | `_write_atomic` | `<path>.tmp` → `replace`；显式 LF |
| `autopilot/conductor.py:1359-1395` | `_persist_l3_provenance` | append-only + 去重（`task_key`）+ tmp + `os.replace`；损坏 sidecar 不覆盖 |
| `mw.py:2378-2388` | `_atomic_write_yml` | `name.tmp<pid>` → `os.replace`；**endings 原样写**（no translation） |
| `autopilot/config.py:114-125` | `save_config` | 校验后原子写 config.json（tmp + `replace`，显式 LF） |
| `autopilot/timeline.py:349` | 轮转 `os.replace` | 10MB 阈值轮转 |
| `autopilot/dispatch.py:557` | task.md 全量预计算后 tmp+replace | 序列化错误不落半文件 |

**直接复用**，无需新建。

#### 2.2 锁原语：**现成**

- `mw_common.py:1480` `acquire_lock` / `:1495` `release_lock`（`O_CREAT|O_EXCL` 自旋，spec GC/§2.4 已点名）
- `conductor.py:92` `lock_file(project_root, name)` / `:97` `acquire_conductor_lock`
- 用法先例：`conductor.py:1695-1699`（pm-state 写锁）、`_persist_l3_provenance` 的调用方在锁内。
- 判定：**直接复用**；但注意"同一工单推进只在 conductor 单点"（Q9）——worker 不持锁写状态。

#### 2.3 「精确行级替换」原语：**不存在通用件，只有 YAML 块级编辑器**

全仓最接近"按位置替换文本"的是 `mw.py` 的 target.yml 块编辑器，全部**以 `key:` 头部定位、按行拼接**，没有 `(file, start_line, end_line, new_bytes)` 形式的通用原语：

| 函数 | file:line | 能做什么 / 不能做什么 |
|---|---|---|
| `_replace_top_level_block` | `mw.py:2054-2076` | 替换顶层 `key:` 块（头部行到下一顶层键/EOF），其余字节不动；**必须给块名，不能给行号** |
| `_find_block_header` | `mw.py:2407-2414` | 找 `^key\s*:` 头部行索引 |
| `_block_end` | `mw.py:2416-2434` | 由头部推块尾（缩进/空行规则） |
| `_block_layout_ok` | `mw.py:2436-2440` | 布局可行性（flow-style 拒绝） |
| `_edit_block_scalar` | `mw.py:2443-2473` | 2 空格缩进标量行级替换/删除/插入（**列固定**） |
| `_edit_block_roots` | `mw.py:2475-2525` | 整个 `roots:` 小节重写 |
| `_apply_mode_block` | `mw.py:2527-2567` | 上述组合；已存在的块内逐行编辑，其余**逐字节保留** |
| `_read_yml_exact` | `mw.py:2340-2346` | 关 newline translation 读取（`:2342-2344` 注释明确"必须让真实 endings 存活"） |
| `_dominant_ending` / `_line_ending` | `mw.py:2395-2405` | 主导换行探测 / 单行 ending |
| `_dominant/line ending` 的镜像测试用法 | `test_mw_partition.py:94-109` `_block_region` 用 `splitlines(keepends=True)` | 保字节的区域比较范式 |

**判定**：(b) 的"应用"步骤需**新建**一个行级替换器，但它是 ~20 行的机械件，且可直接借用 `_replace_top_level_block` 的"按行 splice + 其余字节不动"范式；锁与原子写全部现成。

#### 2.4 交付物形状：unified diff vs JSON edit spec

**关键约束来自 Q1 的事实**：机械校验必须能独立于产生者重算，且必须**抗 EOL 翻转**（P-010）。

| 形状 | 机械校验 | 机械应用 | 仓内先例 | 风险 |
|---|---|---|---|---|
| **unified diff** | 需实现 hunk 解析 + context 匹配（`difflib` 只在前向方向，无法校验"这确实是唯一改动"） | 需实现 apply；context 行不匹配即失败（EOL/行尾空格敏感） | **无**（唯一 `difflib.unified_diff` 是 `test/test_target_baseline.py:218` 的显示用） | P-010：diff 工具会因 CRLF/LF 认为整文件差异；context 漂移不可控；**无法直接给出"改动行集合"** |
| **JSON edit spec（推荐）** | 可机械重算三重校验：① `file` 存在；② `line_range` 处 `sha256(旧块字节)` == spec 记录值；③ 新块 = spec 的 `new_text`。全都由 conductor 独立计算，不信任 worker 的任何断言 | 直接 splice（按 `keepends` 行数组切 `[start-1:end]`，插入 `new_lines`），其余字节不动，tmp + `os.replace` | **无专门先例**，但 `_replace_top_level_block`（`mw.py:2054`）与 `closure.py:159` 三条件授权是同一族范式 | spec 里的行号必须配字节 sha 才稳（见 Q4） |

**推荐 spec 形状**（冻结块整块替换，不改断言主体）：

```json
{
  "file": "tests/test_hitl_channel.py",
  "frozen_symbol": "TOP_LEVEL_GROUPS",
  "line_range": [243, 244],
  "old_block_sha256": "<sha256 of the two lines, bytes verbatim incl. endings>",
  "new_block_text": "TOP_LEVEL_GROUPS = (\"agent\", ... , \"runs\", \"validate\")\n",
  "reason": "…",
  "assertion_relaxed": false
}
```

判定依据：spec §2.3「边界机械强制」+ AC-005「改动行集合 ⊆ 声明集」要求**可独立重算的旧块指纹**；unified diff 给不出这个（它给的是文本差异，不是可校验的定位锚）。**结论：JSON edit spec（block-replace spec）**。

#### 2.5 (b) 的整体可行性

`conductor` 有：原子写（2.1）、锁（2.2）、gate 协议（`gates.py:198/243`、`conductor.py:274`）、闭合事务范式（`conductor.py:1715`）、三条件授权范式（`closure.py:159`）。缺的只有**行级替换器**与**证据包组装器**（后者是 RQ-D2 的范围）。⇒ (b) **可行且改动面小**，且"零残留"由**构造**保证（worker 无写权 ⇒ 无残留）。

### Q3 冻结块定位的可行性（静态实验）

#### 3.0 样本与行号核对

- 失败行样本：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\cli-run-state-and-events\evidence\runs\repair-r1-out-20260925-r3.txt`
  - Python（`\n` 或 universal split）**行 220**：
    `[VERIFY] REPAIR-R1-F1: cross_key_test=tests/test_hitl_channel.py::test_top_level_command_groups_unchanged rc=1 cli_groups=13 frozen_groups=12 owner=cli-hitl-channel handoff=registered not_fixed_by_this_key=True`
  - 同内容 PowerShell `Get-Content` 报 **行 209**（文件总行：Python 224 / PS 213）。该文件为混合换行（118 CRLF + 106 LF-only），见 §4.2。
  - 同一失败行在 r1/r2 版本分别位于 `repair-r1-out-20260925.txt:209`、`...-r2.txt:239`（`Select-String` 口径）⇒ **证据修订一次行号就漂一次**，工单不能锚行号。
- 目标冻结块：`E:\CLI_workspace\FeatureMigrator\tests\test_hitl_channel.py`（39476 B，**纯 LF**，827 行）
  - `:243-244` `TOP_LEVEL_GROUPS`（12 组，实测逐字 `("agent", "analyze", "branch", "config", "gate", "gui", "init",\n                    "install-hooks", "mcp", "mr", "project", "runs", "validate")` ——是的，当前树已含 `"runs"`，即 13 组，与 RQ-2 Q6「红已被人手修复」一致）
  - `:261-271` 测试函数 `test_top_level_command_groups_unchanged`；`:268` `assert tuple(groups) == TOP_LEVEL_GROUPS, f"top-level groups changed: {groups}"`
  - 全文 `TOP_LEVEL_GROUPS` 只出现 2 次（定义 + 该断言）；FM `tests/*.py` 中该名字唯一（`Select-String` 实测），无同名多处

#### 3.1 AST 机械推演（实跑，脚本在 temp，已删）

规则链：失败行正则取 `(file, test_id)` → AST 找同名 `FunctionDef` → 收集函数体内 `Load` 的模块级名字 → 解析 `Assign` 的 `(lineno, end_lineno)`。实跑输出：

```
regex file/test: tests/test_hitl_channel.py | test_top_level_command_groups_unchanged
fn found: True range: (261, 271)
module constants: ['ANSWER_OK_KEYS', 'INPUT_SITE_RE', 'POLICY_LOGGER', 'REPO_ROOT', 'TOP_LEVEL_GROUPS']
module-level names referenced in test fn: ['TOP_LEVEL_GROUPS']
assert @ 268 names: ['TOP_LEVEL_GROUPS', 'tuple', 'groups']
assert @ 269 names: ['groups']
assert @ 271 names: ['subcommands', 'subcommands']
CONST TOP_LEVEL_GROUPS lines 243 - 244
```

⇒ 对**该真实样本**，AST 能把「断言行 :268 → 常量名 → 常量定义精确行范围（243-244）」**完全机械化**，且唯一解。纯正则同样可解（`==\s*([A-Z_][A-Z0-9_]*)` 取 `TOP_LEVEL_GROUPS` + 括号配平得 243-244，实跑一致），但正则无法处理作用域/别名/多引用。

#### 3.2 分层规则（推荐实现）

| 步 | 输入 | 方法 | 适用边界 |
|---|---|---|---|
| S1 | 失败行原文 | 正则 `cross_key_test=(\S+?)::(\S+?)(?:\s|$)` | 只依赖 AC-011 约定的字段形状；失败即降级 |
| S2 | `(file, test_id)` | `ast.parse(file)` 找 `FunctionDef/AsyncFunctionDef` 同名 | 需要文件可解析；解析失败 → 降级 |
| S3 | 函数体 | 收集 `Name(Load)` ∩ 模块级 `Assign/AnnAssign` 目标名 | **必须**排除本地同名绑定（见 3.3 `shadowed`）；命中数 ≠ 1 → 降级 |
| S4 | 常量名 | `Assign` 节点的 `(lineno, end_lineno)` = 冻结常量块候选行范围 | 只接受**同文件**（跨文件常量见 3.3） |
| S5 | 常量值 | `ast.literal_eval` 必须成功（字面 tuple/list/str/常量拼接） | 非字面量（f-string/comprehension/函数调用）→ 降级 |
| S6 | 兜底 | 若 S2/S3 不可用：在函数行范围内正则 `==\s*([A-Z_][A-Z0-9_]*)` 取常量名，再从 `^NAME\s*=` 起括号配平取块范围 | 仅测「单一断言、单引用、同文件字面量」的窄形状 |

#### 3.3 失败模式（10 个人造变体实跑 + 真实语料观察）

实跑结果（temp 脚本）：

```
direct           -> refs=['K']            span=(1,1)     # 正常
multi_const      -> refs=['A','B']        spans A,B      # 歧义：断言引用两个常量
helper_assert    -> refs=['K'] asserts=[]                # 断言在 helper 内 → 断言行不可得（常量仍可得）
imported         -> refs=[]                              # 跨文件常量：同文件解析不可得
aliased          -> refs=['K2'] (K2=K)    span=(2,2)     # 别名：定位到别名赋值而非原始定义
getattr          -> refs=[]                              # 动态引用：无 Name 节点
indirect_local   -> refs=['K']            span=(1,1)     # 经局部变量间接引用（可解，但要跨一步数据流）
shadowed         -> refs=['K'] span=(1,1)                # 局部遮蔽同名：误判为模块常量（false positive）
no_assert        -> refs=[] asserts=[]                   # 无断言（红来自异常/集合差异）
conditional      -> refs=[]                              # 常量在 `if` 内赋值（不在 tree.body）→ 漏
```

扩展失败模式（未跑，逐条可推）：常量由 `+`/`%`/`.format()` 拼接、`globals()[...]`、`__getattr__`、`collections.namedtuple`/dataclass 实例、`set` 字面量做比较但期望集来自 fixture 参数（FM 语料里大量 `hitl.key_sets_ok()` 这类 **fixture 载入的期望**）——此时**文件内根本不存在可定位的常量块**，只能来自**外部契约文件**（如 FM `tests/gui_contract/*.py`、`tests/fixtures/gui_contract/v1/*.json`）。

**真实语料的风险面**：`tests/test_hitl_channel.py` 里还有 `ANSWER_OK_KEYS`（:247，被 :743 断言引用）等同形常量；若某天红落在 :743，AST 会给出 `ANSWER_OK_KEYS:247`——**定位正确但工单边界必须由失败断言决定**，不能"取文件里第一个大写常量"。⇒ S3 必须**从函数体出发**（而不是从文件扫描），这正是 AST 相对"文件扫描 + 最近常量"启发式的关键优势。

#### 3.4 判定

- **机械化可行**，前提是 S1–S5 全过；任一不过 → **降级为仅提案**（spec R-2 已定）。
- **启发式不可独立作为边界权威**：它只用来**生成候选行范围**；工单里必须同时记 `frozen_symbol` + `old_block_sha256`，让行范围可被机械复核（行号漂了、文件被改过都会立刻暴露）。⇒ 支持 D-006 的**混合**方案（见结论映射）。

### Q4 行集合 diff 的计算口径

#### 4.1 两种候选口径

| 口径 | 定义 | 优点 | 缺点 |
|---|---|---|---|
| A. 行号集合 | `{(file, line_no)}` | 直观、易打印 | 行号在**混合换行/插入删除**下漂移（§4.2）；无法表达"字节变了但行号没变"；无法防 EOL 翻转（P-010） |
| B. 三元组 | `{(file, line_range, old_bytes, new_bytes)}`（`old_bytes` 用 sha256 表示） | 可独立重算、抗行号漂移（行号只是显示）、`old_bytes` 同时就是回滚素材与授权锚 | 稍重 |

**推荐 B**，并且：

- 判定用 `sha256(old_line_block_bytes)`（含行尾），computed with `splitlines(keepends=True)`（先例：`mw.py:2407` 的块编辑器与 `test_mw_partition.py:94-109` 的 `_block_region` 都走 `keepends=True`）。
- 越界判据 = 实际改动行范围集合 ⊆ 工单声明的 `line_range` 集合；**行范围相等还不够**，必须再过一遍"新块 sha == spec 的 `new_block_sha256`"（防"范围对但内容被掺入别的改动"）。
- 行号存储时另附 `anchor_symbol`（常量名）与 `old_block_sha256`，三者不一致即 fail-closed。

#### 4.2 EOL（P-010）对判定稳定性的影响

- P-010 逐字（`.agenticdoc/_pitfalls.md:111-121`）：写回必须显式 `newline="\n"`；或 `read_bytes().replace(b"\r\n", b"\n")` 复原创伤判定；判据是 `<file> CRLF=<n> LF-only=<m>`，源码仓应 `CRLF=0`。
- **实测 Q3 语料文件正是混合换行**（`repair-r1-out-20260925-r3.txt`：118 CRLF / 106 LF-only），行号随口径漂移（§3.0 的 220 vs 209）——**这是"用行号当判定锚"的直接反例**。
- 目标文件 `tests/test_hitl_channel.py` 是**纯 LF**（39476 B / 826 LF / 0 CR）。
- 仓内两种哈希口径**都已存在，语义不同，必须选一并在文档里写死**：
  - `closure.py:135` `hashlib.sha256(achieved.read_bytes())` —— **字节精确**（注释 `closure.py:29-31` 明确"no EOL normalization，newline-only 人工修复也会失效授权"）。
  - `mw_common.py:2926-2934` `sha256_eol_normalized` —— **CRLF→LF 归一**（注释：core.autocrlf=input 翻转不产生内容变化，字节精确会误报 drift）。
- **推荐**：授权与回滚锚用**字节精确 sha**（对象是"恢复原状"，必须逐字节）；"是否零残留"的最终判定用**字节精确 sha 相等**；`sha256_eol_normalized` 只用于**辅助诊断**（区分"真内容改动"与"纯 EOL 翻转"）。理由：AC-005 写的是"被涉及文件最终 sha256 等于工单创建时的 sha256"——**恢复原状**语义下 EOL 归一化会掩盖一次真实的 EOL 漂移。

#### 4.3 仓内已有的 diff/行集合工具

- `difflib`：全仓仅 `test/test_target_baseline.py:218`（`difflib.unified_diff(..., lineterm="")`，打印前 60 行后 `pytest.fail`，纯显示）。
- `test_autopilot_closure.py:65` `_snapshot(directory) -> {name: bytes}`：测试内前后快照断言"无残留"——**形状可借鉴，非生产件**。
- FM `repair_r1_frozen_recheck.py`：**文件级** sha 集合（冻结集逐条 sha + `git status --porcelain` 改动集求交），**无行级能力**。
- **结论：无生产侧行级 diff 工具，需新建**（但只是标准库 `difflib`/`splitlines(keepends=True)` 的组合，无外部依赖）。

### Q5 验证执行路径：谁跑定向复跑与全量对照

#### 5.1 "框架不跑套件"再次确认

- L3 prompt `conductor.py:1113-1124` 逐字含「证据记录制：不重跑命令」「需要重跑才能确认的验证命令标记 needs-rerun 并计入遗留」——L3 是**记录制**。
- 框架唯一的"门禁检查"`advance_phase.py`（`.tmp/agentic-task/core/scripts/advance_phase.py`）`:580` `check_gate(key_dir, target)` 是**文件/模式静态检查**（`:187-284`），全文无 pytest/套件调用；其 `subprocess.run` 只在 `:424`（`git rev-parse`）与 `:596`（调 `update_index.py set-phase`）。
- ⇒ RQ-1 Q4 结论成立：**框架无套件执行能力**，本 key 的 AC-006 必须自带执行路径。

#### 5.2 仓内"跑命令并留原文"的现成先例（逐个 file:line + 能否复用）

| # | 位置 | 形状 | 能否复用为「定向复跑 + 全量对照」 |
|---|---|---|---|
| (i) | `autopilot/advance.py:164-205` `advance()`（`subprocess.run` :181） | `subprocess.run([sys.executable, "-X","utf8", script, key, phase], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)`；返回 `(rc, stdout, stderr)`；缺框架返回 `(1,"",reason)` | **范式可复用**（cwd/UTF-8/timeout/返回三件套都与 P-012 一致）；脚本固定为 `advance_phase.py`，**参数面不可承载 pytest**。`_ADVANCE_TIMEOUT_SEC=120`（:36）**不够全量套件**（FM 实测 630.51s，见 `refreeze-request-20260925-guarded-closeout.md:11`） |
| (ii) | `conductor.py:1700-1711` `_set_index_phase` | `subprocess.run([...update_index.py, "set-phase", key, phase], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)` | 同上，固定脚本 |
| (iii) | `mw.py:957-1046` `_toolchain_run` | `subprocess.run(command, shell=True, cwd=control_root, capture_output=True)`（`:1009`）→ `cmd.txt` / `run.log`（stdout+stderr 合并）/ `exit.txt` / `errors.txt` / `meta.json`（含 `exit_code`、`seconds`、`error_line_count`、`ok`）；命令模板来自 per-project `target.yml: toolchain.<name>`（`mw_common.py:2866` `render_toolchain_command` 渲染 `{game}/{engine}/{uproject}`） | **最接近可复用**：命令可配、原始输出落盘、退出码/耗时/派生行都有。**不可直接用**：`ok` 判据依赖 `mw_common.py:2961` `scan_build_error_lines`（`_BUILD_ERROR_RE = error C\d{1,5}\|LNK\d{4}\|error :`，UE/MSVC 专用，测不到 pytest 红数）；`shell=True` 与 `--watch` 的 EOL 归一 sha 是给构建面用的 |
| (iv) | `mw.py:3875-3884` `_run_capture` | `subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)`，**无 cwd**，失败返回 `None`（丢原文） | **不可复用**（无 cwd、丢原始输出，违反 P-012"失败原文是唯一词表载体"） |
| (v) | worker 派发：`conductor.py:1546-1560`（repair）/`1047-1065`（exec `phase-writer`） | 派一个 pi coding worker（tools 含 `bash`），结果落 `workers/<task>/output.md` + `trace.log`；launcher 把 worker **进程** stdout+stderr 落 `<task_dir>/worker.log`（`launcher.py:53-54` `_worker_log_path`，`:953-966` 重定向） | **可跑命令**（bash 工具），但 **`worker.log` 不是 pytest 原始 stdout**（bash 工具输出进 agent 转录，不进 pi 进程 stdout）；原始 stdout 只有 worker **自觉**写进 evidence 文件才有；且长命令会被 idle 看门狗杀（见 5.3） |
| (vi) | FM 语料 `repair_r1_verify.py`（`.agenticdoc/cli-run-state-and-events/evidence/runs/`） | `_run_pytest`（`:81-94`）：`[sys.executable,"-X","utf8","-m","pytest",*argv,"-s"]`，`capture_output=True`，`timeout=1800`，**内存取全量 stdout+stderr**；超时也保留部分输出（`[TIMEOUT]`）；结果逐字写进 append-only 证据文件（`_next_out` → `-rN`，`:62-70`），并派生 `[VERIFY]` 行与 `SUMMARY` JSON | **这就是 AC-006 的真实形状**（定向复跑 `["tests/test_hitl_channel.py","-k","top_level_command_groups","-q"]` :324；批量对照 6 文件 :348）。**但它不是框架能力——是每轮人工/worker 手写的项目脚本**。本 key 若采纳，需把它机制化 |

#### 5.3 两条实现路径的 Pros/Cons

**选项 A：conductor 直接 `subprocess`**
- Pros：原始 stdout/stderr 是**进程现场输出**，P-012 硬要求天然满足；**不受 worker idle 看门狗影响**（框架侧 `DEFAULT_IDLE_MS=10*60_000`，`worker-mode.ts:146`——实测全量套件 630.51s > 10min 会杀 worker，`refreeze-request-…-guarded-closeout.md:74-80` 已记录该事故并要求 `PI_WORKER_IDLE_MS=1800000`）；before/after 红数可在同一函数里紧邻计算；证据包组装与闭合事务同进程、天然原子（`conductor.py:1715` 范式）。
- Cons：命令面必须来自 **per-project 配置**（P-015：落 `config.json` 不落 env，否则重启丢配置；`config.py:38/51/75` + `autopilot/config.py`）；全量套件是**长阻塞**（FM 630s+），要么阻塞 tick（伤 spec §2.2 的 tick 开销边界），要么做成"异步 + 下 tick 收割"（需新增状态位）；命令注入风险需 `shell=False` + list argv（先例 `advance.py:186-188` 正是 list argv）。

**选项 B：派 exec/verification worker**
- Pros：复用 `dispatch.py` 派发 + `launcher` 进程隔离（GC-3）+ 工具白名单；worker 可用 LLM 判断"哪个红是跨 key / 哪个是自身回归"（框架不做分类，RQ-1 Q4）。
- Cons：①**拿不到保证的原始 stdout**——必须要求 worker 自己把 `pytest` 原始输出写到指定证据文件，而这是"纪律"不是"机制"（P-005 家族：只有读者没有写者）；②worker 长命令被杀（5.3 已述）；③worker 结果要经 `output.md` 转录，有 P-013 截断风险；④多一层 token 成本与不确定性（同一个 pytest 命令由 LLM 转述，违反"机器生成、逐字锚定"的取证要求 `spec §1.1 附带发现`）。

**推荐：A（conductor 直接 subprocess）**，理由：
1. AC-006 的两项（定向复跑**原始 stdout** + 全量红数 before→after）是**机械可判**证据，必须由机制自己产生（P-014 家族：判据与表达措辞差会毁掉取证）；
2. 全量套件时长 > worker idle 阈值，B 需要额外调参且仍不保证原文落盘；
3. A 可直接复用 (i)/(iii) 的"cwd + UTF-8 + timeout + 三件套返回 + 落盘 run 目录"范式，只是把命令源从固定脚本换成 per-project `config.json` 的命令模板；
4. **B 保留为诊断路径**：`xkey_repair_enabled` 开启时，conductor 先跑定向复跑拿原始红；若"红 → 冻结块"定位歧义（Q3 降级），才派一个 coding worker 产提案（不落盘、不改状态），conductor 校验后应用。

**落地要点（给 design 的约束）**：
- 命令放 `config.json`（P-015），形状建议 `xkey_repair: {enabled, targeted_cmd, full_cmd, timeout_s}`；渲染复用 `mw_common.render_toolchain_command:2866` 的 fail-closed 占位符语义。
- `subprocess.run(argv_list, cwd=project_root, capture_output=True, timeout=..., encoding="utf-8", errors="replace")`，**`shell=False`**；超时也保留 `exc.stdout/stderr`（先例 `repair_r1_verify.py:88-90`）。
- 原始输出落 append-only 证据文件（先例 `_next_out` 的 `-rN` 命名 + `self_sha256` 自锚，`repair_r1_frozen_recheck.py:62-70`、其输出文件头 `script=… self_sha256=…`）。
- 红数解析**不要复用** `scan_build_error_lines`（`mw_common.py:2961`，UE 专用）；应解析 pytest summary 行（先例 `repair_r1_verify.py:96-99` `_last_summary`：`^\d+ (?:passed|failed)` 取最后一条）。
- 失败原文**不得经 200 字符压平管道**（P-012；`conductor.py:713` `_one_line(text, limit=160)` 就是那个压平器——证据包必须走原始文件路径，不走 timeline）。

## 结论 → 决策映射

### D-005 修复应用路径 ⇒ **推荐 (b)：worker 只产提案，conductor 前置校验后应用（零残留）**

- **(a) 判定不可取（MVP 内）**：worker 侧对 `write/edit/bash` 零路径强制（Q1 §1.1-§1.6），且 FM 上 implementation-gate 根本不触发（§1.3）；仓内**无回滚原语**（§1.7）。走 (a) 要新建"快照 + 行集合 diff + 越界回滚"三件，且"越界窗口内文件已被污染"，与 spec §2.3「越界即作废（fail-closed），无人工例外路径」的强语义相抵。
- **(b) 零残留由构造保证**：worker 只写**提案文件**（提案目录/新文件，不在被涉及树的写面上）；被涉及文件在追认前字节不变（AC-003 已要求），追认后由 conductor 在校验通过后应用——**没有"残留"这个状态**。AC-005 的"前置校验或快照回滚二路径取一"⇒ **取前置校验**。
- 需新建的两件：行级 block-replace 应用器（Q2 §2.3，~20 行，范式 `mw.py:2054`）、行集合/字节校验器（Q4 §4.1 三元组）。锁与原子写现成（§2.1/§2.2）。
- 附带收益：与 AC-006 的证据包、AC-007 的两 key 写回在同进程顺序完成，天然贴合 `_done_transaction`（`conductor.py:1715`）的 check-before-write 事务范式。

### D-006 冻结块定位 ⇒ **推荐 混合：工单显式声明（权威）+ 启发式填充行范围（候选）+ 机械复核（兜底）**

- **单一"启发式"不够**：Q3 §3.3 的 10 个变体给出 5 类不可解（跨文件常量 / 动态引用 / 多常量歧义 / 条件赋值 / fixture 期望）；且启发式本身**不知道断言主体**（`ANSWER_OK_KEYS:247` 与 `TOP_LEVEL_GROUPS:243` 同形）。
- **单一"显式声明"不完整**：人写不出精确 `line_range`（FM 手写申请自己就把 `TOP_LEVEL_GROUPS` 的定位写成"定义见该文件 :1 附近"，实为 `:243-244`——spec §1.1 已记为"取证不可核"）；A-06 的 4 路径白名单（`refreeze-request-20260925-guarded-closeout.md:26-33`）也只到"路径 + 允许改动类型"的自然语言级，不可机械判。
- **混合落法**：机器按 S1–S6 生成 `{file, frozen_symbol, line_range, old_block_sha256}` → 写进工单 → 人在 gate 上追认（可修正/拒绝）→ 应用时 conductor **重算** `sha256(line_range 处的字节)`，不等于工单值即作废（行号漂了/文件被动过都会暴露）。定位歧义（S3 命中 ≠ 1 或 S5 非字面量）⇒ **降级仅提案**（spec R-2 的"定位不确定时降级"落地为这一条判据）。
- 显式声明还应承载"**不可触碰**"清单（同文件其它常量/断言主体），与 AC-005 的"子集"判据同源。

### D-007 验证执行路径 ⇒ **推荐 conductor 直接 subprocess**（per-project 配置命令；worker 仅作诊断旁路）

- 见 Q5 §5.3：原始 stdout 可保证、不受 worker idle 看门狗限制、与证据包/闭合同进程原子；全量套件 630s+ 与 `DEFAULT_IDLE_MS` 10min 的冲突（`worker-mode.ts:146`）使 worker 路径不可靠。
- 命令源必须落 `config.json`（P-015 / AC-008）；`shell=False` + list argv；超时保留部分输出；原始 stdout/stderr 落 append-only 证据文件并自锚 sha（先例 `repair_r1_verify.py` / `repair_r1_frozen_recheck.py`）。
- 红数解析用 pytest summary 行（**不复用** `scan_build_error_lines`）；跨 key vs 自身回归的分类**不由本机制做**（spec 边界），仍由 L3/人判断。

### 未发现（否证清单）

- **未发现**「快照 → 越界检测 → 自动回滚」生产先例（`rollback|revert|restore|snapshot` 全扫：唯一生产命中 `mw.py:2794-2805` 的 pre-write `.bak`）。
- **未发现**通用行级替换/补丁应用工具（`patch|apply|line_range|replace_lines` 全扫：最接近的是 `mw.py:2054/2443/2475/2527` 的 YAML 块编辑器，按 `key:` 头部定位，不接受行号）。
- **未发现** unified diff 的解析/应用侧（`difflib` 仅 `test/test_target_baseline.py:218` 显示用）。
- **未发现**「行级编辑规格」JSON schema（`old_sha|new_sha|old_bytes|edit_spec|patch_spec` 全扫 0 命中）。
- **未发现**「失败 → 修复票」的机器化应用侧（FM 的 `repair_r1_verify.py` / `repair_r1_frozen_recheck.py` 是**每轮手写脚本**，非框架件）。
- **未发现**通用命令执行器（`autopilot/*.py` 的 `subprocess` 仅 `advance.py:92/181` 与 `conductor.py:1705`，全部固定脚本）。
