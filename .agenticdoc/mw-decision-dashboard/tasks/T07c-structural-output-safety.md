# T07c 结构字段输出安全兜底

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/design §9。
- `packages/multi-workers/decision_history.py:1` as_dict/_Sanitizer/_valid_field；workers/dd-review-history-fixes/report.md残留“结构字段不扫描”，原2P1/5P2已关闭。

## 要求
PM不接受token/identity形状可当已知secret豁免。完整读history/test及现有credential redactor接口，保存未修当前基线到证据，先写正确RED并运行保存失败，再实现GREEN。
仅history输出边界：所有输出字符串（含结构字段及任意映射键、嵌套calls/wire捕获副本、basis/flags/warnings/相对路径标签）若注入redactor识别已知secret不得原值回显。内部join/id/opaque_id生成不能被改写污染；输出结构命中secret则omit+诚实marks，不能把redacted占位符当有效ID。无redactor保持既有自由文本omit，结构只保留已验证闭集/形状现有契约，不自行读取凭证。
模拟合法形状credential进入model/transport/reason/override_by/task_key/key和嵌套键，扫page/detail序列化输出原值0，原link/stage/source内部语义不变，warning/mark不可泄漏原字段值或含secret的路径标签；实际archive旧输入路径包括自由字段原修复不退化。不改archive/schema/write方，不扩大UI。
原report不覆写，输出更正文件说明PM为何不接受review残留信任豁免。

## 写入允许面
- `packages/multi-workers/decision_history.py`
- `packages/multi-workers/test_decision_history.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-history-output-safety/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T07c-*`

## 写入禁止面
- 其他所有源/测试/报告/任务相位/真实生产记录/凭证配置/dist/依赖锁。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py -q`，只读邻接monitor可运行（T10b并行变更需注明快照，不改）。严格只读biome --error-on-warnings，不把exit0含warnings当清零；完整check越面风险明确未整跑。禁build/commit/模型/外网/服务。

## 改动历史
- PM吸收T07b PASS原finding关闭，单独收口残留结构secret通道，当前history唯一写者；T10b仅monitor无写冲突。

## 交付格式
report四段，实际基线RED/GREEN日志、输出omit/marks和内部join不改指标、明确新API及剩余未验证。不得以修后mutant冒充先RED。
