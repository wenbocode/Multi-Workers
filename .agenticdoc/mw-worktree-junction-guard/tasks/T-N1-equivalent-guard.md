# T-N1 — 必要性调研 RQ-N1：等价实现盘点（G1 是否冗余）

- type: research
- key: mw-worktree-junction-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq1-equivalent-guard-20261013.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、建/删 junction 或 worktree、跑 `git worktree remove`、跑 `npm install`。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**新增 G1（执行前拦截 `git worktree remove`）是不是重复劳动**——当前仓库是否已有等价/部分覆盖的机制。
- 已坐实事实（可引用，但必须自己复看确认）：
  - 事故机理与最小复现：`.agenticdoc/mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`（`git worktree remove --force` 穿透 junction；`cmd /c rmdir` 无 `/S` 不穿透）。
  - 既有写面门禁的写动词集只有 `tee/cp/mv/rm/sed`：`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:79`（`WRITE_VERBS`），消费逻辑 `:539-637`；其自述缺口在 `:24-27`。
  - 三个 guard 的注册位置：`packages/coding-agent/src/extensions/agent-team-loop/index.ts:42`（protected-config）、`:49`（xkey gate）、`:59`（implementation gate）。
  - `packages/multi-workers/mw.py` 里 grep `worktree` = 0 命中（无 `mw worktree` 子命令）；TS 生产源码 grep `worktree` 仅 `shared/change-ledger.ts:127` 一处注释。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `dist/` 产物、其它 key 的 `.agenticdoc/`、`.git/hooks/`、`.mw/`）。

## 要求

1. **穷举当前所有"执行前"门禁**（TS 扩展、worker 模式 write-scope、mw 侧 write_scope/launcher 校验、pi core 的 tool 校验、key-claim 门禁、mini-spec 快速通道、bash 工具自身），逐条给出：`文件:行号` + 判定逻辑原文片段 + **对 `git worktree remove --force <path>` 是否命中**（命中 / 不命中 / 部分，并给依据）。注意：`mw-write-surface` 那类 path 白名单也算门禁。
2. **明确判定**：G1 与既有机制**是否冗余**？若部分重叠，分别列出"重叠面"与"空缺面"；若完全冗余，给出可复算的证明。
3. **双加载/产物漂移检查**：`packages/multi-workers/dist/extensions/agent-team-loop.js`（全局 bundle）与 `packages/coding-agent/dist/**` 里是否存在**未合并进 src** 的等价实现或更早的 junction/删除保护逻辑（grep `worktree`、`junction`、`reparse`、`rmdir`、`RemoveDirectory`）。
4. **hooks 面**：`.git/hooks/` 实际有哪些可执行 hook、是否拦截或改写命令；`.mw/` 内是否有任何 pre-flight 校验脚本被调用（给出调用点）。
5. 只读：不得修改任何文件；唯一允许写入的是本卡声明的证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq1-equivalent-guard-20261013.md`（结论先行 + 逐条判据 + 上下文来源 + 残留与未验证 + 未覆盖面声明）
- 每一条判据都要有 `文件:行号` + 原文片段 + 计数；未找到就写"未找到（命令 + 输出）"，**禁止推测补齐**。
