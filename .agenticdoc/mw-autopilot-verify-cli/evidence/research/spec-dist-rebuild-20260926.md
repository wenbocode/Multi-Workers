# RQ-3 调研：dist 重建机制、安装位与风险面

- key: `mw-autopilot-verify-cli`（对应 spec §1.1.6 / U-3 / U-4 / AC-009）
- 日期：2026-09-26
- 快照：`HEAD = d52694cc4`（调研过程中 HEAD 被并发会话推进，见 §0）
- 方式：**只读调研**——未运行任何构建、未改任何项目文件；本文件是唯一写面。
- 引用约定：`mw.py` = `packages/multi-workers/mw.py`，`mw_common.py` = `packages/multi-workers/mw_common.py`；行号以本快照为准。

---

## 0. 前提复核（重要：任务前提在其父提交上成立，但调研期间已被并发会话修复）

任务称 tracked 产物 `packages/multi-workers/dist/extensions/agent-team-loop.js` 落后于源码（缺 `xkey-authorize` kind 与 `xkey-gate-guard`）。实测：

- 在前置提交 `181a75332`（xkey-repair-mechanism，本 key 的 dep）上：
  - `git grep -c "xkey-gate-guard" 181a75332 -- packages/multi-workers/dist/extensions/agent-team-loop.js` → **无匹配**
  - `git grep -c "xkey-authorize" 181a75332 -- packages/multi-workers/dist/extensions/agent-team-loop.js` → **无匹配**
  - 而源码已由 `181a75332` 引入：`status-model.ts:511`（kind）与 `shared/xkey-gate-guard.ts`（新文件）。
  - ⇒ 前提成立：产物确实落后于源。
- 调研过程中，**另一个会话提交了 `d52694cc4`**（2026-09-26 14:09:53，`fix(multi-workers,coding-agent): rebuild agent-team-loop dist artifacts for the xkey kind/guard`）：
  - 12 个文件：`packages/multi-workers/dist/extensions/agent-team-loop.js` 与 `packages/coding-agent/dist/extensions/agent-team-loop/{autopilot/status-model.*, index.*, shared/xkey-gate-guard.*}`
  - 新增 4 个 tracked 文件：`.../shared/xkey-gate-guard.{d.ts,d.ts.map,js,js.map}`
- 当前快照状态（实测）：
  - repo bundle：sha256 `1be95bbae4d4c2195f91a8bc49a536b244c5974b52c7cd73363ec3eda46133d1`，923479 bytes
  - 全局副本 `~/.pi/agent/extensions/agent-team-loop.js`：**同 sha（byte-identical）**
  - `mw_common._doctor_bundle()` → `{"stale": false}`（global mtime 14:09:40 ≥ source newest 12:22:24）
  - `git status --porcelain -- packages/*/dist` → 干净（无未提交/未跟踪）

**结论**：AC-009 的"产物含 `xkey-authorize`/guard"与"tracked 产物提交"两条**已客观满足**，但满足它的是 `d52694cc4`（不属于本 key 的提交集合）。PM 需二选一：(a) 直接引用 `d52694cc4` 作为本 key AC-009 的证据并结项；(b) 按 §7 做一次"防复发"改动（推荐，因为根因未消除——见 §3/§7）。

---

## 1. `mw build` / `mw build --install` / `--no-dist` 的确切行为链

### 1.1 CLI 定义

- `build_p`：`mw.py:4791-4797`
  - `--install`（`action="store_true"`，4793）
  - `--no-dist`（`dest="no_dist"`，4795）——仅在 `--install` 下有意义
- `/mw build`（pi 窗口命令）等价 `mw build --install`：`pm/ui-bridge.ts:2112-2118` → `shared/mw-runner.ts:60-73`（`spawnSync(PYTHON_EXE, [mwPy, "build", "--install"])`，mw-runner.ts:64）

### 1.2 构建的输入 / 输出

- `_build_bundle()`：`mw.py:3516-3547`
  - 源：`_EXT_SRC_REL` = `packages/coding-agent/src/extensions/agent-team-loop/index.ts`（`mw.py:3473-3475`，由 `_repo_root()` 拼绝对路径）
  - 出：`_bundle_path()` = `_SCRIPT_DIR / "dist/extensions/agent-team-loop.js"`（`mw.py:3458-3462`），即 **`packages/multi-workers/dist/extensions/agent-team-loop.js`**（单文件 esbuild bundle，ESM / node18 / `external: ['node:*']`，脚本 `mw.py:3481-3508`）
  - 需要 `node`（`shutil.which("node")`，`mw.py:3534-3536`），不需要 bash，cwd-independent

### 1.3 `cmd_build`（`mw.py:3635-3647`）分支

| 调用 | 动作 |
|---|---|
| `mw build` | 只 `_build_bundle()` → 写 repo bundle；**不碰 dist、不碰全局** |
| `mw build --install` | 先 build，再 `_deploy_bundle(no_dist=False)`（3643） |
| `mw build --install --no-dist` | 先 build，再 `_deploy_bundle(no_dist=True)`（跳过 dist 重建） |

### 1.4 `_deploy_bundle(no_dist)`（`mw.py:3609-3632`）的安装位

按执行顺序：

1. `shutil.copy2(_bundle_path(), _global_ext_dir()/"agent-team-loop.js")`（3614-3616）
   - 全局扩展目录：若 agent 主目录 env 覆盖已设置则用其 `extensions`，否则 `~/.pi/agent/extensions`（`mw_common.global_ext_dir()`，`mw_common.py:1637-1641`；`mw.py:3776-3779` 只是转发）
2. 写 `.mw-py-path` sidecar（3617 → `_write_mw_py_path`，`mw.py:3584-3586`；`_mw_py_path_file`，3576-3581）
3. 安装 `/update-agentictask` 扩展 `agentictask-update.ts`（3618-3619 → `_agentictask_update_install`，`mw.py:3590-3605`）
4. **仅当 `--install` 且未给 `--no-dist`**：`_rebuild_pi_dist()`（3622-3631 → `mw.py:3550-3573`，在 `packages/coding-agent` 跑 `npm run build`）

**不装的位**：`<project>/.pi/extensions/agent-team-loop.js`。该位只由 `mw init` 处理，且**全局存在时反而删除项目本地副本**（GLOBAL WINS，`mw.py:3737-3753`）——因为重复注册会被 pi 以 "tool conflicts" 拒载。

### 1.5 `_rebuild_pi_dist` 是否无条件跑

**否。** `_rebuild_pi_dist()` 只在这两处被触达：

- `cmd_build` → `_deploy_bundle` → 需要 `--install` 且非 `--no-dist`（`mw.py:3622-3627`）
- `_apply_update_env` S1 → `_deploy_bundle(no_dist=False)`（`mw.py:4524`），且仅当 bundle/pi-dist 判为 stale

`mw setup --build` 只 `_build_bundle()` + 全局装 bundle，**不重建 coding-agent dist**（`mw.py:3786-3813`）。`mw bootstrap` 走的是另一条链路：repo 根 `npm run build`（`mw.py:4050-4052`），它会重编全部 workspace 包（含 coding-agent），**不写 `packages/multi-workers/dist` 的 esbuild bundle**（该 bundle 只由 `_build_bundle` 产生）。

---

## 2. tracked vs 生成物边界（`git ls-files` 实测）

```
$ git ls-files packages/multi-workers/dist
packages/multi-workers/dist/extensions/agent-team-loop.js          # 恰好 1 个文件

$ git ls-files packages/coding-agent/dist | Measure-Object -Line
953                                                                # dist 内 953 个文件全部 tracked
```

- 各包 tracked dist 数量：`agent 160 / ai 736 / tui 148 / protocol 32 / client 40 / server 68 / coding-agent 953 / multi-workers 1`。**整棵 `packages/*/dist` 都是受版本控制的产物**。
- `.gitignore` 不覆盖它们：`git check-ignore -v <path>` 退出码 1（无匹配）。根 `.gitignore:2` 的 `/dist/` 是**仓库根锚定**，只管 `<repo>/dist/`，不管 `packages/*/dist/`；`packages/coding-agent/.gitignore` 只有 `*.bun-build`；`*.tsbuildinfo` 全局忽略（`.gitignore:6`），而 `tsconfig.build.json` 无 `incremental/composite`，实测也无 `.tsbuildinfo` 生成。
- 本 key 重建后需提交的路径：
  1. `packages/multi-workers/dist/extensions/agent-team-loop.js`（esbuild bundle；单文件）
  2. `packages/coding-agent/dist/extensions/agent-team-loop/**`（至少 `autopilot/status-model.{js,d.ts,js.map,d.ts.map}`、`index.{js,js.map,d.ts.map}`、`shared/xkey-gate-guard.*`）
  3. 若 TS 改动波及 dist 其它模块，则 `packages/coding-agent/dist/**` 的对应 diff（`npm run build` 全量 emit，diff 面可能远大于 2 个目录）
- `d52694cc4` 已提交的路径集正是上面 1 + 2（12 文件）。

---

## 3. UPDATE.md 锚点机制、`mw update-env --apply`、`mw doctor` 判据

### 3.1 文档与实现的对应

`packages/multi-workers/UPDATE.md` 是**文档**（§1 版本锚点 A1-A9，§2 指令矩阵，§3/§4 已工具化）。实现：

- `_check_update_env(project_dir)`：`mw.py:4316-4507`
  - **A1 bundle**：`mw.py:4330-4344`，判据来自 `mw_common._doctor_bundle()`
  - **A2 pi-dist**：`mw.py:4346-4360`，`_newest_file_mtime(packages/coding-agent/dist)` vs `_newest_file_mtime(packages/coding-agent/src)`，slack 2.0s；stale → `auto=True`，fix = "mw build --install（含 dist 重建）"
  - A3 serve：4371+；A4 framework-source；A5 tmp-cache；A6 skill-clone；A7 claude-adapters；A8 manifest
- `_apply_update_env(project_dir, report)`：`mw.py:4509-4560`
  - **S1**（4522-4530）：`if stale("bundle") or stale("pi-dist"): _deploy_bundle(no_dist=False)`
  - S2 tmp-cache pull；S3 framework reinstall；S4 serve restart
- `cmd_update_env`：`mw.py:4597-4633`（`--apply` 后再 `_check_update_env` 复查；退出码 0=healthy / 1=需动作）

### 3.2 `mw update-env --apply` 具体做什么、是否覆盖"重建 dist"

- 覆盖 **`packages/coding-agent/dist`**：是。`stale("pi-dist")` → `_deploy_bundle(no_dist=False)` → `_rebuild_pi_dist()` 真跑 `npm run build`（`mw.py:4524 → 3627 → 3550`）。
- 覆盖 **`packages/multi-workers/dist/extensions/agent-team-loop.js`**：**否**。
  `_apply_update_env` 从不调用 `_build_bundle()`（全仓 `_build_bundle(` 调用点只有 `mw.py:3636`（cmd_build）与 `mw.py:3788`（cmd_setup --build））。
  `_deploy_bundle` 的 docstring 自称 "Install the **freshly built** bundle globally"（`mw.py:3609-3612`），但它只 `shutil.copy2(_bundle_path(), ext_dst)`（3615）——**它假定调用方已经重建过 bundle，而 `_apply_update_env` 没有**。
- **fail-open 路径（实测可推演）**：若 repo bundle 已陈旧而全局副本比源码旧，`stale("bundle")=True` → `_deploy_bundle` 把**陈旧的 repo bundle** 复制到全局（mtime 变新）→ `cmd_update_env` 复查 `_doctor_bundle()` → `stale=False` → 报告 healthy，但扩展内容**仍是旧的**。即"update-env 把 bundle 判据刷新了，却没重建内容"。
- `mw doctor --fix` 也不修 bundle：`doctor_fix` 只修 stale queue 与 stale PID，bundle 是 report-only（`mw_common.py:1655-1671` docstring 明示 "Report-only (suggestions): expired bundle"）。

### 3.3 `mw doctor` 的 bundle 判据

- `_doctor_bundle()`：`mw_common.py:1978-2001`
  - 对象：**全局** `global_ext_dir()/agent-team-loop.js`
  - 判据：`max(source file mtime under _EXT_SRC_DIR) > global_bundle_mtime` → `stale=True`；`_EXT_SRC_DIR = packages/coding-agent/src/extensions/agent-team-loop`（`mw_common.py:1648-1651`）
  - 纯 mtime，**无内容/版本判据**；源目录缺失时 `stale=None`（不可比）
- `doctor_report` 把它放进 `report["bundle"]`（`mw_common.py:2114`），而 `_doctor_issues` 只在 stale 时追加一条 **suggestion**，不是 issue（`mw_common.py:2044-2047`）。⇒ `summary.healthy` 与退出码**不受 bundle 陈旧影响**（`mw_common.py:2124`）；文本行见 2241-2252。

### 3.4 锚点覆盖缺口（本 key 的直接相关发现）

- **`packages/multi-workers/dist/extensions/agent-team-loop.js` 完全不在任何锚点内**：A1 只看全局副本 mtime，A2 只看 coding-agent/dist，A3-A8 无关。这正是本轮 drift 能静默产生的原因。
- A1 的 mtime 判据对"repo bundle 落后"无效——即使全局副本 mtime 比源新，repo tracked 产物仍可能陈旧（内容判据缺失）。
- 建议见 §7。

---

## 4. 机器判据：怎样"证明"产物真的含新 kind/guard

### 4.1 既有自检代码在哪

- **构建期加载自检**（唯一的既有自检）：`_BUILD_NODE_SCRIPT`，`mw.py:3481-3508`（esbuild build 后 `createJiti(...).import(OUT, {default:true})`，断言 `typeof f === 'function'`，`mw.py:3499-3507`）。
  它只验证**可加载性**，**不验证任何 kind/guard 内容**（也不验证 sha）。
- 同一契约的运行时侧：`packages/coding-agent/src/core/extensions/loader.ts:431-433`（`typeof factory !== "function"` → 拒载）。
- `build-extension.sh` 里的等价自检只是同一逻辑的 bash 版（`packages/multi-workers/build-extension.sh:43-56`），`mw build` 的 Python 路径不调用它。

### 4.2 可直接复制的命令与预期输出形状

**C1 标记存在性（最弱，但最便宜）** — PowerShell：

```powershell
$b = 'packages/multi-workers/dist/extensions/agent-team-loop.js'
foreach ($m in '\"xkey-authorize\"', 'xkey-gate-guard:', '\[XKEY_GATE\]') {
  if (-not (Select-String -Path $b -Pattern $m -Quiet)) { Write-Error "MISSING $m" }
}
```
预期：无输出（全部命中）。当前实测：`"xkey-authorize"` ×1、`xkey-gate-guard:` ×3、`[XKEY_GATE]` ×1。
弱点：字符串可能来自注释/日志模板（本 bundle 头部就有 `// packages/.../xkey-gate-guard.ts` 路径注释），**存在 ≠ 行为生效**。

**C2 kind 集合等价（中）** — 从源码提取 `GATE_KINDS` 字面量集合，与产物内 `var GATE_KINDS = [...]` 的集合比较：

- 源：`status-model.ts:505-512` → `{stage-confirm, stage-close, stalled, budget-exhausted, goal-change, xkey-authorize}`
- repo bundle：`agent-team-loop.js:21191-21198` → 同集合（当前实测一致）
- coding-agent dist：`dist/.../autopilot/status-model.js:425-432` → 同集合
预期：三处集合逐字相等。这比 C1 强（落在真实数据结构上），但仍只覆盖 kind。

**C3 guard 模块真被编译进来（中）** — 断言产物含 guard 的**行为标志字符串**（而非路径注释）：
`xkey-gate-guard: blocked`（`shared/xkey-gate-guard.ts:187`、`:229`）与 `[XKEY_GATE]` trace 前缀（`:208`）；并断言 repo bundle 含 guard 函数体而非仅注释。当前实测：`xkey-gate-guard:` 3 处，其中 2 处是 reason 前缀。

**C4 部署面一致性（中）** — 全局副本与 repo bundle byte-identical：

```powershell
python -c "import hashlib,pathlib,os;h=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest();print(h('packages/multi-workers/dist/extensions/agent-team-loop.js')==h(pathlib.Path(os.path.expanduser('~')).joinpath('.pi/agent','extensions','agent-team-loop.js')))"
```
预期：`True`。当前实测：`True`（同 sha `1be95bba…`，923479 bytes）。

**C5 重建幂等 / 与源码同步（最强，推荐作为 AC 的主判据）** — 在**干净工作树**上：

```powershell
python packages/multi-workers/mw.py build --install   # 重建 repo bundle + 全局装 + npm run build(coding-agent dist)
git diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist
```
预期：退出码 0、无 diff。含义：tracked 产物 == 从当前源码可复现构建出的产物（esbuild 输出确定性由 `d52694cc4` 的"两次连续构建同 sha"佐证），且全局副本已一致（C4）。
注意：该判据**会写 tracked 文件**，只能在干净工作树上跑；多会话下必须先确认无他人未提交 src 改动（见 §5）。

---

## 5. 多会话并行风险

### 5.1 `npm run build` 在 `packages/coding-agent` 会写哪些目录

`packages/coding-agent/package.json:37`：
`tsgo -p tsconfig.build.json && shx chmod +x dist/cli.js dist/rpc-entry.js && npm run copy-assets`

- 写 `packages/coding-agent/dist/**`（`tsconfig.build.json:4` `outDir=./dist`，`:17` `include src/**/*.ts`，`:15` `rootDir=./src`）→ **953 个 tracked 文件**，非 gitignored
- `copy-assets`（package.json:39）额外把 `src/modes/interactive/theme/*.json`、`assets/*.png`、`core/export-html/template.*` + `vendor/*.js` 拷进 dist（同样 tracked）
- **不 clean**：`build` 脚本无 `rm -rf dist`（只有独立的 `clean`，package.json:36）。被删除的源文件对应的旧 `.js/.d.ts` 会留在 dist → 孤儿产物
- 不编 sibling 包：`tsconfig.build.json` 通过 `paths` 指向 `../agent/dist/*.d.ts` 等（只作类型解析）。所以 `_rebuild_pi_dist` 只保证 coding-agent 自身 dist 新；若改的是 `packages/agent` 等 pi-core 其它包，需 root `npm run build`（`mw bootstrap` 走这条，`mw.py:4050-4052`）

### 5.2 其它窗口有未提交 TS 改动时会怎样

- **污染（静默）**：tsgo 从 `src/**` 全量 emit，他人未提交的 TS 会**被编进 tracked dist**。之后任何 `git add packages/coding-agent/dist`（含本 key 的提交）都会把这批半成品一并提交。不报错、不提示。
- **失败（连带）**：若他人未提交改动有类型错误，tsgo 非零退出 → `_rebuild_pi_dist` 返回 `(False, "npm run build failed: …")`（`mw.py:3572-3573`）→ `_deploy_bundle` 返回 1（3629-3630）→ `mw build --install` 整体失败。注意**顺序副作用**：全局 bundle 已在 `_deploy_bundle` 开头被替换（3614-3616），dist 才失败 → **部分部署**（全局已新、dist 仍旧）。
- **无护栏**：代码里**没有任何**"构建前检查工作树是否干净"或"构建锁"的逻辑（`mw.py` 无 `O_CREAT|O_EXCL`/`fcntl`/`msvcrt` 构建锁；`_build_bundle` 与 `_rebuild_pi_dist` 均无 mutex）。

### 5.3 `mw build` 写 tracked 产物时其它窗口正在跑

- **读半成品的窗口面很窄，但存在**：pi 扩展只在**进程启动时**加载（UPDATE.md §5.5/A9）。因此只有"在写盘期间正好启动"的窗口会读到半成品。
  - repo bundle：esbuild 直接写 outfile（`mw.py:3481-3508`），脚本里无 temp+rename → 非原子写
  - 全局副本：`shutil.copy2` 目标是**先截断再写** → 另一个窗口若此刻启动 pi，可能加载被截断的 bundle → loader 契约失败（`loader.ts:431-433`）或 jiti 解析失败，该窗口丢失扩展
  - `mw init` 在全局副本缺失的项目里也会 `shutil.copy2(_bundle_path(), …)`（`mw.py:3752`）→ 同样可能拷到半成品
- coding-agent dist：953 个文件被 tsgo 逐个覆盖；同窗口期启动的 pi 可能读到部分新/部分旧的 dist 模块。Node 从 dist 启动，混合版本可表现为难查的运行时错误。

### 5.4 风险面清单

| # | 风险 | 触发 | 现有护栏 |
|---|---|---|---|
| R1 | 他人未提交 TS 被编进 tracked dist 并可能被提交 | 任一窗口跑 `/mw build` 或 `mw bootstrap` | **无** |
| R2 | 非原子写单文件 bundle / 全局副本被截断 | 构建与 pi 启动并发 | **无**（仅构建期自检，读者侧无） |
| R3 | tsgo 并发写 953 个 tracked dist 文件 | 两窗口同时构建 | **无** |
| R4 | dist 重建失败时"全局已换、dist 未换"的部分部署 | `_deploy_bundle` 先 copy 后 rebuild（3615 → 3627） | 仅非零退出码（`mw.py:3629`；`test_mw_build.py:44-51`） |
| R5 | dist 孤儿残留（无 clean） | 删除源文件后重建 | **无** |
| R6 | `mw update-env --apply` 刷新 bundle 判据但不重建内容（fail-open） | repo bundle 陈旧（§3.2） | **无** |

---

## 6. 现有测试对 build 路径的覆盖

- `packages/multi-workers/test_mw_build.py`：**全部 mock**，不跑真实构建。
  - `_build_bundle` 被 monkeypatch 成 `(True,"built ok")`（:25）
  - `_rebuild_pi_dist` 被 monkeypatch，只记录"是否被调用"（:35、:41、:50、:56、:68）
  - 4 个用例覆盖：`--install` 触发 dist 重建（:40-47）、dist 失败 → 整体失败（:49-51）、`--no-dist` 跳过（:53-58）、`mw build`（无 `--install`）永不触 dist（:61-70）
  - ⇒ **不需要 node/npm**，也不验证产物内容
- `packages/multi-workers/test_mw_bootstrap.py:177`：断言假 runner 的调用串 `"npm run build @ repo"`，不执行真实构建
- `packages/multi-workers/test_update_env.py`：:180 mock `_doctor_bundle`；:304/:318 mock `_deploy_bundle` → 只验"stale 集合触发哪些动作"，不验内容
- **CI 不会跑这些**：`packages/multi-workers` **没有 package.json → 不是 npm workspace**（root `package.json` workspaces = `packages/*` 等，而 `npm test` 是 `--workspaces --if-present`），而 `.github/workflows/ci.yml` 只有 `npm ci` → `npm run build` → `npm run check` → `npm test`（:33-39），全仓 workflow 无 `pytest`/`python` 步骤（grep 无命中）。
  - ⇒ multi-workers 的 Python 测试只在开发机手动 `python -m pytest`（`pytest.ini`）跑；无 Windows skip 之说——它们**根本不进 CI**
- ⇒ **AC-009 的"机器判据"目前零自动化覆盖**：既无测试断言产物含 marker，也无测试跑真实构建。§4 的 C1-C5 全是手工流程。

---

## 7. AC-009 评估与更精确的判据建议

### 7.1 我的判断：方向对，但当前表述**不足以防复发**，且有两条偏弱/过度的措辞

原 AC-009：*"dist 重建：`mw build` 之后的产物含 `xkey-authorize` 与新 guard；机器判据（产物内字符串/加载自检 + sha 变化）可复现；tracked 产物随本 key 提交。"*

- **足够之处**：要求"机器判据可复现"、要求 tracked 产物提交——意图正确。
- **不足/偏弱**：
  1. "产物内字符串"：字符串存在 ≠ 行为生效（bundle 内有路径注释也会命中，§4.2 C1）。且不指定**产物集合**（只说 `mw build`，容易漏掉 `packages/coding-agent/dist/extensions/agent-team-loop/**`，那才是 pi 运行时真正加载的码）。
  2. "加载自检"：既有自检只验可加载性（`mw.py:3499-3507`），对 kind/guard 一无所知——用它当判据等于没判。
  3. "**sha 变化**"：这是弱判据且方向反了。构建产物 sha 变化只能证明"写了文件"，任何无关改动都会让它变化；真正要证的是"**产物 sha == 从当前源码重建的 sha**"（即与源码同步且可复现）。
  4. **未触及根因**：本轮 drift 之所以能发生，是因为 ①`packages/multi-workers/dist` 无任何锚点；②`mw update-env --apply` 的 S1 只 copy 不 rebuild（§3.2）。只"提交一次产物"会在下一次 TS 改动后原样复发。
- **可能过度之处**：若把判据实现成"每次 commit 都重跑 `mw build` 并比对 sha"，在多会话并发场景会与他人未提交 src 的编译产物互相污染（§5.2）；应限定"干净工作树 / CI 单会话"。

### 7.2 建议的替代判据（可直接并入 AC-009 或拆成 AC-009a/b）

- **AC-009a（产物集合与同步，强判据）**：在干净工作树上执行
  `python packages/multi-workers/mw.py build --install`（或 `/mw build`），随后
  `git diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist` **必须为空**（退出码 0）。
  — 这直接证明 tracked 产物 == 从当前源码可复现的构建结果，并用 C4 的 sha256 相等证明全局副本一致。替换掉"sha 变化"。
- **AC-009b（行为内容，中判据）**：三处产物的 `GATE_KINDS` 集合必须逐字等于源 `status-model.ts:505-512` 的集合，且 repo bundle 含 guard 的**行为标志**（`xkey-gate-guard: blocked` 与 `[XKEY_GATE]`，不是路径注释）。比单串 grep 强，且把 `packages/coding-agent/dist` 纳入。
- **AC-009c（防复发，真正闭合根因）**：给 `_check_update_env` 增加锚点 **A1b「repo tracked bundle vs 源码」**（内容判据优先：C2 的 kind 集合 + C3；mtime 判据会漏内容陈旧），并把 `_apply_update_env` 的 S1 改成**先 `_build_bundle()` 再 `_deploy_bundle()`**；否则 `mw update-env --apply` 的 bundle 修复是 fail-open 的（§3.2）。
  - 若不做 A1b，至少把 §4 的 C5 落成一个 CI/`mw doctor` 可跑检查，并把它写进 UPDATE.md §1（现在 §1 的 A1/A2 都不覆盖 repo bundle）。
- **AC-009d（护栏，可选但建议）**：`mw build --install` 在 `packages/coding-agent/src` 或 `packages/coding-agent/dist` 有未提交改动时**默认拒跑或强告警**（提示"多会话下会把他人未提交源码编进 tracked 产物"），并提供 `--allow-dirty` 显式绕过。对应 §5 的 R1/R3。这一条是多会话并行场景下最有价值的护栏，且成本低。

### 7.3 结论一句话

AC-009 必须从"产物里有某个字符串 + sha 变了"升级为"**干净树上重建后 tracked 产物零 diff（源码同步性）+ kind 集合等价 + 全局副本 byte-identical**"，并把"repo bundle 锚点 + update-env 真重建"作为防复发交付；否则本次修复只是一次性对齐（如 `d52694cc4` 所做），下一轮 TS 改动会再次静默漂移。