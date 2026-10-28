# T01 四DP简洁契约与model投影

type: coding
ac_refs: AC-001, AC-002, AC-003, AC-004, AC-005, AC-007, AC-017, AC-020
vc_refs: VC-001, VC-002, VC-003, VC-004, VC-005, VC-007, VC-017, VC-020

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan位于`.agenticdoc/mw-decision-context/`，必须读dp2最新修订和签收最小方案。源码种子`packages/multi-workers/decision_points.py:443` _state_builder/decide_for/registry（符号锚定行号可能漂移）；decision_backends.py真实state透传只读。RQ1研究字段上限/改dp2标签方案已撤回，最新design优先。

## 要求
实现批准四DP业务schema+唯一model allowlist投影，identity留本地，实际发送不带审计。dp1一问三类型说明按用户定义；dp2原registry问题instructions/choices/labels保持不变，材料三任务原文+pm_decision_background、可选worker_execution，无worker自评合法；dp3四背景+针对问题处理候选{id,label,description}，只一原生动态选择；dp25四部分不计数代证据。字段按plan固定命名，保留其余21DP。
先写行为测试并实际正确RED，再最小实现GREEN；collection/import失败不是RED。生产decide_for/backend路径证实payload，不手填假writer。缺材料/预算/typed拒零HTTP，必要字段不截断，不引任意字段限额。现2000B若合法完整case不足，明确报告预算证据而非改需求，T07完整case负责后续整体验收。
导出registry JSON/TS/template只由本卡生成，不手改TS生成物。保留当前工作树外来diff、不回滚旧dashboard。无需修改decision.py/transport/CLI/meta事件（T02/T05）。凭证snapshot门和安全脱敏保持，不读取真实用户凭证，测试必须tmp HOME等合成配置+读前spy，不真实Jev/浏览器/服务/安装/构建/提交。
首写前保存允许面原文和hash/diff到自身evidence（untracked也保存）；大文件分页完整检查，read≤120行避免dump回灌，输出卫生不限制npm check完整日志。10分钟内至少产出行为测试RED计划，不无界研读。只实现设计，非阻塞细节集中报告，不自行扩矩阵。

## 写入允许面
- `packages/multi-workers/decision_points.py`
- `packages/multi-workers/decision_book.py`
- `packages/multi-workers/decision_context.py`
- `packages/multi-workers/scripts/gen_decide_registry_ts.py`
- `packages/multi-workers/decide_registry.json`
- `packages/multi-workers/decide_book_template.json`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts`
- `packages/multi-workers/test_decision_context_contract.py`

## 写入禁止面
其它源码/测试/配置、框架脚本、凭证、pi核心、依赖锁、dist、其它key。邻接测试旧断言失败报告坐标由PM分配，不越面追绿。

## 验收命令
从packages/multi-workers运行`python -m pytest test_decision_context_contract.py -q`，合成隔离+读前spy；再相关旧registry/decision_book单文件检查，记录旧断言变化交PM。
Python compile+TS生成物类型检查可定向，npm run check由PM稳定时统一运行，禁止worker全仓biome --write。不得npm test/build或全vitest。

## 状态
代码完成/局部验证通过；PM全文回读report/output/run，原RED/GREEN已转UTF8副本可读，42P exit0/生成检查0，ack。四真实Agent生产路径/T07完整case仍待下游，不追认整AC。

## 改动历史
初派。现工作树有旧dashboard及其它会话diff，全部保留；本卡只改四DP及其投影/schema生成物。主测试新文件防冲突。

## 交付格式
report.md包含行为RED/GREEN原日志路径与UTC/exit、具体API/字段闭集、生成命令、变更文件hash、下游需迁移坐标、非阻塞债；按design版本注明dp2问题没改。接口发布给T03–T07，不实现它们的producer/CLI。自身证据放workers/<task>/evidence，不改PM相位文档。
