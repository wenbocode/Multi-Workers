# 需求依据

用户选择了此前讨论的方案 1 和 4，并要求开发至验证。项目 goal.md 确立文件协调和进程隔离。pm/ui-bridge.ts 的 registerWorkerTools 已提供带显式 task_key 和任务卡检查的 dispatch_worker。launcher.py 消费同一 workers 队列。上述实现决定了本次应复用现有派工入口；项目级 phase 使用 AgenticTask 脚本管理。
