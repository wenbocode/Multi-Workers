# Achieved: mw-l3-fail-marker-forms

## 系统行为变化

L3 FAIL 标记检测从单字形（管道单元格）扩为三形态（管道 / 项目符 / 行首散文结论行）+ token 局部零值豁免，扫描面从 QG 节切片扩为全部可读源的全文件，FAIL 否决扩到非合规源（洗白洞闭合：非合规 output.md 带 FAIL 不再被干净合规 report.md 洗白）；首个 FAIL 行全链穿线（resolver 2→3、round_verdict 3→4 元组；stall reason / l3-verdict timeline detail / provenance sidecar fail_line 字段 / repair prompt 注入四消费面）；`_l3_prompt` 措辞同步三形态口径、`_repair_prompt` 注入修复目标。影响面：conductor 判定区 +78/-33、测试四件（新 L1 文件 30 测试 / exec 5 场景 / fallback 就地更新自审计锁保持 / e2e 新链测试 8/8）、CHANGELOG + `_pitfalls.md` P-014。与 provenance-guard（76d5d612e）复合不改其语义（唯一触碰 = 其测试的元数断言 3→4）。语料实测：121 行中 80 管道命中全保留、25 条非管道正向行从漏检变检出、10 个 meets 轮零误翻；期望翻转表（vs 事故记录仅 sampling a1 meets→below）已写入 CHANGELOG 供 E2 `feature-false-meets-remediation` 引用。生效条件：conductor 进程重启后对新 L3 轮生效。

## 遗留

- S7/S8 行级形态（`FAIL（…）`/`FAIL / below`/汇总行内 FAIL）行级不触发，轮级由共存管道覆盖（语料 5 轮实证）；`FAIL\s*[（(/]` 扩展被负锚点否决——已登记 design §4 + CHANGELOG，接受不处理（轮级无漏）。
- closure-reprompt 预算与 L3 轮预算共享计数的交互：FAIL 轮+修复轮耗尽 l3_limit 后 post-repair 朴素 meets 被 done 门驳时零 reprompt 即 stall（fail-closed 可恢复）——归属 closure/预算域，登记于 e2e 诊断证据，待后续 key 评估。
- E2 `feature-false-meets-remediation`（被本 key 阻塞）可引用 CHANGELOG 判据表与翻转表启动；FM 侧 9 个卡死 key 的 `/mw restart` 自愈同样吃到本修复。
