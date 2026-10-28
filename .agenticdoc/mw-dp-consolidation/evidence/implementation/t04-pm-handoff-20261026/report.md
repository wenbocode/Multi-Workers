# T04 PM 独立吸收与暂不交接（2026-10-26）

## 结论

T04 实际 run 为 `dpc-t04-context-ts-generation@2026-10-26T06:22:40.974Z`，结束 `06:34:10.048Z`，done/exit0。处置落盘后已实际调用 ack_worker_result，工具返回 `Acked 1 task(s): dpc-t04-context-ts-generation.`；acked 不解除下述交接阻断。PM 已回读 output/report/run、五允许路径的当前产物及完整 changed-files.diff，并于 `11:24:13.398865+00:00` 完成独立私有复验。**当前卡内生成实现局部通过，但 semantic_handoff_verified=false，T04 仍需定点测试返工，S1 不关闭，下游不派发。**

新写的 `test_decide_registry_ts_lock.py:289–296` 在 `test_check_and_stdout_modes_write_nothing` 中对整个 `decide_cases/dp*.json` 集合强制 `len == 4`。批准的 T05 原卡明确创建八个 `dp-*.json`，保留四旧文件，总数将为十二；该永久断言与原 DAG 合法演进冲突。PM 仅替换该真实测试函数的目录列表，保留四旧文件内容并加入八个明确标注为 synthetic 的内存条目；真实断言在 line296 被触发。此探针不写 case、不运行 T05 generator、不构造业务 PASS，仅证明断言拒绝合法文件共存。应定点修复为准确保护四旧文件，允许批准的新 case 共存，并保留生成器 check/stdout 全写入边界检查；不能删除保护或扩大 T04 写面。

本轮失败处理请求使用真实 task_before，于 `ask_decision(dp4-failure-handling, trigger=dpc-t04-context-ts-generation)` 返回 `available=false / input-incomplete / blocked-ask-human / missing_fields=[meta.task_before]`。**blocked on decision dp4-failure-handling**。无有效 decision_id、无 receipt，不重复调用、不修活桥或绕通道。新的有界返工尚未获处理裁决，未建卡或派发；需要人工确认仅原 T04 副本 `test_decide_registry_ts_lock.py` 内定点返工及原 T04 evidence 的新子目录，保留原 run/红绿/五文件成果，不改目标/权限/预算/原依赖。

## 证据

- `check.json`、`check.py`、`probe.py`、`probe.json`：新鲜四命令 rc0；`pm-green.log` 为 **35 passed in 0.56s**；`pm-generator-check.log` 为 rc0/空 stdout、stderr；`pm-probe.log` 包含真实导入/输出根与永久四 case 断言反例。
- 所有实际导入均在 implementation-worktree；生成器 `_REPO_ROOT`、output_path 与已静态完整读取的实现一致。只执行 check/stdout，不执行默认写生成或 build_decide_cases。
- 八活动 ID 顺序与 Python 相同，7 pm/1 worker；两个 contextSlots 均仅为 `error_excerpt`，属于 dp-QG/dp-auto。独立运行 assigned 35 tests 验证逐字段、模型白名单、empty_is_value、preparation/core/context 排斥及负例；probe 再独立比较 25 retired 全字段，包括 description/disposition/migratedTo/note。真实 JSON bytes == registry_snapshot_text().encode；真实 TS bytes == render().encode。不是第二手写菜单。
- `pm-generator-stdout.stdout` 是 Windows 文本 stdout，CRLF 而磁盘 TS 为 LF，所以 **stdout_exact_bytes=false**，Windows EOL 等价为 true。真实文件的逐字节 render/snapshot 比较独立成立，不能用 stdout 文本等价冒充磁盘字节锁。
- `after-bytes/`、`pm-full.diff`：五文件 SHA/bytes/EOL 与 worker after 原字节相同；JSON 未变；四文件变化。context 5 hunks、generator 9、test 2、TS 6，共22。PM full diff 92837 bytes 与 worker 完整 diff 逐字节相同。五 live 对应文件 hash 与 T04 派发前相同，且 non-samefile。
- 整副本 inventory 1864→1864、无新增/删除；仅上述四个允许文件变化，全部其他镜像（包括 T03 protocol/tests、T11 consumer、四旧 case）与派发前 SHA 相同。PM 测试/探针/check/stdout 后整副本字节不变，当前无 `__pycache__`。这是前后净差异，不证明执行期间从未发生越面写、无手工 writer、独占作者或全活树清洁。
- worker 历史：`logs/red-01-new-tests.log` 为32 failed/3 passed。但多项失败停在新增 `_LiteralParser` 自己的未引号 key 缺陷，**不能把32全部称为32个真实行为红测**。已有直接行为反例包括旧 slot producer、core collision/retired provenance 没抛 ValueError、缺 preparation/retired/active 声明；后续测试 parser/切片修正不是生产缺陷。worker final assigned35passed/rc0与真实生成日志已回读；PM 新鲜结果单独保存，不改原历史。worker 报告 readonly T03 181passed，本轮没有扩跑 T03，也不借该报告代 PM 新验证。

## 改动清单

PM 本轮只新增本证据目录的 verifier、日志、probe/check JSON、after bytes/full diff、本报告，并更新本 key 当前编排状态。**PM 没有修改业务源码、生成产物或测试实现。** Worker 四项产品变化：context slot provenance/冲突检查、单源 TS generator、35项生成锁 tests、八入口/25退休 TS 投影；允许 JSON 未变。当前 full SHA/EOL 见 check.json。

## 残留与未验证

1. 上述新永久四 case 断言阻断 T04 语义交接；只读探针不是实际 T05 生成或业务验收。依赖 T05 另含 T09，不能越依赖先跑。
2. worker 自报曾有一次未隔离静态 import 写四个 `.pyc`，随后删除；当前净 inventory/无 pycache不抹掉这一历史边界事件，也不能证明历史数量和责任全部独立确认。
3. `test_decision_context.py` 未在原 DAG 写面内：旧 slot/validate 两测试函数至少三种旧 ID 情形与新合同冲突；尚未运行该卡外测试。`test_decision_context_contract.py`/decision_book 属 T09，旧四 TS entry anchors及 fallback需其后继迁移。T11 consumer 迁移另属 T11。不能为了局部35通过称全项目测试通过，也不自行补写无主测试或扩大 T09面。
4. 原 T03 83历史 evidence、主树其他 dirty/原卡文件本轮未重新逐字节核对；整副本和live五项比对只证明已声明的范围，不宣称全历史/全活树不变。
5. TS 编译、模块/依赖等价、T32完整保护check、运行caller/replay/provider/basis/vision/effects、human/H12身份、L2/独立审核/QG/签收未验。未运行 npm check/build/install/full suite/服务探针，未回移/部署/提交/改变权限预算或其他 key。
6. 本轮 PM verifier 首次 rc1 因自身 diff 末尾多一个分隔 LF；第二次 rc1 因未考虑 Windows stdout CRLF。均先查真实 bytes后仅修 evidence verifier，最终 rc0。不是产品红测；前两次工具异常留在会话，当前日志为最后新鲜成功复验。
7. 全 key worker 队列读回无 running/pending；这不是不存在人工 writer 的证明。没有可合法越过 T04 交接依赖的并行编码单元，不为填槽增加研究或第37逻辑任务。

## 上下文来源

`.agenticdoc/goal.md`、锁定 SPEC/已批 design/plan/原7stage36task DAG；当前 `implementation-isolated-dag.json`/`implementation-isolation.md`；isolated T04原卡/hash99c0fb85…12200、isolated `T05-eight-cases.md`明确八新文件与四旧只读；T04 worker run/output/report/after/full diff及 red/final/gen/legacy logs；派发前五bytes/hash/live基线及1864 inventory。PM 当前直接事实来自本目录 fresh logs/bytes/probe，不回填过去进展；phase仍 EXECUTE，不等于 S1关闭、正式QG或签收。
