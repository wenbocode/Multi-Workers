# T20 启动脱敏器接入（用户明确允许后的增量）

## 授权与边界
用户明确“允许”上一轮提出的方案：默认 monitor 仅启动时读取本地凭证，建立内存脱敏器；不输出/修改凭证、不调用模型，history GET/poll 不重新发现凭证。T20 卡已扩写面到 decision_monitor.py、新 test_decision_monitor_history_redactor.py 与默认启动路径旧测试。

并行分析：deps/start/read-side/default契约共享同一实例，PM 唯一 writer，RED/实现/联合验证串行；不派worker避免自动dp1请求。实际验收只使用隔离 HOME/USERPROFILE/PI_CODING_AGENT_DIR、假 auth.json 与配置、private random-port synthetic monitor；未读取用户真实凭证或起停共享实例。

## 实现与实证
- `default_monitor_deps` 显式设置 redactor_on_start=True；裸依赖缺省 False，既有显式注入边界不变。
- `MonitorInstance.start` 在绑定成功后、发布身份和 HTTP 服务前初始化一次；通过 dataclasses.replace 生成实例本地依赖，避免复用模板的跨项目快照混用。
- 成功/None/异常均关闭实例 redactor_factory；历史、health 和后续 playground 读请求不重新发现凭证，不把异常消息（可能含凭证）返给页面。None/发现异常导致的无可用脱敏器沿既有 history `_free` fail-closed omission，playground 503。
- 兼容实例复用仅附着，不初始化新快照。只构造 deps/instance 不发现凭证，启动不创建 playground 或发模型请求。
- 原默认 factory 的 `credential_snapshot(cfg)` 在配置有 key 时跳过 timi 链。新安全测试发现该差异后，改为 `credential_snapshot()` 冻结本地/env 的既有 timi 链，再通过 `credential_redactor(cfg, snapshot=...)` 合并项目配置值；不改决策 transport 的凭证优先级或任何底层 resolver。
- 真实 synthetic writer→默认 startup→monitor HTTP→shipped JS DOM 显示 research 选择、接收答案/原因、行动结果/原因、中文 suggested；POST 除 bootstrap 外为0，storage writes为0。
- 配置值与假 auth 值故意放入 synthetic lifecycle reason，实际 HTTP 详情两者均脱敏；源 config/auth/ledger 原字节不变。

## TDD 与新鲜验证
- startup red1 6F4P；发现测试 root.name 相同的fixture问题并改为 parent.name，不把此项当产品行为 RED。red2 **8F2P**：默认未启动解析、缺脱敏器、失败未启动处理、跨root快照、兼容reuse、playground未应用解析值。
- green1 新文件1F9P，暴露 cfg key 跳过本地 auth 已知值；该安全断言先于 factory 修正。旧 playground1F12P来自已批准的启动 redactor 断言变化。保留原日志，调整该旧断言不是放松安全。
- green2 新文件10P，旧 playground13P/monitor55P1S/restart28P/CLI4P/反馈10P，全 exit0。
- 随后追加默认 HTTP→shipped DOM 整合测试；明确该新增整合测试为后补覆盖，不冒称该项先行 RED。
- 最终十文件运行 `ui-recovery/t20-startup-final-*`：新11P、反馈10P、playground13P、monitor **1F54P1S**、restart28P、restartCLI4P、readableUI44P、history23P、readablebackend32P、contracts119P。原 monitor failure 为 chunked 拒绝测试中的 Windows WinError10053，未改任何安全处理/测试去追绿。
- 独立 monitor 全文件重跑 `t20-startup-monitor-rerun-*` **55P1S exit0**。按各文件最新结果共 **339P1S**；不是一次全绿运行，原 final failure 保留。
- chunked 核查：首次比较脚本漏复制 autopilot，6个collection失败原日志保留（不能当产品结果）；修正fixture后的 baseline/current 各3次指定测试皆1P，`t20-startup-chunked-compare2/*`。10053未复现，不能据此宣称已经证明具体环境根因。字节校验同时证明 HTTP/body拒绝区域及整个 stop/replacement/orchestration/window 区域与启动前基线完全相同，裸测试没有启用本轮启动flag。
- `t20-startup-source-integrity.json` / `t20-startup-*.diff`：monitor 仅intro/deps/defaultfactory/start变化，LF保持；旧测试仅intro/socket import/default path变化，其它字节完全一致。不覆盖任何外来增量。
- 11861文件字节保护副本完整 npm run check：exit1，同三卡外 TS 文件3 warnings/2 infos；formatter_changes=[] / original_changed_during_check=[]，后续 chain 未执行。`t20-startup-check/{stdout.log,stderr.log,metadata.json}`。不称完整质量绿。

## 限制与剩余范围
- 只验证合成默认源码路径与Node DOM shim；不是实际用户monitor/浏览器验收，未部署/build/install/commit/共享serve/模型调用。
- 凭证集合固定于启动；不宣称自动追踪之后的凭证轮换。轮换后需要新的 monitor 启动快照，GET 不重新加载。
- 仍沿用底层 credential_snapshot/resolve_timi_api_key 的错误分类；本轮失败覆盖 factory 异常/返回None/抛出的发现异常，不声称改变了 resolver 对缺少auth或读取/解析失败返回None的既有语义。
- 旧T20报告中的“默认接入待确认”是上一轮事实，本报告为用户授权后补证；不改写原RED/失败日志。
- 原24AC/review/全check/框架finalize许可与另key restart整体验收仍未闭合，保持 EXECUTE；本次接线通过不等整key DONE。
