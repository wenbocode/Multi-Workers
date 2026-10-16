# R-02: mw-model-fallback-cli 修复复评（F1/F2/F3 + D1-D4）

type: review

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（GC-1/GC-2/GC-3）。
- 前轮 R-01（卡：`tasks/R-01-review-fallback-cli.md`，报告：`evidence/review-fallback-cli-20261015.md`）判定 **❌ 未通过 3✅/1⚠️/2❌**，列出必须修复 F1/F2/F3 与覆盖欠债 D1-D4。PM 已完成全部处置，本轮为**针对性复评**（不是全量重审：Q1/Q3/Q4 已判通过，仅复核修复面与其不回归）。
- 规格与实现记录：`spec.md`（AC-001~007）、`mini-spec.md`（含「规格修订」节与「R-01 独立复核处置」表，逐项列明修法与理由）。

## 待复评的修复锚点

| 项 | 声称的修复 | 锚点 |
| --- | --- | --- |
| F1 | 移除校验前 `strip()`/空项过滤，`args.value.split(",")` 原样交 `validate_fallback_models`；仅保留「整参数全空白」的用户友好报错；空格容忍不变 | `packages/multi-workers/mw.py:3614-3627`（注释 + `if not args.value.strip()` + 单次 validator 调用） |
| F1 回归 | 新增 mixed-empty / 项内换行拒绝 + 「带空格仍接受」反例 | `packages/multi-workers/test_dispatch_models.py:609`（`test_set_fallback_rejects_a_mixed_empty_csv_entry`）、`:618`、`:626` |
| F2 | mini-spec 记录规格修订（空值拒绝 / show 全局 none / `TASK_TYPE` 命名），删除「no deviation」 | `.agenticdoc/mw-model-fallback-cli/mini-spec.md`「规格修订」节 + Outcome + 「R-01 独立复核处置」 |
| F3 | README fallback 段改为「重复接受并去重（保首次、大小写归一）」；前缀表补 `zai/` | `packages/multi-workers/README.md`（前缀表 `zai/` 行、fallback 段首条 bullet） |
| D1/D2/D3 | 新增 `TestModelFallbackCliRefusals`：拒绝矩阵（坏 YAML / 坏 models / 坏 fallback 顶层 / 坏链项）× set+clear 逐字节 `read_bytes()` 不变；无文件不创建；整图 `yaml.safe_load` 保留断言；4 条边界 | `packages/multi-workers/test_dispatch_models.py:596`（类头）、`:642`（拒绝矩阵）、`:678`（整图） |
| D4 | TS 守卫矩阵（缺 task type / clear 多参 / 空引号）+ 双引号含空白链原样透传 + runner 失败 + 通用 usage 含新子命令 | `packages/coding-agent/test/extensions/agent-team-loop.test.ts:5236`（守卫矩阵 + 透传）、`:5271`（runner 失败）；usage 断言在 `unknown action` 用例内 |
| show 可观测性 | 坏 fallback 块时 `mw model show` 返回 1（与坏 `models` 块同契约） | `packages/multi-workers/mw.py:3715-3719`；用例 `test_show_fails_loudly_on_a_broken_fallback_block` |
| Q4/Q6 文案 | 注册处注释、`/mw` 通用 usage、`mw-runner.ts` 注释同步新子命令 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（`sub === "model"` 注释、通用 usage 行）、`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（`modelMw` docstring） |

## 审计目标（三态判定 ✅/⚠️/❌）

1. **F1 是否真闭合**（本轮核心）：读 `mw.py` 的 set-fallback 分支，确认 (a) 传给 validator 的是未过滤的原样 CSV split；(b) `a,,b`、`a, ,b`、项内 CR/LF、全空白参数各自的结果与 validator 既有规则（`mw_common.py:399-411`）一致；(c) 空格容忍并未因此丢失（`parse_model_value` 内部 strip 的证据）；(d) 旧的前处理代码确实不存在（无残留副本）。
2. **F1 回归断言强度**：`:609` 起的用例是否真的会在旧实现下失败（即断言依赖「validator 收到空项/换行项」这一点），还是仅断言 rc=1 而可能被其它路径满足；「带空格仍接受」反例是否存在。
3. **D1-D3 覆盖是否达标**：拒绝矩阵是否覆盖 set+clear ×（坏 YAML / 坏 models / 坏 fallback 顶层非 mapping / 坏链项类型），每例是否 **`read_bytes()` 前后相等**（非 `read_text`）；无文件场景是否断言「文件未被创建」；成功路径是否有整图断言（`models`、其它链、外来顶层键存活）。
4. **D4 与文案**：TS 守卫矩阵的每条是否有「runner 未被调用」断言；含空白链用例是否断言 argv 原样（单元素、未 trim）；通用 usage 断言是否钉住两个新子命令；`ui-bridge.ts`/`mw-runner.ts` 注释与 usage 是否已无旧的 show/set/clear-only 表述。
5. **F2/F3 文档一致性**：mini-spec 的「规格修订」与 Outcome 是否与实际实现一致（空值拒绝、show 全局 none、`TASK_TYPE` 命名）；README fallback 段是否不再把「列表内重复」称作 issue，且与 validator 去重行为一致；前缀表是否含 `zai/`（且 `codex_cli`/`claude_cli` 仍被标注为 fallback 不接受）。
6. **show 返回值改动是否自洽**：坏 fallback 块 → 1 是否与坏 `models` 块 → 1 的既有契约一致，是否影响「无链/正常链」场景（应为 0）。

## 要求

- 报告写入 `.agenticdoc/mw-model-fallback-cli/evidence/review-fallback-cli-r2-20261015.md`（唯一证据文件，勿覆盖 R-01 报告）。
- 每项判定给 `文件:行` 或测试用例名证据；三态结论：✅ 通过 / ⚠️ 有条件通过（列欠债）/ ❌ 未通过（列修复项）。
- 明确回答：**R-01 的 3 个修复项（F1/F2/F3）是否全部闭合**，以及 D1-D4 欠债是否解除。
- 只读审计：除该报告文件外零写入。

## 未覆盖面声明（审计边界）

- 不重跑 pytest/vitest/biome/tsgo（review 角色无 bash）：执行证据引用 `mini-spec.md`「R-01 独立复核处置」节的计数（Python 78 passed / TS 7 passed（`-t fallback`）与 201 passed + 1 已知基线失败（全文））。
- 不重审 R-01 已判 ✅ 的 Q1/Q3/Q4 全部细节，只复核其不回归（重点：F1 修复是否改变顺序语义）。
- 不覆盖 pi 窗口实机交互与 bundle 重建；不覆盖并发/I/O 原子性（R-01 已列为继承风险，非本 key 范围）。

## 交付格式

- `evidence/review-fallback-cli-r2-20261015.md`：判定表（R-02-Q/描述/状态/证据引用/备注）+ F1 闭合性推演（旧实现 → 新实现的差分）+ D1-D4 覆盖对照表 + 三态结论 + 残余欠债/修复清单。
- 交付说明：结论一句话 + 三态计数 + 「F1/F2/F3 是否闭合」的明确回答。
