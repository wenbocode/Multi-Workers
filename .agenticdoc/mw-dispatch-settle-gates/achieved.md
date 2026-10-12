# Achieved — mw-dispatch-settle-gates

> key: `mw-dispatch-settle-gates`｜phase: VERIFY → 本文件为收尾账本｜日期: 2026-10-11
> 立项依据：上一 key `mw-gate-verdict-hardening` 完成后，用户要求对三个「框架侧需要修」的 reflect 归因做真实修复；
> 本 key 的 11 条 AC 覆盖 8 个缺口（G-a…G-h）+ 用户新增要求 R22/R23（派发期可满足性、产物自带终态、只读角色写面）。

## 0. 目标对齐（做什么 / 为什么）

| 用户口径 | 本 key 的落点 |
|---|---|
| ① 隔离：本 key 执行不得影响历史 worker | 执行期全程只写自身 key 目录；跨 key 守卫（AC-003）扩到 `/worker`；队列 9 列漂移每次派发后归一化（D-046 时代记录） |
| ② 影响评估 | `evidence/` 内 6 份调研 + T-12 收口报告的 AC 初判表 + 本文件 §3 残留账本 |
| ③ worker 产物自带状态：自报 done 者不得被重启 | AC-006（交付判据 ⇒ `exitCode 2`⇒`needs-clarification`）+ AC-004（派发前查 `run.json` 终态）+ T-07 launcher reap product-first |
| ④ PM 可读全局但只读（不写、不重派） | AC-003 的 `CROSS_KEY_READ_ONLY_SURFACES` = `dispatch_worker` / `/worker` / `advance_phase` 三面共用同一守卫 |
| ⑤ research 可写但限定目录 | AC-005b（bash 写面拦截 + `write_scope:` 契约 + deny 列表绝对优先） |

## 1. AC 状态（**机器判据 + 独立质量门双重判定**）

| AC | 内容 | 状态 | 判据来源 |
|---|---|---|---|
| AC-001 | `mw doctor` gates 段 `blocked_on_human` + 文本后缀 + 零写盘 | ✅ PASS | T-08 报告（14 passed）+ **PM 活体** `mw doctor --json` 实测字段存在 + `_blocked_on_human` 三轴读码（`:3123`）。**含 PM 勘误**：轴 3 与面板「同轴非同源」（有意收窄，已写入 spec） |
| AC-002 | gate 提醒第 4 条件（stage 终态不提醒，两级解析，fail-open） | ✅ PASS | T-09 报告（24 passed）+ PM 读码（`:2529-2530` / `:2561-2567` / `:565`）+ PM 独立读 `pending_gate_reminders` 全文 |
| AC-003 | `/worker` 前置守卫 + 共用判定 + 文案单一声明源 | ✅ PASS | T-01 报告（15 passed）+ PM 三面共用同函数读码 + sha256 字节等价 |
| AC-004 | 派发前首查 `run.json` 终态（零副作用拒绝） | ✅ PASS | T-10 报告（33 passed）+ **PM 自写 monkeypatch 对照** A/B 双红→还原绿 + 模块限定单一读取器 |
| AC-005a | 派发期拒绝不可满足的写意图 + 契约段注入 + 逃生阀 | ⚠️ PARTIAL | T-02 报告（18 passed，语料 `hits=2 FP=0`，PM 亲跑）；**QG-B 证伪两点**：A3 扩展名集（`:1346` 不含 `.toml`/`Makefile`/`.env`）、A4 白名单目录盲判（`:1423-1430` 先判 basename） |
| AC-005b | bash 写面拦截 + `write_scope:` + deny 优先 + 审计行 | ⚠️ PARTIAL | T-03 报告（14 passed + PM 42 passed 双套件）；**QG-B 证伪两点**：A2 变量重定向**误拦**（违反 spec「漏放而非误拦」承诺）、A1 `bash -c`/`>|`/`cp -t` 形态缺口 |
| AC-006 | 三级交付判据 ⇒ `exitCode 0\|2` + reap product-first + `no-product` 告警 | ✅ PASS | T-04 报告（14 passed，语料 `30/28/2/FP=0`，PM 亲跑）+ T-07（15 passed）+ PM 核 `hasProductEvidence` 未被替换 |
| AC-007 | `## Deliverables` 条件化 + `Exit Reason` 带努力度 | ✅ PASS | T-06 报告（199 passed / 2 files，PM 亲跑）+ PM 核 D-117 追加语义未动 |
| AC-008 | 文档勘误 6 处 | ✅ PASS | T-11 报告 + **PM 六处逐条复算**（含独立读 `config._INT_RANGES` 复算 1..64）+ PM 追加同族 1 处（上一 key plan:117「超限拒绝」） |
| AC-009 | 证据标准：`[VERIFY]` 带锚点 + 引用重锚 + 非空洞对照 | ✅ PASS | T-12（31 控制组 A/B/C 全红→绿、9 seam 用例、`verify_lines_anchored=81/81`、`reanchored_refs=35`）+ QG-A（抽 40+ 锚点全落地）+ **PM 勘误**：`evidence-requirement.md` 结果列已按实测重建（25 行实测原文 / 22 行显式标注「无实测行」） |
| AC-010 | 读侧取**末个非占位块** + 写侧 settle 幂等 | ✅ PASS | T-05 报告（11 passed + oracle parity `mismatches=0`）+ PM 亲跑 6 套件 96 passed + PM 核 4 读点与冻结契约 |

**统计：9 PASS + 2 PARTIAL（AC-005a / AC-005b）**，与上一 key 的记账口径一致（PARTIAL 不计为 PASS，且不掩饰）。

## 2. 交付物索引

| 类型 | 路径 | 说明 |
|---|---|---|
| 阶段文档 | `spec.md`（11 AC + §3.1/§3.2）/ `design.md`（DD-01…13、VC-001…046、契约 C1…C10）/ `plan.md`（6 波 + 契约 + 对照协议）/ `tasks/T-01…T-12` | 全部经 PM 复核 |
| 调研 | `evidence/research/*.md` ×6（spec×3、design×3） | 均由 worker 交付并经 PM 核对 |
| 收口 | `evidence/runs/t12-consolidation.md`（21,294 B）、`evidence/scripts/mwds-controls.ps1`（18,443 B） | 31 控制组 + 9 seam + 回归对比 |
| 质量门 | `evidence/quality-gate-evidence-chain-20261011.md`（31 KB，QG-A）、`evidence/quality-gate-code-adversarial-20261011.md`（29,903 B，QG-B） | 独立 review 角色，只读，唯一写入面 = 自身 `report.md` |
| 运行期 | `evidence/runs/r21l-cutover-20261011.md` | R21-L（`/mw restart`）生效验证 |
| 各卡证据 | `workers/<taskKey>/report.md`（13 个 worker 目录） | `[VERIFY]` 原文 + A/B/C 对照 |

## 系统行为变化（新增/修改功能与影响面 —— 供后续任务参考）

| # | 面 | 变化 | 影响面 / 反向保证 |
|---|---|---|---|
| 1 | `mw doctor --json` 与文本 | gates 段新增机器字段 `blocked_on_human`；文本仅在真时追加 ` BLOCKED_ON_HUMAN` | **已活体验证**（新子进程即时生效）；零写盘；pending=0 或存在非终态行 ⇒ false，健康项目文本逐字节不变 |
| 2 | `conductor.py` tick（gate 提醒） | 新增第 4 条件：门所属 stage 为终态 ⇒ **不提醒**（两级解析；解析不到 ⇒ 不抑制） | 默认不传 `stage_status`/`stage_of_key` 时**逐字旧行为**（fail-open） |
| 3 | `/worker` 与 `advance_phase` | 目标 key 为**他人 live 持有**时**拒绝**（与 `dispatch_worker` 共用同一守卫与同一声明源文案） | 拒绝发生在任何 mkdir/写盘/入队之前（零副作用） |
| 4 | `mw.py autopilot dispatch` | 派发前先读 `run.json`：终态（含 `lost`）或 `running` ⇒ 拒绝且零副作用 | 缺 `run.json` ⇒ 与实现前**逐字节相同**（零回填，P-018） |
| 5 | `research`（writeless + shell）worker 的 bash 写面 | P1 拦截：deny 列表**绝对优先**（`pm-state.md` / `_workers*` / `_index.parallel` / 其它 key / `packages/**` / `.git/**`），允许面 = 自身 taskDir + `<key>/evidence`，`write_scope:` 可进一步收窄；命中记 `[WRITE_SCOPE] …` 审计行 | **失败方向承诺 = 漏放而非误拦**（该承诺的「误拦」一半被 QG-B 证伪，见 §遗留 R3） |
| 6 | 派发期写意图判据 | writeless 且无 bash 的角色 + 任务书要求写外部路径 ⇒ **拒绝派发**（逃生门 `allow_foreign_write: true` 记入 frontmatter 供审计）；满足则注入契约段（成对 marker + 固定 3 行 + `write_scope:` 头） | `research` 永不被拒（只注入契约） |
| 7 | worker 交付判据 + launcher reap | 跑完无任何交付信号 ⇒ `exitCode 2` ⇒ 队列 `needs-clarification` + `dispatch-alarm{kind:"no-product"}`（写**真** `.agenticdoc` 根）；launcher reap 改为 **product-first**（`run.json` 终态优先于退出码） | `hasProductEvidence`（纯 `existsSync`，IN-3 守卫）**并存未替换** |
| 8 | `output.md` 段结构 | `## Changed Files` → 有产物时 `## Deliverables`（排除 `output.md`/`progress.md`）、无产物时**整段省略**（`(none)` 不再出现在该段）；`## Exit Reason` 追加 `writes=report.md\|progress.md\|none` | `output-writer.ts` 的「空则覆盖、非空则 `---` 追加」语义（D-117）**未动** |
| 9 | PM 面板终态详情 | 读侧改取**末个非占位块**（首块占位不再遮蔽真报告）；写侧 settle 幂等（同进程二次 settle 直接返回） | 冻结契约 `readOutputSection`/`readOutputSummary`（首匹配）**未动** |

**影响面提示（2026-10-11 18:12 更新）**：R21-H 已执行主体 —— bundle 已安装、Python 驻留进程已换新 ⇒ **新派发的 worker（launcher 以全新 `pi -p` 进程拉起）已运行在新守卫上**；第 1 项 `mw doctor` 由新子进程即时生效，第 2/4 项 Python 侧新调用即时生效。**仍待用户确认**：11 个长命 pi 交互窗口（含本会话 PID 117296）仍持旧 bundle ⇒ 其“在窗行为”未切换 —— 见 §遗留 R1。

## 遗留（未完成项 + 明确去向；**不得写作已修复**）

| # | 残留 | 出处 | 影响 |
|---|---|---|---|
| R1 | **R21-H 已执行主体（2026-10-11 18:12，见 `evidence/runs/r21h-cutover-20261011.md`）**：bundle 已装（`1,010,380 B` / sha256 `5DCBD0A4…5BA6`）+ Python 驻留进程已换新（serve 22420 / launcher 146856，均 18:12:55）。**未完成：11 个 pi 窗口仍持旧代码**（待用户确认是否重启；worker 由 launcher 以全新进程拉起，已加载新 bundle）。原文：`mw build --install` + 重启陈旧窗口 | plan §6、design R-05、pm-state D-026/D-050 | 本 key 的 **TS 侧守卫（AC-003/005a/005b/006/007/010）在运行期不生效**（installed bundle 仍是 2026-10-10 11:40:42 版）⇒ 只在源码/单测级成立，**done ≠ 上线** |
| R2 | P2（OS 级进程隔离）不在本 key 范围 | spec §2 非范围、design R-01 | research 的 bash 写面只做 P1（模式判据），非内核级隔离 |
| R3 | **A2 方向违约**：`echo x > $T`（指向自身 taskDir）被误拦 | QG-B F-2，PM 已复现 `worker-mode.ts:823/960/975` | 与 AC-005b「失败模式 = 漏放而非误拦」的承诺相反（漏放的一半守住、误拦的一半未守住） |
| R4 | **A1 形态缺口**：`bash -c '/sh -c / cmd /c / powershell -Command`、`>\|`、`<>`、`cp -t` | QG-B F-1，PM 已复现 `:733/:821/:786-790/:888` | 「已分类模式自身的形态漏洞」⇒ 可绕过写面拦截 |
| R5 | **A3 扩展名集**：`config.toml` / `Makefile` / `.env` 等零命中 ⇒ fail-open 放行 | QG-B F-3，PM 已复现 `ui-bridge.ts:1346` | AC-005a 的不可满足写意图漏检 |
| R6 | **A4 白名单目录盲判**：basename ∈ 白名单即放行（不看目录） | QG-B F-3，PM 已复现 `ui-bridge.ts:1423-1430` | 外部路径任务书可被判满足 |
| R7 | **A8 角色可被任务书自我翻转**：`parseTaskMd` 全文件逐行 + `type:` 后者胜出 | QG-B，PM 已复现 `worker-mode.ts:331-335` | AC-005a/005b 判据的输入 = 被审文本 ⇒ **判据可被自我关闭**（PM 定级高于 QG-B） |
| R8 | A5 `_`/`.` 前缀 key 豁免跨 key 守卫（`ui-bridge.ts:250`）；A6 key 大小写（`index-store.ts:159-161`）；A7 `_index.md` 隐式兜底 | QG-B（A5/A6/A7，PM 复现 A5，A6/A7 未复现） | 上一 key AC-024 守卫的形态加固 |
| R9 | A9 引用旧 `evidence/**` 的反伪造轴在缺 `run.json` 时关闭；A10 面板/doctor 无 timeline 分叉（**文字已勘误，行为未改**）；A11 跨 stage 重复 key 声明 | QG-B（PM 未逐条复现） | AC-006/AC-001 的边界增强 |
| R10 | 14 条未覆盖分支 + 2 条偏空洞断言（`DELIVERABLE_PLACEHOLDERS.size` 计数自证、t03 模式覆盖断言面薄） | QG-B §⑤ | 测试强度 |
| R11 | plan C2 的 marker 消费端不存在（幂等由 regex 保证） | QG-B §④，PM 已复现（全仓无消费端） | 契约文本与实现不符（已在 plan 加勘误） |

**处置建议**：R3–R11 属同一主题「守卫形态加固」，建议开新 key（候选名 `mw-guard-form-hardening`）**待用户批准**；
R1/R2 需用户决策（R1 = `mw build --install` + 重启 9 个陈旧窗口）。

**去向**：R1/R2 **需用户决策**（R1 = `mw build --install --allow-dirty` + 重启 9 个陈旧窗口；R2 = 明确不在范围，接受不处理）；R3–R11 **立新 key**（候选名 `mw-guard-form-hardening`，待用户批准）；两项偏空洞断言与 14 条未覆盖分支随该新 key 一并处理；本 key 的实现缺口**不记入 `_pitfalls.md`**（已在本表逐条具名，避免重复登记）。

## 4. 本 key 的验证事实（可复算）

| 判据 | 实测值 | 复算方式 |
|---|---|---|
| `npm run check` | **rc 0**（`Checked 1119 files`） | PM 亲跑（含 PM 直执的 1 行 lint 修复：`worker-mode.ts:905` `useOptionalChain`） |
| 全量 Python | **2 failed / 1579 passed / 10 deselected** | PM 亲跑；两条红 = `test_baseline_left_end_bound`、`test_true_below_without_resume_stays_below`（既有基线，非本次引入） |
| TS 卡片套件 | **304 passed**（9 文件，PM 亲跑） | T-01…T-06 + T-12 seam + read-scope + `agent-team-loop.test.ts` |
| T-12 收口 | `verify_lines_anchored=81/81`、`reanchored_refs=35`、`control_groups=A/B/C`（A=11/B=10/C=10 全红→绿）、`ts=903_passed/14_env_baseline`、`new_reds=0` | `evidence/runs/t12-consolidation.md` + PM 复核其前后对比方法论 |
| 冻结面 | 11 个落点 sha256 逐一复算，**0 drift** | PM（含 PM lint 修复后的 `worker-mode.ts abbba40b…`） |
| 质量门 | QG-A：5 ✅ + 1 ⚠️ + 0 ❌；QG-B：11 攻击 / 4 证伪成功 / 12 seam 判定 / 2 空洞断言 / 14 未覆盖分支 | 两份报告 + PM 逐条复现高危项 |

## 5. 结论

- 11 条 AC 中 **9 条 PASS、2 条 PARTIAL**；两个独立质量门**未能证伪**任何一个已实现守卫的**正向机制**（存在性、落位、方向性文档一致性、单点写盘、fail 语义），
  但证伪了 AC-005a/AC-005b 的**完整性假设**（4 项绕过 + 1 项方向违约），并发现 11 项硬化残留。
- 本 key 的产出**在源码与测试级成立**；运行期生效需先做 **R21-H**（待用户批准）。
- 未修项已全部登记在 §3，**没有任何一项被表述为已修复**。
