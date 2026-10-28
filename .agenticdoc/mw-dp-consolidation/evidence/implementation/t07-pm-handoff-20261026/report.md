# T07 PM独立终态吸收与交接处置

## 结论

T07真实run `dpc-t07-policy@2026-10-26T12:08:35.966Z` ended12:17:46.874Z、done/exit0；output/report全文吸收，`ack_worker_result`已实际成功。**semantic_handoff_verified=false，需定点返工**。done/acked/原31green均保留，但不放行相关后继/S2或L2/QG/签收。

PM两次新鲜assignedfile验证均31passed/rc0：12:21:06.732947Z bootstrap调用pytest.main（31passed0.22s），12:22:33.637993Z原文命令加-B（31passed0.20s）。纯函数负例实测却返回allowed=true；不是生产恢复效果，不能由本层green宣告failclosed边界齐备。

## 证据

目录：`.agenticdoc/mw-dp-consolidation/evidence/implementation/t07-pm-handoff-20261026/`。

- `check.py`/`bootstrap.py`/`probe.py`及`check.json`/`probe.json`/`pm-green.stdout|stderr`/`pm-probe.stdout|stderr`：fresh私有minimalUTF8环境，HOME/USERPROFILE/TEMP/TMP/TMPDIR和DPC_T07_FIXTURE_ROOT均在PM新证据目录；禁pyc/autoload/cache，bootstrap和probe拒绝socket连接。实际policy/config文件路径绑定implementation copy；没有import T06/T08/CLI/conductor。
- `supplement.py`/`supplement.json`/`pm-literal.stdout|stderr`：实际argv `python -B -m pytest -p no:cacheprovider -q test_dp_consolidation_recovery.py`，cwd副本multi-workers，31passed0.20s/rc0。该literal进程没有bootstrap socket钩子，但assignedtest完整静态读取、仅stdlib/policy与只读config，无HTTP/CLI调用。
- 当前policy完整1785行及test完整1520行到EOF已read；after-bytes保存原bytes/SHA/EOL：policy60498B/f4c44456316b8c60c7934a209de389ef6366aa864f026f9ba5fba40569dde6bb/1785LF；test53478B/434412b3ea60e60807ea23b52cdc474e892457a0a1747ecf7cb6bf809380a974/1520LF，均0CRLF。新文件pre-dispatch真实不存在，live同名文件仍不存在。
- `pm-full.diff`117458B、SHA120b978c475d86145eaffe26f4bd94b1551ddb0d7c7d24a63e8f61f9c253b62f，与worker mine.diff逐bytes相同；两个addedhunk，产品内容全文读取（原diff只读边界段，其整体字节机械重建核等，不冒充逐diff独立全读）。
- `before-inventory.json`/`after-inventory.json`：1883→1883、verification_net_changes=[]；对S2基线1864，七授权产品面有变化，另14pyc均在exact允许面之外。其余基线文件（含T03/T04/四旧case/TS/JSON/consumer）hash不变，非全live审计或历史独占作者证明。literal补验前后整inventory亦相同。T08两live counterparts比frontier beforebytes不变/non-samefile；五newfile中T07live缺失已核，未fresh覆盖其余三live状态/全dirty。

### PM真实行为负例及根因

`probe.json`三合法控制均allowed=true、有非空对应scope。下列七负例均allowed=true/reasons=[]（读当前真实产品函数，不替换helper、不改生产fixture）。authority仅内存合成，非真实grant。

|反例|观察|根因及定位|
|---|---|---|
|pending-outside-policy|requested key:outside不在policy scope却allowed=true、resume_scope=[]|evaluate_pending_review仅核authority_source覆盖，未核policy.scope覆盖；末尾直接intersection，不把欠覆盖变成阻断|
|pending-missing-scope|required_scope缺失仍allowed=true、resume_scope=[]|`_str_tuple(...) or ()`吞掉缺项，空scope使授权覆盖检查真空通过|
|halted-unverified-guard|hard_guard_active=true，仅非空自报clear字符串、未提供verified仍放行recovery:halted|evaluate_halted_recovery的`hard_guard_cleared_verified`默认True，未记录机器验证被当已验证|
|halted-unknown-origin|halt_origin缺失仍放行|缺项变空串并落普通technical分支；未知人工停止/撤权状态被当不受限|
|halted-unrelated-authority|note改为另一authority_ref，原rule引用未核仍放行|只resolve note.authority_ref，不resolve policy.recovery.authority_ref及适用关联|
|breaker-unrelated-preauthorization|request改为另一preauth引用仍放行recovery:breaker|evaluate_breaker_recovery只resolve request引用，rule引用仅parse存储、不参与判断|
|breaker-unknown-disable|user_disabled缺失仍放行recovery:breaker|只拦`is True`，unknown/missing被当未停用|

`supplement.json.revoked_policy_recovery_ref_bypassed`进一步最小复现：**policy.recovery.authority_ref对应record revoked=True，request指向另一scope相同的record，allowed仍True/recovery:breaker/reasons=[]**。证明这不是仅“允许另一合法授权别名”的争议：政策引用的撤权未被核验。修复不能简单全局强制ref相等来拒绝H11新人工恢复授权；必须核各引用、真实关联/范围及撤权，在已批纯接口范围内保持合法新授权路径，不自建信任来源。

以上是本层权限verdict缺口而非已发生业务动作；未知身份/授权资料不得由PM补造。调用方真实受控writer/渠道来源、决定有效性及锁内再核依原后继责任，不要求纯模块自己证明生产人资格。

### 原证据使用限制

原red为module-absent collection/import rc2，不是先行为断言红；worker自己已披露。四mutant负控是后置断言证明，不冒充TDD红。green-01/02失败和原report/全部日志保留；八VC计数只为被测纯verdict，不是53VC/L2或H12真实恢复全链。output的Ledger Malformed为framework warn，原输出留底，不改framework/原seed来清警告。

## 残留与未验证

1. 上述scope/授权引用撤权/unknown机器验证与停止条件需有界原T07两产品文件定点返工及同测试真实行为red→green，原run/卡/证据不重写。**本轮未获新的bounded rework批准，未创建/派R2或自行修业务代码。** 本轮仅为新T07实际task_key作一次dp4处理请求（不是重问原T03/T04请求），传真实task_before后返回`{"available":false,"unavailable":"input-incomplete","action":"blocked-ask-human","missing_fields":["meta.task_before"]}`；blocked on decision dp4-failure-handling，无有效decision_id/receipt，未重问/绕通道/修活桥。输入审计限制：传入question=`failure_strategy`但注册question未核，material误混了dp2/dp3/dp25准备字段，dp4 material schema未核；这是PM调用质量欠项，不能单凭此输出断言仅live bridge有缺陷或已排除输入问题，不填缺字段或换入口来重试。原T03/T04的独立不可用历史不改。
2. T08自报20:16:49未禁pyc的python-c产生14pyc，两cache目录删除被writeface守卫拒绝。T06/T07只凭名称/mtime和自己的运行声明断言非己不充分；PM保留归因层级=存在性独立核实+T08自报，不证明绝对独占进程作者。**worker让PM清理不授权限**：未删/改14文件、不绕守卫；精确清理需人批准，须保留当前fullbytes/SHA/EOL相关历史后删除且核其它文件不变。
3. T06/T08也真实done/exit0、report/output已全文吸收并分别工具ack；独立完整产品/测试/反例复验待做，不能用65/73worker声明放行T09/T10或其它依赖。T05还待T09。
4. 无额外test/生成器/T05、npm check/build/install/reload/restart/configmigration/commit/push；无live源/config/grant/gate/ledger/预算/watchdog/Phase修改；真实human/H12、L2/TScompile/T32完整check/独立review/QG/signoff未验证。

## 上下文来源

当前root/index/claim恢复及audit EXECUTE PASS、goal.md；原T07isolated卡、已批design §4.2/4.5、S2基线及实际run/output/report/green/importred/after/pycache记录；PM完整当前两productEOF及只读autopilot/config.py；当前私有verification/probe/diff/hash/fixture输出。T03-R3/T04-R2前置交接只作原DAG技术前置，phase audit/ack均不代产品验收。原7stage/36task/53AC-VC及独立key未结债保持。
