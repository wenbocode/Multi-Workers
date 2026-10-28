# T02b 基础实现安全缺陷修复

type: coding
status: code-complete-review-pending
code_status: 代码完成
verification_status: 验收177/重复118/联合邻接650通过，独立复审待回读
ac_refs: [AC-005, AC-007, AC-008, AC-012, AC-016]
vc_refs: [VC-005, VC-007, VC-008, VC-012, VC-016, VC-017, VC-018]

## 上下文
- goal `.agenticdoc/goal.md`；spec/design/evidence-requirement；原T01/T02卡及report。
- 必须全文读取 `workers/dd-review-foundations/report.md`：CHANGES_REQUIRED，P0-1+P1-1..4，P2-1..5。
- `packages/multi-workers/decision_wire.py:225` scrub_tail_prefix；:729 build_event；:1231 append_event；`mw_common.py:2808` lock_owner_state；按实际函数定位。
- T03并行仅写decision.py/backend/test_decision_wire_transport.py，不得越面。T01/T02原worker终态，当前基础文件专属给本卡。

## 要求
使用systematic-debugging与TDD技能，先实测每个审计finding正确RED，记录失败，再GREEN；不以测试已绿否定缺陷。
1. P0长secret：去掉固定64窗口，按完整已知secret前缀在文本完整suffix核对或不确定整段omit；min_prefix不要漏1–3字符，短尾剪裁需标记。测试>=120字符且非周期secret跨segment/read_cap/序列化收缩三处，包含UTF8/latin1，不能只用26字符secret自证。不得落任何安全未确认原文。
2. P1元数据：所有自由字符串（嵌套dict/list、answers/evidence/issues/reason/error）统一先redact再裁，缺回调敏感文本omit，不只修正文。metadata身份键如何保持join说明精确边界；不是盲替换schema枚举破坏协议。嵌套secret与元字段截断测试。
3. P1熔断：同逻辑call首次采集写失败后后续直接failed不再等锁，scope无call preflight失败也不能反复消耗预算；错误保持可见/一次告警。断言第二事件acquire调用0/累计时间，不以<2s松界替代250ms预算。
4. P1隔离：realpath canonical化test sink及project_id，symlink/junction目标误指production拒绝；检查父目录最近存在祖先与不存在最终文件，不自动mkdir验证；真实symlink fixture（平台不支持明确skip，不冒充Windows junction验收）。TOCTOU威胁同用户之外不泛扩大范围。
5. P1 owner：新增保守tri-state探针，Windows OpenProcess/GetExitCode失败/ACCESS_DENIED返回unknown，只有确证不存在/退出才dead；不改变共享_is_alive/check_pid/doctor历史布尔语义，注入异常/None/拒绝探测均unknown。补测试模拟Win32拒绝及真实当前owner。
6. P2-1收缩后capture_status重算、P2-2未知builder键显式报错不吞、P2-3 canonical project_id、P2-5孤立attempt-end不得抬start计数。API变更给T03清单，默认使用仍保持。P2-4未接线seam标下游T05/06消费，不擅自删除未来接口；单调用helper尽量内联，不堆无消费者字段。
- 修复不能扩大本卡功能范围或更改生产archive/signoff，不能调用付费模型/外网/共享服务。

## 写入允许面
- `packages/multi-workers/decision_wire.py`
- `packages/multi-workers/test_decision_wire_store.py`
- `packages/multi-workers/mw_common.py`（仅新增owner tri-state探针与lock_owner_state使用，root/默认_is_alive不改）
- `packages/multi-workers/test_decision_roots_locks.py`
- `.agenticdoc/mw-decision-dashboard/workers/dd-foundation-fixes/**`
- `.agenticdoc/mw-decision-dashboard/evidence/runs/T02b-*`

## 写入禁止面
- decision.py/backend/所有TS/mw.py/points/book/模板、其他worker/task/相位文档、生产记录/授权、dist、凭证、依赖锁文件。

## 验收命令
cwd packages/multi-workers：`python -m pytest test_decision_wire_store.py test_decision_roots_locks.py test_decide_backends.py -q`；T03接线测试可只读运行、失败报告其owner不越面。
root `npm run check` 全输出，共享禁止面formatter风险报告PM，未完整通过如实记录；禁build/npm test/全vitest/commit。

## 改动历史
- 2026-10-22 PM吸收foundation独立review，明确5个严重缺陷及P2契约修复，原T01/T02局部绿不等于安全通过。

## 交付格式
四段report，逐finding confirmed/fixed/未验证，RED/GREEN精确命令/日志/退出码、schema/API变化给T03；完整测试清单与spy指标，不自报review PASS，完成后PM独立复审。
