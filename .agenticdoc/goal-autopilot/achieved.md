# Achieved: goal-autopilot

## 做了什么

在 mw 框架之上交付了 goal-autopilot 自主编排层，18/18 任务（S0 基线 1 / S1 Python 基础设施 7 / S2 conductor 4 / S3 TS 侧 3 / S4 收口 3）全部完成，四轮质检收敛至合入前口径 PASS（A=72 B=0 C=0，无 ❌ 无 ⚠️）。

- **Python 基础设施（autopilot/ 11 模块 + 262 用例）**：config/advance（AC-005 推进只经脚本）、roadmap+roadmap_check、timeline（append-only + 轮转 + 容错）、gates（幂等消费双层）、dispatch（5 类型注册表 + 锁内追加读回校验）、state（claim 四态 / usedRounds distinct-attempt）、audit_evidence（L1 dossier）。
- **conductor（S2）**：serve 监护（D-101 respawn ≤1s）、per-key phase 机（L2 缺口回路 / 预算 / stalled 四产物 / 孤儿和解）、stage 机 + gate 生命周期 + 闭环 dossier、EXECUTE 任务环（plan 序 / 每 key 串行 / 失败计预算）+ L3 收敛环（meets/below 二值 + repair）+ done 六步事务（D-108 check-before-write）。
- **TS 侧（S3）**：worker read-scope 定点读取（界内放行/越界拒绝留痕）、协议增量（typed allowlist fail-closed + [START] pid + 未知 type 拒绝）、/autopilot console（status --json / 视图奇偶 / 时间线水位重放 D-109）。
- **验证层（S4）**：L2 进程链 e2e（真 conductor/launcher/serve + 框架副本真门禁 + PATH 遮蔽 stub，零 LLM 零网络，7 测试 10 组 [VERIFY]）；L0 静态门禁 + 双侧注册表活解析奇偶；全量收口（bundle 重建安装 + VC-001~027 全索引 + AC-012 基线对照零回归）。
- **质检修复轮**：L3 预算配置化（真缺陷：硬编码 2 违三回路共用预算源）、l3-verdict 落盘（dossier 裁决列闭合）、真进程 kill/respawn e2e、多项目隔离 e2e、VC-018 erratum（tick 语义阈值）、平台 Windows-only 裁决。

## 目标收益

单 PM 窗口的 goal 级自主推进落地：conductor 按 roadmap/plan 自动派发、按 phase 门禁推进、按预算收敛失败回路；goal.md 变更 halt 保全对齐；全链证据机械可提取（[VERIFY] 行 + 三层日志）。验证基线：L1 367 passed、L2 e2e 7/7、L0 5/5、vitest 59+106、真 timi e2e 1 passed、smoke 9-0、npm check coding-agent 零错。

## 遗留

见 evidence/runs/final-verification.md §5（7 项，含 2 项已修复标注）：Windows 原子替换窗口竞态（生产读方全带兜底，锁协议下零丢失已证）；l2 cap 不落盘 task.md（worker 缺省回退）；锁协议前提；静态扫描限度；e2e_l2 默认排除；并行会话工作树归属；~~l3-verdict 断言~~（已修复）。

## 提交

- `4c7c07c43` feat(multi-workers) Python S1+S2
- `c28edf7b2` feat(coding-agent) TS S3
- `fceae6eaf` test(multi-workers) L2 e2e + L0 parity gates
- `5e8ecf39d` fix(multi-workers) conductor L3 budget from config + l3 verdict persistence
