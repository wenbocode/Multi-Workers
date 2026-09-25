# Research: 事故证据与方案备选否决记录（spec）

## 决策问题
支撑 spec §0 预期收益、§1.4 范围排除（为什么不是 closure-repair worker / R2 覆盖语义 / 推断式坏稿判定）、§4 风险。

## 调研方法与出处
- handoff 文档与其引用的 timeline 事件（seq 51880-51882 blocked/gate-created/stalled；52973-52974 人工收口后 exit=0；gate-0004/0005 创建于 06:19:07Z/06:21:18Z；人工批准 07:40:15Z）
- 本 session 与用户的 3 轮方案收敛对话：closure-repair worker → L3 失败原文回流简化 → marker 内容寻址（用户提出守卫风险与"脚本明确声明"要求）
- 工作树与提交验证：`git diff`（守卫 +13 行）、`git log`（`6254783b6` read caps、`4e874f5cc` 守卫提交）

## 发现
- A1 事故量化：4/4 key 命中同一缺口、每 key 需一次人工介入；已批准 stalled 门重放 12h 生成 6684 个门禁文件（已修）；Stage 2/3 尚余 9 个 key 待跑（每 key 约需一次人工收口）。
- A2 词表来源修正：handoff 表述为"工程的验收词表"，实为标准模板（`.agents/skills/agentic-task/scripts/advance_phase.py:69-93`）自带规则——所有标准安装工程必然命中，非 FeatureMigrator 特有；4/4 命中率是结构性必然。
- A3 方案备选否决记录：
  - closure-repair worker（新 dispatch 类型 + `closure:{key}` loop 家族 + in-flight 守卫扩展 + pm-state/QG 哈希 diff 校验）：功能等价但引入 3 块新机制。生产者（L3 prompt）本身已在带预算的重试回路内，失败原文回流该回路即可。否决理由 = 复杂度无对应收益。
  - R2 覆盖语义（transaction 覆盖非合规稿）：覆盖内容仍只有不合词表的 L3 文本——不解决生产者问题，只把"永久锁死"换成"重试后照样 stalled"，且每轮销毁原稿 provenance。否决。
  - 推断式坏稿判定（"上次同 edge advance 失败 ⇒ 现稿为坏稿"）：陈旧判定会覆盖人工修好的稿（handoff 附 B 人工收口场景恰好是"失败后人改稿"）；timeline 有界尾部派生不可靠。用户在评审中指出该风险，否决，改为内容寻址 marker（"坏稿需脚本明确声明"）。
- A4 marker 设计要点（用户确认版）：声明绑定被拒稿 sha256；三条件（marker 存在 ∧ marker.sha256 == sha256(当前 achieved.md) ∧ 本次 gate 失败行涉及 achieved.md）全真才允许覆盖；哈希失配 = 声明作废 = 不覆盖（失败方向恒为"少覆盖"）；覆盖成功或 advance exit=0 后删除 marker；崩溃窗口安全（advance 失败后 marker 写入前崩溃 → 无声明 → 不覆盖 → 下 tick 重走，仅浪费一次 advance）。
- A5 escalate-not-loop：gate 失败行不含 achieved.md 的 gate-blocked（pm-state/QG/evidence 类规则）不烧 L3 轮——reviewer 是只读角色修不了文件；直接走既有 5 次 stalled 路径，防止另一类无谓空转。

## 结论 → 决策映射
- A1 → §0 预期收益的量化基准（9 key × 1 次人工介入；通用化为所有标准模板工程）。
- A2 → AC 词表可移植（第二套词表）与框架零硬编码的必要性。
- A3 → §1.4 范围排除项与 key-decision 边界。
- A4 → AC-003 / AC-004 / AC-011 断言来源。
- A5 → AC-006 断言来源。
