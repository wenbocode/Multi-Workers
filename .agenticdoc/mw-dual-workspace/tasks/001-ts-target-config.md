# Task 001: TS 侧 target-config（解析/模式判定/占位符渲染）

- Stage: S1
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，20/20 用例 + npm run check 全绿，证据 evidence/runs/001-ts-target-config.md）
- ac_refs: [AC-001, AC-004]
- vc_refs: [VC-001, VC-006, VC-007, VC-008]
- pattern_refs: []
- deps: []
- 预估: ~1.5h

## 交付物

- `packages/coding-agent/src/extensions/agent-team-loop/shared/target-config.ts`（新增）
- `packages/coding-agent/test/extensions/agent-team-loop-target-config.test.ts`（新增）

## AC 摘录（spec.md §3）

- AC-001: 不配置时行为与现状完全一致——single 模式缺省回落，解析根=cwd
- AC-004: Game/Engine 双目录显式配置；占位符 `{game}/{engine}/{uproject}` 渲染 fail-closed——缺 engine 引用时抛错带明确原因，不回退 game 根

## 实现要点（design.md D-002/D-010/D-014）

- API: `resolveWorkspaceConfig(cwd?)` → `{ mode, controlRoot, gameRoot?, engineRoot?, vcs, uprojectPath?, toolchain, ignore, contract, source }`；`renderToolchainCommand(cmd, config)`；`discoverUproject(gameRoot, explicit?)`
- 优先级: env `MW_TARGET_GAME`/`MW_TARGET_ENGINE` > `.agenticdoc/target.yml` > single（缺省 gameRoot=controlRoot=cwd）
- YAML 解析用 `yaml@2.9.0`（coding-agent 既有直接依赖，零新增，见 design note 补充核查）：`parse()` + try/catch → 损坏配置抛 `TargetConfigError`（fail-closed，不静默回落 single）
- 占位符渲染: 缺字段抛错（消息含缺失字段名 + 命令原文）；渲染后残留 `{game}/{engine}/{uproject}` 子串视为错误
- `{uproject}`: 显式 `uproject:` 字段优先；否则 game 根下唯一 `*.uproject`；0 个或多个 → 抛错（消息含发现数量）
- 遵守 AGENTS.md: 无 `any`、top-level import、erasable-only TS、无 inline imports
- 纯解析模块（fs 只读 target.yml 与 uproject 发现，无写副作用）

## 验证方式（VC 断言，测试输出含 [VERIFY] 行）

- VC-001: 无 target.yml 且无 env → mode=single、gameRoot=controlRoot=cwd → `[VERIFY] VC-001: mode=single roots-equal=true`
- VC-006: engine 配置 + `{engine}` 模板 → 渲染含 engine 绝对路径、无残留占位符
- VC-007: dual 缺 engine + 引用 `{engine}` → 抛错含原因，断言未回退 game
- VC-008: 唯一 uproject → 解析成功；0/2 个 → 抛错含数量
- 证据落盘: `evidence/runs/001-ts-target-config.md`（测试命令 + [VERIFY] 行摘录）

## 依赖与阻塞

- 无前置。Task 002 parity 以本模块行为为参照。
