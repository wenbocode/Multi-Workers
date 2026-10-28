# Evidence Requirement: mw-dp-consolidation

> 状态：候选证据合同，未获设计/VC冻结批准。生成不表示已经验证或签收；本轮没有产品测试结果。

## 锁定指纹

| 字段 | 值 |
|---|---|
| spec_path | `.agenticdoc/mw-dp-consolidation/spec.md` |
| spec_locked_at | 2026-10-25T23:37:14+08:00 |
| spec_sha256 | `cfe737d29aed2d0c4e79d8b02107f754f254a225bb21ea8d900eaa5ba289d006` |
| ac_payload_sha256 | `d73c3050ab0ec4a0af7ddeb169264257638cdfdfb5f34d63f734528d4a20737e` |
| ac_fingerprint | `767fc1acdbcb` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-024, AC-025, AC-026, AC-027, AC-028, AC-029, AC-030, AC-031, AC-032, AC-033, AC-034, AC-035, AC-036, AC-037, AC-038, AC-039, AC-040, AC-041, AC-042, AC-043, AC-044, AC-045, AC-046, AC-047, AC-048, AC-049, AC-050, AC-051, AC-052, AC-053 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-024, VC-025, VC-026, VC-027, VC-028, VC-029, VC-030, VC-031, VC-032, VC-033, VC-034, VC-035, VC-036, VC-037, VC-038, VC-039, VC-040, VC-041, VC-042, VC-043, VC-044, VC-045, VC-046, VC-047, VC-048, VC-049, VC-050, VC-051, VC-052, VC-053 |
| generated_at | 2026-10-26T03:08:59+08:00 |

ac_fingerprint遵循workflow-quality-gate：SPEC全部AC ID排序去重、每行LF（含最后LF）后sha1前12位；它仅锁ID集合。SPEC/AC正文另用以上SHA256，不能只用编号fingerprint判断承诺未变。VC尚未批准/冻结，不能把本生成时间当锁定时间。

## 证据载体与充分性通则

- 单次隔离运行目录：本key `evidence/runs/<run-id>/`，由后续获批任务具体创建，不是本轮既存证据。每个运行必须有输入/fixture清单、生产入口、源码/生成合同版本、环境隔离说明、完整stdout/stderr、exit code、真实request/response/lifecycle/action定位和可机械对照assertions.json；不能手写生产gate/ledger或仅凭worker done/PASS行。
- 每VC的输出必须严格匹配design §7预期字段；assertions.json给每个正向、边界、异常case的expected/observed、路径、失败理由、model_attempts/business_decisions/business_actions及原始证据引用。输出汇总和逐case断言同时成立才充分。
- 全部VC需L2：faux/hermetic真实producer→writer→consumer→projection链。L0注册/grep/生成锁或局部validator可以辅助，不能代生产路径证据。TS在suite/harness.ts+faux provider；Python隔离project/home/env、注入fake backend；没有真实凭证/服务/provider。配置、gate、恢复及签收仅由隔离生产writer产生。
- 输出中的violations=0必须按每项规定的违规事件实际测量；计数基于fixture局部范围，运输重试attempt和业务判断另计。不存在事件时不能随便用null或捏造0；没有观测写unverified，该VC不通过。
- 历史/四旧case字节清单、fixture周界及禁止面before/after hashes需覆盖相关cases；安全拒绝审计允许，但不得计有效成功。秘密使用合成canary，确认发送、记录、DOM均不漏；XSS用无真实攻击目标的faux DOM/browser断言。
- H12必须真实入口资格/受限writer负例：普通熔断链、Worker/伪origin、失效授权、人工撤权、不可用均不解锁；仅布尔preauthorized、page token或移动tick位置不充分。无法证明实际隔离则AC036/037不通过。
- 并发/崩溃证据须真实既有文件锁、同时两个调用者、动作前后故障窗口及实际对象对账；unknown不盲重放。不能靠两个预写fixture或全hash变化推导同事项/实质失效。
- D012A须另记录PM prepared_at/note/basis catalog、同次两个问题的原始model回答、所选basis的真实材料引用和applies_to一致性；显示“文本源自PM预备、选择来自模型”。若用户要求原生自由理由则须更新经批准的设计/VC并提供正式上游能力证据，不能沿用A称达标。
- 来源/time关联保持真实key/task/logical_id、非递减observed_at、null与[]差异，旧before不可回填；sign三数组仍必需。观察observe_only没有executor，不能用观察回答证明gate/签收效果。

## 待验证范围

所有下面AC/VC均待实现后验证，本轮无L2产品通过。caller清单包括生产工具/CLI/book/stdin/replay、观察validate/scaffold/cases/submit、config on/set/apply、human/legacy边界和提示词；静态匹配必须分active/history/security/regression并给完整未覆盖说明。安装/内存身份和部署不由源码hash推断，若不执行部署则明确保留未部署，不能伪称线上迁移通过。独立mw-decision-context26AC/monitor8AC及旧check/formatter/dp3/dropdown债不被本表勾销。

## AC-001: 八活动入口组成

锁定AC原文：在目标注册/schema及运行入口迁移完成后，可调用DP集合精确等于§1.1八个目标名称，旧编号可调用别名数为0；六项职责迁移、19项旧独立职责退出与两个新增入口分开可核，不以原八项/17计数判定。[REVISED @ 2026-10-25：毕业考按已确认组成整合，原草案字节另存，完整AC未锁]

VC断言：迁移后的注册、生成TS、CLI及观察提交集合都精确为§0八名；aliases=0，migrated_roles=6，retired_roles=19，added_entries=2。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-001: active=8 aliases=0 migrated=6 retired=19 added=2` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-001` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B，F01/F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-002: 25旧ID明确拒绝

锁定AC原文：在迁移后的各运行入口请求任一旧编号DP时，返回明确拒绝，模型请求数、业务执行数及新增有效业务决策数均为0；历史只读或安全拒绝审计不恢复调用，也不被错误当成新增成功裁决。[REVISED @ 2026-10-25：旧编号非默认别名，拒绝范围与业务/安全记录分清，完整AC未锁]

VC断言：对每个25旧ID分别从所有运行入口及已有logical_id replay提交，明确retired拒绝；模型/业务动作/新增有效决定各0，安全审计不计成功。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-002: rejected_old_ids=25 model_calls=0 business_actions=0 valid_decisions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-002` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N/replay，F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-003: 生产面无旧活跃调用

锁定AC原文：在盘点生产源码/配置/提示词/case及UI提交面后，旧编号活跃注册/调用/可提交选项数为0；六迁移与19退出职责逐项对应目标/拒绝处理，必要历史解释、安全拒绝与回归测试标注用途，不因删DP删除硬检查或其他框架任务类型。[REVISED @ 2026-10-25：按最新组成替代旧范围，不作为源码删除授权，完整AC未锁]

VC断言：受限生产caller/config/prompt/case/UI清单逐项分类后，旧ID活跃注册/调用/可提交数=0；六迁移与19退出逐项对应，硬检查和非菜单框架类型丢失=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-003: active_old_refs=0 unclassified_refs=0 lost_guards=0 lost_framework_types=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-003` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N/inventory，F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-004: 四职责业务基线

锁定AC原文：在各DP提交其合法业务材料时，dp-sign-key保持mw-decision-context已确认的交付目标/实际完成/已验证与未验证证据/未完成影响及finalize/continue/user-confirm签收语义；dp-w-type四候选及图像硬门、dp-pm-steer四项不降目标、dp-w-check-task三项fire-and-forget均按§1.2。增权、缩减目标/验收、冒充执行/完成或新增Worker同步等待次数为0；各分支正向观测补充见AC-044～047、038/039。[REVISED @ 2026-10-25：毕业考点名业务基线/当前入口并保留原四职责修改确认，完整AC未锁]

VC断言：w-type/pm-steer/w-check/sign-key基线合法场景分别走其全部选择，原签收四部及三数组成立；增权/降目标/假执行完成/新增同步等待均0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-004: baseline_contract_violations=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-004` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F01/F03/F10；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-005: 正式QG证据结论

锁定AC原文：在PM提交完整质量审核材料时，dp-QG依§1.2已确认含义给出pass/fix/reopen正式结论，并带可复核证据、具体缺口/依据问题及未覆盖面；审核意见不冒充已整改，reopen导致未授权修改目标/验收次数为0。精确材料/消费留设计。[REVISED @ 2026-10-25：用户认可三业务选项及含义；完整AC未锁]

VC断言：QG三结论各附真实依据、具体缺口或依据问题及未覆盖面，正式意见与实际整改分开；自动改承诺/验收=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-005: reviewed_choices=3 missing_required_evidence=0 unauthorized_contract_edits=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-005` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B，F10；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-006: QG缺证硬失败不放行

锁定AC原文：在质量证据缺失或机器硬门失败时，dp-QG不得产生可用于放行的有效通过结果，业务放行次数为0，缺失或失败项明确可见。

VC断言：缺必要质量证据及每项硬门失败时，QG有效pass=0、业务放行=0，失败项逐项可见。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-006: usable_pass=0 releases=0 hidden_failures=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-006` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N，F10；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-007: gate四项与note分离

锁定AC原文：在PM提交gate背景/当前状态及送审前预拟note（事项、批准后动作、目标/证据/预算/授权依据）时，dp-gate-approve按§1.2选择approve/steer/need_fix/reject；PM note与模型理由分别保存。steer交PM发起dp-pm-steer，need_fix交PM发起dp-auto，均不作为本gate放行或已整改证据；reject仅在有明确获授权遗留关闭方案时允许对应收尾，越权执行次数为0。精确schema/状态/消费留设计。[REVISED @ 2026-10-25：用户确认四选项及note/reject边界，替代二选项目标；完整AC未锁]

VC断言：gate四选择分别观测PM note与模型依据独立来源；steer/need_fix不放行不声明整改，reject无具体遗留授权时收尾=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-007: gate_choices=4 mixed_note_basis=0 false_release_or_repair=0 unauthorized_closure=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-007` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F02；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-008: gate授权硬条件

锁定AC原文：在具体gate的自动处理启用/授权条件缺失或硬检查失败时，dp-gate-approve任何结果均不产生有效放行，未授权业务副作用次数为0，缺失/失败条件明确记录；其他工程取证仍受原授权约束，不造启用或权限。[REVISED @ 2026-10-25：毕业考点名当前入口/可构造失败条件，完整AC未锁]

VC断言：对启用、授权、预算、claim和机器条件逐项缺失/失败负例，任何gate选择的有效放行/越权副作用=0，并保留各具体原因。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-008: unauthorized_releases=0 unauthorized_effects=0 missing_failure_reasons=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-008` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F02；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-009: phase失败auto处置

锁定AC原文：在相位门禁失败且PM提交该场景专门背景及行动候选时，dp-auto承接处置选择并保留未解决项，不改写原门禁判据，未经重新通过硬门的相位推进次数为0。[REVISED @ 2026-10-25：用户认可dp7由通用入口承接，最新名dp-auto；完整措辞/schema仍待审核]

VC断言：phase硬门失败后，PM用专门背景和候选提交auto并实际受限处理，原硬门未复验通过前phase推进=0，原失败未丢失。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-009: unchecked_phase_advances=0 erased_failures=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-009` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F01/F02；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-010: stage整体验收关闭

锁定AC原文：在PM提交阶段目标/必需交付、必需key有效签收、跨key集成/阶段验收证据及未完成/未验证影响时，由dp-gate-approve审批；缺必需交付/验证或只有done计数/key签收时，可用关闭次数为0。明确披露且不影响阶段验收的非阻断遗留不单独阻止关闭；需用户接受的风险/取舍未获具体确认时不得据此放行。approve不批准下一stage；steer/need_fix/reject不冒充达标关闭，获授权遗留收尾须与成功交付区分；不增加原dp20第二次审批，具体状态转换/消费待设计。[REVISED @ 2026-10-25：阶段关闭归属及H02关闭条件/遗留规则已认可；完整AC未锁]

VC断言：stage正例达标且非阻断遗留披露可关闭=1；缺必需交付/验证、仅done或签收、未接受风险负例关闭=0；下一stage自动批准=0，遗留关闭不计达标。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-010: valid_closures=1 invalid_closures=0 next_stage_approvals=0 false_acceptance_closures=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-010` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-011: 唯一事项owner与复用

锁定AC原文：在八入口处理同一具体事项时，职责表按主体/对象/动作及实质证据指定唯一业务审批归属；路由不代业务审批，同对象/实质证据版本重放不产生额外同事项审批或重复动作。实质影响变化的重审另留痕，不把所有不同gate文件或新材料一律当不同事项。[REVISED @ 2026-10-25：毕业考去除“四门”旧范围，完整AC未锁]

VC断言：同主体对象动作实质版本在不同标签/文件重放及并发，只一个业务审批owner，额外同事项审批=0、重复动作=0；路由放行=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-011: duplicate_approvals=0 duplicate_actions=0 route_releases=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-011` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/concurrent，F01/F02；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-012: 全入口失败阻塞

锁定AC原文：在八入口任一请求决策不可用、材料非法或返回无有效裁决时，对应受门控动作保持阻塞并显示具体原因，默认放行次数为0，不用当前状态补造结果、偷换入口或把失败冒充业务选项；不编造decision_id/执行回执。[REVISED @ 2026-10-25：毕业考明确全入口失败防御，合法失败审计不被禁止，完整AC未锁]

VC断言：八入口材料非法/不可用/无有效选择，各受门控动作=0且原因可见；伪造decision_id/执行回执、默认选择及换入口绕失败=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-012: default_actions=0 fabricated_results=0 failure_bypasses=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-012` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N，F01/F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-013: 退役历史只读原字节

锁定AC原文：在载入含退役DP的历史记录时，列表和详情可只读查看，明确退役且不可发起新运行；原始历史文件字节变化为0，不按当前注册或状态补造事实。

VC断言：退役历史列表详情读取后历史原文件逐字节相同，展示retired/readonly且新运行不可用，不新增当前配置/状态补造事实。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-013: historical_byte_changes=0 historical_fact_fabrications=0 retired_reruns=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-013` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-014: 真链来源安全

锁定AC原文：在审核及反馈跨Python/TS/观察界面传递时，真实producer→writer→consumer→projection链可由隔离生产路径测试核验，建议、实际处理和完成状态不互相冒充；秘密明文和注入脚本执行次数为0。

VC断言：Python/TS真实producer→writer→consumer→projection链可关联，选择/执行/完成不混同；请求、记录、DOM秘密明文及注入执行=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-014: broken_links=0 false_execution_or_completion=0 secret_leaks=0 script_executions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-014` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-015: 首后stage一次启动判断

锁定AC原文：在项目goal、目标范围、写面与硬预算授权已明确、stage在授权内、硬检查满足且尚无有效启动决定时，autopilot首次评估该stage发起1次dp-gate-approve启动判断，逐stage人工确认要求数为0；第一个stage与后续stage使用相同授权规则。[REVISED @ 2026-10-25：毕业考按H10已确认归属点名启动gate，完整AC未锁]

VC断言：授权条件齐备的首stage及后stage各首次评估只有1次启动gate判断；没有有效同事项决定才发起，逐stage人工要求=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-015: first_stage_decisions=1 later_stage_decisions=1 per_stage_human_requirements=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-015` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P，F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-016: 工程证据缺口先补

锁定AC原文：在启动判断仅缺可在授权内补齐的工程证据时，autopilot安排补证/修订后重新判断，补齐前stage启动次数为0，不把该工程缺口直接作为必须人工授权的理由。

VC断言：仅缺授权内工程证据先实际补证，补齐前stage启动=0、把工程缺口升级为新权限请求=0；补齐后可重新判断。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-016: premature_starts=0 fabricated_permission_needs=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-016` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-017: 缺业务权限具体问人

锁定AC原文：在启动判断缺用户业务意图或超出目标/写面/硬预算授权时，autopilot升级信息明确列出缺失意图或所需新权限，越权启动和执行次数均为0，不推测授权代替用户。

VC断言：缺真实用户业务意图或越目标/写面/硬预算的启动场景，具体缺失项/所需权限可见，越权启动及执行=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-017: unauthorized_starts=0 unauthorized_actions=0 vague_escalations=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-017` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N，F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-018: 启动硬门不豁免

锁定AC原文：在启动路径任一机器硬检查失败时，autopilot记录具体阻断并保持该动作停止/等待/修复，因DP批准而豁免硬检查的次数为0。

VC断言：启动各硬检查失败时停止对应动作，DP选approve也不得豁免，具体阻断无遗漏。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-018: waived_hard_checks=0 hidden_start_blockers=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-018` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N，F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-019: 启动实质版本与重放

锁定AC原文：在影响启动的goal、stage目标、key交付范围/依赖或授权边界发生实质版本变化时，autopilot不以旧批准启动并重新判断；同一事项同一证据版本重复处理产生的额外同事项审批与业务动作次数均为0。

VC断言：启动依赖实质变化使受影响旧批准复用=0；同版本及语义等价重复额外审批/动作=0；需要重新判断的新实质版本有真实关联。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-019: stale_starts=0 duplicate_approvals=0 duplicate_actions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-019` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/replay，F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-020: 有依据限定软追加

锁定AC原文：在软轮次耗尽且已有授权允许追加时，dp-gate-approve仅在PM note具备真实进展、预算依据及下一轮明确目标/方案/结束判据时可批准限定追加；不能以硬预算尚余自动批准，无授权或无依据重复追加次数为0。精确计量/消费待设计。[ADDED @ 2026-10-25：由H04认可推导，完整AC未锁]

VC断言：有软追加授权且note具真实进展/预算/方案/结束判据正例仅限定delta追加；无授权/无计划或只凭硬余额负例追加=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-020: unbounded_extensions=0 unsupported_extensions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-020` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F05；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-021: 硬预算不可自提

锁定AC原文：在追加软轮次、steer或need_fix处理将突破硬预算时，不执行越界投入；提高硬预算须取得包含具体追加量/用途/风险的明确人工授权，因DP选择而自行提高硬预算或越界续跑次数为0。[ADDED @ 2026-10-25：由H04认可推导，未设置实际预算值，完整AC未锁]

VC断言：软追加、steer或need_fix将越硬预算时越界执行=0、自行提高硬上限=0；必须具体追加量/用途/风险授权问题，累计消耗不重置。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-021: hard_budget_overruns=0 self_granted_limits=0 reset_usage=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-021` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F05；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-022: pending事件复核非恢复

锁定AC原文：在pending-review因到期、依赖交付或新证据触发复核时，触发不自动恢复或要求人工；仅目标有效、阻断解除且证据/授权/预算满足时，approve可按PM note恢复，无依据恢复次数为0。具体事件/阈值/状态待设计。[ADDED @ 2026-10-25：由H05认可推导，完整AC未锁]

VC断言：pending复核事件/到期只触发评估，不自动恢复/默认要求人工；正例目标有效且阻断消除及证据授权预算充分才approve恢复，无依据恢复=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-022: event_only_resumes=0 unsupported_resumes=0 mandatory_human_waits=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-022` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F05；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-023: pending三项真实后继

锁定AC原文：在pending-review处理选择steer/need_fix/reject时，按§1.2移交PM或拒绝当前方案，不把reject默认映射返工，不冒充已整改/恢复；越权预算/目标/写面变更及无授权遗留关闭次数为0，复用同份有效质量证据不重复审核。[ADDED @ 2026-10-25：由H05认可推导，完整AC未锁]

VC断言：pending三非approve项真实交PM或拒绝方案，reject默认返工=0、假恢复整改=0、越权目标预算写面/遗留关闭=0，同证据重复QG=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-023: default_reworks=0 false_resumes=0 unauthorized_changes=0 redundant_qg=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-023` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F02/F05；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-024: goal有效批准指定采用

锁定AC原文：在goal变化触发核查时，区分实质差异及授权；仅有效approve可按PM预拟note采用指定新目标版本。reject/steer/need_fix不得自动采用或刷新baseline恢复，因仅文件变化或无有效批准而采用新目标次数为0。具体版本/消费待设计。[ADDED @ 2026-10-25：由H06认可推导，完整AC未锁]

VC断言：goal文件变化先核实质差异，仅有效approve采用note指定语义版本；其他三选择及失败不刷新baseline/自动恢复，错误采用=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-024: unapproved_goal_adoptions=0 unapproved_baseline_refreshes=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-024` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F06；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-025: goal影响失效与无关复用

锁定AC原文：在实质goal变更影响key/验收/依赖/写面时，不以受影响旧批准放行；缺新业务意图/权限/风险取舍明确用户决定项，工程补证不造授权，不影响事项有效证据复用且纯非实质变更不重复实质审批。越权限/预算/承诺变化自动执行次数为0。[ADDED @ 2026-10-25：由H06认可推导，具体失效/授权绑定待设计，完整AC未锁]

VC断言：实质goal变更只失效受影响key/验收/依赖/写面批准，缺意图权限具体问人；越权执行=0、无关/纯排版重复审批=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-025: stale_affected_releases=0 unauthorized_actions=0 irrelevant_reapprovals=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-025` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F06；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-026: 跨key限定方案

锁定AC原文：在PM请求跨key受限修复时，note明确必要性、目标key/文件/动作、影响、授权及写面协调/验证；approve仅批准授权内限定方案，开放式或越授权修改次数为0。新写面/承诺变更须具体确认，不以项目写面包含关系自动放行。[ADDED @ 2026-10-25：H07验收推导，仅本key，完整AC未锁]

VC断言：跨key note具体必要性/key/文件/动作/影响/授权/协调/验证，正例只在限定面实施；开放式/新增未授权写面修改=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-026: open_ended_repairs=0 unauthorized_write_surfaces=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-026` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F06；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-027: 跨keyclaim角色独占面

锁定AC原文：在跨key受限修复派发/执行时，明确执行者及受限写面且仍通过claim/角色/独占写面检查；因DP批准而抢占他窗claim、双Worker同文件并写、越权限修改或拒绝后自动关闭次数均为0，选择不冒充已派发/修改。[ADDED @ 2026-10-25：H07验收推导，具体授权绑定/协调/消费待设计，完整AC未锁]

VC断言：实际跨key执行者/claim/角色/独占面检查成立；抢他窗claim、双Worker同文件并写、越权及reject自动关闭=0，选择不得冒充派发/修改。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-027: claim_thefts=0 concurrent_file_writers=0 unauthorized_actions=0 fake_dispatches=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-027` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N/concurrent，F06；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-028: 冻结条目限定差异

锁定AC原文：在申请冻结AC/VC变更时，PM note明确指定key/条目、前后差异/理由、承诺与证据影响、授权/重验安排；approve只批准限定具体变更，旧批准用于未经批准的新变更、无授权删减验收或伪造完成次数为0。越授权或意图不明具体问人。[ADDED @ 2026-10-25：H08验收推导，具体绑定/消费待设计，完整AC未锁]

VC断言：冻结变更仅指定key/条目/前后差异/承诺影响/权限/重验安排获准，旧批准套新变更、未授权降验收和伪完成=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-028: reused_unrelated_change_approvals=0 unauthorized_acceptance_reductions=0 fabricated_completion=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-028` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F06；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-029: 契约受影响重验历史

锁定AC原文：在冻结AC/VC获准变更后，重新验证受影响部分，不直接沿用旧条件通过；原要求/失败/变更历史不改写，dp-QG reopen不直接授予修改权限，reject不自动改契约/关闭/签收。不受影响有效证据依既有规则复用。[ADDED @ 2026-10-25：H08验收推导，具体版本/失效/状态待设计，完整AC未锁]

VC断言：冻结变更后受影响旧证据通过=0，需真实重验；历史原要求/失败/批准字节不改；QG reopen或gate reject自动改契约/签收关闭=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-029: stale_acceptance_passes=0 rewritten_history=0 automatic_contract_or_closure_changes=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-029` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F06；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-030: proposal真实在途有界恢复

锁定AC原文：在proposal派发耗尽恢复前，核实派发/执行/结果接收及pending/running状态、尝试/产物/预算/授权；未知或冲突在途执行时不盲目重派，明确动作/预算/结束判据后仅受控有界恢复，冲突/无依据重派次数为0。[ADDED @ 2026-10-25：H09验收推导，真实状态证明/限额/协调待设计，完整AC未锁]

VC断言：proposal恢复核派发/执行/接收和pending/running、尝试产物预算，未知/冲突在途重派=0；正例只有限定动作预算结束判据的受控恢复。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-030: unknown_state_redispatches=0 conflicting_redispatches=0 unbounded_recoveries=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-030` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F07；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-031: 恢复标记失败保留

锁定AC原文：在proposal耗尽恢复及标记处理时，保留失败记录，清标记仅通过有前置检查/可追踪的恢复机制，不靠改记录/状态制造成功或越权续跑；有效授权证据复用、实质变更重判，仅确有独立审批才追加gate，不因工程故障默认等人。[ADDED @ 2026-10-25：H09验收推导，锁/标记/消费者待设计，完整AC未锁]

VC断言：proposal失败保留且标记清理有前置检查/原恢复关联，改状态造成功=0、未经验证清标记=0、同事项额外gate=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-031: erased_failures=0 unsafe_marker_clears=0 fake_successes=0 redundant_gates=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-031` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N/crash，F07；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-032: roadmap有依据重规划

锁定AC原文：在roadmap/stage提案耗尽时，核实被拒提案/原因及工程或业务缺口，授权内具实质修订依据、预算与结束判据可重规划；无依据无限相似提案或越授权/硬预算规划执行次数为0，缺目标/优先级/权限具体问人，不默认等人。[ADDED @ 2026-10-25：H10验收推导，触发/限额/消费者待设计，完整AC未锁]

VC断言：roadmap耗尽授权内有实质修订/余预算/结束判据才重规划，旧原因可见；无限相似提案/越权硬预算投入=0，缺业务事项具体问人。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-032: unsupported_replans=0 unbounded_proposals=0 unauthorized_planning_actions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-032` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F07；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-033: 新规划版本不授启动

锁定AC原文：在提案重规划时，保留旧提案/拒绝/失败、新版本表达修订，不清次数/重写状态绕限制；新stage启动仍须按H01审批，由重规划直接授新权限或启动次数为0。[ADDED @ 2026-10-25：H10验收推导，版本/归档/状态待设计，完整AC未锁]

VC断言：重规划保留旧提案拒绝失败并以新版本关联，重置尝试/改历史绕限=0，规划直接授新权/启动=0，新stage另按H01。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-033: reset_attempts=0 rewritten_proposals=0 planning_grants_or_starts=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-033` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F07/F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-034: halted限定恢复关联

锁定AC原文：在请求halted stage恢复时，PM note给停止原因/消除证据、stage版本/影响key、目标方案、授权/余预算及动作结束判据；仅条件成立且approve有效时限定恢复。原停止事实通过恢复记录或新版本关联保留，抹历史/重置消耗预算/无依据恢复次数为0。[ADDED @ 2026-10-25：H11验收推导，结构/状态/消费者待设计，完整AC未锁]

VC断言：halted正例note具停止消除证据/版本影响/目标权限余预算结束判据且approve有效才限定恢复；抹停止历史/重置消耗/无依据恢复=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-034: erased_stop_facts=0 reset_usage=0 unsupported_resumes=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-034` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F08；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-035: 人工停止恢复权

锁定AC原文：在halted源于用户明确停止/撤权或硬保护时，技术原因消除/DP选择不能替代恢复所需明确授权与硬检查，未经恢复授权解除人工停止或绕硬保护次数为0；其他三项不冒充已恢复或授新权限。[ADDED @ 2026-10-25：H11验收推导，授权证明/状态待设计，完整AC未锁]

VC断言：人工停止撤权或硬保护负例，技术修复/DP选择不能替代恢复授权，未授权解除人工停止/绕硬保护=0，非approve项假恢复/增权=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-035: unauthorized_user_stop_unlocks=0 hard_guard_bypasses=0 false_resumes=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-035` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N，F08；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-036: 熔断隔离来源受控恢复

锁定AC原文：在自动决策熔断后，仅原因消除有可复核证据、恢复预授权及机器检查满足时，经明确授权受控通道按PM note限定恢复；被熔断链路绕刹车自批、决策不可用默认批准/偷换通道或越能力/权限/预算恢复次数为0。[ADDED @ 2026-10-25：H12验收推导，通道隔离/状态/消费者待设计，完整AC未锁]

VC断言：隔离H12来源/预授权/消除证据/硬检查正例才限定恢复；普通熔断链、伪origin、无权、不可用负例自批/换通道/默认恢复=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-036: breaker_self_approvals=0 unauthorized_recoveries=0 transport_bypasses=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-036` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F09；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-037: 保持刹车与观察再熔断

锁定AC原文：在熔断缺恢复授权/证据或用户明确停用撤权时，保持刹车并提出具体授权/信息问题；不自行解除人工限制、删刹车/改历史造成功，原熔断/恢复记录保留，reject不自动关闭项目，恢复观察/停止/再熔断范围明确。[ADDED @ 2026-10-25：H12验收推导，实际预授权/观察规则未设置，完整AC未锁]

VC断言：H12缺授权证据或用户撤权保持刹车且具体问题可见；原熔断及恢复保留，reject项目关闭=0；观察原因再现正例再熔断=1。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-037: unauthorized_unlocks=0 erased_breaker_history=0 reject_project_closures=0 observed_retrip=1` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-037` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F09；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-038: 同次有效finalize硬门

锁定AC原文：在已批准适用规则要求key签收时，仅有效finalize及对应签收证据满足签收条件；continue/user-confirm、签收文件或QG通过不冒充phase done/stage关闭，不豁免必需验收/claim/契约/证据硬门，不增加第二次PM批准。[ADDED @ 2026-10-25：H13验收推导，真实词表/关联/消费者待设计，完整AC未锁]

VC断言：原适用必需签收场景，仅当前有效finalize及对应证据可满足该项；同次判断写入且第二批准=0，continue/user-confirm/QG/文件存在代done或stage关闭=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-038: second_sign_approvals=0 false_signed_conditions=0 automatic_done_or_stage_closes=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-038` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F10/F04；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-039: 签收词表范围版本

锁定AC原文：在签收命名/硬门衔接及证据实质变更时，正确识别finalize契约，不伪造旧标签/disable规避原必需签收，不自动扩大强制范围或无条件复用受影响旧签收；原历史不补造。具体有效性/版本/框架写面待设计。[ADDED @ 2026-10-25：H13验收推导，完整AC未锁]

VC断言：finalize正确词表与当前matter/实质证据校验成立；旧词表或disable绕原强制规则、强制范围扩大、受影响旧签收复用/历史补造=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-039: legacy_word_bypasses=0 signoff_scope_expansions=0 stale_signoff_reuses=0 historical_fabrications=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-039` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F10；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-040: 七路由非业务动作

锁定AC原文：在PM提交主体/对象/具体待决问题清楚的临时问题时，dp-route只选择§1.1其余七入口之一，入口选择及依据可见，所选业务结论/业务动作不得由路由答复推断，路由造成的业务放行/执行次数为0。目标材料仍按所选入口合同准备。[ADDED @ 2026-10-25：毕业考推导，技术字段/记录留设计，完整AC未锁]

VC断言：route分别选择七目标并显示依据，入口选择不能推出目标业务结论，路由业务放行/执行=0，目标材料另准备。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-040: routed_targets=7 route_releases=0 route_actions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-040` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F01；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-041: 固定直调复合角色

锁定AC原文：在固定业务节点有明确对应DP时可直调，额外强制路由次数为0；PM遇复合问题时拆清独立事项及主体，按对应合同判断，同事项重复审批为0。路由不能使PM冒充Worker自身判断或Worker调用PM专属DP，角色越权执行次数为0。[ADDED @ 2026-10-25：毕业考推导，不新增角色资格，完整AC未锁]

VC断言：固定节点强制route=0；复合事项有独立owner，PM代Worker自身判断及Worker调PM入口成功=0，同事项额外审批=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-041: mandatory_routes=0 role_impersonations=0 duplicate_approvals=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-041` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F01；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-042: auto真实候选理由

锁定AC原文：在PM为现场问题准备合法可区分行动候选及后果/约束时，dp-auto仅从该候选集合选择，选择、理由及关键依据可核，未准备新方案出现数为0；实际动作仍由PM按权限执行，不代固定审核/签收/审批。不套用旧dp3候选数量/技术ID限制。[ADDED @ 2026-10-25：毕业考推导，候选schema留设计，完整AC未锁]

VC断言：auto覆盖不同现场候选数目/非cN ID，实际choice只在提交集合且依据匹配真实引用；未备方案/伪理由/增权或代固定审批签收=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-042: invented_candidates=0 invalid_basis_refs=0 unauthorized_or_substituted_actions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-042` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F01；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-043: 八入口逐例异常

锁定AC原文：在八入口分别构造非法/缺失材料、服务不可用及不匹配或缺失选择时，均可观察具体失败/阻塞且受门控业务动作次数为0；不默认首候选/approve、不偷换通道、不造用户意图/授权或有效选择。原失败保留，可记录真实安全/失败审计而不伪造成功裁决。[ADDED @ 2026-10-25：毕业考异常对照，完整AC未锁]

VC断言：八入口分别构造缺项、错type、不可用、缺选择、错选择或依据不匹配，具体失败逐例可见，受门控动作=0、默认首项/approve/换通道/造授权=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-043: failed_entries=8 failure_actions=0 fabricated_approvals=0 hidden_failure_cases=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-043` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | N，F01/F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-044: 四类型与vision硬能力

锁定AC原文：在派发目标/要求/交付材料齐备且角色/写面允许时，dp-w-type候选精确为coding/research/review/vision；需读图且模型有图像能力的vision方案可合法派发，无图像能力时Worker启动数为0。不回退coding冒充图像能力，也不移除未列菜单的既有框架类型。[ADDED @ 2026-10-25：毕业考正反例，具体能力/派发证据留设计，完整AC未锁]

VC断言：w-type精确四候选，需图且已证能力的vision正例启动=1；无图能力负例启动=0，unknown无证亦不启动，coding降级=0，其他框架类型未删除。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-044: offered_types=4 capable_vision_starts=1 incapable_or_unproven_starts=0 coding_downgrades=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-044` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F01；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-045: 四PM编排真实组织

锁定AC原文：在PM准备真实目标/执行状态/约束并判断任务编排时，dp-pm-steer按四项分别给出不降目标的narrow、独立并行单元split、依赖当前PM上下文的direct-exec或具体人工必要性/问题的escalate；选择/实际编排证据可区分，未协调在途Worker/写面而冲突执行次数为0。[ADDED @ 2026-10-25：毕业考正向选项观测，完整AC未锁]

VC断言：pm-steer四项逐支有不降目标主线/独立并行/当前上下文依赖/具体人工问题证据，真实编排可区分，未协调在途冲突执行=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-045: steering_choices=4 goal_reductions=0 uncoordinated_conflicting_actions=0 vague_human_questions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-045` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F01/F02；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-046: Worker三分支真实终止

锁定AC原文：在Worker任务可达性分别具备充足条件、边界内不可完成及可有界查证未知时，dp-w-check-task对应选择继续/终止真实结论/继续补证；继续分支不立即伪造终态，终止分支输出完成/未完成/阻断及证据并结束本次执行。新增同步等PM指令链数为0，终止推断目标完成或key取消/收窄次数为0。[ADDED @ 2026-10-25：毕业考三分支观测，技术终态映射留设计，完整AC未锁]

VC断言：Worker充足/不可达/有界未知三场景对应三选择；continue即刻伪终态=0，terminate真实结论并结束本次=1，新增同步等待/目标取消收窄=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-046: worker_choices=3 fake_immediate_terminals=0 truthful_terminations=1 added_pm_waits=0 goal_cancellations=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-046` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F03；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-047: 补证来源预算结束

锁定AC原文：在Worker选择继续补证时，待查具体未知、可实施证据来源、权限/预算及结束判据可核；结束后按真实条件继续或终止结论，不无限续跑，不用模型补造未知意图。无结束判据/不可在边界内查证却放行补证次数为0，不由本AC设固定次数/时长。[ADDED @ 2026-10-25：毕业考有界补证，完整AC未锁]

VC断言：补证真实未知/来源/权限预算/结束判据成立后实施并真实继续或终止；无结束判据或边界不可查证放行=0、无限补证/凭空意图=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-047: unsupported_investigations=0 unbounded_investigations=0 invented_intents=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-047` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F03；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-048: stalled专门证据限定

锁定AC原文：在stalled处置送审时，停滞原因/真实状态、已尝试及产物、剩余额度/硬预算、下一方案/结束判据或遗留未完成影响/授权明确；gate仅按note批准限定继续或获授权具体遗留处置，不以预算剩余单独放行，不抹停滞/消耗、不自动降验收或取消目标。缺上述必要证据的有效放行次数为0。[ADDED @ 2026-10-25：毕业考H03专门条件，完整AC未锁]

VC断言：stalled note具原因状态/尝试产物/额度预算/方案结束判据或获权遗留影响，正例仅限定动作；缺项或只硬余额放行=0、抹历史消耗/降验收取消目标=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-048: unsupported_stall_releases=0 erased_usage_or_failures=0 reduced_acceptance_or_goals=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-048` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F05；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-049: PM真实后继与失败

锁定AC原文：在gate选steer/need_fix且PM已准备对应后继材料、角色/授权有效、尚无同事项在途后继请求时，PM发起对应dp-pm-steer/dp-auto请求且有可核调用证据；后继未发起、调用失败、返回选择及实际整改分别可见，不由gate选择推断完成。重复请求或本gate因此放行次数为0。[ADDED @ 2026-10-25：毕业考后继正反观测，不新增固定双批或执行权，完整AC未锁]

VC断言：已备合法后继且无在途时，steer和need_fix各有一次真实PM目标请求；未备/在途/调用失败/有回答/已执行分别可见，重复后继和原gate放行=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-049: steer_successor_requests=1 fix_successor_requests=1 duplicate_successors=0 parent_releases=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-049` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F02；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-050: 真执行结算及前后来源

锁定AC原文：在权限/claim/写面/硬门满足且PM或Worker真实执行所选动作时，动作证据与执行/本轮结算记录可关联，同key/task/logical_id及非递减观察时间可核；任务前后快照保留合法状态/来源，不以当前状态回填旧before，不以仅consumed/选择代执行。未执行或失败回合不得伪造成功executed，settled不代表任务done。[ADDED @ 2026-10-25：毕业考沿用既有来源/关联契约，具体消费者留设计，完整AC未锁]

VC断言：真实执行与本轮结算关联同key/task/logical_id及非递减观察时间，before不由当前回填；未执行/失败伪成功executed=0、settled代done=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-050: broken_action_links=0 backfilled_before=0 fabricated_executed=0 settlement_done_inferences=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-050` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/B/N，F02/F03；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-051: null与[]及签收数组

锁定AC原文：在允许null的任务进展快照中，未记录null与明确无项[]保持可区分，投影不回填历史或由agent-report产生执行权限；dp-sign-key的verified/unverified/unfinished_impact仍按原数组契约，[]表示真实无，缺项不能改成null造有效材料。秘密明文或历史字节改写次数为0。[ADDED @ 2026-10-25：毕业考区分快照/签收契约，非新增材料schema，完整AC未锁]

VC断言：task进展null和[]序列化及投影可区分，sign三数组缺项/null拒绝而合法[]保留；agent-report增权、秘密泄漏或历史回写=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-051: null_empty_conflations=0 invalid_sign_arrays_accepted=0 agent_report_grants=0 secret_or_history_violations=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-051` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N，F03/F10/F11；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-052: 并发实质变化和崩溃对账

锁定AC原文：在同事项重放/并发消费时，有效同事项审批与实际动作不重复，双Worker同文件写及绕既有文件锁次数为0；实质目标/契约/授权/证据变化时受影响旧批准不放行、相关重验/新判断留痕，不受影响有效证据复用。纯排版或无关新材料造成重复实质审批次数为0。[ADDED @ 2026-10-25：毕业考版本/并发正反例，识别及锁消费留设计，完整AC未锁]

VC断言：同事项并发/重放无额外审批动作、双writer或绕锁；实质依赖变化使受影响旧批准无效且真实重验，不受影响/纯排版重复实质审批=0；崩溃未知不盲重试。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-052: duplicate_effects=0 duplicate_approvals=0 concurrent_writers=0 lock_bypasses=0 stale_releases=0 irrelevant_reapprovals=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-052` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | B/N/concurrent/crash，所有Flow；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## AC-053: QG三项正向与不自动改权

锁定AC原文：在正式质量审核分别具备要求满足/证据充分无阻断、明确依据下产物缺口、要求/设计/验收依据实质问题时，dp-QG按pass/fix/reopen给可复核依据、具体缺口或依据问题及未覆盖面；正式结论及后续实际处理可区分，自动改契约、派返工或代签收/审批次数为0。[ADDED @ 2026-10-25：毕业考QG正向观测，完整AC未锁]

VC断言：QG充分无阻断/明确产物缺口/实质依据问题三场景准确对应pass/fix/reopen，证据/缺口/未覆盖明确，自动改契约/派返工/代签收或审批=0。

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---|---|---|---|
| `[VERIFY] VC-053: qg_choices=3 wrong_business_conclusions=0 automatic_contract_dispatch_or_sign_actions=0` | 真实L2生产路径完整输出 | design §7该VC所有预期字段与逐case结果 | 所有规定正向/边界/异常逐case断言成立，非汇总自评 |
| `VC-053` 对应assertions.json与原始记录 | 请求/回答/动作/来源及状态证据 | P/N，F10；实际producer/writer/consumer/projection引用及失败出口 | 测量值和原始证据一一关联，无手写成功或缺失观测 |
| 对应run manifest与完整日志 | 可复核执行与隔离边界 | 版本、命令、exit code、before/after周界，模型与业务次数分清 | 原始日志无截断；未验证明确，不以L0/观察/worker终态替代 |

## 质检门禁使用说明

本文件供后续获批quality-gate逐AC/VC核充分性。缺任何规定case、来源、真实执行、秘密/历史/权限证明或硬门时列具体缺口，不计通过。仅文档结构/Mermaid/audit PASS不代表本表产品验收。D012、human-only隔离及框架写面须先用户确认；本生成不触发签收/phase推进。
