# Research: confirmed intent（spec）

## 决策问题
确定八DP收敛范围、正式质量审核与autopilot gate职责、新建独立key，以及联合设计的必要边界。

## 调研方法与出处
- 用户本轮直接确认：dp6承担正式质量审核；dp15按当前设定边界给autopilot模式做gate审核；独立开key。
- `.agenticdoc/mw-decision-context/evidence/requirements-dp-consolidation-confirmed.md:3`：八DP保留集合及删除运行能力、历史只读、四门联合设计要求。
- `.agenticdoc/goal.md:5`：项目协作目标；Key Constraints要求Extension API、不改pi核心、文件锁和凭证隔离。
- `packages/multi-workers/decide_registry.json:344`：dp6登记，问题qg_verdict，现有选项pass/fix/reopen。
- `packages/multi-workers/decide_registry.json:419`：dp7登记，问题gate_cause，现有选项missing-evidence/stale-verdict/config/unknown。
- `packages/multi-workers/decide_registry.json:1000`：dp15登记，gate.kind包括stage-confirm/stage-close/stalled/budget-exhausted/goal-change/xkey-authorize；现有问题gate_decision。
- `packages/multi-workers/decide_registry.json:1354`：dp20登记，问题stage_action，现有选项close/hold/rework。
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts:1`：人工answer writer说明；读取全文，已有answerGate写入status及审计字段，不负责创建gate。
- `.agenticdoc/_arch_snapshot.md:31`：文件驱动协调资产；`_pitfalls.md` P-005/P-009/P-017/P-023：生产字段写侧缺口、有界失败处置、全仓formatter越面、fixture掩盖生产创建缺口。

## 发现
- 用户确认的是正式审核角色与独立交付，不是允许绕过机器硬门或扩大跨key权限。
- 登记中dp15包含stage-close，与dp20存在职责交叉；stalled与dp2任务处置可能交叉。需要生产链取证后联合定义，不能直接删gate.kind或改既有行为。
- dp7登记问题是原因分类；完整失败处置的材料与动作尚待设计。
- 初步证据来自用户输入与已读取的生成表/answer writer，不是25DP完整运行审计；登记行号会漂移，应按DP id/符号复查。
- 四门均不能只增加问题或界面而无真实producer、消费者和审核结果写入路径。

## 结论 → 决策映射
支撑spec §1范围和职责、§2授权边界、§4重叠风险。完整运行能力盘点与现有autopilot边界尚未完成，依照evidence/parallel-analysis.md的RQ拆解；不据此宣称实现或验收通过。

## 本轮命令口径
旧key audit_phase输出design/plan/tasks/execute PASS；仅为工作流审计。一次update_index claim --help被当成非法key拒绝，未创建claim；组合rg命令未保持目标范围，其输出不作运行盘点证据。没有派worker、真实决策请求或业务执行。
