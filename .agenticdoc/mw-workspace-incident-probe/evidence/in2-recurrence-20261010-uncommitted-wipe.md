# IN-2 复发：2026-10-10 第二次工作区文件消失 + 未提交改动被批量覆盖

- 记录人：`mw-gate-verdict-hardening` 窗口之外的独立审计（本次由 PM 直执的只读审计，非本 key 派发）
- 记录时刻：2026-10-10 15:0x（本地 UTC+8）
- 归属：IN-2（`evidence/in2-file-vanish-incident-20261009.md` 的同族事件，**第二次发生**）
- 性质：只读取证 + 一条落地建议

> 引用来源说明：本文引用的 IN-3 重跑稿（`.agenticdoc/**` 81 份覆写）已于 2026-10-10 15:19（本地）按 PM 决策**整体回退到 HEAD**（命令：`git restore --source=HEAD --worktree --pathspec-from-file=…/rewrites-81-filelist.txt`）。
> 重跑稿全文（含下文 D.11 段落）保存在 `../../_incidents/in3-queue-reenqueue-20261010/rewrites-81-20261010.patch`（81 个 `diff --git` 段，可用 `git apply` 前向复原）。
> 因此下文的行号引用对应当前工作树已不存在的重跑稿版本，检索时请以 patch 为准。

---

## 1. 结论

**IN-2 在 2026-10-10 再次发生**（IN-2 自身为第二次；连同 2026-09-09 同机制先例 `01a080f3:539/:541`，属同机制事件族**已知第三次**，见 `incidents-timeline-20261009.md` §4.4），形态与 10-09 那次一致（tracked 文件先消失、随后被另一会话批量恢复），
但本次多了一个可量化的后果：**恢复用 HEAD 内容覆盖了工作树 ⇒ 11:29 之前落地的全部未提交改动被抹掉**。

---

## 2. 实测时间线

| 时刻（本地） | 事件 | 证据 |
|---|---|---|
| 11:29–11:30 | `packages/coding-agent` 403 + 207 个 `.ts`（src+test）在同一分钟被重写；`packages/ai` 175 个 `.ts` 同在 11:29 | `Get-ChildItem … \| Group-Object LastWriteTime` 直方图 |
| 11:28–11:30 | 同窗口另一 worker 记录 `git ls-files -d` = **3056**（coding-agent 1683 / ai 886 / tui 156 / session-backends 101 / server 99 / client 63 / protocol 49 / evals 19），随后删除计数 `2056→1856→1656→1056→456→256→0` 递减 | 重跑稿 `mw-vision-role/evidence/runs/verify-mw-vision-role-20260926.md` D.11（patch 内检索 `D.11`）+ `%TEMP%\mwv14d\poll-restore.sh` 输出 |
| 11:32 | gitignored `packages/ai/src/providers/data/`（40 个 JSON）被以漂移上游数据重生 ⇒ `npx tsgo --noEmit` 24 红（`together.json` 的 `moonshotai/Kimi-K2.6`：dist=2 / src=0） | D.11.2 |
| 11:35:53 | 该 worker 用 `cp -r dist/providers/data/. src/providers/data/` 定点恢复（本文件记录时复核 `git diff --no-index` 退出 0） | D.11.3；`%TEMP%\mwv14d\ai-recover.sh` |
| 11:40:42–11:40:47 | 全局 bundle 刷新 + coding-agent dist 重建（vision 角色的 dist 补建） | `mw doctor` bundle 段；dist mtime |

恢复机制从删除计数递减率（约 200 条/轮）判断为**另一会话在批量 `git checkout -- <paths>`**（D.11.1 原文："另一个会话正在批量 `git checkout --` 恢复"）。

---

## 3. 可判定的后果：未提交改动被覆盖（硬证据）

`packages/coding-agent/test/extensions/agent-team-loop-ack.test.ts`

- `mw-widget-terminal-lifecycle` 的 T-01 复核行（`.agenticdoc/mw-widget-terminal-lifecycle/tasks/T-01-ack-store.md`）记录：2026-10-10T03:03:50Z（本地 11:03）"HEAD 版本埋点回退为 `console.log`（round 2 修正未提交），重新以 `process.stdout.write` + `verify()` 助手替换…测试 5/5 绿、未 commit"。
- 本文件记录时的实测：该文件 **mtime = 2026-10-10 11:29**、第 88 行仍是 `console.log`、`git status` 干净、`git diff` 为空。
- ⇒ 11:03 的修正与批量恢复事件**时间相邻且被覆盖**；**文档（声称已修）与工作树（未修）互相矛盾**，这是本次复发可判定的第一处净损失。

对照（未被覆盖的 P0 遗留）：`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts` 的 1 处未提交 diff 在 10-09 IN-2 中**未被坐实**（事故前 12:17–12:32 观测窗内无一手记录；QG `[QG-E10]/[QG-E11]` 更正，见 `in2-file-vanish-incident-20261009.md` §4.3），本次复核仍为空。

---

## 4. 复发识别指纹（补齐 IN-2 该有的一栏）

- [ ] `git ls-files -d` 出现**数千**量级，且随后在数分钟内单调递减至 0（=`git checkout --` 批量恢复）
- [ ] `git status` 里 ` M` 计数**不增反减**；`packages/**` 全树 mtime 落在同一分钟（本次 11:29–11:30）
- [ ] 被恢复文件内容逐字节等于 HEAD（`git diff` 空），因此**"已落地但未提交"的工作全部消失且不留 git 痕迹**
- [ ] 同一时段 `.agenticdoc/**` 的改写**不受影响**（恢复面只覆盖 tracked 源码树）⇒ 文档与树出现矛盾
- [ ] gitignored 生成物（例：`packages/ai/src/providers/data/`）在恢复后**不会**被还原，只能被"再生成"成漂移版本 ⇒ `tsgo --noEmit` 变红
- [ ] HEAD 不变、git 对象完好（`git log`/`git fsck` 正常）

---

## 5. 未坐实项（不补洞）

1. 触发第一次消失的**具体命令与会话**（与 10-09 IN-2 相同的开放问题：`checkout -f` / `switch` / `reset --hard` / `worktree remove --force`）。
2. 执行批量恢复的会话与命令原文（只知道"另一个会话"在恢复，未取到 JSONL 证据）。
3. 11:29–11:30 之外是否还有被覆盖的未提交改动（恢复是按 HEAD 覆盖整棵 tracked 树，**理论上全树都可能**；本次只对 1 处做了逐字节实证，其余为形态推断）。
4. 11:03 的 ack.test.ts 修正是否**真的**落过盘（不能排除"该复核行本身是假声明"）；两种可能都需要 JSONL 才能定性。

---

## 6. 建议（只建议，不实施）

1. 把本文件挂到 IN-2 的调查范围内一起收口（同一 key `mw-workspace-incident-probe`，避免开重复 key）。
2. 关键动作前先取窗口快照：`git status --porcelain` 计数 + 关键文件 sha256；该 key 的 `evidence/` 是唯一应被信任的"未提交工作存档"。
3. 任何"批量恢复"必须先备份未提交改动（`git stash push --include-untracked` 或 `git diff > patch`），否则等价于静默丢弃。
