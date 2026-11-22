type: coding
deps: [T03, T04]

# T05 QG/sign前提、可区分性与auto有界路径

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。读spec AC-001/006/008/009、design §6/7、docs详细设计§8/9。依赖T03/T04的真实输入/阶段合同。

AC-014 当前补验已通过 PM 正常入口捕获 sign 实际发出的适用范围、AC/VC 正文和状态、当前合同版本、生产 QG 发布与独审凭据。当前整 key PASS 写入正式签收。较新的正式 FAIL、局部范围、错对象、过期和在途证据漂移均拒绝签收。漏 AC 也有定向 QG 材料验证。 [正常入口及实际 payload](../evidence/review/ac014-bounded-prepare-sign.md) · [独立复核](../evidence/review/ac014-bounded-prepare-sign-independent.md)

## 目标及对应AC

AC-006、AC-008、AC-009，复核AC-001的QG候选覆盖。不是把confidence提高到某值，而是检查材料是否可比较且业务前提成立。

## 工作项与交付

1. QG先核当前独审和完整适用AC/VC，保留not-met/unverified/fail/not-run/unknown；sign核目标/偏差与当前同对象/范围/版本QG。
2. 全候选对比较目标取舍、支持来源、反转条件和未知；n=2..5覆盖1..10对，缺偏好/等价返回本地状态，不造假第三选项。
3. auto核同一决策单位、信息价值、条件后继、步骤/全程硬边界、次数与停止；区分上限和估计。
4. 决策前不可取未知可诚实保留，不一律迫使先完成被比较动作；不私删固定候选或fix原因配对。
5. 旧QG缺reopen、旧auto缺取舍均作负例，不改旧响应。

## 写入允许面

2026-11-22 基线见[当前源码复核](../evidence/research/current-code-review-20261122.md)。复用适用门禁与已落盘独审证据，把当前对象/范围/版本和逐 AC/VC 状态送入对应材料。auto 加入改 ID/标签却同内容，以及六项通过旧校验的回归输入。

- packages/multi-workers/decision_points.py及本任务新增QG/sign/可区分性/路径校验模块。
- prepare.check_inputs/check_discriminability与现有PM适配的限定部分（PM须协调同文件写面）。
- 新测试packages/multi-workers/test/test_dp_material_business_checks.py及必要TS调用适配suite。

## 写入禁止面

既有AC/VC原文的任意改写、正式QG/sign writer绕过、原权限/预算放宽、凭证/依赖、其它key与docs副本。

## 验收命令

```json
["python", "-m", "pytest", "-q", "-s", "packages/multi-workers/test/test_dp_material_business_checks.py"]
```

## 完成判据与输出

VC-006/008/009及候选负例断言可见；覆盖假独审/漏AC/VC未测/借其它QG、全部pair遗漏、反转条件缺失、等价、循环/无终止/超预算/刷新次数。交output.md说明机械检查与原主体语义复核边界，不把高confidence当通过。未来代码交付运行npm run check。

## v0.5范本引用与逐项对比（必验）

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。区分 QG 候选/依据错配、证据超限和独审业务前提。sign 的材料准备失败与 QG 结论、签收 writer 分阶段。原 QG 四条回执用作失败阶段对照，固定候选不足仍另用源码样例验证。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：dp-QG、dp-sign-key、dp-auto-original、dp-auto-optimized；其余案例核适用前提。对照四段中的AC/VC正文和状态、QG引用、auto取舍/路径、原始原因及PM采纳/退回理由；负例保存当前拒绝/接回实际观测。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。
