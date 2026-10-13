# quality-gate-report-20261012.md — mw-dispatch-card-gate

两轮独立对抗式质量门禁 + cutover 后运行期复查的裁定记录。

## 轮次一：T-11b（对抗式 QG，FAIL）

- 执行：`mwd-t11b-adversarial-qg`（type review / `timi/glm-5.3` / 只读 / 101 calls / 31 分钟）
- **裁定：FAIL**，含 2 项 P1 一票否决：
  - **F-01（P1）AC-006 篡改⇒红未实现**：`card_sha256` 无任何读取者，`card_audit.py` 只算当前 digest；测试固化了弱化口径 ⇒ 篡改不会被判红。
  - **F-02（P1）extras 判据对象错位**：G-1 只校验 `readEnvelope`；`typeExtrasMissing` 未被 G-1 调用；G-3 查派生 `task.md` 而 `extractCardSections` 丢弃 extras 段；工具参数描述与实际承诺不符。
- 其余：F-03（边界可伪造：`created` 死码、批写 `dispatched_at` 不可信）、F-04（bash 通道盲）、F-05（种子/extras 无判据）、F-06（`unlisted_dispatches` 三类合流、`--strict` 永久失效）、F-07…F-12（parity 夹具、卡 `type:` 不校验、锚点漂移、PM 手写派发过不了本 key 门、五段契约一行散文可满足、coding 无 `report.md` 全豁免）。
- **PM 独立复核确认 F-01 与 F-09**（`card_audit.py` 中 `card_sha256` 命中 0；`writeDispatchTaskMd`/`_poll_once`/`_spawn` 行号漂移）。
- 无问题项：TS↔Python 常量 token 相等、逃生舱真读、AC-005 修订一致、G-1 零副作用、AC-008 隔离成立。

## 轮次二：T-17（对抗式 QG，PASS）

- 执行：`mwd-t17-final-qg`（type review / `timi/glm-5.3` / 84 calls）
- **裁定：PASS，无一票否决**，12 项 P3 残留（见 `achieved.md` 遗留 §1）。
- F-01 **真关闭**：`card_audit.py` 真读 `card_sha256:` 并比对、**默认红**、有真实 CLI 用例；第一轮的弱化断言已替换（残留 R-01/R-02）。
- F-02 **两入口同判据成立**（残留 R-03 为过拦方向）。
- AC-009（生产者不瘫痪）：伪造高版本号只降级为 plain missing（仍拒）；逃生舱默认关、fail-closed；残留 R-06。
- AC-010（自注入不得触发自身守卫）：最小补偿 R-11。
- **无假达标**：无断言弱化/skip/语料缩小/恒真；金样本重钉带 diff；T-14 用例驱动真实 `_poll_once`。
- **R-07（本 key 自伤暴露）**：当日 18 条手写派发全部落进 `unlisted_after_boundary`（门按设计工作）⇒ 触发 F-10 的修法（PM 一律带卡派发）。

## cutover 与运行期增补（T-08 / T-20~T-26）

- **cutover #1**（T-08）：`mw build --install --allow-dirty`，bundle `A5B0FC9C…4932` → `975D4066…978D`（T-18~T-22 进 bundle）；一正一负运行期证据（带卡渲染件真落盘三行 + 三段 canon + extras；`producer-skew` 与 `envelope missing` 两负例 `spawned=[]`）。
- **cutover 后运行期执法**：PM 一张缺 `改动历史`/种子的卡被 `dispatch refused`（零副作用）⇒ G1/G2/seed 最小项在生产路径生效。
- **AC-011 修复路径生产触发**：通知 `2 orphaned key(s) … claim-free repair dispatch applied` ⇒ 同时证实机制活着并暴露 **C-30**（误触发）。
- **cutover #2**（T-25 后）：bundle → `5877E4FD3F035BDB…FAC669`，`0.83.0` 命中数 0 → 1，构建输出 `built + self-check OK (activate) version=0.83.0`。
- **T-23 运行期复验**：`card_audit` 本卡 `[ok]`、未跌 `unlisted_after`；T-21 正例 `extra=[]`、反例 `extra=[packages/multi-workers/launcher.py]`（**未放松**）；dotless 确认漏红（后由 T-25 修）。
- **T-26/26b 收口验证**（用户两次 `/mw restart` + `/reload` 之后）：
  - **C-31 运行期闭环**：本卡 `task.md` = `envelope_producer: agent-team-loop-pm@0.83.0`（与 `package.json` 一致）；同源校验 global = repo = `5877E4FD…FAC669`。
  - 全量 pytest `2 failed / 1744 passed`（失败恰为两条既有基线）；`npm run check` exit 0（`Checked 1136 files … No fixes applied`，check 前后 `git status` 零差异）。
  - 真实越界仍红复核通过（`launcher.py` 无事件 ⇒ 判 extra；`scripts/deploy` 有/无事件分别不判/判）。
  - 唯一红：**C-33**（T-23 测试写死 cutover #1 bundle sha 的历史期望）—— 判定为**测试脆性，非功能回归**。
  - 半成品派发被服务层**指名拒绝**（`envelope missing: 验收命令 … not provably older than baseline`）且**发生在 spawn 之前**（零 token 消耗）—— fail-closed 语义正确，但其成因 **C-32** 已登记。

## PM 裁定汇总（本 key 内）

1. AC-005 子项 `[REVISED @ 2026-10-12]`：`review` 保持**只读（无 bash）**，不为调度选择放宽既定契约。
2. 金样本变更必须**带 diff 显式重钉**；豁免按**时间边界**而非"有无信号"。
3. T-12 越界最小夹具修正**接受**（属 PM 卡面漏项）；41 条 TS 新红为**真实欠判** ⇒ 另立 T-15 只改夹具。
4. AC-010 在本 key 内修（自注入 marker 触发自身守卫）。
5. C-27 **不硬啃**（前 key 文档口径问题），交专项 key。
6. T-19 请求裁定①：接受"ORPHANED 需已登记"⇒ 后因用户质询**修正为"index 行 ∨ owner 痕迹"**（T-22），再因 C-30 收窄时效（T-24）；请求裁定②：接受（登记为残留）。
7. T-20 请求裁定：接受既有"stage 缺 `### Keys` = available-but-invalid"语义（不改冻结断言）；`parse_roadmap` 默认 strict 保 back-compat；未跑 `npm run check` 由 PM 在收口统一跑。
8. T-22 请求裁定：接受 notice 的模式化路径形态，不为它放宽 T-19 的形态断言。
9. T-24 请求裁定：接受其**最小偏差**实现（req.1b 无条件；req.2/3 时效门禁限定于发布状态文档的 key）——保住 AC-011 的正当核心（无产物、无 owner 的未跑任务仍可修），同时钉死 C-30。
10. 26 条 `unlisted_after_boundary`：**历史证据保留，不改判据、不回填**。
11. C-33：登记为测试脆性，不在本 key 内派卡。
