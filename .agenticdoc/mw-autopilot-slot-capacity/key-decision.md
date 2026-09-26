# KDR: mw-autopilot-slot-capacity

## R（需求）

- 技术栈: Python（multi-workers: conductor/launcher/serve/mw.py）+ TypeScript（agent-team-loop: monitor/status-model）
- 边界: 不重写调度架构、不引入中央调度器（GC-1）；不改 pi 核心；proxy/凭证机制只在被证明是瓶颈时才作为依赖项记录
- 关键约束: 并行度是**文件驱动协调**下的参数（`_index.parallel` + 文件锁）；提高并行度会同时放大共享文件写竞争与跨 key 冻结面风险
- 用户原始提问（2026-09-26）: "当前 autopilot 的 slot 为什么只有两个，并行度是不是不够"
- 需求本质（PM 初判）: 用户问的是**上限的成因与充分性**，不是"给我改大"。因此本 key 的第一交付是**证据**（成因三态判定 + 槽位利用率实测），第二交付才是"改 / 不改"的结论与落地方案。
- `[待确认]` U-1..U-5 见 spec §4（目标形态 / 现象 / 成本容忍 / 层级 / 多项目计额）

## A（架构）← system-design 追加

## I（实施）← PM 执行中追加
