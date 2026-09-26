# T-02 conductor 实现 + fallback 就地更新

状态: done（2026-09-25 17:30，fmr-t02：conductor +78/-33，焦点面 364 passed / 2 外域先在；region-SHA 复核零触碰；偏差1 = provenance 测试 tuple_len 3->4 断言连带更新（+2/-2，本 key 契约必然）；偏差2 = fail 样本统一 _one_line(s,80)） · 执行者: Worker B（fmr-t02-conductor-impl） · 覆盖: VC-001..007/009 · 依赖: provenance-guard 会话落地 + 漂移图；T-00

conductor.py（design D-001..D-006 全量）：

1. 常量：保留 `_L3_FAIL_RE` 名宇（pipe 规则不动）；新增：
   `_L3_FAIL_BULLET_RE = re.compile(r"^\s*[-*]\s*\**\s*FAIL\b")`
   `_L3_FAIL_PROSE_RE = re.compile(r"^[^|\n]*?\**\s*FAIL\s*[—–-]")`
   `_L3_FAIL_ZERO_RE = re.compile(r"FAIL\s*\**\s*[：:=]?\s*\**\s*0\b")`
   行级 helper `_l3_fail_marker_line(text) -> str | None`：逐行判定——pipe 或 prose 命中即返回该行；bullet 命中后以 `_L3_FAIL_ZERO_RE.match(line, fail_token_start)` 判零值豁免（match 锚定 FAIL token 起点，禁整行 search），非零返回该行。
2. `_l3_resolve_source`：FAIL 扫描输入改源文件全文（不再 `_md_section` 切片）；否决扩到全部可读源（含非合规源）；返回 `(verdict, source, fail_line)` 3 元组。
3. `_l3_round_verdict`：3 → 4 元组 `(verdict, status, source, fail_line)`。
4. `_verify_loop` 四消费面：mark_stalled reason 追加 `_one_line(fail_line)`；repair 派发传 fail_line。
5. `_persist_l3_verdict`：增可选 `reason` 参数（进 timeline detail `l3-verdict {before} -> {after} (report from {source}; fail: {sample})`；缺省行为逐字节不变）。
6. `_l3_prompt`（:1123 区）措辞：「任一份出现 FAIL 单元格即 below」改为三形态口径（任一份任意行出现 FAIL 标记——表格单元格 / 项目符 / 结论行——即 below）；`_repair_prompt` 注入 fail_line、删「## Quality Gate Report 的」限定语。
7. provenance sidecar `l3-verdict-provenance.json` 记录增 `fail_line` 字段（append-only 去重不变）。
8. 零触碰：`_parse_l3_output`、`_md_section`、`_l3_qualifies`、`_L3_SOURCE_ORDER`、`_l3_source_paths`、done transaction、closure repair 路径、timeline 事件集（EVENT_TYPES==17）。

fallback 测试就地更新（禁新增函数，`len(new_tests)==15` 自审计锁保持）：
- 8+3 元组解包/索引点机械更新；
- superset 探针（:568-612）改逐规则探针：`FAILED` 样本三规则均不命中，new_only 按新规则集重标；
- :483-489 旧口径探针用新 fail-scan 重写（保持其 `== 0` 断言语义）；
- `test_report_fail_not_whitewashed_by_output_pass` 就地扩展非合规源否决用例；
- 4/3/10 分类计数不变（夹具无 bullet/prose/零值文本——加注释钉口径）。

验收：焦点套件（fallback + freshness + closure + exec + stall + timeline）全绿；region-SHA 测试原样绿。
