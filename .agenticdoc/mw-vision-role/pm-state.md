# PM State: mw-vision-role

## 1. Snapshot
- Key: mw-vision-role
- Phase: DONE
- Next Action: 收波 1 结果（T-03/T-04/T-05/T-08/T-10）→ 派 T-06（依赖 T-04+T-05）
- Started: 2026-09-26 16:38
- Updated: 2026-09-26 18:21
- Completed: 2026-09-26 18:21

## 2. Task Status

（波次见 `plan.md` §1.2；状态：pending / running / done / blocked）

| 任务 | 波 | 状态 | AC/VC | 备注 |
|---|---|---|---|---|
| T-01 Python 注册 | 0 | done | AC-004/019 | 已落盘 `mw_common.py:138/152` + `dispatch.py:110`；VC-004/VC-019 绿；卡缺陷 3 处已更正 |
| T-02 TS 注册 | 0 | done | AC-004/005 | 已落盘两表（vision 末位/同序白名单）；176/176 绿；worker-mode.ts 他人改动未触碰（R1） |
| T-05 images 写侧 | 0 | done | AC-007/009 | `ui-bridge.ts` 头部收敛为单一 `headLines` 来源（`:1044-1047`）；零字节与 golden VC-010 绿；入口未传值 |
| T-03 parity 重冻 | 1 | done | AC-004/005/019 | 4 文件重冻/新增；Python 24 passed、TS 177 passed；对照：删新断言后 `vision: "coding"` 无人发现（洞真存在）、删既有键即红 |
| T-04 能力函数 | 1 | done | AC-008 | `dispatch-models.ts:199-271` 能力段（10 条 unknown 早退）；9/9 单测绿；对照变红 |
| T-06 门禁接线 | 1 | done | AC-006/008 | `ui-bridge.ts` 门禁段 + tool `images` 参数 + `/worker --images`；8/8 新用例，既有 177/177 无新增红；两条对照变红 |
| T-08 Py 渲染 | 1 | done | AC-009 | `dispatch.py` `images` 参数（真值判断）；零字节+行序用例自包含（冻结副本）；4 处 golden 无需重冻 |
| T-10 Python 探针 | 1 | done | AC-010/013 | `mw_common.py` 探针段（`MODEL_PROBE_TIMEOUT_S=3.0`）；12 例 seam 测试；真实三态 `yes no unknown`（0.91s）；两条对照变红 |
| T-07 auto-route | 2 | done | AC-016/017 | `ui-bridge.ts` auto-route 段（11/11 新用例、门禁 8/8 无回归、既有 177/177）；对照：改写 `type:` ⇒ 5 红、放宽 vision 判定 ⇒ 红 |
| T-09 worker 兜底 | 2 | done | AC-011 | `worker-mode.ts` `TaskMeta.images` + `session_start` 兜底（4/4 新用例、177/177、10/10 白名单回归）；两条对照变红 |
| T-11 set 拒绝 + force | 2 | done | AC-001/002/013 | `mw.py` set 段 + `--force`（仅 vision）；行为表 6 行均有用例；48 passed；另补齐 `test_dispatch_models.py` 的陈旧 TS 镜像 `_TS_ROLE_BY_TYPE`（T-01 parity 漏项） |
| T-13 PM 知情面文本 | 2 | done | AC-014 | 四处文本 + L0 token 集合断言（`surfaces=4 token_set_ok=true`）；对照：漏 `PARALLEL_PROTOCOL` ⇒ 红、漏 `rag-research` ⇒ 红 |
| T-12 可见面三态列 | 3 | done | AC-010/015 | 4 层数据流全落（JSON 真源/文本/TS 渲染/show 列）；PM 复现 79 passed、177 passed |
| T-15 doctor 告警收窄到 vision | 3.5 | done | AC-010 | 一行收窄（`role_name != "vision"`）+ 新回归；真实仓库测试：`images=no` suggestion 4→0，`images` 列仍全角色；80 passed |
| T-14 验证收口 | 4 | done（带 2 BLOCKER） | AC-012 | 证据文档 701 行已落盘；L2-2 真视觉通过；发现 tsgo 4×TS2741 + VC-003/VC-007 缺证 + bundle 除旧 |
| T-17 修 `description` 必填 | 4.5 | done | AC-012 | 已落地；PM 复验 `tsgo rc=0`；对照 3 条均红（T-17 还纠正了卡内对照①的预期错位） |
| T-18 补 VC-003/VC-007 缺证 | 4.5 | done | AC-003/007 | 已落地；PM 复验 `[VERIFY] VC-003` / `[VERIFY] VC-007` 行已在（53 passed / 9 passed） |
| T-19 证据刷新 | 5 | done | AC-012 | 已落地（附录 A）；PM 已复验 `tsgo rc=0` + VC-003/007 行 |
| T-16 独立 QG review | 5 | done（用户指定） | 全部活跃 AC | `PASS-WITH-NITS`、`acs_total=18 acs_pass=18 invariant_violations=0 blockers=0`；自算矩阵 + 脚本逐元素镜像 + 10 例对抗 + 自做变异 |
| T-15…T-19 | 3.5-5 | done | — | 执行期追卡：T-15（doctor 告警收窄）、T-17（`description?`）、T-18（补 VC-003/007 证据）、T-19（证据刷新） |

## 3. Evidence Ledger

- E-01（2026-09-26，spec 期）5 份 `spec-*.md` 调研：类型/角色管道、门禁挂点、`images:` 头读侧、视觉链路与候选、PM 知情面。映射：顶层目标「按类型选视觉模型」+「框架主动感知」。
- E-02（2026-09-26，design 期）5 份 `design-*.md` 调研：Python 探针契约（含实测 `pi --list-models` 31 行/0.86s/缺失⇒unknown）、TS 挂点与签名、`images:` 写侧与 golden 断言形态、doctor/show 字节契约（`ui.notify` 不进 agent 上下文）、验证可行性（AC-006..017 实为 L1）。
- E-03（2026-09-26）`pi --list-models timi deepseek-v4-flash-vision-exp` rc=0，`images=yes`；`timi/glm-5.3` `images=no` —— 选定值可用且能区分三态。
- E-04（2026-09-26）`test_autopilot_readcap_injection.py::test_baseline_left_end_bound` 本机现状即红（冻结副本 sha256 ≠ git HEAD）——基线噪声，不得归因本 key。
- E-05（2026-09-26）`git status --porcelain`：`worker/worker-mode.ts` +165/-13 等属**其他会话**未提交改动——本 key 编码前需重锚行号。
- E-06（2026-09-26）新增基线噪声（**非本 key**）：`test_autopilot_readcap_injection.py::test_existing_regression_files_untouched` 因其他会话改了 `test_autopilot_config.py`（工作区 sha ≠ HEAD）而红；同期 `test_baseline_left_end_bound` 仍红（E-04）。另：`dispatch.py` 的签名被其他会话加了 `worker_timeout_min`，故 readcap 的 `extra` 期望同时含 `images` 与该参数（跨会话耦合，已在 T-08 output 留痕）。
- E-07（2026-09-26）T-09 过程事故 + PM 复核：该 worker 用 PowerShell `Get-Content/Set-Content` 改事件名时把 `worker-mode.ts` 的中文注释 GBK 损坏，随后从会话 read 记录重建。PM 独立复核：文件 UTF-8 合法、**U+FFFD = 0**、HEAD 的 10 条 CJK 注释行全部逐字仍在、盒线字符 U+2500 = 411、其他会话的 watchdog/idle-kill 代码（`IDLE_KILL`/`resolveToolIdleMs` 等）完整 ⇒ **未丢他人改动**。教训：Windows 下禁用 PowerShell 文本往返改源码（新坑，已记此）。
- E-08（2026-09-26，PM 抽检）`python -m pytest test_dispatch_models.py test_common.py test_autopilot_dispatch.py test_mwpp_collection_parity.py test_autopilot_readcap_injection.py test_rag_phase.py -q` ⇒ **164 passed, 2 failed**，两红均基部噪声（E-04/E-06）⇒ 已完成任务的 Python 侧无交叉回归。
- E-09（2026-09-26，PM 复核 T-03 重冻「只增不删」）：`git diff -U0` 显示 `test_mwpp_collection_parity.py` 仅删了 **2 行陈旧计数注释**（标题 `10-key`、正文 `6 keys`），无任何断言被删；`test_autopilot_l0.py` 删除行 = **0**（纯新增 6 行）；PM 重跑三文件 ⇒ **24 passed**。T-03 的对照 ① 尤其关键：删掉它新增的 TS 断言后，`roleForTaskType("vision")` 返回 `"coding"` 而 **旧 176 用例全绿** ⇒ 证明该洞真实存在（TS 半边映射此前无任何覆盖）。
- E-10（2026-09-26，PM 真实端到端，AC-010/AC-015 强证据）：本仓库执行 `python mw.py model show --project H:/git/Multi-Workers` ⇒ 5 条角色行均带 `images=`（main/coding/research = `timi/deepseek-v4.1-flash images=no`、review = `timi/glm-5.3 images=no`、vision = `(unset) → … [window] images=no`，**真实探针路径**，非注入）；`python mw.py doctor --project … --json` ⇒ `dispatch.images` 全角色齐全、`healthy=true`、`issues=[]`、`rc=0`（AC-010 退出码）⇒ 与 T-12 断言一致。
- E-11（2026-09-26，PM 真实端到端发现偏差 ⇒ 已开 T-15）：E-10 的 doctor 输出里有 **4 条** `images=no` suggestion（main/coding/research/review 各一），而 AC-010 只要求对 **`vision`** 角色告警。纯文本角色本就不需要看图能力（图任务由 auto-route / `type: vision` 承担）⇒ 假阳性 + 错误处方（“or give 'coding' an image-capable model”）+ 常驻噪声。已派 T-15 收窄，并新增「其他角色静默」回归断言。
- E-12（2026-09-26，独立 QG）：`evidence/reviews/qg-review-mw-vision-role-20260926.md` ⇒ `QG verdict: PASS-WITH-NITS`、`acs_total=18 acs_pass=18 invariant_violations=0 blockers=0`；其**自算** AC/VC 矩阵、脚本 import 两侧表逐元素比对、10 例对抗式反例、自做变异验证测试非空洞性；报 N-1…N-7。
- E-13（2026-09-26，PM 复跑）：T-17 后 `npx tsgo --noEmit` rc=0 零输出（原 4×TS2741 消失）；`rag-required` 12 passed、四个 agent-team-loop 套件 201 passed。
- E-14（2026-09-26，PM 复跑）：T-18 后 `[VERIFY] VC-003: source=config:vision task_override=task`（`test_dispatch_models.py` 53 passed）与 `[VERIFY] VC-007: queue_delta=1 images_line=yes order_ok=true`（`vision-gate` 9 passed）——两项缺证闭环。
- E-15（2026-09-26，T-19 附录 A）：Python 触达面 203 passed / 2 failed（E-04/E-06）、TS 201 passed、`tsgo rc=0`、biome scoped 9 文件与宽面 317 文件 rc=0、真实仓库 `mw model show` 5 行带 `images=`、`mw doctor` rc=0 + suggestion `[]`；新判定 `[VERIFY] VC-012: scoped_tests=green check=green` 取代 T-14 的 `check=FAILED`。
- E-16（2026-09-26，QG 前置门禁校正）：① `ac_fingerprint` 口径统一为 `workflow-quality-gate.md` 的 id-set 算法 ⇒ `918de4e2b149`（旧 6857a77db10f 是 §3 区块文本口径，对 AC-010 的 `[REVISED]` 注敏感；AC 集合未变）；② 补建 `evidence/baseline/baseline-mw-vision-role-20260926.md`（前置门禁要求非空）。

## 4. Hypothesis Queue

- H-01（待验，R13）：真进程 `[IMAGE-CAP]` 退出码无现成基建 ⇒ T-14 人工跑一次真派发验证。
- H-02（待验，R12）：全量 vitest 时 Windows 89 基线噪声可能掩盖本 key 回归 ⇒ 以触达面命令为准。
- H-03（已观察，R14）：worker 会对同一文件做 mtime 轮询自保（T-03 实测对 `worker-mode.ts` 轮询）⇒ 极端情况下两个 worker 互等，靠 wall timeout 兑底；后续派卡可显式写明"该文件当前无其他 worker 持有，无需轮询"。
- H-04（已证伪）：T-06 报告 `worker-mode.ts` 非法 UTF-8（biome INTERNAL）⇒ PM 实测工作区解码 OK（56613 B）、HEAD 亦 OK、单文件 biome 干净 ⇒ 那是 T-09 并发写入期间的**瞬时中间态**；后续遇同类报错先重跑一次再定级。
- H-05（**已确认**）：Windows 下 worker 用 PowerShell `Get-Content/Set-Content` 改源码会 GBK 损坏 UTF-8 中文注释（T-09 实测）⇒ 派卡显式禁 PowerShell 文本往返（用 `edit`）；T-15/T-17/T-18/T-19 全程遵守、无再发。
- H-01（**已确认**）：真进程 `[IMAGE-CAP]` 验证可行且**零 token**（源 builtin + `PI_WORKER_TASK`：`[IMAGE-CAP] … declared=images:yes`、`rc=1`、`trace.log` 有 `[ERROR]`）；L2-2 真视觉亦通过（`red square`）。
- H-06（**已确认**，通用教训）：宽容断言（`any(...)` / 子串）会掩盖**范围溢出**类缺陷——T-12 的 doctor 告警对**所有** `images=no` 角色都发，单测全绿，真实仓库一次跑出 4 条常驻噪声 + 错误处方。⇒ 凡“影响用户可见输出”的改动，收口必须包含一次**真实工程执行**。
- H-07（**已确认**）：VC 编号跨 key 冲突（`VC-003`/`VC-007` 已被 goal-autopilot 占用）会让“缺证”看起来像“有证” ⇒ grep 证据行必须同时限定 key 目录/测试文件。

## 5. Decisions

- 用户拍定（2026-09-26，第二轮）：类型名 `vision`（同名）；模型值 `timi/deepseek-v4-flash-vision-exp`；`--force` 逃生口给予；AC-018 作废；conductor 允许派发；镜像与探针按推荐（追加末尾 / P1 解析表格 / 两侧都加 `images=` 列）；PM 自身看图不做。
- 设计期反向修正（2026-09-26，已留痕于 spec）：① AC-010 `issue → suggestion`（doctor 退出码由 `summary.healthy` 决定，落 issues 必致退出 1，与“三情形退出码 0”互斥）；② §4 auto-route 边界注 → **只换模型不改 `type:`**（改 `type` 会变更工具白名单 ⇒ 只读任务被隐式提权；且原注与锁定 AC-017 互斥）。
- 设计决策 D-001…D-012 见 `design.md` §1/§10；A 章已追写进 `key-decision.md`。
- 测试语料重冻授权（用户“确认”）：`agent-team-loop.test.ts:5029-5031`（D-011 方案 A 必需）；其余重冻均为新增条目。
- 派卡纪律：每个编码任务新建自己的 TS 测试文件；共享测试文件仅 T-03/T-12 触碰且分处波 1/波 3。
- 卡缺陷更正（2026-09-26 实测，已回写 T-01 卡）：① `REGISTRY["vision"]` 值是 frozen dataclass `DispatchType` ⇒ 取证必须属性访问（下标必 `TypeError`）；② `dispatch()` 真实签名需 `project_root/owner/stem` 三个位置参数；③ `TASK_TYPE_TO_ROLE` 追加前为 9 键（非 13）。
- **D-013（PM 决策 @ 2026-09-26，实现期补定）**：`images:` 头的写侧取值规则：显式 `yes` ⇒ `images: yes`；显式 `no` ⇒ `images: no`；**自动检测命中且未显式声明** ⇒ 也写 `images: yes`（否则 AC-011 的 worker 兜底盖不到自动检测出来的任务，会出现"派发面判定需要图、worker 不知情"的缝）；两者皆无 ⇒ 零字节不写。已写入 T-06 派卡。
- **写面隔离（防并行踩踏）**：`test/extensions/agent-team-loop.test.ts` 在 T-03 在飞期间对 T-06 只读（T-06 测试全部写进自己的新文件）；`ui-bridge.ts` 为五段串行链（T-05 → T-06 → T-07 → T-13 → T-12），同一时刻只允许一个 worker 持有。
- **VC-017 期望串修正（实现期，已回写 `design.md` §7 与 `evidence-requirement.md`）**：`type: vision` 的源角色 == 目标角色（AC-004）⇒ 自动路由逻辑不可能触发（同一值不可能既判 `no` 又判 `yes`）；原期望 `routed=2` 改为 `type_unchanged=true effective_vision=2 auto_route_fired=1`。VC-017 语义本身（“均改到 vision 模型 + `type:` 不变”）**未改**，仅计数口径修正；拒绝写假来源 `auto-route: vision -> vision`（测试驱动的语义污染）。
- **T-15 追卡（执行期自查）**：真实仓库实测发现 T-12 对**每个** `images=no` 角色发 doctor suggestion（4 条常驻噪声 + 错误处方），而 AC-010 只管 `vision` ⇒ 一行收窄 + 新回归；`dispatch.images` 全角色保留（AC-015）。
- **T-17/T-18 追卡（T-14 阻塞）**：① `description` 必填打破他人 key 语料 `test/suite/rag-required.test.ts`（tsgo 4×TS2741）⇒ 改可选 + `?? ""`；② VC-003/VC-007 无 `[VERIFY]` 行 ⇒ 补直接断言。两条均经 PM 独立复跑。
- **独立 QG（用户指定）**：T-16 以 `type: research` 派发（有 bash 可重跑、无 write/edit 改不动源码；`type: review` 无 bash 无法独立验证）；结论 `PASS-WITH-NITS`、0 blocker。
- **QG 结论：⚠️ 有条件通过（3 项验证欠债）**：⚠️-1 `npm run check` 字面（写模式会改他人在飞文件）未跑，已逐条跑只读组件全绿；⚠️-2/3 活窗口 bundle 陈旧 ⇒ TS doctor 渲染与活窗口 `[IMAGE-CAP]` 路径待 `/mw build` + `/mw restart` 后复验。N-1…N-7 登记为遗留，均不改变任何 AC 行为判定。
- **T-11 越界声明（已接受）**：T-11 额外把 `test_dispatch_models.py` 的陈旧 TS 镜像 `_TS_ROLE_BY_TYPE` 补上 `"vision"`（T-01 落键时该文件不在 T-03 写面内 ⇒ 无人覆盖）；改动在该卡写面文件内，接受。

## 6. Turn End Records

- 轮次 1（2026-09-26）：顶层目标 = 把“vision 角色 + 能力门禁”从需求推到可执行。新增证据 E-01…E-05。假设 H-01/H-02 未证伪。无已 done 的 task 需重开（尚未进入 EXECUTE）。阻塞点：无（D1..D5 全绿）。下一动作：写 plan.md + 14 张卡 → advance execute → 按波派 worker。
- 轮次 N（2026-09-26 18:55，收口轮，9 问）：
  1. **顶层目标**：把「PM 能主动感知并调用可读图的视觉角色」从实现推到**可交付验收**（含独立质检与证据闭环）。
  2. **新增证据**：E-10…E-16（真实仓库 show/doctor、doctor 告警溢出、T-16 独立 QG、T-17 后 `tsgo rc=0`、T-18 两条 `[VERIFY]` 补齐、T-19 附录 A 全量复验、QG 前置门禁两项校正）。
  3. **假设更新**：H-01 确认；H-05 确认；新增 H-06/H-07 均确认（见上）。
  4. **需重开的 done task**：无。T-14 报出的两个 BLOCKER 分别由 T-17/T-18 闭环并经 PM 独立复跑；T-19 已把 `check=FAILED` 判定正式取代。
  5. **阻塞点**：无阻塞；有 3 项**验证欠债**（⚠️-1 `npm run check` 字面写模式未跑；⚠️-2/3 活窗口 bundle 陈旧 ⇒ TS doctor 渲染与活窗口 `[IMAGE-CAP]` 路径待 `/mw build` + `/mw restart` 后复验）。
  6. **需新增/拆分 task**：无需（本 key 任务已闭）。欠债两项需**用户授权**才能执行（`/mw build` 会改写全局扩展目录）。
  7. **下一轮首要动作**：用户拍定 `/mw build` + `/mw restart` 后复验 ⚠️-2/⚠️-3；随后提交本 key 改动（需用户指示）。
  8. **是否已写入 pm-state.md**：是（本轮记录 + E-10…E-16 + H-06/H-07 + 决策）。
  9. **可提炼 pattern**：是（H-06：“宽容断言掩盖范围溢出 ⇒ 收口必须真跑一次”；H-07：“跨 key 证据编号冲突”）。已登记于 Hypothesis Queue，供 `_pitfalls.md` 提炼。

## 7. Process Log

- 2026-09-26 16:38 key 创建；16:45 spec.md 初稿；spec 期 5 张调研卡（RQ-1..RQ-5）全 done 并吸收。
- 2026-09-26 17:00 用户 spec 评审通过 → `🔒 AC Locked`；`advance_phase spec`。
- 2026-09-26 17:05 design 期 5 张调研卡（D1..D5）全 done 并吸收；design.md 定稿（D-001..D-012/19 VC），mermaid 门禁 PASS，AC→VC 覆盖 19/19。
- 2026-09-26 17:11 生成 `evidence-requirement.md`（ac_fingerprint `6857a77db10f`）→ `advance_phase design` → PLAN。
- 2026-09-26 17:20 plan.md + tasks/T-01…T-14 落盘（按文件边界分 5 波，最大并行度 5）。
- 2026-09-26 17:22 波 0 派发 T-01/T-02/T-05 → T-01、T-02 done（T-01：`mw_common.py:138/152` + `dispatch.py:110`，VC-004/019 绿；T-02：两表落盘 176/176 绿），二者均带非空洞对照。
- 2026-09-26 17:28 波 1 派发 T-03/T-04/T-08/T-10（T-05 仍在飞，并发 5）。
- 2026-09-26 17:32 T-05 done（`headLines` 单一来源，零字节 + golden VC-010 绿）；波 2 的 T-09 提前派发（仅依赖已 done 的 T-02）。
- 2026-09-26 17:36 T-04 done（能力段 `:199-271`，9/9 绿，对照变红）→ 依赖已齐，派发 T-06（并发 5：T-03/T-06/T-08/T-09/T-10）。
- 2026-09-26 17:42 T-10 done（探针段 + 12 例 + 真实三态，对照变红）→ 派发 T-11（并发 5：T-03/T-06/T-09/T-11 + 待收 T-08）。
- 2026-09-26 17:48 T-08 done（`images` 参数真值判断，零字节/行序用例自包含，4 golden 免重冻）；新增基线噪声 E-06。已 done 8/14，在飞 4（T-03/T-06/T-09/T-11）；T-07/T-13 等 T-06，T-12 等 T-11+T-13。
- 2026-09-26 17:24 T-11 done（set 段 6 行为 + `--force`，48 passed，两条对照变红）；T-12 的 T-11 依赖解除。
- 2026-09-26 17:27 T-06 done（门禁 8/8 新用例 + 既有 177/177 无新增红）→ 派发 T-07；PM 核实 `worker-mode.ts` UTF-8/biome 均正常（H-04 证伪）。在飞 3（T-03/T-07/T-09）。
- 2026-09-26 17:33 T-09 done（`[IMAGE-CAP]` 兜底 4/4 + 177/177 + 白名单回归 10/10）；PM 复核其 GBK 重建未丢他人改动（E-07）；PM 抽跑 Python 触达面 164 passed/2 failed（均基部噪声，E-08）。
- 2026-09-26 17:40 T-03 done（parity 重冻只增不删，PM 复核 E-09）；已 done 10/14，在飞仅 T-07。
- 2026-09-26 17:47 T-07 done（auto-route 11/11、门禁 8/8、既有 177/177，两条对照变红）→ 发现并裁定 VC-017 期望串缺陷（`routed=2` → `effective_vision=2 auto_route_fired=1`），已回写 design/evidence-requirement/T-07 卡；随即派发 T-13。已 done 11/14，在飞 1（T-13）；剩 T-12、T-14。
- 2026-09-26 17:52 T-13 done（VC-014 四处文本 + L0 集合断言，对照两条均红）→ 派发 T-12（最后一张编码卡）。
- 2026-09-26 17:58 T-12 done；PM 独立复现 `79 passed` / `177 passed`，并做真实端到端（E-10）：`mw model show` 5 行均带 `images=no`、`mw doctor --json` 的 `dispatch.images` 齐全 + `healthy=true` + `rc=0`；但发现 suggestion 对**所有**角色告警（AC-010 只管 `vision`）⇒ 新增 T-15 修复卡并派发（E-11）。
- 2026-09-26 18:04 T-15 done；PM 独立复现：真实仓库 `img_suggestions = []`、`images` 仍含 4 角色、`rc=0`，`80 passed`；对照（去掉收窄）⇒ 新断言红。⇒ 派发 T-14（最后一张卡，验证收口）。
- 2026-09-26 18:16 T-14 done（带 2 BLOCKER + 1 证据缺口），PM 已独立复现其中最关键的两条：
  - **B1** `npx tsgo --noEmit` rc=2，**4 条 TS2741 全在** `test/suite/rag-required.test.ts:177/182/187/191`（属性 `description` 缺失）。该文件 `git status` 显示对 HEAD **零改动** ⇒ 本 key 的 T-05/T-06 把 `description` 声明为必填所致（T-09/T-12 曾误判为既有/他人）。
  - **B2** 全局 bundle `~/.pi/agent/extensions/agent-team-loop.js` 早于 T-09（grep `IMAGE-CAP` = 0）⇒ 运行时遮蔽 repo 源 builtin，L2-1 走 bundle 打不到本 key 代码（`-ne` 隔离源 builtin 后完全符合预期：`[IMAGE-CAP] … declared=images:yes`、`rc=1`）。属**部署陈旧**（`mw doctor` 已在报 “extension bundle older than source”），非代码缺陷 ⇒ 待用户决定 `/mw build`。
  - 证据缺口：VC-003 / VC-007 的 `[VERIFY]` 行全仓 grep 0（编号在**其他 key** 已被占用，含义不同）。
  ⇒ 并行派发 T-17（`description?:` 可选化）与 T-18（补 VC-003/VC-007 证据），写面无重叠。
- 2026-09-26 18:22 T-17 done（PM 复验 `tsgo rc=0`、`rag-required` 12/12、四套件 201/201）；T-17 主动纠正卡内对照①预期错位（可选化后缺失安全网落在调用点 TS2345，而非测试文件的 4 条 TS2741）—— 采纳。
- 2026-09-26 18:24 T-18 done（PM 复验 `[VERIFY] VC-003` 53 passed、`[VERIFY] VC-007` 9 passed；三条对照均红后还原，`ui-bridge.ts`/`test_dispatch_models.py` sha256 与改前一致）⇒ 派发 T-19（证据刷新）。
- 2026-09-26 18:32 T-19 done（附录 A 已追加重证；`tsgo rc=0`、Python 203 passed / 2 failed（E-04/E-06）、TS 201 passed、真实仓库 5 行 `images=` + suggestion `[]` + rc=0；新判定行取代 T-14 的 `check=FAILED`）⇒ 按用户要求派发 **T-16 独立 QG review**（`type: research`：拥有 bash 可独立重跑，无 write/edit 改不动源码；禁信 PM 结论）。
- 旁注（非本 key）：`.mw/window-model` 已被用户改为 `timi/deepseek-v4-flash-vision-exp`（`mw model show` 显示 `vision: (unset) → … [window] images=yes`）。
- 2026-09-26 18:06 **用户要求：收口阶段单独派一个 review worker 做 QG** ⇒ 已起草 `tasks/T-16-quality-gate-review.md`（独立审查方：自算 AC/VC 矩阵、逐元素核验镜像不变量、门禁顺序与 fail-open、改动面/核心零改动、测试非空洞性抽检、对抗式反例、重跑 PM 证据）。
- 2026-09-26 18:40 T-16 done ⇒ 独立结论 `PASS-WITH-NITS`、`acs_total=18 acs_pass=18 invariant_violations=0 blockers=0`；它自算矩阵、脚本 import 两侧表逐元素比对、做了 10 例对抗式反例与一次自变异；报 N-1…N-7（均不阻塞）。
- 2026-09-26 18:50 收口：校正 `ac_fingerprint` 口径（E-16①，`918de4e2b149`）+ 补建 `evidence/baseline/`（E-16②）⇒ 写 `evidence/quality-gate-report-20260926T1850Z.md`（46 问：44 充分 / 3 验证欠债 / 0 无证据 ⇒ ⚠️ 有条件通过）⇒ 写 `achieved.md`（系统行为变化 9 条 + 遗留 8 条）⇒ `advance_phase done`。
