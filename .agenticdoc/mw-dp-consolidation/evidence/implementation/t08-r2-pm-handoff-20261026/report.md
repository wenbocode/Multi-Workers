# T08 R2 PM 独立复验与终态处置边界

## 结论

当前有界R2产品边界通过独立局部复验，但`semantic_handoff_verified=false`：worker真实`needs-clarification/exit2`的账本恢复尚未获得具体处置。保留原run/output/trace/账本，不以报告done、ack或110绿测改写终态，不派T09及其后继。

## 证据

- `check.json`：2026-10-27T03:49:42.444042～03:49:47.027931Z，copy-bound/network-poisoned bootstrap指定suite110passed0.60s/rc0；literal指定suite110passed0.69s/rc0；39个PM断言fixture全部通过。
- cap1返回budget-exhausted且0HTTP/0business decisions，额度仍1；合法cap2与bool miss正常单次两问，bool hit零请求；八类nonbool失败关闭；25旧ID在replay前拒绝。
- 非适用basis为业务bad-response/0business decisions，同时原transport available=true记录仍保留；并不证明有效业务决定写入。backend原bytes不变，REASON_CODES/_EVIDENCE_FIELDS/_PREPARED_RESULT_FIELDS AST不变，DecisionClient只有request_prepared方法AST变化。
- 23个原测试函数AST保留；1883镜像验收零净改动，125原worker证据与73个R2证据文件hash保持；14pyc原bytes不变，三相关live路径保持基线。
- `ledger-probe2.json`：本地只读diffLedger把output表头内副本目录误认写入声明，extra=[packages/multi-workers]；仅内存去掉该目录文字则extra=[]；实际worker证据report的ledger也extra=[]。未写报告/parser/run；不证明运行时加载版本或所有瞬时写入作者。

## 改动清单

Worker原面修复prepared question cap异常与strict bool replay，新增37参数化case；backend未改。PM新写check/bootstrap/私有fixture/bytes/diff与本报告，没有产品、live或运行账本修复。

## 残留与未验证

- 真实run `dpc-t08-transport-r2@2026-10-26T15:52:28.169Z`仍needs-clarification/exit2/已ack，body自称done不能覆盖。原WRITE_UNRESOLVED/自动dp3 input-incomplete保留；只读误解析复现不是合法运行恢复或忽略guard的授权。
- 需用户具体决定是否接受上述报告表头误解析为带遗留处理项，允许以PM独立证据完成局部交接并继续原T09，而不修改原终态/parser/账本、部署或预算。未获具体处置前不放行。
- 原DAG核对：T09依T08，T10依T09；不能把T09/T10当独立ready并行派发。T05也依T09，S3依整S2。
- 初始ledger probe报告载体猜错rc1和本轮preparer把RETIRED_25误当AST literal的rc1均保留；后者发生于产品import/pytest前，不是产品red。workerUTF16LE diff/red原字节保留，PM另产UTF8 diff。
- T10实际业务store、T23 CLI active-before-replay/strict-bool seam、真实凭证/HTTP、human/H12、锁/effects、TS/L2/完整check/审计/QG/签收均未验。当前边界读取与AST核对不冒称重新完整EOF/全仓审计。
- 14pyc清理另需授权；全历史/全live瞬时无写或独占作者未经证明，旧dp4不可用不重问/不绕桥。

## 上下文来源

用户原有界R2批准及隔离卡、原T08反例、pre-dispatch1883基线、worker原run/output/trace/report/红绿；PM本目录check/probe与ledger-probe2为新局部证据。目标53AC/VC、36-task原DAG、禁止面不变。
