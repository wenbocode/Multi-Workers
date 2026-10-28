# T05i timi实际凭证与门/capture同次快照

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；design.md:358实际Authorization集合采集安全。
- `packages/multi-workers/decision.py:645` known集合/:1222 retry调用；`decision_backends.py:981` timi每attempt resolve。
- workers/dd-review-cli-config/report.md N1；T05g decide.json双读已closed。T05h唯一points/book/生成物写者，本卡仅decision/backends不冲突。

## 要求
完整读允许文件分页，保存未修基线/hash，先合成env/auth resolver轮换A→B行为测试真RED后GREEN。目标一次逻辑client调用/重试全部实际Authorization与门known集合、wire捕获集合一致，新逻辑调用重新解析获取B，不把后续轮换secretB泄到capture。
必须核查book门发生在client调用之前的解析时点，仅backend freeze可能仍门A/clientB；明确安全快照对象/纯API供CLI与observation后续接线。不要冒称这张切片能自动解决owner外调用方。优先既有cfg显式api_key传输机制，不重复凭证发现、不改resolve全局语义，不跨调用缓存。
仅合成凭证/tmpHOME/auth env+读前spy，不读真实用户凭证，不外网/Jev；隔离127.0.0.1真实HTTP捕获Authorization可用以验证重试同A，下次调用B，日志secret值不落（仅same/different指标），_http_post四参及冻结client返回不变。
显式cfg api_key leg/缺凭证/disabled/全局budget零发送回归，capture失败不改业务/ContextVar reset不退化。不移除动态凭证刷新功能：刷新粒度由每attempt改为每逻辑调用，报告给调用方固定快照接线义务。
如果完整闭合必须points/mw/book改动，报告精确API需求/未覆盖并停，不能越面与T05h争写。禁placeholder/registry/limits/TS/生产记录改变。分页<=400行避免OOM。

## 写入允许面
- `packages/multi-workers/decision.py`（凭证快照必要API/每调用）
- `packages/multi-workers/decision_backends.py`（timi凭证消费）
- `packages/multi-workers/test_decision_timi_credential_snapshot.py`（新专项）
- `.agenticdoc/mw-decision-dashboard/workers/dd-timi-credential-snapshot/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T05i-*`

## 写入禁止面
- points/book/mw/其他测试/registry/生成物/limits/旧报告/任务相位/真实凭证配置/生产账/dist/依赖锁。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_timi_credential_snapshot.py test_decision_wire_transport.py test_decision_book_known_secrets.py test_decide.py -q`，外层HOME/USERPROFILE tmp隔离，全日志exit/hash，其他必要邻接窄选不全包。
root全仓只读biome --error-on-warnings/check子步；未整跑完整check明确不等价；禁build/commit/真实browser/服务/模型外网。

## 改动历史
- PM吸收T05g PASS，N1实际timi活解析集合不一致不接受文档豁免；本卡transport切片独占，owner外接线待T05h结束串行。

## 交付格式
report≤110行，真实RED/GREEN、门/capture/actualAuthorization分别是否闭合、新API与owner外接线、每attempt/逻辑调用刷新指标、剩余，不自报整体PASS/T06放行。
