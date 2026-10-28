# T20 历史反馈：已实现接线修正，默认脱敏器接入待确认

## 已证实根因
1. 真实 writer→reader fixture 表明，无 redactor 的 `MonitorDeps.load_history` 会按既有 fail-closed 合约隐藏自由文本：workbench.selection、consumed.answer、executed.result 为 null，omitted_fields > 0；不会调用 redactor_factory，也不读取凭证。注入显式已知集合 redactor 后，这些真实存储值可通过实际隔离 monitor HTTP GET 和 shipped JS DOM 呈现。默认生产 monitor 没有该注入，因此选择/答案/结果的缺失不能仅靠 UI 修复。
2. history emitted policy disposition `suggested`，但 JS 的 `policyDispositionLabel` 缺此映射；已有其它 status 映射不能覆盖这条路径。
3. 实际节点的依据位于 `node.detail.basis`，JS 错读 `node.basis`；policy_result.basis 也没有被呈现。已按真实层级接线，不从当前配置补旧阈值。
4. lifecycle writer 已写 consumed.reason 与 executed.reason，history fold 未投影；新投影沿既有 `_free` sanitizer，仍 fail-closed，不补写生产 ledger。
5. answer_source 是审计来源字段，样本常缺失，与收到的答案/行动结果不同。底层保留，仅有值时在关闭的 details 内显示，不再空占默认业务节点。

生产形状巡检只输出类型/存在性计数：`t20-inspect-shapes.py`；未输出生产内容、身份或凭证。

## 已实施
- history 仅增加上述两项 reason 投影；exact byte replay 证明其它字节未变。
- suggested 中文为“模型建议（不代表已采纳或执行）”；not-evaluated 为“未记录策略判定（不推断是否已采纳）”。未知值保留原样。
- 接收显示现存答案/原因/时间，明确接收不代表采纳或处理完成。
- 行动保留 action/result 原值并添加固定中文释义；settled 使用本轮结果说明，不将 ok 等同整个任务交付；未知 action/outcome 不猜。
- basis 使用真实 detail/policy_result 记录。不存在的阈值仍显示未记录。
- answer_source 有值才显示“答案来源审计（按需查看）”，默认关闭。

## TDD 与验证
- 原始 red1: 7F3P，其中一个 HTTP helper 的 AttributeError 是测试接线错误，已保留日志；不能当产品 RED。
- 修正 test helper 后 red2: 6F4P，全部六项均为真实生产行为缺口。`ui-recovery/t20-red2-*`。
- green: 新文件10P；既有 readable UI44P、history23P、readable backend32P、dashboard contracts119P；五文件共 **228P**，各 exit0。完整 stdout/stderr/argv/UTC 位于 `ui-recovery/t20-green-*`。
- 新测试含真实 synthetic lifecycle writer→history→shipped DOM、独立随机端口 monitor HTTP GET、未知值原样、reason 脱敏/账本只读、默认 no-redactor 不加载凭证、storage/POST 安全边界。不是实际用户浏览器或 live monitor 验收。
- `t20-source-integrity.json` / `t20-*.diff`：history exact two-insertion replay，JS 当前 LF 与基线 LF 保持一致；未恢复/覆盖外来脏改动。
- 完整 npm run check 在11835文件字节保护副本，exit1，仍为三卡外 TS 文件3 warnings/2 infos。`t20-check/{stdout.log,stderr.log,metadata.json}`；formatter_changes=[]、original_changed_during_check=[]。downstream 链未运行，不宣称全量质量通过。
- phase audit EXECUTE PASS，未推进 DONE。

## 用户待确认的具体边界
本次尚未修改 `decision_monitor.py` 或默认凭证加载路径。要让默认 monitor 的选择/已有答案/自由文本结果恢复可见，需要授权将 monitor startup 的显式已知集合脱敏器接入历史读取；可限定启动时读取本地凭证、仅用于内存脱敏，不输出/修改、不调用模型、不在 history GET 或 polling 时重新发现凭证。也应把默认未知集合继续 fail-closed 并明确安全隐藏的事实，而非猜填旧答案。

该方案将扩展 T20 写面到 decision_monitor.py/相应隔离测试，并改变既有“默认历史读取不发现凭证”的接入行为，必须先确认。已注入 redactor 的测试 GREEN 不等于默认用户 monitor 已恢复显示。

## 未操作
无 worker 派发、模型请求、真实 browser、共享 monitor/serve 操作、build/install、commit、framework/registry/config 修改；生产历史未补写。
