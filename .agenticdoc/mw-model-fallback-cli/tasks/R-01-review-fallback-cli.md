# R-01: mw-model-fallback-cli 独立复核（备用链 CLI 入口）

type: review

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（GC-1 不碰 pi core／GC-2 文件驱动证据／GC-3 watchdog 语义连续）。
- 被审对象是 **mini 快速路径**改动，规格：`.agenticdoc/mw-model-fallback-cli/mini-spec.md`（含 Outcome 段）。需求来源：用户在 `mw-model-error-perception` 收口后指出「备用模型应能通过 `mw model` 设置，且必须是按序尝试的数组」；原 `fallback_models` 只能手编 `.mw/dispatch.yml`。
- 运行时语义（背景，非本次改动）由已 DONE 的 `mw-model-error-perception` 提供：worker exit 3 → launcher 同模型重试 ≤`PI_WORKER_MODEL_ERR_MAX`（默认 2）→ 按链顺序降级 → 链耗尽 failed。
- 本次改动锚点（待你核验）：
  - `packages/multi-workers/mw.py:3464`（`_model_write` 新增 `fallback_models` 参数：None=保留／映射=替换／空=删顶层键）
  - `packages/multi-workers/mw.py:3602`（`set-fallback` 分支）、`:3652`（`clear-fallback` 分支）、`:3709`（`show` 追加 fallback 展示）、`:6739`（argparse 两个子命令）
  - `packages/multi-workers/test_dispatch_models.py:477`（`TestModelFallbackCli`，10 例）
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3367`（窗口侧 `set-fallback`/`clear-fallback` 薄转发 + 用法守卫）
  - `packages/coding-agent/test/extensions/agent-team-loop.test.ts:5184`（TS 转发/守卫 3 例）
  - `packages/multi-workers/README.md`（命令表 + 用法示例 + `/mw model` 行 + fallback 段落的 CLI 说明与「注释不保留」提示）、两个包 `CHANGELOG.md` 的 `[Unreleased] ### Added` 条目
- 校验单一事实源（复用，未改）：`packages/multi-workers/mw_common.py:365`（`validate_fallback_models`，含 `FALLBACK_MAX_MODELS=4`、CLI transport 前缀拒绝、归一化去重）。

## 审计目标（三态判定 ✅/⚠️/❌）

1. **写入语义正确性（读码）**：`_model_write` 的 `fallback_models=None/非空/空` 三条路径是否分别等价于「保留原键」「替换」「删除顶层键」；`_dispatch_extra_keys` 的提取与 `data.pop` 是否会留下空 `fallback_models: {}` 或吞掉 `models` 之外的其它顶层键。重点：`set-fallback`/`clear-fallback` 传入的 `models` 取自 `load_dispatch_config`，是否存在「另一个顶层键被静默丢弃」的路径。
2. **校验复用与拒绝路径**：`set-fallback` 是否真的把 `{task_type: raw_list}` 交给 `validate_fallback_models` 并**完全接受其归一化结果**（顺序/大小写/去重/上限/`*_cli` 前缀/未知前缀）；参数为空/全空白、未知 task type、已有 `fallback_models` 块不可解析时是否**拒绝且文件零变化**（自行判断 `args.role`/`args.value` 在两个分支下是否可能触发 `AttributeError` 或绕过校验）。
3. **数组按序语义**：本改动写入的链是否与 launcher 读取顺序一致（有无任何排序/逆序/去重导致顺序变化的路径）；`show` 输出的链顺序是否与文件一致。
4. **TS 薄转发面**：`ui-bridge.ts` 的分支是否只做 argv 透传（校验仍唯一在 Python）、用法守卫是否会漏放非法形态（缺 chain、多余参数、缺 task type）进 runner；usage 行与实现是否一致；`/mw model` 的 docstring 是否与新子命令相符。
5. **测试充分性（读码，不重跑）**：`TestModelFallbackCli` 10 例与 TS 3 例是否覆盖 mini-spec 的 AC-1~AC-4；是否存在**未被任何用例覆盖的拒绝路径**（如 `set-fallback` 遇损坏 `models` 块、`clear-fallback` 遇损坏块、`fallback_models` 顶层非 mapping）；测试断言是否真的钉死语义（例如「拒绝时文件零变化」是否逐字节断言）。
6. **文档与实现一致性**：README 三处新增/修改与 CHANGELOG 条目是否与实现相符（含「键是任务类型而非角色」「1..4」「注释不保留」这些易错点）；mini-spec 的 Outcome 段是否有夸大或未兑现的声明。

## 要求

- 报告写入 `.agenticdoc/mw-model-fallback-cli/evidence/review-fallback-cli-20261015.md`（唯一证据文件）。
- 每条判定给证据引用（`文件:行` 或测试用例名）；结论三态：✅ 通过 / ⚠️ 有条件通过（列欠债）/ ❌ 未通过（列修复项）。
- 只读审计：除该报告文件外零写入。

## 未覆盖面声明（审计边界）

- 不重跑 pytest/vitest/biome/tsgo（review 角色无 bash）：测试与静态检查的执行证据引用 mini-spec Outcome 段（Python 104 passed、TS 199 passed/1 已知基线失败、biome/tsgo 干净）。
- 不审计 `.agenticdoc/mw-model-error-perception`（已 DONE）的实现本体，只审本次 CLI 入口对它的读写契约。
- 不覆盖 pi 窗口内联 `/mw model set-fallback` 的实机交互（窗口 bundle 尚未重建，需 `mw build --install` + 重启；Python CLI 已实机验证）。
- 不覆盖 `mw doctor` 的 `dispatch_fallback` 渲染实现（`mw-common` 既有面），只核对它与本 CLI 写入格式兼容。
- 不判断 YAML 文本格式美观（注释丢失是已声明的既有行为，不算缺陷）。

## 交付格式

- `evidence/review-fallback-cli-20261015.md`：判定表（Q-ID/描述/状态/证据引用/备注）+ 关键拒绝路径与顺序语义的读码推演 + 汇总（三态计数）+ 欠债/修复清单。
- 交付说明：结论一句话 + 三态计数。
