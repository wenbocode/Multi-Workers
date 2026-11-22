type: coding
deps: [T01, T02, T03]

# T04 prepare Worker隔离、状态机与吸收

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。读spec AC-007/011/013、design §4/5，docs prepare合同。依赖T01/T02，写面调度默认等待T03完成，避免decision-tool.ts并发覆盖。

AC-014 补验确认现有 `decide_prepare` 已支持派发角色、`models.decide_prepare`、决策卡和受限决策本写入，可复用入口。现有 role 带受限 shell 和旧卡片允许发送的分支，默认 Timi 路线与 Jev 可共用认证来源。验收应检查新受限准备流程的实际 tool set 和模型凭证来源。越序、越权、换模、旧 revision、重置额度和半发布需由宿主拒绝。复用正常入口的材料预览只能验证直接准备。[实现差额与独立复核](../evidence/review/ac014-followup-independent.md)

本轮通过真正的子额度预留和 `decide_prepare` 派发验证。选择 `prepare_profile: bounded-v1` 时，在已绑定原事项预算的卡头明确 `prepare_dp`、`prepare_sources` 和直连 `model`。受限 Worker 只使用 `prepare_dp`，原主体通过 `absorb_dp_preparation` 核验并接受同一 revision。原 Worker 的委托读取与普通读取共享其实际运行对应的累计额度。 [正常入口和反例](../evidence/review/ac014-bounded-prepare-sign.md)

## 目标及对应AC

AC-007，支撑AC-011/013；专用prepare工具顺序与权限由host实际守卫，简单材料仍能原主体直接准备。

## 工作项与交付

1. 基于现有派发/结果和真实task/run绑定新增受限prepare profile；原主体不靠自填owner字符串获得权限。
2. 按begin/read/check_inputs/compose/check_discriminability/validate/publish/absorb守卫阶段与revision；结果状态与业务choice分离。
3. 指定现有注册prepare_model并记录requested/effective及允许回退，助手无决策密钥/任意shell网络/产品写/认领权限。
4. 限定本run产物原子发布，旧版/半发布不能吸收；原主体语义复核，accepted与真实dp_result或null分开。
5. 读取、等待、返工和模型消耗继承原budget_ref；失败不新增全局等待/审批。

## 写入允许面

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。复用 prepared book、只读 preview、现行 host 和读范围接口。简单材料使用原主体直接准备，专用 profile 的发布吸收仅处理复杂委托，验收分别驱动两条真实入口。

- packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts、worker/worker-mode.ts、worker/read-scope.ts及新增prepare模块。
- packages/multi-workers/launcher.py、dispatch现有profile/model适配和新增prepare产物模块；不改普通派发权限语义。
- 新测试packages/multi-workers/test/test_dp_prepare_profile_v1.py及coding-agent定向suite。

## 写入禁止面

pi核心、凭证配置、其它角色权限扩张、全局claim/预算新系统、依赖锁、其它key与docs冻结副本。read/review来源不因助手自称独立就算独审。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_prepare_profile_v1.py"]
```

## 补充验证与完成判据

必须补充注册工具真实handler的TS suite（从packages/coding-agent运行指定新增suite，harness/faux），Python隔离集成覆盖跨语言产物。VC-007及011/013相关断言包括越序/越界/换模/旧revision/半发布/身份冒充/预算重置和合法直接准备；真实产品/认领副作用=0。交output.md及发布/吸收证据；未来代码交付运行npm run check。

## v0.5范本引用与逐项对比（必验）

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。准备阶段生成可追溯显式引用，核目标产物是否已存在、引用用途、读范围与原额度。需缩窄范围或委托摘要时通过原主体吸收并复核字段绑定。沿用 preview 和已有读取器。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例，重点dp-w-check-task、dp-pm-steer。核准备/吸收本地字段、模型投影边界、返回绑定和原主体接回观测；实际Worker自评不能冒充。范本不证明真实prepare工具已执行。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
