# 事故：autopilot 生产者瘫痪（conductor 零派发）

- 登记: 2026-10-12｜Key: `mw-dispatch-card-gate`（用户裁定纳入本 key，AC-009）｜严重度: **P1（autopilot 主路径失效）**
- 状态: 机制待定位（本文件给出实测证据 + 两个候选机制 + 判别方法），修复分两卡（T-13 producer 侧 / T-14 服务层侧）

## 1. 实测证据（`H:\git\E2Feature`，2026-10-12T14:3xZ）

| 观测 | 数值 | 含义 |
|---|---|---|
| `.agenticdoc/_workers.parallel` 行状态分布 | **675 done / 33 failed / 0 pending / 0 running**（共 708 行） | 队列里**没有任何在途工作** |
| 队列文件 mtime | **`10-10 20:45:16`** | **2 天零写入** ⇒ 2 天内没有任何一次派发/状态推进 |
| 有 `[START] pid=` 出现 ≥2 次的 worker | **0 个** | 该项目**没有**本仓库正在经历的 worker 重启循环 ⇒ 不是同一根因（排除"重启消耗"假说） |
| 33 条 `failed` 行 | 未被重试 | 没有任何生产者把失败行重新派发 |

对照本仓（`H:\git\Multi-Workers`）：队列活跃、worker 运行中、30 分钟内同一 task_key 出现 **5 个 pid**（重启循环，另一主题）。

## 2. 两个候选机制（未定论，需判别）

**机制 M1：生产者缺失（归属缺口）**
`.agenticdoc/*/workers/*/task.md` 的扫描只覆盖「本窗口 watch 的 key + `_scratch`」（AC-019 隔离语义，`pm-orchestrator.ts` `dispatchNewTasks`）；而 conductor 驱动的 key **禁止**被窗口接管（接管即 `CLAIM_LIVE` ⇒ conductor 跳过 ⇒ 死锁）。⇒ 若 conductor 进程未运行或跑不动，**没有任何其他主体拥有重派权**，队列自然停在 2 天前的状态，`failed` 行永不重试。这解释 0 pending / 0 running 与"零派发"完全一致。
判别方法：确认该项目是否有 conductor/autopilot 进程在跑（`mw` 服务、conductor 日志/`_autopilot/auto-decisions.jsonl` 的最近时间戳），以及该进程最近一次决定是"无事可做"还是"派发被拒"。

**机制 M2：门禁版本偏移（本 key 引入风险）**
本 key 的门禁 `ENVELOPE_ENFORCE_SINCE`（T-09）位于**全局服务层** `packages/multi-workers/launcher.py`，而满足门禁所需的**注入**位于**每个项目的 framework 副本** `autopilot/dispatch.py`（`render_task_md`）。两侧是**两个版本域**：全局服务一升级就对所有尚未同步的项目生效。若项目副本是旧版（无注入、无 extras 段），则叠加 F-02（extras 判据对象错位）之后，**该 key 的每一次派发都会被 G-3 拒**（`spawned=[]` + 行 `failed` + `[launcher] envelope missing: …`）⇒ autopilot 表现为"整体瘫痪"，且**逐行表现为 failed 而非 pending**。
判别方法：该项目的 33 条 `failed` 行的 `worker.log` 中是否出现 `envelope missing`。

> 注：本仓尚未 cutover（T-08 未执行）⇒ 本仓当前运行的是**上一 key 的 bundle**；但 M2 的触发条件在 cutover 当天即成立，因此这笔账必须在本 key 内结清（AC-009/P-10）。

## 3. 已确认的相关事实（本 key 内）

- F-10（QG 发现，P3 但属同一根因）：**PM 手写派发风格过不了本 key 自己的门** —— 本 key 全部 14 行 `dispatched_at` 晚于边界，而手写 `task.md` 缺上下文语义 ⇒ cutover 后每次手写派发都会被拒。
- F-02（QG 发现，P1 一票否决）：extras 判据对象错位 ⇒ 合规卡也可能被 G-3 误拒（过拦），且 description 文字可满足卡未声明的 extras（欠拦）。**这就是 M2 的机制**。
- F-03（P2）：边界判定依据是**同手可写**的行内文本列，`created` 分支是死码 ⇒ 边界不可信。
- 告警措辞缺陷（`pm-orchestrator.ts:1201`）：对所有 alarm kind 硬编码前缀 `[mw] dispatch 已拒绝：`，包括纯可见性的 `out-of-scope` ⇒ 把 notice 显示为 refusal，掩盖真实拒绝。且该告警在 autopilot 下**按构造永不清空**（清空条件是 `switch_key`，而 conductor key 禁止接管）⇒ 告警疲劳。

## 4. 修复分工（本 key 内）

- **T-13（producer 侧，可与 T-12 并行）**：`autopilot/dispatch.py` 无条件产出**满足门禁**的 task.md（含 type extras），覆盖有卡/无卡合成/L3/repair/roadmap 全部路径；写入 producer 版本行以便服务层区分"旧 producer"与"真缺段"；新增「旧 producer + enforce ⇒ 可执行地证明瘫痪」回归用例（只读调用 `launcher._envelope_refusal`，不改 `launcher.py`）。
- **T-14（服务层侧，T-12 终态后派）**：`launcher.py` 消费 producer 版本行 —— 版本偏移 ⇒ **不静默零派发**：单行可见告警 + 明确升级指引 + 允许方式（服务层兜底注入，RQ-3 方案 C 混合），并保证不会因偏移使整个 key 的派发同时失效。
- **cutover（T-08）前置条件**：T-12 + T-13 + T-14 全部终态并复核；否则上线即瘫痪所有未同步项目。

## 5. 未定论 / 需人确认

- E2Feature 的 2 天零派发究竟属 M1 还是 M2，**尚未定论**（判别方法见 §2）。若为 M1，则本 key 的门禁并非该项目的直接原因，但 AC-009 仍然成立（门禁不得成为新的瘫痪源）。
- 该项目 675 done 可能意味着工作已收尾（无新任务可派）——若如此，"瘫痪"应改用"无作业可派 + 失败行无重试权"来描述。此点需用户确认。
