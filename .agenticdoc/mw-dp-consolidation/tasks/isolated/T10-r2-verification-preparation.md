---
type: coding
logical_id: T10
execution: worker
deps: [T03, T04, T09]
---
# T10 R2阶段C：独立行为复验准备（当前产品全部只读）

## 上下文
项目目标 `.agenticdoc/goal.md:5`；原T10卡 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`（原AC/VC/验收全保留）；当前 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py:1974`、`decision_lifecycle.py:415`、`test_decision_context_lifecycle.py:1404`。
原36逻辑任务/7stage/DAG/预算不变，本卡只是同T10分段TDD的独立复验准备，不是新37task或提前正式S6review。阶段A旧116+14items；PM两次真red130items各8F122P/focus8F6P在 `evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/`。
阶段B `dpc-t10-r2-product-repair@2026-10-28T06:51:39.278Z` 实际needs-clarification/end07:04:25.204Z/exit2，产品局部交付未验证；原Questions因before/after/diff/pm-red-read shell目标缺machine events，是真实ledger缺口，不修原报告/trace/parser/账本或假成功。PM已全文吸收报告/diffs并工具ack，字节范围核 `evidence/implementation/t10-r2-product-absorption-20261028/check.json`：1891mirror只有wire/lifecycle两获准产品变化、tests/live/14pyc/744旧证据保持；不当全历史无瞬态写或正式recovery-complete。
当前SHA wire `429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc`，lifecycle `73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5`，taskstate `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d`；tests stageA两SHA不变。PM本人全5文件EOF尚未完成，不冒称已读全。你本人必须全部当前产品与两tests/采用的runner及关联单源面读到EOF，不以before快照/AST代读取。

## 要求
1. 独立完整读当前3产品/2tests/原AC-VC与stageB真实diff、现受控pm-controlled四脚本到实际EOF；记录真实当前bytes/LF/逻辑行/读取范围，报告里原2265/1549等指before而非after须勘误，不修改原历史。pm-controlled runner/root的HERE.parents映射及最小环境/逐child guard/保护责任必须核清，不机械复制老冻结SHA。
2. 只写自己新 `rework-r2/verification-preparation/**`。全部product、现两tests、stageA/B/PM red evidence、live、OS只读；本人禁止pytest/collect/产品import/runner执行。机器仍无外部OS写面，人工PM fixture权限不授你执行。只-B纯AST/text/syntax无import校验，可写校验器并保完整log，所有工具文件都用write/edit显式canonical path（不能$e/shell Copy-Item/重定向未知目标造成新ledger缺口）。
3. 基于现pm-controlled审阅后的受控runner，在自己面生成新的 `run_pm_tests.py` 与guard/import-probe/preflight脚本；保留原red runner/全部artifact immutable。绑定实际当前3产品SHA及2test SHA，新的before/after镜像1891/14pyc/744旧evidence/live/产品/脚本保护，原2suite collect不得漏130items；总数可增加不锁116为总数。任何绑定应说明来自当前已读bytes，不把更新常量冒充行为PASS。
4. PM唯一fixture根仍 `C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification`。只允许PM在其下独占新label（已存在拒绝/不清理），所有scripts/logs/sentinels在新keyevidence；最小env白名单无provider/PI/worker/credentials、UTF8/-B/禁pyc/plugin/cache、子孙进程真实有效DNS/TCP/UDP/HTTP禁止、同一解释器-B无-S/-I/-E且guardenv继承/no-shell，实际isolated __file__核；不能把生产scope替代guard的非法sink。
5. 强化harness真实失败分支的可执行负控，但本人不执行：sitecustomize配置缺失/无法写sentinel必须解释器终止、前置产品/hash/scope条件或guard/import/collect失败必须在进入下一产品阶段前停止。具体目标用获批PM新label内假对象，不造活路径/连网络。不创建仓外脚本，保全raw日志再解析，rc不改写；sentinel应能对实际各Python子进程身份对应核查，而不是只看preflight一进程就声称所有child。
6. 生成自己证据内独立 `test_t10_r2_boundaries.py`（不修改原2tests），使用真实isolatedwriter/原锁/注入fake redactor及获批PM新basetemp，顶层imports明确实际模块路径，不shadow/stub/copied产品。只追加必要原AC050/052等既有契约的行为回归和合法对照，所有预期尚未执行，不能称green或confirmed缺陷。
7. 必要S1/S5边界：真实双writer同内容record_request（仅一次written、其余duplicate、首事实不覆盖）；真实不同choice/refusal→有效两不同事实可见但不是业务动作执行权限；S5受控交错两writer在各自precheck后竞争append锁，较旧after不得在较新记录后追加；所有thread/process错误收集可见/锁释放可核，不新timeout或触发外部effect。可用局部barrier包装入口调度，但真实生产append/guard必须运行，不fake锁/复制writer或sleep碰运气。
8. 特别核对幂等正控：同一event_id/同内容的早期executed，在更晚settled已记录后重放，是否应该仍duplicate/零字节而非被新after floor当新事件拒绝？先对原AC052/既有dedupe契约判定再写最小测试；这只是PM预测，尚未复现，不能造新单terminal/global唯一语义。若确为契约问题，写精确预期与根因提示，别在本阶段改product或弱断言。秘密before合法复述与实质不同/顺序/null[]拒绝，guard失败不得写失败sidecar或伪executed，均用真实writer。
9. 新证据tests必须由PM后续运行：runner原两suite/focus保持分开raw logs，再独立extra suite新的basetemp；给实际argv/所有collectednodeids/预期归属，不将stageB8原红预期绿当结果，不修改rc或把已知新红判PASS。原assignedsuite合同保留，附加边界不是删验收或正式L2全部完成。
10. S2/S6/S8未知和8.3未验保留，不引入全局ID唯一/单terminal/privatebuilder等新语义，不扩decision.py/live。若发现产品新red仅准备最小真实回归，交PM真测→下一原面writer，不自修。收口不做无关研究、改预算/timeout/模型/部署或第37逻辑任务。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/**

## 写入禁止面
其他一切。尤其3product/原2tests/旧stageA/B/pm-controlled及全部原证据/worker/card/state/DAG/live/14pyc/all OS（获批PM fixture亦不授本人写）/账本/配置/权限/预算/依赖/dist。禁未知shell写目标、%TEMP%重定向/删除/Copy-Item；新代码与log只显式write/edit在自己面。

## 验收命令
本人仅 `python -B <自己evidence纯AST/text校验器>`，不import产品/测试/runner。PM在你终态后独立审阅、完成当前EOF义务并在获批外部新label执行你交付runner：真实isolated cwd原 `python -B -m pytest -p no:cacheprovider -q --basetemp <新label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py`；另freshbasetemp执行证据extra test，网络/环境/保护同级。全部原stdout/stderr/rc保全，至少两次assigned/focus最终验证不减少。完整npm check归原T32 PM-direct。

## 改动历史
原红/阶段B原needs-clarification/exit2及shellmachine-gap保留，不生成recovery receipt或改旧记录。当前只有独立复验准备，不有绿测或T10handoff/S2通过；新增测试真实执行由PM下一段负责。

## 交付格式
最终回复与 `verification-preparation/report.md` 五节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`，表头 `文件`，每路径canonical且独立一行、包括全部新脚本/tests/校验log。给逐文件SHA/bytes/实际EOF、runner与old差异、原130及新增tests预计items、精确PM argv、预期与实际未运行区分；报告自己仅静态未import/pytest/OS写，产品未验证，不声称PASS/QG/全handoff/recovery-complete。PM吸收终态后ack，随后真实suite/边界判真伪。
