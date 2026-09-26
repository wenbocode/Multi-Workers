# T-08 update-env / build 防复发（A1b/A2b 锚点 + 真重建 + 脏树护栏）

- AC: AC-009 · VC: VC-009, VC-010, VC-012 · 波次: 3（与 T-05 同文件 ⇒ 必须在其之后）
- 写面：`packages/multi-workers/mw.py`（**仅 build/update-env 段**：`_check_update_env`/`_apply_update_env`/`_deploy_bundle`/`cmd_build`/`cmd_bootstrap` 相关）+ `test_update_env.py`、`test_mw_build.py`

## 契约（design D-009/D-010）

1. **A1b 锚点**「repo-bundle vs 源码」：插在 `mw.py:4344` 与 `4346` 之间，`layer="machine"`、`auto=True`；判据 = `mw_common.repo_bundle_anchor()`（kind 集合等价 + guard 限定串）。
2. **A2b 锚点**：`mw_common.sourcemap_drift()`（`packages/coding-agent/dist/**/*.map` 的 `sourcesContent` 内容判据）。
3. **修 fail-open**：`_apply_update_env` 的 S1 改为**先 `_build_bundle()`，成功后才 `_deploy_bundle()`**；build 失败 ⇒ **不 deploy**（当前只 copy ⇒ 刷新 mtime 后复查报 healthy）。
4. **消除部分部署**：`_deploy_bundle` 内部顺序改为**先 `_rebuild_pi_dist()` 再 copy 全局副本**。
5. **脏树护栏**：`mw build --install` 在 `packages/coding-agent/src` 有未提交改动（`git status --porcelain --untracked-files=all -- <paths>`，含 staged/untracked）时**默认拒跑**并提示；`--allow-dirty` 绕过并声明"产物可能含未提交源码"；`mw bootstrap` 扩到 `packages/*/src`；**非 git 目录跳过**。

## 验证

- `python -m pytest -q test_update_env.py test_mw_build.py` 全绿。
- mock 断言调用顺序（build 先于 deploy；build 失败 ⇒ deploy 未被调用）；陈旧产物 fixture ⇒ A1b 为 stale，新鲜 ⇒ healthy（含"仅注释路径"反例）；脏树 ⇒ 返回非 0 且未安装；`--allow-dirty` 通过；非 git 跳过。
- 真实判据（干净树、可选慢测）：`python packages/multi-workers/mw.py build --install` 后 `git -c core.fileMode=false diff --exit-code -- packages/multi-workers/dist packages/coding-agent/dist` 为空。
- `[VERIFY]` 行：A1b/A2b 判据、S1 顺序、脏树护栏。
