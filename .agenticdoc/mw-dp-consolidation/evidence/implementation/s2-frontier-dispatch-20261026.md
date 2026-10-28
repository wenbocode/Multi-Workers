# 原S2 frontier实际派发及终态收集

## 结论

原DAG T06/T07/T08于12:08:35Z正常dispatch（pi/coding、dispatch.yml默认timi/deepseek-v4.1-flash，无pin/images=no/allow_foreign_write=false）。实际run/task全文回读确认下表，非准备状态；前轮记录因三个异步终态插入而中断，现补记真实派发事实。不更改原7stage/36task、53AC/VC/预算/授权。S1是plan技术wave前置，非live autopilot stage关闭。

|逻辑任务|run_id|PID|实际ended_at|exit|
|---|---|---:|---|---:|
|T06|dpc-t06-validity@2026-10-26T12:08:35.978Z|1872|2026-10-26T12:20:16.189Z|0|
|T07|dpc-t07-policy@2026-10-26T12:08:35.966Z|76360|2026-10-26T12:17:46.874Z|0|
|T08|dpc-t08-transport@2026-10-26T12:08:35.871Z|67744|2026-10-26T12:20:09.756Z|0|

## 证据

- `evidence/implementation/s2-frontier-pre-dispatch-20261026/check.json`：12:06:56.147195Z freshbefore；三exact产品面零交叠，1864普通副本；五newfile不存在；T08两existing bytes/live-before/non-samefile/diff已留底。
- 全文实际seed `workers/dpc-t06-validity/task.md` / `workers/dpc-t07-policy/task.md` / `workers/dpc-t08-transport/task.md`：sha分别`1a81029454f59cf2e69c32643f30735efa0827c482f382ca8879c02ef37df15c`、`88bee76800c724909e277485117335cf91d93e989ccc6d9fb09d4e9d99adeb5d`、`07a719095a33f60666fef960ec89034ff96f81066bf7bea599f303178290b1e8`与实际isolated卡相同，exact写面及业务seed一致。
- 仍存在追踪label缺陷：三seed `card_path: tasks/T06-validity.md`、`tasks/T07-policy.md`、`tasks/T08-transport.md`省略`isolated/`；实际调用入参均`tasks/isolated/...`。不改live框架/原seed，不把相等hash代label正确。
- 三`run.json`真实done/exit0，report/output全文吸收，工具分别返回`Acked 1 task(s): dpc-t07-policy.`、`...dpc-t06-validity.`、`...dpc-t08-transport.`。ack不是语义验收。worker声称T06 65、T07 31、T08 73通过，此处只吸收报告；本轮PM独立仅复验T07。
- `evidence/implementation/t07-pm-handoff-20261026/check.json`/`supplement.json`：T07 fresh31passed，但纯判断反例发现阻断，handoff=false。T06/T08产品尚待PM独立完整源码/测试/反例复验，handoff未成立。

## 残留与未验证

派发只各exact产品面及自己的证据。所有import也必须-B/禁pyc，禁止live源码/HTTP/CLI/service/config/grant/gate/ledger、build/install/check/restart、预算/watchdog/timeout/commit；同步写面disjoint不证明完全不存在人工writer。遇新增peer读取依赖须PM协调，不改DAG/复制模块。T07仅纯判断，不证明H12身份；T08仅传输层不证明T23全入口replay；T06仅纯事项判断非锁/效果L2。

T08自报20:16:49未守禁pyc的python-c产生14pyc，删除被scope守卫拒绝。PM核1883副本相比1864前置，七授权产品面变化以外14pyc确实存在；T06/T07的peer归属推断及T08自报保留，不代独立进程独占归因。未授PM删除权限，不删除/抹历史、不声明clean/never-wrote。T07定点返工及精确cache清理须具体授权；此记录未派新的尝试、未取消/重置旧任务。T05/T09/T10等仍待真实交接，不关闭S2/phase/L2/QG/签收。

## 上下文来源

用户原计划执行及隔离批准；三原isolated卡与已批plan/design；T03-R3及T04-R2 PM局部handoff；新frontier基线；三实际工具dispatch/readback/ack、run/output/report；T07独立复验。历史dp4UNAVAILABLE/input-incomplete/meta.task_before无有效id/receipt保留，不重问原失败/绕桥，不凭普通dispatch宣告故障已修。
