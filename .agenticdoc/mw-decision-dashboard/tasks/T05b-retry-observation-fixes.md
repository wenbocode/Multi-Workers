# T05b OOM后窄续办

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec/design；原卡 `.agenticdoc/mw-decision-dashboard/tasks/T05b-observation-fixes.md` 全文包含F1..7修复目标，权限以本卡为准。
- `packages/multi-workers/decision_points.py:3775` observation/step5（函数定位），`packages/multi-workers/test_decision_observation.py:1`已有前worker新增测试但尚未RED。
- workers/dd-observation-fixes/worker.log明确V8 heap OOM约4GB，PID52744已退出；trace最后05:56仅改test，源实现没写，evidence/runs/T05b-observation-fixes/baseline-acceptance.txt已存在。不要覆写旧证据。
- workers/dd-review-observation/report.md为唯一finding权威，T10b/T07c不同写面并行。

## 要求
仅继续原T05b F1 typed核心门、F2 book一致性/秘密、F4 snapshot written关联、F5 actor闭集及F3/F7更正；禁止重新漫游TS/全项目/全包验证。旧新增测试先完整读再运行，确认真实失败，不丢旧改动。立即保存当前points/book/test副本到本卡允许evidence，并先RED日志后实现，不因OOM缺证改报GREEN。
阅读必要文件完整但分页每次<=400行，不输出大批Get-Content/search/多套件失败到模型上下文。环境PowerShell用分号，禁bash &&/heredoc，多行脚本写本证据目录，绝对路径保存日志，测试完整日志保存文件，再read可控分页，不能尾裁当完整输出。优先快速baseline/new-test RED，checkpoint/report骨架先落盘。
做完限定修复跑原卡验收，保留所有25DP合法与非法零发送；其他生产者迁移债报告不造假事实。book循环import不可inline/dynamic import，必要纯校验提取到允许book/points模块。snapshot only written引用，actor闭集当前source一致。report清楚给T06契约。
本次不调整全局NODE_OPTIONS/共享服务/依赖。再发生OOM或环境崩溃停在报告，不自动循环重跑；PM接管/拆分。禁止全包pytest/真实模型/外网/build/commit。

## 写入允许面
- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_book.py`（必要共享纯校验）
- `packages/multi-workers/test_decision_observation.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-observation-fixes-retry/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05b-retry-*`

## 写入禁止面
- 其他所有源/测试/任务相位/旧worker报告证据/真实生产/凭证配置/dist/锁file。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_observation.py test_decide_run_authority.py test_decision_dashboard_contracts.py test_decision_points.py test_decision_book.py test_decide_sign_auto.py -q`。
root严格只读biome --error-on-warnings与其余check子步全输出，完整check越面风险明确未整跑，普通exit0含warnings不算清零。

## 改动历史
- 原dd-observation-fixes OOM失败已回读ack，测试部分修改保留；新task id新上下文仅续办，不改模型或共享服务，原权限串行转本卡。

## 交付格式
report四段，当前基线/实际RED/GREEN精确退出码日志、逐finding与API变化、旧测试吸收及剩余债。不要把修后mutant当实现前RED。
