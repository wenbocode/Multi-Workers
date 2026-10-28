# PM State: mw-dynamic-concurrency

## 1. Snapshot
- Key: mw-dynamic-concurrency
- Claim-Id: WENBOZHOU-PC4:8740
- Phase: DONE
- Next Action: —
- Started: 2026-10-14 01:10
- Updated: 2026-10-14 18:24
- Completed: 2026-10-14 18:24

## 2. Task Status

| Task | 卡 | 状态 | 说明 |
|------|----|------|------|
| mdc-rq1 / rq2 / rq3 | T-C1/C2/C3 | done·acked | spec 期调研（派发链、依赖来源、配置镜像） |
| mdc-rq-d3 / d4 / d5 | T-C-D3/D4/D5 | needs-clarification·acked | design 期调研；结论以 `report.md` 落地，PM 已吸收进 design D-101..D-110 |
| mdc-i01-task-graph | T-C-I01 | done·acked | 任务图解析 + 校验（新增 `autopilot/task_graph.py`） |
| mdc-m02-conductor-frontier | T-C-M02 | done·acked | conductor 前沿消费 + advance 计时 + roadmap 校验进 tick（`conductor.py` 唯一写者） |
| mdc-m03-config-panel | T-C-M03 | done·acked | 配置键两侧镜像 + 面板三量 + 语料 73→77 |
| mdc-m04-dispatch-dedup | T-C-M04 | done·acked | 派发层 identity 去重 + 等待类元组（`dispatch.py` + 一行 `conductor.py`） |
| mdc-m05-tests-python | T-C-M05-py | done·acked | `test_mdc_concurrency.py`（10 条，零生产改动） |
| mdc-m05-tests-ts | T-C-M05-ts | done·acked | `test/suite/autopilot-concurrency-panel.test.ts`（4 条，零生产改动） |
| mdc-m06-e2e-concurrency | T-C-M06 | done·acked | B4 端到端反证 + 量化（`test_mdc_e2e.py` 5 条，零生产改动） |

## 3. Evidence Ledger

- 全部 19 项复核结论：**PASS**（下表每行均为 PM 亲跑；基线失败集对照口径见 P-036）

| # | 判定项 | PM 亲跑证据 | 结果 |
|---|--------|------------|------|
| 1 | 任务图解析与四类问题检测 | `python -m pytest -q test_task_graph.py` | 71 passed |
| 2 | 配置语义/镜像/有效性 | `test_autopilot_config.py` + `_parity` + `_effective_config` | 65 passed |
| 3 | TS 配置镜像与面板 | `autopilot-config-parity` + `-sync` + `autopilot-console` | 44 passed |
| 4 | monitor 快照 | `autopilot-monitor.test.ts` | 26 passed |
| 5 | 并发面板三量 | `autopilot-concurrency-panel.test.ts` | 4 passed |
| 6 | 四文件合成 | 新增面板 + parity + sync + monitor | 36 passed |
| 7 | TS 类型 | `npx tsgo --noEmit` | exit 0 |
| 8 | 全量 Python | `python -m pytest -q -rf` | 6 failed / 2222 passed / 10 deselected，失败集 == 基线 6 条 |
| 9 | M-02 前沿与回退探针 | 原位置重跑附录 A + B | cap/前沿/链式/写面/校验去重 全部复现 |
| 10 | M-02 advance 量化 | 三样本 + idle tick | `ms=[243,561,230]`、`window_share=0.991371`、`81.00x` |
| 11 | M-04 双入口去重 | direct + conductor 入口各 5 连跑 | 均 `grants=1 refusals=1 rows=1 dispatch_events=1`；conductor 侧 `stalled_events=0` |
| 12 | M-04 与写面套件 | `test/test_write_face_dispatch.py` + `test_write_face.py` | 160 passed |
| 13 | M-05 Python | `test_mdc_concurrency.py` + 相邻三文件 | 10 passed；231 passed |
| 14 | conductor/dispatch 组 | 7 个套件 | 186 passed |
| 15 | M-06 e2e | `test_mdc_e2e.py` + 定向四文件 | 5 passed；241 passed |
| 16 | M-06 原始 `[VERIFY]` 回放 | `pytest -q -s test_mdc_e2e.py` | VC-105/106/109 + AC-002 全部复现 |
| 17 | 越界红修复 | `test_rag_launcher.py` + `test_rag_init.py` | 19 passed；12 passed |
| 18 | 仓级检查 | `npm run check` | exit 0（越面副作用已披露，见 P-017 复发） |
| 19 | 语料 | `test/fixtures/autopilot-config-corpus.json` | 77 cases / 19388 B / sha256 `f5b60e81…13e9c1` |

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions

| 决策 | 内容 |
|------|------|
| D-018 | 写面判定（判面）必须先于并发放开 —— 前置 key `mw-write-face-guard` 已 DONE，本 key 据此开闸 |
| D-101..D-110 | 前沿来源、卡头 `deps:` 载体、独立解析器、数字核心 join、fail-closed 串行、观察式校验、面板三量口径、配置键语义、advance 计时载体（无新事件名）、身份去重（详见 `design.md`） |
| D-111 | 队列任务身份 `ap-{owner}-{stem}`（沿用 WFG） |
| D-112/D-113 | 逗号不作写面内容；渲染器遇逗号回退块列表 |
| D-114 | 事件词表冻结：并发观测只能进既有事件 `data`/`detail`，不得新增事件名 |
| D-115 | 写面未声明的卡 = 串行（不拒绝），迁移非必要 |
| PM 裁定 3b | identity 拒绝属"等待下一 tick"类（入 `_WRITE_FACE_WAIT_REFUSALS`），不得 `mark_stalled` |
| PM 裁定 | `test_rag_launcher.py` 中编码了"在飞被覆盖重派"的既有断言由 PM 机械重修（合法作废，未删/未跳/未放宽） |
| PM 裁定 | `upsert_worker_row` 按 `task_key` 无条件替换 = RF-1..RF-4 机制面；M-04 为根修候选；spawner 追查另开 key |

## 6. Turn End Records
*(empty)*

## 7. Process Log

- 2026-10-14 01:10 建 key（deps = mw-write-face-guard）。
- spec 期 3 张调研卡 + design 期 3 张调研卡 → AC-001..013 / VC-101..109 / D-101..110 落定；plan.md 定义 B0–B4 批次与写面唯一性表。
- B0：`mdc-i01-task-graph` ‖ `mdc-m03-config-panel`（写面不相交）。
- B1：`mdc-m02-conductor-frontier`（`conductor.py` 唯一写者）。
- B2：`mdc-m04-dispatch-dedup`（`dispatch.py` + conductor 一行）。
- B3：`mdc-m05-tests-python` ‖ `mdc-m05-tests-ts`（只新增测试文件，零生产写）。
- B4：`mdc-m06-e2e-concurrency`（端到端反证 + 量化）。
- 吸收期每一张卡都做了独立复核（P-025）：探针原位置重跑、代码逐点读证、失败集归因、A/B 隔离证伪既有红、幻影红（P-036）剔除。
- 收口期补建质量门前置件（`evidence-requirement.md` + `baseline/` + `runs/`，脚本可重跑），并按 P-013 形状约束写 `achieved.md`（`## 系统行为变化` + `## 遗留`）。
- 过程偏差三条（`./test.sh` 不可达、`npm run check` 越面写、幻影红）已计入质量门报告 §0 与坑点台账（P-017/P-032 [高危] 复发 + 新增 P-036）。
