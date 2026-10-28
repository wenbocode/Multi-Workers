# 隔离实施执行覆盖（2026-10-26用户已批准）

## 当前生效边界
批准原文/并行分析见evidence/implementation/isolation-approval-20261026.md。本文件是plan物理执行覆盖，不更改design/SPEC/53AC/53VC。原implementation-dag.json和tasks/T03～T36原卡保留历史；当前执行以implementation-isolated-dag.json及tasks/isolated/T03～T36为准，两已派research的原卡/状态/证据不变。不加新的调度器/账本；实际队列仍dispatch_worker。

- 真实实施root：`.agenticdoc/mw-dp-consolidation/implementation-worktree/`。
- 每个product_write_face为原已批exact path加上述prefix；source_product_write_face及source_card_sha256可逆追溯原卡。所有原stage、deps、role、execution、AC/VC、goal/requirements及具体测试argv不变，仅cwd映射；review/PM-direct分工不变。
- 85个DAG产品/测试/框架逐文件允许面是原批准清单的子集，不是目录授权。其余副本仅只读伴随源码/元信息，86原文件引用计数包含其他路径，不能充作85新授权或缺口统计。
- 只允许当前卡对应副本文件；主树同名文件及所有活对象禁止写，副本不可重新从主树覆盖。原有他窗dirty逐字进入snapshot，不把diff归本key；future回移必先核源漂移/作者协调且另批。

## 实际构建证据与适用范围
`evidence/implementation/isolation-baseline-20261026/setup-check.json`：10:29:10实跑，1862普通独立文件、85逐文件基线、34映射卡，原四合同hash未变、DAG/AC/VC不变、unordered overlap=0、源码链接新建=0。每个snapshot写后readback相等，并检查非samefile；全部85原允许路径的存在性/已存在者终态hash相同，未开始者不伪造before bytes。source-inventory.json含逐文件sha/bytes/EOL；original-bytes/original-diff含原允许已存在文件的完整bytes及git HEAD差异（untracked由bytes留底，不把空git diff当净文件）。source-cards/card-mapping含原卡原bytes和两版hash。git-status/framework-status前后输出保留，不宣称全活树无其他session改动。

已排除runtime/credential名称目录及文件、dist、node_modules、Python分发、账本/缓存；skipped-paths.json列实际排除。副本内空.agenticdoc标记无grant/policy/key/账本，仅防祖先查找穿透；它不是活框架root或伪授权。实际测试必须另设本卡evidence内独立fixture project/home/TEMP，不能用副本源码root或本仓root作业务project。

## S0处置与frontier
T01/T02证据/回读/ack完成；切换冲突不靠旧ID别名解除，而是用户批准不切换活树的独立源码路线，源码副本和原dirty冲突通过独立bytes/限定write_face具体隔离。当前纯协议T03可在本覆盖/卡验证后开始；T04等T03实际红绿/合同/哈希交接，不提前排队。其他stage仍原全部依赖和语义出口，单writer规则不变。

这不是human/H12资格、vision能力、实际内存bundle/活覆盖行或部署验证通过。原签收适用/合法disable、H12真实来源及预授权的consumer和最终验收门保留，未知仍fail-closed，不新增grant/token/TTY/角色伪证明。T03只证明纯注册/validator局部，不能签全入口旧ID/replay拒绝或L2；mw.py真正replay guard仍T23，四旧case不改。签收/QG/stage关闭原独立。

## 执行和验证约束
先读本卡副本文件到真实EOF、存卡级before/after/hash/EOL与差异；先业务断言红测再最小实现绿测。Python最小环境、禁plugin autoload/cache/pycache、无provider/worker/project配置继承，脚本/import路径实际绑定副本；backend/network隔离后只跑卡列具体文件。生产writer只能写本卡fixture，脚本/日志/临时文件只写本卡evidence，不能手写伪gate/ledger/PASS。

T03 registry snapshot按副本Python既有单源接口离线生成，只写本卡副本JSON；T04既有gen_decide_registry_ts.py实际_REPO_ROOT须为副本，TS输出也仅副本；T05 --out限本卡隔离目录，四原case字节锁仍需验证。不得拿原仓导入/缓存版本的绿测代副本成果。未列路径先明确原因/minimal scope再请求批准。

TS依赖/完整npm check的模块解析及等价性现在未验证；没有安装/链接或npm/check。TS卡届时先核faux/harness及实际module/script路径，不让ancestor node_modules把目标生产模块指回主树。T32 PM-direct需从实施结果另建完整、等价、无live状态的保护副本；先证明工作区/依赖/脚本/生成锁身份再完整check，不在共享实施树跑Biome --write。缺失或非零保持具体阻塞/修复，不吞旧债。

## 原禁止面继续生效
不改主树源码/框架clone/mirror、pi核心、spec/goal/原worker历史、他key、活config/policy/gate/brake/ledger/凭证/预算/签名、依赖/lock/version/dist/global bundle；不调用实际provider/业务决策probe，不build/install/restart/commit/push。后续回移和真实切换另行授权。当前仅完成setup与编排校验，无产品测试/产品验收/QG/签收或phase推进。
