# dp3调用差异诊断

观察时间：2026-10-25 00:47（本机时间）。文件名沿用本次研究批次日期。
范围：用户要求“先查”；无源码修复、真实决策请求、部署或共享服务操作。

## 结论

本次PM blocked已定位并用faux runner复现：PM调用在合法dp3三块材料之外混入九个dp2/dp25字段。闭合字段集校验正确拒绝这些额外键；工具随后把所有MaterialIssue.field都叫作missing_fields，掩盖了“字段不允许”与“字段缺失”的差别。九项返回不是服务要求补九项，也不是dp3材料丢失。

此前PM记录/回复关于“服务要求其他DP字段、材料传递或校验契约不一致”的判断不成立，由本轮证据纠正。不能继续用该次blocked证明dp3业务或Python服务故障。

RQ2/RQ3 trace里的自动dp3 input-incomplete是另一条本地路径：settle hook不传agent-prepared material，helper按既有契约零spawn转人工。它不是已发送dp3模型请求失败；缺四节仍是原worker exit2的直接交付缺口。

## 证据与数据流

### 1. 实际PM调用与正确case的差异
- 正确材料顶层只有question/background/handling_options。background四事实位于background内，不是顶层task_goal。
- PM原调用额外传入（原顺序）：task_goal/task_requirements/task_deliverables/pm_decision_background/worker_execution/delivery_goal/actual_completion/verification_evidence/unfinished_impact。
- 源码material schema把多DP字段并列，但全部可选；按选择的DP再次执行闭合集校验。这种并列展示有混填风险，不代表源码要求所有字段。尚未检查provider侧schema转换。

### 2. 第一个差异边界及误导反馈
全文读取`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`：
- `validateDecisionMaterial:625`，`:637-640`检测不在allowedTop中的键，产生rule=`not in required_state_fields (closed key set)`。
- `runMaterialAskDecision:1294-1305`先validate；失败时统一返回input-incomplete，并在`:1303`将全部issues映射到missing_fields。
- 失败早于`:1306`身份meta与`:1324`左右的callDecideChild；本次不会生成CLI stdin，也不会启动Python。
- registered tool execute逐项把params.material传入runAskDecision，未见对这九项进行丢失或补造。

### 3. 隔离对照，rc=0
日志：`evidence/dp3-boundary-diagnostic-20261024.log`（已全文回读，原始UTF-8有效）。
- 输入A：从当前dp3.json提取纯业务材料。
- 输入B：A加原PM那九个额外键（同顺序和值类型；具体字符串为合成值，不声称逐字重放原历史材料）。
- 同时覆盖runAskDecision和registerAskDecisionTool实际注册后的execute，四组对照均断言通过。
- A：validate ok，faux decision runner各1次，faux consumed runner各1次，所捕获stdin material与A深度相等。
- B：九项全部是unknown-key规则，不是missing；返回列表和历史PM工具结果完全同名同序，faux runner和feedback各0次；直接入口spawned=false。
- 真实Python决策子进程0、真实模型请求0；所有runner均注入，未调用ask_decision服务。未执行vitest或全测试。
- Node v24.19.0；private cwd/HOME/USERPROFILE/APPDATA/LOCALAPPDATA/PI_CODING_AGENT_DIR，scrub PI/MW及凭证/proxy/endpoint env。
- PowerShell展示的中文曾因控制台解码变乱码；落盘使用原始Node stdout字节，read全文确认UTF-8中文正常，不是材料损坏。

### 4. 安装版本不是本次拒绝的解释
- repo bundle与global bundle均SHA256=`0d08fb32d397f1d63772de55b039990cf3b180ddebb7724ac0d71fa13482e283`。
- bundle确实早于最新源码，但定点读取`:14284-14326`与`:14638-14645`，闭合集校验与issues→missing_fields逻辑与源码相同。
- 源文件SHA256=`3c1388f5ce8ee8d4336be7207083f918c70c6e681c089d62522a36fc671f9f9e`。
- 磁盘hash不证明当前进程内存模块hash；本轮没审计整个1.4MB bundle或完整部署链，但不能把本次九字段拒绝归因版本漂移。

### 5. worker自动trace的实际含义
源码定点读完整attemptDp3Clarification及decideDp3WorkerClarify相关函数：
- `worker-mode.ts:4190`附近的hook调用不携带material。
- `:5677-5679`明确缺input.material时直接返回input-incomplete，detail为`no agent-prepared dp3 material (ask_decision owns dp3)`，早于runner。
- bundle`:24897`及`:25455`同样无material调用/本地拒绝。
- 全文读回现有`decision-context-agent-materials.test.ts`，已有测试覆盖正确纯dp3工具入口、unknown键拒绝、worker无agent材料时zero spawn。与离线case正常不矛盾。

## 后续建议（未实施）

1. PM调用应只构造所选DP的材料，不补其他DP字段；本次先纠正调用和解释，不改dp3业务契约。
2. 保留闭合字段集拒绝，但反馈区分missing/unexpected/invalid，并保留rule；不能将unknown键指导为“补齐”。需先明确改动key、写面、测试及用户实施许可。
3. 工具提示/schema可避免多DP并列字段诱导混填；若怀疑provider强制填满可选字段，应另做schema投影对照，不先归因或放宽未知字段。
4. worker settle缺材料是既有人工降级，不应补造业务事实或自动增加模型调用。原回执四节缺口由已授权PM复核处理，原exit2不改。

## 验证边界

仅本地faux入口复现与静态核对。未重放真实PM服务请求、未调用provider、未验证当前进程内存bundle、未通读整个worker-mode或Python decision_points/mw服务。没有声称线上已修复或全DP测试通过。
本轮仅新增诊断日志/脚本留档/PM证据与状态，不改原worker产物或生产历史。
