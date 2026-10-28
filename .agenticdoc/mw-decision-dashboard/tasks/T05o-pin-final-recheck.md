# T05o 不完整pin安全拒绝与最终命令复验

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358完整known集合。
- `packages/multi-workers/decision.py:1534` _decide pin校验；`decision_points.py:4383` _decision_credential_snapshot。
- workers/dd-review-full-value/report.md F1/F2/F3：None-base直接构造pin已可达，不只理论；PM不接受发送值覆盖豁免遗漏legacy。T05n写者终态，当前无编码写者。

## 要求
保存当前基线/hash，新增None-base直接snapshot pin在client/points两入口真实RED再实现GREEN。isinstance之外校验frozen_known_values非None，否则按非法pin安全拒绝0HTTP/attempt/book-snapshot、安全文本无值。工厂生成pin保持合法、cross-cfg union不删、无scope显式key0额外auth和probe保留。无需移除直接构造类功能：仅阻止未满足冻结契约对象进入发送路径，类作为非发送数据仍可构造。
不同cfg union追加不是跨face恒只增：若实际可变异源对象旧known消失，不能仅当前union更大就证明完整冻结。新增合成异源cfg在gate/capture之间变更探针，若存在raw输出/集合漂移，报告精确场景与最小owner修复，不能静默把探针标green或宽改预算/cfg生产者。允许在此卡decision/points内最小完整安全处理，但需先RED证据、不硬编码key、不删除cross-cfg合法功能。
hermetic新时点复验T05m与T05n各原卡完整六文件命令：T05m为test_decision_bare_scope_known_set.py test_decision_known_set_snapshot.py test_decision_timi_credential_snapshot.py test_decision_credential_seam.py test_decision_book_known_secrets.py test_decision_wire_transport.py；T05n为test_decision_full_value_freeze.py test_decision_bare_scope_known_set.py test_decision_known_set_snapshot.py test_decision_credential_seam.py test_decision_timi_credential_snapshot.py test_decision_book_known_secrets.py。不得只选部分用例追63/80旧数字，实际数字如实。
每轮日志记录完整argv、cwd、UTC起止、exit、隔离fixture与依赖hash前后（decision/points/mw/backends/book/wire/monitor/全部运行test）。两轮各完整独立文件，输出不tail，失败先存档。新证据不retro追认旧六文件覆盖/历史RED墙钟；可查T05n trace归档顺序，但缺证据明确保留。真实测试均tmpHOME/USERPROFILE/auth，后缀env全集清理、读前spy，不读真实凭证，无Jev，HTTP仅隔离127.0.0.1。
F1命令头旧债由当前完整复验替代，dispatch同key失败不豁免不混本卡修面。全check仍未跑不等价。

## 写入允许面
- `packages/multi-workers/decision.py`（pin完整契约安全校验）
- `packages/multi-workers/decision_points.py`（pin完整契约安全校验）
- `packages/multi-workers/test_decision_pin_contract.py`（新专项与异源探针）
- `.agenticdoc/mw-decision-dashboard/workers/dd-pin-final-recheck/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05o-*`

## 写入禁止面
- 其他源测试/真实凭证生产账/旧报告证据/typed/required/预算/placeholder/ref/registry/生成物/依赖锁/dist/相位。

## 验收命令
包目录 `python -m pytest test_decision_pin_contract.py -q` 和上述T05m/T05n显式完整命令，两轮独立日志。root只读biome --error-on-warnings/check子步，不跑write全check，不build/commit/服务/browser/全包pytest/真实模型。

## 改动历史
- PM吸收T05n工厂主链切片PASS，F2/F3不接受仅发送值覆盖豁免；F1完整argv缺失补新时点复验，历史RED顺序仍推断不追认。

## 交付格式
report≤120行，真RED/GREEN/不完整pin拒绝/异源probe结果/完整argv与实际数量/依赖hash/旧证据边界/未覆盖，不自报reviewPASS/T06放行。
