# Quality Gate Report: mw-parallel-protocol

**时间**: 2026-09-22T21:52+08:00
**触发**: T-01 完成（PM 直执）
**范围**: 全量（单 task）

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | 协议追加进 `systemPrompt`，原提示保留为前缀 | 充分 | `agent-team-loop.test.ts` 用例 1（`startsWith("BASE\n\n")` + `endsWith(PARALLEL_PROTOCOL)`） | L1 |
| Q-AC-002 | 四类动作规则齐备（分析 / 调研批量 / 编码边界 / 相位文档串行） | 充分 | 用例 1 五条文本断言（marker、先做并行性分析、RQ-1..N、note 路径模板、同文件互斥、相位文档） | L1 |
| Q-AC-003 | 幂等（回喂自身输出不再追加） | 充分 | 用例 1（`toBeUndefined()`） | L1 |
| Q-AC-004 | 空/缺失 systemPrompt 不抛异常 | 充分 | 用例 1（`{}` → 纯协议文本） | L1 |
| Q-AC-005 | worker 模式不注入 | 充分 | 用例 2（`workerModeActivate` 的 before_agent_start 输出不含 marker） | L1；PM-only 另有 `index.ts` if/else 结构性保证 |
| Q-AC-006 | 零 error/warning/info + 回归无新增失败 | 充分 | `npm run check` exit 0（biome 1080 files、tsgo --noEmit 无输出）；`agent-team-loop.test.ts` 170 passed | L0 + L1 |
| Q-VC-L2 | 真实 PM 窗口系统提示确实含协议 | 不足 | — | 需 `mw build --install` + 重启窗口人工确认；记验证欠债 1 项 |
| Q-REG-001 | 注入不破坏既有 PM 行为（门禁、poll loop、命令注册） | 充分 | 同文件全量回归 170 passed（含 implementation-gate / pmActivate lifecycle / ack 等） | L1 |
| Q-DES-SCOPE | 未越界改动（未动门禁阈值、路由、worker、框架文档） | 充分 | `git status` 仅 3 个源/测试/变更日志文件 + 本 key 状态文件 | 代码审阅 |

## 汇总

- **总问题数**: 9
- **通过（充分）**: 8（88.9%）
- **有条件通过（不足）**: 1（验证欠债 1 项：Q-VC-L2）
- **未通过（无证据）**: 0

**质检结论**: 有条件通过（欠债 1 项，PM 已记录，用户知情）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|------|------|---------|---------|
| Q-VC-L2 | 无头环境无法构造真实 TUI 轮次 | `mw build --install` → 重启 PM 窗口 → 确认系统提示含 `[mw] 并行优先协议` | 结案后手工一步（非新 task） |

## 二次印证结论

无遗漏。二次核查确认两点：worker 侧结构性隔离（`index.ts` 分支 + 用例 2 双保险）、注入为追加式（前缀保留断言）而非替换。
