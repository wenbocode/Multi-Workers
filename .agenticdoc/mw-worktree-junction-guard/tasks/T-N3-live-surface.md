# T-N3 — 必要性调研 RQ-N3：事故面与工作流现状（今天还会不会自发出现）

- type: research
- key: mw-worktree-junction-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq3-live-surface-20261013.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash 与 `%TEMP%` 夹具；**禁止**在真树建/删 junction、worktree 或跑 `npm install`/`npm ci`、禁止 `checkout`/`reset`/`clean`/`stash`。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`。
- 要回答的总问题：**事故的"产生条件"今天是否仍然自发存在**——即：这类 reparse point 会不会持续被创建、还有谁会去删 worktree、以及是否已经出现过第二次。若是，G1..G4 仍然必要；若事故面已自然消失（例如已无人用 worktree、链已全部清除），则要重新评估目标。
- 已坐实事实（可引用，但必须自己复看确认）：
  - 本仓 `node_modules` 顶层有 14 条 reparse point（9 条 `@earendil-works/*` + 5 条 `pi-extension-*`），全部 `Junction`、目标全部存在且指向 `packages/**`（`…/evidence/research/design-observability-and-verification-20261013.md` §F4）。PM 已独立复核其中 9+5 条。
  - 事故前夜的活雷仍在：`%TEMP%\mwvg-t5\node_modules` 是 `Junction`，目标 `H:\git\Multi-Workers\node_modules`（存在且可解析）——PM 已独立复核。
  - 同类事故出现过多次（"已知三次"的计数与口径见 `…/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md` §4.4 与其 in2-recurrence 证据）。
  - 链是 npm workspace reify 的产物：`package.json:9-14` 的 workspaces + 事故时间线里 `npm install --ignore-scripts` 重建了 8 条链。
- 允许并鼓励自行扩大取证范围（全仓只读；`.mw/` 日志、其它 key 的 evidence、`%TEMP%`、`%LOCALAPPDATA%`、其它可能的工作树位置）。

## 要求

1. **事故面全量盘点（今天）**：给出机器可复算的清单与计数——
   - 仓库内：`node_modules` 全部 reparse point（含深度遍历剪枝、不跟进链接），逐条 `link -> target` 与目标存在性；
   - 仓库外：至少扫描 `%TEMP%` 与一个“常见 worktree 落点”（若存在），报出**指向本仓**的链接（活雷形态），给命令 + 原始输出 + 计数 + 耗时；
   - 是否有遗留 worktree 注册（`git worktree list --porcelain`、`.git/worktrees/`）与未登记的孤儿目录。
2. **产生条件是否仍在**：回答"再跑一次 `npm install`/`npm ci` 是否必然重建这些链"——用**只读证据**（`package.json` workspaces、lockfile、既有 `.mw/` 日志里的 npm 调用记录、`node_modules/@earendil-works/*` 的链接形态）推论，注明哪些是**实测**、哪些是**推断**；不允许真树跑 `npm install`。
3. **使用面是否还在**：是否仍有流程/人会删 worktree——grep 全仓（含 `.agenticdoc/**`、`.mw/**`、`packages/**` 脚本与测试）里的 `git worktree remove|add|prune`；检查 `.mw/launcher.log`/`conductor.log`/最近 evidence 里 worktree 使用痕迹；给出计数与最近一次的时间戳（若有）。
4. **是否已复发/是否有新变体**：`.agenticdoc/**` 里 2026-10-09 之后的记录中，是否还有"文件消失/junction 穿透/未提交改动丢失"的第二次、第三次事件（给文件:行号与原文片段），并说明其与首次事故的关系。
5. 只读真树；唯一允许写入的是本卡声明的证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-necessity-rq3-live-surface-20261013.md`（结论先行 + 逐条判据含命令与原始输出 + 计数 + 上下文来源 + 残留与未验证 + 未覆盖面声明）
- 最后必须有一句明确判定："事故面**仍然存在** / **已自然消失**"，并指出如果今天什么都不做，最坏会发生什么。
