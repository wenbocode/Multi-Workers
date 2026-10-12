# achieved — mw-workspace-incident-probe

**性质**：只读取证 key，**零生产改动**（唯一写入为本 key 的 `evidence/**`）。

## 1. 结论

两起事故 **IN-1（workspace junction 消失）** 与 **IN-2（3,448 个已跟踪文件消失又恢复）** 判定为**同源：同一条命令**。

- 元凶：worker `mvr-t16-quality-gate-review`（key `mw-vision-role`）执行 `git worktree remove --force "$env:TEMP\qg-head"`（2026-10-09T12:32:18.452Z / 本地 20:32:18.452；jsonl L142 命令、L144 输出，RC=255）。
- 机制：`qg-head/node_modules` 为指回真树的 junction，真 `node_modules/@earendil-works/pi-ai` 又是指向 `packages/ai` 的 junction ⇒ git 递归删除**穿两层**，删链 + 删 8 个包源码，在 `packages/tui` 撞锁中止（156/236 幸存）。
- 动机（其自述）：为给 key 的 HEAD 状态出可信 QG 判定而隔离建 worktree，用 junction 省一次 `npm ci`。
- 实测语义：`git worktree remove --force` **穿透**；`cmd /c rmdir`（无 `/S`）与 PS `Remove-Item -Recurse` **不穿透**。

## 2. 交付物

`evidence/in1-junction-incident-20261009.md`、`evidence/in2-file-vanish-incident-20261009.md`、`evidence/incidents-timeline-20261009.md`（合并时间线 + 同源判定 + 未坐实清单 + 只建议不实施的 G1..G4）。

## 3. PM 自身纠错

①「9 条 junction 消失」更正为 **8 条消失 + `pi-tui` 保留**；②撤回基于 `npm-cache\_logs` 为空做的 npm 排除（该目录会被滚动清理，PM 自己的 install 也无日志）⇒ **可清理缓存不得用于证明"未发生"**。

## 系统行为变化

本 key **零生产改动**（只读取证）：**无**新增/修改功能，**无** API/行为/配置/产物影响面，不涉 dist 与 changelog。

影响面仅为**新增 4 份取证文档**（本 key `evidence/**`）：`in1-junction-incident-20261009.md`、`in2-file-vanish-incident-20261009.md`、`incidents-timeline-20261009.md`、`research/spec-incident-probe-plan-20261009.md`，以及本 `achieved.md` / `pm-state.md`。对后续任务的参考价值：G1..G4 的判据基础（junction 删除语义实测矩阵）与事故时间线，供 `mw-worktree-junction-guard` 直接引用。

## 4. 遗留

- **未坐实项（原样保留，不补洞）**：删除工具/进程本体（会话穷举为负 ⇒ 来自 pi 之外）；恢复命令具体条目；20:39 npm reify 的触发者；`packages/tui/src` 幸存原因；`%TEMP%\mwvg-t5-probe\node_modules` 链的创建者；触发 `mvr-t16` 重派的窗口。
- **去向：G1..G4 的落地 → 新 key `mw-worktree-junction-guard`**（mini-spec + spec 已建，RQ-1/RQ-2 调研中）。
- **去向：规则缺口 → 待开 key（服务侧）**：AGENTS.md 现有禁令未覆盖 worktree；僵尸 worker 簿记（同日对已 DONE key 报警 8 次）尚未开 key。
- **接受不处理**：`%TEMP%` 内遗留 junction 已用 `rmdir` 摘除（真树零影响）；本 key 不追"恢复命令是谁执行的"（收益低于成本）。
