# Plan: mw-l3-fail-marker-forms

基线: `d20a270d5`（design 评审已吸收 9/9 findings；R1 行锚点以此为准）· fingerprint `435c9b5d12ff`

## 并行度分析（按文件边界）

| 写面 | 归属 | 依赖 |
|---|---|---|
| `autopilot/conductor.py` + `test_autopilot_verdict_source_fallback.py`（就地） | Worker B 单写者 | design D-001..D-006 |
| `test_autopilot_fail_marker_forms.py`（新 L1） | Worker A | 契约 = design D-001 常量名/签名；TDD：B 落地前红 |
| `test_autopilot_conductor_exec.py`（L2 场景追加） | Worker C | 同上，B 落地前红 |
| `test_autopilot_e2e.py`（stub 分支） | PM | B 落地后（分支键 = repair prompt 内 fail_line，D-004 契约） |
| CHANGELOG / `_pitfalls.md` / 任务卡收口 | PM | T-05 全绿后 |

三 worker 同时派发（A/C 为 TDD 红测，B 为实现）；PM 串行收尾。无跨 worker 文件交叠。

## 任务表

| # | 任务 | 执行者 | 覆盖 | 验收 |
|---|---|---|---|---|
| T-00 | 基线锚点核验（HEAD 无漂移：`_L3_FAIL_RE:1148` / resolver:1180 / round_verdict:1196 / verify_loop:1481 / persist:619 / prompts:1113,1129；fallback 测试 :69/:421/:568） | PM | — | 锚点全部在位或更新漂移图 |
| T-01 | L1 真值表新文件 `test_autopilot_fail_marker_forms.py`：三规则 × 豁免逐行用例（正锚 5 + 构造 2 + 负锚 11 + `FAILED` + 双 token 陷阱），verbatim + 出处注释 | Worker A | VC-001/002/003/004 | B 落地后全绿；对 HEAD 红（可证非空洞） |
| T-02 | conductor 实现：`_L3_FAIL_{BULLET,PROSE,ZERO}_RE` 三常量 + 行级扫描 helper + `_l3_resolve_source` 全文件扫描/全源否决/3 元组 + `_l3_round_verdict` 4 元组 + `_verify_loop` 四消费面 + `_persist_l3_verdict` 可选 reason + `_l3_prompt:1123`/`_repair_prompt` 措辞；fallback 测试就地更新（8+3 解包点、superset 逐规则探针重写、洗白洞扩展用例就地并入既有函数） | Worker B | VC-001..007/009 | 焦点套件绿；`_parse_l3_output`/`_md_section` region-SHA 原样绿；`len(new_tests)==15` 锁保持 |
| T-03 | L2 场景（exec 文件追加 `test_fmr_` 前缀）：① sampling 型（决定源仅 bullet、无 report.md）② 洗白洞 ③ fail_line 四消费面 ④ meets 保持 ⑤ 行内否定 | Worker C | VC-004/005/006/007 | B 落地后全绿 |
| T-04 | e2e stub 分支（repair prompt 含 fail_line → stub 响应合规）+ full_chain 变体（round-1 bullet FAIL → below + repair 派发 → round-2 → DONE）+ `e2e_l2` 全跑 | PM | VC-011 | e2e_l2 全绿（含新用例） |
| T-05 | 全量回归：默认套件 vs 基线（927+2 外域先在）+ 证据落 `evidence/runs/` | PM | VC-008/010 | 零新增失败 |
| T-06 | CHANGELOG [Unreleased]（判据表 + 20 轮期望翻转表 + 锚点）+ `_pitfalls.md` 新条目 + 任务卡收口 | PM | VC-012 | 文档 diff 过目 |

## 风险登记

| 风险 | 缓解 |
|---|---|
| B 的就地更新碰 fallback 自审计锁 | 卡面钉死：不新增函数，`len(new_tests)==15` 保持；新函数只进 L1/exec 文件 |
| A/C 红测与 B 实现名宇漂移 | 契约 = design D-001 常量名 + `_l3_fail_marker_line` helper 签名，卡面逐字给出 |
| 全文件扫描暴露未知误伤 | T-05 全量回归 + 语料 0/10 实证前置；若新翻红即回 D-001 豁免表补条目（须语料出处） |
| e2e stub 分支键不稳（B 的 prompt 措辞） | T-04 在 B 落地后执行，分支键取 fail_line 内容本身 |
| 并行会话提交造成基线漂移 | T-00 核验；漂移则更新锚点再派发 |
