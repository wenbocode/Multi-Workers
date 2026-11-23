# mw-key-spec-goal 交付记录

## 系统行为变化

- 完整 SDD 从 `spec.md` 的 §0 中读取 `spec_goal` 小节。Codex-lite 从 `codex_doc.md` 读取「目标」段。PM 随 spec 定稿，replan 沿用原文。
- MW PM 以当前窗口的有效认领取值，Worker 以任务运行的所属 key 取值。宿主把该段追加到原有角色指令之后。旧 key 缺少目标段时继续原有流程。
- 目标随每轮工作请求组装。压缩和恢复沿用相同的 key 绑定，切换或释放认领后从新绑定组装。Worker 卡片继续约束写入。

## 验收证据

- AC-001 覆盖完整 SDD、Codex-lite、旧 key，以及归档重建规格后目标不变。
- AC-002 捕获 PM 和 Worker 请求，覆盖工具续跑、压缩、PM 恢复与切换、释放认领、Worker 接续和卡片外写入拒绝。
- AC-003 比较同一 key 的实际捕获请求，验证计划、进度和压缩变化后的 system prompt 字节一致。

上述为 Codex PM 自验。三条 AC 与相邻用例共 31 项通过，另有两项既有 PM 常驻规则测试通过。 [AC 记录](evidence/codex-pm/self/1795450266406064500-jbdbv8qx/result.json) [测试输出](evidence/codex-pm/self/1795450266406064500-jbdbv8qx/command.log)

根目录的 Biome 扫描遇到历史证据和发布副本中的嵌套配置。完整 `npm run check` 在隔离源码副本通过，四个变更的 TypeScript 文件与工作树哈希一致。 [完整输出](evidence/npm-check.txt)

## 遗留

真实 provider 缓存读写在本次本地测试中不可观测。工作树交付后的全局发布与实窗观察由 `mw-dp-window-acceptance` 接续。
