# T05g CLI书门与发送同一配置快照

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358实际known集合安全门。
- `packages/multi-workers/mw.py:964` client cfg/:1499 _book_secret_redactor/:1531 _book_gate；workers/dd-review-book-known-secret/report.md N2双读TOCTOU。
- T05f已终态，两个测试隔离已交付380P；本卡仅mw/newtest独占，不改已有test。

## 要求
完整读mw.py分页<=400行及实际CLI book调用链，保存当前基线/hash；先合成配置轮换行为测试正确RED后实现GREEN。门redactor与client发送必须用同一DecisionConfig对象/不可变当次快照，避免gate集合A→client配置B。检查run --book/ask及book check路径真实调用点，不猜签名。复用known_secret_redactor单权威，不重造凭证发现。
测试可在配置读取spy第2次返回B，不读真实凭证、不启动模型；门拒绝含当次known A材料0backend/attempt/snapshot，合法材料client必须绑定同一次cfg。若发送使用A则不能冒称已经使用轮换B；新命令才重新解析。bad配置/disabled/缺凭证仍零发送，异常/detail/config repr不漏secret。
不能删除intentional功能/改public语义，若需要其他源写面先报PM；不通过复用旧client/scope造成跨命令泄漏。独立冷启动CLI tmpHOME/USERPROFILE/auth/config隔离。新测试读前spy防真实用户auth访问。
原check_book参数默认离线规则/生产完整known义务保持。placeholder/empty/registry/ref/producer全禁改，P1empty待用户确认。

## 写入允许面
- `packages/multi-workers/mw.py`（仅CLI book门/client配置透传）
- `packages/multi-workers/test_decision_cli_config_snapshot.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-cli-config-snapshot/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05g-*`

## 写入禁止面
- 所有其他源/测试/旧报告/任务相位/真实凭证记录/placeholder/ref/registry/export/依赖锁/dist。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_cli_config_snapshot.py test_decision_book_known_secrets.py test_decide_run_authority.py test_decision_observation.py -q` 全输出exit，外层HOME/USERPROFILE隔离。必要CLI邻接窄选名单不全包。
root全仓严格只读biome --error-on-warnings与check子步，未整跑完整check明确不等价；禁build/commit/browser/服务/外网/Jev。

## 改动历史
- PM吸收T05e PASS和T05f隔离交付，N2配置双读TOCTOU另卡收口，不接受文档豁免实际known集合差异。

## 交付格式
report≤100行，实际RED/GREEN/读取次数与cfg同一指标/CLI入口覆盖/隔离/剩余，不自报reviewPASS/T06放行。
