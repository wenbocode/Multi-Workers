# mw-dp-material-pipeline 结案回查

2026-11-23，通过 `codex_pm.py done` 结案。权威索引与状态回读均为 `DONE / idle`，ClaimId 清空，`active_keys` 已移除本 key。正常入口核验 18 项 AC 的当前结案检查，逐项复读原签收绑定的 QG 39 项和 v0.5 36 项，复用原 `sign-final.md`。 [Done 回执](done-receipt.json) · [认领回读](done-readback.json) · [结案核验](acceptance-revalidation.json) · [正式验收记录](all-criteria-verification.json)

v0.5 实现对账为 32 项差异有据和 4 项符合预期拒绝。QG、签收的哈希和独审 run 均与原回执一致。独审证据按原字节归档。旧 dp-auto 保留为空的历史回执，以及本次 PM 零发送接回记录。 [36 项对账](../ac003-local-budget/v05-four-stage-comparison.md) · [QG](../../quality-gate-report-ac003-cx-ee474fbc353feb7aba95.md) · [Sign](../../review/sign-final.md) · [独审终态](terminal-review/run.json) · [独审报告](terminal-review/report.md)

Done 入口支持读取冻结合同要求的当前签收。正式独审绑定的 `achieved.md` 原文用于交付结果，旧 Worker 的处置记录来自 Codex PM 主记录。轻量结案回归在工作区通过 25 项。

构建以已提交基线和本 key 的源码清单为输入。隔离快照运行离线构建和 MW bundle 自检。全量静态检查时复用了工作区一处既有、仅用于检查的 PM-state 测试参数修正，构建前恢复该测试的基线版本。本 key 提交与全局运行产物仅包含清单内的功能改动。 [构建源码清单](build-source-snapshot.json) · [静态检查](npm-check.log) · [离线构建](build-offline.log) · [MW bundle](build-extension.log)

发布快照回归最终为 195 项通过、1 项跳过。初次快照遗漏的 QG、sign、auto 三份随包样例已连同生成脚本补齐。全局 `mw`、`pi`、MW bundle 和两个路径指针已切换，安装脚本保存了旧入口。新进程验证 Pi `0.83.0`、八个随包决策样例及本地预算 1000/1001 边界。 [发布回归](release-pytest.log) · [全局安装回执](global-install.json)
