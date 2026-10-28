# T-D2 — G2/G3 Python 侧接缝：`mw worktree rm|add` 与 junction 注册表（design 期 RQ-D2）

- type: research
- key: mw-worktree-junction-guard
- 角色约束: 只读；允许 read/find/grep/ls/bash，禁止任何破坏性命令
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-registry-and-worktree-cli-20261013.md`

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 共享工作树不被并发破坏是并行开发的前提；G2/G3 把「正确删除顺序」固化成**唯一正规命令**与**对称命令 + 巡检**，不依赖 agent 自觉。
- **G2/G3 定义（原文）**: `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md`（v3）§6 —— G2 = `mw worktree rm <path>` 固定六步（枚举 reparse point → 校验目标在仓库内 → 只摘链 `rmdir`（禁 `/S`）→ 复核主树 `node_modules/@earendil-works/*` 链接目标逐条未变 → 才 `git worktree remove --force` → 打印前后对照；任一步失败即中止、不降级继续）；G3 = `mw worktree add` 默认不建链，需建链则登记注册表 + `mw doctor` 报出遗留的、指向真树的 junction。
- **spec 期已坐实（直接引用，不要重做）**:
  - `mw.py` CLI 骨架：`packages/multi-workers/mw.py:5324-5659`（`sub.add_subparsers` + `dispatch` dict，`:5639-5659`）；二级动作范式 `_RAG_ACTIONS`（`:2247`）、`cmd_autopilot`（`:3553`）；错误约定 `print(..., file=sys.stderr); return 1`（`:624-628`）；
  - doctor 挂载点：`packages/multi-workers/mw_common.py:2957-2996`（`doctor_report`）、`:2780`（`_doctor_issues`）、`:2999`（`format_doctor_text`），后加段走 `cmd_doctor` 注入（`mw.py:522-532`）；生产 `_doctor_*` 函数 13 个；
  - `mw worktree` 子命令**当前不存在**；仓库内 reparse point 探测原语**0 命中**（需新建）；
  - Python 3.14.3：`os.path.isjunction` 可用、`os.lstat().st_reparse_tag` 可用、`IO_REPARSE_TAG_MOUNT_POINT=2684354563`；`f"os.path.islink"` 对 junction 为 False（不可用）。
- **判据（spec）**: AC-004 六步不可跳步；AC-005 只摘链、主树零损伤；AC-006 链接目标在仓库外 ⇒ fail-closed 拒绝且不摘链；AC-007 任一步失败 ⇒ 中止并保留现场；AC-008 注册表；AC-009 doctor 报遗留链且无遗留时不误报。

## 要求（必须给「原文 + 文件:行号」）

1. **`mw worktree rm`/`add` 的落点与骨架**：给出照哪个先例写的具体代码位置（subparser 注册名/dest、action dispatch 分发、参数解析、退出码）；六步在 Python 侧的分工（哪几步必须在同一进程/同一次调用内完成）；「中止、不降级继续」用什么控制流表达（给出与既有 `mw.py` 风格一致的草案）。
2. **注册表（G3）**：调研 mw 现有**状态/注册表文件**约定 —— `.mw/**`、`.agenticdoc/.mw/**`、`_workers.parallel`、mw run/lock/queue 文件的实际路径与格式（给 `文件:行号` 与样例）；给出 registry 的**存放位置 + 格式 + 读写 API** 草案；并列出仓库内**可复用的文件锁原语**（goal.md 约束：O_CREAT|O_EXCL 独占锁）的实现位置与调用样例。
3. **doctor 检查新增**：现有 `_doctor_*` 检查如何注册/如何产出 issue（原文），新检查（遗留的、指向真树/仓库内的 junction）应挂在哪里、输出哪些字段（与 AC-009 对齐）；给出检查函数草案签名；并说明**成本**：枚举 `node_modules/@earendil-works/*` 与全仓扫描的差异（可实测耗时）。
4. **`mw worktree add` 与既有 bootstrap 的关系**：`mw.py` 里 npm 引导路径（`install_cmd = [npm, "install" if node_modules.is_dir() else "ci", "--ignore-scripts"]` 附近）有没有可复用函数/开关（默认不建链时应走哪条），给行号。
5. **未坐实项**显式列出。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-registry-and-worktree-cli-20261013.md`（本卡唯一允许写入的文件；其余路径只读）

单一文件 `evidence/research/design-registry-and-worktree-cli-20261013.md`，结构：

- `## TL;DR`
- `## 事实`（逐条 `[VERIFY]`：原文 + `文件:行号` + 实测输出）
- `## 对 design 的直接含义`（可直接写进 design.md 的 CLI/注册表/doctor 接口草案）
- `## 未坐实 / caveat`

约束：只读；**不得修改任何生产文件**（本任务只产出证据）；可在 `%TEMP%` 内做只读/临时 fixture 验证，禁止触碰真树 `H:\git\Multi-Workers` 的 junction 或 `node_modules`；数值一律实测，推算值标注为推算。
