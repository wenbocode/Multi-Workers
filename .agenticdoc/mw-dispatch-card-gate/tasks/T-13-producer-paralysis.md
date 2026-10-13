# T-13 生产者侧：conductor 派发不得瘫痪（AC-009）

- Key: mw-dispatch-card-gate｜Wave: 7（**与 T-12 并行**）｜依赖: T-10（终态）、T-09 的门禁语义｜type: coding

## 上下文
用户裁定：**autopilot 的 conductor 事实上已被瘫痪，必须在本 key 内修复**（新增 AC-009「生产者不瘫痪」+ P-10「门禁与注入分处两个版本域」）。

已实测证据（见 `evidence/incidents/autopilot-producer-paralysis-20261012.md`）：
- `H:\git\E2Feature`：队列 675 done / 33 failed / **0 pending / 0 running**，`_workers.parallel` mtime `10-10 20:45`（**2 天零派发**）；该项目全部 worker **无重启**迹象。
- 机制候选 M2（本卡负责的机制）：本 key 的门禁 `ENVELOPE_ENFORCE_SINCE` 在**全局服务层** `packages/multi-workers/launcher.py`，而满足门禁所需的**注入**在**每个项目的 framework 副本** `autopilot/dispatch.py::render_task_md` ⇒ **两个版本域**。全局服务一 enforce，未同步的项目（旧 `dispatch.py`，无注入、无 extras 段）**每一次派发都会被 G-3 拒**（`spawned=[]` + 行 `failed` + `[launcher] envelope missing: …`）⇒ autopilot 表现为整体瘫痪。
- 叠加 F-02（QG 一票否决）：extras 判据对象错位 —— 服务层检查**派生 task.md** 的 extras，而生成端的 `extractCardSections` 只抽三段、丢弃 extras 独立段正文 ⇒ 即使有卡片背书也会被误拒（**过拦**）。你的任务是让 **producer 端自足**，不依赖该注入路径。

## 要求（逐条可验收）

1. **producer 端自足**：`packages/multi-workers/autopilot/dispatch.py::render_task_md`（及同文件内其它 task.md 渲染路径）对**全部生产路径**产出的 task.md 必须自身满足门禁：
   - 有卡（`tasks/*.md` 背书）；
   - 无卡合成派发（L3 修复 / repair / roadmap 等 `synthesized_card` 路径）；
   - 三条 canonical 段 + **该 type 所需的全部 extras**（`coding` 至少：写入允许面、写入禁止面、验收命令、改动历史），且内容非空、来自该任务的真实元数据（不得注入空骨架，沿用 T-10 裁定）。
2. **producer 身份行**：在 task.md 头部区写入机器可读的 producer 身份/版本行（建议 `envelope_producer: <producer>@<version>`）。用途：让服务层能区分「旧 producer（版本偏移）」与「真缺段」。版本值必须来自**既有版本源**（不得新增无来源的硬编码常量）；无 producer 版本源时，取 `packages/multi-workers` 包版本或 conductor 的既有版本常量，并在报告中说明取值出处。
3. **不得制造幽灵引用**：无卡派发**不写** `card_path:` 行（T-10 裁定）；有卡派发写真实路径 + 摘要行。
4. **可执行回归**（新建 `packages/multi-workers/test_mwds_t13_producer_paralysis.py`）：
   - 对每条生产路径：`render_task_md` 的产物喂 `launcher._envelope_refusal(<entry>)`（**只读导入 launcher**）断言返回 `None`（即可 spawn）；覆盖至少：有卡 `coding`、无卡合成 `coding`、无卡合成 `repair`/`roadmap` 形态，以及 `review`/`research` 形态各一；
   - 构造**旧 producer 形态**（无 canonical 段 / 无 producer 身份行）用例，断言它**会被拒**（坐实瘫痪机制；T-14 修服务层后此用例应改为断言"给出升级指引且不静默零产出"，届时由 T-14 调整，本卡只登记该预期）；
   - 断言 producer 身份行可被解析（正则/分词均可，形态要在报告中写明）。
5. **不得触碰 T-12 的写面**：本卡**禁止**修改 `packages/multi-workers/launcher.py`、`autopilot/card_audit.py`、`packages/coding-agent/**` 任何文件、`packages/multi-workers/test_mwds_t27_*.py`、`test_mwds_t29_*.py`（T-12 正在写它们）。若你判断必须改这些文件才能达标，**停下来在报告中说明**，不要动手。

## 交付格式
- 写入允许面：`packages/multi-workers/autopilot/dispatch.py`、新建 `packages/multi-workers/test_mwds_t13_producer_paralysis.py`、必要时 `packages/multi-workers/autopilot/config.py`（仅新增常量/开关，不得改动既有语义键）。
- 写入禁止面：`packages/multi-workers/launcher.py`、`mw.py`、`mw_common.py`、`autopilot/conductor.py`（只读）、`autopilot/card_audit.py`、`packages/multi-workers/test_mwds_t27_*.py`、`test_mwds_t29_*.py`、`packages/coding-agent/**`、其他 key 目录、`.agenticdoc/**`（除本 worker 目录 taskDir 外）。
- 验收命令：
  - `python -X utf8 -m pytest packages/multi-workers/test_mwds_t13_producer_paralysis.py -q` 全绿；
  - `python -X utf8 -m pytest packages/multi-workers/test_autopilot_dispatch.py packages/multi-workers/test_autopilot_conductor_exec.py -q` 全绿（若你的改动使既有金样本断言失效，必须**带 diff 显式重新基线**，不得放宽断言）；
  - `python -X utf8 -m pytest packages/multi-workers -q` 失败数 == **2**（既有基线：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`），不得新增。
- 报告（`report.md`）须含：结论、证据（原始命令与输出，含每条生产路径过闸的实际返回）、改动清单（文件 + 意图）、残留与未验证、上下文来源清单、以及「服务层应如何消费 producer 身份行」的具体建议（供 T-14）。
- 不做 cutover；不改 task 卡；如认为卡有误，在报告中提出供 PM 裁定。
