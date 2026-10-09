# T-22: 证据行陈旧性审计（`[VERIFY]` 数值不得是硬编码字面量）

- 波次: **3** · 依赖: T-19, T-21（语义变更的两端）
- 写面（独占）: `packages/multi-workers/test_autopilot_pending_review.py`、`packages/multi-workers/test_autopilot_auto_decision.py`、`packages/multi-workers/test_doctor_gates.py`、`packages/multi-workers/test_autopilot_attribution.py`（仅这些文件，且仅动**证据行**）
- AC: AC-019, AC-027 · VC: VC-024, VC-039..VC-043
- **来源**：PM 复核 T-21 时发现（P-019 的又一实例）

## 问题（实证）

T-19 用例里有一行证据声明是**硬编码字面量**：

```python
_verify(
    "T-19", step1="pending-review", gate="pending", auto_decision_rows=0,   # ← 字面量
    ...
)
```

而 `_verify(tag, **kv)` 的实现是**只打印不校验**（`def _verify(tag, **kv): print(f"[VERIFY] {tag}: ...")`）。
T-21 改变了语义（延后现在**必定**写一条 `decision="defer"` 台账行）⇒ 该场景实际行数已从 0 变 1，这行成了**假声明**，却仍会以 `[VERIFY] T-19: ... auto_decision_rows=0 ...` 的形式进入证据包与 QG 的 grep 依据。

这类行的危险在于：它**永远不会红**（只打印），所以任何语义变更都不会触发它；而 QG 的判定恰恰是"grep 到 `[VERIFY]` 条目 + 看它是否满足充分性标准"——假声明会被当成证据。

## 交付物

1. **修掉已知的这条**：把 `auto_decision_rows=0` 换成**实测值**：
   ```python
   rows = conductor.auto_decision_rows(project)
   _verify("T-19", step1="pending-review", gate="pending",
           defer_rows=sum(1 for r in rows if r.get("decision") == "defer"),
           escalate_rows=sum(1 for r in rows if r.get("decision") == "escalate"),
           step2="review-escalated{closure}", stage_close=0,
           step3="running", done_exit=0)
   ```
2. **全量审计本 key 的这些测试文件里的所有 `_verify(...)` 调用**：逐个判断每个 kwarg 的值是"实测值"还是"硬编码字面量"。
   - 凡**数字/布尔**类断言性 kwarg 且为字面量 ⇒ 改为实测（或至少加注释说明它为何必须是常量，例如"合法取值范围"）。
   - 凡**语义已在本 key 中被后续卡改变**的行（T-05/T-07/T-08/T-12/T-18/T-19/T-20/T-21 都改过语义）⇒ 必须核对当前真值并改为实测。
3. 回执给出**逐行审计表**：`文件:行号 | 标签 | kwarg | 字面量还是实测 | 判定（保留/改为实测/说明为何是常量）`。

## 契约（不得重定义）

- **只动证据行与为其实测所需的取值代码**；不得改任何 `assert` 的强度（不得放宽、不得删除）。
- 不得引入会掩盖真实值的写法（例如把实测值截断成布尔）。
- 不动生产代码（本卡纯测试侧）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py test_autopilot_auto_decision.py test_doctor_gates.py test_autopilot_attribution.py -q`
- 并**运行一次并贴出** `pytest -q -s` 里新的 `[VERIFY] T-19: ...` 行，证明它现在打的是实测值（`defer_rows=1`）。

## 非空洞对照（必须附）

- 把新写法里的实测计数临时改成 +1 ⇒ 打印值必须随之变化（证明它确实在测量，而不是打印常量）。
- 若发现某行字面量**已经**与真值不符（除已知那条外），逐个列出并给出修复前后对照。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t22-evidence-line-audit/report.md`（含逐行审计表、新旧 `[VERIFY] T-19` 原始输出、反向对照、若有其它陈旧行则逐个列出、残留风险）。
