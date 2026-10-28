# Evidence Requirement: mw-dynamic-concurrency

## 基础信息

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-dynamic-concurrency/spec.md` |
| spec_locked_at | 2026-10-14 |
| ac_fingerprint | `95d6a253ba12` |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013 |
| vc_ids | VC-101, VC-102, VC-103, VC-104, VC-105, VC-106, VC-107, VC-108, VC-109 |
| generated_at | 2026-10-14 |

`ac_fingerprint` 复算方法（与 `workflow-quality-gate.md` 的校验脚本逐字一致）：
`sha1( sort -u( grep -oE 'AC-[0-9]{3}' spec.md ) )[:12]` —— 即上述 AC id 排序去重、每行一个、行尾换行，取 sha1 前 12 位。当前 payload 为 13 行，复算值 `95d6a253ba12`。

## 映射缺口声明（诚实记录，不假装 100%）

| AC | 情况 | 处置 |
|----|------|------|
| AC-008 | design.md 未给对应 VC | 证据载体上移到测试层：`test_task_graph.py`（M-01，71 passed）+ spec 的 5/5 旧解析器空串实测 |
| AC-010 | design.md 未给对应 VC | 证据载体为 M-02 §5 D 的 tick 内事件原始输出 + 只观察实现的代码审计 |

## 汇总：每个 AC 的充分性判定标准

| AC | 内容 | VC | 证据载体 | 充分性判定 |
|----|------|----|---------|-----------|
| AC-001 | key 层前沿恒等（实起 = min(配置上界, |前沿|)） | VC-101, VC-102 | evidence/M-02-conductor-frontier.md §3 B；.agenticdoc/_scratch/evidence/mdc-m02-probe-a-inplace-out-20261014.txt（PM 亲跑） | ≥3 组构造语料复算，键层实起数与 `min(cap,|F|)` 恒等；原始输出可复算 |
| AC-002 | per-key 实起 = min(per-key 上界, |任务前沿|)，且无写面重叠 | VC-101, VC-102, VC-105 | evidence/M-02-conductor-frontier.md §3 A/A2、§4 C2/C3；VC-105 归 evidence/M-06-e2e.md（待） | per-key 实起恒等 + 写面重叠对 = 0（N≥4 端到端反证在 M-06） |
| AC-003 | 依赖/写面缺失或不可解析 ⇒ 该层串行 + 审计行，不默认放大 | VC-104 | evidence/M-02-conductor-frontier.md §4 C/C2/C3、§5 D；evidence/M-05-tests-python.md（待） | 四类 fail-closed（悬空/环/未声明/重叠）各实测实起 = 1 且有 timeline 事件；去重可证 |
| AC-004 | 配置语义（key 层上界 + 新 per-key 键，两侧镜像） | VC-108 | evidence/M-03-config-panel.md；evidence/M-05-tests-ts.md | 默认 8/4、范围 (1,None)/[1,null] 两侧逐字段相等；materialized config 仍合法 |
| AC-005 | monitor 同显配置上界与本 tick effective 并发，同快照可复算 | VC-107 | evidence/M-03-config-panel.md；evidence/M-05-tests-ts.md | 同一快照复算 cap / eff=min(cap,|F|) / |F| 三量一致，渲染行可读 |
| AC-006 | 上界=1 ⇒ 两层串行，无需重启 serve | VC-103 | evidence/M-02-conductor-frontier.md §7 E；evidence/M-05-tests-python.md（待） | 同进程改配置即生效，两层实起 ≤1 |
| AC-007 | 两语言配置镜像逐字段一致（parity 语料） | VC-108 | evidence/M-03-config-panel.md（TS 44 passed）；evidence/M-05-tests-ts.md | 冻结语料具名 case 判决一致且非空洞（含反例） |
| AC-008 | 任务级 `deps:` 载体 + 新增独立解析器（不得复用 `card_audit._header_value`） | **无 VC（映射缺口，见下）** | packages/multi-workers/test_task_graph.py（M-01，71 passed）；spec 实测 5/5 空串证据；M-02 `_read_task_cards` | 解析器对真实卡抽样复现；H1 首行 + 卡头区域规则；5/5 旧解析器空串已实测 |
| AC-009 | 任务级依赖图校验（悬空/自依赖/环/跨 key）⇒ 整 key 串行 + timeline；数字核心 join | VC-104 | packages/multi-workers/test_task_graph.py（V1-V7）；evidence/M-02-conductor-frontier.md §4 C | 每类 V-problem 各有用例；117/125 数字核心命中可复算；整 key 串行不永锁 |
| AC-010 | key 层 roadmap 语义校验在 tick 内执行（只观察，不改 fail-closed） | **无 VC（映射缺口，见下）** | evidence/M-02-conductor-frontier.md §5 D（原始事件 + 去重） | 校验事件在 tick 内产生且同 problem 只写一次；代码只观察、不抑制/不授权派发 |
| AC-011 | 派发判定与队列写入同临界区；同一 `task_key` 不可被两进程各 append | VC-106 | evidence/M-04-dispatch-dedup.md（待）；VC-106 归 evidence/M-06-e2e.md（待） | 判据 = `ok=True` 次数 == 1 且 timeline `dispatch` 事件数 == 1（不是行数）；双入口对拍 5 连跑 |
| AC-012 | 在飞口径单源（`_is_in_flight`/`_row_belongs_to` 一处导出，服务全部消费点） | VC-107 | evidence/M-02-conductor-frontier.md（代码面审计：谓词未动）；PM 复核 .agenticdoc/_scratch/evidence/mdc-m02-code-audit-20261014.txt；evidence/M-05-tests-ts.md | 谓词与面板逐点同形（TS `workerBelongsToKey` vs Python `row_belongs_to`）；无静默滞后消费点 |
| AC-013 | `advance.advance()` 不得成为并发瓶颈，或给实测量化 | VC-109 | evidence/M-02-conductor-frontier.md §6 + PM 复现；VC-109 归 evidence/M-06-e2e.md（待） | `data.ms` 打点落地且不新增事件名；window_share 有原始采样（PM 复现 0.9914 / 81x） |

## AC-001: key 层前沿恒等（实起 = min(配置上界, |前沿|)）

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md §3 B；.agenticdoc/_scratch/evidence/mdc-m02-probe-a-inplace-out-20261014.txt（PM 亲跑） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-101, VC-102 | — | — |

## AC-002: per-key 实起 = min(per-key 上界, |任务前沿|)，且无写面重叠

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md §3 A/A2、§4 C2/C3；VC-105 归 evidence/M-06-e2e.md（待） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-101, VC-102, VC-105 | — | — |

## AC-003: 依赖/写面缺失或不可解析 ⇒ 该层串行 + 审计行，不默认放大

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md §4 C/C2/C3、§5 D；evidence/M-05-tests-python.md（待） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-104 | — | — |

## AC-004: 配置语义（key 层上界 + 新 per-key 键，两侧镜像）

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-03-config-panel.md；evidence/M-05-tests-ts.md | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-108 | — | — |

## AC-005: monitor 同显配置上界与本 tick effective 并发，同快照可复算

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-03-config-panel.md；evidence/M-05-tests-ts.md | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-107 | — | — |

## AC-006: 上界=1 ⇒ 两层串行，无需重启 serve

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md §7 E；evidence/M-05-tests-python.md（待） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-103 | — | — |

## AC-007: 两语言配置镜像逐字段一致（parity 语料）

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-03-config-panel.md（TS 44 passed）；evidence/M-05-tests-ts.md | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-108 | — | — |

## AC-008: 任务级 `deps:` 载体 + 新增独立解析器（不得复用 `card_audit._header_value`）

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | packages/multi-workers/test_task_graph.py（M-01，71 passed）；spec 实测 5/5 空串证据；M-02 `_read_task_cards` | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | **无 VC（映射缺口，见下）** | — | — |

## AC-009: 任务级依赖图校验（悬空/自依赖/环/跨 key）⇒ 整 key 串行 + timeline；数字核心 join

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | packages/multi-workers/test_task_graph.py（V1-V7）；evidence/M-02-conductor-frontier.md §4 C | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-104 | — | — |

## AC-010: key 层 roadmap 语义校验在 tick 内执行（只观察，不改 fail-closed）

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md §5 D（原始事件 + 去重） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | **无 VC（映射缺口，见下）** | — | — |

## AC-011: 派发判定与队列写入同临界区；同一 `task_key` 不可被两进程各 append

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-04-dispatch-dedup.md（待）；VC-106 归 evidence/M-06-e2e.md（待） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-106 | — | — |

## AC-012: 在飞口径单源（`_is_in_flight`/`_row_belongs_to` 一处导出，服务全部消费点）

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md（代码面审计：谓词未动）；PM 复核 .agenticdoc/_scratch/evidence/mdc-m02-code-audit-20261014.txt；evidence/M-05-tests-ts.md | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-107 | — | — |

## AC-013: `advance.advance()` 不得成为并发瓶颈，或给实测量化

| 证据来源 | 证据载体 | 期望节点/值 | 充分性判定 |
|---------|---------|----------|----------|
| [VERIFY]/[FLOW] | evidence/M-02-conductor-frontier.md §6 + PM 复现；VC-109 归 evidence/M-06-e2e.md（待） | 见上行判定标准 | 满足 PASS 需现场复算一致 |
| VC 映射 | VC-109 | — | — |

## 质检门禁使用说明

`/quality-gate` 读取本文件取得每个 AC/VC 的充分性判定标准；`evidence/baseline/` 存冻结基线，
`evidence/runs/` 存各 worker `output.md` 的 `[VERIFY]`/`[FLOW]` 条目（由
`.agenticdoc/_scratch/evidence/mdc-build-evidence-artifacts-20261014.py` 机械抽取，可重跑）。
