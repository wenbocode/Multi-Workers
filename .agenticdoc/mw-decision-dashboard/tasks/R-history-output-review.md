# R T07c 输出安全窄复审

type: review

## 上下文
- goal `.agenticdoc/goal.md`；spec AC-005/016/design §9。
- `packages/multi-workers/decision_history.py:1` _scrub_output/_with_output_policy/as_dict/page；test_decision_history全文；workers/dd-history-output-safety/report.md、evidence/runs/T07c-structural-output-safety/verify-summary.md及baseline/red-02/import proof/green/probe日志。

## 审计目标
结构known-secret输出豁免是否真正闭合，所有字符串/映射键/calls副本/basis/flags/warnings/路径标签无carrier原值，内部join/opaque/filter不变；缺回调契约明确。省略capture.text后hash/stored_len/encoding/byte_exact/capture_status是否诚实（不能text=None仍声称ok完整）；mark字段/占位符本身与secret重合是否泄漏/递归不稳定；所有public序列化面，不只record.as_dict。
page.filters原样回显当前known-secret输入：报告声明例外但不能当全page原值0，判断与AC-005/API契约，给具体最小修复，不把monitor二层当免责。原属性内部保留可接受但消费者只能用安全序列化面，T10合同明确。
155=149+6，45=39+6，基线未修副本+最终测试哈希/import proof真RED核对，不以mutant替代；65→0 probe覆盖何面、真实38dummy未命中不当真实secret证明。ledger两个目录已卡允许，PM已吸收ack。

## 要求
PASS/CHANGES_REQUIRED，新增P0/P1/P2精确path:line/触发/AC/最小修复；只读自身report，不源/测试/凭证/真实记录修改。无shell说明静态旧日志不是本人实测。

## 未覆盖面声明
T10b在产、真实UI/HTTP/平台/Jev/全仓check未验；未知secret非known集合保持设计边界，不泛扩大。

## 写入允许面
- `.agenticdoc/mw-decision-dashboard/workers/dd-review-history-output/**`

## 写入禁止面
- 所有源/测试/任务相位/生产/其他worker。

## 交付格式
report≤130行，结论/关闭表/新finding/证据/残留与未覆盖，摘要≤25行。
