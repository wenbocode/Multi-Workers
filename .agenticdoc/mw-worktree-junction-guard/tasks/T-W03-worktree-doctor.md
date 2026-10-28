# T-W03 — G3：`mw doctor` 报出遗留链（AC-009）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 「Worker 崩溃不影响其他 Worker」的对偶面：**共享树上的遗留危险物必须被机器发现**。AC-009 的语料锚点是事故前夜状态（`%TEMP%` 里的活雷 `mwvg-t5\node_modules` 指向真仓 `node_modules`）。
- **挂载点（设计硬要求，`design.md` §5.2；行号为 2026-10-13 实测值）**：
  - 新检查在 `packages/multi-workers/mw_common.py:3748`（`doctor_report`）**内部**装配为 `report["worktree_links"]`；
  - issue 进 `packages/multi-workers/mw_common.py:3525`（`_doctor_issues`，格式照既有 `queue-burst-shape` 一类的 `issues.append(...)`）；
  - 文本行进 `packages/multi-workers/mw_common.py:3790`（`format_doctor_text`，**条件成立才打印**）；
  - **不能**走 `mw.py` 的 doctor 注入段（那里在 `_doctor_issues` 之后 ⇒ 注定只能 informational、不翻退出码）。
- **循环导入（本任务的实际坑，已实测）**：`packages/multi-workers/worktree_registry.py:37` 顶层 `import mw_common` ⇒ `mw_common` **顶层**不能再 import 新模块。做法：只在 `doctor_report` 内做**函数内 import**（一处，带注释说明），下游 `_doctor_issues` / `format_doctor_text` 只读 `report["worktree_links"]` 字典；并加循环回归测试（`python -c "import mw_common"` 必须通过）。
- **判据（决策 D-10，2026-10-13 用户已确认的域 + PM 实测修正的谓词）**：
  - 域 (a) 注册表：`worktree_registry.read_registry(project)` 的登记项（字段实测 = `link` / `target` / `worktree` / `repo_root` / `created_at` / `created_by`，`REQUIRED_FIELDS = ("link","target","created_at","created_by")`）。`link` 仍存在（`os.path.lexists`）而 `worktree` 已不在 ⇒ `leftover`；`link` 已不在 ⇒ `stale-entry`。**默认开**。
  - 域 (b) 仓内顶层：复用 `tree_watch.scan_links(repo_root)`（`packages/multi-workers/tree_watch.py:215`，纯 stdlib；配套 `resolve_link_target` 在 `tree_watch.py:178` 已处理 `\\?\` 前缀剥离与 `normcase`）。**漏掉前缀剥离就必然误判**（PM 实测踩过：不剥前缀时 5/5 链接被算成"目标在仓外"）。判据 = 顶层 `<repo>/node_modules/*` 链，目标规范化后落在 `repo_root` 内 **且链名不在 `package-lock.json` 的 `"link": true` 期望集内** ⇒ `leftover`；在期望集内 ⇒ 正常 workspace 链，**静默**。**默认开**。
  - 域 (c) 全域猎捕：`mw doctor` 新增 `--worktree-scan-roots <dir1;dir2>`（默认空）。给了根时按 depth-1 形态 `<root>\<wt>\node_modules` 扫描并报出指向本仓的链；必须有 entry 预算，超限即停止并标注未扫完。**默认关**。
- **反向对照的硬要求（本仓就是反例现场）**：本仓实测 `node_modules` 顶层链 5 条全部指向仓内，期望集（lockfile `"link": true`）恰好 14 条 = 磁盘 14 条 ⇒ **本仓 `mw doctor` 不得报出任何 worktree_links 行、不得产生 issue、退出码不变**。若你的实现让本仓 `mw doctor` 变红，就是判据写错了（不是本仓脏）。
- 相关 spec 验收：AC-009（报出遗留 + 不误报）；验证矩阵见 `design.md` §9 的 AC-009 行。

## 要求

1. 新建 `packages/multi-workers/worktree_doctor.py`：`build_section(project_root) -> dict`（纯逻辑，无副作用、只读），返回形状至少含 `leftover[]` / `stale_entries[]` / `domains{registry, repo_local, scan_roots}` 计数 / `scanned{}` 成本信息；每个条目给 `path` / `target` / `kind` / `worktree`（可得时）。
2. `worktree_registry` 与 `tree_watch` **必须复用**（注册表 = 单一事实源；链接枚举与 `\\?\` 剥离 = 已有实现）。**不要**在 `mw_common.py` 或新模块里重写 junction 判定/注册表读取。
3. `mw_common.py` 三处改动（除此之外不动任何既有段）：`doctor_report` 内函数内 import + 装配 `report["worktree_links"]`；`_doctor_issues` 里 `leftover`/`stale-entry` 非空 ⇒ `issues.append(...)`（每条一项，含路径与类型）；`format_doctor_text` 里仅在非空时打印。
4. `mw.py` 只加 `mw doctor` 的 `--worktree-scan-roots` 参数并把它透传到 `doctor_report`（若无既有透传通道，按 `doctor_report` 现有签名扩展；**不要**改 `mw doctor` 的其它行为与退出码逻辑）。
5. 新建 `packages/multi-workers/test_worktree_doctor.py`（pytest，夹具全部 `%TEMP%`）：
   - 域 (a)：夹具注册表 + `link` 在、`worktree` 不在 ⇒ `leftover`；`link` 不在 ⇒ `stale-entry`；
   - 域 (b)：夹具仓库 `node_modules/<name>` 链指向仓内且不在 lockfile 期望集 ⇒ 报；把该名字写进 lockfile 的 `"link": true` ⇒ 静默（期望集减法生效）；
   - 域 (b) 前缀坑回归：链接用 `mklink /J`，断言目标被正确判为仓内（防 `\\?\` 回归）；
   - 域 (c)：夹具 landmine（`<tmp>\<wt>\node_modules` → 夹具"真仓"）在给定 `--worktree-scan-roots` 时被报出，不给开关时不报；
   - 反向对照：干净夹具 `count==0` ⇒ 零行输出、无 issue、rc 不变；
   - 循环回归：`python -c "import mw_common"` 成功；`mw doctor`（对本仓**只读**执行）返回码与改动前一致且不含 worktree_links 行。
6. `python -m pytest test_worktree_doctor.py -q` 全绿；既有 `mw doctor` 相关测试不回归（至少跑 `test_doctor_gates.py` 与 `test_serve_doctor.py`）。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W03-worktree-doctor-20261013.md`：`## 结论`、`## 证据`（域 a/b/c 三组实测输出、本仓 `mw doctor` 的 worktree_links 计数与退出码、期望集实测条数、夹具路径与清理命令、pytest 实际输出）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | 本仓 worktree_links: 0 | rc: <值>`。

## 写入允许面

- `packages/multi-workers/worktree_doctor.py`（新建）
- `packages/multi-workers/mw_common.py`（仅上述三处）
- `packages/multi-workers/mw.py`（仅 `mw doctor` 的 `--worktree-scan-roots` 参数与其透传）
- `packages/multi-workers/test_worktree_doctor.py`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W03-worktree-doctor-20261013.md`（新建）

## 写入禁止面

- `packages/multi-workers/worktree_cmd.py`、`worktree_registry.py`、`test_worktree_cmd.py`（W-02 已落地，冻结）、`tree_watch.py`、`launcher.py`、`test_tree_watch.py`（W-04 已落地，冻结）、`scripts/**`、任何 `packages/coding-agent/**`。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove|add|prune`、`rm`、`npm install`；禁止触碰真树 `node_modules` 下的 junction。
- 夹具硬约束：链目标必须在夹具内；清理 = `cmd /c rmdir <link>`（无 `/S`）→ `rmdir /S /Q <root>`。

## 验收命令

```
cd packages/multi-workers
python -m pytest test_worktree_doctor.py -q
python -m pytest test_doctor_gates.py test_serve_doctor.py -q
python -c "import mw_common; print('cycle-ok')"
python mw.py doctor
```

（最后一条对本仓**只读**；断言不含 worktree_links 行、退出码与改动前一致。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
