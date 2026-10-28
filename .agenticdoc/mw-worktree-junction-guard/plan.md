# plan — mw-worktree-junction-guard

> 输入：`spec.md`（AC-001..AC-013，决策 D-1/D-2/D-9 已确认）、`design.md`（§2 落地顺序、§8 写面切分、§9 AC→证据矩阵）、`evidence/research/design-*.md`（含必要性 RQ-N1/N2/N3）。
> 行号一律以 symbol 名为准（`design.md` §7 行号漂移警告）：实现前 grep 函数名，不照抄数字。

## 0. 批次与依赖（落地顺序）

落地顺序由 `design.md` §2 定死：**G1（拦截）与 G2（唯一正规命令）必须同版本**，否则 AC-002 的 block 文本指不到可执行命令；G3/G4 可后置；AC-013 复用 G2 的摘链原语。

| 批次 | 任务 | 语言/写面 | 依赖 | 覆盖 AC |
|---|---|---|---|---|
| **B0** | W-01 词法器下沉（D-3） | TS · `shared/bash-segments.ts`(新) + `implementation-gate.ts` | — | 支撑 AC-001..003 |
| **B1** | W-01（同批）‖ W-02 ‖ W-04 | TS 1 条 ‖ Python 2 条（三个互不相同的文件集） | W-02/04 无前置 | AC-004..008、AC-010/011 |
| **B2** | W-05 G1 guard ‖ W-07 AC-013 脚本 ‖ W-03 doctor 段 | TS · `shared/worktree-junction-guard.ts`(新)+`index.ts` ‖ `scripts/diff-model-catalog.mjs` ‖ `mw_common.py`+`mw.py` | W-05 依赖 W-01；W-03 依赖 W-02 的注册表模块（接口已在卡内冻结，不并行以避免双实现）；W-07 只依赖摘链原语语义 | AC-001..003、AC-009、AC-013 |
| **B2b** | W-05b 补齐 `rm`/`Remove-Item` 尾分隔符/通配形态 | TS · 同一 guard 文件 + 同一 decide 测试文件 | 依赖 W-05（已落地）；**PM 写卡错误的事后补齐**（D-4 第 2 条 → 决策 D-11） | AC-001/002/003 的扩展面 |
| **B3** | W-06 G1 覆盖测试 ‖ W-08 AC-012 端到端夹具 | TS suite ‖ Python 夹具 | 依赖 W-05 / W-02+W-03 | AC-001..003、AC-004..007、AC-012 |
| **B4** | PM 收口：`npm run check` + `./test.sh` + 只读真机复核 + `achieved.md` + QG | — | B0..B3 全绿 | 全部 |

**为什么 W-01 必须最先且独占**：G1 直接 import 它（D-3，避免两套词法漂移）；且 `implementation-gate.ts` 是跨 key 共享热文件（其它 key 也改它）⇒ 同一时刻只允许一个写者。W-01 落地后 B1 的四条任务文件集两两不相交，可全并行。

## 1. 写面唯一性（并行边界）

| 文件 | 唯一写者 | 说明 |
|---|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/shared/bash-segments.ts`（新） | W-01 | 由 `implementation-gate.ts:273-518` 下沉并 `export` |
| `…/shared/implementation-gate.ts` | W-01 | 仅改 import（行为不变）；跨 key 串行点 |
| `packages/multi-workers/mw.py` | **W-02（全程唯一写者）** | 子命令注册 + `--all-domains` 开关 + `_npm_hydrate` 抽取；其它任务若需改 `mw.py`，把补丁文本交给 W-02 或另开串行小任务 |
| `packages/multi-workers/worktree_cmd.py`（新） | W-02 | G2 六步事务 + CLI |
| `packages/multi-workers/worktree_doctor.py`（新） | W-03 | AC-009 判定（域 a/b/c），import `tree_watch`（纯 stdlib）+ `worktree_registry`（注册表单源） |
| `packages/multi-workers/mw_common.py` | W-03 | 只加 AC-009 段（`doctor_report`/`_doctor_issues`/`format_doctor_text`），不动其它段；**函数内 import** 破循环（`worktree_registry.py:37` 顶层 import mw_common） |
| `packages/multi-workers/mw.py`（doctor 开关） | W-03 | 仅 `mw doctor` 的 `--worktree-scan-roots`（域 c）；其余一律不碰（W-02 已落地后可写） |
| `packages/multi-workers/mw_common.py` | W-03 | 只挂 AC-009 段（`doctor_report` / `_doctor_issues`），不动其它段 |
| `packages/multi-workers/launcher.py` | W-04 | 只加采样挂点 + 告警，不动派发逻辑 |
| `packages/multi-workers/tree_watch.py`（新） | W-04 | AC-010/011 判据与状态文件 |
| `…/agent-team-loop/index.ts` | W-05 | 只加一行 guard 注册 |
| `…/shared/worktree-junction-guard.ts`（新） | W-05 | G1：`decideWorktreeRemove`（纯函数）+ 扫描器 + block 文案（文件名照 `design.md` §3.1） |
| `scripts/diff-model-catalog.mjs` | W-07 | AC-013 最小修复 |
| `test/suite/bash-segments.test.ts`（新） | W-01 | 实际落地文件名：`test/suite/agent-team-loop-bash-segments.test.ts`（已完成） |
| `test/suite/worktree-junction-guard-decide.test.ts`（新） | W-05 | 纯函数矩阵（(a)-(d) + 事故形态 + 反向对照）；W-05b 在同一文件追加 | |
| `test/suite/worktree-guard-coverage.test.ts`（新） | W-06 | 必须用 `test/suite/harness.ts` + faux provider |
| `packages/multi-workers/test_worktree_cmd.py`（新） | W-02 | 已落地（37 测试） |
| `packages/multi-workers/test_worktree_doctor.py`（新） | W-03 | AC-009 正反两向 + 域 c + 循环回归（替代原计划的 `test_worktree_registry.py`：注册表测试已随 W-02 落在 `test_worktree_cmd.py`） |
| `packages/multi-workers/test_tree_watch.py`（新） | W-04 | |
| `packages/multi-workers/test_worktree_e2e.py`（新） | W-08 | AC-012 夹具（阳性 + 阴性两向） |

## 2. 任务清单

### W-01 · 词法器下沉（TS，B0，独占）
- **写面**：上表 W-01 三行；**禁止**改 `implementation-gate.ts` 的判定逻辑（纯搬迁 + import）。
- **交付**：`shared/bash-segments.ts` 导出 `parseBashSegments`（及 `BACKSLASH_ESCAPES_*` 若被引用）；`implementation-gate.ts` 改 import；`test/suite/bash-segments.test.ts` 断言 **事故 token 原样取出**：`git worktree remove --force "$env:TEMP\qg-head"` → 分段含 `worktree`/`remove`/`--force`/`$env:TEMP\qg-head`（引号剥离、插值不展开）。
- **验收**：`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/bash-segments.test.ts`；根 `npm run check` 零 error/warning/info。
- **证据**：`evidence/` 下本任务报告，含 before/after 行号与调用点清单。

### W-02 · G2 唯一正规命令（Python，B1）
- **写面**：`mw.py`、`worktree_cmd.py`(新)、`test_worktree_cmd.py`(新)。
- **交付**：`mw worktree rm|add|list`，契约逐字照 `design.md` §4.3；`rm` 六步（枚举 → 校验三分类 → 只摘链 → 复核主树 `@earendil-works/*` 目标未变 → `git worktree remove --force` → 前后对照），任一步失败 `ABORT at step N/6` + 保留现场、**无 `try/finally` 补偿写**；`add` 默认不建链、`--link-deps` 走注册表（W-03 的接口，若 W-03 未落地则先写注册表 stub 并在报告中标注）；`_npm_hydrate(target_root)` 从 `install_cmd` 抽取；`--json` 机器出口。
- **验收**：`cd packages/multi-workers; python -m pytest test_worktree_cmd.py -q`（含步序断言、步 2 失败 ⇒ 零摘链）。
- **夹具硬约束**：全部在 `%TEMP%\`；链接目标必须在夹具内；清理用 `cmd /c rmdir <link>`（无 `/S`）；**禁碰真树**。

### W-03 · G3 注册表 + doctor 段（Python，B1）
- **写面**：`mw_common.py`、`worktree_registry.py`(新)、`test_worktree_registry.py`(新)。
- **交付**：注册表（目标 / 创建时刻 / 创建者）读写，锁复用 `acquire_lock`/`release_lock`，写入走 tmp + `os.replace` + 读回验证；AC-009 段**必须挂在 `doctor_report` 内部**（`mw.py` 注入段永不产生 issue —— spec §6 坑点 2）；判定域默认 = 注册表域 + 仓库内 `node_modules/*` 顶层（决策 D-2），全域走开关。
- **验收**：`python -m pytest test_worktree_registry.py -q`，含 `capsys` 断言（有遗留 ⇒ 报出路径；干净仓库 ⇒ 零行输出 + rc 不变）。

### W-04 · G4 采样（Python，B1）
- **写面**：`launcher.py`、`tree_watch.py`(新)、`test_tree_watch.py`(新)。
- **交付**：在 `launcher._poll_once` 的挂点每 6 poll（30 s）采样一次，`PI_TREE_WATCH_SEC` 可覆盖、`0` = 关；判据 = `git ls-files -d` 按路径面排除 dist，阈值 `max(20, 1% * 2756) = 28`；断链判据（`lstat`/`isjunction`，不用 `existsSync`）；采样统一 `--no-optional-locks`；告警形状照既有 `launcher.py` 告警。
- **验收**：`python -m pytest test_tree_watch.py -q`（合成骤降触发、单文件编辑不触发、断链触发、完好链不触发）。

### W-05 · G1 拦截（TS，B2）
- **写面**：`shared/worktree-guard.ts`(新)、`index.ts`（一行注册）。
- **交付**：`decideWorktreeRemove(input) -> allow|block` 纯函数 + 同步 fs 扫描器（显式栈、禁 `{recursive:true}`、命中 reparse point 不下钻、entry 预算超限 block）；覆盖形态 = `git worktree remove|rm`（含 `--force`、`-C`、`cd`/`Set-Location` 基准）+ `<path>/`、`<path>/*`（决策 D-4）；block 文案照 `design.md` §4.3 模板（与 G2 逐字一致）；顶层目标不存在 ⇒ allow。
- **硬约束**：**不得**复用 worker write-scope 的抽取器（非字面路径 fail-open）；判定按命令结构，不按词表宽匹配（`design.md` §3.3 第 5/6 条）。
- **验收**：`npm run check`；测试由 W-06 覆盖（同一 key 内两个 worker 串行改不同文件，W-05 必须先落地）。

### W-06 · G1 覆盖测试（TS，B3）
- **写面**：`test/suite/worktree-guard-coverage.test.ts`(新)。
- **交付**：faux provider → agent loop → `ExtensionRunner` → 真 `activate()`；AC-001 = block 且 `BashOperations` 记录器证明**零执行**；AC-002 = 文案含链接路径 + 目标 + 可照抄命令；AC-003 = 17 例矩阵（`design.md` §9），`unknown-var`/`glob`/`bare-name-ambiguous` 必须 BLOCK。
- **验收**：`cd packages/coding-agent; node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-guard-coverage.test.ts`。
- **约束**：不用真实 provider/凭证（AGENTS.md）。

### W-07 · AC-013 脚本修复（B2）
- **写面**：`scripts/diff-model-catalog.mjs`（**只此一处**）。
- **交付**：`git worktree remove --force` 之前摘链（`cmd /c rmdir <wt>\node_modules`，无 `/S`、无尾分隔符；`win32` 才建链的语义保持），或加 `remove` 前断言 `<wt>` 内无 reparse point（复用 G1 扫描函数）。
- **验收**：夹具内跑该脚本的等价流程，断言真树 manifest 的 `removed/added/content_changed/missing_after` **全 0**；反向对照：**现行**脚本在夹具内必须复刻事故（阳性对照成立才说明夹具有效）。
- **硬约束**：不得在真树执行该脚本（它会复刻事故）。

### W-08 · AC-012 端到端夹具（Python，B3）
- **写面**：`test_worktree_e2e.py`(新)。
- **交付**：`%TEMP%\wjg-<key>-<n>\{A,B}`，A = 假真树（`git init` + packages + `node_modules/@scope/*` 链），B = `git worktree add` + `B\node_modules -> A\node_modules` 双层链；阴性对照 = 六步流程跑完 A 的 manifest 全 0；阳性对照 = 直接 `git worktree remove --force` 必须看到 A 侧文件消失（否则夹具不成立）。
- **验收**：`python -m pytest test_worktree_e2e.py -q`。
- **硬约束**：链接目标全部在夹具内；清理 `cmd /c rmdir`（无 `/S`）→ `rmdir /S /Q <root>`。

## 3. 串行点（必须排队，不得并行）

1. **`implementation-gate.ts` 与 `index.ts`**：跨 key 共享热文件。派 W-01/W-05 前先看 `_index.parallel` 是否有其它 live key 正在改这两个文件；有则排队。
2. **`mw.py`**：单一写者（W-02）。B1 之后任何 `mw.py` 改动（如 W-07 若选择走 Python 原语）必须由 W-02 承接或另开串行任务。
3. **G1 与 G2 同版本发布**：W-05 不得先于 W-02 合入发布（AC-002 文案必须指得到可执行命令）。
4. **测试与实现同 key 串行**：W-06 依赖 W-05、W-08 依赖 W-02/W-03 —— 实现落地后才派测试 worker。

## 4. 每批 DoD 与全局门禁

| 批次 | DoD |
|---|---|
| B0 | `npm run check` 全绿；`bash-segments.test.ts` 通过；`implementation-gate.ts` 行为不变（原测试仍全过） |
| B1 | 四条任务各自的单测通过；`npm run check` 全绿；Python 侧 `python -m pytest -q`（新增文件全过、既有不回归） |
| B2 | AC-001/002/003 测试通过；AC-013 阳性 + 阴性对照双向成立（**均在夹具内**） |
| B3 | AC-004..007、AC-012 端到端通过；主树 manifest 零变化 |
| B4 | `npm run check` + `./test.sh`（非 e2e）全绿；真机**只读**复核（`git status`/`ls-files -d`/链枚举）；`achieved.md`（含「## 系统行为变化」「## 遗留」）；`/quality-gate` 出报告 |

**跨 worker 证据义务**（每张卡必带）：① 写入允许面 / 禁止面；② 验收命令原文；③ 改动历史（`file:line` before→after）；④ 唯一证据文件路径；⑤ 目标对齐引用（`goal.md` 锚点 + 至少一条 `path:line`）。research/review 型另按要求（唯一证据文件、审计目标、未覆盖面声明）。

## 5. 风险与回退

| 风险 | 处置 |
|---|---|
| 夹具误指真树 ⇒ 复刻事故 | 卡内硬约束 + 派发前 PM 复核卡片；worker 只允许 `%TEMP%`；清理用不穿透形态；W-08 的阳性对照在夹具内验证（这是唯一的"危险执行"，且负向对照用夹具自身） |
| `checkBashWriteTarget` / `WRITE_VERBS` 语义被顺手扩展 ⇒ 影响其它 key | W-05 卡内明确：**不扩展** `checkBashWriteTarget`（决策 D-4） |
| `mw.py` 行号漂移导致补丁错位 | 卡内要求 grep 符号名（`_parse_args` / `install_cmd` / `_npm_hydrate`），禁照抄行号 |
| Node 判不出 junction vs symlink | junction 权威判定放 Python（spec §6 坑点 5）；TS 侧只用 `lstat.isSymbolicLink()` 做"疑似链 ⇒ 需扫描"的保守判定 |
| 采样命令刷新 `.git/index` | `--no-optional-locks` / `GIT_OPTIONAL_LOCKS=0`，不与其它 git 写操作并跑 |
| G1 误拦正常 `remove` | AC-003 的 17 例矩阵为硬门禁；`unknown-var`/`glob`/`bare-name-ambiguous` 判 BLOCK 是**有意**的保守取向（design §9） |

## 6. 未决 / 假设

- 假设 1：本 key 期间其它 live key 不改 `implementation-gate.ts`/`index.ts`/`mw.py`（派发前每批复核 `_index.parallel`）。
- 假设 2：注册表落点用 `.mw/worktree-registry.json`（形状照 `.agenticdoc/_workers.parallel` 的列语义）；若 W-03 实现时发现更合适的既有落点，需在报告里给出理由。
- 未决 1：AC-013 的修法 (a) 摘链 vs (b) 不建链 —— 默认 (a)，W-07 可在报告中提出反证并改 (b)。
- 未决 2：`decision` 的 entry 预算具体值（design §3.3 建议 20 万条）由 W-05 实测调参并在报告记录。
