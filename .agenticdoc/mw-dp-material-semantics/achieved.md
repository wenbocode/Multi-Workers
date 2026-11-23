# mw-dp-material-semantics

## 系统行为变化

- QG 使用 `model_context.reasons` 声明当前未解决的 finding。空对象可仅提交 pass 与 reopen 判据。非空时每个 fix 提交选中的 finding，宿主生成剩余项。选错编号、重复归属或漏报的分区会被拒绝。保留由独审及当前合同决定 pass 范围的门禁。
- `review` 和显式合同锚点绑定现行合同。日志里出现的旧号和未知编号保留在原文。当前 spec 已声明的替换关系另附出处，预览中的现行判据清单只列当前绑定。VC 所关联的 AC 可作为背景提供，独审范围仍由 review 决定。
- 冻结合同和材料准备共用 VC 解析。多层 Layer 保留原文，损坏或重复的 VC 定位到设计文件，引用越界返回文件总行数。文件名、实例编号和日志事件标记原样保留。未定义术语给出材料字段或原证据位置。

## 验收证据

- AC-001 至 AC-005 通过 107 项 Python 自验。覆盖零、单、多 finding，非法选择与独审范围，陌生编号在日志和 review 两种用途下的差异，同一草稿交错修正、证据漂移复核以及零发送和单次发送。[命令与源码快照](evidence/codex-pm/self/1795442408263239100-1yz0726x/result.json)
- 公开窗口定向回归通过 112 项。Gaze 和 Bearing 的旧材料回放确认编号与事件标记可保留，术语缺口仍由宿主报告。[命令与源码快照](evidence/codex-pm/self/1795442440481029100-lny6a1az/result.json)
- 对 UE 窗口存下的原始请求和 Render 原设计进行了只读材料准备。UE 的 AC-203 映射到 AC-304，出处为 spec 第 50 行。Render 六项 VC 都可解析，95–130 的引用准确报告文件共 128 行，修正范围与 SIE 定义后准备通过。[原材料回放输出](evidence/original-material.txt)
- 完整 npm 检查在源码副本执行，避免格式化影响其他窗口的工作区改动。[完整输出](evidence/npm-check.txt)

## 遗留

以上为 Codex PM 实现者自验。三个在用的项目窗口仍需在 `mw-dp-window-acceptance` 用实际运行版本验收。Render 的准备通过仍需按其项目流程取得独立证据。材料反馈后的推进循环由 `mw-dp-repair-loop` 接续。

窗口扩展回归排除一项已在改动前后复现的签收夹具失败。该夹具未提供当前独立 QG 证明，正式签收入口在两个版本均拒绝 finalize。Python 的真实独审证据链用例通过。
