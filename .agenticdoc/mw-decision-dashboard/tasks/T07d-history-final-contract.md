# T07d 历史筛选回显与状态契约收口

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/016/design §9。
- `packages/multi-workers/decision_history.py:541` HistorySnapshot.page filters/:845 capture omission/:996 empty-key omission。
- workers/dd-review-history-output/report.md全文：T07c核心PASS，P2-a/b、P3-a/b；T07c已终态，当前本卡唯一history/test写者。

## 要求
完整读history/test，保存当前未修基线副本+hash到本证据。先新增测试跑真实RED再实现GREEN。
P2-b：HistorySnapshot携带注入redactor，page筛选逻辑仍原值，公开filters过同输出策略命中secret省略（None，不改有效筛选），page(key=SECRET)仍total1但filters.key None。dp/status/source/task等所有筛选输出统一处理；新增诚实filter省略标记/说明（不把secret塞label），无回调保持已定义契约。不得把monitor二层当免责，history即可修不要争写monitor。原page记录结构与opaque/join不变。
P2-a：文档一处明示capture_status/stored_len/sha描述存储，text_omitted/byte_exact描述本次输出副本；锁定测试存储ok+输出textNone的语义，不改历史存储事实。若需要新增输出状态字段请选择闭集显式output_omitted，不误导UI仅用ok推完整。
P3-a空映射键被丢弃计入omit/drop而不回显；P3-b HistoryRecord docstring明确原属性内部raw，只安全序列化as_dict/page给消费者。
完整page输出（包含filters）known-secret出现0，结构/自由文本/capture原回归不退化，重复序列化稳定；合法过滤值不裁剪、不改结果。
无真实生产修改/凭证/外网/服务/browser/build/commit。避免全项目大读取/全包重跑。

## 写入允许面
- `packages/multi-workers/decision_history.py`
- `packages/multi-workers/test_decision_history.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-history-final-contract/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T07d-*`

## 写入禁止面
- monitor/points/book/store/其他源测试/旧报告/任务相位/真实档案/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py test_decision_monitor.py -q` 全日志/exit，依赖哈希快照注明。严格只读biome --error-on-warnings及其余check子步明确未整跑完整check，不以分拆等价完整。

## 改动历史
- PM已ack T07c复审，核心closed；filters known-secret回显不能因披露自动豁免，精确小卡收口2P2+2P3，不修改生产载体。

## 交付格式
report≤100行，实际RED/GREEN/完整page原值0、状态层次测试/API变化/未覆盖；不自报AC/reviewPASS。
