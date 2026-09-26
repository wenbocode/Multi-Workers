# T-13: doctor gate 段（I1–I8）+ `mw autopilot gates --json`

- 波次: **2** · 依赖: T-03, T-09, T-12
- 写面（独占）: 
  - `packages/multi-workers/mw_common.py`（`_doctor_gates` 段）
  - `packages/multi-workers/mw.py`（autopilot 段）
  - `packages/multi-workers/test_doctor_gates.py`（新建）
- AC: AC-006, AC-012, AC-019, AC-031 · VC: VC-007, VC-014, VC-024, VC-049
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

给门一个机器出口与告警面：今天"门文件坏了"只在 timeline 留 `config` 事件、doctor 静默（这正是"零 gate 内容"缺口的第一个补面）。

## 交付物

- `_doctor_gates`（邻 `mw_common.py:2022-2064`，对齐 `_doctor_autopilot` 范式）：段字段 9 类（`dir/exists/total/pending_count/schema_versions/parse_errors/pending[]/missing_fields[]/drift[]/replayed[]/error`）。
- 告警 I1–I6（解析错 / 缺 `expires_at`+`default_action` / 超 24h（>72h 升级 issue）/ 漂移 / 重放 / schema2 缺字段）+ 零扰动 I7/I8（全绿文本层不出行；`missing_fields` **仅 pending 门**）。
- 文本层一行 `gates: {pending} pending ({oldest} oldest, {n} parse error(s), {n} drift)`，仅在 I1–I6 命中时输出；exit code 由既有 `summary.healthy` 驱动。
- `mw autopilot gates [--json]`：层 B 的机器出口（固定 13 行序）。
- roadmap 校验可见性（AC-031）：`validate_roadmap` 结果进入 doctor 面（现唯一调用点是 `roadmap_check.py:50`，conductor 从未调用）。

## 契约（不得重定义）

- **只读零写**：不得创建目录/文件（`_doctor_autopilot:2025-2034` 纪律）。
- 不在 doctor 里做自动裁决（只告警 + 修复串）。
- `replayed[]` 与层 B L8 同源判据。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_audit.py -q`

## 非空洞对照（必须附在回执里）

- fixture 删掉门的必填字段 ⇒ I1 命中、修复串含 `fix the frontmatter`、exit code 变 1。
- 全绿项目（无 pending 无错）⇒ 段存在、`healthy=true`、**文本无 `gates:` 行**（零扰动）。
- 跑 doctor 前后目录快照一致 ⇒ 零写断言（新建目录即红）。
- 旧格式 roadmap ⇒ 校验问题可见（`validate_roadmap` 未被调用的问题在此关掉）。

## 风险与注意

- `mw_common.py` 与 T-12 同文件 ⇒ 串行；`mw.py` 的 autopilot 段与上一 key 的 CLI 面相邻，勿动既有子命令（`test_mw_autopilot_cli.py` 必须全绿）。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-13-doctor-cli/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
