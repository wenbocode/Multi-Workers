# Spec: mw-model-fallback-cli（备用链 CLI 入口）

- Key: `mw-model-fallback-cli`
- 类型：mini 快速路径升级为可派发 key（本次补齐 spec 以支持独立复核派发）
- 关联：`mw-model-error-perception`（已 DONE，提供 `fallback_models` 运行时语义与校验器）
- 规格细节与实现记录：`mini-spec.md`（Outcome 段）

## 0. Goal Alignment

- 目标锚点：`.agenticdoc/goal.md`。
- **预期收益**：`mw-model-error-perception` 交付的「备用模型链」是运行期韧性机制，但其唯一设置入口是手编 `.mw/dispatch.yml`——配置错误（顺序写反、超过 4 条、用了 `*_cli` transport 前缀）只能靠 `mw doctor` 事后发现。本 key 把该配置面纳入与角色默认模型同级的 CLI 通道（含 pi 窗口的 `/mw model` 转发），使备用链可被脚本化、可被校验、拒绝时无副作用，降低「降级链配错导致故障期继续失败」的风险。
- 对齐既有约束：GC-1 只改 mw 自有面（`mw.py` / TS 扩展层），不碰 pi core；GC-2 证据文件驱动（测试 + 报告）；GC-3 不改变 watchdog/状态机语义（仅配置读写面）。

## 1. 问题

`.mw/dispatch.yml` 顶层 `fallback_models`（任务类型 → 1..4 个有序 `prefix/model`）在 `mw-model-error-perception` 中只落地了 schema/校验/doctor 展示与读改写保留，没有设置入口：`mw model set` 只写 `models.<role>`。用户要求「通过 `mw model` 设置，且必须是按序尝试的数组」。

## 2. 范围

1. `mw model set-fallback <task_type> <m1[,m2,...]>` / `mw model clear-fallback <task_type>`：读改写写入顶层 `fallback_models`。
2. `mw model show` 追加链展示；`mw doctor` 既有 `dispatch_fallback` 保持兼容。
3. pi 窗口 `/mw model set-fallback|clear-fallback` 薄转发（校验唯一在 Python）。
4. 测试与文档（README、两个包的 CHANGELOG）。

## 3. 验收标准

| AC | 内容 | 验证面 |
| --- | --- | --- |
| AC-001 | `set-fallback` 将逗号分隔链按**输入顺序**写入 `fallback_models.<task_type>`（归一化后；大小写统一、去重保首个） | `test_dispatch_models.py::TestModelFallbackCli` |
| AC-002 | 写入值经 `mw_common.validate_fallback_models` 单一事实源校验：1..4 上限、`*_cli` transport 前缀、未知前缀、非 `prefix/model`、空值/空白全部拒绝（非零退出） | 同上（4 例拒绝用例） |
| AC-003 | 任何被拒绝的写入**不改动** `.mw/dispatch.yml`（逐字节不变） | 同上（拒绝后比对文件内容） |
| AC-004 | 写入保留 `models` 与其它顶层键；`clear-fallback` 清掉最后一个链时删除 `fallback_models` 顶层键（不留空对象） | 同上（读改写 + 文本断言） |
| AC-005 | `mw model show` 展示每条链且顺序与文件一致；无链时显式 `fallback: (none configured)`；`mw doctor` 的 `dispatch_fallback` 与本写入格式兼容 | show 用例 + doctor 实机 |
| AC-006 | pi 窗口 `/mw model set-fallback|clear-fallback` 转发到同一 CLI（纯 argv 透传），用法守卫在缺链/缺 task type/多余参数时不调用 runner | `agent-team-loop.test.ts`（3 例） |
| AC-007 | 文档与实现一致：README 命令表/示例/`/mw model` 行/fallback 段落（含「键是任务类型」「1..4」「注释不保留」），两个包 CHANGELOG `[Unreleased] ### Added` 各一条 | 读码核验（R-01 报告 Q6） |

## 4. 超出范围

- per-phase / per-key fallback；降级策略或预算语义变更（属 `mw-model-error-perception`）。
- pi 窗口交互美化（选择器 UI）；YAML 注释保留（CLI 写入为重排，已声明）。
- `main` 角色的 worker fallback（既有语义：无）。

## 5. 证据台账

- 规格与研究：`mini-spec.md`；`evidence/research/spec-zero-research-declaration-2026-10-15.md`
- 实现与测试执行：`mini-spec.md` Outcome 段（Python 104 passed；TS 199 passed / 1 已知基线失败；biome+tsgo 干净）
- 独立复核：`evidence/review-fallback-cli-20261015.md`（R-01，本次派发）
