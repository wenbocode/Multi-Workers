# T05 CLI envelope/feedback与最小dp25直接签收

type: coding
ac_refs: AC-008, AC-009, AC-010, AC-014, AC-019, AC-020
vc_refs: VC-008, VC-009, VC-010, VC-014, VC-019, VC-020

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan `.agenticdoc/mw-decision-context/`，尤其最新D005用户确认最小签收。种子`packages/multi-workers/mw.py:3945` _decide_sign/文件写4086后authority，`decide_signoff.py:340` state/verdict；行号以符号为准。
T02 done接口`.agenticdoc/mw-decision-context/workers/dc-t02-lifecycle/report.md:85`，decision_lifecycle.py可读不可写；Meta=record_version2/logical_id/key/task_key?/initiator_role小写pm/coding/research/review/unknown/retry_of；store生产路径decision-lifecycle.jsonl与test独立；record_start/consumed/executed/settled/signoff+event_id幂等。T01契约在实现、字段design固定，直接CLI接线可先做，不能越面改T01。

## 要求
- `mw decide run <dp-id> --stdin`安全读`{material,meta}`，调用前创建record_start，logical_id唯一关联真实decision_id与attempt，meta不发模型；重复同id已处理不得新模型发送，不按key猜。配置凭证snapshot冻结/typed/全局disabled/预算等门保持。caller角色unknown不冒PM，task空null。
- `mw decide lifecycle --stdin`统一读取`{meta,decision_id,dp,stage,action?,outcome?,reason?,answer?,result?,evidence_path?,evidence_sha256?,event_id?}`调用T02 record_*，reject未知字段和值不回显秘密；API返回`status,recorded,error_class,error_recorded`。读取后只是consumed，不自动执行/完成。T03/T04/T07需该CLI，早发布精确参数给PM，避免假stdin接口。
- dp25材料由PM四部分通过stdin提供，不旧计数替证据，不本地verdict预判完工再复述；必要链/来源/claim/材料/预算/安全写面门调用前保留。
- finalize无二批直接有效签收文件原子写/fsync/replace；包含logical_id/目标材料及证据快照，文件落地即成功，关联authority/反馈失败单列feedback_status，不把日志失败当签收失败。continue/user-confirm交PM实际补缺/待确认回执路径零签收。
- 保留这次选择与快照，已有持久结果不足才补最小结果记录，无强制intent/commit。写失败材料不变仅重试写，不重新调用模型；同次已签文件不重写字节/时间；新决策不key曾签自动跳过；模型期间相关材料/证据变更拒旧结论，显式需新判断。无可信结果读回拒猜最新。
- 建议明确`mw decide sign <key> --stdin`本地envelope带material/meta，重试显式`--retry-write <logical-id>`；根据现argparse语法适配后报告最终命令。禁止新增第二phase门/手改框架，签收与phase gate阻断分列。
- 有效签收校验提供可读无模型/无凭证的明确函数或文件schema给T06，精确同logical_id/snapshot，reader不得hash/id豁免父链安全。
正确行为RED→最小实现GREEN，签收故障/重复/材料变化为必要验收，不泛研究；孤立API stub通过不是整体证据。真实loopback POST仅合成tmp config+HOME等env清理/读前spy；禁生产凭证/Jev/browser/service/build/install/commit。签收全部tmp树非真实key。
首写完整快照允许面原文hash/diff，保留旧dashboard和已有signoff-only行为中不被批准设计替换者。大文件分页完整读≤120行，禁止滚动研读，10分钟内RED计划。

## 写入允许面
- `packages/multi-workers/mw.py`
- `packages/multi-workers/decide_signoff.py`
- `packages/multi-workers/decision_signoff_result.py`
- `packages/multi-workers/test_decision_context_signoff_cli.py`

## 写入禁止面
lifecycle/wire/points/book/history/monitor/TS/其它测试/decide_archive/框架脚本/配置/dist/依赖锁/真实凭证/其它key。必要扩action常量报告PM一次认领，不越面。

## 验收命令
`cd packages/multi-workers; python -m pytest test_decision_context_signoff_cli.py -q`（tmp credentials env isolation）；真实argv/stdin Python调用与loopback capture必须faux/test backend且生产树字节不变；既有signoff定向测试可跑，旧断言坐标报告PM不越面追绿。原日志完整UTF8，含UTC/cmd/exit。npm check PM稳定统一，禁npm test/build/full vitest。

## 状态
代码完成/局部47P日志验收通过，PM全文report/output/run回读ack；T02联合149P日志0已核，3subprocess真实loopback由worker测试证明，PM尚未独立复跑。框架finalize词表不兼容是结案阻塞非非阻塞；旧默认sign入口失效/历史有效文件/失败关联集中T08接线，未改框架。

## 改动历史
初派；T02已交付61/88/25P，T01在运行；本卡独占CLI/signoff，早接线独立部分。dp25强制intent/commit撤回，不恢复。反馈reader归T06，不能以sidecar写了就冒称页面已呈现。

## 交付格式
report.md+自身evidence行为RED/GREEN/HTTP故障日志/hash与快照；CLI命令和stdin/output精确schema可跑例子，T03/T04消费与T06签收无凭证校验接口，签收/反馈状态分列。源码局部/真实HTTP/faux/平台未验分列，非阻塞债集中报告不另研究。
