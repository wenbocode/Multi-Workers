# T-10 conductor 无条件注入 + 金样本显式重新基线

- Key: mw-dispatch-card-gate｜Wave: 5｜依赖: T-09（已终态）、T-02｜type: coding

## 上下文
T-09 按「**仅卡背书注入**」落地，代价是 **card-less 的 autopilot 自动派发**（L3 修复 / repair / roadmap）在 `ENVELOPE_ENFORCE_SINCE` 边界之后会被判缺段拒绝 ⇒ **autopilot 路径在 cutover 后失效**（`evidence/…/workers/mwd-t09-producer-signal/report.md` §4.1 残留①）。同时它实测：若改为无条件注入，`test_autopilot_dispatch.py` 的 AC-015 sha 与 `test_autopilot_conductor_exec` 的 body 逐字节断言失效，全量失败数由 2 涨到 11。

PM 裁定：**无条件注入 + 显式重新基线**。理由：`design.md` §1.3 要求「派发产物由机器注入同一四项」，DQ-3 也把"生成端构造保证"作为零误拒的前提；按需注入等于让门禁的覆盖面取决于"有没有卡"，把炸弹留到 cutover 之后。金样本（sha/逐字节）的职责正是**在形态有意变更时强制一次人工决策** —— 所以正确做法是**带 diff 地重新基线**，而不是为回避它而缩小注入范围。

## 要求
1. **无条件注入**：conductor 的 `render_task_md` 对**所有**派发注入 canonical 三段（`## 上下文` / `## 要求` / `## 交付格式`）+ 头部区裸行 `card_path:` / `card_sha256:`。
   - 有卡：内容与摘要取自卡（现状已实现）。
   - **无卡的自动派发（L3 修复 / repair / roadmap）**：用**任务元数据合成非空内容**，不得注入空骨架 —— 上下文 = 触发检查项/失败原因 + 证据路径；要求 = 修复目标 + 可判定判据；交付格式 = 产物路径与形态。段的**非空**必须由构造保证。
2. **显式重新基线**：更新被本次形态变更影响的字节/摘要冻结金样本（至少 `test_autopilot_dispatch.py` 的 AC-015 sha、`test_autopilot_conductor_exec` 的逐字节 body 断言）；**在报告中给出 pin 的新旧值与 diff**，说明"形态变更属本次有意变更"。**不得放宽断言**（金样本仍须逐字节/逐 sha 固定），不得删除断言。
3. **回归证明**：全量 `packages/multi-workers` 的失败数必须**回到 2（既有基线：`test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below`）**，不得新增。
4. 新增用例（`test_mwds_t29_producer_signal.py` 内扩展或另立文件）：① **无卡自动派发** ⇒ 生成物三段非空且通过校验（含与 TS judge 的 parity）；② 有卡派发 ⇒ 内容来自卡；③ 早于边界豁免、晚于边界拒绝（T-09 已有，须保持绿）。

## 交付格式
- 写入允许面：`packages/multi-workers/autopilot/dispatch.py`、`packages/multi-workers/launcher.py`（仅在必要时）、`packages/multi-workers/test_mwds_t29_producer_signal.py`、`packages/multi-workers/test_autopilot_dispatch.py`、`packages/multi-workers/test_autopilot_conductor_exec*.py`、`packages/multi-workers/test_autopilot_readcap_injection.py`（仅 pin/fixture 数据）。
- 写入禁止面：`packages/multi-workers/mw.py`、`mw_common.py`（只读）、`autopilot/conductor.py`（只读）、`packages/coding-agent/**`、其他 key 目录、`.agenticdoc/**`（除本 worker 目录）。
- 交付物：上述改动 + 测试；`report.md` 含结论/证据（原始命令与输出）/改动清单/残留与未验证/上下文来源清单。
- 回收判据：
  - `python -X utf8 -m pytest packages/multi-workers -q` ⇒ **失败数 == 2** 且均为上述既有基线；
  - 报告须含：pin 新旧值与 diff、「无卡自动派发 ⇒ 三段非空且过闸」的原始输出；
  - 改动清单 ⊆ `trace.log` 的 `[WRITE_FILE]` 事件（cutover 后生效）。
