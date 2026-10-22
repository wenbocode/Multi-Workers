# plan — mw-console-storm-hardening

> date: 2026-10-15 · 输入: spec.md (AC-001..010) + design.md (D-001..D-006) + evidence/research/*4

## 0. 分派并行分析（波次 + 顺序）

| 波次 | 工作束 | 形态 | 依据 |
|------|--------|------|------|
| 1（三束并行） | W-01 Python 主体 / W-02 guard 包 / W-03 TS 入口 | coding worker ×3 | 写面互斥（mw.py+console_run.py vs 新 guard 目录 vs agent-team-loop），接口契约已在 design §2 冻结 |
| 2 | W-04 Python 测试双文件 | coding worker ×1 | 测试 import W-01/W-02 产物，避免实现期 API 漂移打穿；文件新建无冲突 |
| 3（串行尾） | W-05 文档 + 审计终稿 + 全量 verify | coding worker ×1 + PM | 依赖全部终态 |

（design 调研批 RQ-1/2/3 已完成：csg-t01/t01b OOM×2 转 PM 直执、csg-t02 完成、csg-t03 完成。）

## 1. 写入唯一性（冲突边界）

- **mw.py**：仅 W-01 可写（L0 段 + run-detached 子命令挂接，一次会话内串行）。
- `packages/multi-workers/console_run.py`（新）：仅 W-01。
- `packages/multi-workers/mw_console_guard/`（新目录）：仅 W-02。
- `packages/multi-workers/test_console_storm_guard.py`、`test_mw_console_guard.py`（新）：仅 W-04。
- `packages/coding-agent/src/extensions/agent-team-loop/**`：仅 W-03（shared/run-detached.ts 新 + 两激活点 + ui-bridge `/mw` 扩展 + suite 测试新文件）。
- `packages/multi-workers/README.md`、`UPDATE.md`、审计 evidence：仅 W-05。
- 禁止任何 worker 触碰 `packages/ai/src/models.generated.ts`、pi 核心（GC-2）、`.mw/dispatch.yml`。

## 2. 工作束清单

### W-01 — Python 主体：L0 除雷 + run-detached（Python·B0+B1）

- 独占写面: `packages/multi-workers/mw.py`、`packages/multi-workers/console_run.py`（新）
- ac_refs: AC-001, AC-003, AC-004, AC-007 · vc_refs: VC-001, VC-003, VC-004, VC-007(Python 侧)
- 依赖: 无 · 预计: 60-90min
- 契约: design D-001（cmd_start flags + serve-console.log 重定向）、D-002（两层结构、run_dir 文件集、marker/heartbeat schema、rc 哨兵 124/127、CLI 4 行输出、guard 注入 + `MW_CONSOLE_GUARD=0` 退出、posix `start_new_session`）
- 硬规则: Python 显式 `encoding="utf-8"` 写盘 / `os.replace` 原子写（P-003）；`subprocess` list-args 无 shell=True（AC-023 惯例）；timeout 致死用 taskkill /T（win32）/ kill(-pgid)（posix），对齐 mw-worker-tree-kill 先例

### W-02 — guard 包（Python·B0）

- 独占写面: `packages/multi-workers/mw_console_guard/`（sitecustomize.py + mw_console_guard.py）
- ac_refs: AC-005, AC-006, AC-007 · vc_refs: VC-005, VC-006, VC-007(guard 侧)
- 依赖: 无 · 预计: 30-45min
- 契约: design D-003——RQ-3 骨架为基线（evidence 文件含全文），保留 `_patched` 幂等/env 判据/fail-open/POSIX no-op；docstring 记录"creationflags 位置传参不受保护"限制

### W-03 — TS 入口（TS·B0+B1）

- 独占写面: `packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts`（新）+ pm-orchestrator.ts / worker-mode.ts 各一处注册 + ui-bridge.ts `/mw` 子命令 + suite 测试（新文件，faux provider）
- ac_refs: AC-008 · vc_refs: VC-008
- 依赖: 无 · 预计: 60-90min
- 契约: design D-005——双激活路径（registerRagTools 先例锚点 pm-orchestrator.ts:1769 / worker-mode.ts:2773）、activeToolsForType 仅 shell 角色、不进 TOOL_ALLOWLISTS、typebox schema additionalProperties:false、仅 `mw build` 收编
- 硬规则: erasable TS、top-level import、禁 inline `await import()`；不碰 pi 核心

### W-04 — Python 测试双文件（Python·B2）

- 独占写面: `packages/multi-workers/test_console_storm_guard.py`、`packages/multi-workers/test_mw_console_guard.py`（均新）
- ac_refs: 全 Python AC · vc_refs: VC-001..VC-007
- 依赖: W-01, W-02 终态 · 预计: 60-90min
- 断言清单: design §2 D-004 四组（grep 守卫 / cmd_start flags+重定向 / run-detached 集成含 marker·heartbeat·124 / guard 单测五路径含 platform seam）

### W-05 — 文档 + 审计终稿 + 全量 verify（B3）

- 独占写面: `packages/multi-workers/README.md`（新节）、`UPDATE.md`（矩阵行）、`.agenticdoc/<key>/evidence/research/design-spawn-site-audit-20261015.md`（终稿复核）、`evidence/runs/verify-*.md`（新建）
- ac_refs: AC-002, AC-009, AC-010 · vc_refs: VC-002, VC-009, VC-010
- 依赖: W-01..W-04 全部终态 · 预计: 45-60min
- verify 面: pytest 双测试文件 + 包既有套件对照基线；TS suite 新测试 + `npx tsgo --noEmit` + biome（禁 --write）；`mw run-detached` 冒烟（真实短命令 + marker 检查）；EnumWindows 差分实测（**含弹窗预告义务**：off 臂 ~10 窗/轮，跑前向用户报告）

## 3. 冲突点（共享排队，串行校验）

- `mw.py`：W-01 独占（波次 1 内无他人触碰）。
- `test_console_storm_guard.py` 由 W-04 独占创建；W-02 的 guard 单测**必须**落在 `test_mw_console_guard.py`（防同文件双写）。
- ui-bridge.ts / worker-mode.ts / pm-orchestrator.ts：W-03 独占；其他会话若在同文件有未提交改动，dispatch 前 `git status` 校验（跨窗口守卫兜底）。

## 4. 每束 DoD 与全量门禁

- W-01 DoD: `python -m pytest test_common.py -q` 零新增失败 + `python mw.py run-detached -- cmd /c exit` 冒烟产出合法 marker.json（rc=0）
- W-02 DoD: guard 目录两文件就位 + `python -c "import sys; sys.path.insert(0,'<guard>')&&import sitecustomize"` 激活/未激活行为符合 M6
- W-03 DoD: `node ../../node_modules/vitest/dist/cli.js --run test/extensions/<新测试>` 绿 + `npx tsgo --noEmit` 0 错 + biome 通过（对照 Windows 基线 89 环境失败不新增）
- W-04 DoD: 两个测试文件全绿（`print(..., flush=True)` + `-s`）
- W-05 DoD: 全量 `[VERIFY] VC-001..VC-010` 逐条落盘 + README/UPDATE 就位 + 审计表终稿与代码一致
- 全量门禁: `./test.sh`（根）不适用本 key（Python 包独立跑）；以 packages/multi-workers 全套 + coding-agent 相关 suite 对照基线为准

## 5. 风险与缓解（执行期）

- 研究 worker 双 OOM 前科 → 执行卡片一律带输出卫生约束（stdout ≤30 行/命令，长输出落文件）。
- 桌面弹窗实验 → W-05 EnumWindows 实测前向用户预告（本 plan 固化该义务）。
- TS 三文件（ui-bridge/worker-mode/pm-orchestrator）跨会话漂移 → W-03 派发前 PM 核对 `git status`。
- baseline：packages/coding-agent Windows 环境失败基线 76（2026-09-10 分类）——对照法判定，不追环境噪声。
