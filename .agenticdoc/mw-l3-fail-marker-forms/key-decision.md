# Key Decisions: mw-l3-fail-marker-forms

| # | 决策 | 一句话理由 | 证据 |
|---|---|---|---|
| D-001 | 三规则（管道保留名宇 `_L3_FAIL_RE` / bullet / 行首散文）+ token 锚定零值豁免（`ZERO_RE.match(line, fail_pos)`），仅大写 FAIL，行级扫描；裸 `**FAIL**` 由 bullet 规则覆盖 | 语料翻转矩阵：朴素 `\bFAIL\b` 误翻 6/10、`(?i)` 10/10；三规则+值豁免 0/10（评审复演确认） | R2neg §5、R2pos §3、评审 replay 表 |
| D-004b | `_l3_prompt:1123` 措辞更新（三形态口径）+ `_repair_prompt` 删「## Quality Gate Report 的」限定语 | 评审 MINOR-3b：措辞在 reviewer 提示词；fail_line 可来自 QG 节外/非合规源 | R1 §4.2、评审 MINOR-3 |
| D-002 | 扫描面 QG 切片 → 全文件 | TL;DR/Summary 结论行结构性不可见（G2）；全文件下管道命中零漂移（R2pos 附录 A）；与 `_md_section` 解耦 | R1 §2、R2pos G2 |
| D-003 | FAIL 否决扩到全部可读源（含非合规源） | 现行只扫 qualifying 源 = 洗白洞（output.md 带 FAIL 缺节 + 干净 report.md ⇒ meets）；no-whitewash 本意是任一源 | R1 §1.2 洞、R2pos R2-8 |
| D-004 | resolver 2→3 元组、round_verdict 3→4 元组穿 fail_line，四消费面 | R1 §4.2 已枚举穿线路径与 8+3 测试点；不新增事件类型（EVENT_TYPES=17 锁） | R1 §4、§5.5 |
| D-005 | 测试矩阵全部语料锚点驱动（禁凭空构造） | spec §5 规矩；AC-002 用例逐条 file:line | R2pos §6、R2neg §6 |
| D-006 | 变更面收敛：conductor 判定区 + 测试三件 + 文档；冻结原语零触碰 | region-SHA 锁跨 2 文件 3 常量，无必要不解锁 | R1 §5.2 |
| D-007 | S7/S8/斜杠散文行级残留如实登记（轮级由共存管道覆盖） | `FAIL\s*[（(/]` 扩展被 `0 FAIL / 1 needs-rerun`（freshness a1）否决；语料实证 5 轮全有共存管道 | R2pos §1、R2neg §1.2 |

裁定者: PM（2026-09-25）；偏离处理: 实现期任何偏离需回写本表 + 对应 D 条目。
