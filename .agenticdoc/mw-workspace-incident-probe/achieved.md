# achieved — mw-workspace-incident-probe

**性质**：只读取证 key，**零生产改动**（唯一写入为本 key 的 `evidence/**`）。

## 1. 结论

两起事故 **IN-1（workspace junction 消失）** 与 **IN-2（3,456 个已跟踪文件消失又恢复）** 判定为**同源：同一条命令**。

- 元凶：worker `mvr-t16-quality-gate-review`（key `mw-vision-role`）执行 `git worktree remove --force "$env:TEMP\qg-head"`（2026-10-09T12:32:18.452Z / 本地 20:32:18.452；jsonl L142 命令、L144 输出，RC=255）。
- 机制：`qg-head/node_modules` 为指回真树的 junction，真 `node_modules/@earendil-works/pi-ai` 又是指向 `packages/ai` 的 junction ⇒ git 递归删除**穿两层**，删链 + 删 8 个包整树（**3,300** 个 tracked 文件），在 `packages/tui` 子树内撞锁中止 ⇒ `packages/tui` 被删 **156/236**、**原物幸存 80/236**（v2 口径；3,300 + 156 = 3,456，与双源 `D` 计数吻合）。
- 上报口径修正：spec §1.1 的「9 个 junction 消失」与 v1 的「3,448 / 156-236 幸存」均已按 v2 更正（见下文 §4 质量门）。
- 动机（其自述）：为给 key 的 HEAD 状态出可信 QG 判定而隔离建 worktree，用 junction 省一次 `npm ci`。
- 实测语义：`git worktree remove --force` **穿透**；`cmd /c rmdir`（无 `/S`）与 PS `Remove-Item -Recurse` **不穿透**。

## 2. 交付物

`evidence/in1-junction-incident-20261009.md`、`evidence/in2-file-vanish-incident-20261009.md`、`evidence/incidents-timeline-20261009.md`（合并时间线 + 同源判定 + 未坐实清单 + 只建议不实施的 G1..G4）。

## 3. PM 自身纠错

①「9 条 junction 消失」更正为 **8 条消失 + `pi-tui` 保留**；②撤回基于 `npm-cache\_logs` 为空做的 npm 排除（该目录会被滚动清理，PM 自己的 install 也无日志）⇒ **可清理缓存不得用于证明"未发生"**；③事故族计数更正为**已知三次**同机制事件（2026-09-09 先例 → 2026-10-09 本次 → 2026-10-10 复发；先例原文见 timeline v3 §4.4）；④删除 v1 的「97 个未提交改动」（QG 未能找到一手出处，改用一手可见的 75 / 74 / 82）。

## 4. 质量门复核（独立 QG）与修复条件闭合

独立 QG worker `wip-qg-review`（type: review，只读；run `wip-qg-review@2026-10-12T08:05:56.813Z`，87 calls）对 6 份被审文档做**全量独立重核**，结论 **有条件 PASS**：取证核心（AC-001..AC-007）全部经一手证据链复核成立，13 项扣分（E1–E13）全部落在 **PM 合并层**（timeline / achieved.md 未吸收 IN-2 v2 修正稿）。报告全文 = `evidence/quality-gate-report-20261009.md`（28,795 B，QG 原件 `workers/wip-qg-review/report-quality-gate-report-20261009.md`，PM 已复制落位）。

6 条修复条件（C1–C6）闭合情况：

| 条件 | 内容 | 状态 |
|---|---|---|
| C1 | timeline §2/§5 与 achieved §1/§4 吸收 v2：3,456（8 包=3,300 + tui 156）；「156/236 被删后重建、80/236 原物幸存」；恢复机制=「只重写当前缺失路径」；3,550/1,040 删除或改标 v1 口径 | 已闭合（timeline v3 §2、本文件 §1） |
| C2 | 删除「AC-005 穷举为负 ⇒ pi 之外」残留 | 已闭合（timeline v3 §5 显式标注为错误并删除） |
| C3 | 遗留清单移除/标注已坐实三项：删除工具（`git worktree remove --force`）、恢复命令（`restore.sh`）、npm reify 触发者（PM 会话 `01a0d325`） | 已闭合（timeline v3 §5「已坐实」栏） |
| C4 | 修 IN-2 §2.4 引用时刻（12:32:37.458Z → 12:32:28.112Z）与 IN-1 Claim-Id 引证源（pm-state.md → `_index.parallel:46`） | 已闭合（见两份证据文件内 `[QG-E7]` / `[QG-E8]` 标注） |
| C5 | IN-2 §4.3 按 `01a11fac:323` 改写（保留 12:17–12:32 未坐实；撤回「没有任何一手记录/倾向反证」）；同步修 in2-recurrence §3 转述 | 已闭合（见两文件内 `[QG-E10]` / `[QG-E11]` 标注） |
| C6（建议） | timeline 补引 2026-09-09 先例，事故族计数改「已知三次」 | 已闭合（timeline v3 §4.4；本文件 §3 补第 ③ 条） |

**接受项（不影响 PASS，不需修复）**：
- QG §5 对证据层未坐实清单的抽查判定为**诚实**：IN-1 §7（7 项）与 IN-2 §6（10 项）无「把没查够伪装成查过为负」的隐瞒。QC 的 [未复测-无shell] 项（复现 A/B、mtime 直方图、junction 逐条 LinkType、`git fsck`、`npm config get logs-max`、IN-1 的窗口内 70 条 toolCall 计数）保持原样标注，不以推测补洞。
- E9（IN-1 记 pid「无法复核」而 IN-2 记 pid=159560）：**IN-2 正确**，IN-1 过度保守，非事实错误；已在 IN-1 §AC-002/§7 就地更正为坐实。
- E13（2026-09-09 先例为叙事漏项）：已补入 timeline v3 §4.4；该先例**强化**（而非削弱）机制判定。

## 系统行为变化

本 key **零生产改动**（只读取证）：**无**新增/修改功能，**无** API/行为/配置/产物影响面，不涉 dist 与 changelog。

影响面仅为**新增 4 份取证文档**（本 key `evidence/**`）：`in1-junction-incident-20261009.md`、`in2-file-vanish-incident-20261009.md`、`incidents-timeline-20261009.md`、`research/spec-incident-probe-plan-20261009.md`，以及本 `achieved.md` / `pm-state.md`。对后续任务的参考价值：G1..G4 的判据基础（junction 删除语义实测矩阵）与事故时间线，供 `mw-worktree-junction-guard` 直接引用。

## 5. 遗留

- **已坐实、不再列为未解（QG 条件 C3）**：删除工具/进程本体 = `git worktree remove --force`（元凶命令 e335:142）；恢复命令 = `restore.sh`（d2f3:204/206/207，3,456→0）；20:39 npm reify 触发者 = PM 会话 `01a0d325`（`npm install --ignore-scripts`，L2926）。v1 的「穷举为负 ⇒ 来自 pi 之外」为扫描范围不足的伪阴性，已删除（见 §4 C2）。
- **未坐实项（原样保留，不补洞）**：真树 `packages/tui` 内造成 EINVAL 的具体被占用文件/进程（中止发生在 `pi-tui` 子树内这一形态学结论已知，具体中止点/顺序未知）；`%TEMP%\mwvg-t5-probe\node_modules` 链的清理者（链已不存在，清理命令未找到）；触发 `mvr-t16` 重派的窗口（launcher 队列派发，无 `dispatch_worker` 记录）；`3531−3456=75` 的逐条构成；20:3x 是否存在 reflog 之外的 ref 级动作；`.tmp/t13-worktree` 检索为负（实际不存在）。
- **活雷（未处理，已登记）**：2026-10-10 11:20 实测仍有两条指回真树的 junction —— `%TEMP%\mwvg-t5\node_modules`（旧雷）与 `%TEMP%\qg2-head\node_modules`（事故后新埋）；不做删除（本 key 零改动），交由 G3 的 doctor 检查处理。
- **去向：G1..G4 的落地 → 新 key `mw-worktree-junction-guard`**（mini-spec + spec 已建，处 SPEC，下一步 design）。
- **去向：规则缺口 → 待开 key（服务侧）**：AGENTS.md 现有禁令未覆盖 worktree；僵尸 worker 簿记（同日对已 DONE key 报警 8 次）尚未开 key。
- **接受不处理**：本 key 不追「IN-2 复发（2026-10-10）的具体触发命令与会话」（另有 `in2-recurrence-20261010-uncommitted-wipe.md` 记录，收益低于成本）。
