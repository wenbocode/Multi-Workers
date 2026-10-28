# T11 十节点图形与可读请求工作台

type: coding
write_face:
  - packages/multi-workers/decision_dashboard.html
  - packages/multi-workers/decision_dashboard.js
  - packages/multi-workers/decision_dashboard.css
  - packages/multi-workers/test_decision_context_workbench.py
  - packages/multi-workers/test_decision_dashboard_assets.py
  - packages/multi-workers/test_decision_dashboard_contracts.py
  - packages/multi-workers/test_decision_context_readable_ui.py

## 上下文
目标.agenticdoc/goal.md:1；批准增量evidence/design-workbench-readable-revision.md/spec AC015及021～024。packages/multi-workers/decision_dashboard.js:1105裸JSON详情，1127列表非图；decision_dashboard.css:386纵向布局。用户明确授权实施，不新研究。

## 要求
完整读拟改文件，首写前保存允许面原始bytes/hash/diff，精确UTF8 edit保护共享dirty。先真实DOM行为RED后GREEN。后端并行独占history/monitor/playground/points/case及后端测试；禁止改那些文件。
1. 保10节点id key/role/dp/input/decide/request/model/response/receipt/action。真正有向节点图（SVG或HTML+SVG线），不是纵向列表。节点颜色文字状态、点击侧边可读详情，生产/test共用。CSP外部资产/textContent，无innerHTML/eval/inline事件；SVG安全DOM API。图关系按已批准顺序，连线不表示动作已发生。适配窄屏与键盘访问，不新依赖。
2. input只默认显示业务材料分区，不显示book/ref/hash/version/mode/intent/basis；从后端detail.material优先，旧实际snapshot可安全解析取state，不猜正文。
3. request/response显示安全实际capture.text，合法JSON prettify，不双层转义；复制原始捕获字符串，非JSON保留原文；缺失/脱敏/截断明确。元信息只必要状态摘要不铺字段。
4. decide低置信度说明未采纳，显示模型选择/API confidence/本次阈值/人工兜底。后端提供detail.policy_result={reason,selection,confidence,min_confidence,disposition}；阈值未知说未记录，不用当前配置补造。HTTP200不叫API失败。四主状态不变。
5. 日志默认仅时间key/task发起角色、实际请求响应、接收行动结果及错误；删来源阶段决策本版本hash栏目，不删除底层记录/下载原始功能。
6. 四case完整questions编辑与request_preview；case.questions，validate请求{dp,book,questions?}结果request_preview={model,state,questions}，submit允许questions。state及instructions/criteria可编辑，dp3候选仅state.handling_options维护一次，questions.criteria只读派生/规范化，预览与server实际值一致。编辑只观察，不写生产配置。无读取/编辑自动模型调用。原其他21DP通用能力与安全门保留。
接口以后端progress发布为准；可先写fixture UI测试，真实联调等后端停写；不得越面补后端。不要删旧安全测试，合法迁移与替代断言定位。
验证使用isolated HOME/auth/loopback/DOM，不真实模型/凭证/browser/build/install/commit/framework/service操作。不得以字符串搜索代DOM点击图边节点断言。

## 写入允许面
packages/multi-workers/decision_dashboard.html
packages/multi-workers/decision_dashboard.js
packages/multi-workers/decision_dashboard.css
packages/multi-workers/test_decision_context_workbench.py
packages/multi-workers/test_decision_dashboard_assets.py
packages/multi-workers/test_decision_dashboard_contracts.py
packages/multi-workers/test_decision_context_readable_ui.py

## 写入禁止面
其他源码/测试、后端/case、TS及生成registry、framework、dist、配置锁文件和其他key；自身证据经worker角色机制。

## 验收命令
逐文件python -X utf8 -m pytest -q packages/multi-workers/test_decision_context_readable_ui.py及本卡实际修改测试；完整UTF8 stdout/stderr/UTC/argv/cwd/exit，先RED后GREEN。

## 改动历史
2026-10-23 用户确认精简/十节点图形/完整questions并要求实施；本卡首轮。

## 交付格式
自身report/progress/evidence原文hash/diff及完整RED/GREEN；图边/10节点点击/格式化与复制/日志栏目/questions编辑的实际断言出处与未验视觉边界。report必须含## 结论、## 证据、## 残留与未验证、## 上下文来源。
