# R T05b 安全门修复独立复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-004/005/010/011/012/017/design typed单一权威。
- `packages/multi-workers/decision_points.py:1` step5b/state_unknown_key_issues/LEGACY_PRODUCER_STATE_PATHS/BOOK_VALIDATOR/_join_digest/_emit。
- `packages/multi-workers/decision_book.py:1` observation_book_issues/模块尾注册；test_decision_observation全文。
- workers/dd-review-observation/report.md原F1..F7；workers/dd-observation-fixes-retry/report.md全文与corrections-F3-F7.md、evidence/runs/T05b-retry-observation-fixes/基线/RED/GREEN/diff。原OOM仅测试改动保留，本次RED98/31与验收415在档。

## 审计目标
原F1 typed/enum/未知键/数组跨字段预算前零发送、生产与观察同门；重点dp25三legacy字段仅路径放行是否绕typed、book不接受同生产state是否违反25DP单权威，PM不接受兼容白名单为最终契约。指出需要registry声明的真实类型/源证据最小迁移面，不改源不自造值。
F2 book钩子模块导入顺序（仅import points vs import book）/validator缺失 fail-closed、全局可改注册/替换/并发风险；合法book冷启动能否工作、不依赖pytest偶然导入顺序。check_book秘密/证据实际门与state三身份归一化join是否掩盖错误DP/version/实际发送差异，root一致。拒绝材料不落秘密快照/detail/decision-end error。
F4仅written后引用，False/异常仍decision-end与capture状态事实，是否真实snapshot join（并发/孤立ref）。F5actor闭集与id秘密输出、human声明不能证明人工。对新增99测试哪些真正RED、31本已合法，以及旧fixture改动是否正确不降断言。
415绿是否靠生产者豁免追绿，缺contract ad-hoc DP生产不可达事实。F3/F7更正完整，collected-tests.txt在真实目录是否存在（ledger误解析不自动越面），未整check/两归因待核实不抹掉。

## 要求
完整必要源/test分页读取，PASS/CHANGES_REQUIRED，逐F关闭表/新增P0/P1/P2精确path:line/触发/最小修复、dp25迁移建议、给T06开工结论。仅自身report，无源/测试/生产/服务/凭证/外网/build命令。静态旧日志不是本人实测。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-observation-fixes/**`

## 写入禁止面
- 所有源/测试/任务相位/旧报告证据/真实生产。

## 未覆盖面声明
真实Jev/HTTP/TS消费者/T06UI/全仓check未验，合法状态25DP过helper不等全链发送已验。

## 交付格式
report≤150行，关闭表/新finding/证据偏差/迁移面/未覆盖，摘要≤25行。
