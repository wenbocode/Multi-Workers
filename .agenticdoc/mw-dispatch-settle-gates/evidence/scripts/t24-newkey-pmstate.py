# -*- coding: utf-8 -*-
"""新建 key 的 pm-state.md（框架 switch_key 只建 index 行，不建 PM state）。"""

import pathlib

p = pathlib.Path(".agenticdoc/mw-dispatch-settle-gates/pm-state.md")
body = """# PM State: mw-dispatch-settle-gates

## 1. Snapshot
- Key: mw-dispatch-settle-gates
- Phase: SPEC
- Next Action: spec 阶段——已写 `spec.md`（9 条 AC + 5 项待裁决策 + 2 个并行 RQ）。下一步：并行派 RQ-1（stage 终态机器锚）/ RQ-2（只读角色产物契约实况）→ 收口后 `advance(spec→design)`；design 阶段须定 AC-002 的 stage 终态锚、AC-006 的产物谓词、AC-005 的写意图模式。待用户确认 5 项决策（D1 doctor 面落地 vs descope / D2 扩守卫 vs 仅改文案 / D3 第三态 / D4 changedFiles 填充 vs 删段 / D5 R18 是否并入）。
- Started: 2026-10-10 21:10
- Updated: 2026-10-10 21:10

## 2. Task Status
*(empty)*

## 3. Evidence Ledger
*(empty)*

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions
- D-001（2026-10-10 21:10）：**key 立项**（用户 2026-10-10 批准）。范围 = `mw-gate-verdict-hardening` 两次独立复审确认的 3 个 AC 部分实现 + 1 个 AC 边界（G-a AC-008 doctor 面 / G-b AC-007 stage 终态 / G-c AC-024 跨 key 写面 / G-d D-038 Python 派发不读 run.json）+ 该 key 执行期自曝的 worker 产物契约缺陷（R22：G-e 派发期可满足性 / G-f 结算期产物判据 / G-g output.md 信息量）+ 文档勘误（G-h）。**非范围**：R21 运行时切换（另需用户批准）、R18（单独立卡待决）、pi 核心与 `packages/*` 之外。
- D-002（2026-10-10 21:10）：**AC 体系 = AC-001…AC-009**，风格沿用 GC-5/GC-6：fail-closed + 机器可读 + 必带反向用例（见 `spec.md` §3）。**证据标准**（AC-009）：`[VERIFY]` 数值必须实测且带 `文件:行号`，报告引用必须对最终工作区重锚 —— 本 key 的直接动因就是上一 key 的“报告写做、锚点漂移、基线误引”。
- D-003（2026-10-10 21:10）：**5 项待裁决策**（spec §4）暂按 PM 提议执行为默认（D1 落地 doctor 面 / D2 扩守卫 / D3 第三态 = `needs-clarification` / D4 填充 + 无则省略 / D5 R18 不并入），用户可否决。
- D-004（2026-10-10 21:10）：**R22 + L3 产物判据 + changedFiles/exit-reason 并入本 key**（评估结论：同族“派发/结算期机械判据”，且 `ui-bridge.ts`（AC-003+AC-005）与 `worker-mode.ts`/`output-writer.ts`（AC-006+AC-007）的文件冲突面要求同 key 串行，分 key 反而制造跨 key 串行与口径分裂）。

## 6. Turn End Records
- 2026-10-10 21:10：立项 + 写 `spec.md`（9 AC / 5 决策 / 2 RQ）+ 建 `pm-state.md`；下一步并行研究（RQ-1/RQ-2）。

## 7. Process Log
- 21:10：用户批准开新 key，并问 R22 + L3 产物判据 + changedFiles/exit-reason 是否适合并入 ⇒ 评估：**适合并入**（理由见 D-004）；据此立项 `mw-dispatch-settle-gates`、写 spec、记录 5 项待裁决策。记 D-001…D-004。
"""
p.write_text(body, encoding="utf-8", newline="\n")
print("pm-state created:", p.stat().st_size, "bytes")
