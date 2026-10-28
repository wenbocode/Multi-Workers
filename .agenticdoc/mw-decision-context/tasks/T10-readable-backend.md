# T10 可读事实与完整测试请求后端

type: coding
write_face:
  - packages/multi-workers/decision_points.py
  - packages/multi-workers/decision_history.py
  - packages/multi-workers/decision_monitor.py
  - packages/multi-workers/decision_playground.py
  - packages/multi-workers/scripts/build_decide_cases.py
  - packages/multi-workers/decide_cases/dp1.json
  - packages/multi-workers/decide_cases/dp2.json
  - packages/multi-workers/decide_cases/dp3.json
  - packages/multi-workers/decide_cases/dp25.json
  - packages/multi-workers/test_decision_context_history.py
  - packages/multi-workers/test_decision_context_contract.py
  - packages/multi-workers/test_decision_context_readable_backend.py
  - packages/multi-workers/test_decision_monitor.py
  - packages/multi-workers/test_decision_dashboard_playground.py

## 上下文
目标.agenticdoc/goal.md:1；批准增量evidence/design-workbench-readable-revision.md，spec AC015修订/021～024。packages/multi-workers/decision_history.py:2414；decision_points.py:5200低置信度；decision_monitor.py:1926观察validate/submit；decision_playground.py:689。实际记录evidence/dag-live-acceptance-20261023.md，HTTP200 confidence0.62<threshold0.70但UI看不出。

## 要求
完整读全部拟改文件，首写前保存允许面原始bytes/hash/git diff，精确UTF8 edit，保共享dirty。先真实行为RED后最小GREEN。
后端独占本卡路径；前端worker并行写html/js/css与workbench/assets/contracts测试，不改其文件。
1. 本次生效阈值入实际持久决策事实并由history提供可读policy_result，建议{reason,selection,confidence,min_confidence,disposition}。不降低策略，不把HTTP200叫API失败；旧记录无阈值显式未知，不读当前阈值补猜；existing detail如精确记录可用。
2. input节点提供material（仅安全化实际book快照state业务内容）；保必要底层事实，不删安全标记、不扩大known-secret输出。
3. 四离线case含完整原生questions，case shell新增questions；scaffold/validate与case可提供默认问题及最终request_preview={model,state,questions}。validate API允许观察questions可选，submit同字段。questions仅测试覆盖不写生产；严格合法type/instructions/criteria、DP问题映射/选择允许集、原生解析，typed材料/8192B/预算门不绕过。不恢复legacy审计state。dp3 state.handling_options唯一候选源生成完整criteria，questions候选冲突显式拒绝或一致规范化且preview/实际发送一致。
4. validate(dp,book,questions=None)；submit request可携questions，未传保持原功能；server preview复用实际payload builder，不另造模型请求；预览不调用模型。
发布接口到自身progress.md供前端读；未知先报告，不越面。
隔离synthetic HOME/auth/随机端口loopback，真实 edited questions HTTP断言、生产树字节不变、安全secret覆盖。不得真实Jev/provider/browser/build/install/commit/framework/service操作。只跑指定测试，不全pytest；不要为绿删安全测试。

## 写入允许面
packages/multi-workers/decision_points.py
packages/multi-workers/decision_history.py
packages/multi-workers/decision_monitor.py
packages/multi-workers/decision_playground.py
packages/multi-workers/scripts/build_decide_cases.py
packages/multi-workers/decide_cases/dp1.json
packages/multi-workers/decide_cases/dp2.json
packages/multi-workers/decide_cases/dp3.json
packages/multi-workers/decide_cases/dp25.json
packages/multi-workers/test_decision_context_history.py
packages/multi-workers/test_decision_context_contract.py
packages/multi-workers/test_decision_context_readable_backend.py
packages/multi-workers/test_decision_monitor.py
packages/multi-workers/test_decision_dashboard_playground.py

## 写入禁止面
其他源码/测试/配置、TS及生成registry、html/js/css、framework、dist、锁文件、其他key；自身worker证据由角色机制写，不手改PM文档。

## 验收命令
逐文件python -X utf8 -m pytest -q packages/multi-workers/test_decision_context_readable_backend.py及本卡修改的已有测试。完整UTF8 stdout/stderr/UTC/argv/cwd/exit记录；先RED后GREEN。

## 改动历史
2026-10-23 用户确认工作台精简/十节点图/完整questions并授权实施；首轮本卡，未授权额外真实调用。

## 交付格式
自身report.md/progress.md/evidence原文hash/diff与完整RED/GREEN；接口实例及测试出处、未覆盖面，不用通过数量代行为；report必须含## 结论、## 证据、## 残留与未验证、## 上下文来源。
