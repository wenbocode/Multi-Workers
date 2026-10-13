# PM State: autopilot 门禁提醒的存活性与可见性（mw-autopilot-gate-alarm-liveness）

- Phase: DONE
- Key: mw-autopilot-gate-alarm-liveness
- Claim-Id: WENBOZHOU-PC4:117296
- Created: 2026-10-13
- Updated: 2026-10-13 22:05
- Completed: 2026-10-13 22:05
- Baseline commit: 
cc9a46a1a
- 上游：H:\git\E2Feature\.agenticdoc\_autopilot\handoff-serve-drift-and-silent-stall-20261013.md（P0×2/P1×2/P2×1）+ reflect/A-20 + mw-dispatch-card-gate（DONE，同族反模式）

## 1. 立项依据（用户裁定 2026-10-13）

- 用户确认范围 **P0 + P1**（不含 P2 独立文档项，P2 并入 AC-005 自动化）。
- 用户裁定 killer #2 的修法方向：**不靠退避曲线**（"gate 时间不保险"），改为 **monitor 常驻提示**（状态面优先）。
- 用户裁定抑制粒度：按 gate 所属 key 判在飞；无法解析 key/stage 的 gate 一律不抑制。

## 2. 当前动作

- SPEC 阶段：4 个 research RQ 并行派发（T-01..T-04），各自只写唯一证据文件。
- 下一步：收齐 RQ 证据 → 定稿 spec（含可复用资产 §4 / 需规避坑点 §5）→ advance design。
## 3. 过程发现（PM 独立核对，2026-10-13）

- **RQ-3 终态为 `needs-clarification`，判定为假阳性**：`unrecorded write(s): serve.meta`。PM 核对：`serve.meta` 真实路径是 `.mw/serve.meta`（`mw.py:119`），仓库根下无同名文件（`Test-Path serve.meta` = False），该裸词在研究型报告里出现 **35 次**（全是"读取现状"的引用）⇒ 被误判为写入意图。**只读纪律实际守住**：`git status --porcelain packages` 为空。
- **C-36a（假阳性，判定方向反了）**：writeless 角色（`research`/`review`）的报告**天然充满被读取的路径名**，现行写入意图账本会把这些散文引用算成"未记录写入"。T-21 的修法（否定感知/按 worker 归属/词元卫生/dotless 存在性仲裁）覆盖的是 coding 语料，**未覆盖研究/评审报告这一类**。验证语料：`evidence/research/spec-rq3-serve-metadata-drift-20261013.md`（40,704 B / 233 行，含 `serve.meta` 35 处）。
- **C-36b（疑似假阴性，更严重）**：该 worker 的 `trace.log` 里 `[WRITE_FILE]` **只有** `progress.md` 与 `report.md` —— 它**真实写出的交付物**（`evidence/research/spec-rq3-...md`）**完全没有出现在写入事件里**。待定：是 `worker_file` 工具不落账，还是该文件写在 taskDir 之外（研究卡声明的唯一证据文件在 key 的 `evidence/` 下）时账本不覆盖。若为前者，则"改动历史（清单 ⊆ trace 事件）"这一判据存在**写入逃逸**：worker 可经该工具写任何位置而不留账。
- **次要**：worker 自述"357 行"，实测 **233 行**（自述数字不可信，PM 必须实测 —— 与既有教训一致）。
## 4. 范围裁定（用户 2026-10-13）

- **JCodingAss 与 FeatureMigrator 的现场运营动作不跟进**（不核那两个已等 25.3/17.0 天的 pending gate、不推动其 serve 重启）。本 key 只把它们当**只读取证语料**（E7 的 408h/212,609 事件/0 提醒、E9 的存量 gate 统计），不承担其修复与运营责任 —— 见 P-06。
- 因此本 key 的交付边界 = 框架侧能力（monitor 常驻状态面 + 提醒不再静默/整体抑制 + 漂移自检 + `stalled` 分类与重评 + 回收契约对 writeless 角色的判据），**不含任何具体项目的现场修复**。
## 5. 收口（2026-10-14，PM）

- Phase: EXECUTE → DONE，gate verdict: **PASS**
- 交付：16 张实现/修复卡 + 4 张研究卡 + 1 张对抗审计卡全部终态并 acked；`achieved.md`（`## 系统行为变化` / `## 遗留`）；`evidence/quality-gate-report-20261013.md`（AC-001…AC-016 逐条带证据：**11 成立 / 4 部分成立 / 0 判据放宽**）；`evidence/runs/closeout-runtime-actions-20261013.md`（生效清单）；`packages/multi-workers/docs/autopilot-observability-guide.md`（9 个可观测面 + 生效矩阵）。
- 对抗式 QG（`workers/mwgal-t18-adversarial-qg/report.md`）：11 项探针 + 8 条对抗用例；**探针 5 判定 `stage-close` 自动放行不可构造绕过**；探针 6 判定 48h 兜底从不闭合 stage 且与自动放行互补；探针 8 判定 `blocker_class` 五形态 fail-closed 且双语同向。QG 缺陷 **R-1…R-5 全部处置**（R-1 infra 白名单收窄为文件级并恢复框架文件越界检测；R-2/R-3/R-4 队列不可读三面不再静默显示 0 pending；R-5 跨主机不双重持有），R-6 随 R-1 关闭。
- 全局检查：`npm run check` exit 0（`Checked 1149 files … No fixes applied`）。
- 过程发现（PM 自我纠错 12–15，均已转成卡面规则）：① 卡面要求与所引 D 编号相反（我要求改 `== 40`，而 D6 要求序外注册）② 派发描述不得含卡面没有的要求 ③ 卡面交付格式必须含 `## 证据` ④ 验收命令里的测试文件必须实测存在（vitest 对不存在的 filter **静默 exit 0**）⑤ **行号锚点会漂移** —— P-07 v3 早已定"只用字符串锚"，本 key 仍复发，此后一律符号名锚。
- 上一 key 出厂缺陷（本 key 发现并由 T-20 修复）：`b65380d1b` 加入的 `envelope_fallback` 未同步 TS 注册表**与放行集合** ⇒ P5 锁自该提交起红着出厂；根因 **`npm run check` 不跑测试** ⇒ 收口判据须补"至少跑一次跨语言 parity 锁"。
- 未做（见 `achieved.md ## 遗留`）：cutover（`/mw restart`；TS 侧 `build --install` + `/mw restart` + `/reload`，**需用户执行**）；未提交；coding 角色宽别名过判；G-1…G-4；cutover 后应执行"派发 trivial worker ⇒ 账本零 gaps"的生效验收测试。