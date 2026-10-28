# Quality Gate Report: mw-write-face-guard

**时间**: 2026-10-14T07:05Z
**触发**: Stage 完成（EXECUTE 全部执行卡终态吸收完毕，DONE 前合入门）
**范围**: 全量（AC-001..AC-014 + VC-001..VC-008 / VC-024）
**判据**: 本 key 的证据形态 = 「每卡 `evidence/<task>.md` + PM 亲自复跑（P-025：不采信 worker 自述）」

---

## 0. 前置门禁核查（如实披露偏差）

| 检查项 | 结果 | 说明 / 去向 |
|--------|------|------------|
| spec.md 存在 AC 编号 | ✅ | AC-001..AC-014（14 条） |
| design.md 存在 VC 编号 | ⚠️ 偏薄 | VC-001..VC-008 + VC-024（9 条）；本 key 的决策面实际由 **D-001..D-009 + D-111..D-115** 承载（design.md），AC 与 VC 的一一映射矩阵**未在建期建立** |
| AC→VC 映射覆盖 100% | ⚠️ 不成立 | 见上；本报告改以 **Q-AC-xxx 为主清单**、Q-VC-xxx 作补充，使每个 AC 都有独立证据行 |
| `evidence-requirement.md` 存在 | ⚠️ 不存在 | 未补造（该文档是 design Step 6 的产物，事后补写等于伪造当时判据） |
| ac_fingerprint 一致 | ⚠️ 无记录 | 同上（无 evidence-requirement.md 即无指纹） |
| `evidence/baseline/` 非空 | ⚠️ 不存在 | 本 key 的基线写在每卡 `evidence/*.md` 的"基线 → 实测"对照里 |
| `evidence/runs/` 有 `[VERIFY]` 日志 | ⚠️ 不存在 | 本 key 用 PM 亲跑的原始命令输出（见 §1）代替 runs 目录 |
| 每个 task 有非空 ac_refs/vc_refs | ⚠️ 部分 | 19 张卡中 9 张有 ac_refs；`T-W-D1/D2`、`T-W-I01/I02/I04/I05/I06/I07`、`T-W1/W2/W3` 为空（D 系列调研/设计卡与算子基建卡） |

**PM 欠债登记**：以上 5 项问题级之外的流程偏差**不阻断**本报告结论（它们影响的是"证据的归档形态"，不影响"证据是否存在"），已记入 `achieved.md` §遗留第 9 条；若框架要求补齐，需为"evidence-requirement.md / baseline / runs 目录"单独立流程 key，不在本 key 事后编造。

---

## 1. 问题清单与核查结果

### 1.1 来源 A：spec.md AC（Q-AC-001..014）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | 写面被解析为机器可读结构，解析失败给稳定 refusal code 且零副作用 | ✅ 充分 | 算子 `autopilot/write_face.py` + `shared/write-face.ts`（语料 parse 23 行）；`test_write_face.py` 130 passed；`write-face.test.ts` 113 passed；零副作用：`test/test_write_face_dispatch.py` 的目录快照断言 + `dispatch.py` `:1435` 取锁在 `:1461/:1462` task.md 之前 | 两语言同语料同判 |
| Q-AC-002 | 与同 key 在飞 worker 写面有非空交集时拒绝，给 `overlap-with:<task_key>` | ✅ 充分 | 语料 overlap 59 行；B3 双通道 82 行 × 5 字段 = **410 次对照 0 不一致**；`dispatch.py:1210` 一带 reason 形态 `write-face-overlap: overlap-with:<key> sample=<s>` | — |
| Q-AC-003 | 未声明写面按 fail-closed（拒绝或 serial-only）且写审计，不得静默放行 | ✅ 充分 | `dispatch.py:1185` 一带 `write-face-undeclared` 审计+serial-only（D-003）；PM 侧 W-13：`reportWriteFaceRefusal` → `auto-decisions.jsonl` `kind:"write-face-refusal"`，且**被拒不再 `queued += 1`**；`write-face-pm-gate.test.ts` 25 passed | 可见性见 Q-AC-006 |
| Q-AC-004 | 写面进 task.md，运行期拒绝越界写，覆盖**所有可写角色**，记 trace | ✅ 充分 | W-10/W-11：`worker/worker-mode.ts` 的 `tool_call` veto 覆盖 `write`/`edit` + bash；安装条件 `hasWriteTools \|\| isShellRole`；`write-face-runtime.test.ts` 18 passed；`mwds-t03` 63 passed（新口径） | 旧断言已按新语义**重写**（非删除/放宽） |
| Q-AC-005 | 同 key 同文件多写者对 = 0（并发派发 N≥4 无交集对） | ✅ 充分 | W-12：实派后复算 **0 对**；**绕过闸门**直写队列行后复算 **1 对**（检测器不自证）；`test_write_face_dispatch.py` race 用例（`ok=True` 恰好 1 + dispatch 事件恰好 1） | 反证是本条的关键 |
| Q-AC-006 | `mw doctor`（或等价只读面）列出拒绝计数 + 最近样本，无重叠显示 0 而非报错 | ✅ 充分 | W-15：`mw.py:621` `report["write_face"]` + `:641` 文本行；`test/test_write_face_doctor.py` 15 passed；本仓库 `write_face.total=0` 且**不进 issues**；干净项目 3 条拒绝时 exit **0**/healthy；相邻 doctor 7 套件 155 passed | 见 §0 偏差：本仓库退出码 1 来自既有 `STALE CODE` |
| Q-AC-007 | 两通道对同一写面输入给出相同判定 | ✅ 充分 | B3 410 字段 0 不一致 + base 对齐 before=4/after=0；W-14：拒绝分支 `reason` **逐字节相等**（空头/非法条目/逃逸三例，`write-face-pm-gate.test.ts` 25 passed）；D-111/D-112/D-115 裁定在案 | 3 条跨通道对照带 `skipIf(!pythonAvailable)`（既有惯例），本机实跑 **0 skipped**；PM 另以读码独立佐证构造点字面一致 |
| Q-AC-008 | 写面不占队列列（`WORKER_COLS_MAX=9` 保持） | ✅ 充分 | 写面只走 task.md 头/卡 envelope；`shared/worker-store.ts::serializeWorkerLine` 为唯一行实现（W-09，D-114），列集未变；`test/test_write_face_dispatch.py` + B3 队列快照断言 | — |
| Q-AC-009 | 字段名不与既有 `write_scope` 含义冲突且写进 spec | ✅ 充分 | D-115（载体收敛裁定）：`write_face:` 为唯一权威载体；`write_scope:` 仅对 writeless 且须字节相同；双载体不等 ⇒ 取交集 fail-closed + 审计；无第五载体 | spec 已记 |
| Q-AC-010 | 覆盖"read-only 角色经 bash 写证据文件"路径 | ✅ 充分 | W-10/W-11：`isWritelessRole` 保持 research 历史面 + `packages/**` deny；bash 走 `extractBashWriteCandidates`/`checkBashWriteScopeTarget`；`autopilot-read-scope` 计数期望按此更新（PM 亲改 2 处） | — |
| Q-AC-011 | 4 个写面载体收敛为 1，其余各自显式处置 | ✅ 充分 | D-115（W1 `写面` 权威 / W2 gate v2 `write_scope` 异语义保持 / W4 marker 仅 marker / 注释面仅注释）+ W-11 落地；`[WRITE_FACE]` 审计行仅在双载体同时存在时打印 | — |
| Q-AC-012 | C 不得替代 B（可证伪）：两个合法声明同路径时**派发层**必须已拒第二个 | ✅ 充分 | W-12 的 AC-005 表：第二张同文件卡在**派发层**被拒（`write-face-overlap` + `overlap-with` 指向在飞 key），非运行期各写各的；两通道各验一次 | — |
| Q-AC-013 | 写面前提不引入新假阻（引语/文档内容不误拦） | ✅ 充分 | W-10/W-11/W-12：假写族 14/14 两通道全放行（`Write-Output a <term> --glob x` 家族 11 + 只读 3），运行期 `write`/`edit` 与 bash 两路径 0 误拦；真写族 4/4 拦；PM 自己的面内/面外探针（含"面内目录目标不误拦"） | 稳定 repro 已锁 |
| Q-AC-014 | `task.md` 创建不得在 `.mw/workers.lock` 之外发生 | ✅ 充分 | PM 读码：`autopilot/dispatch.py` 取锁 `:1435` → `:1461` mkdir / `:1462` write_text → `:1478` 队列行，**全在锁内**（文件头 `:18-27` 记录旧顺序的孤儿缺陷已修）；PM 侧 `store.upsertWithinLock`（W-09）+ 拒绝时 `cleanupRefusedTaskDir`（W-08） | — |

### 1.2 来源 B：design.md VC（Q-VC-001..008 + VC-024）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-VC-001 | 交集算子语料（边界：`a/**` vs `a`、大小写、`**` 中段、deny 优先）双语言一致 | ✅ 充分 | 冻结语料 v3（LF 归一化 `sha256=b39f8925…`，parse 23 + overlap 59）；PM 600 向量跨语言差分（4 处 verdict-shape ⇒ D-111/D-112）后复跑 0 不一致；`test_write_face.py` 130 + `write-face.test.ts` 113 | — |
| Q-VC-002 | 两通道同输入同判定 | ✅ 充分 | 同 Q-AC-007 | — |
| Q-VC-003 | 零副作用（被拒派发不产生 taskDir/task.md/队列行） | ✅ 充分 | `test/test_write_face_dispatch.py` 目录快照；`write-face-pm-gate.test.ts` 的零副作用用例（含 parse 拒绝）；W-15 的 `test_e_doctor_write_face_is_zero_write`（只读面自身零写） | — |
| Q-VC-004 | serial-only 语义（未声明卡在有在飞时延迟、不拒绝；无在飞时正常派发） | ✅ 充分 | `dispatch.py:1185` 一带（D-003）；W-12 的 undeclared 行两通道同判；卡-less 内部派发豁免（避免永久 stall） | — |
| Q-VC-005 | 临界区：同 `task_key` 只产生 1 行 | ✅ 充分 | W-03 双进程对拍（`ok=True` 恰好 1 **且** dispatch 事件恰好 1）；W-09 单写者（D-114）；`upsertWithinLock` 的前置条件写入文档 | — |
| Q-VC-006 | 运行期越界 `write`/`edit`/bash 被 block 并落 trace | ✅ 充分 | W-10/W-11：18 条 runtime 断言（真写族 4/4 拦）；trace 行由 `[WRITE_FACE]`（双载体审计）+ `[WRITE_SCOPE_SUMMARY]`（每被守卫角色一行）承担（旧 `[WRITE_SCOPE]` 口径按 D-115 重写）；`mwds-t03` 63 passed | 旧口径断言**重写**而非放宽 |
| Q-VC-007 | 假阻回归（AC-013 家族） | ✅ 充分 | 同 Q-AC-013 | — |
| Q-VC-008 | `mw doctor` 计数：无重叠显示 0，有拒绝显示计数 + 最近样本 | ✅ 充分 | 同 Q-AC-006（15 passed，含 0 与 N 两条路径、轮转、坏行、只读证明） | — |
| Q-VC-024 | `mwds-t03` 旧口径反转（"有闸且不误拦" / "每个 shell 角色一行 summary"） | ✅ 充分 | W-11 重写该 4 条断言（不删不放宽），`mwds-t03` **63 passed**；PM 另修本 key 合法失效的 `autopilot-read-scope` 2 处计数期望（1→2）与 `dispatch-card-injection` 1 处字节断言 | 本 key 的红账已清 |

---

## 2. 汇总

- **总问题数**: 23（Q-AC-001..014 + Q-VC-001..008 + Q-VC-024）
- **通过（充分）**: **23（100%）**
- **有条件通过（证据不足）**: 0
- **未通过（无证据）**: 0
- **流程前置偏差（不计入问题级 ⚠️）**: 5 项（见 §0，已登记欠债）

**质检结论**: ✅ 通过（Stage 完成质检口径：无 ❌；问题级 ⚠️ = 0 ≤ 3）

---

## 3. 未通过问题行动计划

无（0 项）。

## 4. 二次印证（Step 4）

| 检查 | 结论 |
|------|------|
| spec 中每个约束（安全/平台）是否被 Q 覆盖？ | ✅ 覆盖：安全面 = Q-AC-004/010/011/013（越界写、read-only 角色、载体收敛、假阻）；平台面 = 语料 `V04-cs`/`V41` 锁定大小写模式，B3 显式断言 `os.name=="nt"` 与 `process.platform==="win32"` 互等 |
| design Function Flow 每个节点是否对应至少一个 Q？ | ✅ 覆盖：conductor 入口（Q-AC-001/002/003）→ PM 入口（Q-AC-007）→ 运行期（Q-AC-004/010/013）→ 审计（Q-AC-003/006）→ doctor 展示（Q-AC-006） |
| Coverage Matrix 每个异常路径是否都有 Q？ | ⚠️ 沿用 §0 偏差：本 key 未建 AC→VC 矩阵，异常路径以 Q-AC-013 假阻族 + D-111（顺序无关）+ D-115（双载体不等取交集）覆盖；**无新增遗漏** |
| 是否有 task 的 `vc_refs` 为空但 AC 有对应 VC？ | ⚠️ 10 张卡 `ac_refs`/`vc_refs` 为空（D 系列与算子基建卡），沿用 §0 偏差登记 |

**二次印证结论**: 无新增遗漏问题；1 类结构性偏差（AC→VC 矩阵/绑定缺失）沿用 §0 登记，属流程归档形态而非证据缺失。

---

## 5. 与"遗留"的边界（不重复 AC 勾销）

本 key 的遗留项（`achieved.md` §遗留 1-10）**不属于质检未通过项**：其中 1（`dist/**` 未重建）是"上线前置动作"、7/8（重复激活缺陷、读回投递缺口）是**本 key 面外**的两个独立缺陷（已各有证据文档与建议 key）、2-6/9-10 是显式接受的边界或流程归档偏差。AC/VC 的勾销以上表为准。
