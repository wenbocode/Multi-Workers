# quality-gate-report-20261015 — mw-console-storm-hardening 收尾质量门

- 审读执行：`csg-qg-review`（type: review，只读角色，2026-10-15）；完整审计输出 = `evidence/review/qg-console-storm-20261015.md`（17,505 B / 99 行，判定行 `[QG] verdict=pass blockers=0 majors=0 minors=4 notes=5`）。本文件为门禁归档件，汇总判定与证据索引。
- 范围：AC-001..AC-010 全部验证闭环判定 + D-001..D-006 设计-实现一致性 + 硬规则合规 + 证据一致性抽核。

## 判定

**[QG] verdict=pass blockers=0 majors=0 minors=4 notes=5** —— 四层交付（L0 spawn 除雷 / L1 run-detached 监督进程 / L2 console guard / L3 文档+守卫测试 + TS 入口）通过质量门。

## 逐项结论（摘要，全文见审读输出 §1-§6）

1. **L0/L1 通过**：mw.py:519 flags=0x8000200 无 DETACHED 位、:512-516 serve-console.log 重定向；console_run.py:150-153 tmp+os.replace 原子写、:202-219 taskkill /T 树杀；GC-3/GC-4 成立。
2. **L2 通过**：OR 语义（:38-42）、fail-open（:45-53）、幂等（:20）、env+平台门（:62）；`del os, sys` 边界如实记录（note N3）。
3. **TS 通过**：写面全在 extensions/ 内（GC-2）；TOOL_ALLOWLISTS 未改且与 dispatch REGISTRY 一致（T-17 parity）；erasable、零 inline import、fail-open 不穿透、shell-only 门控真实接线（rag/tools.ts:400-406）。
4. **测试通过**：17+13 与 verify 文档计数/print 行/断言集互证；tokenize 剥注释无误伤方向风险；posix skip 为能力判据非一刀切。
5. **硬规则通过**：P-001 实体合规；W-05 Python 落盘替代裁定「实体合规、程序留痕」（minor F4，根因 render_task_md 逗号 bullet 渲染缺陷，移交框架）；显式 encoding 全覆盖。
6. **证据一致性一致**：README checklist 全断言集、UPDATE 矩阵行、双 CHANGELOG 追加位置正确；审计表行号抽核 6/6 全中。

## minor 处置（全部关闭）

- F1 run_dir TOCTOU → W-06 原子创建（mkdir exist_ok=False + FileExistsError 驱动 -N 重试）
- F2a/F2b heartbeat_s/timeout_min 负值无下界 → W-06 双侧正数校验（Python argparse type= + 后置检查；TS exclusiveMinimum + 运行时结构化错误；小数语义保持，VC-004a/b 原值复跑通过）
- F3 VC-008 argv_passthrough 恒真 → W-06 改逐元素精确断言
- F4 write_face 渲染缺陷 → 移交框架（P-041 收录）；W-05 绕闸留痕裁定实体合规
- N1/N2（mw.py 冗余别名导入 / serve_log_fh 未关闭）→ PM 直执修复，17 passed 复跑 + ast 校验
- N3/N5 → 记录在案不改（design 已载权衡）

## 收尾验证（QG 后，2026-10-15）

- W-06 快修复跑：Python 17 passed + TS 13 passed + tsgo 0 + biome 0（workers/csg-w06-qg-quickfix/report.md，[VERIFY] VC-003/004a/004b/008 复跑行在案）
- 提交：13a0ce4de / 4980da301 / 3c02d7227 / bf2547cce（混合文件索引级重建，foreign marker 抽查 absent）
- 运行时 bundle 已由并行窗口 build（用户确认）；工作树残留 ` M dist/...js` 归并行会话
