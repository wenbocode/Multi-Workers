# Plan: mw-autopilot-advance-root

> Key: mw-autopilot-advance-root
> 依据：spec.md（AC-001..008）、design.md（D-101..D-107）

## 0. 策略

先改 framework（上游 + 项目副本同步），再改 mw（一致性校验 + `-X utf8`），最后 pi 扩展一行 + 回归。垂直顺序保证 AC-003 的 fail-loud 上线时已无合规项目会被误拒（D-107）。

## 1. 任务分解

| Task | 内容 | 关联 AC | 验证方式 |
|------|------|---------|---------|
| T1 | framework root 定位统一（`advance_phase.py` / `update_index.py` / `migrate_patterns.py` / `verify_project_memory.py`：cwd 专扫优先，`__file__` 回退） | AC-001 | framework 自带 pytest + 手工双 cwd 复算 |
| T2 | `detect_root.py` PROJECT_ROOT cwd 专扫优先 | AC-002 | `test_detect_root.py` + E2Feature 实跑 JSON |
| T3 | mirror 同步（`install.py --skip-codex` 触发 `sync_script_mirrors`）+ 上游 commit/push + E2Feature 同步 | AC-007 | `diff-installed.py` clean + 三副本 hash 一致 |
| T4 | mw `locate_platform_dir` 候选一致性校验 + `-X utf8`（两处） | AC-003/004/006 | `test_autopilot_conductor.py` pytest |
| T5 | pi 扩展 `agent-scripts.ts` `-X utf8` | AC-004 | `npm run check` + 扩展测试 |
| T6 | e2e hermetic（临时项目 spec→design exit 0；错误根无新目录）+ 回归收尾 | AC-005/008 | pytest + `./test.sh`（相关）+ `npm run check` + quality gate |

## 2. 依赖与顺序

```
T1 ─┬─> T3 ──> (E2Feature 同步) ──> T4 ──> T6
T2 ─┘                                  T5 ──> T6
```

T4 必须在 T3 之后（fail-loud 不能先于副本同步）。T5 与 T4 独立，可并行。

## 3. 风险控制

- 每个脚本改动用 write/edit（UTF-8），改动后 `python -m py_compile` + grep 关键锚点（P-003）。
- framework 改完先跑其自带 pytest，再同步 mirror。
- AC-007 的 push 若遇鉴权失败：保留本地 commit，记录为未决并向用户报告（不伪造完成）。

## 4. 验证清单（对应 AC）

- [ ] AC-001 framework 四脚本 cwd 优先 + 回退
- [ ] AC-002 detect_root PROJECT_ROOT
- [ ] AC-003 mw 候选一致性 + fail-loud
- [ ] AC-004 mw 两处 + pi 扩展 `-X utf8`
- [ ] AC-005 e2e 临时项目 advance 成功且不污染其它 `.agenticdoc`
- [ ] AC-006 负路径 fail-loud 可读
- [ ] AC-007 上游 push + 项目副本同步 + diff-installed clean
- [ ] AC-008 pytest + check 全绿无新增失败
