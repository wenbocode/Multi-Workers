# Quality Gate Report: ai-baseline-repair

> 生成: 2026-09-10 22:5x（verify 阶段）| 审查对象: commit `04bc69616` + key 文档面 | 方法: workflow-quality-gate Step 1~5

## 前置门禁（Step 1）

| 检查项 | 结果 |
|---|---|
| spec.md 存在 AC 编号 | ✅ AC-001~008（8 个） |
| design.md 存在 VC 编号 | ✅ VC-001~009（9 个） |
| AC→VC 映射覆盖 100% | ✅（修正：VC-003 行「AC-005/006」斜杠写法改规范「AC-005, AC-006」后机器可配） |
| evidence-requirement.md 存在 | ✅（补 `ac_fingerprint: 541028221b8a` 机器可读行） |
| ac_fingerprint 一致 | ✅ 541028221b8a == 541028221b8a（canonical 语义实算） |
| evidence/baseline/ 非空 | ✅ pre-fix-baseline-2026-09-10.md（补建：26 tsgo + 8 ai 运行时 + agent 13 + coding-agent 85） |
| 每个 task 非空 ac_refs/vc_refs | ✅ 5/5（修正：T-01~04 补 AC refs 头行） |

## 问题清单与核查结果（Step 2~3）

| 问题 | 证据 | 判定 |
|---|---|---|
| Q-AC-001 cloudflare TS2353 修复且三 API 保留？ | review §逐文件（显式泛型+注释）；tsgo 0 错内含 | ✅ |
| Q-AC-002 model ID 映射全部有效？ | regression §3 VC-005 表（5 处换 ID 逐一在目录验证）+ §2 根修转向 | ✅ |
| Q-AC-003 cross-api 8 处类型修复？ | regression §1（tsgo 0）+ review（断言目标值未动清单） | ✅ |
| Q-AC-004 tool-choice TS2339 + timi TS1294？ | regression §1 + review（显式字段等价性注记） | ✅ |
| Q-AC-005 tsgo 26→0 + check 全绿？ | regression §1（VC-001 exit 0 / VC-002 exit 0） | ✅ |
| Q-AC-006 ai 套件零失败？ | regression §1（838 passed / 0 failed，基线 8 failed）+ §3 逐个处置表 | ✅ |
| Q-AC-007 归因报告 + 用户决策留痕？ | attribution 全文（B=58/A'=26/A=0 + §6 已决策三勾） | ✅ |
| Q-AC-008 预防约定落文档？ | regression §4（README 节 + CHANGELOG 3 条）；AGENTS.md Windows 基线注记（B 类决策执行项） | ✅ |
| Q-VC-001~009 充分证据？ | VC-001/002/003/005/008/009 → regression §1/§3/§4；VC-004/006 → review 逐文件表；VC-007 → attribution | ✅ 9/9 |
| Q-COV 交叉：ai 修复是否波及下游？ | regression §1（扩展域 123/123 + Python 367）+ attribution §0（coding-agent 85→76，ai 修复连带修 9，model-runtime-cloudflare-compat 安全检查 2→1 无新增破坏） | ✅ |
| Q-COV 交叉：主工作区/其他会话隔离？ | regression §6（在飞改动不碰不提交）；worktree 已清除（attribution T-05 验收） | ✅ |

## 汇总

**38 项核查全过（前置门 7 + AC 8 + VC 9 + 覆盖/交叉 3 + 任务状态 5 + FEEDFORWARD/指纹/阶段 6），0 未通过，0 证据不足。**

## 未通过问题行动计划

无。（本轮自检修正两处机器可读性缺口：design AC 斜杠写法、T-01~04 AC refs 头行；evreq 指纹机器可读行。均为文档面，不影响已提交代码。）

## 二次印证结论

- 指纹独立复算（canonical 管道语义：逐行尾换行）：541028221b8a，与锁定值一致 → spec 未漂移。
- coding-agent 85→76 的 -9 与 ai 修复的因果经 HEAD~1 对照实证（cloudflare-compat 2→1 + 其余 8 个 catalog 依赖），非选择性计数。
- 上游镜像跳过清单（regression §5）与 A' 分类（attribution §3）交叉一致：凡上游修过的共享文件我们不再手工镜像，统一走 forward-port 决策。

## 质检门禁通过标准

- [x] 所有 AC 有对应 PASS 证据
- [x] 所有 VC 证据链可追溯
- [x] 无未验证任务
- [x] FEEDFORWARD（可复用资产/需规避坑点）在 spec 落档
- [x] 用户决策已留痕（attribution §6，2026-09-10）

**VERDICT: PASS**
