# Quality Gate Report: mw-worker-tree-kill

**时间**: 2026-09-19T18:45:00+08:00（初版）
**时间**: 2026-09-19T18:55:00+08:00（复版：Q-D-2 补验后重跑，用户「按推荐，并做 qg」）
**时间**: 2026-09-19T23:15:00+08:00（终版：独立 review 轮 + 处置复验，用户「review and quality gate」）
**触发**: Stage 3 完成（全量，合入前级）
**范围**: 全量（T-01/T-02/T-03 + Q-D-2 全链补验 + 独立 review）

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec.md AC 编号 | ✅ AC-001~006 |
| design.md VC 编号 | ✅ VC-001~006 |
| AC→VC 映射覆盖 100% | ✅（6/6，design §8） |
| evidence-requirement.md 存在 | ✅ |
| ac_fingerprint 一致 | ✅（264ea1756fc7，执行期 REVISED 后重算并同步） |
| evidence/baseline/ 非空 | ✅（known-windows-env-baseline-2026-09-19.md） |
| 每个 task 非空 ac_refs/vc_refs | ✅（T-01~T-03 均有绑定） |

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | idle watchdog 退出前清理 tracked 树 | ✅ 充分 | runs/run-2026-09-19.md（单测 1：kill_calls=1 且 order < exit） | — |
| Q-AC-002 | wall budget 退出路径行为一致 | ✅ 充分 | runs（单测 2：timeout: 2 wall 分支同断言） | — |
| Q-AC-003 | settled-catch 退出前清理 | ✅ 充分 | runs（单测 3：writePhaseFile 注错 → kill 先于 exit） | — |
| Q-AC-004 | 'exit' 安全网兜底清理 | ✅ 充分 | runs（单测 4：listener 直调 → kill 被调 + 兜底 output 不变） | — |
| Q-AC-005 | 成功路径零回归 | ✅ 充分 | runs（单测 5：零 kill/零 exit/exit=0 + 原套件 158/158） | — |
| Q-AC-006 | 真实进程树（含孙进程）消亡 | ✅ 充分（机制级 L2） | runs（live：orphan_count=0，2.11s） | 全链 mw 派发 smoke 未跑，见 Q-D-2 |
| Q-VC-001 | kill 先于 exit 断言 | ✅ 充分 | invocationCallOrder 断言 | — |
| Q-VC-002 | wall 分支同断言 | ✅ 充分 | 同上 | — |
| Q-VC-003 | catch 分支同断言 | ✅ 充分 | 同上 | — |
| Q-VC-004 | hook 兑底断言 | ✅ 充分 | listeners 直调 | — |
| Q-VC-005 | 成功零调用断言 | ✅ 充分 | — | — |
| Q-VC-006 | live 探活全灭 | ✅ 充分 | 真实 taskkill /T | — |
| Q-COV-F1 | idle 异常路径 | ✅ 充分 | 单测 1 + live | — |
| Q-COV-F2 | wall 异常路径 | ✅ 充分 | 单测 2 | — |
| Q-COV-F3 | catch 异常路径 | ✅ 充分 | 单测 3 | — |
| Q-COV-F4 | 硬崩溃兑底路径 | ✅ 充分 | 单测 4 | — |
| Q-COV-F5 | 成功路径零回归 | ✅ 充分 | 单测 5 + 原套件 | — |
| Q-COV-F6 | 真实树终止（含孙进程） | ✅ 充分 | live | — |
| Q-D-1 | 杀树是否阻塞/破坏写盘顺序 | ✅ 充分 | timeoutExit 内同步写盘（appendFileSync/writeSync）先于 fire-and-forget kill（同函数语句序），单测断言 trace/output 内容完整 | 结构性保证 |
| Q-D-2 | 全链 mw 派发 smoke（真实 worker 挂起 bash 命令 → wall kill → 无孤儿） | ✅ 充分 | runs/run-2026-09-19.md「全链 mw 派发 smoke」：serve 91432 → launcher → worker 44776，挂起 Start-Sleep 109s → wall kill 10:38:16 → kill 后 7s/31s 两次探活 ppid=44776 全空，orphan_count=0；output.md kill 前落盘 | 已补验（复版升级 ✅） |
| Q-D-3 | POSIX 分支（kill(-pgid)）有效性 | ✅ 充分（用户接受） | 复用 pi 既有 killProcessTree（bash 工具超时/print-mode 信号路径同一实现，生产在用）；本 key 未新增平台分支；live 用例已就绪（detached 组长 + 探活），待 Linux 环境可随时闭环 | 用户 2026-09-19 确认接受组合证据 |

## 汇总

- **总问题数**: 21
- **通过（充分）**: 21（100%；含 Q-D-2 补验升级、Q-D-3 用户确认接受）
- **有条件通过（不足）**: 0
- **未通过**: 0

**质检结论**: ✅ 通过（初版 2 项 ⚠️ 均已按用户确认的处置关闭：Q-D-2 补全链真实 smoke，Q-D-3 接受组合证据）

## 未通过问题行动计划

无。遗留跟踪（非欠债）：
- POSIX live 用例（agent-team-loop-worker-tree-kill-live.test.ts）已随仓库就绪，未来在 Linux 环境跑一次即闭环（不阻塞本 key）。

## 二次印证结论

- spec §2 平台约束（win32/POSIX）→ Q-D-3 覆盖（用户已确认接受）。
- spec §2.2 性能（不阻塞退出）→ Q-D-1 覆盖。
- Function Flow 节点（watchdog/catch/硬崩溃/平台分支/写盘）→ Q-AC-001~004、Q-D-1、Q-D-3 一一对应。
- Coverage Matrix 异常路径行（F1~F4、F6）→ 全部有 Q-COV 对应。
- 无 task vc_refs 空绑定遗漏。
- 遗漏检查：无新增发现。

## 独立 review 轮（终版新增）

- 审查者：review-mw-worker-tree-kill（独立 LLM，只读静态审查，37 次工具调用，全量读 spec/design/两测试文件/shell.ts/bash.ts/print-mode.ts/output-writer.ts/既有看门狗套件）
- 判定：0 Critical / 1 Warning（W-1 CHANGELOG 缺失）/ 5 Suggestion；代码与测试本体 LGTM（D-001~004 与 VC-001~006 兑现、mock 边界与 live 分层正确、kill 无抛路径、幂等双重调用可证）
- 处置：W-1/S-1/S-3/S-4/S-2 全部采纳并落地（CHANGELOG 补条目；exit hook try/catch；补 2 早期位点用例；mock 语义注释；Windows 窄窗口记入遗留）
- 复验：单测 7/7 + live 1/1 + 原套件 158/158 = **166/166**；`npm run check` EXIT=0；双 dist 重建（coding-agent/dist + mw bundle/全局安装）均含 S-1 结构
- review 报告全文见 workers/review-mw-worker-tree-kill/output.md

## 终版结论

✅ 通过：21/21 问题充分 + 独立 review 0 Critical、唯一 Warning（流程性 CHANGELOG 条目）已修复、全部 Suggestion 已采纳或记档，复验全绿。无未闭合项。
