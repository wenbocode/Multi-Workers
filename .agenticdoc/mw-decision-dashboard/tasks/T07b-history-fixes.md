# T07b 历史输出与根边界修复

type: coding
status: code-complete-review-pending
code_status: 代码完成
verification_status: 237验收/39重复/68邻接+1skip，复审待回读；实现前RED证据缺失（修后mutants不替代）

## 上下文
- goal `.agenticdoc/goal.md`；本key spec/design/evidence-requirement。
- `packages/multi-workers/decision_history.py:259` as_dict；:1226 signoff读取；:1539 key收集（函数定位）；`workers/dd-review-history/report.md`完整读，2P1/5P2。
- 原T07 report/verify-summary及全量被改代码/测试；T05唯一points/book写者，T10唯一monitor写者，禁止越面。

## 要求
systematic-debugging+TDD：逐finding先在当前缺陷实现实际RED再GREEN，不以skeleton报错充当安全RED。
P1-1：load_history显式注入复用已知secret集合redactor，旧archive/signoff/gate所有输出（列表/详情/stage.detail/claims/warnings及原行快照）自由文本统一脱敏→裁剪→安全边界处理，有诚实redacted/truncated/omitted标记；缺redactor不可证自由文本fail-closed omit。不是HTML转义，不修改历史磁盘，不只修answer漏note/claim/question等。结构性标识符保留join但必须验证，不盲把整个dict所有键当可信schema。注入API给T10明确清单；凭证集合读取用现有credential_redactor不要另造环境启发式或静默读取任意文件。
P1-2：记录key不能直接拼路径，严格内部闭集/形态校验、非法warn+计数skip；signoff路径realpath包含control预检，在任何read前拒外根symlink/junction，relative_to失败不崩。检查gate与test root所有读取同类边界。真实traversal fixture有外文件、真实symlink fixture，拒绝读取spy/外内容0，零mkdir副作用。
P2-1：available=false无answer不能engine echo冒称模型回答，unknown+basis；保留确有模型答案但escalated的来源事实，修固化错误的测试先记录RED。
P2-2：record usage不可最后attempt静默覆盖冒充总数。保留逐call/attempt真实usage，顶层明确语义/basis（如last-attempt）或可证明来源的聚合，测试多attempt不同值/缺键不補0，不估算。
P2-3：重复settled统一最后事件，status与stage一致。
P2-4：gate-only/无key gate不静默隐身：可只读独立gate记录及计数/归属unknown，符合全历史目标，不猜key；至少stats/warnings明确跳过与原因，不假报页面全覆盖。
P2-5：auto-decide/auto-llm signoff、refresh、(dp,key) authority多decision挂接均补测试，来源declared/basis且不把授权当人答。
隔离验证补齐已存在wire/lifecycle/签收/gate fixture前后hash，而不是只有4生产jsonl且缺目标文件。仅tmp，禁止写真实生产。报告纠正“写端负责脱敏”事实错误，不覆写原报告。

## 写入允许面
- `packages/multi-workers/decision_history.py`
- `packages/multi-workers/test_decision_history.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-history-fixes/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T07b-*`

## 写入禁止面
- 其他所有源/测试/其他worker报告/任务相位/真实生产记录/凭证配置/锁file/dist/TS。

## 验收命令
cwd packages/multi-workers `python -m pytest test_decision_history.py test_decide_archive.py test_decide_signoff.py test_decision_wire_store.py -q`，完整stdout/stderr/exit；root npm run check存在formatter越面风险时保持只读子步并明确非整跑。禁build/npm test/全vitest/commit/外网/真实模型/共享服务。

## 改动历史
- PM吸收T07 review CHANGES_REQUIRED，原写者已终态，本卡唯一history写者，T10并行仅服务基础且不暴露未审正文。

## 交付格式
report≤180行，逐finding确认/修复/测试来源、RED/GREEN全输出与隔离hash证据、T10下游API/安全预条件、未验证平台与全AC边界；不自报review PASS。
