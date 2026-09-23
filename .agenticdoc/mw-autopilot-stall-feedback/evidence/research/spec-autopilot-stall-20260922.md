# Spec 阶段调研证据：E2Feature autopilot 停滞现场

- 采集时间：2026-09-22 21:28–23:55（本地）
- 采集人：PM 窗口（本 key 拥有者，PI_SESSION_ID 01a0c949）
- 现场：`H:\git\E2Feature`（control workspace；父 root `E:\UEMigrator`）
- 关联 key：`mw-autopilot-stall-feedback`（spec.md AC-001/AC-003/AC-012 的证据来源）

## 1. 现象与量化

| 观测项 | 值 | 来源 |
|--------|----|------|
| 停滞起点 | 2026-09-22T10:53:06Z | `_autopilot/timeline.jsonl` 首条 `execute->verify exit=1` |
| 同签名失败次数 | 2242（诊断时刻 21:28） | timeline `advance` 事件计数 |
| 无界重试时长 | 2h35m（至 21:35:41 修复生效） | 同上 |
| 同型故障（当日更早） | spec→design ×14；design→plan ×3891 / 4h25m | timeline；后者由 `d106bcfb2` 修复 |
| 期间派发数 | 0（18:54:08Z 之后无 dispatch） | timeline `dispatch` 事件 |
| conductor 心跳 | 每 4s 一跳，从未中断 | timeline `beat`（seq 21480→23357 全为 beat） |
| 事件总数 | 21k+ 行 / 4.14 MB | `timeline.jsonl` 体积 |

结论：不是「进程死了」，而是 **conductor 活着但空转**——每 tick 调一次必然失败的 `advance_phase.py`，失败只记一行自由文本，既无预算、无门禁、无状态提示。

## 2. 根因（第一处，接口漂移）

`H:\git\E2Feature\.agenticdoc\feature-params-service\pm-state.md` 第 5 行（14396 B，无 BOM，CRLF，UTF-8 合法）：

```
- Phase: EXECUTE（T-014 结案完成，待 PM 侧 `advance_phase … done`）
```

写入者：T-014 结案 worker 的 `edit`（`workers/ap-feature-params-service-014-params-service-closeout-quality-gate/trace.log:110`，10:52:24Z）。

消费侧：`advance_phase.py` 用 `^- Phase:\s*(.+)$` 取值 → `execute（t-014 结案完成…）` 不在 `spec|design|plan|tasks|execute|verify|done` → exit 1：

```
ERROR: feature-params-service/pm-state.md has unknown phase 'execute（t-014 结案完成，待 pm … `advance_phase … done`）'.
```

conductor 侧 `conductor.py:878-885`（`execute_loop` 尾部）只做：

```python
code, _out, err = advance.advance(key, "verify", project_root, summary=...)
st.timeline.append("advance", key=key, detail=f"execute->verify exit={code}")
if code != 0:
    st.timeline.append("config", key=key, detail=f"advance verify failed: {err.strip()[:200]}")
return False
```

无计数、无退避、无升级 → 每 4s 一次，直到人工介入。

## 3. 根因（第二处，L3 worker 崩溃被当作 verdict）

修复第一处后（21:35:41 起 `execute->verify exit=0`），流程推进到 VERIFY，暴露出第二个缺陷：

| 时间（本地） | 事件 | 结果 |
|---|---|---|
| 21:35:45 | dispatch `ap-feature-params-service-l3-a1`（reviewer） | 7s 后 `failed` |
| 21:35:53 | dispatch `ap-feature-params-service-repair-a1` | 7m19s 后 done |
| 21:43:16 | dispatch `ap-feature-params-service-l3-a2`（reviewer） | 6s 后 `failed` |
| 21:43:24 | `gate-created gate-0002 kind=stalled` + `stalled` 事件 | `L3 below 2 rounds (budget 2)` |

worker.log（两个 reviewer 相同）：

```
Warning: Model "gpt-5.6.sol" not found for provider "timi". Using custom model id.
OpenAI API error (403): {"message":"请求模型不存在 请确认参数model", ...}
```

即 `.mw/dispatch.yml` 的 `review: timi/gpt-5.6.sol` 为点号笔误（正确 `timi/gpt-5.6-sol`，同仓 `H:\git\Multi-Workers\.mw\dispatch.yml` 与 pi 文档均用连字符）。`_parse_l3_output` 对缺失 output.md 返回 `below` → 触发 repair（对着崩溃的 L3 报告修）→ 预算烧完 → `stalled`。

**报告失真**：真实原因是「reviewer worker 启动即 403」，而门禁/停滞原因写的是「L3 below 2 rounds」——人和面板都会被误导。

## 4. 报告链缺口

`stalled` 门禁问句是「遗留关闭（closed-legacy），还是人工介入后重试？」但 conductor 只消费 **reject**：

- `_apply_stalled_rejections`（`conductor.py`）：`status == "rejected"` → key-status → `closed-legacy`；
- `_consume_answered_gates`：只处理 `stage-confirm` / `stage-close`；
- `_budget_bonus` / `_budget_gate_rejected`：只看 `budget-exhausted`。

**approve 是 no-op**：key-status 停在 `stalled`，`orchestrate` 的 skip 规则（`status_of in ("done","stalled","closed-legacy")`）使该 key 永不再进入；L3 预算也已耗尽（`used=2 >= round_budget=2`），即使复位也会立刻再次 `mark_stalled`。所以「人工介入后重试」这条路在当前实现里不存在。

## 5. 依赖阻塞放大

`roadmap` 的 `> key-status:`：`feature-viewer-mvp=done`、`feature-params-service=stalled`、其余 K3..K6 `running`。K3 `feature-gui-backend` 依赖 K2 → `_DEP_SATISFIED = {done, closed-legacy}` 不满足 → K4/K5/K6 传递阻塞 → 零 eligible key、零派发。单点停滞把整条 Stage 1 拖停。

## 6. 结论（驱动 spec）

1. 非瞬时 advance 失败必须**有界**（连续同 key+edge 失败达阈值即升级），而不是靠人发现。
2. 升级必须走既有 `stalled` 四件套（key-status + 门禁 + achieved 草稿 + pattern），并**实现 approve 的恢复语义**（复位 + 一轮额度），否则门禁问句在骗人。
3. L3 worker 崩溃必须与 reviewer 真裁决 `below` 区分（`no-verdict`），否则修复动作打错目标、原因上报失真。
4. 停滞必须在 PM 窗口可见（底部监控面板），不能只躺在 timeline 里。
