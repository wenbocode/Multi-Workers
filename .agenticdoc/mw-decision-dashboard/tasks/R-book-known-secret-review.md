# R T05e 完整known-secret门独立复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358/AC-005。
- `packages/multi-workers/decision.py:500` known_credential_values/known_secret_redactor/secret_hit；`decision_book.py:560` check_book与book_state；`mw.py:1499` _book_gate；points validator链。
- workers/dd-book-known-secret/report.md全文/evidence/runs/T05e-book-known-secret；workers/dd-review-book-secret/report.md F1P0/F2P1/F3P2。

## 审计目标
逐F1..3关闭：实际cfg.api_key/extras/Authorization/timi/env集合与wire同源是否真冻结，短/长值/轮换/凭证解析失败/坏redactor failclosed。CLI _book_secret_redactor fail-soft是否使已配置known秘密校验退回仅pattern并继续发送，缺/坏配置与transport门保持零发送。
完整book_state发送面扫描keys/values/context额外字段、诊断path/所有错误正文不echo；known集合repr、异常、日志/side账安全。validator冷启动与透传参数，不依赖偶然导入。构造门集合时与实际发送时凭证配置变化的边界明示。
证据RED17/2、后补coldstart2逆向还原只证明基线行为不替代实现前RED，GREEN21/378/295/103+skip，基线359P17F数与验收数量自洽；不把0attempt+FakeBackend称真实HTTP抓包。
隔离违规：report承认运行test_decision_observation含book时读取真实~/.pi/agent/auth.json，原卡禁读真实用户凭证。确认具体调用路径，不读真实文件；给最小test fixture/环境HOME隔离+复验写面建议，该邻接证据不能作为hermetic验证。其他专项tmp隔离是否完整。
P1empty等待用户确认，无规则改动；monitor义务文案与T06必须当次redactor参数明确。完整check未整跑，静态旧日志非本人实测。

## 要求
完整必要源/测试分页读；PASS/CHANGES_REQUIRED，F关闭表/新严重项/证据偏差/隔离复验建议，具体path:line触发与最小owner面。只自身report，无源/测试/服务/外网/build/真实凭证读取。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-book-known-secret/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告/真实档案凭证/其他worker。

## 未覆盖面声明
真实Jev/HTTP/browser/平台/全仓check未验，配置文件只读不等于被授权读真实用户凭证。

## 交付格式
report≤140行，逐F关闭/新finding/隔离偏差/精确续卡/未覆盖。
