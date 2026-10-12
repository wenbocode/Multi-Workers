# spec — mw-worktree-junction-guard

## 0. Goal Alignment（goal.md）

**对齐**：`.agenticdoc/goal.md` 的并行承诺建立在「多 Worker 共享同一工作树而不互相破坏」之上。2026-10-09 的实证事故（`git worktree remove --force` 穿透 junction，删掉 8 个包 3,448 个已跟踪文件、丢弃他人未提交改动、约 5.5 分钟无人报警）直接证伪了这一前提，并让一个 key 的 QG 判定建立在损坏过的树上。

**预期收益**：
1. 危险路径**不可达**（执行前拦截），正确顺序**只由代码保证**，不依赖 agent 自觉；
2. 隔离验证（worktree）从"高危捷径"变成"有唯一正规入口的常规操作"；
3. 同类事故可被**机器发现**而非靠人撞见。

## 1. 事实基础（实证，非推算）

| 事实 | 出处 |
|---|---|
| `git worktree remove --force` **穿透** junction（双层链可穿两层） | `mw-workspace-incident-probe/evidence/in1-junction-incident-20261009.md`（含 `%TEMP%` 最小复现） |
| `cmd /c rmdir <link>`（无 `/S`）与 PS `Remove-Item -Recurse` **不穿透** | 同上（对照实验） |
| 事故命令原文/时刻/会话 | `…evidence/incidents-timeline-20261009.md` §1（jsonl L142/L144） |
| 受害面 3,448 文件 = 8 包整树 + `packages/tui/dist` | `…evidence/in2-file-vanish-incident-20261009.md`（AC-006） |
| 未提交改动被静默丢弃（写入证据齐全） | 同上（AC-007） |

## 2. 验收标准

**G1 · 确定性拦截**
- **AC-001** 对含 reparse point 的 worktree 执行 `git worktree remove`（含 `--force`）时，**执行前被 block**，命令未真正运行（以副作用为零证明）。
- **AC-002** block 的报错文本**包含可直接照抄的正规命令**（G2 形式），且含被检出的链接路径与目标。
- **AC-003** 对**不含** reparse point 的 worktree，`git worktree remove` **不被误拦**（零副作用放行），并有反向对照。

**G2 · 唯一正规命令 `mw worktree rm <path>`**
- **AC-004** 六步顺序固定且不可跳步：枚举 → 校验目标在仓库内 → 只摘链 → 复核主树 `node_modules/@earendil-works/*` 链接目标逐条未变 → `git worktree remove --force` → 打印前后对照。
- **AC-005** 含链 worktree：**只摘链、主树零损伤**（以主树 `node_modules` 与 8 个包的文件清单/哈希前后一致证明）。
- **AC-006** 链接目标**在仓库外**时**拒绝执行**（fail-closed），且拒绝时不摘任何链。
- **AC-007** 任一步失败 ⇒ **中止并保留现场**，明确输出"未降级继续"；不得部分摘链后继续 remove。

**G3 · 对称命令与巡检**
- **AC-008** `mw worktree add <path>` 默认**不创建 junction**；显式 `--link-deps` 时才建链，并**登记注册表**（含目标、创建时刻、创建者）。
- **AC-009** `mw doctor` 报出「遗留的、指向仓库内的 junction」并给出路径；对无遗留的仓库不误报（反向对照，语料锚点 = `%TEMP%\mwvg-t5-probe\node_modules` 曾存在的形态）。

**G4 · 可观测**
- **AC-010** 「已跟踪文件数骤降」判据：构造 file-count 骤降（临时仓库）⇒ 触发；正常波动（如单文件编辑）⇒ 不触发。
- **AC-011** 「junction 目标丢失」判据：构造断链 ⇒ 触发并给出路径；完好链 ⇒ 不触发。
- **AC-012** 端到端复现：在 `%TEMP%` 内建 worktree + 链 → 走新流程清理 → **主树 mtime 与内容零变化**（机器对照），且全程无 block 误放行。

## 3. 约束

- 不改 pi 核心；TS 侧走 Extension API，Python 侧走 `mw.py`。
- **写面按文件切分**：TS guard / `mw.py worktree` 子命令 / doctor 检查 / 测试，**同一文件同一时刻只允许一个 worker**。
- Guard 与 G2 必须**互为闭环**：被 block 的文本能直接照抄执行。
- 所有判据必须**机器可复算**；数值一律实测化（禁陈旧字面量），并附反向对照。

## 4. 交付物

G1..G4 实现 + 测试（含 4 组反向对照）+ 真机端到端复现记录 + `achieved.md`（含「## 遗留」与未坐实项）。
