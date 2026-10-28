---
type: coding
write_face:
  - .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_ts_lock.py
  - .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation/rework-r2/**
ac_refs: [AC-001, AC-003, AC-004, AC-014, AC-040, AC-041, AC-043, AC-051]
vc_refs: [VC-001, VC-003, VC-004, VC-014, VC-040, VC-041, VC-043, VC-051]
deps: [T01, T02, T03]
execution: worker
---

# T04-R2 — 原 T04 单测试面定点返工（不是第37逻辑任务）

## 状态
初始未派发/代码未开始/验证未验证。原 T04 done/exit0/acked、35局部通过与永久四case断言反例保留；新尝试不冒充先前成功或服务裁决。

## 上下文

项目目标 `.agenticdoc/goal.md:5`；原 T04 isolated卡 `tasks/isolated/T04-context-ts-generation.md`，原7stage36task及依赖/53AC/53VC不变。当前允许面测试 `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_ts_lock.py:289–331`：test_check_and_stdout_modes_write_nothing把全部dp*.json计为四旧case，再强制len=4，导致T05八新文件+四旧文件合法共存被拒。

人工批准见 `evidence/implementation/t04-r2-approval-20261026.md`（用户对明确单测试返工问项答“继续推进”）。PM实证 `evidence/implementation/t04-pm-handoff-20261026/{report.md,check.json,probe.json,probe.py,pm-green.log}`：原35passed；TS/JSON真实bytes同源、1864副本仅四允许变化；真实line296在只读十二case列表反例被触发。该探针不是T05业务生成、case有效性或L2 PASS。

接管最新 bytes，不能从live刷新副本。新鲜before为 `evidence/implementation/t04-r2-pre-dispatch-20261026/`（PM只读脚本保存，worker应完整回读并自行保存自己的before）；原测试SHA `9603a817d725f6bf16c4ab0e9b554ab2ca1d756c4fb66f5bd3cc4f6c828e635b`。四readonly peers包括context、generator、JSON、generated TS保持原T04 after，T03两test/protocol、T11consumer、四旧cases及所有其余镜像都禁写。

## 要求

1. 只修上述测试边界，并在同一允许测试内新增回归。不可删除或skip/xfail任何原保护来变绿；无重写parser/生成器/产品语义的授权。原35测试除该四case边界必要差异应保留。
2. 准确界定四旧case为原 dp1.json/dp2.json/dp3.json/dp25.json（不是glob所有dp*.json永远只有四）。仍验证四旧文件实际存在、字节哈希和命令前后不变；同时保留**全部**case目录写入边界，包含现有八活动case或其他已有文件：check/stdout不能新增、删除或改写任何case，也不能改生成TS或JSON。不得把只保护四旧文件当成削弱其他生成输出的保护。
3. 接受T04现在的四旧case状态和T05以后合法四旧+八活动case共存（case字节不要求由本任务证明业务有效）。使用独立 evidence-local private fixture目录/内存列表，不写产品decide_cases。验证缺必需旧文件、命令改/删旧文件、改/新增/删活动case以及TS/JSON改变被明确拒绝。测试变化阶段合法性，而非恢复旧入口调用或给T05提前生成。
4. **真实 red→green**：先加case共存回归，调用原真实test检查路径，在未修原assert时运行该新增回归并明确断言失败；不能用pytest.raises包住现有缺陷当“red”、不能只证明自建替代helper、解析/收集错误不算行为red。然后仅修允许测试并运行新回归与全assigned文件直到通过；保留全部原stdout/stderr/rc、最初失败与中间修正。负例中的预期拒绝应作为green安全测试，不是伪造业务PASS。
5. 完整读取当前允许测试、实际采用的generator/context及必要协议/fixture源码到EOF后再执行；记录路径/行段/EOF，未读范围明确，不称全源审计。基线哈希不是代替阅读。静态确认gen._REPO_ROOT/output_path/imports及所有子进程绝对路径绑定implementation-worktree，再执行check/stdout。仅这两只读模式：**禁止默认写生成器、T05 build_decide_cases、JSON snapshot writer或其他额外test**。
6. evidence fixture HOME/USERPROFILE/TEMP/project都在rework-r2，最小环境不继承provider/worker/project配置，PYTHONDONTWRITEBYTECODE=1、PYTEST_DISABLE_PLUGIN_AUTOLOAD=1，pytest -p no:cacheprovider；无source内pycache/config/gate/ledger写，网络/HTTP/决策CLI/service禁用。模拟subprocess只可证明fixture安全拒绝，真正生产check/stdout及同源测试仍必须实际执行，不用fake结果替代真实generation parity。
7. before/after记录允许测试完整bytes/SHA/EOL/full diff；四readonlyT04 peers及T03tests/protocol/T11consumer/四旧case保护hash、整镜像inventory和原T04 evidence hash前后核对，不能从mtime/空队列证明永未越面写或无人工writer。原证据目录只读，自己的新增rework-r2除外。live counterparts只读并记既有dirty基线，不能用主树净差揽其他session改动。
8. 只用已有授权/预算和正常watchdog，不私设新timeout/grant或重置预算。预算尾段有界收口并写实done/remaining/blockers，未知为null/未知不填造；超范围/服务不可用具体报告、不绕通道。原dp4不可用保留，不再次询问失败裁决或修活bridge。PM吸收结果后独立判定语义交接；不自称S1/L2/QG/签收通过。

## 写入允许面
- .agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_ts_lock.py
- .agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation/rework-r2/**

## 写入禁止面

所有未列面，尤其live任何源码、镜像context/generator/JSON/TS、T03 protocol/tests、T11 consumer、四旧case/八新case、无主test_decision_context.py/T09面、原task/run/output/report/log/PM-state/DAG，goal/spec/design/权限/预算/门禁/brake/活配置/凭证、other key、依赖/lock/dist/install/build/restart/commit/push。不建源symlink/junction/hardlink，不refresh-copy，不全文件格式化或覆盖其他session。TS编译/完整npm check仅T32保护等价workspace，不能在此共享副本运行写式formatter。

## 验收命令
- cwd `.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers`：`python -m pytest -p no:cacheprovider -q test_decide_registry_ts_lock.py`。
- 同文件新增回归可先用 `-k <实际新增共存回归名>` 单独red/green，再完整assigned运行；不扩其他test。
- 已静态核根及完整EOF-read的generator：`python scripts/gen_decide_registry_ts.py --check`、`python scripts/gen_decide_registry_ts.py --stdout`（输出证据内捕获）；不写生成结果。Windows stdout CRLF/text归一化与磁盘TS真正render.encode bytes分开说明。
- 本任务不跑npm check/build/install/full suite，完整check留原T32计划及独立审核/QG，不声称已经通过。

## 改动历史

原T04 run@2026-10-26T06:22:40.974Z ended06:34:10.048Z done/exit0/acked，产物与red/green保留。PM11:24Z真实35passed/check/byte parity及四case锁反例；dp4UNAVAILABLE/input-incomplete/meta.task_before未成功/无receipt。用户本轮具体批准测试-only R2。此处仅新卡未执行；执行后在自己evidence追加真实时间/差异/red-green/保护范围，不回填历史、不改原卡。

## 交付格式

唯一报告 `evidence/implementation/dpc-t04-context-ts-generation/rework-r2/report.md` 和最终回复均需 `## 结论`、`## 证据`、`## 改动清单`、`## 残留与未验证`、`## 上下文来源`。准确区分真实behavior red、纯fixture正反例、实际生产check/生成bytes、TS未编译、卡外旧债和历史pyc事件。给实际changed-files、full diff、before/after/hash/EOL、日志路径/rc/真实read EOF和所有越面写事件（清理后亦保留历史），不以done/acked替代语义交接或全源/全活树审计。
