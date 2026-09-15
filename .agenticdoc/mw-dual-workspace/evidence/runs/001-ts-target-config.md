# Evidence Run: 001-ts-target-config

- Date: 2026-09-11T16:50:00+08:00
- Task: 001-ts-target-config（S1）
- Deliverables:
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/target-config.ts`（新增，~330 行）
  - `packages/coding-agent/test/extensions/agent-team-loop-target-config.test.ts`（新增，20 用例）

## 测试命令与结果

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-target-config.test.ts --silent=false

Test Files  1 passed (1)
      Tests  20 passed (20)
```

## [VERIFY] 行（测试 stdout 摘录）

```
[VERIFY] VC-001: mode=single roots-equal=true
[VERIFY] VC-006: rendered-contains-engine=true unresolved-placeholders=0
[VERIFY] VC-007: exit-nonzero=true fallback=false
[VERIFY] VC-008: uproject-resolved=true ambiguous-fail=true
```

## VC 覆盖明细

| VC | 断言 | 用例 |
|----|------|------|
| VC-001 | 无配置 → mode=single、gameRoot=controlRoot、source=default | "no target.yml and no env → mode=single..." |
| VC-006 | {engine}/{game} 渲染含绝对路径、无残留占位符 | "renders {engine} and {game} with no leftover tokens" |
| VC-007 | dual 缺 engine 引用 {engine} → TargetConfigError(missing-field)，消息不含 game 路径（无回退） | "dual without engine referencing {engine} throws" |
| VC-008 | 唯一 *.uproject 解析；0/2 个 → ambiguous-uproject 含数量；显式字段优先；显式缺失 → uproject-not-found | "unique/0-or-2/explicit" 三组 |

## 全量检查

`npm run check`（repo 根，2026-09-11 16:47）：PASS（biome check + pinned-deps + ts-imports + shrinkwrap + install-lock + tsgo --noEmit + browser-smoke 全绿；biome 自动格式化 1 文件后测试复跑仍 20/20）

## 实现偏差记录

- 初版判定顺序 bug：`mode: single` + `game:` 时 game 非空分支先命中，矛盾检查成死代码——测试抓住（"mode single with a game field is contradictory" FAIL），修正为文件内矛盾先于优先级判定。测试先红后绿，偏差已闭环。
- env game + 文件 mode: single → env 胜出为 dual（env 是显式覆盖，design D-011 优先级语义），已含用例（"env game overrides target.yml game" 反向未加单独用例，语义由优先级用例覆盖）。

## 环境备注

- git status 显示 `packages/multi-workers/autopilot/dispatch.py` 与 `test_autopilot_dispatch.py` 有**其他会话**的未提交改动（provider 路由 ""→"timi"）；本 task 未触碰这两个文件。
