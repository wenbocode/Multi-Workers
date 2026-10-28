# T02 精确关联与安全生命周期基础

type: coding
ac_refs: AC-010, AC-012, AC-014, AC-016, AC-019, AC-020
vc_refs: VC-010, VC-012, VC-014, VC-016, VC-019, VC-020

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan `.agenticdoc/mw-decision-context/`。种子`packages/multi-workers/decision_wire.py:1288` lifecycle_event/production_scope与既有WireScope（按符号）；只读decision.py credential_snapshot、安全redactor与decision_history stage读契约。dp25强制intent/commit已撤回；本卡不实现签收或CLI。

## 要求
实现单一Python模块decision_lifecycle.py（或内部同名API），供T05 CLI和T03/T04消费调用；新记录meta含record_version2/logical_id/key/task_key可空/initiator_role/retry_of，不发model。安全创建record-start元事实保存版本/关联，新捕获失败仍是新记录，不按无wire算旧。不修改T01的decision_points，接线交T05及下游。
提供真实可调用生命周期writer：consumed收到、executed实际行动、settled本次处理结果、signoff实际文件成功；schema如需字段拓展精确添加，不把所有状态塞进自由文本；event_id锁内幂等，不按(decision,word)吞不同事件。公开值键/错误/长尾known-secret全边界；使用受管store安全写，不裸append绕锁/链接。返回失败值，无法读的失败不伪造已记录。能复用现受管存取就复用，不造中心调度/重型事务；错误sidecar只在确有必要时最小实现。
先行为RED再最小GREEN，必须实际生产writer创建→读取，手填事件只能reader单测。与T01独立，不读改其它卡文件。准确API发布含Meta和函数signature给PM/T05/T06。只实现设计，非阻塞細节报告，不滚动研究。
禁真实用户凭证，合成HOME配置+读前spy验证；无真实Jev/browser/build/install/service/commit。首写前保存允许面原文/hash/diff含untracked，保留旧dashboarddiff；大文件分页完整检查read≤120行，不反复dump。10分钟内写行为测试计划，避免无界研读。

## 写入允许面
- `packages/multi-workers/decision_lifecycle.py`
- `packages/multi-workers/decision_wire.py`
- `packages/multi-workers/test_decision_context_lifecycle.py`

## 写入禁止面
decision_points/decision_book/decision.py/decision_history/mw/decide_signoff及其它源码、旧测试、配置、真实凭证、pi核心、框架脚本、dist、锁file、其它key。若发现受管store确缺必要接口报告PM，不自行扩权。

## 验收命令
从packages/multi-workers运行`python -m pytest test_decision_context_lifecycle.py -q`；再`python -m pytest test_decision_wire_store.py -q`单文件（合成隔离检查读前spy）。日志完整保存，不全suite；相关类型/compile可窄运行。npm run check由PM稳定后统一，不worker全仓写格式。

## 状态
代码完成；局部验证通过（61/88/25 passed原日志PM回读，非PM独立重跑），T02 run/output/report全文吸收ack。RED1 collection不计；RED2只失败汇总缺trace，PM不追认完整test-first。T06 sidecar与record-start折叠、T05 CLI/签收是下游主任务，不新开碎修复。

## 改动历史
初派；decision_wire是旧dashboard untracked实现，先完整快照并精准扩展，不删旧设计intentional功能。无其它本keyworker写这三个文件。

## 交付格式
report.md含真实RED/GREEN时间/命令/exit/原日志、唯一API草案落地和可跑例子、event schema/安全路径/读取方式/错误语义、变更hash、下游接线和非阻塞债。自身evidence放workers/<task>/evidence，不写design/plan/pm-state。
