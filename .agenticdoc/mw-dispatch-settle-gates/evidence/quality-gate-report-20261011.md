# 质量门报告 — mw-dispatch-settle-gates

- 日期: 2026-10-11｜key: `mw-dispatch-settle-gates`｜phase: VERIFY
- 判定: **PASS（含 2 条 PARTIAL）** —— 11 条 AC = **9 PASS + 2 PARTIAL（AC-005a / AC-005b）**
- 前置: 12/12 张实现卡全部完成、逐卡经 PM 独立核验（每卡 ≥5 项证据，含 sha256 字节等价 + PM 亲跑测试 + PM 自写对照）；
  `npm run check` rc=0（PM 直执 1 行 lint 修复）；全量 Python `2 failed / 1579 passed`（两条既有红）。

## 1. 质量门方法（不采信实现者自述）

| 手段 | 做法 | 覆盖 |
|---|---|---|
| 独立 review worker ×2 | 只读角色（read/find/grep/ls，无 bash），唯一写入面 = 自身 `report.md`；任务书显式要求「攻击/证伪」而非「复述」 | QG-A 证据链（40+ 锚点、11 AC × 46 VC × 12 卡三方对账）、QG-B 代码对抗（11 攻击 / 13 方向性 / 12 seam / 空洞断言 / 未覆盖分支） |
| PM 逐条复现 | 对 QG 的高危结论**自己翻源码/跑测试**，不转述 | A1/A2/A3/A4/A5/A8/C2/C7（QG-B）+ VC-019 声明串（QG-A） |
| PM 亲跑判据 | 全量 Python、9 个 TS 套件、`npm run check`、`mw doctor --json` 活体 | 见 §4 |
| 冻结面核验 | 11 个落点 sha256 逐一复算 | 0 drift |

## 2. QG-A（证据链）结论

| 项 | 判定 | 依据 |
|---|---|---|
| `[VERIFY]` 锚点真实性 | ✅ | 抽 40+ 锚点覆盖全部实现卡，逐一翻到源文件全部落地；Python 12 锚零漂移；TS 漂移与 T-12 §6 重锚表吻合；81 条数据行计数复核 = 81 |
| AC 覆盖完整性 | ✅ | 11 AC × 46 VC × 12 卡对账无缺口、无撞号 |
| AC-009 证据纪律 | ⚠️ → **PM 勘误后 PASS** | 卡片层成立（31 控制组脚本实存）；但 `evidence-requirement.md` 抽 8 行中 5 行的引号机器行是 design §7 **声明串**而非实测原文（VC-019 最重）。PM 已按各卡 `report.md` 实测行**重建 25 行**、对其余 **22 行显式标注「无实测行」**，并在文件头部加勘误说明 |
| AC-008 六处勘误 | ✅ | 逐处翻原文验证；PM 追加同族 1 处（上一 key `plan.md:117`「超限拒绝」→「截断至 N」） |
| T-12 PARTIAL 闭环 | ✅ | `worker-mode.ts:905` 现为 `previous?.startsWith("-")`，pm-state D-042 记录完整修复链 |
| 诚实性 | ✅ | 18 项自报偏差全部有下落（D-023/028/031/033/036/042 或 T-12 §7），无静默略过 |
| 无法核实项 | 已声明 | 全部 sha256 / 测试执行 / 活体 doctor / 字节数（无 bash）——显式列出，未采信未猜测 |

## 3. QG-B（代码对抗）结论 + PM 复现

**正向机制未被证伪**：6 个落点的守卫存在性、落位、方向性与文档一致、单点写盘、fail-open/closed 语义，逐行读码成立，无「文案写了没实现」回归。

**被证伪项（PM 已逐条复现）**：

| 项 | PM 复现证据 | 判定与影响 |
|---|---|---|
| A2 方向违约（**最重要**） | `worker-mode.ts:823` 收字面 `$T` → `:960 normalizeForCompare` → `:975` 不在 taskDir ⇒ block | 违反 spec AC-005b 明文承诺「漏放而非误拦」；AC-005b ⇒ **PARTIAL** |
| A1 形态缺口 | `:733` 包装器集合无 `bash/sh/cmd/powershell/perl`；`:821` 只认精确 `>`/`>>`；内联脚本扫描唯一调用点 `:888`（python/node） | 已分类模式（重定向/复制）自身形态漏洞 ⇒ AC-005b PARTIAL |
| A3 扩展名集 | `ui-bridge.ts:1346` 仅 `md\|py\|ts\|json\|ya?ml\|log\|txt\|ps1\|sh` ⇒ `config.toml` 零命中 | AC-005a PARTIAL |
| A4 白名单目录盲判 | `:1423-1430` 先判 basename 再判目录 ⇒ `../other-key/.../output.md` 放行 | AC-005a PARTIAL |
| A8 角色自翻转（**PM 升级定级**） | `parseTaskMd:331-335` 全文件逐行、`type:` 后者胜出 | 判据输入 = 被审任务书文本 ⇒ 可自我关闭；AC-005a/005b 共同的可信度约束 |
| A5 `_`/`.` 前缀豁免 | `:250` 直接 return null | 上一 key 跨 key 守卫的形态加固项 |
| C2 marker 无消费端 | 全仓 `WRITE_SURFACE_MARKER` 仅定义/渲染/清理（`src/` 零消费） | 契约文本与实现不符（plan 已加勘误） |
| C7 计数 16 vs 15 | `DELIVERABLE_PLACEHOLDERS` 实测 16 字面量 | 已在 plan 加勘误 |

**PM 未逐条复现**（诚实标注，不写入 PASS 依据）：A6（key 大小写）、A7（`_index.md` 隐式兜底）、A9（反伪造轴）、A11（跨 stage 重复 key）；A10 的行为差异早由 T-08 自报为有意收窄，文字已勘误。

## 4. 机器判据（PM 亲跑）

| 判据 | 实测 |
|---|---|
| `npm run check` | rc 0（`Checked 1119 files`；biome + pinned-deps + ts-imports + shrinkwrap + install-lock + `tsgo --noEmit` + browser-smoke） |
| 全量 Python | `2 failed / 1579 passed / 10 deselected`（200.58 s）；红 = `test_autopilot_readcap_injection.py::test_baseline_left_end_bound`、`test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` |
| TS 卡片套件 | `304 passed`（9 文件） |
| 活体 doctor | `mw doctor --json` rc=0 且 `gates.blocked_on_human=False`（pending=0 ⇒ 口径正确） |
| 冻结面 | 11 落点 sha256 = 记录值（`worker-mode.ts` 因 PM lint 修复 = `abbba40b…`） |
| T-12 收口 | `verify_lines_anchored=81/81`、`reanchored_refs=35`、`control_groups=A/B/C`（A=11/B=10/C=10）、`ts=903 passed/14 env`、`new_reds=0` |

## 5. 残留与未修项

**未修 11 类**（详见 `achieved.md` §3 R1–R11）：R21-H 未做（TS 守卫运行期不生效）、P2（OS 级隔离）不在范围、
A2 方向违约、A1 形态缺口、A3 扩展名集、A4 目录盲判、A8 角色自翻转、A5/A6/A7（跨 key 守卫形态加固）、
A9/A10-行为/A11、14 条未覆盖分支 + 2 条偏空洞断言、C2 消费端缺失。

**处置**：R3–R11 为同一主题「守卫形态加固」，建议新 key（候选名 `mw-guard-form-hardening`）**待用户批准**；
R1/R2 需用户决策。**本 key 的任何产出都不得表述为已上线。**

## 6. 判定

- **PASS（含 2 条 PARTIAL）**：所有 AC 的正向机制成立且有独立证据；AC-005a/AC-005b 的**完整性假设被证伪**，如实记为 PARTIAL 并转入残留。
- 质量门本身的两条 ⚠️（AC-009 证据清单声明串、AC-001 同源措辞）已由 PM 勘误闭环（改文档，不改判据）。
- 本报告的每一条 PASS 都可由 §4 的命令复算；每一条 PARTIAL/残留都指向 §5 的具体条目。
