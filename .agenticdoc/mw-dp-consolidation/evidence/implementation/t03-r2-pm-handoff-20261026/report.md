# T03-R2 PM吸收与独立复验

## 结论
R2原run真实done/exit0（03:31:06.522Z～03:38:08.302Z），output.md与report.md全文回读，实际ack已成功。独立私有环境重跑卡列两文件：166 passed in 1.12s/rc0；缺角色、非法prepared_at及合法角色无模型答案的准备阶段探针均符合预期。
第三项阶段锁仍未完整解决：合成恰八入口TS可过新形状测试，但移除旧号活材料矩阵的合法目标形态仍被本T03测试拒绝。semantic_handoff_verified=false；不据worker done/166绿测推进T04/S1。
处理裁决实际UNAVAILABLE/input-incomplete，missing_fields=[meta.task_before]，action=blocked-ask-human。**blocked on decision dp4-failure-handling**，等具体人工处理；未重复请求、修活桥接/源码或派新返工。新请求关联真实R2，不改上一轮原T03失败；两次均没有有效decision_id，不写executed/settled回执。

## 证据
- 当前四文件bytes/SHA/EOL与R2 after-manifest及after-bytes逐字相同；13个handoff表路径独立核hash一致：check.json（实测03:40:40.460788Z）。所有import均来自implementation-worktree。PM只写本目录证据，private fixture/home/project/temp、最小env禁cache/plugin/pycache，fake测试，无HTTP/服务/CLI/生成器。
- pm-green.log：原两文件完整命令/stdout/stderr/rc；pm-probe.log、probe.json：八入口缺角色拒绝、非法ISO拒绝、合法无choice/basis预备通过；合成eight.synthetic.ts非T04真实产物。
- `test_decide_registry_contract.py::_ts_required_fields`约448仍断言必须有dp4-failure-handling，解析八active目标fixture时给“The required_if matrix was not parsed”，实际已经解析到八行。
- `test_ts_required_rows_follow_the_registry_stage`约497在post-T04分支仍无条件要求retired_rows==四条LEGACY_TS_ROWS；把解析结果设为八active合法REQUIRED_STATE_FIELDS且无旧行，同一新测试明确拒绝。probe.json分别记录post_t04_active_only_matrix及active_only_real_parser的rejected/原始断言。
- T11实际卡tasks/isolated/T11-ts-tool.md全文回读：目标为工具消费八生成合同；T04/T11均无本T03测试文件写权。这里证明目标演进阻碍，不声称真实T11已执行或新增活漏洞。第一次猜T11-ts-tool-contract.md路径ENOENT后列实际文件再完整读，未当错误路径作依据。
- 原red-02-tests-before-impl.log全文读：16 failed/150 passed，前8例实际首先失败在None，后8首先失败在not-an-ISO-timestamp；并非每一循环非法值都在red轮被执行证明。green-03实际166通过；原red-01测试顺序错误保留不当产品故障。

## 残留与未验证
1. 不宣称三项全修或S1通过。第三项尚需消除解析器dp4存在强制与post-T04四旧行永久强制，同时保持历史只读/字段非法拒绝/生成单源，不能简单删验证换绿。
2. 新wiring测试仅检查所引用整文件含ID，不证明指定行真正调用或受控actor/执行链有效；worker合成probe指向注册文件正例不能当真实接线。下游真实caller及T33审计仍必需。
3. PM读两当前测试EOF、完整R2 diff与证据脚本及报告；未声称7102生产行全审计。Worker明确没有遵守开工生产文件EOF要求（哈希不是阅读替代），过程债保留，后续writer须按原卡EOF执行；不通过修改原卡/失败历史消除。
4. 报告数值勘误：decision_points.py实际304640→305745为+1105B（非+462）；新测试before实际31311B（非报告31131）；13handoff表只有decision_points.py一项变化，其他12项不变，两修改测试不在该13表里。四产品表3变1不变，合并去重是15路径，不把“13含3变”当事实。
5. mtime扫描R2_START人为03:33，而run起点03:31:06；扫描不能覆盖开工最初约114秒，更不能证明独占作者。当前hash相等仅证明这些边界当前未漂移，不证明全活树干净/没有人工writer。父证据29文件mtime无新增也不等于逐原hash核验。
6. 第一次PM checker误以after-bytes保留路径层级，实际capture_after.py按basename复制，rc1/无产品变化；完整读helper后仅改PM检查脚本定位，第二次执行rc0。不是产品故障，不改worker证据。
7. 未真实TS生成/parity/编译/依赖解析、T05 case、CLI replay、人面/H12、真实provider/basis/vision、npm check、全L2/QG/签收/部署。没有code切回主树/config/service/gate/ledger/预算/grant/phase动作。

## 上下文来源
原隔离T03-R2卡、人工批准t03-rework-approval-20261026.md、R2 worker output/run与rework-r2/report.md（全文）；当前两测试、完整r2-changes.diff、run_pytest/probe_stage/capture_after、red-02/green-03、after-manifest/write-scope-check；T04与T11实际隔离卡；PM本目录check.py/check.json/probe.json及两log。旧T03/R2记录不改。
