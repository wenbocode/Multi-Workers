# T08固定收口：跨层预算/契约与已知邻接红
type: coding
write_face:
  - packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts
  - packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts
  - packages/coding-agent/test/suite/decision-context-integration.test.ts
  - packages/coding-agent/test/suite/decision-context-agent-materials.test.ts
  - packages/coding-agent/test/suite/decision-tool.test.ts
  - packages/coding-agent/test/suite/triage-client-state.test.ts
  - packages/multi-workers/test_decide_registry_contract.py
  - packages/multi-workers/test_decision_dp25_empty_value.py
  - packages/multi-workers/test_decision_required_refusal.py
  - packages/multi-workers/test_decision_observation.py

## 上下文
目标.agenticdoc/goal.md:1；批准spec/design/plan，T08固定收口，不扩AC。packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:1291仍2000B；packages/multi-workers/test_decide_registry_contract.py:75冻结旧TS行。两r2报告全文必读；Python MAX_STATE_BYTES8192实测最大卡3868B；邻接59F本keyT01遗留，不当Windows噪声。PM已接管，所有旧worker停写。
## 要求
先完整读所有待改文件。首写前保存允许面原文/hash/diff含untracked。10min内保存真实行为RED，不先改源码。
1 四业务material通过真实Python CLI由发布的8192B/transport边界整份拒绝、不截断；取消错误2000B客户端封顶或对齐唯一权威，不全局降安全预算（其余21DP不改）。测试完整真实任务材料>2000B实际POST及>8192B零POST，不仅stub runner。dp25签收路径也须覆盖。
2 查清REQUIRED_FIELDS_BY_DP实际调用，不机械改旧验证器导致业务材料含审计键。三DP字段按registry统一，Python parity对三DP真比较，不冻结旧行；其它dp既有债可明确保留。迁移受影响本面TS测试，不能复活旧四DP兼容。
3 三份邻接pytest真实复现、核每类根因，按新四部分dp25/动态dp3契约迁移原安全断言。不得删测试/跳过/弱化secret/空值/零POST/记录失败安全矩阵追绿。若真实实现缺陷且超写面，立即报告确切路径/失败，禁止越面修。
禁止泛重构/额外研究。固定三缺口闭合后停写交接，剩余低影响债集中报告。无any/inline imports/参数属性；read/edit或UTF8临时脚本，不PowerShell读改源码。禁止框架/凭证/真实provider/Jev/browser/build/install/commit/共享服务起停。临时HOME/USERPROFILE/PI_CODING_AGENT_DIR，合成auth+读前spy、随机loopback。不运行npm full check，PM统一。
## 写入允许面
- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts
- packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts
- packages/coding-agent/test/suite/decision-context-integration.test.ts
- packages/coding-agent/test/suite/decision-context-agent-materials.test.ts
- packages/coding-agent/test/suite/decision-tool.test.ts
- packages/coding-agent/test/suite/triage-client-state.test.ts
- packages/multi-workers/test_decide_registry_contract.py
- packages/multi-workers/test_decision_dp25_empty_value.py
- packages/multi-workers/test_decision_required_refusal.py
- packages/multi-workers/test_decision_observation.py
## 写入禁止面
其余源码/测试/生成物/框架/依赖/config/其它key/PM文档。不得覆盖外来hunks。
## 验收命令
packages/coding-agent根 node ../../node_modules/vitest/dist/cli.js --run test/suite/<每个改动文件>.test.ts；packages/multi-workers根 python -X utf8 -m pytest <每个改动文件> -q；禁止全套。每文件完整UTF8 stdout/stderr+UTC+argv+exit独立落盘，不筛/tail；root node node_modules/@typescript/native-preview/bin/tsgo.js --noEmit若路径实际存在否则用本地bin（禁npx安装），biome只读允许面。修改新测试必须运行。
## 改动历史
T08两r2已交付并ack，但TS2000B/旧row冻结及三邻接suite59F未收口；用户2026-10-23要求继续。本卡是既有T08固定补缺，不新增需求。
2026-10-23首派dc-t08-closure-fixes业务BLOCKED、10/10源码hash未变：正文写面散文被生成信封提取，头正确但runtime只解析散文1项。PM改正文为与头一致精确10路径，重派同任务，不改门禁或旧run。必读旧run报告/真实RED/hand-off；草案未实施，不能当GREEN。
## 交付格式
report.md、原RED/GREEN完整log、首写和终态sha/原文/diff；精确文件登记每行路径，不夹自然语言；真实HTTP正文/预算/零发送和各suite计数；未验/阻塞明确，不称全keydone。
