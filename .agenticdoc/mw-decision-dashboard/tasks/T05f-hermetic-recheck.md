# T05f 凭证隔离修复与复验

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design §9测试合成凭证隔离。
- `packages/multi-workers/test_decision_observation.py:228` fixture；`test_decide_run_authority.py:74` _hermetic。
- workers/dd-review-book-known-secret/report.md全文N3与隔离复验建议；T05e原F1/F2/F3独立PASS已ack但验收非hermetic。

## 要求
只改两个测试的隔离fixture，不改任何业务断言/生产源。完整读测试，先保存基线/hash，新增/修改fixture防step6b默认读取真实auth.json：patch decision_backends._auth_json_path到tmp/no-auth.json，清理真实凭证后缀环境变量，必要HOME/USERPROFILE子进程重定向tmp。保留每用例自己注入合成值的能力。
先用合成sentinel/spy证明未修fixture解析会访问非tmp默认路径，不读取真实文件（spy在read前拒绝），保存正确RED，再改fixtureGREEN；不可用真实文件读来证明隔离。写测试自身安全隔离检查放允许文件内。所有验收均用外层HOME/USERPROFILE临时隔离，禁止读取真实用户凭证。
复跑T05e验收和窄adjacent，记录命令/exit/hash前后，不能覆写旧日志；报告旧acceptance/adjacent不hermetic只被新时点替代，不追认旧违规。无业务功能改变。
禁止production/ref/placeholder/secret实现/registry变更，不外网/模型/共享服务/browser/build/commit/全包pytest。必要源全文分页避免OOM。

## 写入允许面
- `packages/multi-workers/test_decision_observation.py`
- `packages/multi-workers/test_decide_run_authority.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-hermetic-book-recheck/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05f-*`

## 写入禁止面
- 所有其他源测试/旧报告证据/任务相位/真实用户凭证/生产记录/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_book_known_secrets.py test_decision_input_contract_migration.py test_decision_observation.py test_decision_book.py test_decision_dashboard_contracts.py test_decide_run_authority.py -q`，额外隔离检查增测试数量须说明；adjacent按T05e档案真实列表窄运行，外层HOME隔离。
只读全仓biome --error-on-warnings及check子步，完整check未整跑明确不等价。保存全输出不得tail。

## 改动历史
- PM吸收T05e PASS，N3隔离违规独立修复；CLI双读TOCTOU另债不在本卡。P1empty待用户确认。

## 交付格式
report≤100行，RED安全spy/GREEN/新hermetic验收指标、未读真实凭证证明、依赖hash/剩余，不声称全AC或T06放行。
