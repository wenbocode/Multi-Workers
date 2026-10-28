---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/**
ac_refs: [AC-002, AC-004, AC-012, AC-014, AC-043, AC-051]
vc_refs: [VC-002, VC-004, VC-012, VC-014, VC-043, VC-051]
deps: [T03, T04, T08]
execution: worker
---

# 原逻辑 T09 — R2 原面定点修复（不是第37任务）

## 上下文

目标`.agenticdoc/goal.md:5`；锁定`.agenticdoc/mw-dp-consolidation/spec.md:128`及批准`.agenticdoc/mw-dp-consolidation/design.md:201`。继承完整原`tasks/isolated/T09-books.md`所有AC/VC、角色/层次、禁止面和隔离合同，必须全文读取；原终态done/exit0/acked但PM技术handoff=false，不把109green当release。
用户已明确应解决问题并开发完整，原授权面内一般工程缺口由PM组织修复验证；此R2只修具体已复现问题，不扩大原goal/验收/53AC-VC/36DAG/预算/权限。PM证据`evidence/implementation/t09-pm-handoff-20261027/{check.json,probe.json,bootstrap.py}`，两个实际after源码PM已完整读到EOF。原worker证据`evidence/implementation/dpc-t09-books/report.md`与before/after/diffs/失败原样保护。

## 要求

PM09:05:20～25Z两次assigned109passed/rc0；独立17fixture为4通过13失败，非collection/env误报。四组根因在本书库面，先复现并加真实回归红，再最小实现、保留全部109函数AST/断言强度并绿：

1. `prepare_stdin_request`把JSON解析后的非Mapping交给具path重载的`prepare_request`：null/list/[book]/bool/int/float六次TypeError；JSON字符串指向fixture中合法book文件竟准备成功。stdin只接受单个book对象，非对象必须具体book-schema issue、prepared=None、无文件加载/无backend调用/无escaped异常；`prepare_request(path)`合法文件API仍保留且工作。bundle/坏JSON/合法对象三控制保持。
2. `check_book_file`load失败时追加entry缺少ok，`BookReport.as_dict()`对非法legacy file抛KeyError。非法文件仍有完整可序列化issue/ok=false，不造合法书或抹失败；保留合法/混合bundle独立结果。
3. `_schema_issues`对unknown top/notes key、坏version、unknown DP直接repr业务输入，已知secret redactor传给`check_book`仍有四次哨兵回显。所有暴露给调用方的schema/装载/检查失败路径与detail用已有decision安全helper/既有known redactor，不回显已知秘密，不把notes/state/错误码降成generic silent fallback。不得改decision.py/decision_points.py/其它key redactor实现。read+check各入口/嵌套schema错型应覆盖，真实秘密不读/不写；测试用本卡synthetic sentinel。原有效材料、meta隔离、分层、basis不变。
4. schema_version类型判定`version!=3`接受float3.0。JSON schema版本须真正非bool integer3，int3控制合法，bool/string/float等拒绝；不扩大版本/静默升级。

这些是四个定点根因，不重写本书库架构，不顺手加兼容/修context projection/观察/CLI/store/其他测试。T09报告里的context/观察和旧独立26AC测试债需PM核对原后继写面，不能自行修nonface或宣称它们已完成。保留原109测试函数体，新增具体regressions，不再整文件替换。每改测试先真实red，再实现绿，完整stdout/stderr/rc；PM原17fixture独立复验沿用，不能修改PM脚本/旧output/run/原证据来假绿。

## 写入允许面

- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_book.py
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_contract.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t09-books/rework-r2/**

## 写入禁止面

其余所有路径，包括原T09证据/PM复验、原卡/run/output/trace/manifest/state、其他任务/键/副本依赖与测试、live同名源码、框架parser、goal/spec/design/plan、JSON/TS/生成器、config/policy/gate/brake/ledger/grant/signoff。14既有pyc不删不变。禁止依赖lock/dist/install/build/restart/commit/push/copyback/链接/权限/预算/watchdog/真实HTTP/provider/决策CLI/服务探针或绕失败入口。

写前真正完整读两个当前source/test到EOF；baseline expected book SHA dbe2329aa0b84ae10c484f526e812cae36545590c17d857bbfde040f302d32a0/test SHA9bbf89d6e03a6b6d60dd511d37509cc632d61e6c4ea9f3ae7c821da079ff2176。记录before bytes/SHA/EOL、既有完整diff，不拿hash代阅读或重复制覆盖副本。只用新增R2 evidence，所有Python（import/subprocess也含）python -B/PYTHONDONTWRITEBYTECODE=1、禁pytest autoload/cache、minimal UTF8 env/privateHOME-USERPROFILE-TEMP-project、绑定副本imports/子进程根；fakebackend+网络禁用、fixture writer只写本R2 evidence。PowerShell5.1无&&，不放真实凭证到env或证据。

## 验收命令

cwd=.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers：`python -B -m pytest -p no:cacheprovider -q test_decision_context_contract.py`，原109控制+新增四组回归。每轮完整stdout/stderr/rc保存自己R2证据；不跑其他源测试/CLI/生成器/provider/全部check。npm run check只T32 PM-direct保护等价副本，不在共享copy跑写式formatter。

## 改动历史

原T09：真实46failed2passed旧合同baseline→103failed5passed新合同red→109passed/rc0；原两diff27/4hunks、1883mirroronly2变化、14pyc不变。原attempt immutabledone/exit0/acked，PM新fresh109两次/17fixture13fail使当前semanticfalse。此R2由本轮用户完整开发授权内PM组织一般定点修复，不是新逻辑任务/无上限重试，不伪造成功decision/receipt。

## 交付格式

report.md/output.md均五独立节：`## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。exact文件表每行一产品全路径，不在表头声明目录/尺寸片段。给原AST完整保留对账、真正新红/绿、before/after bytes/SHA/EOL、完整incremental diffs、所有runsstdout/stderr/rc、净inventory与已知限制。只称本层，不称完整L2/check/QG/signoff/human权限/观察/部署。终态PM吸收ack并独立复验后按原DAG释放T05/T10，worker不自行派下游或改phase/预算。
