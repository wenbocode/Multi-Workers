# T05n cfg/extras/env全集冻结与redactor安全边界

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358 known集合单权威。
- `packages/multi-workers/decision.py:715` known_credential_values/CredentialSnapshot；`decision_points.py:3322` _command_known_values（函数定位）。
- workers/dd-bare-scope-known-set/report.md R2；workers/dd-review-known-set/report.md 更正1/P4。T05m终态ack，本卡唯一decision/points写者。

## 要求
全文分页读源，保存当前基线/hash，合成cfg/extras/env在gate/capture之间变更的行为测试先真实RED再GREEN。snapshot显式冻结当次cfg/extras/Authorization/env文本全集与实际key，legacy按现有必要scope/门时机一次memo；后续redactor消费冻结值不再次活读cfg/env。下unit刷新，旧unit集不改变，不跨调用缓存。保留无scope显式key0额外auth读取、probe/credential_status原语义；读取内存cfg/env不等于必须增加auth发现，不能借此回退T05m安全。
直接credential_redactor对discovery_error本身failclosed（安全omit或类型安全拒绝），不靠两sender调用序；外来duck snapshot非法/缺完整契约不得静默缩成空集合后发送，纯API安全错误不含值。保留caller-owned验证/不替换、ContextVar finally/reset、缺凭证/disabled/预算0发送0snapshot及sink写失败业务不变。
完整合成known集合冻结测试：env旧B被移除/改C仍旧snapshot覆盖B，下unit覆盖C；cfg/extras同理；正文/任意metadata键值/失败输出均不可旧known raw落盘。actualAuthorization仍当次key，不将集合包含关系称相等。无真实凭证读取，tmpHOME/USERPROFILE/auth及后缀env全清，读前spy；真实HTTP只隔离127.0.0.1。
不得改typed/required/empty/ref/预算/registry/book/mw/backends；必要API调用点只points调整，mw已有snapshot调用须不破坏。

## 写入允许面
- `packages/multi-workers/decision.py`
- `packages/multi-workers/decision_points.py`（冻结集合消费必要接线）
- `packages/multi-workers/test_decision_full_value_freeze.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-full-value-freeze/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05n-*`

## 写入禁止面
- 其他源测试/旧报告/任务相位/真实凭证生产/依赖锁/dist/registry/生成物。

## 验收命令
包目录 `python -m pytest test_decision_full_value_freeze.py test_decision_bare_scope_known_set.py test_decision_known_set_snapshot.py test_decision_credential_seam.py test_decision_timi_credential_snapshot.py test_decision_book_known_secrets.py -q` 全日志，每轮独立归档，稳定依赖hash。
root只读biome --error-on-warnings/check子步，完整check未跑不等价；禁全包pytest/build/commit/Jev/服务/browser/真实凭证。

## 改动历史
- PM不接受cfg/env活读仅措辞豁免。T05m交付80P/1294+skip仅切片，独立review并行审归档final，不混本卡。

## 交付格式
report≤110行，真实RED/GREEN/完整字段冻结/刷新/redactor异常与外来对象failclosed/未覆盖，不自报T06放行。
