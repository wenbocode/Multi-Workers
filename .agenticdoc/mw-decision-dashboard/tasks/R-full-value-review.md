# R T05n 全值冻结独立复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358 完整known集合安全。
- `packages/multi-workers/decision.py:715` CredentialSnapshot和known_credential_values。
- `packages/multi-workers/decision_points.py:3322` snapshot gate与coverage。
- 全读 workers/dd-full-value-freeze/report.md；证据目录 evidence/runs/T05n-full-value-freeze，卡 tasks/T05n-full-value-freeze.md。
- T05m R1复审PASS。T05n编码已终态，无新编码写者。worker目录ledger原卡允许PM已吸收。

## 审计目标
同源cfg、extras、env、actual、resolved key创建冻结；legacy必要时memo；下unit刷新；所有门和capture消费完整集。
异源cfg与budget clone每面仍活读是否实际points路径可达漂移；直接CredentialSnapshot构造无基座保持live是否可达caller pin。不能仅无内部构造点免责。发现错误时known_credential_values返回部分tuple，工厂None omit是否仍安全处理结构metadata与失败输出。实际发送值仅为known集子集。
核查duck安全拒绝、类型错误零发送零快照、异常类名是否可携secret、cfg_origin身份与clone边界、ContextVar恢复、caller-owned完整coverage、无scope显式key零额外auth和probe保持。
真实RED7F1P实现前时序必须查trace，final测试基线回放不能替代先RED。red01顺序与最终差异明确。
63 passed是否实跑卡六文件命令须核完整argv、cwd和选择参数，不能仅55+8算术。1312 passed和1skip和1fail核对，dispatch基线复现仍是同key迁移债。T05m缺命令头仍待最终hermetic复验。
环境后缀全扫、tmp auth、读前spy、loopback证据和依赖hash时点核实。完整check未跑如实。

## 要求
给PASS或CHANGES_REQUIRED，全集冻结及API关闭表，新增finding、严重度、具体源行号、最小修复面、命令和时序偏差、T06前债。纯静态review，不运行测试，不读取真实凭证。hash不重算须声明。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-full-value/**`

## 写入禁止面
所有源代码、测试、任务相位、旧报告证据、真实凭证生产档案、其他worker文件。

## 未覆盖面声明
真实Jev、浏览器、平台、并发、全仓check未验。dispatch迁移债未关。

## 交付格式
使用 worker_file 写 report.md，最多130行，含关闭表、新边界、准确argv与覆盖、RED时序、精确下一卡、未覆盖声明。
