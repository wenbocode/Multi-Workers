# Evidence Requirement: goal-autopilot

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/goal-autopilot/spec.md` |
| spec_locked_at | 2026-09-08T20:31:02Z |
| ac_fingerprint | `ccc2c018e052`（v3，QG 规范命令 `grep -oE 'AC-[0-9]{3}' spec.md | sort -u | sha1sum | cut -c1-12` 重算；v1=`09522ef47912`、v2=`475a2958a5ca` 为早期不可复现口径（三种变体均无法重现）；AC 编号集经 ac_ids 逐项交叉验证未变（恰 AC-001~025）） |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-024, AC-025 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-024, VC-025, VC-026, VC-027 |
| generated_at | 2026-09-08T22:20:00Z（v2，ga-spec-design-review-2 处置后） |

## 证据矩阵（按 AC 汇总）

| AC | 主要 VC | 证据来源 | 期望内容 | 充分性判定 |
|----|---------|---------|---------|-----------|
| AC-001 | VC-001, VC-002 | roadmap_check CLI 输出 + conductor tick 测试日志 | 完整样例 exit 0 / 缺失样例 exit 1 缺失项非空；roadmap-writer 产物全 stage 过校验 | 各单次 PASS |
| AC-002 | VC-003, VC-004 | conductor 测试（gate 未答 3 tick 行数计数）+ L2 计时测试 | 未答 rows=0；答后首行 delay ≤ 2×配置 interval（动态阈值，输出双值） | 计数断言 + 计时断言各一次 PASS |
| AC-003 | VC-005 | conductor 测试（全 key 终态后 tick）+ exec 套件 meets→done→dossier 裁决链 | dossier 文件存在 + next gate pending + next rows=0，均在 1 tick 内；dossier 每 key 行含 meets/below 裁决与 l3-report.md 引用（l3-verdict.txt 落盘断言） | 双层 PASS |
| AC-004 | VC-006 | L2 计时测试（双 key 并行） | 两 key 行均出现且 delay < 10s | 单次 PASS |
| AC-005 | VC-007 | L0 静态扫描输出 + timeline advance 事件 | phase 直写数 0 / goal 写 0 / 推进事件全带脚本退出码 | 静态扫描 0 命中 + 运行期全事件 |
| AC-006 | VC-008 | conductor stalled 路径测试 | stalled 四产物齐备 / dep rows=0 / indep rows≥1，1 tick 内 | 单次 PASS |
| AC-007 | VC-009 | audit_evidence CLI 双样例 | 齐全 exit 0 三键 JSON / 缺失 exit 1 gaps 非空 | 双样例各一次 PASS |
| AC-008 | VC-010 | conductor L2 上限测试 | 第 3 轮 verifier rows=0 + gate 文件 1 tick 内存在 | 单次 PASS |
| AC-009 | VC-011 | vitest（read_scope 拦截器单测） | 越界 block reason 含路径与规则 / output.md 拒绝节含条目 / 界内放行 | 三断言一次 PASS |
| AC-010 | VC-012 | conductor L3 路径测试 | 裁决二值 / 复评 ≤2 / meets 时两文件落盘 | 单次 PASS |
| AC-011 | VC-013 | conductor budget=1 测试（三回路各一用例） | L1↔L2、L3、task-retry 三回路各 1 轮后升级，第 2 轮 rows=0 | 三回路各自单次 PASS |
| AC-012 | VC-014 | L2 隔离测试 + 现有套件运行（baseline 冻结：套件清单+期望通过数在实现期首 commit 固化于 evidence/baseline/baseline-manual-suites.md） | conductor_alive=0 / _autopilot 写入 0 / 手动套件全绿（对照冻结 baseline） | 套件全绿为充分 |
| AC-013 | VC-015 | conductor claim 测试 | skip rows=0 + skip 事件 ≥1 + 接管后 rows=0 | 单次 PASS |
| AC-014 | VC-016 | conductor 接手测试 | resumed_phase=EXECUTE + artifact mtime 不变 | 单次 PASS |
| AC-015 | VC-017 | vitest（status-model）+ 计时 | --json 三字段 / 重建 <10s / 视图一致 | 单次 PASS |
| AC-016 | VC-018 | L2 计时测试（gate 回答） | consume delay ≤ interval + tick 处理开销（erratum 2026-09-10，断言 slack=250ms，输出 delay/interval/slack 三值） | 单次 PASS |
| AC-017 | VC-019 | conductor 转移矩阵测试 | 每类转移事件 ≥1 行含 ts+key（key 级填 key，stage/全局填哨兵非 null，erratum 对齐） | 全转移类型覆盖一次 |
| AC-018 | VC-020 | vitest + conductor 双侧读同源 | rounds 数值 parity=true | 单次 PASS |
| AC-019 | VC-021 | L2 存活观测（60s 窗） | beats ≥12 | 单次 PASS |
| AC-020 | VC-022 | 并发写压测（conductor + 模拟人工） | parse_failures=0 / lost_rows=0；列数按各文件实际（erratum 对齐：_index 7 / _workers 7|8 容错） | 单次 PASS |
| AC-021 | VC-023 | L0 per-type 奇偶测试 + conductor 未知 type 测试 + worker fail-closed 测试 | unknown rows=0 + registry_parity=per-type-exact + verifier 显式条目 + origin=conductor 未知 type exit 1 | 静态 + 动态各一次 |
| AC-022 | VC-024 | L1 状态重建测试 + L2 真进程 kill/respawn e2e（test_conductor_kill_respawn） | L1：[START]=1 + 计数相等 + mtime 不变；L2：真 taskkill conductor PID → serve 监护重生（新 PID）→ 2 interval 内续推 + 无重派 + 预算/mtime 不变 | 双层 PASS |
| AC-023 | VC-025 | conductor 失败注入测试 | retry 计入预算 + 其他 key rows≥1 | 单次 PASS |
| AC-024 | VC-026 | conductor reject 语义测试 | 重提案恰 1 次 + 二拒后 0 提案 + stalled 遗留关闭不阻塞闭环 | 单次 PASS |
| AC-025 | VC-027 | L2 enable 流程测试 | mw status 含 conductor 行 + 提案行 delay ≤ 配置 interval（act-then-sleep，输出双值） | 单次 PASS |

## 证据落盘约定

- Python 侧测试断言输出行格式：`[VERIFY] VC-NNN: key=value`（conductor 测试 harness 统一 emit，供 quality-gate 机械提取）
- vitest 侧：expect 失败即 VC FAIL；通过即 PASS（测试名含 VC 编号）
- L2 计时/隔离类：以脚本化 E2E（`packages/multi-workers/test_autopilot_e2e.py`，stub worker 完成器）运行并输出 [VERIFY] 行
- 现有手动工作流套件结果：`packages/multi-workers/test_*.py` + smoke_test.sh 按 mw-dispatch-reliability L0/L1/L2 矩阵执行的原样输出

## 质检门禁使用说明

本文件由 /quality-gate 读取，对每个 AC/VC 逐条核查证据充分性；VC 输出行缺失或值不达标的 AC 记 FAIL，进入 L3 修复回路（≤2 轮）。
