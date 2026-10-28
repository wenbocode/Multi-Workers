# R T05l known集合快照复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358完整known-secret单权威保护。
- `packages/multi-workers/decision.py:715` CredentialSnapshot/known_credential_values；`decision_points.py:3322` known_secret_superset/_command_known_values（函数定位）。
- workers/dd-known-set-snapshot/report.md全文/evidence/runs/T05l-known-set-snapshot/基线/final/diff/RED/GREEN/measure/hash。
- T05m当前只改decision裸production采集冻结与冲突T05i测试，不修改points；T05l审归档final副本+diff，不混T05m成果。

## 审计目标
完整tuple是真冻结actual/cfg/extras/Authorization/env/legacy还是仅legacy memo，后续known_credential_values对cfg/env活读取是否违反要求、异常是否静默丢集合继续发、门/capture/client消费同一次全集与caller覆盖完整。精确API与severity，不能发送值覆盖免责非发送secret输出。
R1 cold raw泄漏已证明不是理论，本卡不算闭合，由T05m正修；旧explicit discovery0测试现获PM精确迁移，不授权真实凭证。snapshot lazy冻结/discovery_error时点/book离线failclosed、捕获正文/任意meta键值/失败输出安全。
TDD RED6F3P时序/red01/02测试自身纠正最终red03是否实现前，201/1369+skip与mutants修后、每轮日志与hash、true冷裸scope measure不得被TLDR全面PASS遮蔽。逐核读前spy/tmp env隔离与scope独立。

## 要求
PASS/CHANGES_REQUIRED针对已要求完整集合（可partial closed），原项关闭/剩余/报告过称/必要精确owner面。只report不源/test/外网/build/真实凭证读取；静态在档非实跑。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-known-set/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告证据/真实生产凭证/其他worker。

## 未覆盖面声明
T05m未完成/真实Jev/browser/平台/全仓check未验，hash未实算须声明。

## 交付格式
report≤120行，关闭表/新缺口/完整冻结与lazy语义/证据更正/下游义务/未覆盖。
