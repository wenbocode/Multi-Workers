# T-W02 — G2：`mw worktree rm|add|list` 六步事务 + 注册表模块（AC-004..008）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**任何破坏性 git/文件命令与真树 npm 操作（见「写入禁止面」）

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 「文件驱动的去中心化协调 + Worker 进程隔离」要求共享树在任何清理路径下都不可被穿透删除。本任务是 spec 的 **G2：唯一正规命令**，也是 AC-002 里 G1 会照抄的那条命令。
- **事故面（已实测，勿重做）**: `git worktree remove --force` 会穿透 `node_modules` 下的 junction（双层链可穿两层），2026-10-09 删掉 **3,456** 个已跟踪文件（`mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` v3 §2）。而 `cmd /c rmdir <link>`（无 `/S`）**不穿透**（`…/in1-junction-incident-20261009.md` 对照实验）—— 这就是 G2 的摘链原语。
- **设计契约（必须逐字实现）**: `design.md` §4.2 六步、§4.3 CLI 契约、§4.4 三分类（决策 D-1）、§6 决策 D-6（`_npm_hydrate` 抽取）。
- **可复用资产（先读再写，禁止重新发明；行号会漂移 ⇒ 用 grep 找符号）**:
  - 快照/动作/复核/退出码范式：`packages/multi-workers/mw.py:1057`（`_toolchain_run`，"前置快照 → 动作 → 后置快照 → drift 判定 → 打印对照 → `0 if ok else 1`"）；
  - git 调用：`mw.py:4222`（`_git`）、`mw.py:4489`（`_repo_root`）、`mw.py:4930`（`_run_stream(cmd, *, cwd)`）；
  - 依赖引导现有实现（D-6 的抽取源）：`mw.py:4724`（`_install_framework`）内的 `mw.py:5104`（`step(2, "npm ci/install --ignore-scripts")`）与 `mw.py:5105`（`install_cmd = [npm, "install" if node_modules.is_dir() else "ci", "--ignore-scripts"]`）；
  - 并发锁：`packages/multi-workers/mw_common.py:2039`（`acquire_lock`）/ `mw_common.py:2054`（`release_lock`，`O_CREAT|O_EXCL`）；
  - 原子写：`mw_common.py:2063`（`_write_workers_file`，校验 → tmp → 读回验证）；
  - 路径面惯例：`mw.py` 中排除 dist 的路径并集对照（`_git_dirty` / `_claude_adapter_drift` 附近）—— 步 4 的复核面沿用同一惯例；
  - 子命令注册：`mw.py:6259`（`_parse_args`）的 `sub.add_parser(...)` 组（`mw worktree` 是新增的**二级**子命令）。
- 相关 spec 验收：AC-004（六步不可跳）、AC-005（只摘链、主树零损伤）、AC-006（三分类）、AC-007（中止保留现场）、AC-008（`add` 默认不建链 + `--link-deps` 登记）。

## 要求

1. **CLI 契约逐字照 `design.md` §4.3**：
   `mw worktree add <path> [--project DIR] [--ref REF] [--link-deps] [--dry-run] [--json]`、`mw worktree rm <path> [--project DIR] [--json]`、`mw worktree list [--project DIR] [--json]`。参数定义加在既有 parser helper 内（**禁止**在 `mw.py` 里写一次性 ad-hoc 解析）。
2. **`rm` 六步固定顺序**（枚举 → 校验三分类 → 只摘链 → 复核主树 `node_modules/@earendil-works/*` 链接目标逐条未变 → `git worktree remove --force` → 打印前后对照）：
   - 任一步失败：`ABORT at step N/6` + 明确输出"未降级继续"，返回码非 0，**保留现场**；**禁止** `try/finally` 补偿写、禁止"把剩下的链摘完"；
   - **不接受**任何跳步开关（无 `--force`/`--continue`；`rm` 的 `--force` 语义只存在于内部对 git 的调用）；
   - 步 2 与步 3 之间**零写入**：`links` 是步 1 冻结的列表；
   - 手工介入提示照抄可用：输出 `cmd /c rmdir "<link>"`（禁 `/S`）。
3. **三分类判定（D-1）实现为纯函数**（便于单测）：① 目标在 `repo_root` 内 ⇒ 摘链 → 复核 → remove；② 目标在**待删 worktree 子树内**（自指链）⇒ 摘链；③ 其它 ⇒ fail-closed 拒绝、不摘任何链。纯函数签名与返回结构须写进报告的 `## 证据`（供 W-05/W-06 对齐）。
4. **注册表模块** `worktree_registry.py`（本任务的写面内）：落点 `.mw/worktree-registry.json`，条目含 `target` / `created_at` / `created_by`；提供 `register_link(...)` 与只读遍历接口；写走 `acquire_lock` + tmp + `os.replace` + 读回验证。
5. **`add`**：默认**不建链**；`--link-deps` 才建 junction 并登记注册表；`--dry-run` 打印将做之事而不落盘；非 `--dry-run` 的依赖引导走 `_npm_hydrate(target_root)`（从 `install_cmd` 抽取的公共函数，`npm ci --ignore-scripts`）。**`install_cmd` 既有行为必须逐字节不变**（用现有测试或等价断言证明）。
6. **`list`**：注册表 + `git worktree list --porcelain` 合并视图，只读。
7. **摘链原语**：`cmd /c rmdir <link>`（无 `/S`、无尾分隔符）；非 Windows 平台明确报错退出（不静默降级）；摘链前把 `Path/LinkType/Target` 落到普通对象（PowerShell `Target` 惰性解析坑，见 `spec.md` §6 坑点 10）。
8. **测试** `test_worktree_cmd.py`（`pytest`）：步序断言（含步 2 失败 ⇒ 零摘链）、三分类三例、`--json` 字段断言、注册表往返、`_npm_hydrate` 抽取后 `install_cmd` 无回归。**测试不得真的执行 `npm ci`**（用 `--dry-run` 或等价注入；真树禁 `npm install`/`npm ci`）。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W02-worktree-cli-20261013.md`：`## 结论`、`## 证据`（六步与步序实测输出、三分类判定函数、`--json` 样例、pytest 实际输出）、`## 改动历史`（before→after `file:line`）、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | 夹具位置: %TEMP%\<...>`。

## 写入允许面

- `packages/multi-workers/mw.py`（子命令注册 + `_npm_hydrate` 抽取 + 参数）
- `packages/multi-workers/worktree_cmd.py`（新建：六步事务与 CLI 逻辑）
- `packages/multi-workers/worktree_registry.py`（新建）
- `packages/multi-workers/test_worktree_cmd.py`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W02-worktree-cli-20261013.md`（新建）

## 写入禁止面

- `packages/multi-workers/mw_common.py`（T-W03 写）、`launcher.py`（T-W04 写）、`scripts/diff-model-catalog.mjs`（T-W07 写）、任何 `packages/coding-agent/**` 文件（T-W01/W-05 写域）。
- 禁止破坏性命令：`git checkout|reset|clean|stash|worktree remove`、`rm`、`npm install`/`npm ci`（**在真树上一律禁止**；夹具内也只允许 `--dry-run`/等价注入）。
- 禁止触碰真树 `H:\git\Multi-Workers\node_modules` 下的 junction；禁止 `git worktree remove` 任何真仓 worktree。
- 禁止内联 import；Python 侧不引入新第三方依赖。

## 验收命令

```
cd packages/multi-workers
python -m pytest test_worktree_cmd.py -q
python mw.py worktree --help
python mw.py worktree list --json
```

（最后两条只在**只读**语义下跑；不得对真仓执行 `add`/`rm`。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
