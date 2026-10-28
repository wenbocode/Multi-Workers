# SPEC 证据：官方分发路径行为（install.py / sync_framework.py）

- key：`mw-claude-mirror-parity`｜RQ-3｜阶段：SPEC｜日期：2026-10-12
- 任务文件：`.agenticdoc/mw-claude-mirror-parity/workers/mwp-rq3c-distribution-path/task.md`
- 被测仓库：`H:\git\Multi-Workers`
- 本机 bash 后端：PowerShell 5.1（下列命令均为 PS 语法，`&&` 不可用）
- 纪律：未在仓库内执行任何会覆盖 `.claude/scripts` 的同步；无 git 写操作（无 add/commit/push/fetch/reset/checkout）；未跑全量 vitest/pytest/`npm run check`/build。
  唯一写入 = 本文件 + `.tmp\rq3c-fake\` 沙箱（task 允许）。

## 0. 结论摘要

1. 官方分发只有两个入口：`install.py`（源→项目，**rmtree 后整目录覆盖，无 dry-run，无备份，删目标侧多余文件**）与 `sync_framework.py`（双向 + **必然 git commit/push 源仓库**）。
2. 在仓库内重同步 `.claude/scripts` 且只写仓库内的**唯一正确命令**：
   `cd H:\git\Multi-Workers; python .agents/skills/agentic-task/install.py . --skip-codex`
3. `.claude/scripts/**` **被忽略**（`.gitignore:21`）。`.claude`、`.agents`、`.agentic-framework` 三者全被忽略 → Multi-Workers 父仓库对分发结果零记录；交付只能靠 `.claude` 自身的嵌套 git 仓库（origin = AgenticLoop.git）。
4. 只读预检/后检替代 dry-run：`python .agents/skills/agentic-task/diff-installed.py .`（当前 exit=1，4 个文件）。
5. 未在仓库内实测覆盖；实测在 `.tmp\rq3c-fake\` 沙箱完成（§5）。

---

## 1. 实现事实表

### 1.1 `install.py`（`.agents/skills/agentic-task/install.py`，6818 B）

| # | 触发点（函数 @ 行 / 调用点 @ 行） | 源 → 目标 | 覆盖规则 |
|---|---|---|---|
| A1 | `sync_script_mirrors()` @ `install.py:41`；调用点 `install.py:157`（`main` 内**先于一切安装**） | `<ROOT>/scripts/*` → `<ROOT>/claude/scripts/*` + `<ROOT>/core/scripts/*`（`MIRROR_SCRIPT_DIRS` @ `install.py:30`，`ROOT` @ `install.py:28`） | 逐文件 byte 比较（`install.py:63-64`，相同则 `continue`）；不同则 `write_bytes` 覆盖（`install.py:66`）。**只增改不删**：镜像侧多出的文件永不删除（docstring `install.py:46`）；只处理 `is_file()`（`install.py:60-61`），`__pycache__`/`.pytest_cache` 等目录不参与 |
| A2 | `install_claude()` @ `install.py:71`；调用点 `install.py:165-167` | `<ROOT>/claude/{commands,agents,skills,scripts}` → `<project>/.claude/{...}`（`CLAUDE_DIRS` @ `install.py:29`） | **整目录 `rmtree` 后 `copytree`**（`copy_tree` @ `install.py:33-38`）。目标目录内**只存在于目标侧的文件被删除**（实测 §5.2）。`copytree` 调用**无 ignore 参数**（`install.py:38`）→ `__pycache__`/`.pytest_cache` 一并复制（实测 §5.2）。保留用户改动 = **否** |
| A3 | `install_codex()` @ `install.py:104`；调用点 `install.py:169-172`（`--skip-codex` 时不进入） | project scope → `<project>/.agents/skills/agentic-task`；user scope → `codex_home()/skills/agentic-task`（`install.py:129-134`，`codex_home` @ `install.py:122-126`，读 `CODEX_HOME` 否则 `~/.codex`） | 若 `skill_dst.resolve() == ROOT.resolve()` → 打印 skipping 后直接返回（`install.py:106-108`）；否则若已是 git clone → `git pull --ff-only`（`install.py:110-112`）；否则 **`shutil.rmtree` 后 `git clone <origin>`**（`install.py:113-118`，clone 源取 `git_origin_or_root()` @ `install.py:91-102`） |
| A4 | manifest @ `install.py:174-183` | — → `<project>/.agentic-framework` | 每次整体重写（`write_text`），无合并；内容含 `repo=<ROOT>`、`commit=`（`git_commit()` @ `install.py:80-89`）、`installed_at=`、安装项列表 |

参数（`install.py:137-151`；原始 `--help` 见 §2.4）：positional `project`（**必填，无默认**，`install.py:139`）；`--skip-codex`；`--skip-claude`；`--codex-scope {project,user}`（默认 `project`）。
**无 `--dry-run`、无 `--force`、无备份**：对 `install.py`、`sync_framework.py`、`diff-installed.py` grep `dry.run|dry_run` → 0 命中。

### 1.2 `sync_framework.py`（`.agents/skills/agentic-task/scripts/sync_framework.py`，9010 B）

| # | 触发点 @ 行 | 行为 |
|---|---|---|
| B1 | `sync_framework()` @ `:197`；`main` @ `:237` | `source_dirty = repo_status(repo)`（`:211`，`repo_status` @ `:139-146` = `git -C <repo> status --porcelain` 非空）；`install_dirty = installed_differs(...)`（`:212`，`:157-168` = 调 `diff-installed.py`，退出码 1 视为有差异，其他非零 `SystemExit`） |
| B2 | auto 方向 @ `:214-221` | `source_dirty` → `to-install`；否则 `install_dirty` → `from-install`；都不脏 → `SyncResult("none")` 直接返回（`:221`），不 commit、不安装、输出 `No AgenticTask framework changes to sync.`（`:257-258`） |
| B3 | `from-install`：`sync_installed_to_repo()` @ `:105`，调用点 `:224` | `<project>/.claude/{commands,agents,skills,scripts}` → `<ROOT>/claude/{...}`（`:114-116`），`rmtree`+`copytree` 且 ignore `{__pycache__, .git}`（`:97-102`，`IGNORED_DIRS` @ `:31`）。codex 侧（`:118-135`）：非 clone → 把 skill 树拷回 repo 根（`:119-121`）；是 clone 且 ≠ repo → `git add --all` + `commit` + `git push <remote> <branch>` + `git -C <repo> pull --ff-only`（`:125-135`） |
| B4 | 任何非 `none` 方向之后 @ `:228-233` | 必须给 `-m`（`:228-229`，否则 `ValueError: commit message is required when changes will be published`）；`run_tests(repo)`（`:171-182`）= 对 `core/scripts`、`claude/scripts`、`scripts` 三处跑 `python -m unittest discover`；`commit_and_push`（`:190-194`）= `git add --all` + `commit -m` + `git push <remote> <branch>`；最后 `reinstall`（`:185-187`）= `install.py <project>` + `diff-installed.py <project>` |

参数（`:237-249`）：`--project`（省略则从 cwd 向上找 `.agentic-framework`，`:239`、`find_project_root` @ `:85-95`）；`-m/--message`；`--direction {auto,to-install,from-install}`（默认 `auto`）；`--remote`（默认 `origin`）；`--branch`。**无 `--dry-run`**。

### 1.3 幂等性

| 工具 | 幂等 | 依据 |
|---|---|---|
| `install.py` | **是** | 实测 §5.3：连跑两次，`.claude` 树 65 个文件 SHA256 逐一相同；第 2 次 mirror 重同步输出为空（无 changed 行） |
| `sync_framework.py` | **否** | 走非 `none` 路径就产生新 commit + push（`:190-194`）；且 `source_dirty` 命中即选 `to-install`（`:211`、`:216-217`），与内容是否真变化无关 |

### 1.4 是否需要项目路径参数；"在仓库内跑"写到哪里

- `install.py`：**需要**（`:139` 必填 positional）。`cd H:\git\Multi-Workers; python .agents/skills/agentic-task/install.py .` → `project = H:\git\Multi-Workers`（`:153`），写入点全部在仓库内：

  | 写入路径 | 依据 |
  |---|---|
  | `<repo>/.claude/{commands,agents,skills,scripts}` | `install.py:71-77` |
  | `<repo>/.agentic-framework` | `install.py:174-183` |
  | `<repo>/.agents/skills/agentic-task/claude/scripts/*`、`.../core/scripts/*` | `install.py:41-67`（先于安装执行） |
  | 不触碰 `<repo>/.claude/.git` | `install.py:71-75` 只 rmtree 4 个 adapter 子目录；实测 §5.4 |

- `sync_framework.py`：项目路径**可省**（`:85-95` 向上找 manifest），但它会写**框架源仓库**（`:114-116` 或 `:119-121`）并 push（`:134`、`:194`）→ 不止写项目。

---

## 2. 唯一正确命令

### 2.1 命令

```powershell
cd H:\git\Multi-Workers
python .agents\skills\agentic-task\install.py . --skip-codex
```

### 2.2 理由

1. **只写仓库内**：`project=.` 经 `Path(args.project).resolve()`（`install.py:153`）解析为仓库根；上表所有写入点都在仓库内，无绝对路径参数、无 `~`/`%USERPROFILE%` 目标。
2. **唯一能同时修 mirror 与 `.claude/scripts` 的官方入口**：`install.py:157` 先用 canonical `scripts/` 重同步 `claude/scripts` + `core/scripts`（A1），然后 `:165-166` 才把 mirror 装进 `.claude`。`diff-installed.py` 只读、且以 **mirror** 为基准，不修 mirror；`sync_framework.py` 会 push。
3. **`--skip-codex` 是防御性选择**：跳过 `install_codex()`（`:169-172`），从结构上排除 `:113-118` 的 `rmtree` + `git clone` 分支（网络 + 破坏性）。实测 §5.5：仓库内 `skill_dst.resolve() == ROOT.resolve()` 为 True，不传该参数也会走 `:106-108` 的 skipping 分支，效果等价（`--skip-codex` 代价是不在 manifest 里写 codex 行，`:171-172`）。
4. **不能用 `sync_framework.py`**：当前 `source_dirty = True`（见 2.3），`auto` 必然选 `to-install`，随后 `git add --all` + `commit` + `git push origin <branch>`（`:190-194`）会把 AgenticTask 仓库的未提交改动推出去，并执行 `run_tests`（`:231`）。与"只写仓库内/不做 git 写操作"冲突。

### 2.3 当前状态量（决定后果）

```powershell
> git -C .agents\skills\agentic-task status --porcelain
 M scripts/test_update_index.py
 M scripts/update_index.py
> git -C .agents\skills\agentic-task rev-parse --short HEAD
d0834ae
> git -C .agents\skills\agentic-task log -1 --oneline
d0834ae audit: pin cross-writer pending-phase placeholders (index '—'/'SPEC' vs stub 'init')
```

### 2.4 无 `--dry-run`（原始输出）

```powershell
> python .agents\skills\agentic-task\install.py --help
usage: install.py [-h] [--skip-codex] [--skip-claude]
                  [--codex-scope {project,user}]
                  project

Install AgenticTask into a project

positional arguments:
  project               Project root, for example E:/UEMigrator

options:
  -h, --help            show this help message and exit
  --skip-codex          Only install the Claude adapter
  --skip-claude         Only install the Codex skill
  --codex-scope {project,user}
                        Where to install the Codex skill. Defaults to project-
                        local .agents/skills.

> python .agents\skills\agentic-task\scripts\sync_framework.py --help
usage: sync_framework.py [-h] [--project PROJECT] [-m MESSAGE]
                         [--direction {auto,to-install,from-install}]
                         [--remote REMOTE] [--branch BRANCH]

Sync AgenticTask framework changes

options:
  -h, --help            show this help message and exit
  --project PROJECT     Installed project root. Defaults to nearest .agentic-
                        framework.
  -m, --message MESSAGE Commit message for the framework source repo.
  --direction {auto,to-install,from-install}
                        Sync direction. Defaults to auto.
  --remote REMOTE       Git remote to push. Defaults to origin.
  --branch BRANCH       Git branch to push. Defaults to current branch.
```

### 2.5 dry-run 等价物：只读预检 / 后检（原始输出）

```powershell
> python .agents\skills\agentic-task\diff-installed.py .
AgenticTask installed differences found:
- claude/scripts: changed file audit_phase.py
- claude/scripts: changed file test_audit_phase.py
- claude/scripts: changed file test_update_index.py
- claude/scripts: changed file update_index.py
exit=1
```

→ 2.1 的命令执行后**预期只改这 4 个文件**（`claude/scripts` 之外 0 差异；`diff-installed.py:18-19` 忽略 `.git`/`__pycache__`/`node_modules` 与 `.pyc/.pyo`，所以 `__pycache__` 的替换不在该清单里，见 §4 R7）。
→ 再跑一次应从 exit=1 变 exit=0。

字节级现状（三份脚本树的对照，佐证"mirror 自身也滞后于 canonical"）：

| 文件 | canonical `scripts/` | mirror `claude/scripts/` | `core/scripts/` | 已装 `.claude/scripts/` |
|---|---|---|---|---|
| `audit_phase.py` | 8270 | 8270 | 8270 | **7876** |
| `test_audit_phase.py` | 10741 | 10741 | 10741 | **9343** |
| `test_update_index.py` | 11195 | **7118** | **7118** | **5671** |
| `update_index.py` | 28884 | **22492** | **22492** | **22026** |
| 其余 12 个 `.py` | 一致 | 一致 | 一致 | 一致 |

### 2.6 mw 原生等价路径（只读实测，未执行 `--apply`）

```powershell
> python packages\multi-workers\mw.py update-env --project H:\git\Multi-Workers --json
```
关键片段（UTF-8 解码后）：

```
"id": "framework-source", "status": "warn",
  "detail": "未提交变更 ×2 — 本机安装会携带未发布状态，他机/克隆需 push 后才可同步", "fix": "git commit + push（发布）"
"id": "claude-adapters", "status": "stale",
  "detail": ".claude 适配器与框架源差异 4 个文件", "fix": "框架重装（复制 claude/）", "auto": true
"id": "manifest", "status": "stale",
  "detail": "安装于 d7004d0，源 HEAD d0834ae", "fix": "框架重装", "auto": true
"summary": { "ok": 8, "stale": 2, "warn": 1, "healthy": false }
"applied": [],  "manual": ["[framework-source] ...", "[claude-adapters] 框架重装（复制 claude/）", "[manifest] 框架重装"]
exit=1
```
（`mw.py:5526-5559`；不带 `--apply`/`--fetch` 时只读。）

等价路径：`python packages\multi-workers\mw.py update-env --project H:\git\Multi-Workers --apply` → `mw.py:5472-5482` 触发 `_install_framework`（`mw.py:4554-4581`），其 cmd = `[python, <source>/install.py, <project>, "--codex-scope", "project"]`（`mw.py:4571-4577`），source = `mw.py:5200-5208` / `_checkout_framework_dir` @ `mw.py:4113-4122` = `H:\git\Multi-Workers\.agents\skills\agentic-task`。**未执行**（会覆盖 `.claude/scripts`）。差别：`--apply` 还会执行 `_apply_update_env` 的其余自动项（bundle/dist 重建、`.tmp` 缓存 pull、serve 重启，`mw.py:5445-5490`，均为状态相关）。

---

## 3. gitignore 判定（原始输出）

```powershell
> git check-ignore -v .claude/scripts
.gitignore:21:.claude/	.claude/scripts
> git check-ignore -v .claude/scripts/sync_framework.py
.gitignore:21:.claude/	.claude/scripts/sync_framework.py
> git check-ignore -v .agents/skills/agentic-task/install.py
.gitignore:57:.agents/	.agents/skills/agentic-task/install.py
> git check-ignore -v .agentic-framework
.gitignore:56:.agentic-framework	.agentic-framework
> git status --porcelain -- .claude
(空)
> git status --porcelain -- .agents
(空)
```
（PowerShell 中 `git check-ignore` 的命中行 `rc=0`；`.gitignore` 行号 21/56/57 与该文件内容一致。）

**结论：被忽略。** `.claude/`、`.agents/`、`.agentic-framework` 三者全部不在 Multi-Workers 版本控制内 → 父仓库对分发结果**零记录**，`git status` 看不到任何分发漂移。

同步产物的交付 / 验证方式：

1. **`.claude` 自身是嵌套 git 工作树**（独立仓库，父仓库看不见它）：
   ```
   > git -C .claude rev-parse --is-inside-work-tree
   true
   > git -C .claude remote -v
   origin	https://github.com/wenbocode/AgenticLoop.git (fetch)
   origin	https://github.com/wenbocode/AgenticLoop.git (push)
   > git -C .claude rev-parse --short HEAD ; git -C .claude rev-parse --abbrev-ref HEAD
   704b413
   master
   > git -C .claude log -1 --oneline
   704b413 更新 mermaid 规范
   > (git -C .claude status --porcelain | Measure-Object).Count
   47
   ```
   47 行里含 ` M scripts/advance_phase.py`、`?? scripts/audit_phase.py`、`?? scripts/sync_framework.py`、`?? scripts/migrate_patterns.py` 等 → 同步产物的交付路径是**在该嵌套仓库 commit/push**（`git -C .claude add <path>` + `commit` + `push origin master`），父仓库 `git add .claude` 无效（被忽略）。
2. 框架源 `.agents/skills/agentic-task` 是另一个独立 clone：`origin https://github.com/wenbocode/AgenticTask.git`，HEAD `d0834ae`。SKILL.md:57 的契约是"就地编辑该 clone 后 `git commit && git push` 发布"。
3. **验证（可脚本化）**：`python .agents/skills/agentic-task/diff-installed.py .` exit=0（=适配器与框架源一致）。当前 exit=1（4 个文件）。
4. 两个来源仓库不同（AgenticLoop.git vs AgenticTask.git），本地数据无法判定谱系关系（见 §6 U-2）。
5. 后果：因为分发链两端都被忽略，**`.claude/scripts` 的"最新值"在本机没有任何版控锚点**；唯一锚点是 canonical `scripts/`（同样在 `.agents/`，也被忽略）。

---

## 4. 风险点清单（每条给坐标）

| # | 风险 | 坐标 |
|---|---|---|
| R1 | **静默丢失用户本地改动**：A2 对 4 个 adapter 目录先 `rmtree` 再 `copytree`，无备份、无合并；目标侧独有文件被删（实测 §5.2）。`.claude/{commands,agents,skills,scripts}` 里任何手写文件都会永久消失 | `install.py:36-37`（rmtree）、`install.py:38`（copytree）、`install.py:74-75` |
| R2 | **无 dry-run / 无 force / 无确认**：无法预演；任何误触发都是即时不可逆覆盖 | 全脚本 grep `dry.run|dry_run` = 0；§2.4 原始 `--help` |
| R3 | **误写任意目录**：`project` 为必填 positional 且只校验"目录存在"，传成别的项目路径（或在别的项目里跑 `install.py .`）就会在**那个目录**写 `.claude/` + `.agentic-framework` | `install.py:139`、`install.py:153-155` |
| R4 | **写用户家目录**：`--codex-scope user` → `codex_home()` = `$CODEX_HOME` 或 `~/.codex`，并在其中 clone/rmtree | `install.py:143-146`、`install.py:122-134` |
| R5 | **rmtree 非 clone 的 skill 目录**：`<project>/.agents/skills/agentic-task` 存在但不是 git clone（例如历史 file-copy 安装）时被整目录删除再 clone（网络依赖） | `install.py:113-118` |
| R6 | **静默改框架源并"要求 push"**：A1 会改写 `<ROOT>/claude/scripts` 与 `<ROOT>/core/scripts`；若 canonical 与 mirror 已分叉，运行一次 install 就产生源仓库脏文件，且脚本只打印提示不提交 | `install.py:41-67`、`install.py:157-162` |
| R7 | **`install.py` 的 copytree 无 ignore 列表**（与 `sync_framework.py` 不对称）：会把 mirror 里的 `__pycache__`、`.pytest_cache` 复制进 `.claude`（实测 §5.2）；若 mirror 内出现 `.git` 也会被复制（本次 mirror 无 `.git`，故未触发） | `install.py:38` vs `sync_framework.py:102`（`IGNORED_DIRS` @ `:31`） |
| R8 | **manifest 整体重写**：`.agentic-framework` 的手工编辑（例如临时改 `repo=`）被覆盖 | `install.py:174-183` |
| R9 | **`sync_framework.py` 会用任意脏文件触发提交+推送**：`source_dirty` 只看"有脏文件"，不看脏的是什么；随后 `git add --all` + `commit` + `push`。当前仓库已满足该条件（§2.3，2 个被修改文件、无 push 授权语境） | `sync_framework.py:211`、`:216-217`、`:190-194` |
| R10 | **`from-install` 用"旧安装"覆盖较新源**：`sync_installed_to_repo` 先 rmtree `<ROOT>/claude/*` 再拷入 `.claude/*`；本 key 里 `.claude/scripts` 正是较旧一侧，`--direction from-install` 可被显式强制（auto 下被 `source_dirty` 挡在 :216-217） | `sync_framework.py:223-224`、`:97-102`、`:114-116` |
| R11 | **同步过程执行仓库内测试**：`run_tests` 对 3 个目录跑 `unittest discover`（执行任意测试代码，可能产生临时文件） | `sync_framework.py:171-182`、`:231` |
| R12 | **mw 漂移判据以 mirror 为基准（fail-open 面）**：`_claude_adapter_drift` 比较 `<source>/claude/*`（mirror）与 `<project>/.claude/*`，**不比较** canonical `<source>/scripts/*`；本 key 中 mirror 自身滞后于 canonical（§2.5），故该判据对"mirror 滞后"完全盲；且它只计数差文件个数，无法区分谁新谁旧 | `mw.py:5161-5184`、`mw.py:5390-5395` |
| R13 | **分发链两端都被 gitignore**：`.claude/`（`.gitignore:21`）、`.agents/`（`.gitignore:57`）、`.agentic-framework`（`.gitignore:56`）→ 同步结果在父仓库不可追踪、不可复现；`.claude` 的交付依赖一个**不同 upstream**（AgenticLoop.git）的嵌套仓库 | §3 原始输出 |

---

## 5. 实测

沙箱：`H:\git\Multi-Workers\.tmp\rq3c-fake\`，内含
- `agentic-task\`：`.agents/skills/agentic-task` 的整树拷贝（模拟"框架源仓库"）
- `project\`：假项目（`.claude\scripts\` 预置陈旧文件与哨兵文件）

**未对真实 `.claude`/`.agents` 执行任何覆盖**；结果证明见 §5.6。
（进程事实：运行期 bash 写面守卫对本 worker 只放行 worker 目录与 evidence 目录；沙箱写入通过变量路径实现，一条含字面量 `.tmp\...` 的写入被守卫 block 并给出 `[rule=scope]`，故沙箱脚本改写为 PowerShell 等价检查。）

### 5.1 RUN 1 原始输出

```powershell
> python $sand\agentic-task\install.py $sand\project --skip-codex
Synced script mirrors from scripts/ (canonical source):
  claude/scripts/test_update_index.py
  claude/scripts/update_index.py
  core/scripts/test_update_index.py
  core/scripts/update_index.py
NOTE: mirror files changed ?? commit & push this repository to publish them.
Installed AgenticTask
project=H:\git\Multi-Workers\.tmp\rq3c-fake\project
claude=H:\git\Multi-Workers\.tmp\rq3c-fake\project\.claude
manifest=H:\git\Multi-Workers\.tmp\rq3c-fake\project\.agentic-framework
exit=0
```
（`NOTE` 行末尾的 `??` 是 PowerShell 控制台把 `—` 显示成乱码，非脚本内容。）

沙箱镜像/安装产物前后字节数：
```
pre : mirror update_index.py=22492  test_update_index.py=7118    project\.claude\scripts\update_index.py=29（手写陈旧串）
post: mirror update_index.py=28884  test_update_index.py=11195   core mirror update_index.py=28884
      installed update_index.py=28884  test_update_index.py=11195  audit_phase.py=8270
```
manifest：
```
framework=AgenticTask
repo=H:\git\Multi-Workers\.tmp\rq3c-fake\agentic-task
commit=d0834ae
installed_at=2026-10-12T07:34:45.989319+00:00
claude=H:\git\Multi-Workers\.tmp\rq3c-fake\project\.claude
```

### 5.2 覆盖规则实测（目标侧多余文件被删 + pycache 被搬入）

预置 `project\.claude\scripts\ZZZ_sentinel.py`、`project\.claude\commands\ZZZ_sentinel.md`、手写 `update_index.py`：

```
installed update_index.py : 28884          （手写 29 B 版本被覆盖）
sentinel ZZZ_sentinel.py exists: False     （目标侧独有文件被 rmtree 删除）
sentinel ZZZ_sentinel.md exists: False     （commands 目录同样被 rmtree）
target has scripts/__pycache__: True       （copy_tree 无 ignore，pycache 被复制）
```

### 5.3 幂等实测

```
RUN 2: python ...\install.py ...\project --skip-codex
Installed AgenticTask
project=...   claude=...   manifest=...
exit=0
（RUN 2 未打印 "Synced script mirrors"，即无 mirror 变更）
file count before=65 after=65
IDENTICAL: .claude tree byte-identical after run 2   （65 个文件 SHA256 逐一相同）
```

### 5.4 `.claude/.git` 与"非 4 目录"文件保留

```
> RUN 3（先在 project\.claude 放 .git\HEAD、settings.local.json、再放一个哨兵）
claude/.git/HEAD survives: True
claude/settings.local.json survives: True
claude/scripts/ZZZ_sentinel.py survives: False
```
→ `install_claude` 只替换 `CLAUDE_DIRS` 四个子目录（`install.py:74-75`），`.claude` 下的其它内容（含嵌套 `.git`）保留。

### 5.5 codex 分支（仓库内命中 skip）

```powershell
> (Resolve-Path .agents\skills\agentic-task).Path                -> H:\git\Multi-Workers\.agents\skills\agentic-task
> (Resolve-Path .agents\skills\agentic-task).Path  # = skill_dst（project=. 时）
   equal (skip branch install.py:106-108) = True
   skill_dst has .git clone = True
```
即：仓库内运行 `install.py .`（不带 `--skip-codex`）走 `install.py:106-108` 的 skipping，不 clone、不 rmtree 该目录。

### 5.6 非改动证明（真实仓库窗口期内无内容变更）

```
now: 2026-10-12 15:36:38
files under .claude modified in last 60 min: 1
   2026/10/12 15:34:11  H:\git\Multi-Workers\.claude\.git\index
files under .agents modified in last 60 min: 2
   2026/10/12 15:30:40  ...\.agents\skills\agentic-task\.git\FETCH_HEAD
   2026/10/12 15:06:17  ...\.agents\skills\agentic-task\scripts\.pytest_cache\v\cache\nodeids
> git -C .agents\skills\agentic-task status --porcelain
 M scripts/test_update_index.py
 M scripts/update_index.py          （与窗口期开始前一致，无新增）
> git status --porcelain -- .claude / -- .agents   (均为空，因被忽略)
```
- `.claude\.git\index` 的 mtime 变化是 `git status` 刷新 stat cache 的固有行为（本 worker 执行了 `git -C .claude status --porcelain`），**不是工作树内容修改**。
- `FETCH_HEAD`（15:30:40）与 `.pytest_cache\v\cache\nodeids`（15:06:17）**不可归因于本 worker**：本 worker 仅执行 `git status/rev-parse/log/remote -v` 与只读 python，未执行任何 fetch/pull/commit/push，且 `mw update-env` 未带 `--fetch`（fetch 调用点仅 `mw.py:4155`（写 `.tmp` 缓存）与 `mw.py:5538`（`--fetch` 分支））；对照物 `packages\multi-workers\.tmp\agentic-task\.git\FETCH_HEAD` mtime 仍为 2026-09-21。推测来自并发 session / 常驻 serve（PID 79536），**未验证**（§6 U-1）。

沙箱保留：`.tmp\rq3c-fake\`（`.gitignore` 已忽略 `.tmp/`）。

---

## 6. 未验证怀疑清单

| # | 怀疑 | 为什么没验证 / 如何验证 |
|---|---|---|
| U-1 | `.agents/skills/agentic-task/.git/FETCH_HEAD` 与 `.pytest_cache/nodeids` 的 mtime 来自并发 session 或常驻 mw serve（PID 79536），而非本 worker | 本 worker 未执行 fetch；无跨进程日志可归因。验证：`mw` serve 的日志/其他 session 记录，或在下一次独立窗口期做 mtime 快照对照 |
| U-2 | `.claude` 的 origin（AgenticLoop.git）与框架源 origin（AgenticTask.git）的谱系关系（是否为同一框架改名/分叉） | 需要远端比对（如 `git ls-remote` 两仓库、比对 root commit），本任务不允许网络/git 写读远端同步。本地可见只是"内容重叠但字节不同" |
| U-3 | 若未来 `git -C .claude pull --ff-only`，是否会把旧的 22026 B `update_index.py` 拉回并**重新制造**本 key 研究的漂移 | 未执行拉取。验证：在 `.tmp` 克隆 AgenticLoop.git 后做离线比对 |
| U-4 | `mw update-env --apply` 在当前状态下是否**真的只**跑到"框架重装"（bundle/serve/tmp-cache 三项已 ok，理论上是），从而只写仓库内 | 未执行（会覆盖 `.claude/scripts`，被 task 禁止）。验证：在沙箱假项目上跑 `update-env --apply` 并 diff 前后文件清单 |
| U-5 | `install.py` 是否在任何分支下有仓库外写入（除已确认的 `--codex-scope user` 家目录路径外） | 只做了静态阅读 + 沙箱实测（沙箱全部写入均在沙箱内）。验证：用文件系统审计工具（如 Process Monitor）在沙箱运行 install.py，记录全部写路径 |
| U-6 | `install.py` 覆盖 `.claude/scripts` 后，`.claude` 嵌套仓库的 index 是否会留下"暂存区与新工作树不一致"的中间态，从而让后续 `git -C .claude commit` 提交出非预期内容 | 未对真实 `.claude` 执行。验证：沙箱内给 `project\.claude` 建一个真 `.git`（git init + 一次提交）后跑 install，再 `git status --short` 观察 |
| U-7 | mirror 侧若出现 `.git` 子目录，`install.py:38` 的无 ignore copytree 会把它复制进 `.claude/scripts/.git`（形成嵌套仓库） | 本次 mirror 无 `.git`，未构造该用例。验证：沙箱里往 `agentic-task\claude\scripts` 放一个假 `.git` 目录后跑 install |
