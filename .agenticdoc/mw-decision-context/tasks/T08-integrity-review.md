# T08只读完整性审查
type: review
write_face:
  - .agenticdoc/mw-decision-context/workers/dc-t08-integrity-review/report.md
  - .agenticdoc/mw-decision-context/workers/dc-t08-integrity-review/evidence/integrity-review.md

## 写入允许面
仅自身report.md与evidence/integrity-review.md，由框架角色产物机制落盘；禁止其它文件写入。

## 上下文
目标.agenticdoc/goal.md:1；批准spec/design/plan与两r2report/progress。packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:1编码事故；packages/multi-workers/decision_dashboard.js:1间接脚本写漏ledger。PM hash核TS15/Python30终态均一致，但不证明外来hunks/原文恢复。另coding closure lane只改decision-tool/triage-client与列明测试；你只读，不争写。
## 要求
固定审查首写前与r2终态完整性，不泛审计。TS从r2 baseline-writeface.diff + 对应HEAD构造可靠原文到自身证据（只在沙盒），无需worktree checkout；比对decision-tool非ASCII/注释与实际改动，核34处乱码恢复是否改变无关原文。优先审查r2冻结终态(final-writeface.diff、final-hashes)而非在飞closure源码；如无法构造可靠基线明确覆盖不足，不猜恢复。
Python两间接写decision_dashboard.js/test_decide_sign_auto.py对snapshot/files原文与r2终态/脚本，逐hunk核已批准契约/安全断言是否保留，补可追溯登记建议。测试数量减少不能只听未删安全测试声明，核每删除测试的替代断言。
输出阻塞仅明确泄漏/误执行/数据损坏/主功能不可用；其它集中债，不展开新研究。不执行模型/凭证/服务/真实browser/build/install/commit；只read/find/grep/ls，若工具不能重建git基线则报告给PM执行，不越角色工具。
## 审计目标
.agenticdoc/mw-decision-context/workers/dc-t08-ts-integration-r2/evidence/baseline-writeface.diff与final-writeface.diff；其report/progress/恢复脚本；Python snapshot/files下两文件与patch_dashboard_js.py/rewrite_sign_auto_tests.py/最终hash；批准AC002/019/020。
## 未覆盖面声明
不代PM行为复验、npm check、20AC整体验收；不审计所有大模块；不把语法绿/hash一致当字符原文一致；closure在飞更改不混入r2审查。
## 交付格式
自身report.md + evidence/integrity-review.md；每finding路径:line+基线证据/新证据/严重级别/最小处置；每已删安全用例替代定位或明确缺口。不得修改源码/测试/PM文档/框架。
