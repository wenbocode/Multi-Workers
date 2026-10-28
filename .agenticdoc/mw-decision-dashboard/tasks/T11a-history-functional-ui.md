# T11a 历史页签可用闭环

type: coding
status: pending

## 上下文
- goal `.agenticdoc/goal.md`；本key spec.md AC002至006、design.md两页签与安全契约；原tasks/T11-dashboard-ui.md。
- `packages/multi-workers/decision_monitor.py:1541` _static/:1587 history API/:1885 load_history；`decision_history.py:1` 安全page和detail。
- T07d和T10b已切片PASS。用户要求功能优先，先拆历史页签不依赖T06观察提交。T05q仅decision/points，T12a仅TS，两者并行无文件冲突。本卡独占monitor与assets，不写history/provider。

## 要求
交付能使用的历史UI，不仅静态占位壳：启动fragment exchange、清fragment、token仅内存，项目历史列表/筛选/分页/详情，来源分列、book/调用/实际请求返回/吸收应答展示。无数据和缺失显示未记录，未知unknown、推断inferred，usage不补0，capture存储与本次output_omitted分层，filters_withheld和filters_basis传递渲染。
monitor最小接线实际从新assets提供静态文件与上述两marks，不重复维护内嵌HTML/JS副本，不改token/Host/Origin安全或provider submit实现。两页签框架保留，DP测试页签诚实显示待接入，不造成功按钮/自动提交；后T06和T11b继续接完整测试页签。
安全textContent禁innerHTML/eval/inline JS，CSP闭集，打开刷新筛选绝不请求模型。完整分页读修改源，先行为测试RED再实现GREEN。隔离HTTP验证实际assets路由与bootstrap/history/detail JSON至DOM渲染；可用现有无外部依赖JS测试设施，不能只grep字符串声称DOM通过。不安装新依赖，不实际用户浏览器/Jev，不起共享服务。
若DOM设施不可用报告准确覆盖，先交付可运行资产与真实本地HTTP行为测试，真实可见浏览器验收仍未授权。tmpHOME/auth/env隔离与读前spy，不读取真实生产历史或凭证。

## 写入允许面
- `packages/multi-workers/decision_dashboard.html`
- `packages/multi-workers/decision_dashboard.js`
- `packages/multi-workers/decision_dashboard.css`
- `packages/multi-workers/test_decision_dashboard_assets.py`
- `packages/multi-workers/decision_monitor.py`（仅静态资产和history marks接线）
- `.agenticdoc/mw-decision-dashboard/workers/dd-history-functional-ui/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T11a-*`

## 写入禁止面
其他源测试、history、playground/provider、decision/points、TS、生产账本凭证、依赖锁、dist、任务相位。

## 验收命令
包目录 `python -m pytest test_decision_dashboard_assets.py test_decision_monitor.py test_decision_history.py -q`；所有新增JS测试按实际设施执行，argv/cwd/UTC/exit/hash全日志。root严格只读biome与check子步，未完整check不等价，不build/commit/全包pytest/真实browser。

## 改动历史
- PM按用户功能闭环优先解除原T11历史切片T06依赖。monitor最小前置接线合并本卡独占，避免额外往返任务。DP测试明确待T06，不追认整体T11完成。

## 交付格式
report最多110行，真实RED/GREEN/HTTP和DOM覆盖/可使用路由/缺失诚实展示/剩余DP页签与未覆盖。
