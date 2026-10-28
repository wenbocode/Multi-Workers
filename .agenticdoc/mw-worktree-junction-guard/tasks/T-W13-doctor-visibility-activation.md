# T-W13 — doctor 可见性两项：注册表损坏可见（AC-015/N-04）+ 激活自检（AC-016/N-01c）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令；禁 `npm install`/`npm ci`；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— INV-4「同类事故可被机器发现」。护栏与巡检如果**自己不被看见**，等于没有。
- **来源**: 独立负空间审计 `.agenticdoc/mw-worktree-junction-guard/evidence/negative-space-audit-20261013.md` 的 N-04 与 N-01（PM 已复验：两份 bundle `worktree` 命中 0、`.mw/tree-watch.json` 不存在、`launcher.log` 零 `[TREE-WATCH]`）。spec 已据此新增 **AC-015 / AC-016**（见 `spec.md` §2 G6 与 §7 D-14/D-15）。
- **现有结构（实测坐标，先读代码确认）**:
  - 注册表读取与错误折叠：`packages/multi-workers/worktree_doctor.py:138`（`_registry_domain`）把 `WorktreeRegistryError` 折进 `scanned["registry_error"]`（约 `:152-166`），`build_section`（约 `:290`）把它带出。
  - issue 装配：`packages/multi-workers/mw_common.py:3535`（`def _doctor_issues(report)`）；既有 `worktree_links` 消费块 `mw_common.py:3760-3768`；W-09 新增的 tree-watch 消费点在 `mw_common.py:3818` 附近（**不要动它**）。
  - 文本面：`packages/multi-workers/mw_common.py:4025-4033`（`format_doctor_text` 的 `worktree_links` 段，**只在 `count` 非零时打印**）。
  - serve 代码新鲜度判据已存在：`mw doctor` 输出里的 `serve code: STALE CODE ...`（PM 实跑可见）；本卡**复用**它，不得另造进程探针。
  - 部署产物路径（激活自检对象）：`packages/multi-workers/dist/extensions/agent-team-loop.js`（tracked）与 `~/.pi/agent/extensions/agent-team-loop.js`（全局）；两者当前均 **1,115,336 B 且 `worktree` 命中 0**。
- **能力标记选择**：G1 源码里的稳定字面量（esbuild 后仍存在），建议用 `reparse-point`（basis 值）或 `mw worktree rm`（处方文本）。先用 grep 在**当前 bundle** 上验证"修复前必然缺失、部署后必然出现"，再定标记；把选择理由与双向实测写进证据。

## 要求

1. **AC-015 注册表损坏可见**：当 `report["worktree_links"].registry_error` 非空时 ① `_doctor_issues` 追加 issue（含错误摘要 + 注册表路径，影响 rc）；② `format_doctor_text` 打印明确行（即使 `count==0`）。**反向对照**：注册表健康（或不存在）⇒ 零新增行、rc 与改动前一致。
2. **AC-016 激活自检**：在 doctor 装配面新增一项检查，报出「G1 能力未部署到运行面」：
   - 对两份 bundle 各自判定"是否含能力标记"；**文件缺失**也要报（不是静默跳过），修复提示给可照抄的 `mw build --install`；
   - ② serve 层面**复用**既有 stale 判据，不重复输出（若既有判据已覆盖，只在报告里说明复用关系）；
   - 保持 fail-open-to-verdict：读失败/编码异常 ⇒ 不 raise，视为"无法确认"并如实写进 issue 文本（不要伪装成"已激活"）；
   - **反向对照**：构造两份含标记的假 bundle 夹具 ⇒ 零新增行、rc 不变。
   - 该检查**必须能在部署后自动转绿**（标记出现即静默）——这是它的验收方式，写进证据。
3. **测试**（夹具全 `%TEMP%`；不得动真树 `node_modules` 的 junction）：
   - 在 `packages/multi-workers/test_worktree_doctor.py` 追加：损坏注册表 ⇒ issue + 文本行 + rc 变化；健康注册表 ⇒ 静默（反向对照）；
   - 新建 `packages/multi-workers/test_doctor_activation.py`：标记齐全 ⇒ 静默；标记缺失 ⇒ issue（含路径 + `mw build --install`）；bundle 文件缺失 ⇒ issue；读取异常 ⇒ 不 raise 且文本如实；两份都齐全时 rc 不变（反向对照）。
4. **真实仓只读运行**：`python mw.py doctor --project H:/git/Multi-Workers` —— 现在**预期会出现新的"能力未部署"issue**（这正是设计意图：当前 bundle 确实没有 G1），把它连同 rc 一起如实记入证据；**不要**为了让它变绿而放宽判据，也**不要**在本卡里执行部署（PM 会在本卡落地后执行 `mw build --install` 并复跑验证转绿）。
5. **不回归**：`python -m pytest test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py test_serve_doctor.py -q` 全绿（现有基线 138 + 本卡新增）。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W13-doctor-visibility-activation-20261013.md`：`## 结论`、`## 证据`（能力标记的选择与双向实测、五类用例的实测输出、真实仓 doctor 前后对照与 rc、pytest 输出、夹具路径与清理）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | 标记: <literal> | 真实仓: <新增 issue 数> rc=<n> | CHECK: clean`。

## 写入允许面

- `packages/multi-workers/mw_common.py`（**仅** doctor 装配/文本面：`_doctor_issues` 新增消费 + `format_doctor_text` 新增行；**不得动** `mw_common.py:3818` 附近的 tree-watch 块与既有 `worktree_links` 块语义）
- `packages/multi-workers/worktree_doctor.py`（仅当注册表错误需要更丰富暴露时；不动域判定与扫描逻辑）
- `packages/multi-workers/test_worktree_doctor.py`（追加用例）
- `packages/multi-workers/test_doctor_activation.py`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W13-doctor-visibility-activation-20261013.md`（新建）

## 写入禁止面

- `packages/multi-workers/{mw.py,worktree_cmd.py,worktree_registry.py,tree_watch.py,launcher.py}`、`test_worktree_cmd.py`、`test_worktree_e2e.py`、`test_tree_watch.py`、`test_tree_watch_doctor.py`、`test_serve_doctor.py`、`test_doctor_gates.py`（除下述允许追加者外一律冻结）。
- `packages/coding-agent/**`（含 `worktree-junction-guard.ts`——同轮另有 W-14 在改它）、`scripts/**`、任何 `.ts`/`.mjs`。
- **禁止执行部署**：不得跑 `mw build` / `mw build --install` / `mw start|stop`（PM 负责）。
- 真树：禁 `git worktree add|remove|prune`、禁 `rm`、禁碰真树 `node_modules` 下的 junction、禁 `npm install`/`npm ci`。

## 验收命令

```
cd packages/multi-workers
python -m pytest test_doctor_activation.py -q
python -m pytest test_worktree_cmd.py test_worktree_doctor.py test_worktree_e2e.py test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py test_serve_doctor.py -q
python -c "import mw_common; print('cycle-ok')"
python mw.py doctor --project H:/git/Multi-Workers
```

（最后一条对本仓**只读**：允许出现"能力未部署"新 issue；不得修改真树任何文件。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
