# 零研究声明：mw-model-fallback-cli（2026-10-15）

- key: `mw-model-fallback-cli`
- phase: spec
- 声明类型：**zero-research declaration**（本 phase 未派 research worker）

## 为什么不需要独立调研

本 key 是**配置读写面**的增量，其全部约束在派生前已由既有代码与已 DONE 的 `mw-model-error-perception` 定死，不存在需要外部调研或代码探索才能确定的未知：

1. **校验规则已是既有事实**：`packages/multi-workers/mw_common.py:365`（`validate_fallback_models`，含 `FALLBACK_MAX_MODELS=4`、`CLI_PREFIX_TO_CLI` transport 前缀拒绝、`KNOWN_MODEL_PREFIXES`、归一化与去重）——本 key 直接复用，不重新定义。
2. **写入契约已是既有事实**：`packages/multi-workers/mw.py:3444`（`_dispatch_extra_keys` 读改写保留其它顶层键）与 `mw-model-error-perception` T-02 的落地说明（`.agenticdoc/mw-model-error-perception/tasks/T-02-fallback-config.md`）。
3. **运行期消费方已定**：链顺序由 launcher 按数组顺序消费（`.agenticdoc/mw-model-error-perception/evidence/quality-gate-report-20261015.md` 门禁输出与 2026-10-15 生产 trace 实证）。
4. **CLI 风格已有样板**：`mw.py` 的 `model set/clear/show` 分支（同一文件 3482 起）与 TS 侧 `runMwModelCommand`（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3302`）。

因此需求面（用户要求「CLI 可设置 + 按序数组」）到实现之间没有需要调研消解的分歧；直接进入实现，证据由测试执行与 R-01 独立复核提供。

## 未覆盖（交由 R-01 复核与后续 key）

- 未调研 timi 代理链上游（`gpt-6.1-sol` 的 stream 中断）——属外部路由问题，与本配置面无关。
- 未研究 per-phase fallback 的可行性——已在 spec §4 明确超出范围。
