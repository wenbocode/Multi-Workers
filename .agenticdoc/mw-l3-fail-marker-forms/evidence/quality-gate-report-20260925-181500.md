# Quality Gate Report: mw-l3-fail-marker-forms

- generated_by: autopilot PM (verify 阶段)
- generated_at: 2026-09-25T18:15:00Z
- ac_fingerprint: `435c9b5d12ff`（门禁口径：sorted-unique AC-ID 集 sha1 前 12 位，带尾换行实测一致）
- 基线: `d20a270d5`（spec/design 锚点）→ 实现落盘于 `76d5d612e` 之后的工作树（provenance-guard 先落地，本 key 复合不改其语义）

## VC 断言表

| AC | verdict | 证据 |
|----|---------|------|
| AC-001 三形态检测 | PASS | `test_autopilot_fail_marker_forms.py` 30/30 绿（含 S1/S2/S3 管道三变体 + S4 bullet + S6 行首散文五个语料锚点 verbatim 回放 + 全文件扫描面）；`test_fmr_bullet_fail_only_source_below`（决定源仅 bullet、无 report.md，轮级 below） |
| AC-002 零值豁免与误翻面 | PASS | L1 负锚点 11 条 + `FAILED` + `PASS/FAIL` 元话语全不触发；构造双 token 行 `- FAIL 9 项，其中 FAIL：0` 首 token 触发（token 锚定断言）；行内否定 `| VC-034 | **FAIL** | yes | … 0 fail … |` 触发（L1 + `test_fmr_inline_negation_still_fires`）；`test_fmr_meets_preserved_with_zero_fail_texts` meets 保持 |
| AC-003 回归零新增 | PASS | run-suite-20260925.txt：2 failed / 978 passed / 10 deselected（对账 927 基线 + 16 provenance + 30 L1 + 5 L2 = 978，2 失败 = 已知外域先在，与基线一致）；e2e_l2 8/8（run-e2e-l2-20260925.txt；kill_respawn 首跑 Windows 文件锁瞬态，隔离复跑绿 run-kill-respawn-rerun-20260925.txt）；fallback 15/15 自审计锁保持 |
| AC-004 判定组合语义（[REVISED] 洗白洞闭合） | PASS | `test_fmr_nonqualifying_output_fail_vetoes_clean_report`（非合规 output 带 FAIL bullet + 干净合规 report → below，且 l3-report.md 持非合规源字节）；fallback 就地扩展用例绿；`EVENT_TYPES == 17` 无新事件（timeline 16/16 绿） |
| AC-005 fail_line 四消费面 | PASS | `test_fmr_fail_line_threading`：stall reason `fail:` 片段 / timeline `l3-verdict … (report from …; fail: …)` / provenance sidecar `fail_line` verbatim / repair task.md 含样本行；e2e 链断言 repair prompt 注入 |
| AC-006 e2e 链 | PASS | `test_l3_fail_marker_repair_chain`（13.2s）：round-1 `- **FAIL：1**` bullet → below（无 false-meets，phase 断言非 DONE）→ repair 派发含 fail_line → round-2 合规 → meets → DONE（`verify->done exit=0`）；provenance 两轮 fail_line 有/无断言 |
| AC-007 文档 | PASS | CHANGELOG [Unreleased] Fixed 追加条目（Fixed 节 10 条，结构验证：Added 16 / Changed 4 / Fixed 10，含判据表/翻转表/语料锚点/重启生效）；`_pitfalls.md` P-014 |

## 反向红线核查

1. meets 轮误翻：无——L2 ④ + L1 全部负锚点 + fallback false-meets 探针（全文件口径重推导）绿；语料 10 meets 轮期望翻转表 0 误翻（CHANGELOG 记录）。
2. 冻结原语 region-SHA：绿——`_parse_l3_output`/`_md_section` 字节不变（fallback VC-007 + provenance VC-013 双锁断言过）。
3. timeline 事件类型集：绿——17 类无新增（仅复用 `config` detail 扩展）。
4. G3：绿——场景①断言 `report.md` 前后均不存在，below 由 output.md 独立触发。

## 运行证据

- evidence/runs/run-suite-20260925.txt（默认套件 978+2）
- evidence/runs/run-e2e-l2-20260925.txt（8/8 终稿）+ run-e2e-l2-attempt1-20260925.txt（修复前诊断轮）+ run-kill-respawn-rerun-20260925.txt（瞬态复跑）
- evidence/runs/run-e2e-diag-20260925.txt（closure-reprompt/L3-轮预算共享计数交互登记，观察项非缺陷）
- evidence/research/（RQ-1/2/3 + spec 笔记）；workers/fmr-review-spec-design/report.md（设计评审 9/9 吸收）

## 残留（如实登记）

- S7/S8 行级形态（`FAIL（…）`、`FAIL / below`、汇总行内 FAIL）不触发三规则——轮级由共存管道覆盖（语料实证 5 轮全有），行级 miss 已在 design §4 与 CHANGELOG 登记；`FAIL\s*[（(/]` 扩展被 freshness a1 负锚点否决。
- closure-reprompt 预算与 L3 轮预算共享计数：FAIL 轮+修复轮耗尽 l3_limit 后，post-repair 朴素 meets 被 done 门驳时零 reprompt 直接 stall（verdict 保持 meets，fail-closed 可恢复）——归属 closure/预算域，e2e 以合规稿绕开，登记待后续 key。
- 生效需重启：判定逻辑在 conductor 进程内 import 缓存，`mw serve` 重启后对新 L3 轮生效。
