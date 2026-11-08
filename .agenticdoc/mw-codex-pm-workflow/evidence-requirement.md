# Evidence requirements

ac_fingerprint: 77f5c1909c96

| 验收 | 充分性判据 |
| --- | --- |
| AC-001 / VC-001 | 同时运行两次 CLI 派同卡，读取同一条真实队列行；无效卡、路径、claim、roadmap 所有者覆盖拒绝路径。 |
| AC-002 / VC-002 | 从独立进程分别读取排队与终态，核对卡引用、执行状态、产物和验收历史。 |
| AC-003 / VC-003 | 固定同一验收命令，对错误实现运行失败，对修复实现运行成功；保留两份日志。输出丢失或执行根变化时拒绝验收。 |
| AC-004 / VC-004 | 使用真实 AgenticTask 阶段脚本、PM dispatch_worker、launcher 及独立验证进程，完成后 audit_phase 重放通过。记录 worker 测试替身的边界。 |
