# Final Verification — goal-autopilot 全量收口（T-18）

> Key: goal-autopilot · Task: T-18 · 汇总时间: 2026-09-10 22:20（QG 修复轮更新 2026-09-11 00:05）
> 环境: Windows · Python 3.14.3 / pytest 9.0.2 · node + vitest（repo node_modules）
> 用途: L3 reviewer / quality-gate 机械提取面——VC-001~027 全索引 + 原样输出指针 + AC-012 对照 + 遗留清单（D-112 语义）

## 1. 套件结果总表

| # | 层级 | 套件 | 命令 | 结果 | 原样输出 |
|---|------|------|------|------|---------|
| 1 | L1 | Python 全量（默认排除 e2e_real/e2e_l2） | `python -m pytest`（packages/multi-workers 下） | **367 passed, 8 deselected**（QG 修复轮 +2 用例 + 并行会话 +2） | `l1-python-final.log` |
| 2 | L1 | [VERIFY] 机械提取面 | `python -m pytest -q -s` | **110 行 [VERIFY]，20 个 VC** | `l1-verify-lines.log` |
| 3 | L0 | 静态门禁 + 双侧奇偶 | `python test_autopilot_l0.py` | **5/5**（含 vitest autopilot-protocol 10/10 活跑） | `l0-parity-final.log` |
| 4 | L2 | 进程链 e2e（stub worker，零 LLM/零网络） | `python test_autopilot_e2e.py`（默认窗口：beat 60s@4s、压测 60s@0.5s） | **7/7，10 组 [VERIFY] 全 pass=true，exit 0**（QG 修复轮新增 kill/respawn 与多项目隔离两测试） | `l2-e2e-final.log` |
| 5 | L1 | TS autopilot 三套件 | vitest --run test/suite/autopilot-{read-scope,protocol,console}.test.ts | **59/59** | `vitest-autopilot-final.log` |
| 6 | L1 | TS agent-team-loop 回归 | vitest --run test/extensions/agent-team-loop.test.ts | **106/106**（基线 90，+16 为并行会话演进，零失败） | `vitest-agent-team-loop-final.log` |
| 7 | L2 | 真实链路 e2e（真 pi + timi） | `python -m pytest test_e2e_real.py -m e2e_real` | **1 passed (17.09s)** — 与基线一致 | `e2e-real-final.log` |
| 8 | L2 | smoke E2E（真 mw serve/init/stop） | `bash smoke_test.sh`（Git Bash） | **PASS: 9 FAIL: 0, exit 0** — 与基线一致 | `smoke-final.log` |
| 9 | — | `npm run check` | repo 根 | coding-agent **零 TS 错误**；26 个错误全为 packages/ai 存量基线（与 S3 验收时同一集合，见 §4 演进说明） | `npm-check-final.log` |
| 10 | — | bundle 重建安装 | `python mw.py build --install` | built + self-check OK；全局安装 `~/.pi/agent/extensions/agent-team-loop.js` | 见执行记录 |

## 2. VC-001~027 全索引（机械提取面）

格式：VC → 证据位置（L1 = l1-verify-lines.log 计数；L0/L2 = 对应 log；TS = vitest 测试名含 VC 编号）。

| VC | 主题 | 证据 |
|----|------|------|
| VC-001 | roadmap 结构校验（stage/依赖/key-status 覆盖） | L1 ×18（test_autopilot_roadmap.py） |
| VC-002 | roadmap 产物独立校验（roadmap_check 全 stage 过） | L2 ×1（stub roadmap-writer 产物，exit 0） |
| VC-003 | stage-confirm 未答不派发 / 拒后流程 | L1 ×2（test_autopilot_conductor_stage.py） |
| VC-004 | stage 门禁时延（回答→首派发 ≤2×interval） | L2 ×1（1014ms / 2000ms） |
| VC-005 | stage 闭环 dossier + close gate | L1 ×9（conductor_stage + exec 套件 meets→done→dossier 裁决链：l3-verdict.txt=meets 落盘 + dossier 每 key 行含 meets/l3-report.md） |
| VC-006 | 并行派发（双 key 首派 <10s 且并存） | L2 ×1（264ms，parallel=2） |
| VC-007 | AC-005 静态（Phase 零直写/goal 零写/exit 码 schema） | L0 ×2 + L1 ×3（AST 扫描 + 运行期双码） |
| VC-008 | conductor 锁/窃取 | L1 ×1（test_autopilot_conductor.py） |
| VC-009 | L1 审计 dossier（AC 提取/决策映射/缺口） | L1 ×5（test_autopilot_audit.py） |
| VC-010 | L2 缺口回路 | L1 ×1（conductor） |
| VC-011 | 派发事件/队列行 | L1 ×1 + TS ×1（read-scope 套件） |
| VC-012 | L3 裁决 + done 三件套事务 | L1 ×7（test_autopilot_conductor_exec.py）+ L2 spine（6 次 advance 真门禁全过） |
| VC-013 | beat 存活/静默诊断 | L1 ×3（conductor） |
| VC-011/013 | budget=1 三回路（L1↔L2 / L3 / task-retry） | L1 ×5 — QG 修复轮：产品修复（L3 预算从硬编码 2 改 round_budget 配置源）+ l3/task-retry 两回路新用例（second_round_rows=0 escalated=stalled） |
| VC-014 | 未启用隔离（无 conductor/无写入） | L2 ×1（serve 场景） |
| VC-015 | live claim 跳过 | L1 ×2（conductor） |
| VC-016 | artifact mtime 不变 | L1 ×2（conductor） |
| VC-017 | /autopilot console（status --json/视图奇偶/时间线重放） | TS ×5（autopilot-console.test.ts） |
| VC-018 | gate 消费时延（≤1×interval） | L2 ×1（1014ms / 1000ms） |
| VC-019 | 派发/预算/门禁事件流 | L1 ×17（conductor 族） |
| VC-020 | usedRounds 口径（distinct attempt） | L1 ×2 + TS ×3（console rounds 结构） |
| VC-021 | beat 观测窗（60s@4s ≥12） | L2 ×1（beats=15）+ L1 ×3 |
| VC-022 | 并发写完整性（零丢失/列数/无重复） | L2 ×1（294 人工行 + 24 conductor 行）+ L1 ×4（崩溃不变量，conductor_exec） |
| VC-023 | 双侧注册表奇偶 + fail-closed + 手动 fallback | L0 ×3 + L1 ×10 + TS ×5（protocol 套件） |
| VC-024 | 重启不变量（[START]=1/预算/mtime/续推） | L1 ×4 + TS ×1 + L2 真进程形态 ×1（QG 修复轮：taskkill conductor PID → serve 监护重生新 PID → 续推 + 无重派 + 预算/mtime 不变） |
| VC-025 | 失败注入（重试/超限 stalled/他 key 不受阻） | L1 ×2（conductor_exec） |
| VC-026 | stalled-reject 同 tick 解锁 | L1 ×5（conductor_stage） |
| VC-027 | enable 链路（serve 检测+spawn+首派发） | L2 ×1（752ms）+ L1 ×11 |

**覆盖核对：VC-001~027 共 27 项全部有至少一条本 key 证据。**

**QG 修复轮补充（2026-09-11 00:05，回应 quality-gate-report-2026-09-10-qg.md run3）**：
- 多项目隔离（Q-X-MULTIPROJECT）：L2 `test_multi_project_isolation` — [VERIFY] MULTI-PROJECT: conductors=2 per_project_pids=true queues_isolated=true p2_unaffected=true p1_respawned=true（双 serve 实例、独立 conductor PID、独立队列、杀 p1 conductor 不影响 p2 且 p1 自愈）
- 真进程 kill/respawn（Q-AC/VC-022/024）：L2 `test_conductor_kill_respawn` — [VERIFY] VC-024 kill=real-process respawned=true new_pid=... start_lines=1 budgets_unchanged=true mtime_unchanged=true
- budget=1 三回路（Q-AC/VC-011/013）：产品修复（L3 预算改配置源）+ 两新用例 — [VERIFY] VC-013 loop=task-retry/l3 各一行 second_round_rows=0 escalated=stalled
- l3-verdict 落盘（Q-AC-003/Q-X-L3-DOSSIER）：产品修复（done 事务/停派路径写 l3-verdict.txt+l3-report.md）— meets 链 [VERIFY] VC-005 dossier_verdict=meets + below 链 l3-verdict.txt=below 断言
- VC-018 erratum（用户批准 2026-09-10）：阈值改「首个后续 tick 内消费（≤ interval + tick 处理开销，slack=250ms）」，spec §2.2/AC-016、design VC-018、evidence-requirement AC-016 行同步；e2e 断言与输出对齐（delay/interval/slack 三值）；ac_fingerprint 不变（ccc2c018e052，erratum 无 AC-id 变更）
- Unix 平台（Q-X-UNIX）：用户裁决 2026-09-10 出范围，spec §2.1 erratum 改 Windows-only，问题关闭

## 3. AC-012 手动套件对照（T-01 基线）

基线锚点 `f6cea320c`（evidence/baseline/baseline-manual-suites.md）：

| 套件 | 基线 | 本次 | 判定 |
|------|------|------|------|
| e2e_real（真 timi） | 1 passed | 1 passed (17.09s) | **一致** |
| smoke_test.sh | 9 PASS 0 FAIL | 9 PASS 0 FAIL, exit 0 | **一致** |
| TS agent-team-loop | 90 passed | 106 passed | **零失败**；+16 为并行会话（launcher beat D-007/D-008）演进，非 autopilot 改动，属基线 §4 条款 4 演进项 |
| Python 六基线文件 | 121 passed | 167 collected 全过 | **零失败**；test_common 37→61、test_launcher 47→69 为同一并行会话演进项；autopilot 自身为新增独立文件（test_autopilot_*.py ×11，196 用例），不触碰基线文件 |
| 全量 Python | 121+1deselected | 363+6deselected | 演进构成：121 基线 + 46 并行会话 + 196 autopilot（L1 191 + L0 5）；6 deselected = e2e_real ×1 + e2e_l2 ×5 |

判定：**AC-012 PASS**——基线测试在同一工作树内零回归；全部增量可归因（autopilot 新增文件 / 并行会话 launcher 工作，后者工作树未提交改动不属于本 key）。

## 4. npm run check 说明

- `packages/coding-agent`（本 key TS 侧全部改动所在）：**零 TS 错误**。
- 26 个 `error TS` 全部位于 `packages/ai`（cloudflare-ai-gateway + 15 个 test 文件），与 T-13/14/15 验收及 S3 提交前同一存量集合，非本 key 引入。

## 5. 遗留清单（D-112：needs-rerun 与已知限制，如实列出）

1. **Windows 原子替换竞态（已知限制，非缺陷）**：`_write_workers_file` 的 tmp→replace 在替换窗口内，并发 open（读或追加）可瞬时 `PermissionError`。生产读方全部带兜底（launcher 每轮 poll catch-all / conductor tick catch-all / TS 侧另有重试语义），数据完整性契约（锁协议下零丢失）在 60s 压测中成立。L2 测试线程已加重试（与生产读方同型）。后续可选：`parse_workers_file` 读侧重试内置化。（Windows-only 平台裁决后，此项为平台固有语义非跨平台债）
2. **dispatch render_task_md 不写 l2_read_file_cap/l2_read_byte_cap**：worker 侧缺省回退 8 文件/65536 字节；紧 scope verifier 下 8 文件够用。T-16 e2e 中 verifier stub 全链通过，实际容量上限未在真实 LLM 场景标定（needs-rerun on real workload）。
3. **VC-022 行集无丢失契约的前提是文档化锁协议**（workers.lock/index.lock O_CREAT|O_EXCL）：裸写（不加锁的追加）在替换窗口内仍可能丢行——按设计文档，人工侧应走框架工具（TS WorkerStore / mw 脚本）。
4. **AC-005 静态扫描的限度**：写族段扫描覆盖字面目标写与 goal_path() 令牌；变量间接无法静态完全穷尽——与 `- Phase:` 字面量禁令组合后在源码级锁定；运行期由 L2 真时间线 exit 码复核。
5. **e2e_l2 默认排除**（pytest.ini `-m "not e2e_l2"`）：完整窗口跑一次 ~3 分钟，入口 `python test_autopilot_e2e.py`；MW_E2E_FAST=1 等占空比缩窗用于迭代。
6. **并行会话工作树改动**（launcher.py/mw_common.py/test_common.py/test_launcher.py，D-007/D-008 launcher beat）：不属于本 key；本次所有套件在含该改动的同一工作树上全绿，但其提交/收口由该会话负责。
7. ~~L3 dossier 裁决字段未单独断言~~ **已修复（QG 修复轮）**：done 事务与停派路径现写 l3-verdict.txt + l3-report.md，exec 套件断言 meets→done→dossier 裁决链（VC-005 新增）与 below 落盘。

## 6. 原样输出文件清单（evidence/）

- `baseline/baseline-manual-suites.md` — T-01 冻结基线（QG 工作流契约的目录形态）

- `l1-python-final.log` — L1 全量 363 passed
- `l1-verify-lines.log` — L1 [VERIFY] 提取面（107 行）
- `l0-parity-final.log` — L0 5/5（VC-007/VC-023）
- `l2-e2e-final.log` — L2 5/5（8 组 [VERIFY]，默认窗口）
- `vitest-autopilot-final.log` — TS autopilot 59/59
- `vitest-agent-team-loop-final.log` — TS 回归 106/106
- `e2e-real-final.log` — 真 timi 链路 1 passed
- `smoke-final.log` — smoke 9 PASS 0 FAIL
- `npm-check-final.log` — check 输出（coding-agent 零错误）
- 历史档：`l2-e2e-2026-09-10.log`、`l0-parity-2026-09-10.log`、`baseline/baseline-manual-suites.md`（T-01 冻结，2026-09-10 QG 前置门禁后由 evidence/ 根迁入目录形态）
