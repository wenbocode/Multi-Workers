# T-09 · 结案：`achieved.md` + quality-gate report + 记忆回写（PM 直执）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「项目级目标对齐」「Worker 执行过程中追踪 goal 一致性」）——结案必须回答「系统行为变了什么」与「遗留去哪」，否则下一轮 worker 无从继承。
- **本卡由 PM 直执**（不派 worker）。
- 门禁要求（`advance_phase.py` 的 `done` 闸，实现锚点 `.claude/scripts/advance_phase.py:191` 的 `check_gate`）：`achieved.md` ≥ 200 B 且含「## 系统行为变化」与「## 遗留」；`pm-state.md` 含 `PASS` 证据；`evidence/quality-gate-report-*.md` ≥ 1 份。
- 前置：T-08 done（部署生效 + AC-010(b) 全绿）。
- 记忆回写：`_framework-reflect.md` FW-001 的状态更新（AC-014 的「另一契约数字」误引已由 PM 在设计阶段更正，结案须把 FW-001 标为已闭合）与 FW-009 的修法落地记录；`_pitfalls.md` 回写本 key 新踩到的坑。

## 写入允许面

- `.agenticdoc/mw-worker-output-contract/achieved.md`（新建）
- `.agenticdoc/mw-worker-output-contract/evidence/quality-gate-report-*.md`（新建）
- `.agenticdoc/_pitfalls.md`
- `.agenticdoc/_framework-reflect.md`

## 写入禁止面

其余一切路径。特别地：`packages/*/src/**`、`packages/*/test/**`、其它 key 目录只读；`goal.md` **只读**（低 churn，只允许 `/goal` workflow 或用户显式指令改）。

## 要求

1. **`achieved.md`**：必含 `## 系统行为变化`（新增/修改功能与影响面，面向后续任务参考；AC 勾销由 quality-gate-report 承担，不在此复读）与 `## 遗留`（遗留项 + 明确去向：立新 key / 记入 `_pitfalls.md` / 接受不处理）。另附：AC-001…AC-017 的兑现位置索引（哪份证据/测试文件）、`## 系统行为变化` 必须点名五切面（写面 / 账本 / 检查点 / 判定 / 回读）。
2. **`evidence/quality-gate-report-*.md`**：全 AC 勾销表 + VC（若有）+ 证据链溯源 + 未覆盖面声明；引用 T-07 的矩阵结果与 T-08 的 ≥6 新产物 `exit=0` 表格。
3. **`_framework-reflect.md`**：FW-001 状态更新为已闭合（含 AC-014 更正的落点）；FW-009 记录修法落地（检查点判据改用落盘信号）。只追加/就地改这两条的状态字段，不动其它条目。
4. **`_pitfalls.md`**：把本 key 新踩的坑按既有 `P-NNN` 格式追加（至少：抽取器误拦合法只读命令的现场、`notified` 兼任每任务一次界的陷阱）。
5. **人工步骤显式列出**：每个已打开的 pi 窗口 `/reload`（引用 T-08 的记录）。
6. **`pm-state.md`** 更新 Task Status 与 Decisions（D-009+），写入 `PASS` 证据行。
7. 全部 AC 勾销后：`advance_phase(key, verify)` → `advance_phase(key, done, summary=…)`。

## 交付格式

`achieved.md` 按上文两节 + AC 索引；quality-gate report 为独立文件。报告正文里给**证据指针**（`evidence/…` 路径 + `file:line`），不复读 AC 正文。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers
python -X utf8 .claude/scripts/audit_phase.py mw-worker-output-contract
python -X utf8 .claude/scripts/verify_project_memory.py
git diff --stat -- .agenticdoc
```

（相位推进只用 `advance_phase.py`；`done` 的目标相位参数由 PM 走本窗口的 `advance_phase` 工具。）

## 改动历史

- 2026-10-14 plan §3 批次 C 定义；`_framework-reflect.md` FW-001 的误引更正在 spec 阶段（AC-014）已执行一半，结案须闭合状态。
