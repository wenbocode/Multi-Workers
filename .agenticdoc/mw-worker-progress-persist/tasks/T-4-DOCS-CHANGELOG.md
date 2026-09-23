# Task T-4: 变更记录与文档同步

## 元信息
- Stage: 3
- 依赖: T-3（文案需与最终实现文本一致）
- 风险: 低
- Agent: PM 直执（不派 worker）
- ac_refs: [AC-010]
- vc_refs: [VC-010]

## 背景

本 key 改变了 worker 侧的两处用户可见行为：只读角色的检查点证据落盘位置、以及只读角色可用的窄工具；同时给只读角色新增了工具面。既有文档/注释中对 `progress.md` 的陈述需要与新行为对齐（P-008：删改符号后文档静默过期）。

## 交付物

1. `packages/coding-agent/CHANGELOG.md` 的 `[Unreleased]` 下新增一条（说明：只读角色缺少落盘通道导致检查点自评只能口头求 PM 代记 → 新增窄工具 + 机器检查点行 + 角色化 steer；生效需 `mw build --install` + 新 spawn）。
2. `packages/multi-workers/CHANGELOG.md` 的 `[Unreleased]` 下新增一条（从 bundle 使用者视角描述同一变更）。
3. 文档同步：以 `rg -n 'progress\.md' packages/coding-agent/src packages/multi-workers --glob '!node_modules' --glob '!dist' --glob '!.agenticdoc'` 的命中清单为准逐处核对，至少包含：
   - `packages/multi-workers/docs/dual-toolchain-practice-guide.md:367`（发散判据写的是「无 progress.md」——改造后只读角色任务也会自动有机器行，需改写为「无自评行/只有机器行」之类）；
   - `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:556`（升级消息把 progress.md 当证据）——核验后保留有效；
   - T-3 已同步的源码内注释与 steer 文本：核验不再有「请把一行追加到 …progress.md」对只读角色的错误指令陈述。

## 约束

- 只追加到既有 `[Unreleased]` 小节（先读全文，不重复创建子小节；已发布版本段落不可改）。
- 不改代码、不改测试、不改 dist。
- 不 commit。

## 验收命令

```
rg -n 'progress\.md' packages/coding-agent/src packages/multi-workers --glob '!node_modules' --glob '!dist'
rg -n -A 6 '^## \[Unreleased\]' packages/coding-agent/CHANGELOG.md packages/multi-workers/CHANGELOG.md
```

## 报告要求

列出：两条 CHANGELOG 条目原文、文档命中清单的逐处判定（需要改/不需要改及理由）。
