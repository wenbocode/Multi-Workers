# PM State: 派发任务卡门禁（mw-dispatch-card-gate）

- Phase: DONE
- Key: mw-dispatch-card-gate
- Claim-Id: WENBOZHOU-PC4:117296
- Created: 2026-10-12
- Updated: 2026-10-13 11:18
- Completed: 2026-10-13 11:18
- Baseline commit: 6c5189831
- 上游：mw-guard-form-hardening（DONE）的 T-20 实测事件 + `.agenticdoc/_incidents/dispatch-card-omission-20261012/README.md`

## 1. 立项依据（用户裁定）

- 用户指出的洞：**dispatch 派发实现型/任何任务时不要求卡片**，卡片既无格式要求也无检查 ⇒ 任务可能被错误派发
  （无写入面白名单、无验收判据、追溯链断裂；实测案例 T-20：卡片 `tasks/T-20-final-ci-and-heredoc-fixes.md` 不存在，worker 自行上报）。
- 用户裁定 (b)：另立本 key（mirror key 封存为 PAUSED）。
- 用户对范围的明确要求：**覆盖所有任务类型**（coding / review / research / vision / rag-research），
  且每张卡/每次派发都必须明确：**上下文（上下文/背景）、要求（要做什么、判据）、交付物（产物路径与形态）**。

## 2. 用户约束（绑定）

1. **隔离**：不写其他 key 的任何文件；对其他 key 只读。
2. **影响评估**：必须给出「改动面 → 消费者 → 影响 → 处置」。
3. **worker 产物自带状态**：报告须含实测命令 + 原始输出。
4. **所有类型**都要有上下文/要求/交付物（不是只 coding）。
5. PM 可读其他 key，但**不写、不重派**。

## 3. 阶段计划

- SPEC（当前）：RQ 并行取证（现有派发路径假设了卡存在吗 / 现有卡片语料的格式实况 / 门禁该落在哪一层）。
- DESIGN：DRQ 并行（最小格式契约、失败方向与逃生舱、与既有 `readTaskType` 单源的关系）。
- PLAN/TASKS → EXECUTE（改派发路径，注意属驻留服务 ⇒ 需 cutover 与冒烟）→ VERIFY（两轮 QG，新 task_key）。

## 4. 决策记录

### D-001（2026-10-12 16:10）立项、范围与目标

- key 名：`mw-dispatch-card-gate`。
- 目标（可判定）：
  - **G1 卡片强制**：所有类型的派发都必须有卡片；缺失 ⇒ **拒绝派发**并指名缺失路径。
  - **G2 三段必备**：卡片必须含**上下文 / 要求 / 交付物**三段且非空；缺项 ⇒ 拒绝并指名缺失段。
  - **G3 一致与可追溯**：`tasks/*.md` 卡片集合 ⊇ 本 key 已派发的 task_key 集合（不一致 ⇒ 检查变红）；每次派发记录卡路径 + 卡 sha256。
  - **G4 失败方向**：默认 **fail-closed**；例外必须显式声明并留审计（形态参照既有 `allow_foreign_write: true`）。
- 范围 **Out**：C-9 分发副本门禁（mirror key 的事）、上一 key 的守卫形态残余、OS 级隔离。
- 待决：G1/G2 的**强制点**在工具层（`dispatch_worker`）还是服务层（mw 队列消费前），由 RQ-3 的实测决定；
  改派发路径 = 改驻留服务 ⇒ 必须走 cutover（rebuild + restart + 冒烟）。

## 5. 下一动作

- 派发 3 个 SPEC RQ（并行，各写唯一证据文件）：现有派发路径的假设点、卡片语料格式实况、门禁落层与最小格式契约。

### D-002 设计总原则（用户裁定 2026-10-12）

- **投递优先**：机制第一职责是把正确、必要的**上下文 + 任务内容 + 交付格式**送到 worker；限制只是副产品（不是先把 worker 管起来）。
- **不设探索限制**：投递物是**种子**而非上界；worker 可启发式自行寻找上下文（全仓只读，含其他 key 只读），并在交付物记录「上下文来源清单」。写仍 fail-closed。
- **回收契约进本 key**：`output.md` 必备段 + `_workers.parallel` 状态判据与交付格式对齐（对治实测 3/4 实例「内容齐全却因占位段被判 needs-clarification」）。
- **review 不限制输入**：必填「审计目标/问题域」+「未覆盖面声明（必填）」；工具集含 bash 以便执行验证。
- **coding 改动历史必填**：trace 写入事件（机器事实）+ 报告改动清单（意图），回收时校验 清单 ⊆ 事件。

### D-003 cutover 预授权（用户裁定 2026-10-12）

- 用户裁定「可以 cutover」⇒ 本 key 实现落地后 PM **无需再次征询**：执行 `python -X utf8 packages/multi-workers/mw.py build --install --allow-dirty`、重建 `packages/coding-agent/dist`，并重启服务（`/mw restart`）与 pi 窗口（`/reload`）。
- 边界：cutover 属**实现完成后**动作；前置条件「源码 + 单测全绿」；cutover 前后各留运行期证据（一正例一负例）到 `evidence/runs/`。
- 依据：§8 P-01（驻留服务约束）。
- 2026-10-13 收口 PASS：质量门禁两轮裁定 —— 轮次一 T-11b FAIL（2 项 P1）→ T-12 修复；轮次二 T-17 PASS（无一票否决，12 项 P3 登记）；cutover 后运行期复查 T-23 PASS（本卡未跌 unlisted、判据未放松）+ T-26b PASS（全量 pytest 2 failed / 1744 passed = 恰两条既有基线；npm run check exit 0；真实越界仍红；C-31 运行期闭环 envelope_producer=agent-team-loop-pm@0.83.0；全局与 repo bundle 同源 5877E4FD3F035BDB1E3F26527191B754B680FDB5C9522B4F049097A17FAC669）。证据：evidence/quality-gate-report-20261012.md、achieved.md、evidence/incidents/roadmap-parse-paralysis-20261012.md
