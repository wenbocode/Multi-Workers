# mini-spec — mw-worktree-junction-guard

## 背景（事故实证，2026-10-09）

`git worktree remove --force "$env:TEMP\qg-head"` 穿透了 worktree 内**指回主树的 junction**（双层链 `qg-head/node_modules → 真 node_modules → @earendil-works/pi-ai → packages/ai`），删掉 8 个包 3,448 个已跟踪文件 + 8 条 workspace 链接，在 `packages/tui` 撞锁中止（RC=255），约 5.5 分钟后才被恢复、期间丢弃他人未提交改动。取证见 `mw-workspace-incident-probe/evidence/{in1-junction-incident-20261009.md,in2-file-vanish-incident-20261009.md,incidents-timeline-20261009.md}`。

**实测语义（本方案的事实基础）**：`git worktree remove --force` **穿透** junction；`cmd /c rmdir <link>`（无 `/S`）与 PS `Remove-Item -Recurse` **不穿透**；同日 2 次"先摘链再删"零事故。

## 目标

把「正确的删除顺序」**固化为机械步骤**：让危险路径**不可达**（执行前拦截），并只留**一条**唯一正规命令。**不依赖 agent 自觉。**

## 交付（G1..G4）

- **G1 确定性拦截**：在 pi 工具层（与既有 `protected-config` guard 同层）拦截 bash 命令中的 `git worktree remove`（含 `Remove-Item -Recurse`/`rm -rf` 指向含 reparse point 的目录）：执行前扫描目标树下 reparse point（junction/symlink），**命中即 block**，报错文本给出 G2 命令。
- **G2 唯一正规命令 `mw worktree rm <path>`**：固定六步且不可跳步 —— ① 枚举 reparse point；② 逐个校验链接目标在仓库内（否则拒绝）；③ **只摘链**（`rmdir`，禁 `/S`）；④ 复核主树 `node_modules/@earendil-works/*` 链接目标逐条未变；⑤ 才 `git worktree remove --force`；⑥ 打印前后对照。任一步失败 ⇒ **中止，不降级继续**。
- **G3 对称命令 + 巡检**：`mw worktree add <path> [--npm-ci|--copy-deps]` 默认**不建链**；如需建链则登记注册表供 G2 识别。`mw doctor` 新增「遗留的、指向真树的 junction」检查（样本：`%TEMP%\mwvg-t5-probe\node_modules` 曾存在）。
- **G4 可观测**：doctor/看门狗新增「已跟踪文件数骤降」「junction 目标丢失」两条机器判据（本次 3,448 文件消失 5.5 分钟零报警）。

## 约束

- 不改 pi 核心，全部走 Extension API / mw 侧实现。
- **并行切面按文件**：TS guard / `mw.py` 子命令 / doctor 检查 / 测试，同一文件同一时刻只有一个 worker。
- Guard 与 `mw worktree rm` 必须互为闭环：被 block 的报错必须能直接照抄成 G2 命令。
- 测试必须含**反向对照**：危险命令确实被 block、被穿透场景确实被拒绝、摘链后主树链接逐条未变。

## 验收（起草，spec 期细化编号）

- 危险命令（含 junction 的 worktree + `git worktree remove`）**必定被拦**，报错含正规命令；
- `mw worktree rm` 对含链 worktree：**只摘链、主树零损伤**，且**人为造一条链时必拒绝**（目标在仓库外）；
- doctor 能报出遗留链；两条告警判据有语料化测试；
- 真机复现：`%TEMP%` 内建 worktree+链 → 走新流程 → 主树 mtime/内容零变化。

## 完成判据

G1..G4 全部实现且各有反向对照测试；在 `%TEMP%` 内端到端复现不再损伤主树；`mw-workspace-incident-probe` 的取证记录作为语料锚点被引用。
