# Achieved: mw-write-face-guard

- **Key**: `mw-write-face-guard`（前置 key；`mw-dynamic-concurrency` 依赖本 key DONE 才开并发，见 D-018）
- **时间**: 2026-10-14
- **一句话**: 把"写面声明"做成**机器可读载体 + 两通道同一判定 + 运行期真拦**，使"同一时刻同 key 同文件多写者对 = 0"从口号变成可测事实。

## 系统行为变化

1. **新增权威写面载体 `write_face:`（task.md 头）**：卡 envelope 的「写入允许面」经**同一渲染器**在两条派发通道落地——conductor `autopilot/dispatch.py::render_write_face_line` 与 PM `pm/ui-bridge.ts::mergeCardHeader`；含逗号条目自动走块列表形态（D-113：`parse(render(E)) == E`），两通道渲染逐字节相同。
2. **新增双语言交集算子**（`autopilot/write_face.py` + `shared/write-face.ts`），共享一份冻结语料（`test/fixtures/write-face-corpus.json`，v3：parse 23 + overlap 59，LF 归一化 `sha256=b39f8925…`）。**allow/refuse 决策两通道零分歧**：B3 端到端 82 行 × 5 字段 = 410 次对照 0 不一致，且两侧都与文档算法一致；base 对齐坑已量化（错对齐 4 处不一致 → 对齐 0）。
3. **派发期闸门（两条通道同形）**：判定与队列行写入在**同一把 `.mw/workers.lock`** 临界区内完成（AC-008/AC-014）；拒绝形状 `write-face-overlap` + `overlap-with:<task_key>` + 冲突样例 + `serial-only`，**零副作用**（不写队列行、不建/清理 taskDir）；未声明写面（D-003）⇒ 记审计 + serial-only（**不是**拒绝）；卡-less 内部派发豁免（避免永久 stall）。
4. **运行期闸门（`worker/worker-mode.ts`，D-007 IP-1b）**：`write`/`edit` 工具与 bash 都受判；面表**按角色类别化**（writeless 保持 research 历史面与 `packages/**` deny；writable 默认面 = 工作树根 + 跨 worker/框架隔离红线）；安装条件 `hasWriteTools || isShellRole`（`roadmap-writer` 这类写角色从**零闸门**变为有闸）。**D-115 载体收敛**：`write_face:` 权威，`write_scope:` 仅对 writeless 仍是声明面，双载体同时存在且不等 ⇒ **取交集（fail-closed）并写审计行**；不得新增第五载体。
5. **审计与可见性**：conductor → `.autopilot/timeline.jsonl`（`write-face-rejected`/`-overlap`/`-undeclared`）；PM → `_autopilot/auto-decisions.jsonl`（`kind:"write-face-refusal"`，复用既有 `recordDispatchAlarm`，best-effort）；运行期 → trace 的 `[WRITE_FACE]`（双载体）与 `[WRITE_SCOPE_SUMMARY]`。**PM 侧派发计数诚实化**：被拒任务不再计入 `queued`（原会污染 `dispatch-quota` 告警）。
6. **队列文件单写者（D-114）**：`WorkerStore.upsertWithinLock` 成为唯一行格式实现，删掉 PM 侧字节镜像；`upsert` = 取锁 + 调它。
7. **影响面（下游必须知道的既有断言反转）**：`mwds-t03` 的 VC-024 从"写角色不装闸"反转为"装闸且不误拦"；`autopilot-read-scope` 的 `interceptorCount` 期望 1 → 2（coding 现在同时装读面与写面）；`dispatch-card-injection` 的 byte-exact 头多一行 `write_face:`；`[WRITE_SCOPE_SUMMARY]` 现在每个被守卫角色各一行。
8. **落地上线的唯一前置**：`dist/**` 未重建（见遗留 1）。

## 验证口径（本 key 自证）

- 双侧算子/闸门套件（PM 自跑）：Python `test_write_face.py` 130 passed、`test/test_write_face_dispatch.py` 29 passed、`test/test_write_face_e2e.py` 7 passed；TS `write-face.test.ts` 109、`write-face-pm-gate.test.ts` 22、`write-face-runtime.test.ts` 18、`mwds-t03` 63、`write-face-e2e.test.ts` 8（全部为 PM 亲自复跑，不采信 worker 自述）。
- 反证：AC-005 的"多写者对 = 0"在绕过闸门直写队列行后复算为 **1 对** ⇒ 0 来自检测器而非空集；AC-013 假阻族 14 条两通道全放行、真写族两通道全拒；PM 另用探针确认面内目录目标（`rm -rf <面内目录>` 家族）**不被误拦**。

## 遗留

| # | 遗留 | 明确去向 |
|---|------|---------|
| 1 | **`dist/**` 未重建** —— 运行期闸门/渲染只在 `src` 生效；`packages/multi-workers/dist/extensions/agent-team-loop.js` 已被其它 session 改动（mtime 2026-10-14 08:38:48）并导致 `mwds-t23` req-4 的 sha 断言红。`AGENTS.md` 禁止 PM 自行 `npm run build`。 | **交给用户**：上线/合入前重建两侧 dist 并同步该 sha（避免与其它 session 的 dist 写权相撞） |
| 2 | 存量卡迁移脚本（把 419 份存量任务书批量渲染 `write_face:`）未做 | **接受不处理**：D-003（未声明不中断）+ D-115（writable 无 `write_face:` 时回落 `write_scope:`）保证不迁移也可用；若将来要清空 legacy 载体再立 key |
| 3 | `write_face.py::globs_overlap`（数组变体）无生产调用方、未做 parity 覆盖 | **接受**：唯一调用点恒 1×1；一旦出现多元素调用必须同族化（记于 `plan.md` §7.1） |
| 4 | 运行期包含判定是**重叠**语义（单个具体目标时等于成员判定，正确）；glob 型目标只要求有交集而非子集 | **接受（暴露面被限）**：生产路径上 glob 目标走 `allow-unknown`（只审计不拦）；建议后续 key 显式裁定 subset vs overlap |
| 5 | `write-face-refusal` 审计未做 session 去重（长期被拒任务每轮扫描各落一行） | **接受**：与 conductor `_write_face_audit` 每次尝试一行同形；若要"每 session 一行"需把去重集并入 `DispatchScanOptions` |
| 6 | 运行期 base/junction 的 realpath 归一未做（极端情况下 junction cwd 可能 fail-closed 误拦） | **归 `mw-worktree-junction-guard` key**（该 key 已 DONE 覆盖该族） |
| 7 | **同 task 重复激活缺陷 RF-1..RF-4**（激活期唯一性闸 / `writeRunState` 前置条件与撕裂状态 / 产物写所有权 / ≥2 次激活告警）—— 本 key 期间实测到 13 次重复激活污染同一产物 | **需立新 key**：证据已固化在 `.agenticdoc/_scratch/evidence/wfg-i03-duplicate-activation-20261014.md` + `_pitfalls.md` P-034（含未解问题与捕获仪器设计） |
| 8 | **PM 读回推送 scope 缺口**（terminal worker 结果不推送：`notified.add` 早于 owner 门 + 开窗基线 + C3 静默），本会话 3 次自然复现 | **需立新 key（建议 `mw-readback-delivery-scope`）**：证据在 `.agenticdoc/_scratch/evidence/readback-push-scope-gap-20261014.md` + 可复跑探针 |
| 9 | `evidence-requirement.md` / `evidence/baseline/` / `evidence/runs/` 三个目录在本 key **不存在**（本 key 的证据以 `evidence/<task>.md` + PM 复跑为准） | **接受并记入质检报告 ⚠️**：本 key 的 AC 证据链是"每卡证据文档 + PM 亲自复跑"，不是 runs 目录制 |
| 10 | 拒绝分支 `reason` 串的引号边界（Python `{raw!r}` 对含单引号条目会换双引号） | 见 `wfg-i14-reject-reason-parity` 结论：能对齐则对齐，不能则显式记为有界差异并给原始输出 |
