# T05e book完整发送面与实际known-secret注入

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358/AC-005实际Authorization/config/timi集合，不能仅env启发式。
- `packages/multi-workers/decision_book.py:1046` _check_secrets/:1102 book_state/:747 context错误path；`decision_points.py:4117` book validator/:2416 unknown key path；`mw.py:1519` _book_gate。
- workers/dd-review-book-secret/report.md全文F1P0/F2P1/F3P2，T05d数组遍历已closed，原写者终态。本卡唯一client/book/points/mw写者，保留其他会话原改动。

## 要求
保存当前基线/hash，新增行为测试在未修实现正确RED并记录完整输出，后实现GREEN。不要重新全项目漫游，必要文件全文分页<=400行。
F1：CLI _book_gate、observation decide_for→validator接入当次实际known-secret集合，复用credential_redactor(cfg,extra_secrets)现有单权威；优先注入redactor接口，不重复发现逻辑。若必须抽known values纯helper，则credential_redactor同源重构且冻结行为，所有值仅内存/repr不含/不入日志。cfg.api_key/extras.api_key、实际Authorization、timi解析(auth.json合成fixture)、env现有规则同等，不只sk/Bearer。无凭证/transport disabled/预算仍零发送，不借secret检查误触外网。
F2：扫描实际完整发送面book_state(book)，递归字符串键值/数组/context extra字段，扫描与发送不双轨；原书字段合理path保持（context前缀诊断），已知值命中book-secret零backend/HTTP/零快照，错误不echo。不能修改发送内容以隐藏漏扫，也不默删合法context字段。
F3：所有unknown slot/key错误路径安全化，恶意凭证键不得进入outcome/CLI stderr/证据；只安全化显示path不改内部closed校验/字段关联。不要依赖redactor缺失时猜已配置secret。
针对独立冷启动CLI+points/book注册链/凭证轮换做合成fixture RED/GREEN。config凭证非env非sk非Bearer的长/短值均测，auth.json只合成tmp，禁止读取真实用户凭证。必要真实HTTP仅127.0.0.1隔离fixture，拒绝0 POST，不真实Jev。
原数组遍历/typed/flatten/identity/enum/actor/snapshot/retry/签收隔离不退化；check_book新增参数与注册签名所有调用点明确，不保留不安全的默认生产绕过。纯离线check可无cfg但不冒称完整known校验，给T06明确参数义务。
禁empty/placeholder规则（用户确认待定）、registry/生成物/ref/producer语义改变，不越面修其他债。新增report先骨架，checkpoint收口。

## 写入允许面
- `packages/multi-workers/decision.py`（实际known/redactor共享接线必要，不改变client返回/传输语义）
- `packages/multi-workers/decision_book.py`
- `packages/multi-workers/decision_points.py`（validator接线/安全path）
- `packages/multi-workers/mw.py`（仅_book_gate必要接线及安全错误输出）
- `packages/multi-workers/test_decision_input_contract_migration.py`
- `packages/multi-workers/test_decision_book_known_secrets.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-book-known-secret/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05e-*`

## 写入禁止面
- 其他所有源/测试/TS/export/placeholder/ref/旧报告/任务相位/真实档案/凭证配置/dist/依赖锁。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_book_known_secrets.py test_decision_input_contract_migration.py test_decision_observation.py test_decision_book.py test_decision_dashboard_contracts.py test_decide_run_authority.py -q`；client邻接按实际必要文件窄运行报告，不全包重跑。全日志exit/依赖hash。
root严格全仓只读biome --error-on-warnings及其余check子步，不跑write越面时明确完整npm run check未整跑，分拆不等价；browser-smoke子步不是禁止真实browser，不混同。禁build/commit/真实窗口/服务起停/外网/模型。

## 改动历史
- PM吸收T05d复审CHANGES_REQUIRED：数组遍历closed但book集合未闭，精确多文件注入续卡，不通过DP更改需求，P1empty仍待用户确认。

## 交付格式
report≤130行，逐F1..3实证RED/GREEN、配置/Authorization/timi集合覆盖与0POST指标、CLI/validator/check_book API义务、实际modified hunks/剩余未验证，不自报reviewPASS/T06放行。
