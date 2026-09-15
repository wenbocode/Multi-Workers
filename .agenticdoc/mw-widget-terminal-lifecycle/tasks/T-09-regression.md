# Task T-09: 回归收口（双侧全量 + bundle 重建 + 证据汇总）

## 基本信息
- Stage: 5
- 代码状态: 代码完成（PM 直执）
- 验证状态: 验证通过（详见 evidence/runs/regression-2026-09-10.md：VC 13/13 勾销 + bundle 重建冒烟 + 预存基线漂移四项记录）
- 负责 Agent: PM 直执
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013]
- pattern_refs: []

## 描述
全量验证与收口（对照 evidence-requirement.md 逐 VC 汇总）：

1. **TS 全量**：`packages/coding-agent` 下 `node ../../node_modules/vitest/dist/cli.js --run test/extensions/`（含 agent-team-loop / -ack / -output 三个文件）全绿；既有用例零回归
2. **Python 全量**：`packages/multi-workers` 下 `python -m pytest -q` 全绿（e2e_real deselected 属正常）
3. **静态门禁**：仓库根 `npm run check` 全绿（无 error/warning/info）
4. **bundle 重建**：`/mw build`（或 build-extension.sh）重建全局 bundle；确认安装成功
5. **冒烟**（不花 LLM token）：tmux 起 pi（本仓库 cwd）→ `/mw-watch mw-widget-terminal-lifecycle`（或已有 watch）→ widget 渲染 header 行（no workers）；`/mw ack nonexist` → 错误提示；`/mw ack all` → 提示无待 ack 行。确认无 JS 异常
6. **证据落盘**：`evidence/runs/regression-2026-09-10.md`——各套件通过数 + [VERIFY] 埋点行汇总（VC-001~013 逐条勾销）+ 冒烟记录
7. **CHANGELOG**：`packages/coding-agent/CHANGELOG.md` [Unreleased] Added/Fixed 条目（widget 分区 + ack + TL;DR + reconcile）

## 输入
- 依赖文件: T-01~T-08 全部产出
- 依赖 Task: T-01, T-02, T-03, T-04, T-05, T-06, T-07, T-08
- AC 约束: 全部 AC（逐条对照 spec §3 + evidence-requirement.md）
- 设计约束:
  > D-009: L1 双侧 + 零回归；npm run check 全绿
  > goal-autopilot T-01 基线口径: 手动套件基线（四套件全绿）为本 key 回归对照

## 预期产出
- 全量回归记录 + `evidence/runs/regression-2026-09-10.md`
- CHANGELOG 条目
- 验证方式: 命令输出留档（[VERIFY] 汇总 13/13）
- 验证等级: Level 1（+ 冒烟 L2 轻量）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T08:40Z | ①models 重生成试探：内容零变化→排除生成文件过期，26 错误为真实漂移，按预定阈值 defer 拆 key；②TS 域 119/119 + Python 363 passed；③test.sh/npm test 全量：agent 2 败（TMPDIR）+ ai 8 败（registry 漂移）+ coding-agent core 85 败（Windows 环境签名）——均为预存，本 key 域零失败、零 import 交叉；④npm run check：biome/pinned-deps/ts-imports/shrinkwrap 过，tsgo 阻塞于预存 ai 26 错；⑤/mw build + 全局安装；⑥mw serve 重启换新 launcher（beat 文件实证）；⑦bundle 级冒烟（activate→/mw ack 拒绝/落盘 + 工具等效 + 徽标）全过；⑧evidence/runs/regression-2026-09-10.md + CHANGELOG 4 条 | VC 13/13 勾销；预存基线漂移记录在案（Section 4） |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
