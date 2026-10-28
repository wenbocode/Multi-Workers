# 事故合并时间线与结论 — 2026-10-09

**key**：mw-workspace-incident-probe（只读取证，零生产改动）
**两起事故同源判定：是 —— 同一条命令。**

**版本**：v3（2026-10-13 PM 修订）。按独立 QG 报告 `evidence/quality-gate-report-20261009.md`（有条件 PASS）的 6 条修复条件（C1–C6）与 13 项缺陷（E1–E13）吸收 IN-2 v2 修正稿；v1 的陈旧数字（3,448 / 3,550 / 1,040 / "97 个"）与错误推断（"穷举为负 ⇒ pi 之外"）已逐条替换或删除，替换处标注 `[E#]`。

## 1. 元凶（已坐实）

worker `mvr-t16-quality-gate-review`（key `mw-vision-role`，pid 159560）于 **2026-10-09T12:32:18.452Z（本地 20:32:18.452）** 执行：

```
cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" …
→ error: failed to delete '…qg-head': Invalid argument   RC=255
```
来源：`.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` L142（命令）/ L144（输出）。
前置（造链）：同文件 L60，12:21:48；善后：L145，12:32:28。

**动机（其自述）**：12:21:28「isolate from concurrent edits and give a trustworthy verdict for HEAD」；12:21:48「set up a clean detached worktree at HEAD for deterministic evidence」。为给 key 出可信 QG 判定而建 worktree，用 junction 借主树 `node_modules` 省一次 `npm ci`。

**共享树脏度（口径修正，`[E12]`）**：v1 写"当时共享树有 97 个他人未提交改动"，QG 未能在会话记录中找到 97 的一手出处，已删除。一手可见的脏度计数：12:32:54.960Z `git status --short` 计 3,531 条（其中 `D`=3,456 ⇒ 非 `D` 条目 75）、12:38:26.354Z 实测 `total modified: 74`、12:40:27.142Z 实测 82 条（78 `M` + 4 `??`）。

## 2. 合并时间线

| 本地时刻 | 事件 |
|---|---|
| 20:21:48 | `git worktree add --detach %TEMP%\qg-head HEAD` + `mklink /J qg-head\node_modules → H:\git\Multi-Workers\node_modules` |
| 20:32:18.452 | `git worktree remove --force "$env:TEMP\qg-head"` 启动 |
| 20:32:22 | 主树 `node_modules` mtime 变化；**穿透第一层**：删 `node_modules/@earendil-works/*` |
| 20:32:22–24 | **穿透第二层**（`@earendil-works/pi-ai` → `packages/ai` 等 8 条链接）：**8 个包整树共 3,300 个 tracked 文件消失** `[E1]`（226+1060+63+1683+19+49+99+101；v1 的 3,448 既非总口径也非 8 包口径——8 包 = 3,300，加上 `packages/tui` 被删的 156 才等于 3,456）；`packages/coding-agent` mtime 20:32:24 |
| 20:32:24.249–29.183 | 删除瞬间被夹逼（同会话先 `Get-FileHash` 成功、5 秒后 ENOENT；区间 = [12:32:14.011Z 树完好, 12:32:29.183Z ENOENT]，元凶执行窗含于其中） |
| 20:32:24.444 | git 在 `packages/tui` 撞锁中止，返回 `Invalid argument` RC=255 ⇒ **`pi-tui` 链接保留；其目标 `packages/tui` 被删 156/236（= 148 `dist` + 7 `native` + 1 根文件，删除后重建），原物幸存 80/236（= 37 `src` + 36 `test` + 3 旧 `native` + 4 旧根文件）** `[E2]` |
| 20:36:07–20:38:18 | 恢复（命令原文已坐实，`[E3]`）：`git ls-files -d -z \| xargs -0 -r -n 200 git checkout --`，**只重写 `git ls-files -d` 的当前缺失路径**（d2f3:204 脚本原文 / :206 执行 / :207 `deleted_before=3456 → checkout_batches_rc=0 → deleted_after=0`）；`agent-team-loop-ack.test.ts` mtime 即此刻。v1 的"缺失 ∪ 与 HEAD 有差异"机制表述作废——恢复后实测 `total modified: 74`（d2f3:209），在场的已修改文件未被重写 |
| 20:37:54 前后 | mtime 直方图口径（**方法漂移、未复核**）：v1 的 3,550 / 1,040 已作废；v2 自测为「落在 `2026-10-09 20:xx` 的 tracked 文件合计 **2,512**」（20:36=1202 / 20:37=833 / 20:38=457，其余分钟 ≤3；2026-10-10 11:1x 复测 **2,537**，含漂移；v1 的 3,550 与本值的差额 ≈ 2026-10-10 的 coding-agent 构建 953 个新 mtime）。该直方图 QG 为 [未复测-无shell]，仅作旁证，不作承重数字 |
| 20:38:49 | PM 会话首次观测「`node_modules\@earendil-works` 仅剩 1 条 junction = `pi-tui`」（session `01a0d325` L2925，QG 已复核） |
| 20:38:58–20:39:10 | PM 会话 `01a0d325` 执行 `npm install --ignore-scripts`（L2926）reify 重建 8 条被删 workspace junction（mtime 20:39:03）与被删的 `node_modules` 条目；重建后 `@earendil-works` 共 **10 条目**（9 条 junction + `gondolin` 真目录），lockfile 零改动（L2927） |

## 3. 两起事故的关系

IN-1（junction 消失）与 IN-2（3,456 个已跟踪文件消失又恢复）**不是两件事，是同一条命令的两种表现**：`qg-head/node_modules` 是**双层 junction 链**，git 递归删除穿两层 → 既删了链接（IN-1）也删了各包真实源码（IN-2）。三点互证：时间戳（20:32:22–24）、损坏边界（8 包整树 3,300 + `packages/tui` 被删 156 = 3,456，与双源 `D` 计数吻合）、恢复链（`restore.sh` 3,456→0 + `npm install` 重建 8 条链；恢复面恰为删除面的补集）。

**同源判定的复核级别（诚实标注）**：由独立 QG worker `wip-qg-review` 一手复核成立（`evidence/quality-gate-report-20261009.md` §3.2）——三点各自独立；"另有解释"经五项约束（窗口内唯一破坏性命令、git 自身错误文本、删除面精确等于链接目标集合、零 ref 变动、worktree 注册消失而目录残留）逐类排除，未发现可信替代解释。**限制**：复现 A/B 与 mtime 直方图两项在该 QG 为 **[未复测-无shell]**（QG 无 shell），仅做「与一手会话记录互证」级核验；同机制先例见 §4.4。

## 4. 关键教训（含 PM 自身错误）

1. **`git worktree remove --force` 穿透 junction；`cmd /c rmdir`（无 `/S`）与 PS `Remove-Item -Recurse` 实测均不穿透。** 同日 4 次「worktree 内带 junction 指回真树」的操作中，先 `rmdir` 摘链的 2 次零事故，直接 `remove` 的 1 次即本次事故 —— 规则已被现实检验。
2. **PM 错误 ①**：曾述"9 条 junction 消失"，实测为 **8 条消失 + `pi-tui` 保留**（`@earendil-works` 共 9 条 junction + `gondolin` 真目录）。
3. **PM 错误 ②（重要）**：曾用 `npm-cache\_logs` 为空来排除 npm —— 该目录会被滚动清理（`logs-max=10`，现存最早 2026-10-10 11:07:28，**PM 自己 20:38:58 的 `npm install` 也未留日志**）⇒ **可清理缓存不得用于证明"未发生"**。该排除已撤回。
4. **同机制先例（QG 漏项补齐，`[E13]`）**：**2026-09-09 已发生过一次同机制事故**。session `2026-09-08T12-16-45-828Z_01a080f3-0704-77dc-aaf8-29e1e16b4e29.jsonl`：L539（09:43:19.740Z）记 `failed to delete: Invalid argument`；L541（09:44:18.454Z）记 **"DISASTER. The `git worktree remove --force` DID delete through the junctions and beyond"**；L543（09:46:47.817Z）记 "~1100+ deleted tracked files across packages/agent, packages/ai, packages/coding-agent"、"multi-workers SURVIVED — the junction chain didn't reach it"（本文件直接复核原文）。⇒ 同机制事故族**已知三次**：2026-09-09 → 2026-10-09（本次）→ 2026-10-10（复发，见 `in2-recurrence-20261010-uncommitted-wipe.md`）。

## 5. 未坐实项

**已坐实、不再列为未解（QG 条件 C3，吸收 v2）**：
- 删除工具/进程本体 = `git worktree remove --force`（元凶命令原文见 §1，e335:142）；
- 恢复命令 = `restore.sh` 内的 `git ls-files -d -z | xargs -0 -r -n 200 git checkout --`（d2f3:204/206/207，3,456→0）；
- 20:39 npm reify 触发者 = PM 会话 `01a0d325`（`npm install --ignore-scripts`，L2926）。

v1 写的"删除工具/进程本体（AC-005 穷举会话记录为负 ⇒ 指令来自 pi 之外的进程）"**错误且已删除（`[E4]`）**：v1 的扫描词表只匹配命令**字面**触及 `packages/**` 的文本，漏掉整类「字面删 worktree、实际穿链进真树」的命令，属扫描范围不足的伪阴性（IN-2 §5 自曝、QG §3.4 复核）。

**仍未坐实（原样保留，不补洞）**：
1. 真树 `packages/tui` 内造成 `unlink` EINVAL 的**具体被占用文件/进程**（"中止发生在 `pi-tui` 子树内"这一形态学结论已知，具体中止点与顺序未知）；
2. `%TEMP%\mwvg-t5-probe\node_modules` 链的清理者（该链现已不存在，清理命令未找到）；
3. 触发 `mvr-t16` 重派的窗口（launcher 队列派发；10-09 派发行已被 10-10 重派覆盖，无 `dispatch_worker` 记录）；
4. `3531 − 3456 = 75` 的逐条构成（仅有算术关系与 `total modified=74` 旁证）；
5. 事故当下 20:3x 是否存在 reflog 之外的 ref 级动作（只能给出 reflog 无条目、`refs/stash` 不存在、`git fsck` rc=0 三条）；
6. `.tmp/t13-worktree`（spec 提及的路径）：2026-10-09 全量 toolCall 检索为负 ⇒ 该 worktree 实际不存在。

**活雷（v2 新增，供 G1..G4 参考）**：2026-10-10 11:20 实测仍有两条指回真树的 junction —— `%TEMP%\mwvg-t5\node_modules`（旧雷）与 `%TEMP%\qg2-head\node_modules`（事故后新埋）。现场状态以 `mw doctor` 为准。

## 6. 建议（**只建议，不在本 key 实施**）

必须**固化为机械步骤**，不能依赖 agent 自觉：

- **G1 确定性拦截**：工具层 guard 命中 `git worktree remove` 且目标树下存在 reparse point ⇒ 执行前 block，报错指向 G2。
- **G2 唯一正规命令** `mw worktree rm <path>`：枚举 reparse point → 校验目标在仓库内 → **只摘链**（`rmdir`，禁 `/S`）→ 复核主树链接目标逐条未变 → 才 `git worktree remove --force` → 打印前后对照；任一步失败即中止，**不降级继续**。
- **G3**：`mw worktree add` 默认不建链（`npm ci` 或真实复制）；如需建链则登记注册表。`mw doctor` 增加「遗留的、指向真树的 junction」检查（当前已知活雷见 §5）。
- **G4 可观测**：doctor/看门狗加「已跟踪文件数骤降」「junction 目标丢失」两条机器判据（本次 3,456 文件消失约 5.5 分钟、零报警）。

**待办**：上述 G1..G4 的实现走新 key `mw-worktree-junction-guard`（mini-spec + spec 已建，阶段 SPEC）。
