# D-RQ3 工作台DAG与四离线case

type: research

## 上下文
目标 `.agenticdoc/goal.md:1`；锁定 `.agenticdoc/mw-decision-context/spec.md` AC011–019，四DP已确认业务语义不能改。
种子 `packages/multi-workers/decision_monitor.py:1` default_monitor_deps/serve，decision_dashboard.html/js/css，DecisionPlayground scaffold/validate/submit/submission/history；读旧dashboard T11b report与安全边界事实。
本任务不读取图片，无mockup视觉验收。

## 要求
仅只读设计研究，不改源码/跑测试/开浏览器/服务/安装或真实模型，不读真实凭证。
1. 基于现有独立窗口和安全资产路由提出最小UI/API改动：key/DP下拉、业务主表、4状态、日志结构弹窗、单次10节点DAG、节点真实请求返回代码块、旧记录可查不可展开、重试精确关联。至少2方案pros-cons，不引Electron/新框架。
2. 提供文本线框和新旧数据明确表现、缺失/零发送/脱敏事实呈现，模型返回不等接收/行动；事件协议归RQ2，不自造另套。
3. 四份离线case内容草案可直接对应dp1/2/3/25确认输入，离线生成存放/读取/编辑/校验/显式提交；首批只有4case不删其它21DP能力，必须真实edit→HTTP载荷，不旧本审计字段手填。
4. 生产与观察隔离、测试反馈仅观察事实不真签收，API变更消费者/测试覆盖边界清单；DOM shim/本地HTTP/真实browser分别标注验证层。
≤200行，分页read≤120行，命令stdout≤30行，无全仓漫游/反复dump大文件。不得把静态线框或样例草案称浏览器已验/代码已实现。

## 唯一证据文件
.agenticdoc/mw-decision-context/evidence/research/design-workbench-cases-20261022.md

## 写入允许面
- `.agenticdoc/mw-decision-context/evidence/research/design-workbench-cases-20261022.md`

## 写入禁止面
源码/配置/凭证/其它key/spec/design/plan文档；自身report.md可按框架记录。

## 交付格式
证据含问题/方法出处路径行号+符号/两方案和推荐/文本线框/接口建议/四case草案/下游认领与验证/未决。由PM写design.md。
worker_file的file传上述evidence相对路径，回执传basename report.md，禁止绝对file参数，≤64KiB。
