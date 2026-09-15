# Task 004: read-scope deny globs（双基准匹配 + deny 优先）+ worker 拦截器接入

- Stage: S2
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，24/24 + 关联 139/139 + check exit=0，含 D-003 [EXEC 注记] 目录自匹配修正，证据 evidence/runs/004-read-scope-deny.md）
- ac_refs: [AC-006]
- vc_refs: [VC-011, VC-012]
- pattern_refs: []
- deps: [001]
- 预估: ~2h

## 交付物

- `packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts`: denyGlobs 解析（task.md frontmatter `deny_globs:` 列表）+ verdict 扩展 `deny-glob` + block 原因输出
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`: read/ls/find/grep 四类拦截器接入 deny 分支（判定顺序: deny 先于 scope allow——deny 优先）
- trace: block 时经 appendReadScopeTraceLine 写 `[READ_SCOPE] rule=deny-glob` 行
- `packages/coding-agent/test/suite/autopilot-read-scope.test.ts` 扩展 deny 用例

## AC 摘录（spec.md §3）

- AC-006: ignore 配置节的 deny globs（`**/*.uasset` 与 `DerivedDataCache/**` 形态）在调用级 100% 强制拦截，block 有 trace 记录

## 实现要点（design.md D-003/D-004，实测依据 design note 补充核查）

- **双基准匹配**: 对「归一化绝对路径」与「game 根相对路径」各跑一次 minimatch，任一命中即 deny——minimatch 实测裸目录形态 `DerivedDataCache/**` 不匹配绝对路径（false）但匹配相对路径（true），双基准使 AC-006 两形态均生效
- minimatch@10.2.5 已是依赖；Windows 反斜杠绝对路径实测可直接命中 `**/*.uasset`（无需预归一分隔符；game 相对基准计算时统一 `\`→`/`）
- gameRoot 来自 Task 001 的 resolveWorkspaceConfig（single 模式 gameRoot=controlRoot，相对基准=相对控制根，行为自洽）
- glob 工具不在 L1 拦截范围（维持现状，design D-004）
- 代码锚点: worker-mode.ts:477-483（四类拦截器）、read-scope.ts 现有 verdict 流（allow/scope/cap-file/cap-bytes）

## 验证方式（VC 断言）

- VC-011: `**/*.uasset` + `DerivedDataCache/**` 两形态 × read/ls/find/grep 四工具 → 100% block + trace 含 rule=deny-glob → `[VERIFY] VC-011: deny-block-rate=100 trace-has-reason=true`
- VC-012: 同路径命中 allow scope + deny glob → block → `[VERIFY] VC-012: precedence=deny`
- 证据落盘: `evidence/runs/004-read-scope-deny.md`

## 依赖与阻塞

- 依赖 001（gameRoot 解析）。与 005 无依赖关系，可并行。
