# T-11 质量门禁（对抗复核）

- Key: mw-dispatch-card-gate｜Wave: 6｜依赖: T-01…T-07、T-09、T-10（均终态）｜type: review

## 上下文
本 key 已落地 9 张实现卡（T-01 信封契约库、T-02 生成端注入+工具层校验、T-03 服务层兜底、T-04 回收契约、T-05 coding 改动历史、T-06 卡追溯与一致性、T-07 终态翻转+逃生舱真读+type 单一来源+ledger 接入、T-09 生产者信号覆盖、T-10 无条件注入+金样本重新基线）。PM 已逐卡独立复核（跑验收命令、核对改动清单、检查禁止面），但**尚未做对抗性复核**：PM 复核自己的产物存在系统性盲区（本 key 已记录 5 次 PM 自纠，均为"写卡/复核时未核实既有事实"）。故需独立 review 角色以**对抗方式**检验证据链，而不是复述报告。

## 审计目标（问题域，不限制输入面）
1. **AC 覆盖真有证据吗**：`spec.md` 的 AC-001…AC-008 逐条，找出「有实现无证据」「有证据但不可解析」「证据与主张不符」的项；特别检查 AC-002（上下文种子 + 探索不被限制）、AC-003（回收契约）、AC-004（改动清单 ⊆ 事件）、AC-006（追溯与一致性）、AC-007（逃生舱真读）。
2. **形式满足（假达标）**：判据是否可被"只注入标题、内容为空"这类形态骗过？`dispatch-card.ts` / `card_audit.py` / `output-sections.ts` / `change-ledger.ts` 的宽档判据各自的后门在哪里？
3. **豁免与边界的可绕性**：`ENVELOPE_ENFORCE_SINCE`（`packages/multi-workers/launcher.py`）的时间边界能否被伪造/绕过（如行内时间戳可写、缺失时的补写逻辑、`_envelope_enforced` 的判定路径）？`unlisted_dispatches`（`packages/multi-workers/autopilot/card_audit.py`）是否会把"漏检"掩盖成"迁移期允许"？
4. **合成段的实质**：T-10 对无卡自动派发的 `synthesized_card`（`packages/multi-workers/autopilot/dispatch.py`）产出的三段是否为**形式合格的垃圾**（例如把 prompt 原样塞进要求、上下文只有路径）；与 `spec.md` §1.3「两个产物一处权威」是否冲突。
5. **两入口同一判据**：TS `shared/dispatch-card.ts` 与 Python `launcher.py` 的判据/词表是否真的一致（parity 用例是否覆盖了全部常量与边界；`ENVELOPE_*` 与 `TYPE_EXTRA_*` 是否逐项对齐）。
6. **回收契约的作用域**：`worker/output-writer.ts` 的终态缺口折叠是否覆盖所有退出路径（成功/失败/无 `type:`/无 `task.md`）；是否存在"缺段却仍 done"的残留路径。
7. **PM 自纠记录与产物的一致性**：`pm-state.md` 与各 worker 报告中 PM 的裁定（例如 AC-005 子项撤回、T-10 的 `card_path` 仅在有卡时注入）是否与代码实际行为一致。
8. **本 key 的文档锚点**：`spec.md`/`design.md` 引用的 `路径:行号` 在 T-02/T-03/T-05/T-07/T-09/T-10 落地后是否已失真（本 key 自己的锚点复核尚未执行）。

## 要求
- **角色约束（遵守契约）**：本角色为只读（无 bash、无 write/edit）。因此**不得声称"已运行测试"**；一切结论必须基于可解析的静态证据（代码、测试断言、证据文件、报告原文）。需要动态验证才能定论的项，**写入未覆盖面声明**并给出具体验证命令建议。
- **不得采信自报**：worker 报告与 PM 结论都只是待验主张；命中的每一项必须给出 `路径:行号` 或符号级定位。
- **对抗优先**：优先寻找能证伪设计方案的反例；对"PM 已复核"的项同样按未验证对待（PM 复核恰是最可能有盲区之处）。
- **只读仓库**：不得写任何文件（包括不得修改本卡）。
- **已知不属发现**（不要当成新发现）：cutover 未执行 ⇒ 运行期一正一负证据缺失；`packages/multi-workers` 全量 pytest 有 2 条既有基线失败（`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`）；另有 8 条 `failed` 回读记录对应的是健康运行中的 worker（回读误判，PM 已登记为独立事故）。这些可指出**由它们衍生的风险**，但不作为"新问题"计数。

## 交付格式
- 产物：唯一证据文件 `.agenticdoc/mw-dispatch-card-gate/evidence/quality-gate/T-11-adversarial-review.md`（若该目录不存在则写入本 worker 的 `report.md`，二者择一，不得写别处）。
- 形态：
  1. **结论**：PASS / FAIL（含一票否决项）；
  2. **发现清单**：每条 `编号 | 严重度 P1/P2/P3 | 主张 | 证据（路径:行号） | 复现或定位方式 | 建议处置`；
  3. **AC 覆盖矩阵**：AC-001…AC-008 × {实现位置, 证据文件, 是否有反例证据, 判定}；
  4. **未覆盖面声明（必填）**：明确列出本角色**没有**检查到的面（须含：无 bash 故未动态执行；未读过的目录/文件类；未能定论的问题及其所需验证命令）。
- 回收判据：证据文件存在且非空；发现清单每条都有路径级证据；未覆盖面声明非空且具体；不得出现"已运行/已通过测试"这类本角色无法产生的断言。
