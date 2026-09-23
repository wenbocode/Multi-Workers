# Quality Gate Report: mw-target-partition

**时间**: 2026-09-19T14:30+08:00
**触发**: PM verify 阶段（两轮：mwtp-verify-gate FAIL → BLOCKER 处置 → mwtp-verify-gate-2 复核 PASS）
**范围**: 全量（spec §3 生效 AC 21 条：AC-001~013、AC-016~020、AC-022、AC-023；AC-014/015 OBSOLETE；VC 20 条）

## 前置门禁

| 检查项 | 状态 | 说明 |
|--------|------|------|
| spec.md AC 编号 | ✅ | 22 行（21 生效 + 2 OBSOLETE 标注；021 未分配） |
| design.md VC 映射 | ✅ | D-001~D-013 回链 AC；VC-001~013/016~020/022/023 全声明，mermaid 门禁 PASS，AC 覆盖 22/22 |
| AC→VC 覆盖 | ✅ | 21 生效 AC 全部有 VC；OBSOLETE 两条不要求 |
| evidence-requirement.md | ✅ | 指纹 `7b09f3e5e571`（AC-007 [REVISED] 后重算，与质检 A 项独立重算一致） |
| tasks/*.md | ✅ | 12 文件 BACKFILLED 归档（首轮质检 FAIL 项 4 → 已处置，复核 B4 PASS） |
| evidence/baseline golden | ✅ | S0 双侧 16 条 golden，实现后逐字节 MATCH（VC-016） |

## 质检轮次

**第一轮（mwtp-verify-gate，gpt-5.6-sol，独立评审）**: QUALITY GATE: **FAIL**（4 BLOCKER）
- A 指纹一致性 PASS；C 独立重跑 PASS（Py 145 / TS 134）；D 红线核验 PASS（fixture 001~014 零修改、6 删行全为 runner 空值容差、mw.py v1 路径零回归、P-002 无违规）
- BLOCKER 1: E2E 未覆盖真实 worker spawn/profile 注入（spec §0 收益判定条件缺口）
- BLOCKER 2: VC-013 reviewer 签署未落盘
- BLOCKER 3: 偏差清单缺 3 项（design §9 口径精化、签署缺失、E2E 缺口）
- BLOCKER 4: tasks/ 目录缺失（phase audit FAIL）

**处置（PM + worker mwtp-e2e-spawn）**:
- B1 → 真实 spawn E2E：独立 launcher + 真实 pi worker（glm-5.3，22s，exit=0）spawn 于分片根，cwd-evidence.txt = 分片绝对路径；v2 profile 经 **dist 产物** dispatchTask 真实注入（`<!-- mw-profile: v2 -->` + `[mw] mode: partition` + Parent/Partition/Named roots）；trace/output/worker.log 写回控制根 .agenticdoc；config-torn 负路径（任务 failed 含 `config torn`、无 [START]、无 pi 进程）。证据 evidence/e2e-spawn-2026-09-19.md
- B2 → verify-run §6 Reviewer 签署节（第一轮 D 项四条结论结构化落盘）
- B3 → verify-run §5 条目 7/8/9 补记（B2/B1 处置后闭环）
- B4 → tasks/ 12 文件 BACKFILLED 归档（T-00~T-11，ac/vc refs 对齐 spec）

**第二轮复核（mwtp-verify-gate-2，gpt-5.6-sol）**: QUALITY GATE: **PASS**（B1~B4 全 PASS，时间序列/PID/清理记录核验一致；phase audit PASS；VC 覆盖全）

**终审三轮（mwtp-final-review / -2 / -3，gpt-5.6-sol，代码级 review+gate）**:
- 第一轮：REVIEW+GATE **FAIL**（5 BLOCKER + 3 MAJOR + 1 MINOR：conductor 派发无 profile 绕过撕裂、同 mode 配置变化陈旧 profile、malformed v2 块 fail-open、partition show 无文件 exit 0、非字符串 roots 键 parity；target clear v2 删整文件、非 mapping YAML 迁移覆盖、.bak 非原子）
- 处置：mwtp-final-fixes 修复 8 项，M6 WONTFIX（AC-019 锁定 marker→EOF 边界为规格契约）；PM 逐条实测核实前提成立后才派发
- 第二轮复核：8/9 PASS，残留 1 BLOCKER（YAML null fail-open——PM 核实为历史行为与 fail-closed 的交叉：空文件→single 必须保留，`null\n` 内容应拒）+ 3 覆盖欠债（块头注释不容忍、roots 值非字符串无夹具、conductor profile 无全文 parity）
- 处置：mwtp-final-fixes-3（4 项）+ PM 跟进（BOM-only 文件历史也是 single，补双侧 BOM 剥离分支与测试）
- 第三轮复核：REVIEW+GATE **PASS**（FIX-10～13 全闭环；独立实测 0 字节/BOM-only/null 三态；回归扫描无超纲；全部基线 MATCH）

## AC/VC 勾销清单

| AC | VC | 证据 | 状态 |
|----|----|------|------|
| AC-001 | VC-001 | parity 夹具 39 case（015~039 新增）双侧逐字段 | ✅ 充分 |
| AC-002 | VC-002 | 夹具 error case + runner 断言消息要素 | ✅ 充分 |
| AC-003 | VC-003 | 结构层 7 类（混格式/active 值/双层白名单/块间错放/roots 键名/根关系相等与互嵌）夹具 case | ✅ 充分 |
| AC-004 | VC-004 | 渲染分派 case（034 等）+ dual 零变化（S0 golden） | ✅ 充分 |
| AC-005 | VC-005 | 027/028/033 夹具（EP 子集覆盖/空白串/dual env） | ✅ 充分 |
| AC-006 | VC-006 | test_partition_dispatch（cwd）+ **真实 spawn E2E**（cwd-evidence.txt） | ✅ 充分 |
| AC-007 | VC-007 | profile-injection describe 6 用例 + E2E 注入全文（v2 标记/mode 行） | ✅ 充分 |
| AC-008 | VC-008 | test_partition_dispatch（scope 锚定/不并 parent） | ✅ 充分 |
| AC-009 | VC-009 | doctor checks + 指纹重探测用例 | ✅ 充分 |
| AC-010 | VC-010 | test_mw_partition（set 三路/迁移 .bak 440 字节完整/拒绝路径）+ E2E 步 a/f | ✅ 充分 |
| AC-011 | VC-011 | test_mw_partition（缺参/clear 三态/块缺失 exit 0） | ✅ 充分 |
| AC-012 | VC-012 | agent-team-loop "/mw partition" describe（fake runner 参数序列）+ Py set 输出确定性 | ✅ 充分 |
| AC-013 | VC-013 | 四类证据：全绿（Py 660/TS 377）+ 零修改审计（fixture 001~014 零改动、6 删行归类）+ reviewer 签署（verify-run §6）+ VC-016 golden | ✅ 充分 |
| AC-016 | VC-016 | S0 双侧 golden 16 条，实现后 MATCH（[BASELINE] MATCH ×4） | ✅ 充分 |
| AC-017 | VC-017 | active-mode-table.json 112 组合双侧同表（规则行 2/3/5~12）+ 行 1/4 入口测试 | ✅ 充分 |
| AC-018 | VC-018 | 守卫（target show exit 1）+ mode 行（注入/E2E）+ partition-only 键（doctor 用例）+ 指纹随切换失效 | ✅ 充分 |
| AC-019 | VC-019 | profile-injection AC-019 用例（切换整体替换/同配置幂等；专用 [VERIFY] 行偏差已记录） | ✅ 充分（偏差记录在案） |
| AC-020 | VC-020 | test_partition_dispatch 撕裂四场景 + **E2E 负路径**（真实 failed 无 spawn） | ✅ 充分 |
| AC-022 | VC-022 | 同参幂等/手维护段保留/原子替换/.bak 完整用例 | ✅ 充分 |
| AC-023 | VC-023 | on/off 全矩阵用例 + E2E 步 d（off→single 块保留→on）+ v1 报错 | ✅ 充分 |

## 测试/静态核查基线（2026-09-19 终审三轮后最终）

- Py 全量：**677 passed, 8 deselected**（S0 前基线 579 → 净增 98）
- TS extensions 目标 8 文件：**387 passed**（基线 365 → 净增 22；并发 key 新增文件后全目录 393，本 key 目标集仍 387）
- parity 夹具：**44 cases**（001~044，双侧 [PARITY] 一致）+ active-mode 参数表 112 组合 + partition profile 全文 parity golden（753 字节，双侧逐字节 MATCH）
- npm run check：exit 0，biome 零 findings，tsgo 0 错误
- dist bundle：三轮后重建（含 BOM 分支）+ coding-agent dist 对齐
- 独立重跑（各轮质检）：Py 145/660/670/677、TS 134/377/382/387 目标族全绿
- YAML 顶层语义钉死（终审产出）：0 字节/纯空白/BOM-only → single/default（历史）；`null\n`/`~\n`/list/标量 → invalid-config；双侧同构同文案

## 已记录偏差（非阻塞，verify-run §5 台账）

1. AC-007 v2 标记仅 partition 注入（dual 维持 v1，保 AC-016d 逐字节）——spec 已 [REVISED @ 2026-09-19]
2. 撕裂校验 v1 块按 `Game root:` 行判 mode（防 single+sections 误判）——test_single_injected_v1_block_not_torn 锁定
3. design §9 VC-013 证据口径精化（语义红线对齐）
4. doctor E2E exit 1 唯一 issue 为环境性 service-not-running（target 段全绿）
5. VC-019 无专用 [VERIFY] 行（用例级覆盖，偏差已记录）
6. yaml round-trip 迁移排版（.bak 兜底 + AC-022 内容级断言）

## 结论

**QUALITY GATE: PASS**（证据链三阶段：S4 终验 → 两轮证据质检 → 三轮终审代码评审收敛，最终判 REVIEW+GATE: PASS，mwtp-final-review-3）——21 条生效 AC 证据充分；零回归三层保障（既有用例零语义修改 / S0 golden 逐字节 / 规则表行 8 v1 语义钉死）；真实 spawn E2E；conductor 注入与 Py/TS 逐字节 parity golden；fail-closed 三态撕裂 + YAML null/BOM 语义钉死。
