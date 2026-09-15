# Achieved: mw-widget-terminal-lifecycle

> 完成日期：2026-09-10
> 质检通过：evidence/quality-gate-report-2026-09-10T1755.md（38/38；指纹重锚 95d6a253ba12）
> 评审：evidence/runs/review-2026-09-10.md（LGTM，S1~S3 当日修复）

## 做了什么

修复 agent-team-loop 底部 watch widget 的三类现场问题（OverCode 项目取证），全部落在扩展域（TS）+ launcher 域（Python），队列协议（GC-4）零改动：

1. **AC-001~003 widget 三区渲染**：live（running→pending，区内 newest-first）/ unhandled（未 ack 的 failed/nc，永不折叠，header 带 `N unhandled` 计数）/ history（done ∪ acked，新→旧 cap 5 + `+N more`）——替代旧的全体 cap 6，终态行堆积与手动回收不更新两个现场问题同时消除
2. **AC-004~006, 010, 011 ack 通道与持久化**：sidecar `.agenticdoc/_workers.acked`（workers.lock + tmp/rename，幂等）+ `/mw ack <key>|all` 命令 + `ack_worker_result` 工具（PM-only 注册，worker 模式零注册）+ list_tasks `acked` 徽标 + PM_CONTINUE_HINT ack 指示；拒绝非终态行且不落盘；ack 后 dispatchNewTasks 不重派
3. **AC-007~009 终态 detail 取源**：按状态回退链（failed：spawn 原因→Exit Reason；nc：Questions→worker.log 尾（256KB guard）→no-output 提示；done：TL;DR→清洗 Summary 首行），统一剥 markdown 前导标记；TL;DR 由 worker 侧 writeOutput 首节写入（headline 归一化 ≤100 字符）+ starter 单句指令双保险
4. **AC-012, 013 孤儿 running 行 reconcile**：launcher `_poll_once` 内新增 reconcile 步（beat→archive→reap→reconcile→discover→spawn），正证据（[END] exit 0/1/2 三映射 / output.md-only→failed+unverifiable）每 poll 无条件；静默 90m（`PI_WORKER_ORPHAN_DEAD_MIN`） presumed dead；beat 协议（`.mw/launcher-beat.<pid>`，30s 新鲜阈）让静默规则对其他存活 launcher 退让；过期且 pid 已死的 beat 顺手清理（review S2）

## 目标与产出

- 现场（OverCode）：超时/失败 worker 的 widget 行永不消失 + detail 无信息量 → 三区渲染 + 按状态取源 + PM ack 语义闭环；mw serve 重启后孤儿 running 行永久滞留 → launcher reconcile 收敛（三条路径闭合：存活 worker 不误杀 / 完成走 [END] / 挂死 90m 收敛）
- 验证：TS 121/121（agent-team-loop 106 + ack 5 + output 8 + S1/S3 2 + 原 VC 用例）、Python 365 passed（含 reconcile 17 + S2 2）；[VERIFY] 埋点 VC-001~013 全量输出；bundle 重建 + 全局安装 + 安装产物冒烟（activate→/mw ack 拒绝/落盘/工具等效/徽标）；mw serve 重启后新 launcher beat 生产实证
- 生产环境已切换：mw serve 89364 运行新 launcher；widget 新渲染随 pi 窗口重启生效

## 遗留与移交

- packages/ai 基线漂移（26 tsgo + 8 运行时失败，catalog 演进 vs 过时代码/测试，非本 key 引入）→ 移交新 key `ai-baseline-repair`
- packages/agent 2 + coding-agent core 85 Windows 环境性失败 → 同上，先 CI 归因再定修/不修
- 冒烟副作用留痕：wtl-t03/t04 两行 done 被 ack（演示态，无功能影响）

## 学到了什么

- PowerShell→bash 传参的内层双引号会被吞（外双内单才可靠）；`Get-Content`/`Select-String` 的 CJK 乱码是显示层，edit 工具按 UTF-8 真实内容匹配
- 早前会话 ad-hoc 计算的指纹（无 canonical 脚本固化）不可复现——本次以 quality-gate 文档管道重锚并在 evreq 留 provenance 注记；教训：指纹必须用文档化管道计算并当场可复验
- 队列行 7/8 列协议的双侧解析器（TS WorkerStore / Python parse_workers_file）是所有状态类特性的地基，sidecar（`_workers.acked`）比第 9 列或新 status 值便宜得多
- reconcile 的「正证据无条件 + 静默规则量化窗口 + beat 退让」三段式让 kill -9 双 launcher 场景不误杀也能收敛；own running_procs 行绝不触碰是单写者纪律的关键
