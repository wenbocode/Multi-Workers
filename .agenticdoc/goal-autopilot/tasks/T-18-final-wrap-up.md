# Task T-18: 全量收口（回归 / check / bundle / 证据汇总）

## 基本信息
- Stage: 4
- 代码状态: 代码完成（无新产品代码；测试线程加固 + 汇总产物）
- 验证状态: 验证通过（全套件绿：L1 363 / L0 5/5 / L2 5/5 / vitest 59+106 / e2e_real 1 / smoke 9-0 / check coding-agent 零错 / bundle 重建安装；VC-001~027 全索引见 evidence/runs/final-verification.md）
- 负责 Agent: PM 窗口（直执）
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-024, AC-025]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-024, VC-025, VC-026, VC-027]
- pattern_refs: []

## 描述
EXECUTE 收口任务——全量验证 + 零回归确认 + 证据汇总，产出供 L3 QG 机械提取的完整 [VERIFY] 面。

1. **L1 全量**：`packages/multi-workers/test_autopilot_*.py` 全绿（config/roadmap/timeline/gates/dispatch/state/audit/conductor/conductor_stage/conductor_exec）
2. **L0**：`test_autopilot_l0.py` 全绿（VC-007/VC-023）
3. **L2**：`test_autopilot_e2e.py` 全绿（8 组计时/隔离/并发断言）
4. **vitest 全量**：autopilot-read-scope / autopilot-protocol / autopilot-console + 既有 agent-team-loop 套件零回归
5. **AC-012 手动套件对照**：packages/multi-workers/ 既有 test_*.py + smoke_test.sh 按 T-01 baseline 冻结的清单与期望通过数逐项对照，结果一致
6. **`npm run check`**：本 key 改动零错误/零警告（TS 侧）
7. **bundle 重建安装**：`mw build --install`（教训来源 mw-stale-builtin-fix：stale dist 双载与实际源不一致；TS 改动必须重建）
8. **证据汇总**：全部 [VERIFY] 行（Python harness 输出 + vitest 名单 + E2E 原样输出）汇总至 `evidence/runs/final-verification.md`，按 VC-001~027 编号索引，供 L3 reviewer 与 quality-gate 机械提取
9. **遗留清单**：needs-rerun 项与已知限制如实列出（D-112 语义）

## 输入
- 依赖文件: 全部前序 task 产物 + T-01 baseline
- 依赖 Task: T-01~T-17 全部
- AC 约束:
  > 全部 25 AC（spec §3 锁定版；本 task 为覆盖面收口，不新增行为）
- 设计约束:
  > evidence-requirement 证据落盘约定：Python [VERIFY] 行 / vitest 测试名含 VC 编号 / L2 脚本化 E2E / 手动套件原样输出
  > D-112: 需重跑命令标 needs-rerun 计入遗留

## 预期产出
- `evidence/runs/final-verification.md`（VC-001~027 全索引 + 原样输出）
- 全部套件绿 + npm run check 绿 + bundle 重建完成
- 验证方式: 本 task 自身即验证任务；完成判定 = 汇总文件齐 + 全绿证据链
- 验证等级: Level 2（收口）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 21:50-22:20 | ①mw build --install（bundle 重建+全局安装，S3 TS 改动入 bundle）；②L2 全窗口复跑（修复后 exit 0 零线程异常，294+24 行零丢失）；③L1 全量+L0 证据跑；④vitest 四套件；⑤AC-012 手动对照（e2e_real 1 passed 17.09s、smoke 9-0 exit 0，均与基线一致；agent-team-loop 90→106、基线六文件 121→167，演进项归因并行会话）；⑥npm run check（coding-agent 零错，26 错全为 packages/ai 存量）；⑦[VERIFY] 机械提取（L1 107 行 20 VC + vitest 15 VC 名测试）；⑧写 evidence/runs/final-verification.md（VC-001~027 全索引 27/27 + 原样输出清单 + 遗留 7 项） | 全绿；VC 27/27 覆盖 |
| 2 | 2026-09-10 22:35-22:50 | QG run1（worker t18-quality-gate，gpt-5.6-sol）前置门禁中止：①ac_fingerprint 失配（当前 ccc2c018e052 vs 记录 v2 475a2958a5ca，三种命令变体均不可复现历史值→早期口径漂移非 AC 集变更，ac_ids 逐项交叉验证恰 AC-001~025）；②evidence/baseline/ 目录缺失（T-01 冻结为文件形态）。PM 处置：指纹以 QG 规范命令重算落 v3；基线文件迁入 evidence/baseline/baseline-manual-suites.md（全引用点同步：evidence-requirement/plan/pm-state/T-01/final-verification）；run1 中止报告归档 quality-gate-report-2026-09-10-qg-run1-aborted.md；重派 t18-quality-gate-2 | 前置门禁修复待复检 |
| 3 | 2026-09-10 22:55-23:00 | QG run2（t18-quality-gate-2，1m/45 工具调用）仍中止于同一指纹失配——PM 归因：run1 处置时 edit 调用含两个 edits，edits[1] 不匹配致整批原子回滚，指纹 v3 替换（edits[0]）实际未落盘而我误判已改（基线路径编辑是另一次独立调用已生效）。本次单独重放指纹编辑并 rg 复核落盘 + 规范命令复算（ccc2c018e052，25 AC）双确认；run2 报告归档 -run2-aborted | E2b 教训：edit 工具整批原子——任一 oldText 不匹配则全部不应用，处置后必须逐项 rg 验证；重派 run3 |
| 4 | 2026-09-10 23:05-23:25 | QG run3（t18-quality-gate-3，5m/83 工具调用）全流程跑完：前置门禁 8/8，结论 FAIL（A=61/B=10/C=2，73 问题）。PM 逐项亲核 6 类阻塞发现全部属实且均在 spec 合同内。呈用户处置：四项可修 + VC-018 erratum + Unix 策略 | 验收成立，待决策 |
| 5 | 2026-09-10 23:30-2026-09-11 00:05 | 用户裁决：A 批准 VC-018 erratum；B Unix 出范围（Windows-only）。QG 修复轮 PM 直执：①产品修复×2（conductor.py：L3 回路预算硬编码 2→round_budget 配置源【AC-011 三回路一致】；done 事务/停派路径写 l3-verdict.txt+l3-report.md【AC-003 dossier 裁决链】）；②新用例×2（budget=1 × l3/task-retry 双回路 VC-013；exec 套件 meets→done→dossier 裁决链断言 VC-005）；③e2e 新测试×2（test_conductor_kill_respawn：真 taskkill+serve 重生+不变量 VC-024；test_multi_project_isolation：双 serve 双 conductor 隔离+互不干扰）；④VC-018 erratum 落地（spec §2.2/AC-016 + design VC-018 + evidence-requirement AC-016 行 + e2e slack_ms 三值断言）；⑤spec §2.1 平台 Windows-only erratum。验证：L1 367 passed（+2 用例，1 个 test_integration 抖动三重跑全绿）；e2e 7/7 exit=0；指纹不变 ccc2c018e052；证据双日志刷新 + final-verification.md 修复轮块 | 全绿待 QG 复检 |
| 6 | 2026-09-11 00:25 | QG run4（t18-quality-gate-4，4m/75 工具调用）复检 **PASS（A=72 B=0 C=0，100%）**：前置门禁 8/8；六类原阻塞项全部充分（MULTI-PROJECT/VC-024 kill=real-process/VC-013 三回路/VC-005 裁决链/VC-018 修订合同 967ms≤1000+250）；Unix 按裁决关闭。报告 evidence/quality-gate-report-2026-09-11-qg.md。**合入前质检通过** | 待：修复轮 commit（用户确认）+ done 事务 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | 真发现（Windows 竞态） | mw_common._write_workers_file tmp→replace | 压测中人工线程 `PermissionError: [Errno 13] ... _workers.parallel`（替换窗口内并发 open）；生产读方全带 catch-all，数据零丢失，测试线程已加 _retry_io 同型重试 | 已处置：测试加固 + 遗留清单 #1（可选后续：parse_workers_file 读侧重试内置化） |

### 设计取舍备注
- **AC-012 对照口径**：基线 §4 条款 4——“同一工作树既有测试零回归 + 演进项归因”；本 key 全部新增为独立 test_autopilot_*.py 文件，零触碰基线六文件；agent-team-loop/launcher 增量归因并行会话（其工作树未提交改动非本 key 责任）
- **VC 索引双源**：Python [VERIFY] 行（pytest -s 提取 107 行）+ vitest 测试名含 VC 编号（15 个）——两者均为机械可提取面，无人工计数
- **e2e_real/smoke 重跑成本**：真 timi 一次 + 真 serve 一轮，均为基线冻结口径内的必要复验
