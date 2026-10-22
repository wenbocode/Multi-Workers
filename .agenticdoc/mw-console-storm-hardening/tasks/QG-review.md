# QG — 质量门审读:console storm hardening 全量交付

- key: mw-console-storm-hardening · type: review · 波次 4（VERIFY 相位质量门）
- timeout: 75

## 上下文

goal.md（.agenticdoc/goal.md）GC-1..GC-4；spec.md AC-001..010；design.md D-001..D-006 + M1..M8 + VC-001..010；evidence/runs/verify-mw-console-storm-hardening-20261015.md（声称全 PASS，本审独立核验）。修复目标：Windows 控制台窗口风暴（H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md §8-B）。四层交付：L0 spawn 除雷 / L1 run-detached 监督进程 / L2 子树 console guard / L3 文档+守卫测试；TS 侧工具与命令入口。

## 审计目标

1. **L0/L1**：`packages/multi-workers/mw.py:485`（cmd_start 改点，:519 起重定向）+ `packages/multi-workers/console_run.py:1`（全文 ~260 行）——flags 组合语义、marker/heartbeat 原子写（P-003：禁 `open(p,"w")` 截断，须临时文件+rename）、timeout taskkill /T 树杀、run-dir 竞争（-N 后缀 O_CREAT|O_EXCL）、GC-3（监督进程崩溃不影响主服务）、GC-4（无中心调度器）。
2. **L2**：`packages/multi-workers/mw_console_guard/mw_console_guard.py:1`——OR 语义（creationflags=0 → 加 CREATE_NO_WINDOW；显式 NEW_CONSOLE/DETACHED 原样）、fail-open（patch 异常 → 告警+放行）、幂等、`del os, sys` 已知权衡仅此一例、creationflags 位置传参不保护且全仓零该形态。
3. **TS**：`packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts:1` + 三注册点 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1774` / `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2788` / `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3440`——GC-2（不碰 pi 核心）、TOOL_ALLOWLISTS 未改（T-17 parity）、erasable TS、无 inline import、fail-open 不穿透、shell-only 门控真实接线（applyRagTools 链）、schema additionalProperties:false。
4. **测试**：`packages/multi-workers/test_console_storm_guard.py:1` + `packages/multi-workers/test_mw_console_guard.py:1` + `packages/coding-agent/test/extensions/agent-team-loop-run-detached.test.ts:1`——断言真锚定 VC 行（对照 verify 文档引用）、tokenize 剥注释是否误伤字符串字面量、posix skip 是否过宽。
5. **硬规则**：P-001 合规（含 W-05 用 Python 落盘替代 write-face 拦截的合规性复核）、Python 显式 `encoding="utf-8"`、新测试已跑过（对照 verify 文档输出）。
6. **证据一致性**：verify 文档 vs 磁盘——README 新节、UPDATE 矩阵行、双 CHANGELOG 追加位置正确且不动已发布节、审计表 10 处行号更正抽 3 处实核。

## 未覆盖面声明

不重跑大套件（verify 文档已含 455s 全量）；不实测 POSIX 与真实长跑 serve-console.log 轮转；不审计本 key 之外的并行改动；不验 FeatureMigrator（§8-A 已移交）。

## 要求

按审计目标 1-6 逐项出具 blocker/major/minor/note 分级结论（每条带 文件:行号 + 一句问题 + 建议处置），最后给 QG 判定。

## 唯一证据文件

- `.agenticdoc/mw-console-storm-hardening/evidence/review/qg-console-storm-20261015.md`（新建，全文中文，含逐项分级结论 + 判定行 `[QG] verdict=... blockers=n majors=n minors=n notes=n`）

## 写入允许面

- `.agenticdoc/mw-console-storm-hardening/evidence/review/qg-console-storm-20261015.md`

## 写入禁止面

- 一切源码/测试/文档（只读审读）；禁止 git add/commit；禁止改任何代码

## 验收命令

```bash
cd H:\git\Multi-Workers
python -c "import pathlib; t=pathlib.Path('.agenticdoc/mw-console-storm-hardening/evidence/review/qg-console-storm-20261015.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('verdict line:', [l for l in t.splitlines() if l.startswith('[QG]')])"
```

## 改动历史

- 2026-10-15 QG 首派（VERIFY 相位质量门，用户指令）。

## 交付格式

- 证据文件全文要点 + 分级清单（每条：文件:行号 + 一句问题 + 建议处置）+ `[QG]` 判定行。
- 输出卫生（硬性）：每命令 stdout ≤30 行。
