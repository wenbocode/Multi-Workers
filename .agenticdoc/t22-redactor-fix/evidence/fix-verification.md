# T22 生产写链路修复：验证证据

日期：2026-10-25（本机）
缺陷记录：`.agenticdoc/mw-decision-context/evidence/t22-redactor-contract-defect.md`

## 改动

| 文件 | 改动 |
|---|---|
| `packages/multi-workers/mw.py` | `_decide_lifecycle_store` 改用 `decision.credential_redactor()`（wire 兼容 capture filter）；返回 `None` 时抛 `LifecycleInputError` 明确拒绝。`_decide_lifecycle` 的外层 catch 补 `LifecycleInputError` → 输出 `status=refused/error_class=input`，不再抛 traceback。 |
| `packages/multi-workers/decision_wire.py` | 新增 `METADATA_KEY_MIN_SCRUB = 4`；`_sanitize_metadata_key` 只在尾部被裁掉 ≥4 字符时才改写键，否则保留（redacted+clipped）键名。值侧语义未变。 |
| `packages/multi-workers/decision_dashboard.js` | `renderTaskState` 改为结构化卡片：状态徽标（`TASK_STATE_TONES`）+ 来源/记录时间 + `已完成`/`待处理`/`阻塞` 分项 `ul>li`（`task-state-item`）；`null`→未记录、`[]`→无、非法→无法确认保持原语义。 |
| `packages/multi-workers/decision_dashboard.css` | `.task-state` / `.task-state-head` / `.task-state-chip` / `.tone-*` / `.task-state-items` / `.task-state-item` 样式。 |
| `packages/multi-workers/test_decision_task_state.py` | +5 条回归（capture filter 契约与 gate 形状仍被拒、production filter 写全六字段并读回 `recorded`、键的短尾巴不清理、不可证 filter 拒绝建店、`_scratch` 创建事实被拒）。 |
| `packages/multi-workers/test_decision_task_state_ui.py` | +1 条结构化展示断言（chip 文本 + 每项独立 `li`）。 |

`decision.py` 未改（A 取代了先前的 B 方案；`KnownSecretRedactor` 仍是 gate 过滤器）。

## 复现与修复对照

修复前（同一 envelope）：

```
AttributeError: 'KnownSecretRedactor' object has no attribute 'scrub_tail_prefix'
exit 1，账本 0 行
```

修复后：

```
python -X utf8 packages/multi-workers/mw.py decide run dp1-dispatch-type \
  --project . --stdin --json < .agenticdoc/mw-decision-context/evidence/t22-cli-envelope.json
{"available": true, "transport": "timi-decisions", "model": "jev-latest",
 "confidence_source": "api", "attempts": 1, "latency_ms": 1004,
 "answers": {"triage_type": {"value": "research", "confidence": 0.92}},
 "decision_id": "dp1-dispatch-type:9f4c1d2e-…", "record_start": "written",
 "feedback_status": "recorded", ...}
```

账本（`.agenticdoc/_autopilot/decision-lifecycle.jsonl`，47 行 → 49 行）：

```json
{"kind":"record-start","logical_id":"9f4c1d2e-…","key":"mw-decision-context",
 "task_key":"t22-live-verify-cli","decision_id":"dp1-dispatch-type:9f4c1d2e-…",
 "task_before":{"status":"not-queued","observed_at":"2026-10-25T07:10:00Z",
                "source":"worker-registry","completed":null,"remaining":null,"blockers":null}}
{"kind":"lifecycle","lifecycle":"executed","action":"record","result":"answer-returned", …}
```

读侧投影（`decision_history.load_history(..., redact=credential_redactor)`）：

```
task_before = {status: not-queued, observed_at: 2026-10-25T07:10:00Z, source: worker-registry,
               completed: null, remaining: null, blockers: null}
task_before_visibility = "recorded"     (修复前：无记录 / 改 A 不改 B 时：invalid)
task_after_visibility  = "unrecorded"   (本行是 CLI answer，没有派发，符合契约)
```

字段名保真：`observed_at` 与 `completed` 原样落盘（改 A 不改 B 时实测被截成
`observed_a` / `complete`，读侧 `INVALID -> task state requires exactly the declared fields`）。

## 测试

| 套件 | 结果 |
|---|---|
| `test_decision_task_state.py` | 23 passed |
| `test_decision_task_state_ui.py` | 8 passed |
| `test_decision_dashboard_{assets,contracts,playground}.py` + `test_decision_context_readable_ui.py` | 185 passed |
| `test_decision_wire_store.py` + `test_decision_context_lifecycle.py` + `test_decision_history_feedback.py` + `test_decision_redactor_contract.py` + `test_decision_bare_scope_known_set.py` | 169 passed |
| `test_decision_coverage_safety.py` + `test_decision_known_set_snapshot.py` | 10 failed —— 与改动前同一集合（基线，已用"临时回退本次两处改动"对照确认） |
| `test_decision_credential_seam.py` | 9 failed —— 同样为基线（回退对照一致） |

## 运行态

`mw status --project .` 报 `serve code: STALE CODE (content changed) … fix: /mw restart`：
dashboard 的 JS/CSS 在 `decision_monitor` 导入时读入 `STATIC_ASSETS`，所以**必须
`/mw restart`** 才能在浏览器看到新的结构化展示。决策写入不需要重启——扩展调用的
`mw decide run` 每次都是新的 Python 子进程（`.mw-py-path` 指向本仓 `mw.py`）。

### 实测：restart 后仍然看到旧界面（2026-10-25）

restart 后 serve 已是 `serve code: fresh`（PID 27196），但 `/app.js` 仍是旧版：
看板是一个**独立的 detached 实例**（`mw.py _decide_monitor_starter`，PID 39264，
起于 2026-10-24 22:32，父进程早就不在了），它继续占着 43228 并服务旧资产；
`mw decide monitor status` 同时警告 “built from a different protocol/code fingerprint”。

用工具自身的指引替换实例：

```
python -X utf8 packages/multi-workers/mw.py decide monitor open --project . --no-open
# → instance http://127.0.0.1:43228/ (pid 9360, replaced)
```

替换后实测 HTTP：`/app.js` 含 `task-state-chip` / `task-state-item` / `TASK_STATE_TONES`，
`/app.css` 含 `task-state-chip`。浏览器 Ctrl+F5 即见新布局。

## 未做 / 后续

- 不回填历史记录（AC025）。
- 扩展侧对 `mw decide run` 非零退出的处理仍是静默降级
  （`triage-client.triageDispatchEnvelope`：`raw.status !== 0` → `upstream-error`，
  而 `computeDispatchTriage` 仍打 `state=material`）。`_scratch` 这类不可记录 key
  因此在 trace 里仍看不到明确原因，需要 TS 侧另开条目（要重新打包 bundle）。
- `implementation-gate` 的 claim 路径在本仓失效：`_index.parallel` 无表头行，
  `parseIndexRows()` 找不到 `key/status/claimid` 列，于是永远"无 claim"。本次用
  mini-spec 快速路径通过，该缺陷另立条目。
- `/mw restart` 不替换仍在运行的 detached monitor 实例（旧 code fingerprint 继续占端口），
  需要 `mw decide monitor open --no-open`；可考虑让 serve 在 code 变化时自动替换。
