# Quality Gate Report: autopilot-monitor

**时间**: 2026-09-11T17:20:00+08:00
**触发**: T-01 + T-02 完成，全量质检（合入前）
**范围**: 全量（AC-001..009 / VC-001..011 / Coverage F1-F8）
**执行**: PM（本窗口），独立复验 + worker 证据交叉核对

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec AC 编号 | ✅ AC-001..009 |
| design VC 编号 | ✅ VC-001..011 |
| AC→VC 覆盖 100% | ✅（9/9，机械比对） |
| evidence-requirement.md | ✅ 存在 |
| ac_fingerprint 一致 | ✅ 记录 77e45dafd9cb = 当前 spec 重算值（spec 锁定后未变更） |
| evidence/runs/ 非空 | ✅ t02-verification.md（L0/L2）+ workers/*/progress.md（L1） |
| task ac_refs/vc_refs | ✅ 任务书正文逐条绑定（T-01: VC-001..008/011；T-02: VC-009/010） |

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 |
|--------|------|------|---------|
| Q-AC-001 | 开启 ≤1 周期出面板，serve 行 PID+fresh/stale | ✅ 充分 | VC-001（首帧 0 tick，实测先于 timer advance） |
| Q-AC-002 | conductor 死亡 ≤2 周期变 dead | ✅ 充分 | VC-002（dead pid 帧 0 即现；活 pid 翻转验证） |
| Q-AC-003 | running workers 行 + 分钟数 | ✅ 充分 | VC-003（2 行 running ceil(90/60)=2m，done 行缺席） |
| Q-AC-004 | pending gates 行 + 归零 | ✅ 充分 | VC-004（approve 后下 tick 归零） |
| Q-AC-005 | off 清面板不重建 | ✅ 充分 | VC-005（clear + 推进 1000ms 零新调用） |
| Q-AC-006 | print 模式降级 | ✅ 充分 | VC-006（"no visual UI" 提示、0 widget 调用、无异常） |
| Q-AC-007 | serve down 显示指引 | ✅ 充分 | VC-007（"not running -> /mw restart"，其余段照常） |
| Q-AC-008 | 纯只读无副作用 | ✅ 充分 | VC-008（3 tick 前后 .mw/_autopilot 全文件 sha1 不变）+ VC-009 |
| Q-AC-009 | 单窗口内存态 | ✅ 充分 | VC-009（L0）+ VC-010 + VC-011（双模块实例隔离） |
| Q-VC-001..011 | 各 VC [VERIFY] PASS 证据 | ✅ 充分 | t01 progress.md（VC-001..008,011）+ t02-verification.md（VC-009,010） |
| Q-COV-001 | F1 命令入口/toggle/hasUI | ✅ 充分 | wiring 测试（toggle 语义、USAGE、幂等 off） |
| Q-COV-002 | F2 serve 行（含 stale/meta 缺失回退） | ✅ 充分 | VC-001/007 + stale 变体 + PM 补测（长 detail 截断保 hint） |
| Q-COV-003 | F3 conductor 行（含 paused/未启用边界） | ✅ 充分 | VC-002 + PM 补测（paused:true / everEnabled:false 直接断言） |
| Q-COV-004 | F4 workers 区（0 running 折叠） | ✅ 充分 | VC-003 + PM 补测（"workers: 0 running"） |
| Q-COV-005 | F5 gates 行（目录缺失/非法 frontmatter） | ✅ 充分 | VC-004 + PM 补测（"gates: 0 pending"）；非法文件跳过在实现 L151-160 |
| Q-COV-006 | F6 生命周期（首帧即时/幂等/窗口关闭） | ✅ 充分 | VC-001/005 + wiring 幂等分支；interval 属扩展进程，窗口关闭随进程消亡（L0 架构事实） |
| Q-COV-007 | F7 只读性 | ✅ 充分 | VC-008/009 |
| Q-COV-008 | F8 双 widget 并存 | ✅ 充分 | VC-010（同 fake UI 双 id 互不覆盖、交错刷新保帧、off 只清 monitor） |
| Q-X-001 | AC-001/AC-005 开关交互（toggle 竞态） | ✅ 充分 | wiring 测试（无参双次 = on→off；重复 off 通知不误清） |
| Q-X-002 | AC-006×AC-009（headless 不留状态） | ✅ 充分 | VC-006（started=false + isMonitorActive 仍 false） |
| Q-X-003 | spec §2.2 性能预算（单轮询 <100ms） | ✅ 充分 | PM 实测（下方 SP-001） |

## PM 独立复验（不信 worker 转述）

- `npx tsgo --noEmit`（repo 根）→ exit 0
- vitest：autopilot-monitor（12/12，含 PM 补测）+ autopilot-console + agent-team-loop → **159 passed**（此前 worker 报 158，PM 补 1 条边界测试）
- `npm run check` → exit 0 全绿
- 指纹重算 → 77e45dafd9cb 一致

## SP-001 性能实测（PM，dist 构建）

```
readMonitorState x50（真实 repo 项目，含 serve/conductor/config/workers/gates 全源）: avg 1.46 ms/call
PASS: < 100ms budget (spec §2.2)
```

附产物：真实快照显示本 repo serve 被正确判为 STALE（serve 14:35 启动 < 代码 17:11 变更）且面板文案含恢复指引——特性在自身仓库上首跑即生效（dogfood PASS）。

## PM 直执补齐（QG 过程中发现的两处低于 VC 粒度的边界缺口）

1. `renderMonitorLines` 边界直接断言测试（paused conductor / never-enabled / 0 running / 0 pending / 长 stale detail 截断保 `/mw restart` hint）→ autopilot-monitor.test.ts 第 12 条，PASS
2. 任务卡 ac_refs/vc_refs 正文绑定已确认（T-01 → VC-001..008+011；T-02 → VC-009+010）

## 汇总

- **总问题数**: 22（Q-AC 9 + Q-VC 汇总 1 + Q-COV 8 + Q-X 3 + SP 1）
- **通过（充分）**: 22（100%）
- **有条件通过（不足）**: 0
- **未通过**: 0

**质检结论**: ✅ 通过

## 遗留备注（非欠债）

- D-003 视觉叠放顺序（monitor 与 watch widget 在实屏上的上下排布）超出 harness 证明范围（id 契约与互不覆盖已证）；建议用户首次实窗使用时目视确认，异常则走 design 的合并 fallback。
- 本 repo serve 当前 STALE（代码晚于 serve 启动）——新窗口打开时会提示 `/mw restart`，属预期行为。
