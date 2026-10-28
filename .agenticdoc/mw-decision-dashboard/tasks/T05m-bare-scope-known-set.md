# T05m 裸production scope完整known集合

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358完整known集合保护，不限实际发送值。
- `packages/multi-workers/decision.py:1656` _ensure_wire_redactor/_decide；`packages/multi-workers/test_decision_timi_credential_snapshot.py:1` test_explicit_cfg_api_key_leg_wins_and_is_frozen_per_call（函数定位）。
- workers/dd-known-set-snapshot/report.md R1及logs/measure.json cold_capture_stores_frozen_leg_raw=true。T05l写者终态已ack，当前唯一decision新写者。

## 要求
保存当前基线/hash，新测试真实RED（裸client+显式cfgA+未提前gate冻结production scope，合成authB在response正文/任意metadata键值/失败输出）再实现GREEN。不得以现无内部调用点/旧测试要求discovery0豁免已证raw泄漏。
仅必要production采集路径在capture前完整冻结known集合，门无需预热。一个逻辑call自注入完整known超集，重试不再发现，下call刷新；发现异常零发送/零snapshot/detail无值无异常message。actualAuthorization仍A，probe/credential_status/无scope显式key可继续原零多余discovery语义，禁全局额外读auth。
精确更新test_explicit_cfg_api_key_leg_wins_and_is_frozen_per_call与新需求冲突的次数断言：无scope显式key仍0，production scope为安全集合允许一次合成legacy发现，保持Authorization优先级/每call刷新/retry稳定等全部原断言。不是移除业务功能，不降安全，不删测试。
所有测试tmpHOME/USERPROFILE/tmp_auth_json_path、env后缀全集清理、读取真实路径前spy拦截；仅合成fixture，允许隔离127.0.0.1 HTTP，不授权真实凭证读取。全部日志不得合成值误称已掩码。ContextVar/caller-owned覆盖保留，未知scope无回调既有failclosed不变。
检视T05l“全tuple冻结”实际cfg/env是否仍每面活读，仅在本卡报告指出精确未闭合面，不越面points/mw修；如必须依赖变更报PM。snapshot并发单线程注记非安全实测。

## 写入允许面
- `packages/multi-workers/decision.py`（裸production scope冻结）
- `packages/multi-workers/test_decision_timi_credential_snapshot.py`（只冲突次数/对应新增scope边界断言）
- `packages/multi-workers/test_decision_bare_scope_known_set.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-bare-scope-known-set/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05m-*`

## 写入禁止面
- points/mw/backends/book/wire/monitor/其他tests/registry/生成物/required/typed/placeholder/ref/预算/旧报告/真实凭证生产账/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_bare_scope_known_set.py test_decision_known_set_snapshot.py test_decision_timi_credential_snapshot.py test_decision_credential_seam.py test_decision_book_known_secrets.py test_decision_wire_transport.py -q` 全日志/独立每轮日志/依赖hash，外层tmpHOME隔离。
root只读biome --error-on-warnings/check子步，完整check未整跑不等价，禁全包pytest/build/commit/服务/browser/Jev/真实凭证。

## 改动历史
- PM不接受T05l自报PASS全面闭合：R1实有measure raw泄漏，按完整known安全要求批准精确旧测试次数迁移，无scope功能仍保留。不授权真实凭证读取。

## 交付格式
report≤110行，RED/GREEN、裸scope cold与下一call刷新、发现异常、无scope0发现原语义、冲突测试精确diff、T05l措辞更正/剩余，不自报reviewPASS/T06放行。
