# T22 生产写链路缺陷：生产 redactor 不满足 wire 契约

记录时间：2026-10-25（本地验证，只读 + 一次真实 `mw decide run` 复现）
状态：**已定位，未修复**（工作树已复原，无半成品改动）

## 症状

reload + `mw build --install` 之后，任何新的 dp1 派发都**不写账本**：

- 本窗口派发 `t22-live-verify-20261025`（owner key `_scratch`）：`[DECISION] dp1 state=material bytes=2072` 已打印，账本零行。
- 另一窗口派发 `dpc-rq7/rq8/rq9`（07:00Z，owner key `mw-dp-consolidation`）：同样 `state=material`，账本零行。
- 账本最后写入停在北京时间 10:16（`2026-10-25T02:13:12Z`），之后全部 `_autopilot/*.jsonl` 无写入。

## 复现（真实请求，一次）

```bash
python -X utf8 packages/multi-workers/mw.py decide run dp1-dispatch-type \
  --project . --stdin --json \
  < .agenticdoc/mw-decision-context/evidence/t22-cli-envelope.json
```

envelope 只比日常多一个合法 `meta.task_before`（schema 见 T22）。exit 1：

```
File ".../decision_wire.py", line 936, in _sanitize_metadata_key
    scrubbed, _scrubbed_flag = scope.redact.scrub_tail_prefix(clipped)
AttributeError: 'KnownSecretRedactor' object has no attribute 'scrub_tail_prefix'
```

## 根因 1（主因，阻断级）

- `mw._decide_lifecycle_store` 注入 `decision.known_secret_redactor(...)` → `KnownSecretRedactor`。
- 该类的设计定位是 **book gate 的过滤器，不是 capture filter**：它只有 `redact()`。
  既有测试明确要求它**必须被拒绝**作为 `scope.redact`
  （`packages/multi-workers/test_decision_coverage_safety.py:569-580`：
  “KnownSecretRedactor ... is not a capture filter ... Refusing it is the observable form of that”）。
- `decision_wire` 的 sanitizer 却直接调用 `scope.redact.scrub_tail_prefix(...)`；
  异常被 transport 吞掉 → 账本静默零行（`decision.py:1213 _capture_filter_contract_issue`
  已把这一失效模式写成契约，但 `mw` 的注入点没有走该检查）。
- 只有携带**嵌套 metadata**（`task_before`）的记录会触发 metadata-key sanitizer；
  T22 之前的普通 record-start 只含标量，因此历史上未暴露。即：**T22 的前后快照写入
  在真实路径从未成功**，与“新记录仍显示未记录”一致。

## 根因 2（修好根因 1 之后仍会挡路）

把过滤器换成 wire 兼容的 `decision.credential_redactor(...)`（`_CredentialRedactor`
→ `decision_wire.SubstringRedactor`）后，写会成功，但 metadata key 的尾部清理
按 `MIN_SCRUB_PREFIX = 1` 执行：只要某个已知凭证以某字母开头，键尾 1 个字符就被删掉。

本地实测（同一份已发现凭证集）：

```
observed_at -> ('observed_a', True)
completed   -> ('complete', True)
```

读侧 `decision_task_state.validate_task_state` 要求六个字段精确齐全 → `observed_a`
会被判为非法，DAG 显示“任务状态无法确认”，而不是“未记录”。所以根因 1 修好后
仍需给“键的尾部清理”加最小片段长度（`decision.py::_MIN_SECRET_LEN = 4`，与
`_COVER_RESIDUAL_LEN` 一致；1–3 字符不是可用凭证片段）。

## 候选修复

A（推荐）：三处最小改动，保留既有 T05q 设计
  1. `mw.py::_decide_lifecycle_store` 改用 `decision.credential_redactor(...)`；
     返回 `None`（wire 不可用／快照不可证）时**拒绝写入并报告**，不要静默降级。
  2. `decision_wire._sanitize_metadata_key` 的 `scrub_tail_prefix` 采用 4 字符下限
     （或用显式参数），避免 `observed_at` 被截。
  3. 补两条回归：生产过滤器真写 `record-start`；六个状态字段名不被清理改写。

B：给 `KnownSecretRedactor` 补 `scrub_tail_prefix`（我临时实现过，2 条契约测试转红，
   且与 `test_decision_coverage_safety.py:569-580` 的既定点设计冲突）→ 不推荐。

C：只修 AttributeError（A 的第 1 步），接受 `observed_a` → 快照读侧永远非法 → 不解问题。

## 旁证与相关发现

- 独立 worker（`t22-live-verify-20261025`，research/done）只读核对：账本 47 行，本任务
  0 行；12 条 `record-start` 中 7 条带 `task_before` 字段且全为 `null`；20 条带
  `task_after` 的记录全为 `null`；最后写入 `2026-10-25T02:13:12Z`。
  证据：`.agenticdoc/_scratch/evidence/t22-live-verify.md`。
- `_scratch` 不是合法 lifecycle key（`decision_lifecycle.py:118 _KEY_PATTERN`
  要求首字符 `[A-Za-z0-9]`）。因此**无 claim 窗口的默认 `_scratch` 派发永远无法留下
  决策记录**；该路径应改用合法 key 或显式报告“不可记录”，不能静默。需另立条目。
- 相关两个测试文件存在**改动前基线失败 10 条**（与本缺陷无关）：
  `test_decision_coverage_safety.py` 6 条（points entry 的 caller-filter 系列 +
  1 条 complete-wrapped）、`test_decision_known_set_snapshot.py` 4 条。
  对比方法：临时移除候选实现后复跑，失败集合与基线一致。

## 本次未做

- 未提交任何修复：`decision.py` 与 `test_decision_task_state.py` 已复原
  （`test_decision_task_state.py` 18 passed）。
- 未改 `mw.py`、未改 wire 语义、未回填历史记录、未重置任何账本。
- 除上面一次真实 `mw decide run`（用于取 traceback）外未追加模型调用。
