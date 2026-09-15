# Quality Gate Report: mw-dispatch-flow-fixes

**时间**: 2026-09-08T15:05:00+08:00
**触发**: 全量（T-01~T-11 全部完成，done 前）
**范围**: 13 AC / 19 VC / 覆盖矩阵 F1~F11 / 交叉问题 4 项

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec.md AC 编号 | ✅ AC-001~AC-013（含 [REVISED @ 2026-09-08] AC-001/AC-008 两处措辞修订，编号集合不变） |
| design.md VC 编号 | ✅ VC-001~VC-019 |
| AC→VC 映射覆盖 | ✅ 13/13（脚本复检 none missing） |
| evidence-requirement.md | ✅ 存在 |
| ac_fingerprint 一致 | ✅ `95d6a253ba12`（规范公式重算 @ 15:00，AC ID 集合自锁定未变） |
| evidence/baseline/ | ⚠️ 空——本 key 无 AC 要求存储基线对比；AC-008 的"同规格回归"由 evidence/runs/l2-rerun-2026-09-08.md 实跑满足 |
| task ac_refs/vc_refs | ✅ T-01~T-11 全部非空 |

## 问题清单与核查结果

### Q-AC（spec 验收条件）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | owner=激活 key，task 落 {K}/workers/ | ✅ 充分 | VC-001/002/003/017 + L2 队列行 | — |
| Q-AC-002 | watch 不一致同步 + 一次告警 | ✅ 充分 | VC-003（warn_count=1，含两 key 名，二次派发 0 条） | — |
| Q-AC-003 | 心跳 ≤60s 结构化条目 | ✅ 充分 | VC-004（L0 常量+格式）+ VC-012（L2 实跑 14 条全间隔 30.0s） | — |
| Q-AC-004 | 活性判定机制（阈值可配） | ✅ 充分 | VC-006（pytest 三判定+阈值覆盖）+ VC-007 + L2 doctor alive 现场 | — |
| Q-AC-005 | 既有协议 additive | ✅ 充分 | VC-005（混合 trace 格式不变）+ VC-008（61/61 全量）+ L2 真实 [FLOW] 行格式不变 | — |
| Q-AC-006 | 无凭证环境 review 默认 pi 完成 | ✅ 充分 | VC-009（L1）+ VC-012（L2：type: review → pi/timi done） | — |
| Q-AC-007 | 显式 claude 保留；type 不触发 | ✅ 充分 | VC-010（显式 cli=claude 队列行 + research 扫描 pi/timi） | — |
| Q-AC-008 | 同规格 review 重放三项 | ✅ 充分 | VC-012（evidence/runs/l2-rerun-2026-09-08.md） | REVISED 落点=认领 key（用户决策 9） |
| Q-AC-009 | 显式 claude 缺凭证隔离不降级 | ✅ 充分 | VC-011（pytest 112 含 8 隔离用例回归） | — |
| Q-AC-010 | gate 仅评有未入队任务的 key | ✅ 充分 | VC-013（全入队 0 事件）+ VC-014（对照） | — |
| Q-AC-011 | 播报按窗口认领 key 过滤 | ✅ 充分 | VC-015（scoped notifier 三态）+ VC-016（终态摘要作用域） | — |
| Q-AC-012 | widget 心跳进度 monitor | ✅ 充分 | VC-018（三态行断言）；4s 刷新为既有 poll 基建（既有 startWorkerPollLoop 用例覆盖 renderWatchLines 接线） | — |
| Q-AC-013 | 终态摘要附心跳统计 | ✅ 充分 | VC-019（≥2 hb 附统计、<2 保持原格式） | — |

### Q-VC（设计断言）

| 问题 ID | 状态 | 证据引用 | 问题 ID | 状态 | 证据引用 |
|--------|------|---------|--------|------|---------|
| Q-VC-001 | ✅ | vitest VC-001 ×2（混合格式安全） | Q-VC-011 | ✅ | pytest 112（隔离 8 用例） |
| Q-VC-002 | ✅ | vitest VC-002 ×2 | Q-VC-012 | ✅ | runs/l2-rerun-2026-09-08.md |
| Q-VC-003 | ✅ | vitest VC-003 | Q-VC-013 | ✅ | vitest VC-013 |
| Q-VC-004 | ✅ | vitest VC-004 | Q-VC-014 | ✅ | vitest 既有 undoc gate 用例 |
| Q-VC-005 | ✅ | vitest VC-005 + L2 [FLOW] 实跑 | Q-VC-015 | ✅ | vitest VC-015 |
| Q-VC-006 | ✅ | pytest TestWorkerLiveness ×4 | Q-VC-016 | ✅ | vitest 既有 scoping 用例 |
| Q-VC-007 | ✅ | vitest VC-007 | Q-VC-017 | ✅ | T-03 脚本 [VERIFY] ×3 |
| Q-VC-008 | ✅ | 全量 in-suite 61/61 | Q-VC-018 | ✅ | vitest VC-018 |
| Q-VC-009 | ✅ | vitest VC-009 + L2 | Q-VC-019 | ✅ | vitest VC-019 |
| Q-VC-010 | ✅ | vitest VC-010（t4 显式 claude） | | | |

### Q-COV（覆盖矩阵 F1~F11）

F1 owner 解析链 ✅（VC-001~003/017）· F2 心跳写入 ✅（VC-004/005）· F3 心跳消费面 ✅（VC-018/019）· F4 路由 ✅（VC-009/010）· F5 gate 收敛 ✅（VC-013/014）· F6 播报作用域 ✅（VC-015/016）· F7 doctor 判定 ✅（VC-006/007）· F8 doctor 摘要 ✅（VC-007）· F9 隔离回归 ✅（VC-011）· F10 全量回归 ✅（VC-008）· F11 心跳消费面（D-008）✅（VC-018/019）

### 交叉问题（来源 D）

| 问题 | 结论 | 依据 |
|------|------|------|
| 显式 key 派发不触发 mismatch 告警（AC-002×AC-001 交互） | ✅ 构造性覆盖 | resolveOwnerKeyWithSync 显式分支 early return 在告警调用之前；VC-003 覆盖自动路径 |
| TS STALE 90s ↔ doctor 90s 双处常量同步 | ✅ | 两侧注释互指（heartbeat.ts / mw_common.py）；VC-018 + VC-006 各自断言默认值 |
| 旧 bundle 兼容（no-hb 占位 / no-heartbeat 判定 / <2 hb 原格式） | ✅ | VC-018 / VC-006 / VC-019 三面均有显式用例 |
| 看门狗 30min 语义未动（GC-4） | ✅ | worker-mode 改动仅增 interval+clear；既有看门狗断言在 61/61 内 |

## 汇总

- **总问题数**: 47（13 Q-AC + 19 Q-VC + 11 Q-COV + 4 交叉）
- **通过（充分）**: 46（97.9%）
- **有条件通过（不足）**: 1 ⚠️（见下）
- **未通过（无证据）**: 0

**质检结论**: ⚠️ 有条件通过（欠债/豁免 1 项，经用户确认后可合入）

## ⚠️ 项（需用户确认接受）

| # | 项 | 事实 | 影响 | 建议 |
|---|-----|------|------|------|
| W-1 | `npm run check` 仓库整体红（580 错误） | 复检 @ 15:1x：全部 580 个 TS 错误存在于已提交 HEAD（出错文件工作区零修改）：579 个在 test/examples 文件（引用的模型 ID 如 claude-sonnet-4-5/gemini-2.5-flash 不在当前生成注册表 → never），1 个在 packages/ai/src/github-copilot.ts；另有 Windows 无 sh 的测试失败。分布：ai 545 / coding-agent 31 / agent 4；本 key 范围（agent-team-loop、multi-workers）0 错误 | 合入本 key 不引入新错误；HEAD 的 test 模型 ID 陈旧需要单独修复（另开 key） | 接受现状；修复建议另开 key 处理 |

## 二次印证结论

重读 spec/design 全文二次扫描：spec §2 场景、§1.3 场景 2（监控方区分"在工作/疑似挂起"）由 AC-004/012 消费面覆盖；Function Flow 三图节点均有对应 VC；异常路径行（STALE/no-heartbeat/旧 bundle/冲突预检保留）均有 Q-COV。L2 评审 worker 提出的 3 项 UNCLEAR 已处置（AC-001 精度修订、design anchor/VC-012 同步、AC-005/008 可追溯性注记于 evidence/runs）。无新增遗漏。

---

# Round 2（2026-09-08 17:5x，S6 评审修复轮后）

**触发**：code-review-1 发现处置完成 + AC-014 追加后重跑全量。

## 变更面

- spec：AC-014 append（终态自动回读，用户决策）+ AC-001/AC-008/AC-013 措辞精度修订；指纹 9c90fbb3e171（14 AC）
- 代码：M1/M2（原子 claim 原语 + restoreWatch 静默重绑）、M3（Z 后缀归一）、m1（gate 槽不烧）、m2（pm-key new 走 takeover）、m3（poll 句柄 session_shutdown 清理）、m4（删 activeKeys）、n2（文档措辞）、M4（框架 claim 协议对齐，已推 0f4959b）、T-14（readOutputBody 全文回读）

## 问题清单增量

| 问题 | 状态 | 证据 |
|------|------|------|
| Q-AC-014（终态全文回读 ≤20k 截断指路） | ✅ 充分 | VC-020（vitest 66/66 内） |
| Q-VC-020 | ✅ 充分 | 同上 |
| M1 原子性（双窗竞争不得都认为认领成功） | ✅ 充分 | claim 单锁 + 写后验证 + 测试 ×2 |
| M2 静默重绑不踩活 claim/不写回陈旧快照 | ✅ 充分 | restoreWatch 走 claim(quiet) + 测试（key-x 不降级、状态保持） |
| M3 Python 3.10 活性失效 | ✅ 充分 | _parse_heartbeat_ts + 线格式钉住测试 |
| M4 跨写者协议 | ✅ 充分 | host:pid + 共享锁 + stale-local 免 force；pytest ×3 + 四象限手动验证 |
| m1/m2/m3/m4/n2 | ✅ 充分 | 各有测试/新断言（66/66、116 passed） |

## 结论更新

- 52 问题（14 Q-AC + 20 Q-VC + 11 Q-COV + 4 交叉 + 3 评审交叉）→ **51 充分 / 0 未通过 / 1 ⚠️**
- ⚠️ 仍为 W-1（HEAD 既有 580 错误，归因已修正为已提交状态；本 key 0 错误，全仓与 T-10 基线完全一致零新增）
- 底部 widget 冻结归因补充：旧 bundle（HEAD）无每-tick 重绘能力，非本 key 代码缺陷；新 bundle 已安装，重启窗口即生效


---

# Round 3（2026-09-09 晚，恢复复验）

**触发**：worktree junction 删除事故后，本 key 全部源码（与本仓其它未提交工作）按 pi/Claude 会话日志重放恢复；接管复跑门禁。

## 恢复完整性证据

- 重建扩展 bundle 与事故前（16:11 构建、16:1x 全局安装）bundle **SHA256 字节一致**——质检所验证的扩展代码与恢复后工作区完全相同
- vitest agent-team-loop **90/90**（Round 2 时 66/66；增量为 mw-worker-timeout-convergence 14 + pm-state 守卫 3，均与本 key 无交集且零回归）
- mw pytest 116+5 全绿（doctor 15/15 含 worker_liveness）
- audit_phase：**PASS**（design/plan/tasks/execute 全过）
- AC-016 等价复验（dist 事故中被删、已全量重建）：exitWithSuccess 0 处 / finishSuccess 3 处 / ACTIVATION_FLAG 双载防护在位 / 裸 `pi -p "Say exactly: ok"` exit=0、5s 自然退出、输出 ok（对照 smoke-ac016b 的 4.1s）/ `pi --version` 0.83.0

## 结论更新

- Round 2 的 51 充分 / 0 未通过 / 1 ⚠（W-1）维持；W-1 全仓基线由 580 收敛至 26（数据重拉），本 key 范围仍 0 错误
- AC-015 实机首验与 mw serve 旧 launcher 重启两项转记 achieved.md 遗留（用户窗口重启后自然完成）
