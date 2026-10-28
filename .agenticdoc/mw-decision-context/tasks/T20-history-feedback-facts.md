# T20 决策历史事实接线与简短说明

## 上下文
- goal.md: `.agenticdoc/goal.md`；让 PM/Worker 协作决策可追踪，不补造执行事实。
- 用户要求：选择列不应一直未记录；suggested 应中文解释；节点依据需接真实记录；接收签收需显示已有答案；行动与结果需简短说明；answer_source 不应空占业务展示。
- 源码锚点：packages/multi-workers/decision_history.py:2389 (_selection)、:3059 (consumed 投影)、:3146 (executed 投影)；packages/multi-workers/decision_dashboard.js:886 (policyDispositionLabel)、:1547 (basis).

## 要求
- 沿 writer→history→DOM 定位并先写真实行为 RED；只显示记录确实存在的事实，不从当前配置补阈值、不将建议/接收等同采纳或完成。
- answer_source 保留底层审计字段；无值不在默认节点展示占位，有值按需审计查看。不得删除运行能力。
- 不修改历史生产账本，不补写旧反馈，不新增决策 API/worker 派发/共享服务操作/browser/build/install/commit。
- 并行分析：writer 事实、reader 投影、DOM 可分为三个只读问题；派发会隐式调用 dp1，因此 PM 直接核查；reader 与 DOM 虽文件分离但共享契约，RED/实现/联合验证串行，唯一源码 writer 为 PM。

## 写入允许面
- packages/multi-workers/decision_history.py
- packages/multi-workers/decision_dashboard.js
- packages/multi-workers/test_decision_history_feedback.py
- packages/multi-workers/decision_monitor.py（本轮用户明确授权：仅启动时接入内存脱敏器）
- packages/multi-workers/test_decision_monitor_history_redactor.py
- packages/multi-workers/test_decision_dashboard_playground.py（仅默认启动路径断言随批准行为调整）
- 本 key T20 任务与 evidence/t20-*、pm-state.md

## 写入禁止面
- 已有其它源码/test/config/framework/生产历史账本/共享运行状态；所有外来脏改动。
- 不读取或写入真实凭证作验收；隔离测试使用假凭证。用户授权实现默认 monitor 启动时读取本地凭证建立内存脱敏器，不输出/修改、不调用模型，history GET/poll 不再发现凭证。失败仍 fail-closed；裸依赖显式注入及仅构造不发现凭证的边界保留。

## 验收命令
- 隔离 HOME/凭证环境 pytest 指定 test_decision_history_feedback.py 与已有 history/readable/dashboard 测试；保留完整 stdout/stderr/时间/argv/exit。
- npm run check 在字节保护副本，现存卡外阻塞不擅自修。

## 交付格式
- 根因/原始 RED 与 GREEN/字节基线及定向验证/未覆盖面，不以定向绿关闭 key。

## 改动历史
- 已完成限定接线修正：suggested/not-evaluated 中文、detail/policy basis、两项已存 reason 投影、接收与本轮行动说明、answer_source 关闭审计。red2 6F4P→新文件10P；五文件228P。
- 默认无 redactor 隐藏选择/答案/结果已证实；上一轮未接入默认 monitor。
- 本轮用户明确“允许”，批准上一轮提出的默认 monitor 启动时内存脱敏器接入、相应写面与本地凭证读取边界。实现/验证前不宣称该缺口已修复。并行分析：启动/read-side/default契约共享同一 deps，PM 单写与顺序合成验证；仍不派worker以免自动dp1调用。
- 上轮报告：evidence/t20-history-feedback-report.md；授权后默认启动接入已落源码，startup red2 8F2P→新11P，实际默认HTTP→DOM已覆盖选择/接收/行动与脱敏，不修改生产ledger或真实凭证。
- 最新十文件逐文件结果339P1S（monitor final曾10053失败，重跑55P1S；原失败保留，baseline/current各3次未复现，原因未证实）。完整保护check仍卡外3warnings2infos exit1/原字节无formatter变化。
- 本轮报告：evidence/t20-startup-redactor-report.md；未部署/真实browser或monitor操作，未关闭key。
