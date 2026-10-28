# R T05g CLI配置快照独立复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358 known集合与预算零发送。
- `packages/multi-workers/mw.py:964` _decide_config_snapshot/_book_gate/_decide_run/_decide_ask/_decide_book_check（函数定位）；`decision_book.py:960` _limits。
- workers/dd-cli-config-snapshot/report.md全文与evidence/runs/T05g-cli-config-snapshot/基线/RED/GREEN/measure/adjacent；workers/dd-review-book-known-secret/report.md N2。

## 审计目标
同一cfg对象贯通book门与真实client，run/ask/check各分支，无二次凭证读取/残留client重配置，跨命令轮换，异常fail-soft是否保持明确零发送/退出码不移除intentional功能。
标题每命令只读一次实际3→2/mw2→1，_limits第二读预算可能与发送cfg预算不同，给明确边界或缺陷，不能仅因int就推无害。解析timi auth是否门/发送再次解析真实credential导致另TOCTOU，与cfg对象一致区分。
RED3/5先实现时序/GREEN8/166与逆向重建只补证，actual gate_cfg is sent_cfg与Authorization来源A；coldstart零HTTP是何证据不冒称抓包。全源码/test必要全文分页。
测试delenv仅5具名是否遗漏任意credential后缀环境，real auth tmp隔离是否完整，不读真实用户凭证。158baseline/166GREEN/222邻接与375+1失败核实；dispatch属于同keyT04迁移债不豁免，基线复现仅不是T05g新回归。
未跑tsgo/browser-smoke等与完整check如实留账，普通warnings未清零。

## 要求
PASS/CHANGES_REQUIRED，具体path:line/trigger/severity/minfix、原N2关闭表、新预算/实际resolved credential边界，T06前债项。仅report，无源/测试/服务/外网/build/真实凭证读取。静态在档非本人复跑。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-cli-config/**`

## 写入禁止面
- 所有源/测试/任务相位/旧证据报告/真实档案/其他worker。

## 未覆盖面声明
真实Jev/HTTP/browser/全仓check/跨平台未验；P1empty仍待用户确认。

## 交付格式
report≤120行，关闭表/新finding/证据偏差/精确下游义务/未覆盖。
