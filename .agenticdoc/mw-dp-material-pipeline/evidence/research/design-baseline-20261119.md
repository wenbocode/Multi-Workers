# Research: 设计复用与接入边界

## 决策问题

为design D-001—006和任务写面确定可复用入口、待确认参数及证据要求。

## 方法与出处

仅本地读取docs详细设计第3—14/17节、prepare-worker-contract.json、development-guide.md；枚举packages/multi-workers的decision/来源/现有测试和agent-team-loop PM/Worker模块。未对所有生产文件做完整源码审计，不将文件存在当成能力已经接入。相关历史能力/坑点来自_arch_snapshot与_pitfalls P-001/003/005/006/007。

## 发现

存在决策后端、来源范围/材料诊断、PM工具、读写隔离、continuity及suite/faux入口，可作为候选接入面。精确接口与当前未提交变更须实施前完整阅读；本轮不改它们。已有真实捕获需要保持原schema/字节，规范差额不能通过改实验原件“补绿”。

## 结论与决策

复用既有文件/锁/预算/发送通道，专属投影+状态/权限守卫+同版反解。任务T03/T04默认因热文件共享串行，最终T09另一个执行者报告-only独立复核；本轮不派出任何Worker。
