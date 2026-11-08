# Codex PM 工作流设计

## Function Flow

Codex 在控制工作区使用项目自带的命令行。写操作指定已认领的 key 和卡名。派发调用已有 PM 工具 dispatch_worker，传入卡来源、稳定的 worker 标识和执行角色，沿用 MW 的文档、信封、路由、写入范围门禁。MW launcher 从共享队列启动 worker。查询从索引和队列恢复身份，并返回 worker 产物路径。PM 在独立进程中运行卡上约定的验收程序，报告写到该 key 的 evidence 目录，可在之后的 VERIFY 阶段引用。

## Coverage Matrix / Verification Contract

| 标准 | 断言 | 验证手段 |
| --- | --- | --- |
| AC-001 | VC-001 同卡重派保持同一任务，拒绝越界卡、无效卡、其他写者的活跃 claim | 调用生产派工入口，检查队列和退出状态 |
| AC-002 | VC-002 在另一进程按 key 查询，重建 worker 路径、执行和验收状态 | 在收割之前和之后调用只读查询 |
| AC-003 | VC-003 只有成功的 worker 和非空产物可进入验收。新进程执行约定命令，独立记录每次成功或失败 | 真子进程执行失败和成功断言，检查结果、退出码及日志 |
| AC-004 | VC-004 跑通 Codex PM → 原有派工 → 真实 launcher → 隔离 worker → PM 验收，按现有门禁结案 | 定向跨进程测试、根检查、操作指南 |

## 决策

使用本仓库的 pi PM 工具和 Python 的队列、目标工作区解析函数，以降低双写分歧。采用本地 CLI，不引入远端依赖。验收命令使用 argv 表示，以明确空格和参数边界。每次验收独立留档，保留失败历史。详见 evidence/research/design-entry.md。
