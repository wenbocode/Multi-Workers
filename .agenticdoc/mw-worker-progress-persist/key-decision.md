# KDR: mw-worker-progress-persist

## R（需求）

- 技术栈: TypeScript 扩展（packages/coding-agent/src/extensions/agent-team-loop/**，bundle → packages/multi-workers/dist/extensions/agent-team-loop.js）+ Python parity（packages/multi-workers/autopilot/dispatch.py REGISTRY）。
- 边界（不做什么，一句话）: 不给只读角色任意路径写能力、不引入服务端状态、不改超时判据、不解决 provider 流中断本身。
- 关键约束: 写入面必须限定在 worker 自身目录内的白名单文件名；框架自有文件（task.md/trace.log/worker.log/output.md）不可被 worker 工具写入；TS/Python 白名单 parity 锁同步。
- 触发来源: 2026-09-23 用户反馈「worker 写入不了 progress.md，请编排方代为追加」，实例 = OverCode `chroma-review-evidence-r1`（type: review，read/find/grep/ls，146 次工具调用 writes=0，30/40/50m 三次检查点均只能口头求代记）与 `chroma-review-lifecycle-r1`（同限制，PM 已事后从 session 代记）。
- 用户决策: 2026-09-23 确认「开 key 做 (a) 只读角色 worker 目录受限写 + (c) mw 侧自动记录检查点」。

## A（架构）← system-design 追加

- D-101 落盘通道形态: 选「专用窄工具 worker_file」，否「通用 write/edit + 路径守卫」（无路径解析 → 漏拦不可达；证据文件不可写）
- D-102 白名单文件名: 选「progress.md + report*.md 正则（仅 basename）」，否「任意 *.md」（任意 *.md 会放行 task.md）
- D-103 output.md 归属: 选「不可写，报告落 report*.md」，否「纳入白名单」（避开 harness D-117 合并语义双写）
- D-104 机器行角色范围: 选「仅无写工具角色」，否「全角色统一」（coding 已有自评行，避免双轨）
- D-105 机器行格式: 选「CKPT <n>m [machine] …」，否「与 [CHECKPOINT] 同构」（需与自评行可区分）
- D-106 集合计算挂载点: 选「新 activeToolsForType，TOOL_ALLOWLISTS 表不动」，否「直接改白名单表」（保 parity 锁，零 Python 改动）
- D-107 机器行写入器: 选「appendProgressLine 追加语义」，否「writeOutput / open(w)」（append-only 且规避 P-003）
- D-108 窄工具写入计数: 选「不计入 WRITE_TOOLS」，否「计入」（保住零产出信号）
- D-109 拒绝留痕: 选「复用 [TOOL]/[TOOL_ERR]」，否「新 trace 行类型」（免改 heartbeat 解析器）

## I（实施）← PM 执行中追加
