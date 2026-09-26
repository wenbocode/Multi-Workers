# T-01 L1 真值表新文件

状态: done（2026-09-25 17:00，fmr-t01 worker：30 测试落盘，py_compile + collect 干净，HEAD 红 28/30 符合 TDD，参考实现自证 30/30） · 执行者: Worker A（fmr-t01-l1-truth-table） · 覆盖: VC-001/002/003/004 · 依赖: 契约 = design D-001（B 落地前红）

新文件 `packages/multi-workers/test_autopilot_fail_marker_forms.py`：

- 从 `conductor` import `_L3_FAIL_RE`、`_L3_FAIL_BULLET_RE`、`_L3_FAIL_PROSE_RE`、`_L3_FAIL_ZERO_RE` 及行级 helper `_l3_fail_marker_line(text) -> str | None`（返回首个命中行原文，无命中 None）。
- 正锚 5（verbatim + 出处注释）：
  1. `| VC-001 | FAIL | yes | ... |`（mvp a1 report.md:26，S1 朴素管道）
  2. `| VC-006 | **FAIL** | no | ... |`（marker a3 output.md:22，S2 加粗管道）
  3. `| 总裁决 | **FAIL / below** |`（gui-time a2 report.md:17，S3 斜杠管道）
  4. `- **FAIL：9**`（sampling a1 output.md:12，S4 项目符非零）
  5. `FAIL — 21/30 VC 通过，9 项失败`（sampling a1 output.md:3，S6 行首散文）
- 构造变体 2（标注「构造，无语料出处」）：裸 `**FAIL**`（bullet 规则覆盖，fail-closed）；`- FAIL 9 项，其中 FAIL：0`（零值豁免 token 锚定：首 token 触发——实现须 `ZERO_RE.match(line, fail_pos)` 而非整行 search）。
- 负锚 11（verbatim + 出处）：
  1. `PASS（有非阻断遗留）——35/35 条 VC 均有 PASS 证据，FAIL=0，needs-rerun=0。`（cigate a1 output.md:3）
  2. `**汇总**：PASS 35，FAIL 0，needs-rerun 0。质量门禁结论为 **PASS（有非阻断证据维护遗留）**。`（cigate a1 report.md:50）
  3. `**汇总**：**PASS 35 / FAIL 0 / needs-rerun 0**。`（cigate a2 output.md:84）
  4. `- VC：**32 PASS / 0 FAIL**（按冻结的 VC 与已记录 EXECUTE 证据）。`（tier-a a1 report.md:44）
  5. `- FAIL：0`（tier-a a2 report.md:53）
  6. `- 质量门禁：38 PASS、0 FAIL、0 needs-rerun。`（mvp a2 output.md:10）
  7. `> 总结：**PASS 24 / FAIL 0 / needs-rerun 0**。`（params a3 output.md:12）
  8. `**门禁总判定：PASS（19 PASS / 0 FAIL / 1 needs-rerun）。**`（freshness report.md:31）
  9. 含 `fail_items=[]` 的指标行（cigate a1 output.md:12）
  10. `3005 passed / 9 failed` 套件计数行（cigate a2 output.md:42）
  11. `9 failed` 套件计数行（gui-time a2 report.md:74）
  另：`FAILED`（fallback 测试 :592 样本）三规则均不命中；`逐条 VC PASS/FAIL`（tier-a a1 output.md:12）不命中。
- 行内否定锚：`| VC-034 | **FAIL** | yes | ... featuremark 0 fail ... |`（marker a3 report.md:44）→ 命中（豁免 token 局部，禁整行丢弃）。
- 断言口径：正锚 → `_l3_fail_marker_line` 返回非 None 且含该行；负锚 → None。
- 禁止：触碰 conductor.py 或任何既有测试文件。B 落地前本文件红（import 失败或断言红）属预期；验收 = B 落地后全绿 + 对 HEAD 可证非空洞。
