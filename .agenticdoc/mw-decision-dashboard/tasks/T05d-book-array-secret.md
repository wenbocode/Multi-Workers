# T05d book数组秘密门安全修复

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/010/011/012/design秘密零发送。
- `packages/multi-workers/decision_book.py:1010` _check_secrets/:1204 _flatten；workers/dd-review-unified-input/report.md完整P0。T05c已终态，此卡唯一book/迁移test写者。

## 要求
先完整读book/test/秘密redactor接口，保存当前未修基线与hash；新增数组秘密行为测试在未修实现真RED并保存完整日志，再实现GREEN。修复secret遍历必须递归dict/list字符串值，覆盖嵌套对象/数组数组、真实dp25两数组及其他合法DP数组；键是否进入发送体且可藏秘密须核实并同样扫描。不得为了秘密扫描改变typed/closed flatten行为，分离遍历职责，安全field path不得回显恶意key或secret值。
复用既有secret识别规则/注入配置known-set与Bearer/sk等pattern，明确到底识别哪类，不能声称未知secret全面识别。观察book含已知或规则命中secret时book-secret、零backend/HTTP调用、零snapshot、错误detail/证据无原值；使用合成secret/tmp，不读真实凭证。保留合法数组/长secret与原标量门。合法完整book仍可发送FakeBackend。
修复仅秘密扫描P0；严禁改is_placeholder/empty规则（用户确认待定）、registry/生成物/身份/ref/producer，不趁本卡扩面。
另自身更正文件：T05c“实测可发送”无档探针只静态结论、AC-019来自其他key且空容器规则属实现+D-060非本key17AC；原报告不覆写。
新增安全测试不固定错误现状追绿，不全包重跑，分页<=400行避免OOM，report骨架先落。

## 写入允许面
- `packages/multi-workers/decision_book.py`（仅secret扫描）
- `packages/multi-workers/test_decision_input_contract_migration.py`（仅新增secret回归）
- `.agenticdoc/mw-decision-dashboard/workers/dd-book-array-secret/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05d-*`

## 写入禁止面
- points/registry/export/placeholder/ref/其他源测试/旧报告证据/任务相位/真实档案/凭证/dist/依赖锁。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_input_contract_migration.py test_decision_observation.py test_decision_book.py test_decision_dashboard_contracts.py -q` 全日志/exit。严格只读biome --error-on-warnings（全仓不是单文件）与其余check子步，不整跑check越面要明确不等价；禁build/commit/外网/Jev/服务/browser。

## 改动历史
- PM吸收T05c review CHANGES_REQUIRED，先独立修P0，P1空值规则等待用户字段级确认，不通过dp裁决改需求。

## 交付格式
report≤100行，实际RED/GREEN/secret扫描覆盖与零发送指标/更正/剩余。不得称T06可开工或全AC完成。
