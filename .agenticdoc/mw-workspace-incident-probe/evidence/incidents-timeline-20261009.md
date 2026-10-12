# 事故合并时间线与结论 — 2026-10-09

**key**：mw-workspace-incident-probe（只读取证，零生产改动）
**两起事故同源判定：是 —— 同一条命令。**

## 1. 元凶（已坐实）

worker `mvr-t16-quality-gate-review`（key `mw-vision-role`，pid 159560）于 **2026-10-09T12:32:18.452Z（本地 20:32:18.452）** 执行：

```
cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head" …
→ error: failed to delete '…qg-head': Invalid argument   RC=255
```
来源：`.pi/agent/sessions/--H--git-Multi-Workers--/2026-10-09T12-07-43-157Z_01a1208f-e335-767d-a127-bf295f75a861.jsonl` L142（命令）/ L144（输出）。
前置（造链）：同文件 L60，12:21:48；善后：L145，12:32:28。

**动机（其自述）**：12:21:28「isolate from concurrent edits and give a trustworthy verdict for HEAD」；12:21:48「set up a clean detached worktree at HEAD for deterministic evidence」。当时共享树有 97 个他人未提交改动 ⇒ 为给 key 出可信 QG 判定而建 worktree，用 junction 借主树 `node_modules` 省一次 `npm ci`。

## 2. 合并时间线

| 本地时刻 | 事件 |
|---|---|
| 20:21:48 | `git worktree add --detach %TEMP%\qg-head HEAD` + `mklink /J qg-head\node_modules → H:\git\Multi-Workers\node_modules` |
| 20:32:18.452 | `git worktree remove --force "$env:TEMP\qg-head"` 启动 |
| 20:32:22 | 主树 `node_modules` mtime 变化；**穿透第一层**：删 `node_modules/@earendil-works/*` |
| 20:32:22–24 | **穿透第二层**（`@earendil-works/pi-ai` → `packages/ai` 等 8 条链接）：8 个包整树共 3,448 个 tracked 文件消失；`packages/coding-agent` mtime 20:32:24 |
| 20:32:24.249–29.183 | 删除瞬间被夹逼（同会话先 `Get-FileHash` 成功、5 秒后 ENOENT） |
| 20:32:24.444 | git 在 `packages/tui` 撞锁中止，返回 `Invalid argument` RC=255 ⇒ **仅 `pi-tui` 与 156/236 的 `packages/tui` 幸存** |
| 20:37:54 | 恢复动作：路径级强制 checkout 家族（实测只重写「缺失 ∪ 与 HEAD 有差异」的文件，3,550 个文件获新 mtime，1,040 个无关 tracked 文件 mtime 未变）；`agent-team-loop-ack.test.ts` mtime 即此刻 |
| 20:39:03 | `npm install` reify 重建 8 条 workspace junction（11 个 `@earendil-works` 条目全部 20:39:0x） |

## 3. 两起事故的关系

IN-1（junction 消失）与 IN-2（3,531 文件消失）**不是两件事，是同一条命令的两种表现**：`qg-head/node_modules` 是**双层 junction 链**，git 递归删除穿两层 → 既删了链接（IN-1）也删了各包真实源码（IN-2）。三点互证：时间戳（20:32:22–24）、损坏边界（8 包 + 8 链接）、恢复链。

## 4. 关键教训（含 PM 自身错误）

1. **`git worktree remove --force` 穿透 junction；`cmd /c rmdir`（无 `/S`）与 PS `Remove-Item -Recurse` 实测均不穿透。** 同日 2 次"先 rmdir 摘链"的 worktree 零事故，1 次直接 remove 即本次事故 —— 规则已被现实检验。
2. **PM 错误 ①**：曾述"9 条 junction 消失"，实测为 **8 条消失 + `pi-tui` 保留**。
3. **PM 错误 ②（重要）**：曾用 `npm-cache\_logs` 为空来排除 npm —— 该目录会被滚动清理（现存最早 20:45:34，**PM 自己 20:38:58 的 `npm install` 也未留日志**）⇒ **可清理缓存不得用于证明"未发生"**。该排除已撤回。

## 5. 未坐实项（两卡合计）

删除工具/进程本体（AC-005 穷举会话记录为负 ⇒ 指令来自 pi 之外的进程）；恢复命令具体是哪一条；20:39 `npm` reify 由谁触发；`packages/tui/src` 为何幸存；`%TEMP%\mwvg-t5-probe\node_modules` 链由谁建；触发 `mvr-t16` 重派的窗口（launcher 队列派发，无 `dispatch_worker` 记录）。

## 6. 建议（**只建议，不在本 key 实施**）

必须**固化为机械步骤**，不能依赖 agent 自觉：

- **G1 确定性拦截**：工具层 guard 命中 `git worktree remove` 且目标树下存在 reparse point ⇒ 执行前 block，报错指向 G2。
- **G2 唯一正规命令** `mw worktree rm <path>`：枚举 reparse point → 校验目标在仓库内 → **只摘链**（`rmdir`，禁 `/S`）→ 复核主树链接目标逐条未变 → 才 `git worktree remove --force` → 打印前后对照；任一步失败即中止，**不降级继续**。
- **G3**：`mw worktree add` 默认不建链（`npm ci` 或真实复制）；如需建链则登记注册表。`mw doctor` 增加「遗留的、指向真树的 junction」检查。
- **G4 可观测**：doctor/看门狗加「已跟踪文件数骤降」「junction 目标丢失」两条机器判据（本次 3,448 文件消失约 5.5 分钟、零报警）。

**待办**：上述 G1..G4 的实现走新 key `mw-worktree-junction-guard`（mini-spec 已定形）。
