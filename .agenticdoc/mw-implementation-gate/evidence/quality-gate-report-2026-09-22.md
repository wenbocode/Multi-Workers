# Quality Gate Report: mw-implementation-gate

> 日期: 2026-09-22
> 门禁: /quality-gate
> 备注: 本 key 由 4 个 worker（2 research + 2 coding）与 PM 协作完成——流程本身即本 key 主题的正确示范（spec → claim → dispatch → 吸收 → 闭环）。

## AC 勾销表

| AC | 判定 | 证据 |
|----|------|------|
| AC-001 无 claim 拒写代码路径 + reason 指引 | PASS | suite 测试 1/2（write 文件未建、edit 内容未变；reason 含 implementation-gate/mini/.agenticdoc/spec.md 指引；blocked 审计行含 tool/basis/target） |
| AC-002 本窗口 claim 放行 | PASS | suite 测试 3（claim 行= currentClaimId() 本进程 host:pid → 放行无审计；行移除后同批再写被拦——门中介证明）+ 测试 4（他窗口 claim 仍拦，判定确为窗口级） |
| AC-003 mini fast path 放行且留审计 | PASS | suite 测试 5（fresh mini-spec → 放行 + mini-pass 审计行 basis=mini-spec:<path>）+ 测试 6（25h 衰减回拦） |
| AC-004 白名单路径不受影响 | PASS | suite 测试 8（同批 .md/docs/.agenticdoc/tmp 全过，对照 packages/x/real.py 唯一被拦——经门而过，非绕门） |
| AC-005 框架 SKILL.md 触发词 + diff-installed clean | PASS | commit `e9360db`（origin/master，fa97ed6..e9360db）；description 含 "non-trivial implementation"；diff-installed.py exit 0（PM 复核） |
| AC-006 真实工具层自动化测试 | PASS | test/suite/agent-team-loop-implementation-gate.test.ts 9/9：faux provider tool_use → agent-loop → beforeToolCall → ExtensionRunner.emitToolCall → 真实 createExtensionAPI 注册面（唯一 stub：bash 后端记录器，兼"未达执行"证明）；接线敏感性实证（去 register 行 9/9 红） |

## 回归

- 守卫 suite 9/9（PM 复跑）；protected-config 11/11（词法修复零波及，独立词法器）；`npm run check` exit 0（PM 复跑全链）。
- 真缺陷闭环：Windows 反斜杠词法漏拦（T3 worker 发现）→ 最小修复 → 13 必中/10 必避探针 → 登记 P-004。

## 偏差与边界（如实声明）

- **部署生效面**：守卫需 `mw setup --build` + 窗口重启后生效；当前窗口跑旧 bundle，重启前真机无门禁（suite 层已验证行为）。遗留到 achieved。
- bash 侧非沙箱（python -c 内联写、预写脚本、find -delete、PowerShell cmdlets 已知漏过）——模块头声明，属接受的边界非缺陷。
- 三条件放行语义含妥协项：他窗口持有 active claim 不会放行本窗口（窗口级，spec 原义）；worker env 全放行（预授权，派发门禁已在上游把关 key 文档）。

## 结论

**PASS** —— 6/6 AC 勾销，回归零破坏，接线敏感性实证，真缺陷已修并沉淀坑点 P-004。
