# T-12 — 收口：A/B/C 对照脚本 + 全量回归 + 共享测试重锚 + 质量门材料

- key: `mw-dispatch-settle-gates`｜AC: **AC-009**（+ 全 VC 复核）｜VC: **VC-040…VC-042** + 全量跨卡复核｜波次 **4**｜**独占串行**
- 角色: coding
- **唯一允许改的路径**：① 新建 `.agenticdoc/mw-dispatch-settle-gates/evidence/scripts/mwds-controls.ps1`（A/B/C 组）；② `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（仅重锚受影响的既有断言）；③ 新建 `packages/coding-agent/test/suite/mwds-t12-regression.test.ts`（跨卡 seam 用例）；④ `packages/multi-workers/test_*.py` 中因 T-07…T-10 语义变化需重锚的断言；⑤ 写 `evidence/runs/t12-consolidation.md`；⑥ 自身目录 `report.md`
- 上游：`plan.md §7`；全部 T-01…T-11 的报告（先读它们的 `[VERIFY]` 行）

## 必须做
1. **对照脚本 A/B/C 组**：把各卡报告里的对照汇总成一份可重复执行的脚本（每组：摘除判据 / 反转默认 / 移除白名单或护栏 ⇒ 具名用例必须红；再还原 ⇒ 必须绿），并把**真实执行输出**粘进报告。**只写脚本不落红 = 未验证**。
2. **跨卡 seam 用例（本卡新增）**：
   - `write_scope` 头（T-02 写）被 T-03 消费（含缺省/空值形态）；
   - `deliverable-evidence` 通道口径（T-04）与 T-07（Python reap）**判定结果一致**（同 fixture 双端跑，结论必须相同）；
   - `output-sections`（T-05）与 T-06 的段生成互不破坏（同 fixture 双跑）；
   - AC-001 的 `blocked_on_human`（T-08）与面板同源量（`monitor.ts` 口径）在同 fixture 下一致；
   - T-09 的 stage 终态与 `mw doctor` 的 gates 段互不干扰。
3. **全量回归（贴完整输出，不截断）**：
   - TS：受影响套件全跑（`test/suite/*` 相关文件 + `test/extensions/agent-team-loop.test.ts`）；
   - Python：`python -X utf8 -m pytest packages/multi-workers -q`（与基线对比：上一 key 记录 **2 failed / 655 passed**；本卡要求 **新红 = 0**，两条既有红逐条点名）；
   - `npm run check`（**本卡唯一允许跑者**；biome 会改写文件 ⇒ 跑完再跑一遍受影响测试确认仍绿，并贴 `git status` 说明被改写的文件）。
4. **共享测试重锚**：`agent-team-loop.test.ts` 中受影响的既有断言"更新而非放松"（逐条在报告列出旧断言 → 新断言 → 理由）。
5. **质量门材料**：写 `evidence/runs/t12-consolidation.md`，含各 AC 的 PASS/PARTIAL 初判 + 机器判据 + 残留；**不得**自行写 `achieved.md`（PM 负责）。
6. 发现任何卡未达判据 ⇒ **如实登记为 PARTIAL**（不得替实现者掩饰），并在报告中给出最小复现命令。

## 反向用例（本卡自身的对照）
- (a) 对照脚本整体运行 ⇒ 每个 A/B/C 组至少一条具名用例转红（贴输出）；
- (b) seam 用例组：任一端被改回旧实现 ⇒ 对应 seam 用例转红（至少演示 2 组）；
- (c) 回归对比脚本：断言"新红 = 0"（把基线两条红与本次输出逐条对应）。

## 证据
```
[VERIFY] VC-040: verify_lines_anchored=<N>/<N> unanchored=0
[VERIFY] VC-041: reanchored_refs=<N> drift_registered=<N>
[VERIFY] VC-042: control_groups=A/B/C per_group_red>=1
[VERIFY] regression: ts=<passed> py=<failed/passed> new_reds=0 npm_check_rc=0
```

## 禁止
不改 `packages/*/src/**`（实现卡所有；如发现必须改 ⇒ **停止并报告**，不得自行修实现）；不 build / `mw build --install`；不 commit；不重启进程；不写 `achieved.md` / `quality-gate-report-*.md`（PM 所有）。
