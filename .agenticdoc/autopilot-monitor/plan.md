# Plan: autopilot-monitor

> Key: autopilot-monitor
> 生成时间: 2026-09-11T18:10:00+08:00
> 依据: spec.md（AC-001..009, 指纹 77e45dafd9cb）+ design.md（D-001..D-007, VC-001..011）

## 任务总览

| 任务 | 类型 | 标题 | 依赖 | 主要产出 |
|------|------|------|------|---------|
| T-01 | coding | monitor.ts 模块 + console 命令接线 + L1 测试 | — | autopilot/monitor.ts、console.ts monitor case、vitest 全绿（VC-001..008, VC-011） |
| T-02 | research | L0 静态扫描 + changelog + 构建部署 + L2 双 widget 验证 | T-01 | CHANGELOG 条目、mw build --install、VC-009/VC-010 证据落盘 |

## 执行顺序

T-01 → T-02（严格串行：T-02 扫描/构建的对象是 T-01 的产物）。

## T-01 细化

单 worker 单上下文完成（模块 + 接线 + 测试一体，避免接口漂移）：

1. `autopilot/monitor.ts`（新文件）：
   - `MonitorSnapshot` 四段接口（serve/conductor/workers/gates，签名见 design §4.1）
   - `readMonitorState(projectDir, nowMs)`：复用 mw-runner 的 getMwStatus/serveStaleness/readServeMeta；conductor 读 `.mw/conductor.pid` + signal-0 + `_autopilot/config.json`（缺文件 everEnabled=false）；workers 用 WorkerStore.readAll() 过滤 running（跨 key，elapsed=now-Date.parse(dispatchedAt)，非法 dispatchedAt 剔除）；gates 行扫描 `_autopilot/gates/*.md` frontmatter（id:/kind:/stage:/status:，仅 pending）
   - `renderMonitorLines(snapshot)`：英文标签 + glyph，110 列截断，固定段结构（serve/conductor/workers/gates 四段恒在，空态折叠成区头行）；serve down 含 `/mw restart` 指引（AC-007）
   - `startMonitor/stopMonitor/isMonitorActive`：模块级 interval 单例；开启立即渲染首帧（VC-001 ticks=0）；off 同步 clearInterval + setWidget(id, undefined)（VC-005）
2. `console.ts`：switch 加 `monitor` case（on/off/无参 toggle）+ `ctx.hasUI === false` 降级提示（VC-006）；deps 加 readMonitorState/monitorIntervalMs 注入缝；USAGE 文案补 monitor
3. 测试（`test/suite/autopilot-monitor.test.ts` 或并入现有两个文件，照 fakeConsolePi/fakeCmdCtx 模式）：VC-001（首帧即时 + serve 行）、VC-002（fake timers 推 2 tick conductor dead）、VC-003（2 running + 分钟数 ceil）、VC-004（pending→approved 归零）、VC-005（off 清除 + 无后续 tick）、VC-006（hasUI=false 降级）、VC-007（serve down 指引）、VC-008（3 tick 内容哈希不变）、VC-011（两个 fake pi 实例互不污染）
4. 验证命令：repo 根 `npx tsgo --noEmit` 零错；packages/coding-agent 下 `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts`（+ 相关既有文件回归）

## T-02 细化

1. L0 静态扫描（VC-009）：rg 证明 monitor.ts + console.ts 的 monitor 路径无写 API（writeFile/appendFileSync 等）、无 config 写入
2. CHANGELOG `[Unreleased]` Added 条目（coding-agent）
3. `python mw.py build --install`（部署全局 bundle + dist）
4. L2 双 widget 验证（VC-010）：优先 vitest harness 级（faux provider + ui 调用记录，断言两个 widget id 并存互不覆盖）；不可行则写手动验证步骤文档供用户实窗确认
5. 证据落盘 `.agenticdoc/autopilot-monitor/evidence/runs/t02-verification.md`（[VERIFY] 行逐条对照 evidence-requirement.md）

## 完成判据

- T-01：tsgo 零错 + vitest 全绿（含新增）+ 既有测试无回归
- T-02：L0/L2 证据落盘 + build --install 成功
- PM 收尾：npm run check 全绿 → quality-gate（对照 evidence-requirement.md 逐 VC）→ done 事务 → 提交（用户确认后）
