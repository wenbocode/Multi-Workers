# T-06 文档收口

状态: done（2026-09-25 18:05，PM 直执） · 执行者: PM · 覆盖: VC-012

CHANGELOG [Unreleased] Fixed 末尾追加 mw-l3-fail-marker-forms 条目（Fixed 节现 10 条，结构验证过：Added 16 / Changed 4 / Fixed 10，既有条目头完好）：三规则+token 局部零值豁免判据、全源全文件扫描面、fail_line 四消费面、语料实测（121 行/80 管道保留/25 漏检/sampling a1 事故链）、期望翻转表（vs HEAD 四轮 below 保持仅归因变；vs 事故记录仅 sampling a1 meets->below；meets 轮 0 误翻 + 朴素放宽对照 6/10、10/10）、兼容面（_L3_FAIL_RE 名宇/region-SHA/4-3-10 不变/事件 17/provenance 组合仅 tuple 断言 3->4）、重启生效、测试清单（L1 30 + L2 5 + fallback 就地 + e2e 链）；closure-reprompt 预算交互登记为观察项。
_pitfalls.md 追加 P-014（判据与表达措辞差：单字形判定器 + 语料双面穷举纪律 + token 局部豁免 + 提示词措辞同步）。
