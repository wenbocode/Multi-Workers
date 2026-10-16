# Plan: mw-model-error-perception

> Key: mw-model-error-perception
> 创建时间: 2026-10-15
> 输入: spec.md（AC-001~010）、design.md（§1 架构 / §2 决策 D1-D7 / §3 模块 / §4 协议 / §5 测试）

## §1 并行性分析

- 可并行单元：4 个编码任务按文件边界切分——T-01（TS worker-mode.ts+output-writer.ts）、T-02（Python mw.py+mw_common.py）、T-03（Python launcher.py）、T-04（TS pm-orchestrator.ts），互不重叠。
- 共享资源与冲突面：协议契约（design §4：env 格式/trace 行/退出码 3/dispatch.yml 键）为跨任务契约，已在 design 冻结，各任务照约实现；测试任务依赖实现任务（T-05←T-01/T-04，T-06←T-02/T-03）。
- 必须串行：Stage 2 测试任务（依赖 Stage 1 产物）；Stage 3 收尾（全库 check + 套件 + 文档，单 worker）。
- 相位文档由 PM 串行完成，不派 worker。

## §2 任务分解与派发

| 任务 | 类型 | 写入允许面 | 依赖 | AC 映射 |
|------|------|-----------|------|---------|
| T-01 worker 侧错误状态机 | coding | worker-mode.ts、output-writer.ts | - | AC-001/002/003/004/005（worker 半）、D1/D3/D4/D6 |
| T-02 fallback 配置层 | coding | mw.py、mw_common.py | - | AC-008（配置半）、AC-009（预校验半）、D5 |
| T-03 launcher 重派链 | coding | launcher.py | 契约（design §4），无文件依赖 | AC-008（重派半）、AC-009（trace/预校验半）、AC-001（有界性）、D6 |
| T-04 PM model-error 告警 | coding | pm-orchestrator.ts | - | AC-006、D7 |
| T-05 TS 测试 | coding | packages/coding-agent/test/**（新增文件） | T-01、T-04 | AC-005/007 |
| T-06 Python 测试 | coding | packages/multi-workers/test_*.py（新增/扩展） | T-02、T-03 | AC-007/008/009 断言 |
| T-07 收尾 | coding | CHANGELOG、README/docs、golden | T-05、T-06 | 全 AC 终验 |

阶段：Stage 1 = T-01∥T-02∥T-03∥T-04（4 worker 并行）；Stage 2 = T-05∥T-06；Stage 3 = T-07；质量门（PM 主导）→ verify。

## §3 契约冻结（各任务共同遵守，源自 design §4）

- 退出码：0=done / 2=needs-clarification / 3=model-exhausted（run.json status 均按 markOutcome：3→failed）/ 其他=failed
- env：`PI_WORKER_MODEL_ERR_MAX`（int，默认 2，0=禁用计数仅记证据）、`PI_WORKER_FALLBACK_MODELS`（csv "provider/model"）、`PI_WORKER_FALLBACK_INDEX`（int 从 0）、`PI_WORKER_TRIED_MODELS`（csv，含主模型）
- trace 行：`[MODEL_ERR] <iso> model=<p/m> run=<k> err=<≤200>`（worker 写）；`[MODEL_FALLBACK] <iso> from=<m> to=<n> attempt=<k>`（launcher 写）；`[IDLE_KILL]` 追加 `last_model_error=yes|no`
- dispatch.yml：顶层 `fallback_models: {<type>: ["provider/model", ...]}`，上限 4，与主模型去重
- run.json 新字段：`model_exhausted: true`（exit 3 时）；Exit Reason 终局形如 `model unavailable: tried=a(2),b(2) last=<err>`
- 禁改面：packages/ai、pi core、`~/.pi/agent` 任何文件、conductor stalled-gate

## §4 验收命令（各任务卡内落地）

- TS：`npm run check`（相关包）+ `node ../../node_modules/vitest/dist/cli.js --run test/<file>` 指定套件
- Python：`python -m pytest test_<file>.py -x`（packages/multi-workers 下）
- 收尾：`npm run check` 全绿 + `./test.sh` 相关套件 + pytest 全绿

## §5 风险与回退

- 活动钟语义变更回归：T-05 时序级断言覆盖既有 worker-idle-heartbeat 期望；破坏时回退方案=仅加 [IDLE_KILL] 标记不移除喂钟（design D4 方案 B）
- `_model_write` 丢键：T-06 专项断言；回退=显式键拷贝
- 重派风暴：重派上限=fallback 数组长度，无额外配额；PM 告警 K=2 兜底
