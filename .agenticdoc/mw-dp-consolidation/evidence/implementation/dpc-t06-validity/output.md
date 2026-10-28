# T06 output（dpc-t06-validity）

## 结论

status: **done（代码完成，局部纯判断验证通过）**
key result: 新增 `decision_validity.py` 只读事项/实质版本/授权/证据/claim/重放判断，assigned 测试 **65 passed / rc=0**（隔离副本，两次一致）；red=63 failed/1 passed（stub）、green 一致。非 L2、非真实并发/锁/效果对账，非 S2/QG/签收/运行切换通过。

## 证据

- 验收命令（cwd=`implementation-worktree/packages/multi-workers`）：`python -m pytest -p no:cacheprovider -q test_dp_consolidation_concurrency.py` → rc=0，65 passed；日志 `green-06-final.log`、`green-07-final-rerun.log`、`green-09-verbose.log`（逐条 PASSED）。
- red/green 全序列与 rc：`red-01` rc=2（模块缺失）、`red-02/03` rc=1（63 failed/1 passed）、`green-01` rc=1、`green-02` rc=1（自身测试/实现缺口）、`green-03..09` rc=0。
- before：两文件真实不存在（`baseline/before.json`，与 isolation baseline `existed:false` 一致）；卡 SHA `1a8102…`，envelope 卡 SHA 一致。
- 写面：`write-scope.json` 1864→1883，`own_changes` 仅 2 文件，`unexpected=[]`；其他 5 个产品文件属并发 T07/T08，14 个 pyc（20:16:49）为他人运行产物且不含本模块。
- VC 映射/可观测值/limit：`assertions.json`（VC-011/019/025/027/028/029/039/052）。
- 终态字节：`decision_validity.py` 54353 B `64b9b9e1…c049eb1`（LF 1652）；`test_dp_consolidation_concurrency.py` 49049 B `c9dc0131…1c2a97349`（LF 1297）；均 LF、EOF newline、读到实际 EOF。

## 残留与未验证

- 无 L2 producer→writer→consumer→projection、无真实 O_CREAT|O_EXCL 锁/双调用者/崩溃对账（T20/T31 接管同测试文件，须依赖 + hash 交接）。
- 25 旧 ID 仅抽样 dp1/dp4/dp25；`ACTIVE_ENTRIES`/`MATTER_OWNERS` 常量需 T31 与 T03 单源交叉核对。
- D012A 模型理由 vs PM basis、真实 authority/policy/budget usage 来源、dp-QG reopen/gate reject 真实消费者、真实 AC/VC/goal/签收文件均未接线未验证。
- 未跑 npm check / TS / build / install / deploy / commit；未真实 provider/HTTP/CLI/服务。
- 并发 pyc 未清理、未据以判断产品。

## 上下文来源

`tasks/isolated/T06-validity.md`（SHA `1a8102…`）；`workers/dpc-t06-validity/task.md`（`eb6c3f…`）；`design.md` §4.1/4.3/4.5、§7、§8；`design-write-scope.md`；`evidence-requirement.md`；T03-R3/T04-R2 PM handoff；`s2-frontier-pre-dispatch-20261026/check.json`；`implementation-isolation.md`；本目录 `baseline/before.json`、`write-scope.json`、`assertions.json`、日志与 3 个 runner/检查脚本。

## 改动清单

- `implementation-worktree/packages/multi-workers/decision_validity.py`（新增）
- `implementation-worktree/packages/multi-workers/test_dp_consolidation_concurrency.py`（新增）
- `evidence/implementation/dpc-t06-validity/**`（新增证据：baseline、写面/哈希核对、assertions、red/green 日志、runner）

未改：主树同名文件、T03/T04/T07/T08 产物、其他 task、config/gate/ledger/policy/goal/spec、TS/依赖/lock、活对象；无 symlink/hardlink，无权限/预算/watchdog 改动。
