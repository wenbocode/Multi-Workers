# T-14 服务层：门禁版本偏移不得瘫痪生产者（AC-009 / P-10）

- Key: mw-dispatch-card-gate｜Wave: 8（可与 T-13 并行）｜依赖: T-12（终态，`launcher.py` 已释放）、T-13（producer 侧）｜type: coding

## 上下文
用户裁定：**autopilot 的 conductor 事实上已被瘫痪，必须在本 key 内修复**（AC-009 + P-10）。事故证据：`evidence/incidents/autopilot-producer-paralysis-20261012.md`（实测 `H:\git\E2Feature` 队列 675 done / 33 failed / **0 pending / 0 running**，队列 2 天零写入 = 零派发）。

机制 M2（本卡负责）：门禁 `ENVELOPE_ENFORCE_SINCE` 在**全局服务层** `launcher.py`，满足它所需的注入在**每项目 framework 副本** `autopilot/dispatch.py` ⇒ **两个版本域**。全局服务一 enforce，未同步的项目**每一次派发都被 G-3 拒**（`spawned=[]` + 行 `failed` + `envelope missing`）⇒ autopilot 整体表现瘫痪。T-13 使 producer 端自足并写入 **producer 身份行**；本卡让**服务层**把「版本偏移」与「真缺段」区分开，并把前者变成**响亮、可操作、可一键放行**的事件而不是静默清零。

**接口契约（PM 固定，本卡按此实现）**：producer 在 `task.md` 头部区写机器可读行
`envelope_producer: <producer-id>@<version>`（T-13 负责产出；缺失即为 legacy/unknown）。版本比较基准 = 服务层自己认识的 `ENVELOPE_ENFORCE_SINCE` 与 producer 身份行的组合语义。

## 要求（逐条可验收）

1. **三分支可判**：服务层在 spawn 判定处必须能区分并**分别记录**三种情形：
   - (a) task.md 含 canonical 信封（含该 type 的 extras）⇒ 放行（现状）；
   - (b) task.md 缺信封**但带有 `envelope_producer:` 行且其版本早于服务基线** ⇒ **版本偏移（skew）**，不得记成普通 `envelope missing`：行状态/原因须为**可检索的偏移原因**（如 `failed(producer-skew ...)`），并在该 worker 的 `worker.log` 写**一行可操作指引**（说明缺什么、以及升级项目 framework 副本的命令/入口）；
   - (c) 无 `envelope_producer:` 行且无信封（legacy/unknown producer）⇒ 保持 **fail-closed**（T-09 裁定不变，不得因本卡放宽默认），但同样必须**响亮**：写指引行，不得只留一句 `envelope missing`。
2. **不得静默零产出**：同一 key 在同一轮 poll 中因 (b) 被拒的行数 > 0 时，必须产生**一条聚合可见告警**（不是每行一条），内容含 key、行数、producer 身份、基线、以及升级指引；写入服务层既有的可诊断出口（`worker.log` / 行原因 / 既有的 doctor 可读面）。**不要**修改 `pm-orchestrator.ts` 的 TS 告警通道（不在本卡写面）——若你判断必须联动，在报告中说明供 PM 另立卡。
3. **逃生舱（默认关）**：提供一个**显式开关**（配置键，默认关闭）允许把 (b)/(c) 降级为「服务层兜底注入 canonical 三段 + extras 骨架并放行」。要求：
   - 默认值**必须**是关闭（fail-closed 默认不变）；
   - 开关开启时，放行的每一行**必须**留可检索的审计事实（如 `[ENVELOPE_FALLBACK]`）并写进 `worker.log`；
   - 开关必须**只影响信封判定**，不得放宽 `allow_foreign_write` 等写面判据（沿用逃生舱既有的"真读 + 不放宽 deny 面"约束）。
4. **收窄失效面**：偏移只允许影响**被拒的那一行**，不得使同 key 其它行、其它 key 的行停止被 poll（即：不得因偏移提前 return / 抛异常中断 `_poll_once`）。请给出可执行反例。
5. **回归用例**（新建 `packages/multi-workers/test_mwds_t14_producer_skew.py`）：
   - (b) 用例：构造 post-boundary + 无信封 + `envelope_producer: dispatch.py@<旧版本>` 的 task.md ⇒ 断言行原因/日志为**偏移**且含指引、含聚合告警、且同批次的另一合规行**照常 spawn**（收窄失效面）；
   - (c) 用例：无身份行 + 无信封 ⇒ 断言仍 fail-closed（`spawned=[]`）但日志含指引；
   - 开关用例：开关关闭 ⇒ 拒绝；开关开启 ⇒ 放行且留 `[ENVELOPE_FALLBACK]` 审计事实；断言开关**不**放宽写面判据；
   - 与 T-13 的联调用例：`dispatch.py` 产出的合规 task.md（含身份行）⇒ 放行（若 T-13 产物尚未落地，用等形态夹具并在报告中标注）。

## 交付格式
- 写入允许面：`packages/multi-workers/launcher.py`、`packages/multi-workers/autopilot/config.py`（仅新增开关键，不得改动既有语义键）、新建 `packages/multi-workers/test_mwds_t14_producer_skew.py`、`packages/multi-workers/test_launcher.py`（仅必要夹具）。
- 写入禁止面：`packages/multi-workers/autopilot/dispatch.py`（T-13 正在写）、`autopilot/card_audit.py`、`mw_common.py`、`autopilot/conductor.py`（只读）、`packages/coding-agent/**`、其他 key 目录、`.agenticdoc/**`（除本 worker 目录 taskDir 外）。
- 验收命令：
  - `python -X utf8 -m pytest packages/multi-workers/test_mwds_t14_producer_skew.py -q` 全绿；
  - `python -X utf8 -m pytest packages/multi-workers/test_mwds_t27_service_envelope.py packages/multi-workers/test_mwds_t29_producer_signal.py packages/multi-workers/test_launcher.py -q` 全绿（T-09 的早于边界豁免 / 晚于边界拒绝用例**必须保持绿**，不得放宽）；
  - `python -X utf8 -m pytest packages/multi-workers -q` 失败数 == **2**（既有基线：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`），不得新增。
- 报告（`report.md`）须含：结论、证据（原始命令与输出，含三分支各自的判定与日志原文、收窄失效面的反例、开关开/关对照）、改动清单（文件 + 意图）、残留与未验证、上下文来源清单。
- 不做 cutover；不改 task 卡；如认为卡有误，在报告中提出供 PM 裁定。
