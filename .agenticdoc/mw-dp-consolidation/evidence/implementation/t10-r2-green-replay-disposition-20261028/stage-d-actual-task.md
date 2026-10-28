type: coding
images: no
card_path: tasks/T10-r2-replay-repair.md
card_sha256: 512796236decacca0e6b773b6de68453736be22f00f2b975900b9732623bc608
envelope_producer: agent-team-loop-pm@0.83.0
write_face: .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py, .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py, .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/**

<!-- mw-dispatch-card: v1 -->
## 上下文

项目目标 `.agenticdoc/goal.md:5`；原T10 `.agenticdoc/mw-dp-consolidation/tasks/isolated/T10-lifecycle-state.md:35`，原36tasks/7stage/DAG/AC/VC/预算/timeout均不变，本卡仍原T10分段TDD重修，不是第37逻辑task/扩大目标/新授权。
真实产品 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py:1070` 与 `decision_wire.py:1980`；真实回归 `.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-postfix-tests/test_replay_probe.py:21`。
阶段B原needs-clarification/exit2，阶段C `dpc-t10-r2-verification-preparation@2026-10-28T07:09:46.792Z` 实际end07:24:46.085Z/needs-clarification/exit2，均完整报告回读并tool ack；shell/静态器写两个JSON缺machine events是真实ledger-gap，当前byte-envelope可核但不是正式recovery-complete，历史/trace/report/parser/exit保持不动。
PM本人现在已实际当前3产品/2tests全部EOF，并审阅新PMrunner/guard到EOF，先读后真实测试（不回填以前red的顺序偏差）。本次 `.agenticdoc/mw-dp-consolidation/evidence/implementation/t10-r2-green-replay-disposition-20261028/check.json`：PM新受控两次原assigned130passed、focus两次14passed、preflight/import/collect/pytest/focus rc0/protections相同；随后独立真实AC052最小probe **1 failed/rc1**，不是预期而是观测，raw stdout/meta在 `rework-r2/pm-postfix-tests/runs/t10-r2-replay-probe-first/`。
真实红：09时executed已记录event_id，同一args之后10时settled也记录；再次调用09时原executed同event_id被 `record_lifecycle -> _recorded_after_floor` 在进入append之前抛LifecycleInputError，无法到达duplicate/零字节；wire内部guard也排在dedupe前。原契约按event_id幂等，重复已有事实并不是追加较旧新观察。
阶段C独立16item边界套件仅准备/预测15green1red，未执行；其runner/guard/static_verify未PM全部EOF/未采用运行，别称PM已跑全部16或独立全qualification。PM只采纳已实际自写probe红为本修复依据，阶段C原报告边界测试全部只读后续再真验。

## 要求

1. 先完整当前3产品/原2tests/实际本卡与PM红绿证据/根因契约到EOF，记录实际范围。产品当前SHA wire `429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc`、lifecycle `73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5`、taskstate `b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d`，tests原 `1bca28c5…/30c6e4dd…`不变。对照PM freshbefore，取自己before/after/diff/static evidence，不重复业务设计。
2. **只修已实际复现的AC052幂等与S5新观察时间floor的顺序冲突。** 已存在event_id的合法同内容原事件，即使后来有更新的after，也应duplicate/zero新增字节/不覆写/不error-sidecar；未知/新event_id+较旧after仍必须fail closed。去重与新写入floor最终判断都在原同一append锁内，不能read-before-writeTOCTOU、newlock/secondledger/new scheduler或缩短旧预算掩盖。
3. 保留原association/task-before合法性与结构校验、secret零原文、真实`_ledger_facts`损坏检测、元数据null≠[]/顺序、合法新观察/failed-round与锁释放。判断并修正预检查与锁内guard先于dedupe的问题；可以重新安排检查而非移除S5功能，但不得简单禁guard、给旧观察新ID、篡改timestamp、改tests/固定knownIDs或把所有after都放行。返回duplicate始终指原记录事实，不升级业务批准/执行/terminal权限。
4. 原T22 `test_duplicate_after_write_does_not_replace_first_snapshot` 的event-id幂等语义保留，原116+stageA14全部断言/源码/tests SHA不动。不要为了本case发明content-equality拒绝旧duplicate/globaldecision_id唯一/singleterminal/privatebuilder等新S2/S6/S8语义；记录after的表示/红actor/S1content-address request/S3dynamic候选/S4case guard修复均保留。未确定的secret等价类与8.3仍未验，不偷改decision.py或协议。
5. 实施仅三个原产品面（预期wire/lifecycle、taskstate如无必要不改），原tests与stageC/PM probes全部只读。所有验证必须PM真实执行；本人 **不得pytest/collect/import产品/测试/runner/任何OS写**，包括获批PM根也不授本人写、%TEMP%重定向/删除/Copy-Item。只-B纯AST/text校验，可用显式write/edit写自己面脚本/log，但不写生产pytestfixture或调用fake scope逃guard。
6. 本人新证据全部显式canonical工具write/edit目标，禁$e/变量shell重定向/隐式JSON落盘导致新机器ledger缺口；校验器若需结果JSON由本人read返回内容再显式write，纯checker stdout直接tool结果，禁止使用shell写未知目标。不是修活机器账本，历史原gaps不补。
7. 收口给精确改动/锁顺序/去重与新观察floor仍串行理由/损坏与失败分支、before/afterSHA及原测试不变。不称green/修复完成/T10handoff/S2/QG/signoff。PM终态后先独立EOF/diff/SHA/protection，再新runner绑定afterbytes，原130/focus两次、AC052probe及完整stageC16边界真实运行；原130绿仅本轮历史，不作你postfix证据。

## 交付格式

reply + `replay-repair/report.md` 五节：结论、证据、改动清单、残留与未验证、上下文来源。表头`文件`、每canonical path独立行，包含全部新checker/logs/copies/diff。准确当前EOF/原testSHA/3productdelta及锁内执行次序/代码与观察分开；所有执行未验证明确无pytest/import/OS写，不能把static67或旧130P当本postfix验收。PM吸收终态ack后独立真测。

## 写入允许面

- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_wire.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_lifecycle.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_task_state.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/**

## 写入禁止面

除此全部只读：原tests、stageA/B/C、pm-controlled/pm-postfix-tests与全部旧红绿/probe证据、live/cache/worker/state/DAG/ledger/config/所有OS/预算/模型/依赖/dist。禁实际决策/HTTP/provider/服务/CLI/liveeffect/重启/安装/commit、禁止借production scope绕测试scope守卫。

## 验收命令

本人仅 `python -B <自己显式面内纯AST/text校验器>`，无产品import/pytest/fixture。PM后续获批新label、最小env/UTF8/-B/no plugin/cache/真实子孙护栏：真实isolated cwd原 `python -B -m pytest -p no:cacheprovider -q --basetemp <PM新label>/pytest-basetemp test_decision_context_lifecycle.py test_decision_task_state.py` 两次+focus；独立真实AC052 probe→绿色、stageC全部16并发/新旧观察/secret/guard controls→实际结果，不删/skip/xfail/弱断言，不把预期rc1算通过；npm check原T32。

## 改动历史

阶段B/C原needs-clarification/exit2/acked/gaps完整保留。新PMgreen two130P/focus14P、probe1F与实际UTC/raw logs在新证据目录；PM freshbefore1891mirror/14pyc/744旧证据/live5/所有B-C-PM artifacts保护。此卡机器4面与正文一致，写入历史由真实工具产生不补造。[WRITE_FILE]覆盖显式新证据目标。

## 交付段契约（本角色）

本角色（type: coding）的恢复契约段：report.md / output.md 必须按下列标题成节（可直接复制；缺任一段即 settle 判缺失）：

- `## 结论`
- `## 证据`
- `## 残留与未验证`
- `## 上下文来源`
- `## 改动清单`

以上为种子，不是探索上界；可自行检索补充上下文
<!-- /mw-dispatch-card: v1 -->

继续原T10分段TDD阶段D，只修已真实PM复现的AC052重放1F：同event_id早期executed在后来settled后再次原调用，被record_lifecycle的floor precheck以及wire guard-before-dedupe拒绝。PM当前5文件/新受控runner/guard已经本人EOF读完，原130套件两次真130P，focus两次14P，另真probe1F/rc1，完整raw日志和freshbefore在卡。保持event-id duplicate零增量、不覆写、无sidecar；新ID旧after仍严格拒绝，去重与新写入floor同原append锁内无TOCTOU，association/secret/metadata/原S1S3S4S5全部不弱。禁止新S2/S6/S8/globalID唯一/单terminal语义或改tests/decision.py。唯一4面3原products+自己replay-repair evidence；本人禁pytest/collect/import产品/测试/runner/所有OS写，仅-B纯AST/text；所有新证据用显式write/edit canonical目标不变量shell/隐式JSON落盘。B/C真实needs-clarification/exit2/acked/机器gaps保留，原红绿及C全部artifact immutable。不称postfix已绿/handoff/S2/QG；终态PM再新SHA runner双原suite/focus及probe/C16全部边界实测。先阅读全文EOF、最小根修复，五节规范报告精准完整变更清单。
