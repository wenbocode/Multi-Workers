# T-W09 — 补 design §6.1 动作 (3)：骤降 + 同窗口链清单 delta 升级为 doctor issue（QG F-02）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— INV-4「同类事故可被机器发现」。G4 已能在 `mw serve` 的 poll 循环里采样并在 stderr 告警，但**告警只进 `.mw/launcher.log`**：一个不看日志、只跑 `mw doctor` 的人看不到它。
- **被补的设计条款（本 key 唯一未实现的设计动作）**: `design.md:295`（§6.1 AC-010 动作 (3)）原文——「同窗口 `link_inventory` 也有 delta ⇒ 升级为 issue（`mw_common.py:3401`），`mw doctor` rc=1」。
- **为什么漏**（独立 QG 发现，F-02）: 该升级横跨 W-04（采样，写面 `tree_watch.py`/`launcher.py`）与 W-03（doctor 段，写面 `mw_common.py`/`worktree_doctor.py`）两张卡，双方都未认领 ⇒ 掉进卡缝；`mw_common.py` 当前对 tree-watch 零引用（grep 无命中）。
- **现成原语（必须复用，不要重写）**:
  - `packages/multi-workers/tree_watch.py:53`（`STATE_FILE_NAME = "tree-watch.json"`）、`:107`（`collapse_threshold`）、`:256`（`evaluate`，已产出 `events[]`（`kind` = `collapse` / 断链 / `inventory migration`）与 `alarms[]`）、`read_state`/`write_state`。
  - 状态落点 = `<root>/.mw/tree-watch.json`，字段含 `ts` / `tracked` / `deleted_non_dist` / `deleted_paths` / `link_inventory` / `events` / `alarms`（以实测为准，先读代码）。
- **挂载纪律（W-03 已验证）**: 新 issue 必须在 `mw_common._doctor_issues`（实测 `mw_common.py:3750` 起的 `worktree_links` 块附近）内追加，才能影响 rc；`format_doctor_text` 如需打印只在非空时打印。
- 相关 spec 验收：AC-010（骤降判据）+ AC-004（可观测）。

## 要求

1. **`tree_watch.evaluate` 事件补字段**：`collapse` 事件里记录**同窗口的链清单 delta**（例如 `link_delta: {"removed": n, "changed": n, "added": n}` 或等价的布尔 + 计数），**复用**已有的 inventory-migration 比较结果，不要新增第二套清单比较；该字段必须落进状态文件（`write_state`）。
2. **`mw_common` 消费点**：在 `_doctor_issues` 里读 `<project>/.mw/tree-watch.json`（缺失/损坏/字段类型异常 ⇒ **静默跳过**，绝不 raise —— 与注册表读取同一个 fail-open-to-verdict 原则）：当存在**新鲜**的 `collapse` 事件**且**其同窗口链 delta 非零 ⇒ `issues.append(...)`（影响 rc；文本要含事件 `ts`、`deleted_non_dist`、`delta`、链 delta 计数）。
3. **新鲜度**：定义常量 `TREE_WATCH_ISSUE_WINDOW_SEC`（默认 3600，写进 `mw_common`，注释说明理由），只对窗口内的事件升级；过期事件**不**升级（但仍留在状态文件里可回溯，符合 design §6.1「事件落盘（自清后仍可回溯）」）。窗口值与其理由写进证据报告。
4. **测试（新文件 `packages/multi-workers/test_tree_watch_doctor.py`，夹具全 `%TEMP%`）**：
   - 新鲜 `collapse` + 同窗口链 delta ⇒ `_doctor_issues` 出 issue、rc 变化；
   - `collapse` **无**链 delta（只删文件不动链）⇒ **不**出 issue（design 的"且"条件）；
   - 过期 `collapse` + 链 delta ⇒ **不**出 issue（反向对照）；
   - 无状态文件 / 损坏 JSON / `events` 类型异常 ⇒ 不出 issue、不 raise；
   - 与既有 doctor 的其它 issue 项共存时不吞并其它项（顺序/条数断言）。
5. **`test_tree_watch.py` 追加 1 例**：`evaluate` 的 `collapse` 事件确实带上同窗口链 delta 字段（正反两向：链被摘 ⇒ 非零；链完好 ⇒ 零）。
6. 不回归：`pytest test_tree_watch.py test_worktree_doctor.py test_worktree_cmd.py test_worktree_e2e.py test_doctor_gates.py test_serve_doctor.py -q` 全绿。

## 交付格式

- 代码变更（见「写入允许面」）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W09-tree-watch-doctor-20261013.md`：`## 结论`、`## 证据`（四类升级/不升级用例的实测输出与 `_doctor_issues` 原文、窗口常量取值与理由、状态文件样例、夹具路径与清理、pytest 输出）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 报告末行 `TESTS: <通过数>/<总数> | 升级用例: <n> | 反向对照: <n> | WINDOW_SEC: <值>`。

## 写入允许面

- `packages/multi-workers/tree_watch.py`（仅 `evaluate` 事件字段 + 必要常量）
- `packages/multi-workers/mw_common.py`（**仅** `_doctor_issues` 的 tree-watch 消费点；不动既有 `worktree_links` 块与其它段）
- `packages/multi-workers/test_tree_watch.py`（追加 1 例）
- `packages/multi-workers/test_tree_watch_doctor.py`（新建）
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W09-tree-watch-doctor-20261013.md`（新建）

## 写入禁止面

- `packages/multi-workers/{mw.py,worktree_cmd.py,worktree_registry.py,worktree_doctor.py,launcher.py}`、`test_worktree_*.py`、`test_doctor_gates.py`、`test_serve_doctor.py`、`test_launcher.py`（全部冻结）。
- `packages/coding-agent/**`、`scripts/**`、任何 `.ts`/`.mjs`。
- 真树：禁止 `git worktree add|remove|prune`、禁 `rm`、禁碰真树 `node_modules` 下的 junction、禁 `npm install`/`npm ci`。

## 验收命令

```
cd packages/multi-workers
python -m pytest test_tree_watch_doctor.py -q
python -m pytest test_tree_watch.py test_worktree_doctor.py test_worktree_cmd.py test_worktree_e2e.py test_doctor_gates.py test_serve_doctor.py -q
python -c "import mw_common; print('cycle-ok')"
python mw.py doctor --project H:/git/Multi-Workers
```

（最后一条对本仓**只读**：本仓 `.mw/tree-watch.json` 若不存在或事件过期，必须零新增 `tree_watch` issue 行、rc 与改动前一致。）

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
