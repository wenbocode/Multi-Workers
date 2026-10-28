# T-W16 — AC-015 裂缝修复（悬空链）+ AC-016 多标记（D-17/D-18）

- type: coding
- key: mw-worktree-junction-guard
- 角色约束: 允许 read/find/grep/ls/bash + 写；**禁止**破坏性 git/文件命令；禁 `npm install|ci`；夹具只能在 `%TEMP%` 内

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` INV-4（同类事故可被机器发现）。AC-015/AC-016 都是「护栏自己要被看见」，第三审计发现这两条各有一处看不见的角落（`spec.md` §7 D-17/D-18 已据此定稿）。
- **来源**: `evidence/delta-adversarial-audit-20261013.md`（对抗性审计，43 条攻击向量）§2 与 §3 C4②。PM 已自核修复基础：`packages/multi-workers/worktree_registry.py:86` = `if not path.exists(): return []`；`"user_bash"` 在扩展源 **2** 处、两份 bundle 各 **2** 处（`packages/multi-workers/dist/extensions/agent-team-loop.js`、`~/.pi/agent/extensions/agent-team-loop.js`），`reparse-point` 在 bundle 各 **1** 处。
- **既有实现坐标（先读确认）**: `worktree_registry.read_registry`（`worktree_registry.py:83-97`）；`mw_common` 的 `ACTIVATION_MARKER`（约 `:2740`）、`_activation_bundle_paths`（约 `:2745`）、`_activation_scan`（约 `:2780`）、`_doctor_activation`（约 `:2830`）、`_doctor_issues` 的 activation 消费（约 `:3895-3908`）、`format_doctor_text` 的 `activation:` 行与 `REGISTRY-ERROR` 行（约 `:4176-4198`）。

## 要求

1. **D-17 悬空链接可见**：`read_registry` 的存在性门改用 `os.path.lexists(path)`（**只改这一处门**，不改其余语义；缺文件仍返回 `[]`）。验收形态：`.mw/worktree-registry.json` 是指向**不存在目标**的 junction/符号链接 ⇒ `lexists` 真 → `read_text` 抛 → `WorktreeRegistryError` ⇒ doctor 出 issue + `worktree_links: REGISTRY-ERROR <path>: …` 行 + rc=1。
   - Windows 上**不需要管理员**即可造该形态：`cmd /c mklink /J "<夹具>/.mw/worktree-registry.json" "<夹具>/nonexistent-target"`（junction 不校验目标存在性）。测试须自证该形态成立：断言 `os.path.lexists(p) is True` **且** `p.exists() is False`（否则 skip 而非假绿）。
   - 反向对照：文件不存在 ⇒ 零新增行、rc 不变；正常注册表 ⇒ 同上。
2. **D-18 AC-016 多标记**：把单标记升级为标记集合 `("reparse-point", "user_bash")`：
   - 逐标记独立判定，`has_marker` = 全部存在；任一缺失 ⇒ `guard-not-deployed` issue，且 issue 与 `activation:` 行**必须指明缺失的标记名**（例如 `MARKER-ABSENT 'user_bash' <path> - run 'mw build --install'`）；
   - 不可读/缺文件/编码异常照旧 fail-open-to-verdict（`None` ≠ 已激活，文本写 `UNVERIFIABLE`）；读取失败不得 raise；
   - 保持「适用域」判据与既有 scope gate 不变（拥有 `packages/coding-agent/src/extensions/agent-team-loop` 的项目才检查）。
3. **文案修正（W-15 §3 C9 次要项）**：issue/行文本要区分两份副本的角色——`packages/multi-workers/dist/extensions/agent-team-loop.js` 是**构建产物/暂存**（pi 不直接加载它），`~/.pi/agent/extensions/agent-team-loop.js` 才是 pi 实际加载位；两者的缺失含义不同（前者=未 `mw build`，后者=未 `--install`）。
4. **测试**（夹具全 `%TEMP%`，清理干净）：
   - `test_worktree_doctor.py`：追加悬空链用例（含 `lexists`/`exists` 自证 + expect issue/行/rc）+ 缺文件与健康注册表两条反向对照；
   - `test_doctor_activation.py`：追加「仅缺 `user_bash`」「仅缺 `reparse-point`」「两个都缺」「两个都在（反向对照，rc 不变）」四类，并断言 issue 文本含缺失标记名；保留既有 10 项不回归。
5. **真实仓只读复跑**：`python mw.py doctor --project H:/git/Multi-Workers` —— 当前两份 bundle 已含两个标记（PM 实测 `"user_bash"`=2、`reparse-point`=1）⇒ 期望 **0 条 activation 命中**；注册表不存在 ⇒ 无 `REGISTRY-ERROR` 行；rc 仍为 1（既有 serve `STALE CODE`）。把实测输出如实记录；**不要**执行部署、不要为了让 rc 变绿而放宽判据。
6. **不回归**：`python -m pytest test_doctor_activation.py test_worktree_doctor.py test_worktree_cmd.py test_worktree_e2e.py test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py test_serve_doctor.py -q` 全绿（当前基线 **172** + 本卡新增）。

## 交付格式

- 代码变更（见写面）+ 证据报告 `.agenticdoc/mw-worktree-junction-guard/evidence/T-W16-ac015-crack-ac016-markers-20261013.md`：`## 结论`、`## 证据`（悬空链形态自证输出、四类标记用例输出、真实仓 doctor 前后对照与 rc、pytest 输出、夹具路径与清理）、`## 改动历史`、`## 残留与未验证`、`## 上下文来源`。
- 末行 `TESTS: <通过数>/<总数> | 悬空链: <可见|静默> | 标记: reparse-point+user_bash | 真实仓 activation 命中: <n> | CHECK: n/a(python)`。

## 写入允许面

- `packages/multi-workers/worktree_registry.py`（仅 `read_registry` 的存在性门）
- `packages/multi-workers/mw_common.py`（仅 activation 段与 doctor 文本/issue 面）
- `packages/multi-workers/test_worktree_doctor.py`、`packages/multi-workers/test_doctor_activation.py`
- `.agenticdoc/mw-worktree-junction-guard/evidence/T-W16-ac015-crack-ac016-markers-20261013.md`（新建）

## 写入禁止面

- 其它 Python 文件（`mw.py`/`worktree_cmd.py`/`worktree_doctor.py` 除非确实需要——后者只在 `registry_error` 折叠位需要时允许，且须在证据说明）、`test_worktree_cmd.py`/`test_worktree_e2e.py`/`test_tree_watch*.py`/`test_serve_doctor.py`/`test_doctor_gates.py`
- `packages/coding-agent/**`（同轮 W-17 在改 guard）、`scripts/**`、任何 `.ts`/`.mjs`
- **禁部署**：不跑 `mw build`/`mw start|stop`；真树禁 `git worktree add|remove|prune`、禁 `rm`、禁碰真树 `node_modules` 链

## 验收命令

```
cd packages/multi-workers
python -m pytest test_doctor_activation.py test_worktree_doctor.py -q
python -m pytest test_doctor_activation.py test_worktree_doctor.py test_worktree_cmd.py test_worktree_e2e.py test_tree_watch.py test_tree_watch_doctor.py test_doctor_gates.py test_serve_doctor.py -q
python -c "import mw_common; print('cycle-ok')"
python mw.py doctor --project H:/git/Multi-Workers
```

## 改动历史

报告内逐条列 `file:line` before→after + `git status --porcelain` 的本人改动清单。
