# T05l 完整known集合单权威快照

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358实际cfg/Authorization/timi/env集合单权威，所有公开输出/出站门均保护known-secret，发送值覆盖不足以免责。
- `packages/multi-workers/decision.py:715` known_credential_values/:1656 _ensure_wire_redactor；`decision_points.py:3322` known_secret_superset（函数定位）。
- workers/dd-review-credential-seam/report.md R1/R2/R3，T05i/j已切片PASS，T05k已复审PASS所有编码写者终态。

## 要求
全文分页读取被改文件，保存当前基线/hash，新测试先真实RED再实现GREEN。CredentialSnapshot冻结当次actual key及完整known安全超集（cfg/extras/实际Authorization/legacy timi/env）。单一decision发现权威注入，points不能再次活解析legacy leg；wire自注入/CLI/book/points都消费同快照known集。下一逻辑调用/命令重新解析刷新，不跨调用缓存，不减去T05e双key保护。
合成explicit cfg A+auth B场景：门与capture同次覆盖A+B，auth中途轮换C不导致各面集合不一致，下一调用覆盖A+C。实际Authorization仍A，不能把发送值含A当B可明文落盘免责。裸production scope+显式key通过真实DecisionClient链验证非发送known B也不落正文/任意metadata键值/失败输出，不手造event。
已缺凭证/disabled/预算零发送，不为了采集超集提前读真实auth或启用transport，tmpHOME/USERPROFILE/auth及后缀env全集隔离，安全spy在真实路径读取前阻断，所有凭证合成；唯允许网络隔离127.0.0.1，无Jev。
发现异常不可静默丢known集然后发送，明确failclosed/安全错误不回显secret；不能错误改变capture存储失败不影响业务的既定语义（凭证发现安全门与sink故障区别）。保留_http_post四参/返回键/probe活刷新。
caller-owned scope必须覆盖完整冻结known集而不仅actual key，缺覆盖则零发送/零snapshot；已覆盖保持不替换与finally复位。caller跨cfg pin混用只可用性拒绝不允许错发，给明确单线程client契约注记不借此删并发功能；若发现真实并发新增泄漏报PM，不越面宽改。
现有credential_snapshot/known_secret_superset API可精确调整，不重写seam/typed/placeholder/required/refs/预算/registry。

## 写入允许面
- `packages/multi-workers/decision.py`（完整冻结known集与redactor消费）
- `packages/multi-workers/decision_points.py`（去重复发现/完整caller coverage）
- `packages/multi-workers/test_decision_known_set_snapshot.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-known-set-snapshot/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05l-*`

## 写入禁止面
- mw/backends/book/monitor/其他test/schema/registry/生成物/ref/typed/placeholder/required/预算/旧报告/任务相位/真实凭证生产账/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_known_set_snapshot.py test_decision_credential_seam.py test_decision_timi_credential_snapshot.py test_decision_book_known_secrets.py test_decision_required_refusal.py test_decision_observation.py -q` 全输出，各轮独立日志；稳定依赖hash含mw/backends/book/monitor。
root只读biome --error-on-warnings与check子步，完整check未整跑明确不等价，禁全包pytest/build/commit/服务/browser/真实外网。

## 改动历史
- PM吸收T05k PASS，T05j R1/R2 known超集缺失/漂移不接受文档豁免，串行唯一decision/points写者。T05k数字已PM勘误11+8=19，401/729各仅1完整日志。

## 交付格式
report≤120行，真实RED/GREEN，完整known冻结/调用刷新/裸scope/caller覆盖/异常failclosed各指标，必要API与未覆盖，不自报T06放行。
