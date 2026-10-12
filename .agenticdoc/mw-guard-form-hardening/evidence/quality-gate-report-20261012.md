# 质量门报告：mw-guard-form-hardening（20261012）

- key：`mw-guard-form-hardening`｜阶段：verify｜门禁轮次：**6 轮**（QG-A / QG-B / QG-A2 / QG-B2 / QG-A3 / QG-B3）
- 本文件是 done 前置（`advance_phase.py` 的 verify→done 门禁要求 `evidence/quality-gate-report-*.md` 存在）。

## 1. 轮次与判定

| 轮次 | task_key | 类型 | 判定 | 主要发现与处置 |
|---|---|---|---|---|
| QG-A #1 | `mwgf-qga-code-adversarial` | review | 静态未验证 | **PM 派发错误**（review 无 bash）；其中 F-6 由 PM 源码确认 = 真实缺陷 ⇒ T-17(A1) |
| QG-B #1 | `mwgf-qgb-evidence-chain` | research | **FAIL 7 阻断** | B-1 锚点漂移、B-2 AC-008 13/14、B-3 C-9、B-5 C-2/C-13、B-6 `forms_total` 0 命中、B-7 AC-010、B-4=C-12 ⇒ 全部处置（T-17/T-18 + AC 修订） |
| QG-A2 | `mwgf-qga2-code-adversarial` | research | 3/4 不可伪证 + 8 残余 + 1 前提被推翻 | biome「Fixed 1 file」前提撤回；新增 C-14…C-19 |
| QG-B2 | `mwgf-qgb2-evidence-recheck` | research | **FAIL 2 阻断**（7→2 收敛） | ① AC-011 VC 标签口径；② AC-010 文档同步 ⇒ 由 T-18（VC-MWGF-0NN 挂牌）与 PM（design 同步）关闭 |
| QG-A3 | `mwgf-qga3-final-adversarial` | research | **FAIL 7 项** | H-1 锚点（PM 的 §9.4 引用，已修）／H-2 CI 阻断（POSIX 下 `.exe` 用例必红）／H-3 混合 EOL heredoc 漏放／H-4 同行 `;` heredoc 漏放 ⇒ 全部由 **T-20** 修复；H-5/H-6/H-7 ⇒ C-22/C-23/C-24 |
| QG-B3 | `mwgf-qgb3-final-recheck` | research | **FAIL 1 阻断** | 唯一硬阻断 = H-1（同上）；AC-011 子判据不可测 ⇒ `[REVISED @ 2026-10-12]`；`corpus_py_md5_eq_ts_md5` 330→332、`task-frontmatter` 69→65（C-24）；发现 done 前置缺 `quality-gate-report`（本文件） |

## 2. 最终验收（PM 亲跑，末次）

| 项 | 结果 |
|---|---|
| TS 9 文件验收 | **433 passed / EXIT=0** |
| `[FORMS]` 形态门禁 | `total=79 covered=79 missing=0` |
| `[ANCHORS]` 锚点门禁 | `refs_total=77 resolved=77 unresolved=0 out_of_range=0 content_mismatch=0 unanchored_refs=0` |
| Python 4 文件 | **144 passed** |
| `npm run check` | EXIT 0（biome 1121 文件、0 修复） |

## 3. cutover 运行期验证（C-12 收口）

- 产物：全局扩展 `~/.pi/agent/extensions/agent-team-loop.js` **1,043,634 B**、sha256 `0FE644319ACB25F5B16F1CD29FF2559281C78A71518B27A99E3435DDC4E026E9`、8/8 新符号命中；`packages/coding-agent/dist` 与 `packages/multi-workers/dist` 同步重建。
- 装载：运行中 bundle 经独立读取确认含新审计实现与 `[WRITE_SCOPE_SUMMARY]`。
- 行为（冒烟 v3，research = shell+writeless 角色）：**6/6** 越面写入被拦（含 `bash -c` / `cmd.exe /c` / `powershell.exe -Command` 包装器），`blocked=true rule=scope detail=outside-allowed-surface`；4 个越面文件未创建；`[WRITE_SCOPE]` 6 条 + `[WRITE_SCOPE_SUMMARY]` 由 PM 在 `workers/mwgf-cutover-smoke3/trace.log` 复核。
- 附带证据：一次派发尝试被 dispatch 守卫拒绝（「52 个 key 只读可见、从未触碰」）⇒ ① 隔离 / ② 影响评估 在运行期成立。

## 4. 阻断项清账

| 来源 | 阻断 | 状态 |
|---|---|---|
| QG-B #1 | 7 项 | 已处置（T-17/T-18 + AC 修订），QG-B2 复核仅余 2 |
| QG-B2 | 2 项 | 已关闭（T-18 VC 挂牌；PM design 同步） |
| QG-A3 / QG-B3 | 锚点门禁红（PM 引入） | 已修复并复跑绿（77/77/0） |
| QG-A3 | H-2 CI 阻断 / H-3 / H-4 漏放 | 已由 T-20 修复（TS 9 文件 429→**434**，`mwds-t03` 59→63） |
| QG-B3 | AC-011 子判据不可测 | `[REVISED @ 2026-10-12]`（由 `VC-MWGF-0NN` 唯一标签承载） |
| QG-B3 | done 前置缺本文件 | 本文件即该项 |

## 5. 仍未解除（如实登记）

C-9（`.claude` 分发包副本无门禁，用户裁定后续 key）、C-19/C-20/C-21/C-22/C-23/C-25/C-26（登记不修）；11 个陈旧 pi 窗口待各自 `/reload`。
